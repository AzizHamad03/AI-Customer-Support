from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from support.models import (
    Conversation,
    DocumentChunk,
    KnowledgeDocument,
    SupportTicket,
)
from support.services.chat import policy_only_escalation_text
from support.services.documents import set_document_active
from support.services.retrieval import search_knowledge_base


class CustomerImprovementTests(TestCase):
    def test_customer_ticket_list_is_isolated(self):
        session = self.client.session

        conversation = Conversation.objects.create(
            session_key=session.session_key
        )

        ticket = SupportTicket.objects.create(
            conversation=conversation,
            contact_email="customer@example.com",
            description="My delivery arrived with a damaged item.",
        )

        url = reverse("support:customer_ticket_list")

        self.assertContains(
            self.client.get(url),
            ticket.reference,
        )
        self.assertNotContains(
            Client().get(url),
            ticket.reference,
        )

    def test_escalation_keeps_policy_and_removes_contact_request(self):
        text = (
            "Report damaged deliveries within 48 hours. "
            "Please provide a contact email or phone number. "
            "A support ticket will be created after confirmation."
        )

        self.assertEqual(
            policy_only_escalation_text(text),
            "Report damaged deliveries within 48 hours.",
        )

    @patch(
        "support.services.retrieval.embed_question",
        return_value=[1.0] + [0.0] * 1535,
    )
    def test_deactivated_document_is_excluded(self, embed_question):
        staff = get_user_model().objects.create_user(
            username="document-test-staff",
            is_staff=True,
        )

        document = KnowledgeDocument.objects.create(
            title="Test Shipping Policy",
            file="documents/test.txt",
            uploaded_by=staff,
            status=KnowledgeDocument.Status.READY,
            is_active=True,
        )

        DocumentChunk.objects.create(
            document=document,
            position=0,
            page_number=1,
            text="Standard shipping costs SAR 25.",
            embedding=[1.0] + [0.0] * 1535,
        )

        self.assertEqual(
            len(search_knowledge_base("Shipping price")),
            1,
        )

        set_document_active(document.pk, False)

        self.assertEqual(
            search_knowledge_base("Shipping price"),
            [],
        )

        set_document_active(document.pk, True)

        self.assertEqual(
            len(search_knowledge_base("Shipping price")),
            1,
        )