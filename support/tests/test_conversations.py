from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from support.models import Conversation, Message, SupportTicket
from support.services.accounts import ACTIVE_CONVERSATION_KEY


class ConversationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="conversation-owner"
        )
        self.other = get_user_model().objects.create_user(
            username="other-owner"
        )
        self.first = Conversation.objects.create(user=self.user)
        self.second = Conversation.objects.create(user=self.user)
        self.foreign = Conversation.objects.create(user=self.other)

        Message.objects.create(
            conversation=self.first,
            role=Message.Role.USER,
            content="Shipping question",
        )
        Message.objects.create(
            conversation=self.second,
            role=Message.Role.USER,
            content="Return question",
        )
        Message.objects.create(
            conversation=self.foreign,
            role=Message.Role.USER,
            content="Private foreign question",
        )

        self.client.force_login(self.user)

    def test_list_only_shows_owned_conversations(self):
        response = self.client.get(
            reverse("support:conversation_list")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Shipping question")
        self.assertContains(response, "Return question")
        self.assertNotContains(response, "Private foreign question")

    def test_new_conversation_preserves_old_messages_and_tickets(self):
        ticket = SupportTicket.objects.create(
            conversation=self.first,
            contact_email="demo@example.com",
            description="Please investigate my delivery.",
        )
        session = self.client.session
        session["support_ticket_draft"] = {"test": "old draft"}
        session.save()

        previous_ids = set(
            Conversation.objects.filter(user=self.user)
            .values_list("pk", flat=True)
        )

        response = self.client.post(
            reverse("support:conversation_new")
        )

        self.assertRedirects(response, reverse("support:chat"))

        active_id = self.client.session[ACTIVE_CONVERSATION_KEY]
        self.assertNotIn(active_id, previous_ids)
        self.assertTrue(
            Conversation.objects.filter(
                pk=active_id,
                user=self.user,
                session_key__isnull=True,
            ).exists()
        )
        self.assertNotIn(
            "support_ticket_draft",
            self.client.session,
        )

        history = self.client.get(
            reverse("support:chat_api")
        ).json()
        self.assertEqual(history["messages"], [])

        self.assertTrue(
            Message.objects.filter(conversation=self.first).exists()
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.conversation_id, self.first.pk)

    def test_open_loads_selected_history_and_clears_draft(self):
        session = self.client.session
        session["support_ticket_draft"] = {"test": "old draft"}
        session.save()

        self.client.post(
            reverse(
                "support:conversation_open",
                args=[self.first.pk],
            )
        )

        history = self.client.get(
            reverse("support:chat_api")
        ).json()

        self.assertEqual(history["conversation_id"], self.first.pk)
        self.assertEqual(
            history["messages"][0]["content"],
            "Shipping question",
        )
        self.assertNotIn(
            "support_ticket_draft",
            self.client.session,
        )

    def test_foreign_conversation_cannot_be_opened(self):
        session = self.client.session
        session[ACTIVE_CONVERSATION_KEY] = self.first.pk
        session.save()

        response = self.client.post(
            reverse(
                "support:conversation_open",
                args=[self.foreign.pk],
            )
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            self.client.session[ACTIVE_CONVERSATION_KEY],
            self.first.pk,
        )

    def test_new_and_open_require_post(self):
        self.assertEqual(
            self.client.get(
                reverse("support:conversation_new")
            ).status_code,
            405,
        )
        self.assertEqual(
            self.client.get(
                reverse(
                    "support:conversation_open",
                    args=[self.first.pk],
                )
            ).status_code,
            405,
        )

    def test_guest_is_redirected_to_login(self):
        self.client.logout()

        for name in ["conversation_list", "conversation_new"]:
            response = self.client.get(reverse(f"support:{name}"))
            self.assertEqual(response.status_code, 302)
            self.assertIn("/accounts/login/", response.url)

    def test_new_conversation_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        response = client.post(
            reverse("support:conversation_new")
        )

        self.assertEqual(response.status_code, 403)

    def test_stale_tab_cannot_send_into_another_conversation(self):
        session = self.client.session
        session[ACTIVE_CONVERSATION_KEY] = self.second.pk
        session.save()

        previous_count = Message.objects.count()

        response = self.client.post(
            reverse("support:chat_api"),
            {
                "content": "Question from an old tab",
                "conversation_id": self.first.pk,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Message.objects.count(), previous_count)