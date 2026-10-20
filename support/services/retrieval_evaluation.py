from statistics import mean
from time import perf_counter

from django.db import DatabaseError

from support.ai.answers import ChatError, make_standalone_question
from support.ai.embeddings import EmbeddingError
from support.services.retrieval import search_knowledge_base


CUTOFFS = (1, 3, 5)


def normalize(text):
    return " ".join(text.casefold().split())


def evidence_found(group, matches):
    for title in group["titles"]:
        texts = [
            normalize(match["text"])
            for match in matches
            if match["title"] == title
        ]

        if texts and all(
            any(normalize(phrase) in text for text in texts)
            for phrase in group["contains"]
        ):
            return True

    return False


def score_case(case, matches):
    scores = {}

    for cutoff in CUTOFFS:
        selected = matches[:cutoff]

        if case["kind"] == "unsupported":
            scores[str(cutoff)] = {
                "no_matches": not selected,
            }
            continue

        expected = case["expected_evidence"]
        found = sum(
            evidence_found(group, selected)
            for group in expected
        )

        scores[str(cutoff)] = {
            "evidence_groups_found": found,
            "evidence_groups_expected": len(expected),
            "evidence_coverage": found / len(expected),
            "complete_evidence": found == len(expected),
        }

    return scores


def evaluate_case(case):
    started = perf_counter()
    retrieval_started = None

    result = {
        "case": case,
        "standalone_question": None,
        "matches": [],
        "scores": None,
        "rewrite_ms": None,
        "retrieval_ms": None,
        "latency_ms": None,
        "error": None,
    }

    try:
        history = case.get("history", [])

        if history:
            question = make_standalone_question(
                case["question"],
                history,
            )
        else:
            question = case["question"]

        result["standalone_question"] = question
        result["rewrite_ms"] = round(
            (perf_counter() - started) * 1000,
            2,
        )

        retrieval_started = perf_counter()

        matches = search_knowledge_base(
            question,
            limit=max(CUTOFFS),
        )

        result["retrieval_ms"] = round(
            (perf_counter() - retrieval_started) * 1000,
            2,
        )
        result["matches"] = matches
        result["scores"] = score_case(case, matches)

    except (ChatError, EmbeddingError, DatabaseError) as exc:
        result["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }

        if retrieval_started is not None:
            result["retrieval_ms"] = round(
                (perf_counter() - retrieval_started) * 1000,
                2,
            )

    result["latency_ms"] = round(
        (perf_counter() - started) * 1000,
        2,
    )

    return result


def summarize(results):
    successful = [
        result
        for result in results
        if result["error"] is None
    ]
    positive = [
        result
        for result in successful
        if result["case"]["kind"] != "unsupported"
    ]
    unsupported = [
        result
        for result in successful
        if result["case"]["kind"] == "unsupported"
    ]

    summary = {
        "total_cases": len(results),
        "successful_cases": len(successful),
        "error_count": len(results) - len(successful),
        "answerable_and_followup_cases": len(positive),
        "unsupported_cases": len(unsupported),
        "mean_latency_ms": (
            round(mean(r["latency_ms"] for r in successful), 2)
            if successful else None
        ),
        "at_k": {},
        "unsupported_cases_with_matches": sum(
            bool(result["matches"])
            for result in unsupported
        ),
        "unsupported_no_match_rate": (
            mean(not result["matches"] for result in unsupported)
            if unsupported else None
        ),
    }

    for cutoff in CUTOFFS:
        key = str(cutoff)

        summary["at_k"][key] = {
            "mean_evidence_coverage": (
                mean(
                    result["scores"][key]["evidence_coverage"]
                    for result in positive
                )
                if positive else None
            ),
            "complete_evidence_rate": (
                mean(
                    result["scores"][key]["complete_evidence"]
                    for result in positive
                )
                if positive else None
            ),
        }

    return summary