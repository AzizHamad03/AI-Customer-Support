from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from support.models import (
    DocumentProcessingJob,
    KnowledgeDocument,
)


class JobLeaseLost(Exception):
    pass


@transaction.atomic
def queue_document_processing(document_id):
    document = KnowledgeDocument.objects.select_for_update().get(
        pk=document_id
    )

    if document.status == KnowledgeDocument.Status.READY:
        return None, False

    job, created = (
        DocumentProcessingJob.objects.select_for_update()
        .get_or_create(document=document)
    )

    if not created and job.is_busy:
        return job, False

    if not created:
        job.status = DocumentProcessingJob.Status.QUEUED
        job.queued_at = timezone.now()
        job.started_at = None
        job.finished_at = None
        job.run_token = None
        job.lease_expires_at = None
        job.error = ""
        job.save(
            update_fields=[
                "status",
                "queued_at",
                "started_at",
                "finished_at",
                "run_token",
                "lease_expires_at",
                "error",
            ]
        )

    document.processing_error = ""
    document.save(update_fields=["processing_error"])

    return job, True


@transaction.atomic
def claim_next_job():
    now = timezone.now()

    job = (
        DocumentProcessingJob.objects.select_for_update(
            skip_locked=True
        )
        .filter(
            Q(status=DocumentProcessingJob.Status.QUEUED)
            | Q(
                status=DocumentProcessingJob.Status.PROCESSING,
                lease_expires_at__lte=now,
            )
        )
        .order_by("queued_at", "pk")
        .first()
    )

    if job is None:
        return None

    job.status = DocumentProcessingJob.Status.PROCESSING
    job.started_at = now
    job.finished_at = None
    job.attempts += 1
    job.run_token = uuid4()
    job.lease_expires_at = now + timedelta(
        seconds=settings.DOCUMENT_JOB_LEASE_SECONDS
    )
    job.error = ""
    job.save(
        update_fields=[
            "status",
            "started_at",
            "finished_at",
            "attempts",
            "run_token",
            "lease_expires_at",
            "error",
        ]
    )

    return job


def lock_processing_job(document_id, job_run=None):
    """
    Call inside a transaction after locking the document.

    Document locks always precede job locks in processing operations.
    """
    job = (
        DocumentProcessingJob.objects.select_for_update()
        .filter(document_id=document_id)
        .first()
    )

    if job_run is None:
        if job is not None and job.is_busy:
            raise ValueError(
                "This document has queued or running processing. "
                "Let the background worker finish it."
            )
        return job

    job_id, token = job_run

    if (
        job is None
        or job.pk != job_id
        or job.status != DocumentProcessingJob.Status.PROCESSING
        or job.run_token != token
        or job.lease_expires_at is None
        or job.lease_expires_at <= timezone.now()
    ):
        raise JobLeaseLost(
            "This processing attempt no longer owns the job."
        )

    return job


def finish_job(job_run, *, status, error=""):
    job_id, token = job_run
    now = timezone.now()

    updated = DocumentProcessingJob.objects.filter(
        pk=job_id,
        run_token=token,
        status=DocumentProcessingJob.Status.PROCESSING,
        lease_expires_at__gt=now,
    ).update(
        status=status,
        finished_at=now,
        lease_expires_at=None,
        error=error[:2000],
    )

    return bool(updated)