from django.db import transaction

from support.ai.embeddings import EmbeddingError
from support.models import KnowledgeDocument
from support.services.chunking import prepare_document_chunks
from support.services.document_processing import (
    DocumentProcessingError,
    process_document,
)
from support.services.indexing import index_document
from support.services.processing_jobs import lock_processing_job


def save_indexing_error(document_id, error, job_run):
    with transaction.atomic():
        document = KnowledgeDocument.objects.select_for_update().get(
            pk=document_id
        )
        lock_processing_job(document.pk, job_run)

        if document.status == KnowledgeDocument.Status.EXTRACTED:
            document.processing_error = str(error)
            document.save(update_fields=["processing_error"])


def process_and_index_document(document_id, *, job_run=None):
    extraction_error = None

    # Local extraction/chunk preparation is serialized per document.
    with transaction.atomic():
        document = KnowledgeDocument.objects.select_for_update().get(
            pk=document_id
        )
        lock_processing_job(document.pk, job_run)

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

    # Commit extraction failures so staff can inspect them.
    if extraction_error:
        raise DocumentProcessingError(extraction_error)

    try:
        return index_document(
            document_id,
            job_run=job_run,
        )

    except EmbeddingError as exc:
        save_indexing_error(document_id, exc, job_run)
        raise

    except ValueError:
        document = KnowledgeDocument.objects.get(pk=document_id)

        if document.status == KnowledgeDocument.Status.READY:
            return document.chunks.count()

        raise