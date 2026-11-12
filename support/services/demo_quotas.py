from contextlib import contextmanager
from datetime import UTC, datetime, time, timedelta

from django.db import transaction

from support.demo_access import is_demo_user
from support.models import DemoQuotaBucket


DEMO_UPLOAD_MAX_BYTES = 2 * 1024 * 1024
DEMO_UPLOADS_PER_WORKSPACE = 3
DEMO_UPLOADS_GLOBAL = 40


class DemoUploadQuotaExceeded(Exception):
    def __init__(self, message, retry_after):
        super().__init__(message)
        self.retry_after = retry_after


@contextmanager
def reserve_demo_upload(user):
    if not is_demo_user(user):
        yield
        return

    now = datetime.now(UTC)
    tomorrow = datetime.combine(
        now.date() + timedelta(days=1),
        time.min,
        tzinfo=UTC,
    )
    retry_after = int((tomorrow - now).total_seconds()) + 1

    limits = (
        (
            "global",
            DEMO_UPLOADS_GLOBAL,
            "The demo has reached its daily upload limit.",
        ),
        (
            f"workspace:{user.pk}",
            DEMO_UPLOADS_PER_WORKSPACE,
            "This workspace has used all three of its daily uploads.",
        ),
    )

    with transaction.atomic():
        for scope, limit, message in limits:
            bucket, _ = DemoQuotaBucket.objects.select_for_update().get_or_create(
                action="upload",
                scope=scope,
                day=now.date(),
            )
            if bucket.used >= limit:
                raise DemoUploadQuotaExceeded(
                    f"{message} Try again after midnight UTC.",
                    retry_after,
                )

            bucket.used += 1
            bucket.save(update_fields=["used"])

        yield