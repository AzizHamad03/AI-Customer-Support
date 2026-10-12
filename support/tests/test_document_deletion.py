from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from support.models import (
    Conversation,
    DocumentChunk,
    KnowledgeDocument,
    Message,
    MessageCitation,
)
from support.services.documents import create_document
from support.services.retrieval import search_knowledge_base


class DocumentDeletionTests(TestCase):
    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)

        setting = override_settings(MEDIA_ROOT=media.name)
        setting.enable()
        self.addCleanup(setting.disable)

        self.staff = get_user_model().objects.create_user(
            username="delete-staff",
            is_staff=True,
        )
        self.document = create_document(
            title="Shipping policy",
            category="shipping",
            file=SimpleUploadedFile(
                "shipping.txt",
                b"Shipping costs SAR 25.",
            ),
            uploaded_by=self.staff,
        )
        self.url = reverse(
            "support:document_delete",
            args=[self.document.pk],
        )
        self.client.force_login(self.staff)

    def test_get_and_unconfirmed_post_preserve_document(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.post(self.url).status_code, 302)

        self.assertTrue(
            KnowledgeDocument.objects.filter(
                pk=self.document.pk
            ).exists()
        )
        self.assertTrue(
            self.document.file.storage.exists(self.document.file.name)
        )

    def test_confirmed_delete_removes_search_data_and_preserves_citation(self):
        self.document.status = KnowledgeDocument.Status.READY
        self.document.save(update_fields=["status"])

        chunk = DocumentChunk.objects.create(
            document=self.document,
            position=0,
            page_number=1,
            text="Shipping costs SAR 25.",
            embedding=[1.0] + [0.0] * 1535,
        )
        conversation = Conversation.objects.create(
            session_key="delete-test-session"
        )
        message = Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content="Shipping costs SAR 25.",
        )
        citation = MessageCitation.objects.create(
            message=message,
            chunk=chunk,
            source_key="S1",
            document_title=self.document.title,
            document_version=1,
            page_number=1,
            source_text=chunk.text,
            is_txt=True,
        )

        document_id = self.document.pk
        chunk_id = chunk.pk
        storage = self.document.file.storage
        file_name = self.document.file.name

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.url,
                {"confirm": "yes"},
            )

        self.assertRedirects(
            response,
            reverse("support:document_list"),
        )
        self.assertFalse(
            KnowledgeDocument.objects.filter(pk=document_id).exists()
        )
        self.assertFalse(
            DocumentChunk.objects.filter(pk=chunk_id).exists()
        )
        self.assertFalse(storage.exists(file_name))

        citation.refresh_from_db()
        self.assertIsNone(citation.chunk_id)
        self.assertEqual(citation.source_text, "Shipping costs SAR 25.")
        self.assertEqual(citation.document_title, "Shipping policy")
        self.assertTrue(Message.objects.filter(pk=message.pk).exists())

        with patch(
            "support.services.retrieval.embed_question"
        ) as embed:
            self.assertEqual(search_knowledge_base("Shipping cost?"), [])
            embed.assert_not_called()

    def test_document_with_replacement_cannot_be_deleted(self):
        replacement = create_document(
            title="Shipping policy",
            category="shipping",
            file=SimpleUploadedFile(
                "replacement.txt",
                b"Shipping costs SAR 20.",
            ),
            uploaded_by=self.staff,
        )
        replacement.replaces = self.document
        replacement.version = 2
        replacement.save(update_fields=["replaces", "version"])

        self.client.post(self.url, {"confirm": "yes"})

        self.assertTrue(
            KnowledgeDocument.objects.filter(
                pk=self.document.pk
            ).exists()
        )
        self.assertTrue(
            self.document.file.storage.exists(self.document.file.name)
        )

    def test_deleting_replacement_does_not_reactivate_original(self):
        self.document.is_active = False
        self.document.save(update_fields=["is_active"])

        replacement = create_document(
            title="Shipping policy",
            category="shipping",
            file=SimpleUploadedFile(
                "replacement.txt",
                b"Shipping costs SAR 20.",
            ),
            uploaded_by=self.staff,
        )
        replacement.replaces = self.document
        replacement.version = 2
        replacement.save(update_fields=["replaces", "version"])

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse(
                    "support:document_delete",
                    args=[replacement.pk],
                ),
                {"confirm": "yes"},
            )

        self.document.refresh_from_db()
        self.assertFalse(self.document.is_active)
        self.assertFalse(
            KnowledgeDocument.objects.filter(
                pk=replacement.pk
            ).exists()
        )

    def test_only_staff_can_access_deletion(self):
        ordinary = get_user_model().objects.create_user(
            username="delete-customer"
        )

        for user in [None, ordinary]:
            self.client.logout()
            if user is not None:
                self.client.force_login(user)

            for method in ["get", "post"]:
                with self.subTest(user=user, method=method):
                    response = getattr(self.client, method)(
                        self.url,
                        {"confirm": "yes"},
                    )
                    self.assertEqual(response.status_code, 302)
                    self.assertIn("/admin/login/", response.url)

        self.assertTrue(
            KnowledgeDocument.objects.filter(
                pk=self.document.pk
            ).exists()
        )

    def test_delete_post_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)

        response = client.post(self.url, {"confirm": "yes"})

        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            KnowledgeDocument.objects.filter(
                pk=self.document.pk
            ).exists()
        )