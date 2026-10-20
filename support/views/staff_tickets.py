from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import (
    require_GET,
    require_http_methods,
)

from support.forms import TicketFilterForm, TicketStatusForm
from support.models import SupportTicket
from support.services.tickets import (
    search_tickets,
    update_ticket_status,
)


@staff_member_required(login_url="support:login")
@require_GET
def staff_ticket_list(request):
    filter_form = TicketFilterForm(request.GET)

    if filter_form.is_valid():
        tickets = search_tickets(
            query=filter_form.cleaned_data["q"],
            status=filter_form.cleaned_data["status"],
        )
    else:
        tickets = SupportTicket.objects.none()

    page_obj = Paginator(tickets, 20).get_page(
        request.GET.get("page")
    )

    parameters = request.GET.copy()
    parameters.pop("page", None)

    return render(
        request,
        "support/staff_ticket_list.html",
        {
            "filter_form": filter_form,
            "page_obj": page_obj,
            "filter_query": parameters.urlencode(),
        },
    )


@staff_member_required(login_url="support:login")
@require_http_methods(["GET", "POST"])
def staff_ticket_detail(request, pk):
    ticket = get_object_or_404(
        SupportTicket.objects.select_related("conversation"),
        pk=pk,
    )

    if request.method == "POST":
        status_form = TicketStatusForm(request.POST)

        if status_form.is_valid():
            update_ticket_status(
                ticket.pk,
                status_form.cleaned_data["status"],
            )
            messages.success(request, "Ticket status updated.")
            return redirect("support:staff_ticket_detail", pk=pk)
    else:
        status_form = TicketStatusForm(
            initial={"status": ticket.status}
        )

    conversation_messages = (
        ticket.conversation.messages
        .prefetch_related("citations")
        .order_by("id")
    )

    return render(
        request,
        "support/staff_ticket_detail.html",
        {
            "ticket": ticket,
            "status_form": status_form,
            "conversation_messages": conversation_messages,
        },
    )