from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import OuterRef, Subquery

from support.models import Conversation, Message


def list_user_conversations(user):
    first_question = (
        Message.objects.filter(
            conversation_id=OuterRef("pk"),
            role=Message.Role.USER,
        )
        .order_by("id")
        .values("content")[:1]
    )

    return (
        Conversation.objects.filter(user=user)
        .annotate(first_question=Subquery(first_question))
        .order_by("-updated_at", "-pk")
    )


@transaction.atomic
def create_user_conversation(user):
    # Match the account lock used by get_conversation().
    get_user_model().objects.select_for_update().get(pk=user.pk)

    return Conversation.objects.create(
        user=user,
        session_key=None,
    )