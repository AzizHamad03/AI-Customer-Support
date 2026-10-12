from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from threading import Barrier
from unittest.mock import patch

from django.conf import settings
from django.db import (
    OperationalError,
    close_old_connections,
    connections,
)
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse

from support.ai.tools import DRAFT_KEY, execute_tool
from support.models import Message, SupportTicket

from django.contrib.auth.models import AnonymousUser

TICKET_FIELDS = {
    "contact_email": "customer@example.com",
    "contact_phone": "",
    "description": "My delivery arrived with a damaged item.",
    "order_reference": "DEMO-123",
}


class TicketSaveFailureTests(TestCase):
    def test_failed_save_rolls_back_ticket_and_retry_succeeds(self):
        self.client.post(
            reverse("support:ticket_request"),
            TICKET_FIELDS,
        )

        request_id = self.client.session[DRAFT_KEY]["request_id"]

        # Fail after the ticket insert, when its conversation
        # message is being saved. Both writes must roll back.
        with patch(
            "support.services.tickets.Message.objects.create",
            side_effect=OperationalError("Simulated write failure"),
        ):
            with self.assertLogs(
                "support.views.customer_tickets",
                level="ERROR",
            ):
                response = self.client.post(
                    reverse("support:ticket_confirm"),
                    {
                        "confirm": "yes",
                        "request_id": request_id,
                    },
                )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(SupportTicket.objects.count(), 0)
        self.assertEqual(Message.objects.count(), 0)
        self.assertContains(
            response,
            "The ticket could not be saved.",
            status_code=503,
        )

        # Retrying the same confirmed draft should succeed.
        response = self.client.post(
            reverse("support:ticket_confirm"),
            {
                "confirm": "yes",
                "request_id": request_id,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(SupportTicket.objects.count(), 1)
        self.assertEqual(Message.objects.count(), 1)

        ticket = SupportTicket.objects.get()

        self.assertEqual(str(ticket.request_id), request_id)
        self.assertEqual(
            ticket.contact_email,
            TICKET_FIELDS["contact_email"],
        )
        self.assertIn(ticket.reference, Message.objects.get().content)


class ConcurrentTicketConfirmationTests(TransactionTestCase):
    def test_simultaneous_confirmations_create_one_ticket(self):
        self.client.post(
            reverse("support:ticket_request"),
            TICKET_FIELDS,
        )

        session_key = self.client.session.session_key
        request_id = self.client.session[DRAFT_KEY]["request_id"]
        barrier = Barrier(2)

        SessionStore = import_module(
            settings.SESSION_ENGINE
        ).SessionStore

        def confirm():
            close_old_connections()

            try:
                # Bound waits if a locking regression occurs.
                with connections["default"].cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")

                request = RequestFactory().post(
                    reverse("support:ticket_confirm"),
                    {
                        "confirm": "yes",
                        "request_id": request_id,
                    },
                )
                request.session = SessionStore(
                    session_key=session_key
                )
                request.user = AnonymousUser()

                # Load the same saved draft in both connections.
                request.session[DRAFT_KEY]
                barrier.wait(timeout=10)

                return execute_tool(
                    "create_support_ticket",
                    {},
                    request=request,
                )
            finally:
                connections["default"].close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(confirm),
                executor.submit(confirm),
            ]
            results = [
                future.result(timeout=20)
                for future in futures
            ]

        self.assertEqual(results[0], results[1])
        self.assertEqual(SupportTicket.objects.count(), 1)
        self.assertEqual(Message.objects.count(), 1)

        ticket = SupportTicket.objects.get()

        self.assertEqual(
            results[0]["reference"],
            ticket.reference,
        )
        self.assertEqual(
            ticket.description,
            TICKET_FIELDS["description"],
        )