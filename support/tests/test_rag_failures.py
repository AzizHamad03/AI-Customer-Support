from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from langchain_core.exceptions import OutputParserException

from support.ai.answers import (
    ChatError,
    GroundedAnswer,
    generate_answer,
)
from support.ai.embeddings import EmbeddingError
from support.models import (
    Conversation,
    DocumentChunk,
    KnowledgeDocument,
    Message,
    MessageCitation,
    SupportTicket,
)
from support.services.chat import FALLBACK, send_message


class RagFailureTests(TestCase):
    def setUp(self):
        staff = get_user_model().objects.create_user(
            username="rag-staff",
            is_staff=True,
        )

        self.document = KnowledgeDocument.objects.create(
            title="Shipping policy",
            file="documents/test.txt",
            uploaded_by=staff,
            status=KnowledgeDocument.Status.READY,
            is_active=True,
        )

        self.chunk = DocumentChunk.objects.create(
            document=self.document,
            position=0,
            page_number=1,
            text="Shipping costs SAR 25.",
        )

        self.conversation = Conversation.objects.create(
            session_key=self.client.session.session_key,
        )

        self.match = {
            "chunk_id": self.chunk.pk,
            "title": self.document.title,
            "document_version": 1,
            "page_number": 1,
            "text": self.chunk.text,
            "is_txt": True,
            "distance": 0.0,
        }

        rewrite = patch(
            "support.services.chat.make_standalone_question",
            side_effect=lambda question, history: question,
        )
        self.rewrite = rewrite.start()
        self.addCleanup(rewrite.stop)

        search = patch(
            "support.services.chat.search_knowledge_base",
            return_value=[self.match],
        )
        self.search = search.start()
        self.addCleanup(search.stop)

        generate = patch(
            "support.services.chat.generate_answer",
        )
        self.generate = generate.start()
        self.addCleanup(generate.stop)

        self.generate.return_value = self.answer()

    def answer(self, **changes):
        fields = {
            "supported": True,
            "needs_human_support": False,
            "answer": "Shipping costs SAR 25.",
            "source_keys": ["S1"],
        }

        return GroundedAnswer(**(fields | changes))

    def test_supported_answer_saves_valid_citation_once(self):
        self.generate.return_value = self.answer(
            source_keys=["S1", "S1"],
        )

        messages = send_message(
            self.conversation.pk,
            "Shipping cost?",
        )

        self.assertEqual(Message.objects.count(), 2)
        self.assertEqual(
            messages[1]["content"],
            "Shipping costs SAR 25.",
        )
        self.assertEqual(len(messages[1]["citations"]), 1)

        citation = MessageCitation.objects.get()

        self.assertEqual(citation.chunk_id, self.chunk.pk)
        self.assertEqual(citation.source_text, self.chunk.text)
        self.assertEqual(
            citation.document_title,
            self.document.title,
        )
        self.assertEqual(citation.page_number, 1)
        self.assertEqual(citation.document_version, 1)

    def test_invalid_or_unsupported_answers_use_fallback(self):
        cases = [
            {"supported": False},
            {"source_keys": ["invented"]},
            {"source_keys": ["S1", "invented"]},
            {"source_keys": []},
            {"answer": "   "},
            {"answer": "x" * 4001},
        ]

        for changes in cases:
            with self.subTest(changes=changes):
                self.generate.return_value = self.answer(
                    **changes
                )

                messages = send_message(
                    self.conversation.pk,
                    "Shipping cost?",
                )

                self.assertEqual(
                    messages[1]["content"],
                    FALLBACK,
                )
                self.assertEqual(
                    messages[1]["citations"],
                    [],
                )

        self.assertEqual(MessageCitation.objects.count(), 0)

    def test_no_evidence_uses_fallback_without_answer_generation(self):
        self.search.return_value = []

        messages = send_message(
            self.conversation.pk,
            "Unknown policy?",
        )

        self.assertEqual(messages[1]["content"], FALLBACK)
        self.generate.assert_not_called()
        self.assertEqual(MessageCitation.objects.count(), 0)

    def test_escalation_directs_to_form_without_creating_ticket(self):
        self.chunk.text = (
            "Report damaged deliveries within 48 hours."
        )
        self.chunk.save(update_fields=["text"])
        self.match["text"] = self.chunk.text

        self.generate.return_value = self.answer(
            needs_human_support=True,
            answer="Report damaged deliveries within 48 hours.",
        )

        messages = send_message(
            self.conversation.pk,
            "My item arrived damaged.",
        )

        self.assertIn("within 48 hours", messages[1]["content"])
        self.assertIn(
            "Request human support",
            messages[1]["content"],
        )
        self.assertIn("confirm", messages[1]["content"])

        self.assertEqual(SupportTicket.objects.count(), 0)
        self.assertEqual(MessageCitation.objects.count(), 1)

    def test_saved_citation_survives_source_changes_and_chunk_deletion(self):
        send_message(self.conversation.pk, "Shipping cost?")
        citation = MessageCitation.objects.get()

        self.document.title = "Changed title"
        self.document.version = 2
        self.document.is_active = False
        self.document.save(
            update_fields=["title", "is_active", "version"]
        )

        self.chunk.delete()
        citation.refresh_from_db()

        self.assertIsNone(citation.chunk_id)
        self.assertEqual(
            citation.document_title,
            "Shipping policy",
        )
        self.assertEqual(
            citation.source_text,
            "Shipping costs SAR 25.",
        )

        response = self.client.get(
            reverse("support:chat_api")
        )

        self.assertEqual(response.status_code, 200)

        saved = response.json()["messages"][-1]["citations"][0]

        self.assertEqual(saved["title"], "Shipping policy")
        self.assertEqual(
            saved["text"],
            "Shipping costs SAR 25.",
        )
        self.assertEqual(saved["document_version"], 1)

    def test_api_failures_do_not_save_partial_messages(self):
        cases = [
            (self.rewrite, ChatError("Rewrite unavailable")),
            (self.search, EmbeddingError("Embedding unavailable")),
            (self.generate, ChatError("Answer unavailable")),
        ]

        for mocked_call, error in cases:
            with self.subTest(stage=str(error)):
                mocked_call.side_effect = error

                try:
                    response = self.client.post(
                        reverse("support:chat_api"),
                        {"content": "Shipping cost?"},
                        content_type="application/json",
                    )

                    self.assertEqual(response.status_code, 503)
                    self.assertIn("error", response.json())
                    self.assertEqual(Message.objects.count(), 0)
                    self.assertEqual(
                        MessageCitation.objects.count(),
                        0,
                    )
                finally:
                    mocked_call.side_effect = None

        # A successful retry still saves a normal response.
        messages = send_message(
            self.conversation.pk,
            "Shipping cost?",
        )

        self.assertEqual(
            messages[1]["content"],
            "Shipping costs SAR 25.",
        )

    def test_followup_uses_rewritten_question_and_bounded_history(self):
        for number in range(8):
            Message.objects.create(
                conversation=self.conversation,
                role="user" if number % 2 == 0 else "assistant",
                content=f"Previous message {number}",
            )

        self.rewrite.side_effect = None
        self.rewrite.return_value = "Shipping cost to Riyadh?"

        send_message(
            self.conversation.pk,
            "What about Riyadh?",
        )

        question, history = self.rewrite.call_args.args

        self.assertEqual(question, "What about Riyadh?")
        self.assertEqual(len(history), 6)
        self.assertEqual(
            history[0]["content"],
            "Previous message 2",
        )

        self.search.assert_called_once_with(
            "Shipping cost to Riyadh?"
        )

    def test_changed_conversation_rejects_stale_reply(self):
        def concurrent_message(*args):
            Message.objects.create(
                conversation=self.conversation,
                role="assistant",
                content=(
                    "A message saved while the reply "
                    "was being prepared."
                ),
            )
            return self.answer()

        self.generate.side_effect = concurrent_message

        response = self.client.post(
            reverse("support:chat_api"),
            {"content": "Shipping cost?"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(MessageCitation.objects.count(), 0)

    def test_chunk_deleted_during_generation_rejects_new_answer(self):
        def delete_source(*args):
            self.chunk.delete()
            return self.answer()

        self.generate.side_effect = delete_source

        response = self.client.post(
            reverse("support:chat_api"),
            {"content": "Shipping cost?"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn(
            "store documents changed",
            response.json()["error"],
        )
        self.assertEqual(Message.objects.count(), 0)
        self.assertEqual(MessageCitation.objects.count(), 0)

    def test_changed_document_rejects_new_answer(self):
        changes = [
            {"is_active": False},
            {"status": KnowledgeDocument.Status.EXTRACTED},
            {"version": 2},
        ]

        for change in changes:
            with self.subTest(change=change):
                KnowledgeDocument.objects.filter(
                    pk=self.document.pk
                ).update(
                    is_active=True,
                    status=KnowledgeDocument.Status.READY,
                    version=1,
                )

                def change_document(*args):
                    KnowledgeDocument.objects.filter(
                        pk=self.document.pk
                    ).update(**change)
                    return self.answer()

                self.generate.side_effect = change_document

                response = self.client.post(
                    reverse("support:chat_api"),
                    {"content": "Shipping cost?"},
                    content_type="application/json",
                )

                self.assertEqual(response.status_code, 409)
                self.assertEqual(Message.objects.count(), 0)
                self.assertEqual(MessageCitation.objects.count(), 0)

    def test_changed_passage_rejects_new_answer(self):
        def change_passage(*args):
            DocumentChunk.objects.filter(
                pk=self.chunk.pk
            ).update(text="Shipping now costs SAR 20.")
            return self.answer()

        self.generate.side_effect = change_passage

        response = self.client.post(
            reverse("support:chat_api"),
            {"content": "Shipping cost?"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Message.objects.count(), 0)
        self.assertEqual(MessageCitation.objects.count(), 0)

    def test_malformed_model_output_returns_error_without_saving(self):
        # Run the real answer-generation error handling, while
        # replacing the external model call.
        self.generate.side_effect = generate_answer

        with patch(
            "support.ai.answers.get_chat_model"
        ) as get_model:
            structured_model = (
                get_model.return_value
                .with_structured_output.return_value
            )
            structured_model.invoke.side_effect = (
                OutputParserException("Malformed model response")
            )

            response = self.client.post(
                reverse("support:chat_api"),
                {"content": "Shipping cost?"},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("error", response.json())
        self.assertEqual(Message.objects.count(), 0)
        self.assertEqual(MessageCitation.objects.count(), 0)