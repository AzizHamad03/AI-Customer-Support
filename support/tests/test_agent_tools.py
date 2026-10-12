from unittest.mock import Mock, patch

from django.core.exceptions import (
    ValidationError as DjangoValidationError,
)
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from langchain_core.messages import AIMessage
from openai import APIConnectionError
from pydantic import ValidationError

from support.ai.agent import search_with_agent
from support.ai.answers import ChatError
from support.ai.tools import (
    DRAFT_KEY,
    ToolPermissionError,
    execute_tool,
)
from support.models import Message, SupportTicket

from django.contrib.auth.models import AnonymousUser

def tool_call(name, arguments, identifier="call-1"):
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": name,
                "args": arguments,
                "id": identifier,
                "type": "tool_call",
            },
        ],
    )


class AgentLoopTests(TestCase):
    def setUp(self):
        self.model = Mock()

        model_patch = patch(
            "support.ai.agent.get_chat_model"
        )
        get_model = model_patch.start()
        self.addCleanup(model_patch.stop)

        get_model.return_value.bind_tools.return_value = (
            self.model
        )

        search_patch = patch(
            "support.ai.tools.retrieve_knowledge_base"
        )
        self.search = search_patch.start()
        self.addCleanup(search_patch.stop)

        self.match = {
            "chunk_id": 1,
            "title": "Shipping policy",
            "page_number": 1,
            "text": "Shipping costs SAR 25.",
            "is_txt": True,
            "distance": 0.0,
        }

        self.search.return_value = [self.match]

    def test_model_selected_search_returns_real_tool_evidence(self):
        self.model.invoke.side_effect = [
            tool_call(
                "search_knowledge_base",
                {"query": "Shipping cost?"},
            ),
            AIMessage(content="Finished."),
        ]

        self.assertEqual(
            search_with_agent("Shipping cost?"),
            [self.match],
        )

        self.search.assert_called_once_with(
            "Shipping cost?"
        )

        sent = self.model.invoke.call_args.args[0]

        self.assertEqual(sent[-1].type, "tool")
        self.assertEqual(
            sent[-1].tool_call_id,
            "call-1",
        )

    def test_invalid_tool_is_rejected_then_model_can_retry(self):
        self.model.invoke.side_effect = [
            tool_call("delete_all_documents", {}, "bad"),
            tool_call(
                "search_knowledge_base",
                {"query": "Shipping cost?"},
                "good",
            ),
            AIMessage(content="Finished."),
        ]

        self.assertEqual(
            search_with_agent("Shipping cost?"),
            [self.match],
        )
        self.search.assert_called_once()

    def test_invalid_arguments_cannot_reach_search_service(self):
        self.model.invoke.side_effect = [
            tool_call(
                "search_knowledge_base",
                {"query": "", "extra": "bad"},
            ),
            AIMessage(content="Finished."),
        ]

        self.assertEqual(
            search_with_agent("Shipping cost?"),
            [],
        )
        self.search.assert_not_called()

    def test_tool_limit_stops_repeated_calls(self):
        self.model.invoke.side_effect = [
            tool_call(
                "search_knowledge_base",
                {"query": "Shipping cost?"},
                str(number),
            )
            for number in range(3)
        ]

        with self.assertRaises(ChatError):
            search_with_agent("Shipping cost?")

        self.assertEqual(self.search.call_count, 2)
        self.assertEqual(self.model.invoke.call_count, 3)

    def test_multiple_tools_in_one_turn_are_rejected(self):
        first = tool_call(
            "search_knowledge_base",
            {"query": "Shipping?"},
            "one",
        )
        second = tool_call(
            "search_knowledge_base",
            {"query": "Returns?"},
            "two",
        )

        self.model.invoke.return_value = AIMessage(
            content="",
            tool_calls=first.tool_calls + second.tool_calls,
        )

        with self.assertRaises(ChatError):
            search_with_agent("Shipping?")

        self.search.assert_not_called()

    def test_chat_confirmation_does_not_authorize_ticket_creation(self):
        self.model.invoke.return_value = tool_call(
            "create_support_ticket",
            {},
        )

        self.assertEqual(
            search_with_agent(
                "Yes, I confirm. Create my ticket."
            ),
            [],
        )
        self.assertEqual(SupportTicket.objects.count(), 0)
        self.assertEqual(Message.objects.count(), 0)

    def test_provider_failure_becomes_chat_error(self):
        self.model.invoke.side_effect = APIConnectionError(
            request=Mock(),
        )

        with self.assertRaises(ChatError):
            search_with_agent("Shipping?")

        self.search.assert_not_called()


