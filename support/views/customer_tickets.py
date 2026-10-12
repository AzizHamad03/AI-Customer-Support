import logging
from uuid import uuid4

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.shortcuts import get_object_or_404, redirect, render

from support.forms import SupportTicketForm
from support.models import SupportTicket
from support.services.chat import get_conversation
from support.services.tickets import create_support_ticket

from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)
DRAFT_KEY = "support_ticket_draft"


def ticket_request(request):
    conversation = get_conversation(request.session)
    previous_draft = request.session.get(DRAFT_KEY, {})

    if request.method == "POST":
        form = SupportTicketForm(request.POST)

        if form.is_valid():
            request.session[DRAFT_KEY] = {
                "request_id": str(uuid4()),
                "conversation_id": conversation.pk,
                "fields": form.cleaned_data,
            }
            return redirect("support:ticket_confirm")
    else:
        form = SupportTicketForm(
            initial=previous_draft.get("fields", {})
        )

    return render(
        request,
        "support/ticket_request.html",
        {"form": form},
    )


def ticket_confirm(request):
    conversation = get_conversation(request.session)
    draft = request.session.get(DRAFT_KEY)

    if not draft or draft.get("conversation_id") != conversation.pk:
        return redirect("support:ticket_request")

    existing = SupportTicket.objects.filter(
        conversation=conversation,
        request_id=draft["request_id"],
    ).first()

    if existing:
        return redirect("support:ticket_detail", pk=existing.pk)

    # Revalidate the stored draft before showing or submitting it.
    form = SupportTicketForm(draft["fields"])

    if not form.is_valid():
        messages.error(request, "Please check your ticket details.")
        return redirect("support:ticket_request")

    context = {"details": form.cleaned_data}

    if request.method == "POST":
        if request.POST.get("confirm") != "yes":
            messages.error(
                request,
                "Confirm the details before creating the ticket.",
            )
            return redirect("support:ticket_confirm")

        try:
            ticket = create_support_ticket(
                conversation_id=conversation.pk,
                request_id=draft["request_id"],
                fields=form.cleaned_data,
            )
        except ValidationError:
            messages.error(request, "Please check your ticket details.")
            return redirect("support:ticket_request")
        except DatabaseError:
            logger.exception("Support ticket creation failed")
            messages.error(
                request,
                "The ticket could not be saved. Please try again.",
            )
            return render(
                request,
                "support/ticket_confirm.html",
                context,
                status=503,
            )

        return redirect("support:ticket_detail", pk=ticket.pk)

    return render(
        request,
        "support/ticket_confirm.html",
        context,
    )


def ticket_detail(request, pk):
    conversation = get_conversation(request.session)

    ticket = get_object_or_404(
        SupportTicket,
        pk=pk,
        conversation=conversation,
    )

    return render(
        request,
        "support/ticket_detail.html",
        {"ticket": ticket},
    )

@require_GET
def customer_ticket_list(request):
    conversation = get_conversation(request.session)

    tickets = SupportTicket.objects.filter(
        conversation=conversation
    )

    return render(
        request,
        "support/customer_ticket_list.html",
        {"tickets": tickets},
    )