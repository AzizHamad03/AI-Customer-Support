from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from support.ai.answers import ChatError
from support.ai.embeddings import EmbeddingError
from support.api.authentication import ChatSessionAuthentication
from support.api.serializers import ChatMessageSerializer
from support.services.chat import (
    conversation_history,
    get_conversation,
    send_message,
)


@ensure_csrf_cookie
def chat_page(request):
    return render(request, "support/chat.html")


@api_view(["GET", "POST"])
@authentication_classes([ChatSessionAuthentication])
@permission_classes([AllowAny])
def chat_api(request):
    if request.method == "POST":
        serializer = ChatMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

    conversation = get_conversation(request.session)

    if request.method == "GET":
        return Response(
            {"messages": conversation_history(conversation)}
        )

    try:
        messages = send_message(
            conversation.pk,
            serializer.validated_data["content"],
        )
    except (ChatError, EmbeddingError) as exc:
        return Response({"error": str(exc)}, status=503)

    return Response({"messages": messages})