from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from support.services.health import database_is_available


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    ready = database_is_available()
    return Response(
        {"status": "ok" if ready else "unavailable", "database": "connected" if ready else "unavailable"},
        status=200 if ready else 503,
    )
