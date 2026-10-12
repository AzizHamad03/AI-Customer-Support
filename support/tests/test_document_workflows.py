from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

from support.ai.embeddings import EmbeddingError
from support.forms import DocumentUploadForm
from support.models import KnowledgeDocument
from support.services.chunking import prepare_document_chunks, split_text
from support.services.document_processing import process_document
from support.services.documents import (
    create_document,
    create_replacement_document,
    set_document_active,
)
from support.services.indexing import index_document
from support.services.retrieval import search_knowledge_base

from support.services.document_pipeline import (
    process_and_index_document,
)
from support.services.document_processing import (
    DocumentProcessingError,
)

VECTOR = [1.0] + [0.0] * 1535


def make_pdf(*, text=False, encrypted=False):
    """Create small PDFs without adding another dependency."""
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)

    if text:
        # A blank first page checks that source page numbers are preserved.
        page = writer.add_blank_page(width=300, height=300)

        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })

        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({
                NameObject("/F1"): font,
            }),
        })

        stream = DecodedStreamObject()
        stream.set_data(
            b"BT /F1 12 Tf 20 250 Td "
            b"(Shipping costs SAR 25.) Tj ET"
        )
        page[NameObject("/Contents")] = stream

    if encrypted:
        writer.encrypt("test-only-password")

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class DocumentWorkflowTests(TestCase):
    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)

        setting = override_settings(MEDIA_ROOT=media.name)
        setting.enable()
        self.addCleanup(setting.disable)

        self.staff = get_user_model().objects.create_user(
            username="document-staff",
            is_staff=True,
        )

    def document(
        self,
        content=b"Shipping costs SAR 25.",
        name="policy.txt",
    ):
        return create_document(
            title="Shipping policy",
            category="shipping",
            file=SimpleUploadedFile(name, content),
            uploaded_by=self.staff,
        )

    def prepared(self, content=b"Shipping costs SAR 25."):
        document = self.document(content)
        process_document(document)
        prepare_document_chunks(document.pk)
        return document

    def index(self, document):
        vectors = [
            VECTOR for _ in range(document.chunks.count())
        ]

        with patch(
            "support.services.indexing.embed_document_texts",
            return_value=vectors,
        ):
            index_document(document.pk)

        document.refresh_from_db()

    def replacement(self, original):
        return create_replacement_document(
            document_id=original.pk,
            file=SimpleUploadedFile(
                "updated.txt",
                b"Shipping costs SAR 20.",
            ),
            uploaded_by=self.staff,
        )

    def test_upload_rejects_bad_extension_and_oversized_file(self):
        uploads = [
            ("policy.exe", b"text"),
            ("policy.txt", b"x" * (10 * 1024 * 1024 + 1)),
        ]

        for name, content in uploads:
            with self.subTest(name=name):
                form = DocumentUploadForm(
                    data={
                        "title": "Policy",
                        "category": "shipping",
                    },
                    files={
                        "file": SimpleUploadedFile(name, content),
                    },
                )

                self.assertFalse(form.is_valid())
                self.assertIn("file", form.errors)

        self.assertEqual(KnowledgeDocument.objects.count(), 0)

    def test_txt_extraction_cleans_bom_and_null_characters(self):
        document = self.document(
            b"\xef\xbb\xbf Shipping\x00 costs SAR 25. "
        )

        process_document(document)
        document.refresh_from_db()

        self.assertEqual(document.status, "extracted")
        self.assertEqual(
            document.extracted_pages,
            [{"page": 1, "text": "Shipping costs SAR 25."}],
        )

    def test_empty_and_invalid_utf8_documents_fail(self):
        for content in [b"   ", b"\xff\xfe"]:
            with self.subTest(content=content):
                document = self.document(content)
                process_document(document)
                document.refresh_from_db()

                self.assertEqual(document.status, "failed")
                self.assertEqual(document.extracted_pages, [])
                self.assertTrue(document.processing_error)

    def test_pdf_keeps_original_page_numbers(self):
        document = self.document(
            make_pdf(text=True),
            "policy.pdf",
        )

        process_document(document)

        self.assertEqual(document.status, "extracted")
        self.assertEqual(
            document.extracted_pages[0]["page"],
            2,
        )
        self.assertIn(
            "SAR 25",
            document.extracted_pages[0]["text"],
        )

        prepare_document_chunks(document.pk)
        self.assertEqual(document.chunks.get().page_number, 2)

    def test_blank_encrypted_and_invalid_pdfs_fail(self):
        contents = [
            make_pdf(),
            make_pdf(encrypted=True),
            b"not a PDF",
        ]

        for content in contents:
            with self.subTest(content=content[:10]):
                document = self.document(content, "policy.pdf")

                with patch(
                    "support.services.document_processing.logger.exception"
                ):
                    process_document(document)

                document.refresh_from_db()

                self.assertEqual(document.status, "failed")
                self.assertEqual(document.extracted_pages, [])
                self.assertTrue(document.processing_error)

    def test_extracted_text_limit_is_enforced(self):
        document = self.document(b"x" * 31)

        with patch(
            "support.services.document_processing.MAX_CHARACTERS",
            30,
        ):
            process_document(document)

        self.assertEqual(document.status, "failed")
        self.assertEqual(document.extracted_pages, [])

    def test_chunks_require_extraction(self):
        document = self.document()

        with self.assertRaises(ValueError):
            prepare_document_chunks(document.pk)

        self.assertEqual(document.chunks.count(), 0)

    def test_chunk_overlap_and_repeated_preparation(self):
        self.assertEqual(
            split_text("a b c d e f g h", 5, 2),
            ["a b c d e", "d e f g h"],
        )

        document = self.prepared(("word " * 300).encode())

        first = list(
            document.chunks.values_list(
                "position",
                "page_number",
                "text",
            )
        )

        prepare_document_chunks(document.pk)

        self.assertEqual(
            list(
                document.chunks.values_list(
                    "position",
                    "page_number",
                    "text",
                )
            ),
            first,
        )
        self.assertEqual(document.chunks.count(), 2)

    def test_indexing_requires_prepared_chunks(self):
        document = self.document()

        with self.assertRaises(ValueError):
            index_document(document.pk)

        process_document(document)

        with self.assertRaises(ValueError):
            index_document(document.pk)

    def test_bad_embedding_results_do_not_partially_index(self):
        document = self.prepared(("word " * 300).encode())

        results = [
            [VECTOR],
            [VECTOR, [1.0, 0.0]],
        ]

        for vectors in results:
            with self.subTest(
                vector_lengths=[len(v) for v in vectors]
            ):
                with patch(
                    "support.services.indexing.embed_document_texts",
                    return_value=vectors,
                ):
                    with self.assertRaises(EmbeddingError):
                        index_document(document.pk)

                document.refresh_from_db()

                self.assertEqual(document.status, "extracted")
                self.assertFalse(
                    document.chunks.filter(
                        embedding__isnull=False
                    ).exists()
                )

    def test_indexing_api_failure_can_be_retried(self):
        document = self.prepared()

        with patch(
            "support.services.indexing.embed_document_texts",
            side_effect=EmbeddingError("Service unavailable"),
        ):
            with self.assertRaises(EmbeddingError):
                index_document(document.pk)

        document.refresh_from_db()

        self.assertEqual(document.status, "extracted")
        self.assertFalse(
            document.chunks.filter(
                embedding__isnull=False
            ).exists()
        )

        self.index(document)

        self.assertEqual(document.status, "ready")
        self.assertTrue(
            document.chunks.filter(
                embedding__isnull=False
            ).exists()
        )

        with self.assertRaises(ValueError):
            index_document(document.pk)

    def test_failed_replacement_preserves_original_then_retry_switches(self):
        original = self.prepared()
        self.index(original)

        replacement = self.replacement(original)

        self.assertEqual(replacement.version, 2)
        self.assertEqual(replacement.replaces_id, original.pk)
        self.assertFalse(replacement.is_active)

        process_document(replacement)
        prepare_document_chunks(replacement.pk)

        with patch(
            "support.services.indexing.embed_document_texts",
            side_effect=EmbeddingError("Service unavailable"),
        ):
            with self.assertRaises(EmbeddingError):
                index_document(replacement.pk)

        original.refresh_from_db()
        replacement.refresh_from_db()

        self.assertTrue(original.is_active)
        self.assertEqual(original.status, "ready")
        self.assertFalse(replacement.is_active)
        self.assertEqual(replacement.status, "extracted")
        self.assertFalse(
            replacement.chunks.filter(
                embedding__isnull=False
            ).exists()
        )

        self.index(replacement)
        original.refresh_from_db()

        self.assertFalse(original.is_active)
        self.assertTrue(replacement.is_active)
        self.assertEqual(replacement.status, "ready")

        with self.assertRaises(ValueError):
            set_document_active(original.pk, True)

    def test_pending_replacement_prevents_another_upload(self):
        original = self.prepared()
        self.index(original)

        self.replacement(original)

        with self.assertRaises(ValueError):
            self.replacement(original)

        self.assertEqual(
            original.replacement_versions.count(),
            1,
        )

    @patch(
        "support.services.retrieval.embed_question",
        return_value=VECTOR,
    )
    def test_replacement_changes_actual_vector_retrieval(self, _embed):
        original = self.prepared()
        self.index(original)

        replacement = self.replacement(original)

        before = search_knowledge_base("Shipping cost")

        self.assertEqual(
            {match["chunk_id"] for match in before},
            set(original.chunks.values_list("pk", flat=True)),
        )

        process_document(replacement)
        prepare_document_chunks(replacement.pk)
        self.index(replacement)

        after = search_knowledge_base("Shipping cost")

        self.assertEqual(
            {match["chunk_id"] for match in after},
            set(replacement.chunks.values_list("pk", flat=True)),
        )
        self.assertIn("SAR 20", after[0]["text"])

    def test_document_endpoints_require_staff(self):
        document = self.document()

        actions = [
            "document_process",
            "document_prepare_chunks",
            "document_index",
            "document_set_active",
            "document_replace",
        ]

        ordinary = get_user_model().objects.create_user(
            username="ordinary",
        )

        for user in [None, ordinary]:
            self.client.logout()

            if user:
                self.client.force_login(user)

            for action in actions:
                with self.subTest(user=user, action=action):
                    response = self.client.post(
                        reverse(
                            f"support:{action}",
                            args=[document.pk],
                        )
                    )

                    self.assertEqual(response.status_code, 302)
                    self.assertIn("/admin/login/", response.url)

        document.refresh_from_db()

        self.assertEqual(document.status, "pending")
        self.assertTrue(document.is_active)
        self.assertEqual(KnowledgeDocument.objects.count(), 1)

    @patch(
        "support.services.indexing.embed_document_texts",
        return_value=[VECTOR],
    )
    def test_process_button_completes_pipeline_and_repeat_is_safe(self, embed):
        document = self.document()
        self.client.force_login(self.staff)

        url = reverse(
            "support:document_process",
            args=[document.pk],
        )

        self.assertEqual(
            self.client.post(url).status_code,
            302,
        )

        document.refresh_from_db()
        self.assertEqual(document.status, "ready")
        self.assertEqual(document.chunks.count(), 1)

        self.assertEqual(
            self.client.post(url).status_code,
            302,
        )
        embed.assert_called_once()

    def test_pipeline_preserves_failed_extraction_without_calling_ai(self):
        document = self.document(b"   ")

        with patch(
            "support.services.indexing.embed_document_texts"
        ) as embed:
            with self.assertRaises(DocumentProcessingError):
                process_and_index_document(document.pk)

        document.refresh_from_db()
        self.assertEqual(document.status, "failed")
        self.assertTrue(document.processing_error)
        embed.assert_not_called()

    def test_pipeline_retry_keeps_chunks_after_embedding_failure(self):
        document = self.document()

        with patch(
            "support.services.indexing.embed_document_texts",
            side_effect=EmbeddingError("Unavailable"),
        ):
            with self.assertRaises(EmbeddingError):
                process_and_index_document(document.pk)

        document.refresh_from_db()
        self.assertEqual(document.status, "extracted")
        self.assertEqual(
            document.processing_error,
            "Unavailable",
        )

        previous_ids = list(
            document.chunks.values_list("pk", flat=True)
        )

        with patch(
            "support.services.indexing.embed_document_texts",
            return_value=[VECTOR],
        ):
            process_and_index_document(document.pk)

        document.refresh_from_db()
        self.assertEqual(document.status, "ready")
        self.assertEqual(document.processing_error, "")
        self.assertEqual(
            list(document.chunks.values_list("pk", flat=True)),
            previous_ids,
        )

    def test_pipeline_failure_keeps_original_replacement_active(self):
        original = self.prepared()
        self.index(original)
        replacement = self.replacement(original)

        with patch(
            "support.services.indexing.embed_document_texts",
            side_effect=EmbeddingError("Unavailable"),
        ):
            with self.assertRaises(EmbeddingError):
                process_and_index_document(replacement.pk)

        original.refresh_from_db()
        replacement.refresh_from_db()

        self.assertTrue(original.is_active)
        self.assertFalse(replacement.is_active)