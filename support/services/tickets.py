from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q

from support.forms import SupportTicketForm
from support.models import (
    Conversation,
    KnowledgeDocument,
    Message,
    SupportTicket,
)

DRAFT_KEY = "support_ticket_draft"


class TicketConfirmationError(Exception):
    pass


@transaction.atomic
def confirm_ticket_draft(
    session,
    user,
    posted_request_id,
    *,
    confirmed=False,
):
    draft = session.get(DRAFT_KEY)

    if not isinstance(draft, dict):
        raise TicketConfirmationError(
            "A saved ticket draft is required."
        )

    if (
        not confirmed
        or not draft.get("request_id")
        or posted_request_id != draft["request_id"]
    ):
        raise TicketConfirmationError(
            "Review and confirm the current ticket draft."
        )

    try:
        request_id = UUID(str(draft["request_id"]))
    except (TypeError, ValueError, AttributeError) as exc:
        raise TicketConfirmationError(
            "The ticket draft is invalid. Please prepare it again."
        ) from exc

    conversation_id = draft.get("conversation_id")

    if type(conversation_id) is not int:
        raise TicketConfirmationError(
            "The ticket draft is invalid. Please prepare it again."
        )

    # Check ownership while holding the same conversation lock
    # used when saving the ticket.
    conversations = Conversation.objects.select_for_update().filter(
        pk=conversation_id
    )

    if user is not None and user.is_authenticated:
        conversations = conversations.filter(user=user)
    else:
        if not session.session_key:
            raise TicketConfirmationError(
                "The draft does not belong to you."
            )

        conversations = conversations.filter(
            user__isnull=True,
            session_key=session.session_key,
        )

    conversation = conversations.first()

    if conversation is None:
        raise TicketConfirmationError(
            "The draft does not belong to you."
        )

    fields = draft.get("fields")

    if not isinstance(fields, dict):
        raise ValidationError(
            "Please check your ticket details."
        )

    # Validate the saved draft, never ticket fields supplied
    # directly by the confirmation POST.
    form = SupportTicketForm(fields)

    if not form.is_valid():
        raise ValidationError(
            "Please check your ticket details."
        )

    return create_support_ticket(
        conversation_id=conversation.pk,
        request_id=request_id,
        fields=form.cleaned_data,
    )

@transaction.atomic
def create_support_ticket(*, conversation_id, request_id, fields):
    conversation = Conversation.objects.select_for_update().get(
        pk=conversation_id
    )

    existing = SupportTicket.objects.filter(
        conversation=conversation,
        request_id=request_id,
    ).first()

    if existing:
        return existing

    ticket = SupportTicket(
        conversation=conversation,
        request_id=request_id,
        contact_email=fields["contact_email"],
        contact_phone=fields["contact_phone"],
        description=fields["description"],
        order_reference=fields["order_reference"],
    )

    ticket.full_clean()
    ticket.save()

    Message.objects.create(
        conversation=conversation,
        role=Message.Role.ASSISTANT,
        content=(
            f"Your support ticket {ticket.reference} has been created "
            "and is available for staff review."
        ),
    )

    conversation.save(update_fields=["updated_at"])

    return ticket

def tickets_visible_to(*, session, user):
    tickets = SupportTicket.objects.select_related("conversation")

    if user is not None and user.is_authenticated:
        return tickets.filter(conversation__user=user)

    if not session.session_key:
        return tickets.none()

    return tickets.filter(
        conversation__user__isnull=True,
        conversation__session_key=session.session_key,
    )

def dashboard_summary():
    ticket_counts = SupportTicket.objects.aggregate(
        total=Count("id"),
        open=Count(
            "id",
            filter=Q(status=SupportTicket.Status.OPEN),
        ),
        in_progress=Count(
            "id",
            filter=Q(status=SupportTicket.Status.IN_PROGRESS),
        ),
        resolved=Count(
            "id",
            filter=Q(status=SupportTicket.Status.RESOLVED),
        ),
    )

    return {
        "tickets": ticket_counts,
        "documents": KnowledgeDocument.objects.count(),
        "ready_documents": KnowledgeDocument.objects.filter(
            is_active=True,
            status=KnowledgeDocument.Status.READY,
        ).count(),
    }


def search_tickets(query="", status=""):
    tickets = SupportTicket.objects.select_related("conversation")

    if status:
        if status not in SupportTicket.Status.values:
            raise ValueError("Invalid ticket status.")

        tickets = tickets.filter(status=status)

    if query:
        matching = (
            Q(contact_email__icontains=query)
            | Q(contact_phone__icontains=query)
            | Q(description__icontains=query)
            | Q(order_reference__icontains=query)
        )

        reference = query.upper().removeprefix("TKT-")

        if reference.isdigit() and len(reference) <= 18:
            matching |= Q(pk=int(reference))

        tickets = tickets.filter(matching)

    return tickets


@transaction.atomic
def update_ticket_status(ticket_id, status):
    if status not in SupportTicket.Status.values:
        raise ValueError("Invalid ticket status.")

    ticket = SupportTicket.objects.select_for_update().get(
        pk=ticket_id
    )
    ticket.status = status
    ticket.full_clean()
    ticket.save(update_fields=["status", "updated_at"])

    return ticket