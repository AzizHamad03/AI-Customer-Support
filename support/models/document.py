from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models


def validate_file_size(file):
    if file.size > 10 * 1024 * 1024:
        raise ValidationError("The file must be 10 MB or smaller.")


def document_upload_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"documents/{uuid4().hex}{extension}"


class KnowledgeDocument(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        EXTRACTED = "extracted", "Extracted"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    class Category(models.TextChoices):
        SHIPPING = "shipping", "Shipping"
        RETURNS = "returns", "Returns"
        PRODUCTS = "products", "Products"
        GENERAL = "general", "General"

    title = models.CharField(max_length=200)

    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.GENERAL,
    )

    file = models.FileField(
        upload_to=document_upload_path,
        validators=[
            FileExtensionValidator(["pdf", "txt"]),
            validate_file_size,
        ],
    )

    version = models.PositiveIntegerField(
        default=1,
        editable=False,
    )

    replaces = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="replacement_versions",
        editable=False,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        editable=False,
    )

    extracted_pages = models.JSONField(
        default=list,
        blank=True,
        editable=False,
    )

    processing_error = models.TextField(
        blank=True,
        editable=False,
    )

    is_active = models.BooleanField(default=True)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_documents",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title