from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import (
    close_old_connections,
    connection,
    connections,
)
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from support.ai.embeddings import EmbeddingError
from support.models import DocumentProcessingJob, KnowledgeDocument
from support.services.chunking import prepare_document_chunks
from support.services.document_pipeline import process_and_index_document
from support.services.document_processing import process_document
from support.services.document_worker import process_next_document_job
from support.services.documents import (
    create_document,
    create_replacement_document,
)
from support.services.indexing import index_document
from support.services.processing_jobs import (
    JobLeaseLost,
    claim_next_job,
    queue_document_processing,
)


VECTOR = [1.0] + [0.0] * 1535


class BackgroundDocumentTests(TransactionTestCase):
    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)

        media_setting = override_settings(MEDIA_ROOT=media.name)
        media_setting.enable()
        self.addCleanup(media_setting.disable)

        self.staff = get_user_model().objects.create_user(
            username="background-document-staff",
            is_staff=True,
        )

    def document(self, content=b"Shipping costs SAR 25."):
        return create_document(
            title="Background test policy",
            category="shipping",
            file=SimpleUploadedFile("policy.txt", content),
            uploaded_by=self.staff,
        )

    def test_post_queues_once_without_running_the_pipeline(self):
        document = self.document()
        self.client.force_login(self.staff)

        url = reverse(
            "support:document_process",
            args=[document.pk],
        )

        with patch(
            "support.services.indexing.embed_document_texts"
        ) as embed:
            self.assertEqual(self.client.post(url).status_code, 302)
            self.assertEqual(self.client.post(url).status_code, 302)

        embed.assert_not_called()

        document.refresh_from_db()
        job = DocumentProcessingJob.objects.get()

        self.assertEqual(document.status, "pending")
        self.assertEqual(document.chunks.count(), 0)
        self.assertEqual(job.status, "queued")
        self.assertEqual(job.attempts, 0)

    def test_worker_requests_embeddings_outside_transaction(self):
        document = self.document()
        queue_document_processing(document.pk)

        def embed(texts):
            self.assertFalse(connection.in_atomic_block)
            return [VECTOR for _ in texts]

        with patch(
            "support.services.indexing.embed_document_texts",
            side_effect=embed,
        ):
            process_next_document_job()

        document.refresh_from_db()
        job = DocumentProcessingJob.objects.get()

        self.assertEqual(document.status, "ready")
        self.assertEqual(job.status, "succeeded")
        self.assertEqual(job.attempts, 1)
        self.assertTrue(
            document.chunks.filter(
                embedding__isnull=False
            ).exists()
        )

    def test_failed_embedding_can_retry_with_existing_chunks(self):
        document = self.document()
        job, _ = queue_document_processing(document.pk)

        with patch(
            "support.services.indexing.embed_document_texts",
            side_effect=EmbeddingError("Service unavailable"),
        ):
            process_next_document_job()

        document.refresh_from_db()
        job.refresh_from_db()

        self.assertEqual(document.status, "extracted")
        self.assertEqual(job.status, "failed")

        chunk_ids = list(
            document.chunks.values_list("pk", flat=True)
        )

        retried_job, queued = queue_document_processing(document.pk)

        self.assertTrue(queued)
        self.assertEqual(retried_job.pk, job.pk)

        with patch(
            "support.services.indexing.embed_document_texts",
            return_value=[VECTOR],
        ):
            process_next_document_job()

        document.refresh_from_db()
        job.refresh_from_db()

        self.assertEqual(document.status, "ready")
        self.assertEqual(job.status, "succeeded")
        self.assertEqual(job.attempts, 2)
        self.assertEqual(
            list(document.chunks.values_list("pk", flat=True)),
            chunk_ids,
        )

    def test_replacement_switches_only_after_successful_retry(self):
        original = self.document()

        with patch(
            "support.services.indexing.embed_document_texts",
            return_value=[VECTOR],
        ):
            process_and_index_document(original.pk)

        replacement = create_replacement_document(
            document_id=original.pk,
            file=SimpleUploadedFile(
                "replacement.txt",
                b"Shipping costs SAR 20.",
            ),
            uploaded_by=self.staff,
        )
        queue_document_processing(replacement.pk)

        with patch(
            "support.services.indexing.embed_document_texts",
            side_effect=EmbeddingError("Service unavailable"),
        ):
            process_next_document_job()

        original.refresh_from_db()
        replacement.refresh_from_db()

        self.assertTrue(original.is_active)
        self.assertFalse(replacement.is_active)
        self.assertNotEqual(replacement.status, "ready")

        queue_document_processing(replacement.pk)

        with patch(
            "support.services.indexing.embed_document_texts",
            return_value=[VECTOR],
        ):
            process_next_document_job()

        original.refresh_from_db()
        replacement.refresh_from_db()

        self.assertFalse(original.is_active)
        self.assertTrue(replacement.is_active)
        self.assertEqual(replacement.status, "ready")

    def test_two_workers_cannot_claim_the_same_active_job(self):
        document = self.document()
        job, _ = queue_document_processing(document.pk)
        barrier = Barrier(2)

        def claim():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                claimed = claim_next_job()
                return claimed.pk if claimed else None
            finally:
                connections["default"].close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(claim),
                executor.submit(claim),
            ]
            results = [
                future.result(timeout=20)
                for future in futures
            ]

        self.assertEqual(results.count(job.pk), 1)
        self.assertEqual(results.count(None), 1)

    def test_expired_attempt_cannot_publish_after_reclaim(self):
        document = self.document()
        queue_document_processing(document.pk)

        first = claim_next_job()
        first_run = (first.pk, first.run_token)

        def reclaim_during_embedding(texts):
            self.assertFalse(connection.in_atomic_block)

            DocumentProcessingJob.objects.filter(
                pk=first.pk
            ).update(
                lease_expires_at=(
                    timezone.now() - timedelta(seconds=1)
                )
            )

            second = claim_next_job()

            self.assertEqual(second.pk, first.pk)
            self.assertNotEqual(second.run_token, first.run_token)

            return [VECTOR for _ in texts]

        with patch(
            "support.services.indexing.embed_document_texts",
            side_effect=reclaim_during_embedding,
        ):
            with self.assertRaises(JobLeaseLost):
                process_and_index_document(
                    document.pk,
                    job_run=first_run,
                )

        document.refresh_from_db()

        self.assertEqual(document.status, "extracted")
        self.assertFalse(
            document.chunks.filter(
                embedding__isnull=False
            ).exists()
        )

    def test_changed_chunks_reject_embeddings_without_partial_save(self):
        document = self.document()
        process_document(document)
        prepare_document_chunks(document.pk)

        def change_chunk(texts):
            self.assertFalse(connection.in_atomic_block)

            document.chunks.update(
                text="The policy changed during embedding."
            )
            return [VECTOR for _ in texts]

        with patch(
            "support.services.indexing.embed_document_texts",
            side_effect=change_chunk,
        ):
            with self.assertRaisesRegex(ValueError, "changed"):
                index_document(document.pk)

        document.refresh_from_db()

        self.assertEqual(document.status, "extracted")
        self.assertFalse(
            document.chunks.filter(
                embedding__isnull=False
            ).exists()
        )