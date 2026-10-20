from django.db import models
from django.utils import timezone


class DocumentProcessingJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    document = models.OneToOneField(
        "support.KnowledgeDocument",
        on_delete=models.CASCADE,
        related_name="processing_job",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
    )
    queued_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    attempts = models.PositiveIntegerField(default=0)
    run_token = models.UUIDField(
        null=True,
        blank=True,
        editable=False,
    )
    lease_expires_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["queued_at", "pk"]
        indexes = [
            models.Index(
                fields=["status", "queued_at"],
                name="document_job_queue_idx",
            ),
        ]

    @property
    def is_busy(self):
        return self.status in {
            self.Status.QUEUED,
            self.Status.PROCESSING,
        }

    def __str__(self):
        return (
            f"Document {self.document_id}: "
            f"{self.get_status_display()}"
        )