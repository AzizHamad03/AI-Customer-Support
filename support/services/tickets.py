from django.db import transaction

from support.models import Conversation, Message, SupportTicket
from django.db.models import Count, Q

from support.models import KnowledgeDocument

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