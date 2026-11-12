from datetime import UTC, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from support.demo_access import DEMO_GROUP
from support.models import (
    Conversation,
    DemoQuotaBucket,
    DocumentProcessingJob,
    KnowledgeDocument,
    SupportTicket,
)
from support.services.documents import delete_document


def expired_workspaces(cutoff):
    return get_user_model().objects.filter(
        groups__name=DEMO_GROUP,
        username__startswith="demo-",
        is_staff=False,
        is_superuser=False,
        date_joined__lt=cutoff,
    )


@transaction.atomic
def remove_workspace(user_id, cutoff):
    user = (
        expired_workspaces(cutoff)
        .select_for_update(of=("self",))
        .filter(pk=user_id)
        .first()
    )
    if user is None:
        return False

    documents = list(
        KnowledgeDocument.objects.select_for_update()
        .filter(uploaded_by_id=user_id)
        .order_by("pk")
    )
    jobs = list(
        DocumentProcessingJob.objects.select_for_update()
        .filter(document_id__in=[document.pk for document in documents])
        .order_by("pk")
    )

    now = timezone.now()
    if any(
        job.status == DocumentProcessingJob.Status.PROCESSING
        and job.lease_expires_at is not None
        and job.lease_expires_at > now
        for job in jobs
    ):
        return False

    # Delete newer versions first because they protect earlier versions.
    for document in sorted(documents, key=lambda item: item.version, reverse=True):
        delete_document(document.pk)

    SupportTicket.objects.filter(conversation__user_id=user_id).delete()
    Conversation.objects.filter(user_id=user_id).delete()
    user.delete()
    return True


class Command(BaseCommand):
    help = "Remove staff demo workspaces older than 24 hours and old quota counters."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show which workspaces would be considered for cleanup.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        cutoff = now - timedelta(hours=24)
        quota_cutoff = now.astimezone(UTC).date() - timedelta(days=7)

        user_ids = list(
            expired_workspaces(cutoff)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        old_quotas = DemoQuotaBucket.objects.filter(day__lt=quota_cutoff)

        if options["dry_run"]:
            self.stdout.write(
                f"Expired workspace IDs: {user_ids}. "
                f"Old quota rows: {old_quotas.count()}."
            )
            return

        removed = 0
        for user_id in user_ids:
            try:
                removed += int(remove_workspace(user_id, cutoff))
            except ProtectedError:
                self.stderr.write(
                    f"Skipped workspace {user_id} because a related record "
                    "still protects its data."
                )

        quota_rows, _ = old_quotas.delete()
        self.stdout.write(
            f"Removed {removed} of {len(user_ids)} expired workspaces "
            f"and {quota_rows} old quota rows."
        )