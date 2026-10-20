from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class FoundationTests(TestCase):
    def test_home(self):
        response = self.client.get(reverse("support:home"))
        self.assertContains(response, "AI Customer Support Assistant")

    def test_database_health(self):
        response = self.client.get(reverse("support:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "connected"})

    @patch("support.views.health.database_is_available", return_value=False)
    def test_database_failure_returns_503(self, _):
        self.assertEqual(self.client.get(reverse("support:health")).status_code, 503)

    def test_staff_access(self):
        url = reverse("support:staff_dashboard")
        self.assertEqual(self.client.get(url).status_code, 302)
        user = get_user_model().objects.create_user(username="customer", password="test-only-password")
        self.client.force_login(user)
        self.assertEqual(self.client.get(url).status_code, 302)
        user.is_staff = True
        user.save()
        self.assertContains(self.client.get(url), "Staff workspace")
