from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from support.api.throttles import ChatAnonRateThrottle
from support.models import Message


@override_settings(
    CACHES={
        "default": {
            "BACKEND": (
                "django.core.cache.backends.locmem.LocMemCache"
            ),
            "LOCATION": "chat-throttle-tests",
        },
    },
)
class ChatThrottlingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

        self.url = reverse("support:chat_api")

        send_patch = patch(
            "support.views.chat.send_message",
            return_value=[],
        )
        self.send_message = send_patch.start()
        self.addCleanup(send_patch.stop)

    def send(self, client=None, *, ip="192.0.2.1"):
        if client is None:
            client = self.client

        return client.post(
            self.url,
            {"content": "How much does shipping cost?"},
            content_type="application/json",
            REMOTE_ADDR=ip,
        )

    def fill_guest_limit(self, client=None, *, ip="192.0.2.1"):
        for _ in range(10):
            response = self.send(client, ip=ip)
            self.assertEqual(response.status_code, 200)

    def test_guest_limit_blocks_before_chat_service(self):
        self.fill_guest_limit()
        self.send_message.reset_mock()

        response = self.send()

        self.assertEqual(response.status_code, 429)
        self.assertIn("detail", response.json())
        self.assertIn("Retry-After", response.headers)
        self.send_message.assert_not_called()
        self.assertEqual(Message.objects.count(), 0)

    def test_guest_limit_is_shared_by_ip(self):
        self.fill_guest_limit()

        second_browser = Client()

        response = self.send(second_browser)
        self.assertEqual(response.status_code, 429)

        response = self.send(
            second_browser,
            ip="192.0.2.2",
        )
        self.assertEqual(response.status_code, 200)

    def test_history_remains_available_after_guest_limit(self):
        self.fill_guest_limit()

        response = self.client.get(
            self.url,
            REMOTE_ADDR="192.0.2.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("messages", response.json())

        # Reading history does not reset the sending limit.
        self.assertEqual(self.send().status_code, 429)

    def test_registered_user_limit_is_shared_across_browsers(self):
        user = get_user_model().objects.create_user(
            username="throttle-customer",
        )
        self.client.force_login(user)

        for _ in range(30):
            self.assertEqual(self.send().status_code, 200)

        self.send_message.reset_mock()

        second_browser = Client()
        second_browser.force_login(user)

        response = self.send(
            second_browser,
            ip="192.0.2.2",
        )

        self.assertEqual(response.status_code, 429)
        self.send_message.assert_not_called()

        history = second_browser.get(self.url)
        self.assertEqual(history.status_code, 200)

    def test_accounts_have_separate_limits_on_same_ip(self):
        User = get_user_model()

        first_user = User.objects.create_user(
            username="throttle-first",
        )
        second_user = User.objects.create_user(
            username="throttle-second",
        )

        self.client.force_login(first_user)

        for _ in range(30):
            self.assertEqual(self.send().status_code, 200)

        self.assertEqual(self.send().status_code, 429)

        second_browser = Client()
        second_browser.force_login(second_user)

        self.assertEqual(
            self.send(second_browser).status_code,
            200,
        )

    def test_guest_can_send_after_window_expires(self):
        with patch.object(
            ChatAnonRateThrottle,
            "timer",
            return_value=100.0,
        ):
            self.fill_guest_limit()
            self.assertEqual(self.send().status_code, 429)

        with patch.object(
            ChatAnonRateThrottle,
            "timer",
            return_value=161.0,
        ):
            self.assertEqual(self.send().status_code, 200)