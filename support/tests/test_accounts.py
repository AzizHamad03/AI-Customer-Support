from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from support.models import Conversation, Message, SupportTicket
from support.services.accounts import ACTIVE_CONVERSATION_KEY


PASSWORD = "Demo-Test-Password!739"


class AccountTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="customer-one",
            password=PASSWORD,
        )
        self.other = get_user_model().objects.create_user(
            username="customer-two",
            password=PASSWORD,
        )

    def guest_history(self):
        self.client.get(reverse("support:chat_api"))
        conversation = Conversation.objects.get(
            session_key=self.client.session.session_key
        )
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.USER,
            content="My guest question",
        )
        return conversation

    def test_signup_transfers_guest_history_without_staff_access(self):
        conversation = self.guest_history()

        response = self.client.post(
            reverse("support:signup"),
            {
                "username": "new-customer",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )

        self.assertRedirects(response, reverse("support:chat"))

        user = get_user_model().objects.get(
            username="new-customer"
        )
        conversation.refresh_from_db()

        self.assertEqual(conversation.user_id, user.pk)
        self.assertIsNone(conversation.session_key)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

        history = self.client.get(
            reverse("support:chat_api")
        ).json()["messages"]
        self.assertEqual(history[0]["content"], "My guest question")

    def test_login_transfers_guest_tickets(self):
        conversation = self.guest_history()
        ticket = SupportTicket.objects.create(
            conversation=conversation,
            contact_email="demo@example.com",
            description="My delivery needs investigation.",
        )

        self.client.post(
            reverse("support:login"),
            {
                "username": self.user.username,
                "password": PASSWORD,
            },
        )

        conversation.refresh_from_db()
        self.assertEqual(conversation.user_id, self.user.pk)
        self.assertEqual(
            self.client.get(
                reverse("support:ticket_detail", args=[ticket.pk])
            ).status_code,
            200,
        )

    def test_history_returns_on_another_browser(self):
        conversation = Conversation.objects.create(user=self.user)
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.USER,
            content="Saved account question",
        )

        second_browser = Client()
        second_browser.login(
            username=self.user.username,
            password=PASSWORD,
        )

        history = second_browser.get(
            reverse("support:chat_api")
        ).json()["messages"]

        self.assertEqual(
            history[0]["content"],
            "Saved account question",
        )

    def test_foreign_conversation_id_and_ticket_are_rejected(self):
        foreign = Conversation.objects.create(user=self.other)
        Message.objects.create(
            conversation=foreign,
            role=Message.Role.USER,
            content="Private question",
        )
        ticket = SupportTicket.objects.create(
            conversation=foreign,
            contact_email="other@example.com",
            description="Another customer's private issue.",
        )

        self.client.force_login(self.user)
        session = self.client.session
        session[ACTIVE_CONVERSATION_KEY] = foreign.pk
        session.save()

        history = self.client.get(
            reverse("support:chat_api")
        ).json()["messages"]

        self.assertEqual(history, [])
        self.assertEqual(
            self.client.get(
                reverse("support:ticket_detail", args=[ticket.pk])
            ).status_code,
            404,
        )

    def test_logout_does_not_expose_account_history_to_guest(self):
        conversation = Conversation.objects.create(user=self.user)
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.USER,
            content="Private account history",
        )

        self.client.force_login(self.user)
        self.client.get(reverse("support:chat_api"))
        self.client.post(reverse("support:logout"))

        history = self.client.get(
            reverse("support:chat_api")
        ).json()["messages"]

        self.assertEqual(history, [])
        self.assertTrue(
            Message.objects.filter(conversation=conversation).exists()
        )

    def test_invalid_password_does_not_transfer_guest_history(self):
        conversation = self.guest_history()

        response = self.client.post(
            reverse("support:login"),
            {
                "username": self.user.username,
                "password": "wrong-password",
            },
        )

        self.assertEqual(response.status_code, 200)
        conversation.refresh_from_db()
        self.assertIsNone(conversation.user_id)