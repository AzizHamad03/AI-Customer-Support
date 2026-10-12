from django.db import models
from pgvector.django import VectorField

class DocumentChunk(models.Model):
    document = models.ForeignKey(
        "support.KnowledgeDocument",
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    position = models.PositiveIntegerField()
    page_number = models.PositiveIntegerField()
    text = models.TextField()
    embedding = VectorField(
        dimensions=1536,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "position"],
                name="unique_document_chunk_position",
            ),
        ]

    def __str__(self):
        return f"{self.document.title} — chunk {self.position + 1}"