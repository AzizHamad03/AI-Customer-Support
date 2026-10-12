from django.db import models


class MessageCitation(models.Model):
    message = models.ForeignKey(
        "support.Message",
        on_delete=models.CASCADE,
        related_name="citations",
    )
    chunk = models.ForeignKey(
        "support.DocumentChunk",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    source_key = models.CharField(max_length=20)

    # Snapshots preserve the evidence even if the source later changes.
    document_title = models.CharField(max_length=200)
    document_version = models.PositiveIntegerField(
        null=True,
        blank=True,
    )
    page_number = models.PositiveIntegerField()
    source_text = models.TextField()
    is_txt = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["message", "source_key"],
                name="unique_message_source_key",
            ),
        ]