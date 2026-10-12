import re
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.validators import MinLengthValidator
from django.db import models


class SupportTicket(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In Progress"
        RESOLVED = "resolved", "Resolved"

    conversation = models.ForeignKey(
        "support.Conversation",
        on_delete=models.PROTECT,
        related_name="tickets",
    )
    request_id = models.UUIDField(
        default=uuid4,
        unique=True,
        editable=False,
    )
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    description = models.TextField(
        max_length=2000,
        validators=[MinLengthValidator(10)],
    )
    order_reference = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def reference(self):
        return f"TKT-{self.pk:06d}" if self.pk else "Unsaved ticket"

    def clean(self):
        super().clean()

        self.contact_email = self.contact_email.strip()
        self.contact_phone = self.contact_phone.strip()
        self.description = self.description.strip()
        self.order_reference = self.order_reference.strip()

        errors = {}

        if not self.contact_email and not self.contact_phone:
            errors["__all__"] = (
                "Provide an email address or phone number."
            )

        if self.contact_phone:
            digits = re.sub(r"\D", "", self.contact_phone)

            if (
                not re.fullmatch(r"\+?[0-9 ()-]+", self.contact_phone)
                or not 7 <= len(digits) <= 15
            ):
                errors["contact_phone"] = (
                    "Enter a valid phone number with 7–15 digits."
                )

        if len(self.description) < 10:
            errors["description"] = (
                "Describe the issue using at least 10 characters."
            )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.reference