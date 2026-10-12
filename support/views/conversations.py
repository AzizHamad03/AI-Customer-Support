from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from support.models import Conversation
from support.services.accounts import ACTIVE_CONVERSATION_KEY
from support.services.conversations import (
    create_user_conversation,
    list_user_conversations,
)


@login_required(login_url="support:login")
@require_GET
def conversation_list(request):
    conversations = list_user_conversations(request.user)
    page_obj = Paginator(conversations, 20).get_page(
        request.GET.get("page")
    )

    return render(
        request,
        "support/conversation_list.html",
        {
            "page_obj": page_obj,
            "active_conversation_id": request.session.get(
                ACTIVE_CONVERSATION_KEY
            ),
        },
    )


@login_required(login_url="support:login")
@require_POST
def conversation_new(request):
    conversation = create_user_conversation(request.user)

    request.session[ACTIVE_CONVERSATION_KEY] = conversation.pk
    request.session.pop("support_ticket_draft", None)

    return redirect("support:chat")


@login_required(login_url="support:login")
@require_POST
def conversation_open(request, pk):
    conversation = get_object_or_404(
        Conversation,
        pk=pk,
        user=request.user,
    )

    request.session[ACTIVE_CONVERSATION_KEY] = conversation.pk
    request.session.pop("support_ticket_draft", None)

    return redirect("support:chat")