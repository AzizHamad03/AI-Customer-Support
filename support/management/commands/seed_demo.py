from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from support.models import KnowledgeDocument
from support.services.documents import create_document
from support.services.document_worker import process_next_document_job
from support.services.processing_jobs import queue_document_processing


POLICIES = (
    ("Demo Store Shipping Policy", "shipping", "shipping_policy.txt"),
    ("Demo Store Returns Policy", "returns", "returns_policy.txt"),
    ("Demo Store Product Catalog", "products", "product_catalog.txt"),
    ("Demo Store Support Policy", "general", "support_policy.txt"),
)


def get_or_create_policy(title, category, path, staff_user):
    with transaction.atomic():
        # Serialize lookup and creation across concurrent seed runs.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s)::bigint)",
                ["support.seed_demo"],
            )

        matches = KnowledgeDocument.objects.filter(title=title)

        try:
            document = matches.get(is_active=True)
        except KnowledgeDocument.MultipleObjectsReturned as exc:
            raise CommandError(f"{title}: multiple active versions.") from exc
        except KnowledgeDocument.DoesNotExist:
            if matches.exists():
                raise CommandError(
                    f"{title}: existing versions are inactive. "
                    "Activate the intended version in the staff workspace."
                )

            with path.open("rb") as source:
                return create_document(
                    title=title,
                    category=category,
                    file=File(source, name=path.name),
                    uploaded_by=staff_user,
                )

        if document.category != category:
            raise CommandError(
                f"{title}: the existing document has a different category."
            )

        return document


class Command(BaseCommand):
    help = "Load and index the four sample store policies."

    def add_arguments(self, parser):
        parser.add_argument("--staff-username", required=True)

    def handle(self, *args, **options):
        staff_user = get_user_model().objects.filter(
            username=options["staff_username"],
            is_active=True,
            is_staff=True,
        ).first()

        if staff_user is None:
            raise CommandError(
                "Provide the username of an active staff account."
            )

        policies_dir = settings.BASE_DIR / "sample_data" / "policies"

        for title, category, filename in POLICIES:
            path = policies_dir / filename
            if not path.is_file():
                raise CommandError(f"Sample file missing: {path}")

            document = get_or_create_policy(title, category, path, staff_user)
            if document.status == KnowledgeDocument.Status.READY:
                self.stdout.write(f"Already ready: {title}")
                continue

            job, _ = queue_document_processing(document.pk)
            if job is not None:
                process_next_document_job(document_id=document.pk)

            document.refresh_from_db()
            if (
                document.status != KnowledgeDocument.Status.READY
                or not document.is_active
            ):
                reason = document.processing_error
                if job is not None and not reason:
                    job.refresh_from_db()
                    reason = job.error

                raise CommandError(
                    f"{title}: {reason or 'Indexing has not finished. Retry shortly.'}"
                )

            self.stdout.write(f"Indexed: {title}")

        self.stdout.write(self.style.SUCCESS("All four demo policies are ready."))