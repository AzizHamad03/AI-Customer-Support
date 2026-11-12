from django.db import models


class DemoQuotaBucket(models.Model):
    action = models.CharField(max_length=40)
    scope = models.CharField(max_length=80)
    day = models.DateField()
    used = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["action", "scope", "day"],
                name="support_demo_quota_unique_bucket",
            ),
        ]