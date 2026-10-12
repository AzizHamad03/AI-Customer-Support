from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from support.ai.tools import (
    DRAFT_KEY,
    ToolPermissionError,
    execute_tool,
)
from support.models import (
    Conversation,
    KnowledgeDocument,
    Message,
    MessageCitation,
    SupportTicket,
)
from support.services.accounts import attach_guest_conversation
from support.services.documents import create_document


PASSWORD = "Demo-Test-Password!739"

TICKET_FIELDS = {
    "contact_email": "customer@example.com",
    "contact_phone": "",
    "description": "My delivery arrived with a damaged item.",
    "order_reference": "DEMO-123",
}


class AccountPermissionTests(TestCase):
    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)

        setting = override_settings(MEDIA_ROOT=media.name)
        setting.enable()
        self.addCleanup(setting.disable)

        User = get_user_model()

        self.customer = User.objects.create_user(
            username="permission-customer",
            password=PASSWORD,
        )
        self.other = User.objects.create_user(
            username="permission-other",
            password=PASSWORD,
        )
        self.staff = User.objects.create_user(
            username="permission-staff",
            password=PASSWORD,
            is_staff=True,
        )

        self.document = create_document(
            title="Permission test policy",
            category="general",
            file=SimpleUploadedFile(
                "policy.txt",
                b"Demo policy text.",
            ),
            uploaded_by=self.staff,
        )

    def test_guest_login_preserves_messages_citations_and_ticket(self):
        self.client.get(reverse("support:chat_api"))

        old_session_key = self.client.session.session_key
        conversation = Conversation.objects.get(
            session_key=old_session_key
        )

        message = Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content="Shipping costs SAR 25.",
        )
        citation = MessageCitation.objects.create(
            message=message,
            chunk=None,
            source_key="S1",
            document_title="Shipping policy",
            document_version=1,
            page_number=1,
            source_text="Shipping costs SAR 25.",
            is_txt=True,
        )
        ticket = SupportTicket.objects.create(
            conversation=conversation,
            **TICKET_FIELDS,
        )

        self.client.post(
            reverse("support:login"),
            {
                "username": self.customer.username,
                "password": PASSWORD,
            },
        )

        conversation.refresh_from_db()
        ticket.refresh_from_db()
        citation.refresh_from_db()

        self.assertEqual(conversation.user_id, self.customer.pk)
        self.assertIsNone(conversation.session_key)
        self.assertNotEqual(
            self.client.session.session_key,
            old_session_key,
        )
        self.assertEqual(ticket.conversation_id, conversation.pk)
        self.assertEqual(citation.message_id, message.pk)

        history = self.client.get(
            reverse("support:chat_api")
        ).json()["messages"]

        self.assertEqual(history[0]["content"], "Shipping costs SAR 25.")
        self.assertEqual(
            history[0]["citations"][0]["text"],
            "Shipping costs SAR 25.",
        )
        self.assertEqual(
            self.client.get(
                reverse("support:ticket_detail", args=[ticket.pk])
            ).status_code,
            200,
        )

        # A second account cannot reclaim the transferred guest history.
        self.assertIsNone(
            attach_guest_conversation(old_session_key, self.other)
        )
        conversation.refresh_from_db()
        self.assertEqual(conversation.user_id, self.customer.pk)

    def test_authenticated_ticket_confirmation_is_idempotent(self):
        self.client.force_login(self.customer)

        self.client.post(
            reverse("support:ticket_request"),
            TICKET_FIELDS,
        )

        draft = self.client.session[DRAFT_KEY]
        confirmation = {
            "confirm": "yes",
            "request_id": draft["request_id"],
        }

        self.client.post(
            reverse("support:ticket_confirm"),
            confirmation,
        )
        self.client.post(
            reverse("support:ticket_confirm"),
            confirmation,
        )

        self.assertEqual(SupportTicket.objects.count(), 1)

        ticket = SupportTicket.objects.select_related(
            "conversation"
        ).get()

        self.assertEqual(
            ticket.conversation.user_id,
            self.customer.pk,
        )
        self.assertEqual(
            ticket.contact_email,
            TICKET_FIELDS["contact_email"],
        )

    def test_authenticated_customer_cannot_confirm_foreign_draft(self):
        foreign = Conversation.objects.create(user=self.other)
        self.client.force_login(self.customer)

        session = self.client.session
        session[DRAFT_KEY] = {
            "request_id": "00000000-0000-4000-8000-000000000001",
            "conversation_id": foreign.pk,
            "fields": TICKET_FIELDS,
        }
        session.save()

        request = RequestFactory().post(
            reverse("support:ticket_confirm"),
            {
                "confirm": "yes",
                "request_id": session[DRAFT_KEY]["request_id"],
            },
        )
        request.user = self.customer
        request.session = session

        with self.assertRaises(ToolPermissionError):
            execute_tool(
                "create_support_ticket",
                {},
                request=request,
            )

        self.assertEqual(SupportTicket.objects.count(), 0)

    def test_signup_cannot_grant_staff_permissions(self):
        self.client.post(
            reverse("support:signup"),
            {
                "username": "ordinary-signup",
                "password1": PASSWORD,
                "password2": PASSWORD,
                "is_staff": "true",
                "is_superuser": "true",
            },
        )

        user = get_user_model().objects.get(
            username="ordinary-signup"
        )

        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

        response = self.client.get(
            reverse("support:staff_dashboard")
        )
        self.assertEqual(response.status_code, 302)

    def test_guest_and_customer_cannot_delete_staff_document(self):
        for user in [None, self.customer]:
            self.client.logout()

            if user is not None:
                self.client.force_login(user)

            with self.subTest(user=user):
                response = self.client.post(
                    reverse(
                        "support:document_delete",
                        args=[self.document.pk],
                    ),
                    {"confirm": "yes"},
                )

                self.assertEqual(response.status_code, 302)
                self.assertTrue(
                    KnowledgeDocument.objects.filter(
                        pk=self.document.pk
                    ).exists()
                )
                self.assertTrue(
                    self.document.file.storage.exists(
                        self.document.file.name
                    )
                )

    def test_customer_cannot_view_staff_pages_or_update_ticket(self):
        conversation = Conversation.objects.create(user=self.customer)
        ticket = SupportTicket.objects.create(
            conversation=conversation,
            **TICKET_FIELDS,
        )

        self.client.force_login(self.customer)

        for name in [
            "staff_dashboard",
            "document_list",
            "staff_ticket_list",
        ]:
            with self.subTest(page=name):
                response = self.client.get(
                    reverse(f"support:{name}")
                )
                self.assertEqual(response.status_code, 302)

        response = self.client.post(
            reverse(
                "support:staff_ticket_detail",
                args=[ticket.pk],
            ),
            {"status": SupportTicket.Status.RESOLVED},
        )

        self.assertEqual(response.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, SupportTicket.Status.OPEN)

    def test_staff_can_login_through_customer_login_page(self):
        response = self.client.post(
            reverse("support:login"),
            {
                "username": self.staff.username,
                "password": PASSWORD,
            },
        )

        self.assertRedirects(
            response,
            reverse("support:staff_dashboard"),
        )
        self.assertEqual(
            self.client.get(
                reverse("support:document_list")
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse("support:staff_ticket_list")
            ).status_code,
            200,
        )