from django.core.exceptions import ValidationError
from pydantic import BaseModel, ConfigDict, Field

from support.forms import SupportTicketForm
from support.models import Conversation
from support.services.retrieval import (
    search_knowledge_base as retrieve_knowledge_base,
)
from support.services.tickets import create_support_ticket


DRAFT_KEY = "support_ticket_draft"


class ToolPermissionError(Exception):
    pass


class SearchArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    query: str = Field(min_length=1, max_length=1000)


class TicketArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Search active store documents for evidence. "
                "Use before answering policy or product questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_support_ticket",
            "description": (
                "Request ticket creation from an existing, "
                "customer-confirmed form draft. Without verified "
                "form confirmation, this returns a confirmation-required "
                "error and creates nothing."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
]


def execute_tool(name, arguments, *, request=None):
    if name == "search_knowledge_base":
        parsed = SearchArguments.model_validate(arguments)
        query = parsed.query.strip()

        if not query:
            raise ValueError("Enter a non-empty search query.")

        return {
            "matches": retrieve_knowledge_base(query),
        }

    if name != "create_support_ticket":
        raise ValueError("Unknown tool.")

    # Model arguments cannot supply confirmation or ticket fields.
    TicketArguments.model_validate(arguments)

    if request is None or request.method != "POST":
        raise ToolPermissionError(
            "Use Request human support and confirm the form."
        )

    draft = request.session.get(DRAFT_KEY)

    if not isinstance(draft, dict):
        raise ToolPermissionError(
            "A saved ticket draft is required."
        )

    if (
        request.POST.get("confirm") != "yes"
        or not draft.get("request_id")
        or request.POST.get("request_id") != draft["request_id"]
    ):
        raise ToolPermissionError(
            "Review and confirm the current ticket draft."
        )

    owns_conversation = (
        request.session.session_key
        and Conversation.objects.filter(
            pk=draft.get("conversation_id"),
            session_key=request.session.session_key,
        ).exists()
    )

    if not owns_conversation:
        raise ToolPermissionError(
            "The draft does not belong to this browser session."
        )

    if not isinstance(draft.get("fields"), dict):
        raise ValidationError(
            "Please check your ticket details."
        )

    form = SupportTicketForm(draft["fields"])

    if not form.is_valid():
        raise ValidationError(
            "Please check your ticket details."
        )

    ticket = create_support_ticket(
        conversation_id=draft["conversation_id"],
        request_id=draft["request_id"],
        fields=form.cleaned_data,
    )

    return {
        "ticket_id": ticket.pk,
        "reference": ticket.reference,
    }