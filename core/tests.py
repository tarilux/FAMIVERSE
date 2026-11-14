import json

from django.test import TestCase
from django.urls import reverse


class HealthCheckTests(TestCase):
    def test_health_endpoint_returns_ok(self):
        response = self.client.get(reverse("health_check"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class ProgressiveWebAppTests(TestCase):
    def test_manifest_declares_installable_app_and_raster_icons(self):
        response = self.client.get(reverse("pwa_manifest"))
        manifest = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("application/manifest+json"))
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(
            {icon["sizes"] for icon in manifest["icons"]},
            {"192x192", "512x512"},
        )

    def test_manifest_and_offline_page_follow_arabic_language(self):
        manifest_response = self.client.get(
            reverse("pwa_manifest"),
            HTTP_ACCEPT_LANGUAGE="ar",
        )
        offline_response = self.client.get(
            reverse("offline"),
            HTTP_ACCEPT_LANGUAGE="ar",
        )
        manifest = json.loads(manifest_response.content)

        self.assertEqual(manifest["lang"], "ar")
        self.assertEqual(manifest["dir"], "rtl")
        self.assertContains(offline_response, "أنت غير متصل بالإنترنت")
        self.assertContains(offline_response, 'lang="ar" dir="rtl"')

    def test_service_worker_has_root_scope_and_is_not_cached(self):
        response = self.client.get(reverse("service_worker"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertIn("no-cache", response["Cache-Control"])
        self.assertIn("requestUrl.pathname.startsWith(\"/static/\")", response.content.decode())
