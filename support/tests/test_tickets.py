from uuid import uuid4

from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from support.models import Conversation, Message, SupportTicket
from support.services.tickets import create_support_ticket


class TicketTests(TestCase):
    def setUp(self):
        self.conversation = Conversation.objects.create(
            session_key="ticket-test-session"
        )
        self.fields = {
            "contact_email": "customer@example.com",
            "contact_phone": "",
            "description": "My delivery arrived with a damaged item.",
            "order_reference": "DEMO-123",
        }

    def test_repeated_request_creates_one_ticket(self):
        request_id = uuid4()

        first = create_support_ticket(
            conversation_id=self.conversation.pk,
            request_id=request_id,
            fields=self.fields,
        )
        second = create_support_ticket(
            conversation_id=self.conversation.pk,
            request_id=request_id,
            fields=self.fields,
        )

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(SupportTicket.objects.count(), 1)
        self.assertEqual(Message.objects.count(), 1)

    def test_contact_method_is_required(self):
        fields = {
            **self.fields,
            "contact_email": "",
            "contact_phone": "",
        }

        with self.assertRaises(ValidationError):
            create_support_ticket(
                conversation_id=self.conversation.pk,
                request_id=uuid4(),
                fields=fields,
            )

        self.assertEqual(SupportTicket.objects.count(), 0)

    def test_review_does_not_create_ticket(self):
        self.client.post(
            reverse("support:ticket_request"),
            self.fields,
        )
        self.client.get(reverse("support:ticket_confirm"))

        self.assertEqual(SupportTicket.objects.count(), 0)

    def test_confirmation_and_session_isolation(self):
        self.client.post(
            reverse("support:ticket_request"),
            self.fields,
        )

        self.client.post(
            reverse("support:ticket_confirm"),
            {
                "confirm": "yes",
                "request_id": self.client.session[
                    "support_ticket_draft"
                ]["request_id"],
            },
        )
        ticket = SupportTicket.objects.get()

        # Repeating the confirmation returns the existing ticket.
        self.client.post(
            reverse("support:ticket_confirm"),
            {
                "confirm": "yes",
                "request_id": self.client.session[
                    "support_ticket_draft"
                ]["request_id"],
            },
        )
        self.assertEqual(SupportTicket.objects.count(), 1)

        own_response = self.client.get(
            reverse("support:ticket_detail", args=[ticket.pk])
        )
        other_response = Client().get(
            reverse("support:ticket_detail", args=[ticket.pk])
        )

        self.assertEqual(own_response.status_code, 200)
        self.assertEqual(other_response.status_code, 404)