import hashlib
import json
import re
from datetime import datetime, timezone

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from support.ai.prompt_loader import PROMPTS_DIR
from support.models import KnowledgeDocument
from support.services.chunking import CHUNK_WORDS, OVERLAP_WORDS
from support.services.retrieval_evaluation import (
    evaluate_case,
    normalize,
    summarize,
)


DOCUMENT_FILES = {
    "Demo Store Shipping Policy": "shipping_policy.txt",
    "Demo Store Returns Policy": "returns_policy.txt",
    "Demo Store Product Catalog": "product_catalog.txt",
    "Demo Store Support Policy": "support_policy.txt",
}


def digest(value):
    encoded = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def corpus_snapshot():
    documents = list(
        KnowledgeDocument.objects.filter(
            is_active=True,
            status=KnowledgeDocument.Status.READY,
        ).order_by("title", "pk")
    )

    expected = sorted(
        (title, 1)
        for title in DOCUMENT_FILES
    )
    actual = sorted(
        (document.title, document.version)
        for document in documents
    )

    if actual != expected:
        raise CommandError(
            "This dataset requires exactly the four active, Ready "
            "sample documents at version 1, using the titles listed "
            "in sample_data/README.md.\n"
            f"Found: {actual}"
        )

    snapshot = []

    for document in documents:
        source_path = (
            settings.BASE_DIR
            / "sample_data"
            / "policies"
            / DOCUMENT_FILES[document.title]
        )
        expected_text = normalize(
            source_path.read_text(encoding="utf-8")
        )
        actual_text = normalize(
            " ".join(
                page["text"]
                for page in document.extracted_pages
            )
        )

        if actual_text != expected_text:
            raise CommandError(
                f"{document.title}: extracted text does not match "
                "the version-1 sample file."
            )

        chunks = list(
            document.chunks.order_by("position")
        )

        if not chunks or any(
            chunk.embedding is None
            for chunk in chunks
        ):
            raise CommandError(
                f"{document.title}: complete indexing first."
            )

        snapshot.append({
            "title": document.title,
            "version": document.version,
            "text_sha256": digest(actual_text),
            "chunks": [
                {
                    "position": chunk.position,
                    "page_number": chunk.page_number,
                    "text_sha256": digest(chunk.text),
                    "embedding_sha256": digest([
                        float(value)
                        for value in chunk.embedding
                    ]),
                }
                for chunk in chunks
            ],
        })

    return snapshot


def load_cases(path):
    try:
        cases = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CommandError(
            f"Cannot read dataset: {exc}"
        ) from exc

    if not isinstance(cases, list) or not cases:
        raise CommandError("The dataset must be a non-empty list.")

    identifiers = []

    for case in cases:
        if not isinstance(case, dict):
            raise CommandError("Each case must be an object.")

        identifier = case.get("id")
        kind = case.get("kind")
        question = case.get("question")
        evidence = case.get("expected_evidence")

        if not isinstance(identifier, str) or not identifier:
            raise CommandError("Each case needs a non-empty ID.")

        if kind not in {"answerable", "unsupported", "followup"}:
            raise CommandError(f"{identifier}: invalid case kind.")

        if (
            not isinstance(question, str)
            or not question.strip()
            or len(question) > 1000
        ):
            raise CommandError(f"{identifier}: invalid question.")

        if not isinstance(evidence, list):
            raise CommandError(
                f"{identifier}: expected_evidence must be a list."
            )

        if (kind == "unsupported") != (len(evidence) == 0):
            raise CommandError(
                f"{identifier}: unsupported cases need no evidence; "
                "other cases need evidence labels."
            )

        for group in evidence:
            if (
                not isinstance(group, dict)
                or not isinstance(group.get("titles"), list)
                or not group["titles"]
                or any(
                    title not in DOCUMENT_FILES
                    for title in group["titles"]
                )
                or not isinstance(group.get("contains"), list)
                or not group["contains"]
                or any(
                    not isinstance(phrase, str) or not phrase.strip()
                    for phrase in group["contains"]
                )
            ):
                raise CommandError(
                    f"{identifier}: invalid evidence group."
                )

        history = case.get("history", [])

        if not isinstance(history, list) or any(
            not isinstance(message, dict)
            or message.get("role") not in {"user", "assistant"}
            or not isinstance(message.get("content"), str)
            for message in history
        ):
            raise CommandError(f"{identifier}: invalid history.")

        if kind == "followup" and (
            not history
            or not isinstance(
                case.get("expected_standalone_question"),
                str,
            )
        ):
            raise CommandError(
                f"{identifier}: follow-up labels are incomplete."
            )

        identifiers.append(identifier)

    if len(set(identifiers)) != len(identifiers):
        raise CommandError("Case IDs must be unique.")

    return cases