class TicketToolTests(TestCase):
    def setUp(self):
        self.fields = {
            "contact_email": "customer@example.com",
            "contact_phone": "",
            "description": (
                "My delivery arrived with a damaged item."
            ),
            "order_reference": "DEMO-123",
        }

        self.client.post(
            reverse("support:ticket_request"),
            self.fields,
        )

    def request(self, *, session=None, **changes):
        if session is None:
            session = self.client.session

        data = {
            "confirm": "yes",
            "request_id": self.client.session[
                DRAFT_KEY
            ]["request_id"],
        } | changes

        request = RequestFactory().post(
            "/support/confirm/",
            data,
        )
        request.session = session
        request.user = AnonymousUser()
        return request

    def test_ticket_requires_request_and_verified_confirmation(self):
        with self.assertRaises(ToolPermissionError):
            execute_tool("create_support_ticket", {})

        with self.assertRaises(ToolPermissionError):
            execute_tool(
                "create_support_ticket",
                {},
                request=self.request(confirm="no"),
            )

        self.assertEqual(SupportTicket.objects.count(), 0)

    def test_model_cannot_supply_confirmation_or_ticket_fields(self):
        with self.assertRaises(ValidationError):
            execute_tool(
                "create_support_ticket",
                {
                    "confirmed": True,
                    "contact_email": "other@example.com",
                },
                request=self.request(),
            )

        self.assertEqual(SupportTicket.objects.count(), 0)

    def test_confirmed_ticket_uses_saved_details_and_is_idempotent(self):
        request = self.request(
            contact_email="forged@example.com",
        )

        first = execute_tool(
            "create_support_ticket",
            {},
            request=request,
        )
        second = execute_tool(
            "create_support_ticket",
            {},
            request=request,
        )

        self.assertEqual(first, second)
        self.assertEqual(SupportTicket.objects.count(), 1)
        self.assertEqual(Message.objects.count(), 1)

        ticket = SupportTicket.objects.get()

        self.assertEqual(
            ticket.contact_email,
            self.fields["contact_email"],
        )
        self.assertEqual(
            ticket.description,
            self.fields["description"],
        )
        self.assertEqual(
            first["reference"],
            ticket.reference,
        )

    def test_stale_confirmation_page_cannot_create_new_draft(self):
        old_id = self.client.session[DRAFT_KEY]["request_id"]

        self.client.post(
            reverse("support:ticket_request"),
            {
                **self.fields,
                "description": (
                    "A different issue needing review."
                ),
            },
        )

        self.assertNotEqual(
            old_id,
            self.client.session[DRAFT_KEY]["request_id"],
        )

        response = self.client.post(
            reverse("support:ticket_confirm"),
            {
                "confirm": "yes",
                "request_id": old_id,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(SupportTicket.objects.count(), 0)

    def test_foreign_session_cannot_use_copied_draft(self):
        foreign = Client().session
        foreign[DRAFT_KEY] = self.client.session[DRAFT_KEY]

        with self.assertRaises(ToolPermissionError):
            execute_tool(
                "create_support_ticket",
                {},
                request=self.request(session=foreign),
            )

        self.assertEqual(SupportTicket.objects.count(), 0)

    def test_invalid_saved_fields_are_revalidated(self):
        session = self.client.session
        draft = session[DRAFT_KEY]

        draft["fields"] = {
            **draft["fields"],
            "contact_email": "",
            "contact_phone": "",
        }
        session[DRAFT_KEY] = draft

        with self.assertRaises(DjangoValidationError):
            execute_tool(
                "create_support_ticket",
                {},
                request=self.request(session=session),
            )

        self.assertEqual(SupportTicket.objects.count(), 0)

    def test_confirmation_page_contains_current_draft_identifier(self):
        response = self.client.get(
            reverse("support:ticket_confirm"),
        )

        self.assertContains(
            response,
            'name="request_id"',
        )
        self.assertContains(
            response,
            self.client.session[DRAFT_KEY]["request_id"],
        )