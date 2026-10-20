from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from support.models import Conversation, SupportTicket


class TicketViewRulesTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.customer = User.objects.create_user(
            username="view-rules-customer",
        )
        self.staff = User.objects.create_user(
            username="view-rules-staff",
            is_staff=True,
        )

        conversation = Conversation.objects.create(
            user=self.customer,
        )
        self.ticket = SupportTicket.objects.create(
            conversation=conversation,
            contact_email="customer@example.com",
            description="Please investigate my damaged delivery.",
        )

    def test_customer_ticket_pages_reject_unsupported_methods(self):
        self.client.force_login(self.customer)

        cases = [
            (
                reverse("support:ticket_request"),
                "PUT",
            ),
            (
                reverse("support:ticket_confirm"),
                "DELETE",
            ),
            (
                reverse("support:ticket_detail", args=[self.ticket.pk]),
                "POST",
            ),
            (
                reverse("support:customer_ticket_list"),
                "POST",
            ),
        ]

        for url, method in cases:
            with self.subTest(url=url, method=method):
                response = self.client.generic(method, url)
                self.assertEqual(response.status_code, 405)

        self.assertEqual(SupportTicket.objects.count(), 1)

    def test_staff_ticket_pages_reject_unsupported_methods(self):
        self.client.force_login(self.staff)

        cases = [
            (
                reverse("support:staff_ticket_list"),
                "POST",
            ),
            (
                reverse(
                    "support:staff_ticket_detail",
                    args=[self.ticket.pk],
                ),
                "DELETE",
            ),
        ]

        for url, method in cases:
            with self.subTest(url=url, method=method):
                response = self.client.generic(method, url)
                self.assertEqual(response.status_code, 405)

        self.ticket.refresh_from_db()
        self.assertEqual(
            self.ticket.status,
            SupportTicket.Status.OPEN,
        )

    def test_guest_staff_redirect_uses_application_login(self):
        staff_url = reverse("support:staff_dashboard")
        login_url = reverse("support:login")
        query = urlencode({"next": staff_url})

        response = self.client.get(staff_url)

        self.assertRedirects(
            response,
            f"{login_url}?{query}",
        )

    def test_customer_staff_redirect_does_not_loop(self):
        self.client.force_login(self.customer)

        response = self.client.get(
            reverse("support:staff_dashboard"),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.redirect_chain), 1)
        self.assertTemplateUsed(
            response,
            "support/login.html",
        )

    def test_guest_without_session_sees_no_account_tickets(self):
        response = self.client.get(
            reverse("support:customer_ticket_list"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            self.ticket.reference,
        )

        response = self.client.get(
            reverse(
                "support:ticket_detail",
                args=[self.ticket.pk],
            ),
        )

        self.assertEqual(response.status_code, 404)