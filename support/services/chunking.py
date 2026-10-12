import re

from django.db import transaction

from support.models import DocumentChunk, KnowledgeDocument


CHUNK_WORDS = 200
OVERLAP_WORDS = 30


def split_text(text, chunk_words=CHUNK_WORDS, overlap_words=OVERLAP_WORDS):
    """Split at word boundaries while preserving original formatting."""
    if chunk_words <= 0 or not 0 <= overlap_words < chunk_words:
        raise ValueError("Invalid chunk size or overlap.")

    words = list(re.finditer(r"\S+", text))
    chunks = []
    start = 0

    while start < len(words):
        end = min(start + chunk_words, len(words))

        chunk = text[
            words[start].start():words[end - 1].end()
        ].strip()

        chunks.append(chunk)

        if end == len(words):
            break

        start = end - overlap_words

    return chunks


@transaction.atomic
def prepare_document_chunks(document_id):
    document = KnowledgeDocument.objects.select_for_update().get(
        pk=document_id
    )

    if document.status != KnowledgeDocument.Status.EXTRACTED:
        raise ValueError(
            "Extract the document text before preparing chunks."
        )

    chunks = []

    for page in document.extracted_pages:
        for text in split_text(page["text"]):
            chunks.append(
                DocumentChunk(
                    document=document,
                    position=len(chunks),
                    page_number=page["page"],
                    text=text,
                )
            )

    if not chunks:
        raise ValueError("This document has no readable text to split.")

    # Repeating this step replaces the previous chunks instead of
    # creating duplicates. The transaction makes the replacement atomic.
    document.chunks.all().delete()
    DocumentChunk.objects.bulk_create(chunks)

    return len(chunks)