from django.db import models


class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user", "Customer"
        ASSISTANT = "assistant", "Assistant"

    conversation = models.ForeignKey(
        "support.Conversation",
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]