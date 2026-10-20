from django.db import transaction

from support.ai.embeddings import EmbeddingError, embed_document_texts
from support.models import DocumentChunk, KnowledgeDocument
from support.services.processing_jobs import lock_processing_job


def lock_documents(document_id):
    original_id = KnowledgeDocument.objects.values_list(
        "replaces_id",
        flat=True,
    ).get(pk=document_id)

    original = None

    if original_id is not None:
        original = KnowledgeDocument.objects.select_for_update().get(
            pk=original_id
        )

    document = KnowledgeDocument.objects.select_for_update().get(
        pk=document_id
    )

    if document.replaces_id != original_id:
        raise ValueError(
            "The replacement relationship changed. Please try again."
        )

    return document, original


def validate_indexing_state(document, original):
    if document.status == KnowledgeDocument.Status.READY:
        raise ValueError("This document is already indexed.")

    if document.status != KnowledgeDocument.Status.EXTRACTED:
        raise ValueError("Extract the document text first.")

    if original is None:
        return

    if original.status != KnowledgeDocument.Status.READY:
        raise ValueError(
            "The original document must be successfully indexed."
        )

    if document.version != original.version + 1:
        raise ValueError(
            "The replacement version number is invalid."
        )

    if original.replacement_versions.filter(
        status=KnowledgeDocument.Status.READY
    ).exclude(pk=document.pk).exists():
        raise ValueError(
            "Another replacement has already been indexed. "
            "Replace the latest version instead."
        )


def indexing_snapshot(document, original, chunks):
    return (
        document.title,
        document.version,
        document.replaces_id,
        document.file.name,
        document.is_active,
        (
            original.pk,
            original.version,
            original.is_active,
        ) if original is not None else None,
        tuple(
            (
                chunk.pk,
                chunk.position,
                chunk.page_number,
                chunk.text,
            )
            for chunk in chunks
        ),
    )


def index_document(document_id, *, job_run=None):
    # Capture a consistent input snapshot in a short transaction.
    with transaction.atomic():
        document, original = lock_documents(document_id)
        lock_processing_job(document.pk, job_run)
        validate_indexing_state(document, original)

        chunks = list(
            document.chunks.select_for_update().order_by("position")
        )

        if not chunks:
            raise ValueError("Prepare the document chunks first.")

        expected = indexing_snapshot(
            document,
            original,
            chunks,
        )
        texts = [
            f"{document.title}\n\n{chunk.text}"
            for chunk in chunks
        ]

    # No transaction or row locks are held by this function here.
    vectors = embed_document_texts(texts)

    if len(vectors) != len(texts):
        raise EmbeddingError(
            "The embedding service returned an incomplete result."
        )

    if any(len(vector) != 1536 for vector in vectors):
        raise EmbeddingError(
            "The embedding dimensions do not match the database."
        )

    # Re-lock and revalidate before publishing anything.
    with transaction.atomic():
        document, original = lock_documents(document_id)
        lock_processing_job(document.pk, job_run)
        validate_indexing_state(document, original)

        current_chunks = list(
            document.chunks.select_for_update().order_by("position")
        )

        current = indexing_snapshot(
            document,
            original,
            current_chunks,
        )

        if current != expected:
            raise ValueError(
                "The document or its chunks changed while embeddings "
                "were being prepared. Retry processing."
            )

        for chunk, vector in zip(current_chunks, vectors):
            chunk.embedding = vector

        DocumentChunk.objects.bulk_update(
            current_chunks,
            ["embedding"],
        )

        document.status = KnowledgeDocument.Status.READY
        document.processing_error = ""

        if original is not None:
            original.is_active = False
            original.save(update_fields=["is_active"])

            document.is_active = True
            document.save(
                update_fields=[
                    "status",
                    "processing_error",
                    "is_active",
                ]
            )
        else:
            document.save(
                update_fields=["status", "processing_error"]
            )

    return len(current_chunks)