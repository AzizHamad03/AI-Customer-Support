from django.contrib.auth import get_user_model
from django.db import transaction

from support.models import Conversation


ACTIVE_CONVERSATION_KEY = "active_conversation_id"


@transaction.atomic
def attach_guest_conversation(session_key, user):
    if not session_key:
        return None

    # Serialize account-history changes for this user.
    get_user_model().objects.select_for_update().get(pk=user.pk)

    conversation = (
        Conversation.objects.select_for_update()
        .filter(
            session_key=session_key,
            user__isnull=True,
        )
        .first()
    )

    if conversation is None:
        return None

    conversation.user = user
    conversation.session_key = None
    conversation.save(
        update_fields=["user", "session_key", "updated_at"]
    )

    # Messages, citations, and tickets remain attached to this conversation.
    return conversation.pk