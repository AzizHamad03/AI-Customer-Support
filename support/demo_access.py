from django.conf import settings
from django.contrib.auth.decorators import user_passes_test

from support.models import KnowledgeDocument, SupportTicket


DEMO_GROUP = "Public staff demo"


def is_demo_user(user):
    return (
        user is not None
        and user.is_authenticated
        and user.groups.filter(name=DEMO_GROUP).exists()
    )


def can_open_workspace(user):
    return user.is_active and (
        user.is_staff
        or (settings.PUBLIC_STAFF_DEMO and is_demo_user(user))
    )


workspace_required = user_passes_test(
    can_open_workspace,
    login_url="support:login",
)


def public_documents():
    return KnowledgeDocument.objects.exclude(uploaded_by__groups__name=DEMO_GROUP)


def workspace_documents(user=None):
    if is_demo_user(user):
        return KnowledgeDocument.objects.filter(uploaded_by=user)
    return public_documents()


def workspace_tickets(user=None):
    tickets = SupportTicket.objects.all()
    if is_demo_user(user):
        return tickets.filter(conversation__user=user)
    return tickets.exclude(conversation__user__groups__name=DEMO_GROUP)