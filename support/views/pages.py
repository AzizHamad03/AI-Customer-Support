from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.models import Group
from django.db import transaction
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from support.demo_access import DEMO_GROUP, can_open_workspace, workspace_required
from support.models import Conversation, Message
from support.services.accounts import ACTIVE_CONVERSATION_KEY, attach_guest_conversation
from support.services.tickets import create_support_ticket, dashboard_summary


def home(request):
    return render(
        request,
        "support/home.html",
        {
            "show_demo_button": (
                settings.PUBLIC_STAFF_DEMO and not request.user.is_authenticated
            ),
            "can_open_workspace": can_open_workspace(request.user),
        },
    )


@require_POST
def start_staff_demo(request):
    if not settings.PUBLIC_STAFF_DEMO:
        raise Http404

    if can_open_workspace(request.user):
        return redirect("support:staff_dashboard")

    if request.user.is_authenticated:
        return HttpResponseForbidden(
            "Open the homepage in a private window to start a staff demo."
        )

    with transaction.atomic():
        demo_group, _ = Group.objects.get_or_create(name=DEMO_GROUP)
        demo_user = get_user_model().objects.create_user(
            username=f"demo-{uuid4().hex}",
        )
        demo_user.groups.add(demo_group)

        guest_conversation_id = attach_guest_conversation(
            request.session.session_key,
            demo_user,
        )

        sample = Conversation.objects.create(user=demo_user)
        Message.objects.bulk_create([
            Message(
                conversation=sample,
                role=Message.Role.USER,
                content="Where is order DEMO-SAMPLE?",
            ),
            Message(
                conversation=sample,
                role=Message.Role.ASSISTANT,
                content=(
                    "I can’t check live order status. "
                    "You can ask the support team to look into it."
                ),
            ),
        ])
        create_support_ticket(
            conversation_id=sample.pk,
            request_id=uuid4(),
            fields={
                "contact_email": "demo@example.com",
                "contact_phone": "",
                "order_reference": "DEMO-SAMPLE",
                "description": "My order is late. Could you check its status?",
            },
        )

        active_conversation_id = guest_conversation_id
        if active_conversation_id is None:
            active_conversation_id = Conversation.objects.create(user=demo_user).pk

    login(
        request,
        demo_user,
        backend="django.contrib.auth.backends.ModelBackend",
    )
    request.session[ACTIVE_CONVERSATION_KEY] = active_conversation_id
    request.session.set_expiry(3600)
    return redirect("support:staff_dashboard")


@workspace_required
def staff_dashboard(request):
    return render(
        request,
        "support/staff.html",
        {"summary": dashboard_summary(user=request.user)},
    )