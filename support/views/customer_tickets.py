import logging
from uuid import uuid4

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import (
    require_GET,
    require_http_methods,
)

from support.forms import SupportTicketForm
from support.models import SupportTicket
from support.services.chat import get_conversation
from support.services.tickets import (
    DRAFT_KEY,
    TicketConfirmationError,
    confirm_ticket_draft,
    tickets_visible_to,
)



logger = logging.getLogger(__name__)


@require_http_methods(["GET", "POST"])
def ticket_request(request):
    conversation = get_conversation(request.session, request.user)
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

@require_http_methods(["GET", "POST"])
def ticket_confirm(request):
    conversation = get_conversation(
        request.session,
        request.user,
    )
    draft = request.session.get(DRAFT_KEY)

    if (
        not isinstance(draft, dict)
        or draft.get("conversation_id") != conversation.pk
    ):
        return redirect("support:ticket_request")

    fields = draft.get("fields")

    if not isinstance(fields, dict):
        messages.error(
            request,
            "Please check your ticket details.",
        )
        return redirect("support:ticket_request")

    # Validate the saved details before displaying the review page.
    form = SupportTicketForm(fields)

    if not form.is_valid():
        messages.error(
            request,
            "Please check your ticket details.",
        )
        return redirect("support:ticket_request")

    context = {
        "details": form.cleaned_data,
        "request_id": draft.get("request_id", ""),
    }

    if request.method == "POST":
        try:
            ticket = confirm_ticket_draft(
                request.session,
                request.user,
                request.POST.get("request_id"),
                confirmed=request.POST.get("confirm") == "yes",
            )
        except TicketConfirmationError as exc:
            messages.error(request, str(exc))
            return redirect("support:ticket_confirm")
        except ValidationError:
            messages.error(
                request,
                "Please check your ticket details.",
            )
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

        return redirect(
            "support:ticket_detail",
            pk=ticket.pk,
        )

    if not draft.get("request_id"):
        return redirect("support:ticket_request")

    existing = SupportTicket.objects.filter(
        conversation=conversation,
        request_id=draft["request_id"],
    ).first()

    if existing:
        return redirect(
            "support:ticket_detail",
            pk=existing.pk,
        )

    return render(
        request,
        "support/ticket_confirm.html",
        context,
    )


@require_GET
def ticket_detail(request, pk):
    tickets = tickets_visible_to(
        session=request.session,
        user=request.user,
    )
    ticket = get_object_or_404(tickets, pk=pk)

    return render(
        request,
        "support/ticket_detail.html",
        {"ticket": ticket},
    )

@require_GET
def customer_ticket_list(request):
    tickets = tickets_visible_to(
        session=request.session,
        user=request.user,
    )

    return render(
        request,
        "support/customer_ticket_list.html",
        {"tickets": tickets},
    )