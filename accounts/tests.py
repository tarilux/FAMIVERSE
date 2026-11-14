from datetime import date

from django.test import TestCase
from django.urls import reverse

from core.models import Family

from .models import Account, ChildProfile, LoginAttempt


class AccountAccessTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name="Famille Test")
        self.parent = Account.objects.create_user(
            username="parent",
            password="4826",
            role=Account.Role.PARENT,
            family=self.family,
        )

    def create_child(self, username, first_name):
        account = Account.objects.create_user(
            username=username,
            password="7315",
            role=Account.Role.CHILD,
            family=self.family,
        )
        return ChildProfile.objects.create(
            user=account,
            first_name=first_name,
            date_of_birth=date(2017, 5, 10),
        )

    def test_parent_can_create_child_with_hashed_code(self):
        self.client.force_login(self.parent)

        response = self.client.post(
            reverse("accounts:child_create"),
            {
                "username": "lea",
                "first_name": "Léa",
                "date_of_birth": "2017-05-10",
                "pin": "5724",
                "language": "fr",
                "maturity": "standard",
            },
        )

        self.assertRedirects(response, reverse("accounts:home"))
        child = Account.objects.get(username="lea")
        self.assertEqual(child.family, self.family)
        self.assertNotEqual(child.password, "5724")
        self.assertTrue(child.check_password("5724"))
        self.assertEqual(child.child_profile.first_name, "Léa")

    def test_child_cannot_create_another_child(self):
        child_profile = self.create_child("lea", "Léa")
        self.client.force_login(child_profile.user)

        response = self.client.get(reverse("accounts:child_create"))

        self.assertEqual(response.status_code, 403)

    def test_child_dashboard_only_contains_own_profile(self):
        child_profile = self.create_child("lea", "Léa")
        self.create_child("adam", "Adam")
        self.client.force_login(child_profile.user)

        response = self.client.get(reverse("accounts:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Léa")
        self.assertNotContains(response, "Adam")

    def test_repeated_bad_codes_trigger_temporary_lock(self):
        url = reverse("accounts:login")
        for _ in range(5):
            response = self.client.post(
                url, {"username": "unknown", "pin": "0000"}
            )
            self.assertEqual(response.status_code, 200)

        attempt = LoginAttempt.objects.get()
        self.assertEqual(attempt.failures, 5)
        self.assertIsNotNone(attempt.locked_until)
        response = self.client.post(url, {"username": "unknown", "pin": "0000"})
        self.assertContains(response, "Trop de tentatives")

    def test_parent_can_sign_in_with_code(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "parent", "pin": "4826"},
        )

        self.assertRedirects(response, reverse("accounts:home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.parent.pk)

    def test_login_page_uses_arabic_and_rtl_when_requested(self):
        response = self.client.get(
            reverse("accounts:login"),
            HTTP_ACCEPT_LANGUAGE="ar",
        )

        self.assertContains(response, 'dir="rtl"')
        self.assertContains(response, "تسجيل الدخول")

    def test_future_birth_date_and_short_pin_are_rejected(self):
        self.client.force_login(self.parent)

        response = self.client.post(
            reverse("accounts:child_create"),
            {
                "username": "lea",
                "first_name": "Léa",
                "date_of_birth": "2999-01-01",
                "pin": "123",
                "language": "fr",
                "maturity": "standard",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Account.objects.filter(username="lea").exists())
