from django.db import transaction

from support.ai.embeddings import EmbeddingError, embed_document_texts
from support.models import DocumentChunk, KnowledgeDocument


@transaction.atomic
def index_document(document_id):
    # Lock the original first so replacement operations use the same
    # lock order as the document service.
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

    if document.status == KnowledgeDocument.Status.READY:
        raise ValueError("This document is already indexed.")

    if document.status != KnowledgeDocument.Status.EXTRACTED:
        raise ValueError("Extract the document text first.")

    if original is not None:
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

    chunks = list(document.chunks.order_by("position"))

    if not chunks:
        raise ValueError("Prepare the document chunks first.")

    vectors = embed_document_texts(
        [
            f"{document.title}\n\n{chunk.text}"
            for chunk in chunks
        ]
    )

    if len(vectors) != len(chunks):
        raise EmbeddingError(
            "The embedding service returned an incomplete result."
        )

    for chunk, vector in zip(chunks, vectors):
        if len(vector) != 1536:
            raise EmbeddingError(
                "The embedding dimensions do not match the database."
            )

        chunk.embedding = vector

    DocumentChunk.objects.bulk_update(chunks, ["embedding"])

    document.status = KnowledgeDocument.Status.READY
    document.processing_error = ""

    if original is not None:
        # Both changes commit together only after embeddings succeed.
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

    return len(chunks)