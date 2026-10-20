import logging

from django.db import DatabaseError
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from support.ai.answers import ChatError
from support.ai.embeddings import EmbeddingError
from support.api.authentication import ChatSessionAuthentication
from support.api.serializers import ChatMessageSerializer
from support.api.throttles import (
    ChatAnonRateThrottle,
    ChatUserRateThrottle,
)
from support.services.chat import (
    ConversationChanged,
    KnowledgeChanged,
    conversation_history,
    get_conversation,
    send_message,
)


logger = logging.getLogger(__name__)


@ensure_csrf_cookie
def chat_page(request):
    return render(request, "support/chat.html")


@api_view(["GET", "POST"])
@authentication_classes([ChatSessionAuthentication])
@permission_classes([AllowAny])
@throttle_classes([
    ChatAnonRateThrottle,
    ChatUserRateThrottle,
])
def chat_api(request):
    if request.method == "POST":
        serializer = ChatMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

    try:
        conversation = get_conversation(request.session, request.user)

        if request.method == "GET":
            return Response({
                "conversation_id": conversation.pk,
                "messages": conversation_history(conversation),
            })

        expected_id = request.data.get("conversation_id")

        if (
            expected_id is not None
            and (
                type(expected_id) is not int
                or expected_id != conversation.pk
            )
        ):
            return Response(
                {
                    "error": (
                        "The selected conversation changed. "
                        "Review the reloaded conversation before sending again."
                    )
                },
                status=409,
            )

        messages = send_message(
            conversation.pk,
            serializer.validated_data["content"],
        )

    except (ConversationChanged, KnowledgeChanged) as exc:
        return Response(
            {"error": str(exc)},
            status=409,
        )

    except (ChatError, EmbeddingError) as exc:
        logger.warning("Chat request failed: %s", exc)

        return Response(
            {
                "error": (
                    "I could not complete your request. "
                    "Please try again or use Request human support."
                ),
            },
            status=503,
        )

    except DatabaseError:
        logger.exception("Chat database operation failed")

        return Response(
            {
                "error": (
                    "Your conversation is temporarily unavailable. "
                    "Please try again shortly."
                ),
            },
            status=503,
        )

    return Response({
        "conversation_id": conversation.pk,
        "messages": messages,
    })