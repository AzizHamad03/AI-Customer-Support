from django.urls import path

from support.views.documents import (
    document_detail,
    document_list,
    document_prepare_chunks,
    document_process,
    document_upload,
    document_index,
    document_set_active,
    document_delete,
)
from support.views.health import health
from support.views.pages import home, staff_dashboard
from support.views.knowledge_search import knowledge_search
from support.views.chat import chat_api, chat_page

from support.views.customer_tickets import (
    customer_ticket_list,
    ticket_confirm,
    ticket_detail,
    ticket_request,
)
from support.views.staff_tickets import (
    staff_ticket_detail,
    staff_ticket_list,
)

from support.views.documents import document_replace

from support.views.accounts import (
    CustomerLoginView,
    CustomerLogoutView,
    signup,
)
from support.views.conversations import (
    conversation_list,
    conversation_new,
    conversation_open,
)

app_name = "support"

urlpatterns = [
    path("", home, name="home"),
    path("staff/", staff_dashboard, name="staff_dashboard"),
    path("staff/documents/", document_list, name="document_list"),
    path(
        "staff/documents/upload/",
        document_upload,
        name="document_upload",
    ),
    path(
    "staff/documents/<int:pk>/",
    document_detail,
    name="document_detail",
    ),
    path(
        "staff/documents/<int:pk>/process/",
        document_process,
        name="document_process",
    ),
    path(
        "staff/documents/<int:pk>/chunks/",
        document_prepare_chunks,
        name="document_prepare_chunks",
    ),
    path("api/health/", health, name="health"),
    path(
        "staff/documents/<int:pk>/index/",
        document_index,
        name="document_index",
    ),
    path(
        "staff/knowledge-search/",
        knowledge_search,
        name="knowledge_search",
    ),
    path("chat/", chat_page, name="chat"),
    path("api/chat/", chat_api, name="chat_api"),
    path(
        "support/request/",
        ticket_request,
        name="ticket_request",
    ),
    path(
        "support/confirm/",
        ticket_confirm,
        name="ticket_confirm",
    ),
    path(
        "support/tickets/<int:pk>/",
        ticket_detail,
        name="ticket_detail",
    ),
    path(
        "staff/tickets/",
        staff_ticket_list,
        name="staff_ticket_list",
    ),
    path(
        "staff/tickets/<int:pk>/",
        staff_ticket_detail,
        name="staff_ticket_detail",
    ),
    path(
        "support/tickets/",
        customer_ticket_list,
        name="customer_ticket_list",
    ),
    path(
        "staff/documents/<int:pk>/active/",
        document_set_active,
        name="document_set_active",
    ),
    path(
        "staff/documents/<int:pk>/replace/",
        document_replace,
        name="document_replace",
    ),
    path(
        "staff/documents/<int:pk>/delete/",
        document_delete,
        name="document_delete",
    ),
    path(
        "accounts/signup/",
        signup,
        name="signup",
    ),
    path(
        "accounts/login/",
        CustomerLoginView.as_view(),
        name="login",
    ),
    path(
        "accounts/logout/",
        CustomerLogoutView.as_view(),
        name="logout",
    ),
    path(
        "conversations/",
        conversation_list,
        name="conversation_list",
    ),
    path(
        "conversations/new/",
        conversation_new,
        name="conversation_new",
    ),
    path(
        "conversations/<int:pk>/open/",
        conversation_open,
        name="conversation_open",
    ),
]