from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase

from support.models import Conversation, Message
from support.services.chat import send_message


class ChatTransactionTests(TransactionTestCase):
    def test_ai_work_runs_outside_database_transaction(self):
        conversation = Conversation.objects.create(
            session_key="transaction-test",
        )

        def rewrite(question, history):
            self.assertFalse(connection.in_atomic_block)
            return question

        def retrieve(question):
            self.assertFalse(connection.in_atomic_block)
            return []

        with (
            patch(
                "support.services.chat.make_standalone_question",
                side_effect=rewrite,
            ),
            patch(
                "support.services.chat.search_with_agent",
                side_effect=retrieve,
            ),
        ):
            send_message(
                conversation.pk,
                "Shipping cost?",
            )

        self.assertEqual(Message.objects.count(), 2)