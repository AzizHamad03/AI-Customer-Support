from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from support.models import (
    Conversation,
    DocumentChunk,
    KnowledgeDocument,
)
from support.services.chat import FALLBACK, send_message
from support.services.retrieval import search_knowledge_base


QUERY_VECTOR = [1.0] + [0.0] * 1535

# Cosine similarity approximately 0.6, so distance approximately 0.4.
RELEVANT_VECTOR = [0.6, 0.8] + [0.0] * 1534

# Orthogonal to the query, so cosine distance exactly 1.
ORTHOGONAL_VECTOR = [0.0, 1.0] + [0.0] * 1534

# Opposite to the query, so cosine distance exactly 2.
OPPOSITE_VECTOR = [-1.0] + [0.0] * 1535


@override_settings(RETRIEVAL_MAX_DISTANCE=0.80)
class RetrievalThresholdTests(TestCase):
    def setUp(self):
        staff = get_user_model().objects.create_user(
            username="threshold-test-staff",
            is_staff=True,
        )

        self.document = KnowledgeDocument.objects.create(
            title="Threshold test policy",
            file="documents/threshold-test.txt",
            uploaded_by=staff,
            status=KnowledgeDocument.Status.READY,
            is_active=True,
        )

        embedding_patch = patch(
            "support.services.retrieval.embed_question",
            return_value=QUERY_VECTOR,
        )
        self.embed_question = embedding_patch.start()
        self.addCleanup(embedding_patch.stop)

    def add_chunk(self, position, vector):
        return DocumentChunk.objects.create(
            document=self.document,
            position=position,
            page_number=1,
            text=f"Policy passage {position}.",
            embedding=vector,
        )

    def test_relevant_match_is_kept_and_weak_match_is_removed(self):
        relevant = self.add_chunk(0, RELEVANT_VECTOR)
        self.add_chunk(1, ORTHOGONAL_VECTOR)

        matches = search_knowledge_base("Shipping cost?")

        self.assertEqual(
            [match["chunk_id"] for match in matches],
            [relevant.pk],
        )
        self.assertAlmostEqual(
            matches[0]["distance"],
            0.4,
            places=5,
        )
        self.embed_question.assert_called_once_with(
            "Shipping cost?"
        )

    def test_only_weak_matches_returns_empty_list(self):
        self.add_chunk(0, ORTHOGONAL_VECTOR)
        self.add_chunk(1, OPPOSITE_VECTOR)

        matches = search_knowledge_base("Unrelated question?")

        self.assertEqual(matches, [])

    @override_settings(RETRIEVAL_MAX_DISTANCE=1.0)
    def test_boundary_is_inclusive_and_larger_distance_is_removed(self):
        below = self.add_chunk(0, RELEVANT_VECTOR)
        boundary = self.add_chunk(1, ORTHOGONAL_VECTOR)
        self.add_chunk(2, OPPOSITE_VECTOR)

        matches = search_knowledge_base("Boundary question?")

        self.assertEqual(
            [match["chunk_id"] for match in matches],
            [below.pk, boundary.pk],
        )
        self.assertEqual(
            matches[1]["distance"],
            1.0,
        )

    def test_no_acceptable_evidence_uses_existing_chat_fallback(self):
        self.add_chunk(0, ORTHOGONAL_VECTOR)

        conversation = Conversation.objects.create(
            session_key="threshold-fallback-test",
        )

        # Exercise real vector retrieval through the chat service,
        # while replacing the external agent loop.
        with (
            patch(
                "support.services.chat.search_with_agent",
                side_effect=search_knowledge_base,
            ),
            patch(
                "support.services.chat.generate_answer",
            ) as generate_answer,
        ):
            messages = send_message(
                conversation.pk,
                "Unrelated question?",
            )

        generate_answer.assert_not_called()

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[1]["content"], FALLBACK)
        self.assertEqual(messages[1]["citations"], [])