from contextlib import contextmanager
from hashlib import sha256
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

DEMO_CHAT_PER_VISITOR = 20
DEMO_CHAT_GLOBAL = 150
DEMO_SEARCH_PER_WORKSPACE = 10
DEMO_SEARCH_GLOBAL = 100


class DemoActionQuotaExceeded(Exception):
    def __init__(self, message, retry_after):
        super().__init__(message)
        self.retry_after = retry_after


def _consume_daily_quota(action, scope, visitor_limit, global_limit, label):
    now = datetime.now(UTC)
    tomorrow = datetime.combine(
        now.date() + timedelta(days=1),
        time.min,
        tzinfo=UTC,
    )
    retry_after = int((tomorrow - now).total_seconds()) + 1

    limits = (
        ("global", global_limit, f"The demo has reached its daily {label} limit."),
        (scope, visitor_limit, f"You’ve reached your daily {label} limit."),
    )

    with transaction.atomic():
        for bucket_scope, limit, message in limits:
            bucket, _ = DemoQuotaBucket.objects.select_for_update().get_or_create(
                action=action,
                scope=bucket_scope,
                day=now.date(),
            )

            if bucket.used >= limit:
                raise DemoActionQuotaExceeded(
                    f"{message} Try again after midnight UTC.",
                    retry_after,
                )

            bucket.used += 1
            bucket.save(update_fields=["used"])


def consume_demo_chat_quota(user, session):
    if user.is_staff:
        return

    if user.is_authenticated:
        scope = f"user:{user.pk}"
    else:
        if session.session_key is None:
            session.save()
        session_digest = sha256(session.session_key.encode("utf-8")).hexdigest()
        scope = f"session:{session_digest}"

    _consume_daily_quota(
        "chat",
        scope,
        DEMO_CHAT_PER_VISITOR,
        DEMO_CHAT_GLOBAL,
        "chat",
    )


def consume_demo_search_quota(user):
    if not is_demo_user(user):
        return

    _consume_daily_quota(
        "knowledge_search",
        f"workspace:{user.pk}",
        DEMO_SEARCH_PER_WORKSPACE,
        DEMO_SEARCH_GLOBAL,
        "knowledge search",
    )