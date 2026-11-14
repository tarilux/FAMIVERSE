from datetime import date, timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Account, ChildProfile
from core.models import Family
from missions.models import MissionOccurrence

from .models import (
    BadgeAward,
    BadgeDefinition,
    CoinTransaction,
)
from .services import (
    adjust_child_balance,
    award_manual_badge,
    evaluate_badges,
    get_balances,
    get_level_progress,
)


class ProgressionTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name="Famille Test")
        self.other_family = Family.objects.create(name="Autre famille")
        self.parent = Account.objects.create_user(
            username="parent",
            password="4826",
            role=Account.Role.PARENT,
            family=self.family,
        )
        self.other_parent = Account.objects.create_user(
            username="other-parent",
            password="2719",
            role=Account.Role.PARENT,
            family=self.other_family,
        )
        self.child = self.create_child(self.family, "lea", "Léa")
        self.other_child = self.create_child(
            self.other_family, "sara", "Sara"
        )

    def create_child(self, family, username, first_name):
        user = Account.objects.create_user(
            username=username,
            password="7315",
            role=Account.Role.CHILD,
            family=family,
        )
        return ChildProfile.objects.create(
            user=user,
            first_name=first_name,
            date_of_birth=date(2017, 5, 10),
        )

    def test_cumulative_xp_selects_level_without_resetting_xp(self):
        below_threshold = get_level_progress(99)
        at_threshold = get_level_progress(100)
        maximum = get_level_progress(3200)

        self.assertEqual(below_threshold["current_level"].level, 1)
        self.assertEqual(below_threshold["xp_remaining"], 1)
        self.assertEqual(at_threshold["current_level"].level, 2)
        self.assertEqual(maximum["current_level"].level, 10)
        self.assertIsNone(maximum["next_level"])

    def test_parent_adjustments_use_separate_ledgers_and_preserve_details(self):
        coin_addition = adjust_child_balance(
            self.child.pk, "coins", "add", 40, "Bonus familial", self.parent
        )
        xp_addition = adjust_child_balance(
            self.child.pk, "xp", "add", 60, "Effort remarquable", self.parent
        )
        coin_withdrawal = adjust_child_balance(
            self.child.pk, "coins", "remove", 15, "Correction", self.parent
        )
        xp_withdrawal = adjust_child_balance(
            self.child.pk, "xp", "remove", 20, "Correction XP", self.parent
        )

        self.assertEqual(get_balances(self.child), {"coins": 25, "xp": 40})
        self.assertEqual(coin_addition.amount_delta, 40)
        self.assertEqual(coin_withdrawal.amount_delta, -15)
        self.assertEqual(xp_addition.amount_delta, 60)
        self.assertEqual(xp_withdrawal.amount_delta, -20)
        for entry in (
            coin_addition,
            coin_withdrawal,
            xp_addition,
            xp_withdrawal,
        ):
            self.assertEqual(entry.actor, self.parent)
            self.assertEqual(entry.kind, "adjustment")
            self.assertTrue(entry.reason)
            self.assertIsNotNone(entry.created_at)

    def test_adjustment_cannot_make_either_balance_negative_or_cross_families(self):
        adjust_child_balance(
            self.child.pk, "coins", "add", 10, "Crédit", self.parent
        )
        adjust_child_balance(
            self.child.pk, "xp", "add", 5, "Crédit", self.parent
        )
        for currency, amount in (("coins", 11), ("xp", 6)):
            with self.subTest(currency=currency):
                with self.assertRaises(ValidationError):
                    adjust_child_balance(
                        self.child.pk,
                        currency,
                        "remove",
                        amount,
                        "Retrait",
                        self.parent,
                    )
        with self.assertRaises(ValidationError):
            adjust_child_balance(
                self.other_child.pk,
                "coins",
                "add",
                1,
                "Hors famille",
                self.parent,
            )
        with self.assertRaises(PermissionDenied):
            adjust_child_balance(
                self.child.pk,
                "coins",
                "add",
                1,
                "Enfant",
                self.child.user,
            )
        self.assertEqual(get_balances(self.child), {"coins": 10, "xp": 5})

    def test_parent_adjustment_view_requires_confirmation_and_shows_history(self):
        self.client.force_login(self.parent)
        url = reverse("progression:adjust_balance", args=[self.child.pk])
        self.assertContains(self.client.get(url), "Je confirme cet ajustement")
        arabic_form = self.client.get(url, HTTP_ACCEPT_LANGUAGE="ar")
        self.assertContains(arabic_form, "نوع الرصيد")
        self.assertContains(arabic_form, 'dir="rtl"')

        missing_confirmation = self.client.post(
            url,
            {
                "currency": "coins",
                "direction": "add",
                "amount": 12,
                "reason": "Récompense familiale",
            },
        )
        self.assertEqual(missing_confirmation.status_code, 200)
        self.assertFalse(CoinTransaction.objects.exists())

        response = self.client.post(
            url,
            {
                "currency": "coins",
                "direction": "add",
                "amount": 12,
                "reason": "Récompense familiale",
                "confirm": "on",
            },
        )
        self.assertRedirects(
            response,
            reverse("progression:child_progress", args=[self.child.pk]),
        )
        progress = self.client.get(
            reverse("progression:child_progress", args=[self.child.pk])
        )
        self.assertContains(progress, "+12")
        self.assertContains(progress, "Récompense familiale")
        rejected_withdrawal = self.client.post(
            url,
            {
                "currency": "coins",
                "direction": "remove",
                "amount": 13,
                "reason": "Retrait trop élevé",
                "confirm": "on",
            },
        )
        self.assertContains(
            rejected_withdrawal,
            "Le solde est insuffisant pour retirer ce montant.",
        )
        self.assertEqual(get_balances(self.child)["coins"], 12)

        self.client.force_login(self.child.user)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertContains(
            self.client.get(reverse("progression:my_progress")),
            "Récompense familiale",
        )

    def test_automatic_badges_are_earned_once_from_approved_activity(self):
        start = timezone.now().replace(hour=12, minute=0, second=0, microsecond=0)
        for day in range(3):
            MissionOccurrence.objects.create(
                child=self.child,
                title="Ranger sa chambre",
                category_name="Rangement",
                status=MissionOccurrence.Status.APPROVED,
                submitted_at=start + timedelta(days=day),
            )
        CoinTransaction.objects.create(
            child=self.child,
            amount_delta=5,
            kind=CoinTransaction.Kind.MISSION,
            reason="Ranger sa chambre",
            actor=self.parent,
        )

        created = evaluate_badges(self.child, actor=self.parent)
        repeated = evaluate_badges(self.child, actor=self.parent)

        self.assertEqual(repeated, [])
        self.assertEqual(
            set(
                BadgeAward.objects.filter(child=self.child).values_list(
                    "badge__slug", flat=True
                )
            ),
            {"first_mission", "regularity_3_days", "first_coin"},
        )
        self.assertEqual(len(created), 3)

    def test_manual_badges_are_scoped_and_idempotent(self):
        badge = BadgeDefinition.objects.get(slug="birthday")

        first, created = award_manual_badge(
            self.child.pk, badge.pk, self.parent
        )
        repeated, created_again = award_manual_badge(
            self.child.pk, badge.pk, self.parent
        )

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.pk, repeated.pk)
        self.assertEqual(first.actor, self.parent)
        with self.assertRaises(ValidationError):
            award_manual_badge(
                self.other_child.pk, badge.pk, self.parent
            )
        with self.assertRaises(ValidationError):
            award_manual_badge(
                self.child.pk,
                BadgeDefinition.objects.get(slug="first_mission").pk,
                self.parent,
            )

    def test_parent_can_award_manual_badge_from_child_progress_page(self):
        self.client.force_login(self.parent)
        url = reverse("progression:child_progress", args=[self.child.pk])
        badge = BadgeDefinition.objects.get(slug="royal")

        response = self.client.post(
            url, {"badge": badge.pk, "confirm": "on"}
        )

        self.assertRedirects(response, url)
        self.assertTrue(
            BadgeAward.objects.filter(child=self.child, badge=badge).exists()
        )

    def test_child_progress_is_private_and_displays_level_and_badges(self):
        self.client.force_login(self.child.user)

        response = self.client.get(reverse("progression:my_progress"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Explorateur")
        self.assertContains(response, "Aucun badge obtenu")
        self.assertEqual(
            self.client.get(
                reverse("progression:child_progress", args=[self.other_child.pk])
            ).status_code,
            403,
        )
