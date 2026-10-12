import re

from django.db import transaction

from support.ai.answers import (
    ChatError,
    generate_answer,
    make_standalone_question,
)
from support.models import (
    Conversation,
    DocumentChunk,
    Message,
    MessageCitation,
)
from support.ai.agent import (
    search_with_agent as search_knowledge_base,
)

class ConversationChanged(ChatError):
    pass

FALLBACK = (
    "I don't have enough consistent information in the store documents "
    "to answer that reliably. You can use Request human support "
    "to submit your issue for staff review."
)


def get_conversation(session):
    if not session.session_key:
        session.save()

    conversation, _ = Conversation.objects.get_or_create(
        session_key=session.session_key
    )
    return conversation


def serialize_message(message):
    return {
        "id": message.pk,
        "role": message.role,
        "content": message.content,
        "citations": [
            {
                "source_key": citation.source_key,
                "title": citation.document_title,
                "document_version": citation.document_version,
                "page_number": citation.page_number,
                "text": citation.source_text,
                "is_txt": citation.is_txt,
            }
            for citation in message.citations.all()
        ],
    }


def conversation_history(conversation):
    messages = conversation.messages.prefetch_related("citations")
    return [serialize_message(message) for message in messages]


def policy_only_escalation_text(text):
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    kept = []

    for sentence in sentences:
        requests_details = re.search(
            r"\b(?:provide|share|enter|send|give)\b.*"
            r"\b(?:contact|email|phone|details|order reference)\b",
            sentence,
            flags=re.IGNORECASE,
        )

        describes_ticket_creation = (
            re.search(r"\bticket\b", sentence, re.IGNORECASE)
            and re.search(
                r"\b(?:create|created|creation|confirm|confirmation)\b",
                sentence,
                re.IGNORECASE,
            )
        )

        if not requests_details and not describes_ticket_creation:
            kept.append(sentence)

    return " ".join(kept)


def send_message(conversation_id, question):
    conversation = Conversation.objects.get(
        pk=conversation_id
    )

    recent = list(
        conversation.messages.order_by("-id")[:6]
    )
    expected_last_id = recent[0].pk if recent else None
    history = [
        {
            "role": message.role,
            "content": message.content[:2000],
        }
        for message in reversed(recent)
    ]

    standalone_question = make_standalone_question(question, history)
    matches = search_knowledge_base(standalone_question)

    source_map = {
        f"S{number}": match
        for number, match in enumerate(matches, start=1)
    }

    answer_text = FALLBACK
    selected_keys = []

    if matches:
        passages = [
            {
                "source_key": key,
                "title": match["title"],
                "page_number": match["page_number"],
                "text": match["text"],
            }
            for key, match in source_map.items()
        ]

        result = generate_answer(question, history, passages)
        keys = list(dict.fromkeys(result.source_keys))
        text = result.answer.strip()

        if result.needs_human_support:
            text = policy_only_escalation_text(text)

        # Reject invented source identifiers and unsupported responses.
        if (
            result.supported
            and keys
            and all(key in source_map for key in keys)
            and text
            and len(text) <= 4000
        ):
            answer_text = text
            selected_keys = keys

        # Append form instructions only to an accepted, cited answer.
        # The fallback already directs customers to human support.
        if result.needs_human_support and selected_keys:
            answer_text += (
                "\n\nTo have staff review this issue, click the "
                "Request human support button above the chat. "
                "Enter your details in the form, review the summary, "
                "and confirm to create a ticket."
            )

    # AI calls have finished. Lock only while checking and saving.
    with transaction.atomic():
        conversation = Conversation.objects.select_for_update().get(
            pk=conversation_id
        )

        current_last_id = (
            conversation.messages.order_by("-id")
            .values_list("pk", flat=True)
            .first()
        )

        if current_last_id != expected_last_id:
            raise ConversationChanged(
                "Your conversation changed while this answer "
                "was being prepared. Review the latest messages "
                "and send your question again."
            )

        live_chunk_ids = set(
            DocumentChunk.objects.select_for_update()
            .filter(
                pk__in=[
                    source_map[key]["chunk_id"]
                    for key in selected_keys
                ]
            )
            .order_by("pk")
            .values_list("pk", flat=True)
        )

        customer_message = Message.objects.create(
            conversation=conversation,
            role=Message.Role.USER,
            content=question,
        )

        assistant_message = Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content=answer_text,
        )

        MessageCitation.objects.bulk_create(
            [
                MessageCitation(
                    message=assistant_message,
                    chunk_id=(
                        source_map[key]["chunk_id"]
                        if source_map[key]["chunk_id"] in live_chunk_ids
                        else None
                    ),
                    source_key=key,
                    document_title=source_map[key]["title"],
                    document_version=source_map[key].get(
                        "document_version"
                    ),
                    page_number=source_map[key]["page_number"],
                    source_text=source_map[key]["text"],
                    is_txt=source_map[key]["is_txt"],
                )
                for key in selected_keys
            ]
        )

        conversation.save(update_fields=["updated_at"])

    return [
        serialize_message(customer_message),
        serialize_message(assistant_message),
    ]