from django.db import transaction

from support.ai.embeddings import EmbeddingError
from support.models import KnowledgeDocument
from support.services.chunking import prepare_document_chunks
from support.services.document_processing import (
    DocumentProcessingError,
    process_document,
)
from support.services.indexing import index_document


def process_and_index_document(document_id):
    extraction_error = None

    # Protect local preparation from overlapping submissions.
    with transaction.atomic():
        document = KnowledgeDocument.objects.select_for_update().get(
            pk=document_id
        )

        if document.status == KnowledgeDocument.Status.READY:
            return document.chunks.count()

        extracted_now = (
            document.status != KnowledgeDocument.Status.EXTRACTED
        )

        if extracted_now:
            process_document(document)

        if document.status == KnowledgeDocument.Status.FAILED:
            extraction_error = document.processing_error

        elif extracted_now or not document.chunks.exists():
            prepare_document_chunks(document.pk)

    # Keep extraction failures saved so staff can inspect them.
    if extraction_error:
        raise DocumentProcessingError(extraction_error)

    try:
        return index_document(document_id)

    except EmbeddingError as exc:
        KnowledgeDocument.objects.filter(
            pk=document_id,
            status=KnowledgeDocument.Status.EXTRACTED,
        ).update(processing_error=str(exc))

        raise

    except ValueError:
        document = KnowledgeDocument.objects.get(pk=document_id)

        if document.status == KnowledgeDocument.Status.READY:
            # Another request already completed the same document.
            return document.chunks.count()

        raise