from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from support.models import Conversation, Message, SupportTicket


class StaffTicketTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="ticket-staff",
            password="test-only-password",
            is_staff=True,
        )

        conversation = Conversation.objects.create(
            session_key="staff-ticket-test"
        )

        self.ticket = SupportTicket.objects.create(
            conversation=conversation,
            contact_email="customer@example.com",
            description="My package arrived with a damaged item.",
            order_reference="DEMO-123",
        )

        Message.objects.create(
            conversation=conversation,
            role=Message.Role.USER,
            content="My package is damaged.",
        )

    def test_staff_pages_require_staff_access(self):
        url = reverse("support:staff_ticket_list")
        self.assertEqual(self.client.get(url).status_code, 302)

        ordinary_user = get_user_model().objects.create_user(
            username="ordinary-user",
            password="test-only-password",
        )
        self.client.force_login(ordinary_user)
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_search_and_status_filter(self):
        self.client.force_login(self.staff)
        url = reverse("support:staff_ticket_list")

        response = self.client.get(
            url,
            {"q": "DEMO-123", "status": "open"},
        )
        self.assertContains(response, self.ticket.reference)

        response = self.client.get(
            url,
            {"q": "DEMO-123", "status": "resolved"},
        )
        self.assertNotContains(response, self.ticket.reference)

    def test_detail_shows_linked_conversation(self):
        self.client.force_login(self.staff)

        response = self.client.get(
            reverse(
                "support:staff_ticket_detail",
                args=[self.ticket.pk],
            )
        )
        self.assertContains(response, "My package is damaged.")

    def test_status_update_and_invalid_status(self):
        self.client.force_login(self.staff)
        url = reverse(
            "support:staff_ticket_detail",
            args=[self.ticket.pk],
        )

        response = self.client.post(url, {"status": "in_progress"})
        self.assertEqual(response.status_code, 302)

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, "in_progress")

        response = self.client.post(url, {"status": "invalid"})
        self.assertEqual(response.status_code, 200)

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, "in_progress")