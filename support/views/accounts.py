from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.views import LoginView, LogoutView
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from support.services.accounts import (
    ACTIVE_CONVERSATION_KEY,
    attach_guest_conversation,
)


class CustomerLoginView(LoginView):
    template_name = "support/login.html"
    redirect_authenticated_user = False

    def form_valid(self, form):
        user = form.get_user()

        # Capture guest ownership before Django rotates the session key.
        conversation_id = attach_guest_conversation(
            self.request.session.session_key,
            user,
        )

        response = super().form_valid(form)

        self.request.session.pop("support_ticket_draft", None)
        self.request.session.pop(ACTIVE_CONVERSATION_KEY, None)

        if conversation_id is not None:
            self.request.session[
                ACTIVE_CONVERSATION_KEY
            ] = conversation_id

        return response

    def get_default_redirect_url(self):
        if self.request.user.is_staff:
            return "/staff/"
        return "/chat/"


class CustomerLogoutView(LogoutView):
    next_page = "support:home"


@require_http_methods(["GET", "POST"])
def signup(request):
    if request.user.is_authenticated:
        return redirect("support:chat")

    form = UserCreationForm(
        request.POST if request.method == "POST" else None
    )

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save()
            conversation_id = attach_guest_conversation(
                request.session.session_key,
                user,
            )

        login(
            request,
            user,
            backend="django.contrib.auth.backends.ModelBackend",
        )

        request.session.pop("support_ticket_draft", None)
        request.session.pop(ACTIVE_CONVERSATION_KEY, None)

        if conversation_id is not None:
            request.session[
                ACTIVE_CONVERSATION_KEY
            ] = conversation_id

        return redirect("support:chat")

    return render(
        request,
        "support/signup.html",
        {"form": form},
    )