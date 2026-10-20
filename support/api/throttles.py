from rest_framework.throttling import (
    AnonRateThrottle,
    UserRateThrottle,
)


class ChatAnonRateThrottle(AnonRateThrottle):
    scope = "chat_anon"

    def get_cache_key(self, request, view):
        if request.method != "POST":
            return None

        return super().get_cache_key(request, view)


class ChatUserRateThrottle(UserRateThrottle):
    scope = "chat_user"

    def get_cache_key(self, request, view):
        if (
            request.method != "POST"
            or not request.user.is_authenticated
        ):
            return None

        return super().get_cache_key(request, view)