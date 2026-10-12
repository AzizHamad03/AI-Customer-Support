from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from support.models import Message


class ChatTests(TestCase):
    @patch(
        "support.services.chat.make_standalone_question",
        side_effect=lambda question, history: question,
    )
    @patch(
        "support.services.chat.search_knowledge_base",
        return_value=[],
    )
    def test_history_is_saved_and_isolated(self, _search, _rewrite):
        first = Client()
        second = Client()
        url = reverse("support:chat_api")

        first.post(
            url,
            {"content": "My private question"},
            content_type="application/json",
        )

        first_history = first.get(url).json()["messages"]
        second_history = second.get(url).json()["messages"]

        self.assertEqual(len(first_history), 2)
        self.assertEqual(
            first_history[0]["content"],
            "My private question",
        )
        self.assertEqual(second_history, [])
        self.assertEqual(Message.objects.count(), 2)

    def test_anonymous_post_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("support:chat"))

        response = client.post(
            reverse("support:chat_api"),
            {"content": "Hello"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_blank_message_is_rejected(self):
        response = self.client.post(
            reverse("support:chat_api"),
            {"content": "   "},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Message.objects.count(), 0)