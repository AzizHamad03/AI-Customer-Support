from time import sleep

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from support.services.document_worker import process_next_document_job


class Command(BaseCommand):
    help = "Process queued document jobs in a separate worker."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Process at most one available job and exit.",
        )
        parser.add_argument(
            "--poll-interval",
            type=float,
            default=2.0,
            help="Seconds between checks when no job is available.",
        )

    def handle(self, *args, **options):
        interval = options["poll_interval"]

        if not 0.1 <= interval <= 30:
            raise CommandError(
                "--poll-interval must be between 0.1 and 30 seconds."
            )

        self.stdout.write(
            "Document worker started. Press Ctrl+C to stop."
        )

        try:
            while True:
                close_old_connections()

                result = process_next_document_job()

                if result is not None:
                    job_id, status = result
                    self.stdout.write(
                        f"Job {job_id}: {status}"
                    )

                if options["once"]:
                    break

                if result is None:
                    sleep(interval)

        except KeyboardInterrupt:
            self.stdout.write("Document worker stopped.")