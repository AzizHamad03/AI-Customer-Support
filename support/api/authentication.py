from rest_framework.authentication import SessionAuthentication


class ChatSessionAuthentication(SessionAuthentication):
    def authenticate(self, request):
        # DRF normally checks CSRF only for authenticated users.
        # Our anonymous, session-based chat needs the check too.
        self.enforce_csrf(request)
        return super().authenticate(request)