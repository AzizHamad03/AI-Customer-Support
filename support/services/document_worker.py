import logging

from support.ai.embeddings import EmbeddingError
from support.models import DocumentProcessingJob, KnowledgeDocument
from support.services.document_pipeline import process_and_index_document
from support.services.document_processing import DocumentProcessingError
from support.services.processing_jobs import (
    JobLeaseLost,
    claim_next_job,
    finish_job,
)


logger = logging.getLogger(__name__)


def process_next_document_job():
    job = claim_next_job()

    if job is None:
        return None

    job_run = (job.pk, job.run_token)
    error = ""

    try:
        process_and_index_document(
            job.document_id,
            job_run=job_run,
        )

    except JobLeaseLost:
        return job.pk, "superseded"

    except (
        DocumentProcessingError,
        EmbeddingError,
        ValueError,
        KnowledgeDocument.DoesNotExist,
    ) as exc:
        status = DocumentProcessingJob.Status.FAILED
        error = str(exc)

    except Exception:
        logger.exception(
            "Unexpected processing failure for document %s",
            job.document_id,
        )
        status = DocumentProcessingJob.Status.FAILED
        error = (
            "Document processing failed unexpectedly. "
            "Please retry. If it continues, check the server logs."
        )

    else:
        status = DocumentProcessingJob.Status.SUCCEEDED

    saved = finish_job(
        job_run,
        status=status,
        error=error,
    )

    return job.pk, status if saved else "superseded"