from unittest.mock import patch

from django.test import SimpleTestCase

from support.ai.embeddings import EmbeddingError
from support.services.retrieval_evaluation import (
    evaluate_case,
    score_case,
    summarize,
)


class RetrievalEvaluationTests(SimpleTestCase):
    def case(self, **changes):
        return {
            "id": "TEST-01",
            "kind": "answerable",
            "question": "Shipping cost?",
            "expected_evidence": [
                {
                    "titles": ["Shipping policy"],
                    "contains": ["SAR 25", "below SAR 200"],
                },
            ],
            **changes,
        }

    def match(self, title, text):
        return {
            "chunk_id": 1,
            "title": title,
            "document_version": 1,
            "page_number": 1,
            "text": text,
            "distance": 0.2,
            "is_txt": True,
        }

    def test_evidence_requires_the_correct_source_and_phrases(self):
        case = self.case()

        matches = [
            self.match(
                "Other document",
                "Shipping costs SAR 25 below SAR 200.",
            ),
            self.match(
                "Shipping policy",
                "Shipping costs SAR 25 below SAR 200.",
            ),
        ]

        scores = score_case(case, matches)

        self.assertFalse(scores["1"]["complete_evidence"])
        self.assertTrue(scores["3"]["complete_evidence"])
        self.assertEqual(scores["3"]["evidence_coverage"], 1.0)

    def test_all_evidence_groups_are_required(self):
        case = self.case(
            expected_evidence=[
                {
                    "titles": ["Shipping policy"],
                    "contains": ["SAR 25"],
                },
                {
                    "titles": ["Support policy"],
                    "contains": ["confirm"],
                },
            ],
        )

        matches = [
            self.match("Shipping policy", "Shipping costs SAR 25."),
            self.match("Support policy", "Review and confirm."),
        ]

        scores = score_case(case, matches)

        self.assertEqual(scores["1"]["evidence_coverage"], 0.5)
        self.assertFalse(scores["1"]["complete_evidence"])
        self.assertTrue(scores["3"]["complete_evidence"])

    def test_unsupported_case_records_unwanted_matches(self):
        case = self.case(
            kind="unsupported",
            expected_evidence=[],
        )

        empty = score_case(case, [])
        matched = score_case(
            case,
            [self.match("Shipping policy", "Shipping costs SAR 25.")],
        )

        self.assertTrue(empty["1"]["no_matches"])
        self.assertFalse(matched["1"]["no_matches"])

    @patch(
        "support.services.retrieval_evaluation.search_knowledge_base",
        return_value=[],
    )
    @patch(
        "support.services.retrieval_evaluation.make_standalone_question",
        return_value="Actual rewritten question",
    )
    def test_followup_searches_actual_rewrite(self, rewrite, search):
        history = [
            {"role": "user", "content": "Earlier question"},
        ]
        case = self.case(
            kind="followup",
            history=history,
            expected_standalone_question="Expected reference wording",
        )

        result = evaluate_case(case)

        rewrite.assert_called_once_with(
            case["question"],
            history,
        )
        search.assert_called_once_with(
            "Actual rewritten question",
            limit=5,
        )
        self.assertEqual(
            result["standalone_question"],
            "Actual rewritten question",
        )
        self.assertIsNone(result["error"])

    @patch(
        "support.services.retrieval_evaluation.search_knowledge_base",
        side_effect=EmbeddingError("Simulated embedding failure"),
    )
    def test_failed_case_is_recorded_without_quality_score(self, search):
        result = evaluate_case(self.case())
        summary = summarize([result])

        self.assertEqual(
            result["error"]["type"],
            "EmbeddingError",
        )
        self.assertIsNone(result["scores"])
        self.assertEqual(summary["error_count"], 1)
        self.assertEqual(summary["successful_cases"], 0)
        self.assertIsNone(
            summary["at_k"]["1"]["complete_evidence_rate"]
        )