class Command(BaseCommand):
    help = "Evaluate retrieval against the version-1 sample policies."

    def add_arguments(self, parser):
        parser.add_argument(
            "--split",
            choices=["dev", "eval"],
            required=True,
        )
        parser.add_argument(
            "--label",
            default="baseline",
        )

    def handle(self, *args, **options):
        split = options["split"]
        label = options["label"]

        if not re.fullmatch(r"[A-Za-z0-9_-]+", label):
            raise CommandError(
                "Use letters, numbers, underscores, or hyphens "
                "in the run label."
            )

        dataset_path = (
            settings.BASE_DIR
            / "evaluation"
            / f"retrieval_{split}.json"
        )
        cases = load_cases(dataset_path)
        before = corpus_snapshot()

        results = []

        for number, case in enumerate(cases, start=1):
            self.stdout.write(
                f"[{number}/{len(cases)}] {case['id']}"
            )

            result = evaluate_case(case)
            results.append(result)

            if result["error"]:
                self.stderr.write(
                    f"  ERROR: {result['error']['message']}"
                )

        try:
            unchanged = corpus_snapshot() == before
        except CommandError:
            unchanged = False

        summary = summarize(results)
        now = datetime.now(timezone.utc)

        report = {
            "metadata": {
                "created_at": now.isoformat(),
                "split": split,
                "label": label,
                "dataset_sha256": digest(cases),
                "corpus_sha256": digest(before),
                "corpus_unchanged": unchanged,
                "embedding_model": settings.EMBEDDING_MODEL,
                "rewrite_model": settings.CHAT_MODEL,
                "retrieval_max_distance": settings.RETRIEVAL_MAX_DISTANCE,
                "chunk_words": CHUNK_WORDS,
                "overlap_words": OVERLAP_WORDS,
                "retrieval_source_sha256": hashlib.sha256(
                    (
                        settings.BASE_DIR
                        / "support"
                        / "services"
                        / "retrieval.py"
                    ).read_bytes()
                ).hexdigest(),
                "rewrite_prompt_sha256": hashlib.sha256(
                    (PROMPTS_DIR / "rewrite_question.md").read_bytes()
                ).hexdigest(),
                "corpus": before,
            },
            "summary": summary,
            "results": results,
        }

        output_dir = settings.BASE_DIR / "evaluation" / "results"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = now.strftime("%Y%m%dT%H%M%S%fZ")
        output_path = (
            output_dir
            / f"{split}_{label}_{timestamp}.json"
        )

        with output_path.open("x", encoding="utf-8") as output:
            json.dump(
                report,
                output,
                indent=2,
                ensure_ascii=False,
            )

        self.stdout.write(json.dumps(summary, indent=2))
        self.stdout.write(f"Saved: {output_path}")

        if not unchanged:
            raise CommandError(
                "The knowledge base changed during evaluation. "
                "The saved report is not a valid baseline."
            )

        if summary["error_count"]:
            raise CommandError(
                "Some cases failed. Results were saved, but resolve "
                "the errors before treating this as a baseline."
            )