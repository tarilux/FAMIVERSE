from datetime import date

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse

from accounts.models import Account, ChildProfile
from core.models import Family
from progression.models import CoinTransaction

from .models import Reward, RewardRequest
from .services import decide_reward_request, request_reward


class RewardShopTests(TestCase):
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
        self.reward = Reward.objects.create(
            family=self.family,
            created_by=self.parent,
            category=Reward.Category.OUTINGS,
            name="Choisir le film",
            name_ar="اختيار الفيلم",
            price_coins=30,
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

    def add_coins(self, child, amount):
        return CoinTransaction.objects.create(
            child=child,
            amount_delta=amount,
            kind=CoinTransaction.Kind.ADJUSTMENT,
            reason="Essai",
            actor=self.parent,
        )

    def test_request_requires_balance_and_preserves_requested_price(self):
        with self.assertRaises(ValidationError):
            request_reward(self.reward.pk, self.child.user)
        self.assertFalse(RewardRequest.objects.exists())

        self.add_coins(self.child, 50)
        reward_request, created = request_reward(
            self.reward.pk, self.child.user
        )
        self.assertTrue(created)
        self.assertEqual(reward_request.price_coins, 30)

        self.reward.price_coins = 45
        self.reward.save(update_fields=("price_coins",))
        repeated, created_again = request_reward(
            self.reward.pk, self.child.user
        )
        self.assertFalse(created_again)
        self.assertEqual(repeated.pk, reward_request.pk)
        self.assertEqual(repeated.price_coins, 30)
        self.assertEqual(RewardRequest.objects.count(), 1)

    def test_acceptance_debits_once_and_rejection_does_not_debit(self):
        self.add_coins(self.child, 50)
        accepted_request, _ = request_reward(
            self.reward.pk, self.child.user
        )
        decided = decide_reward_request(
            accepted_request.pk, self.parent, approve=True
        )
        self.assertEqual(decided.status, RewardRequest.Status.ACCEPTED)
        self.assertEqual(
            CoinTransaction.objects.filter(child=self.child).aggregate(
                total=Sum("amount_delta")
            )["total"],
            20,
        )
        debit = CoinTransaction.objects.get(reward_request=accepted_request)
        self.assertEqual(debit.amount_delta, -30)
        self.assertEqual(debit.actor, self.parent)
        with self.assertRaises(ValidationError):
            decide_reward_request(
                accepted_request.pk, self.parent, approve=True
            )
        self.assertEqual(
            CoinTransaction.objects.filter(
                reward_request=accepted_request
            ).count(),
            1,
        )

        self.add_coins(self.child, 30)
        rejected_request, _ = request_reward(
            self.reward.pk, self.child.user
        )
        decide_reward_request(
            rejected_request.pk, self.parent, approve=False
        )
        self.assertEqual(
            rejected_request.__class__.objects.get(
                pk=rejected_request.pk
            ).status,
            RewardRequest.Status.REJECTED,
        )
        self.assertFalse(
            CoinTransaction.objects.filter(
                reward_request=rejected_request
            ).exists()
        )

    def test_approval_with_changed_balance_keeps_request_pending(self):
        self.add_coins(self.child, 30)
        reward_request, _ = request_reward(
            self.reward.pk, self.child.user
        )
        CoinTransaction.objects.create(
            child=self.child,
            amount_delta=-30,
            kind=CoinTransaction.Kind.CORRECTION,
            reason="Correction d'essai",
            actor=self.parent,
        )

        with self.assertRaises(ValidationError):
            decide_reward_request(
                reward_request.pk, self.parent, approve=True
            )

        reward_request.refresh_from_db()
        self.assertEqual(reward_request.status, RewardRequest.Status.PENDING)
        self.assertFalse(
            CoinTransaction.objects.filter(
                reward_request=reward_request
            ).exists()
        )

    def test_parent_can_review_and_accept_request_from_views(self):
        self.add_coins(self.child, 50)
        reward_request, _ = request_reward(
            self.reward.pk, self.child.user
        )
        self.client.force_login(self.parent)

        list_response = self.client.get(reverse("rewards:request_list"))
        self.assertContains(list_response, "Choisir le film")
        decision_url = reverse(
            "rewards:decide_request",
            args=[reward_request.pk, "approve"],
        )
        self.assertContains(self.client.get(decision_url), "Confirmez-vous")
        response = self.client.post(
            decision_url,
            {"confirm": "yes", "parent_note": "Bon choix"},
        )

        self.assertRedirects(response, reverse("rewards:request_list"))
        reward_request.refresh_from_db()
        self.assertEqual(reward_request.status, RewardRequest.Status.ACCEPTED)
        self.assertEqual(reward_request.parent_note, "Bon choix")
        self.assertEqual(
            CoinTransaction.objects.get(
                reward_request=reward_request
            ).amount_delta,
            -30,
        )

    def test_views_are_scoped_by_family_and_role(self):
        self.add_coins(self.child, 40)
        self.client.force_login(self.child.user)
        french_response = self.client.get(reverse("rewards:shop"))
        self.assertContains(french_response, "Choisir le film")
        self.assertContains(french_response, "Demander cette récompense")
        response = self.client.get(
            reverse("rewards:shop"), HTTP_ACCEPT_LANGUAGE="ar"
        )
        self.assertContains(response, "اختيار الفيلم")
        self.assertContains(response, 'dir="rtl"')

        self.client.force_login(self.other_child.user)
        self.assertEqual(
            self.client.post(
                reverse("rewards:request", args=[self.reward.pk])
            ).status_code,
            302,
        )
        self.assertFalse(RewardRequest.objects.exists())

        self.client.force_login(self.other_parent)
        self.assertEqual(
            self.client.get(reverse("rewards:catalog")).status_code,
            200,
        )
        self.assertNotContains(
            self.client.get(reverse("rewards:catalog")),
            "Choisir le film",
        )

    def test_archiving_removes_reward_from_shop_but_keeps_history(self):
        self.add_coins(self.child, 30)
        reward_request, _ = request_reward(
            self.reward.pk, self.child.user
        )
        self.client.force_login(self.parent)
        archive_url = reverse("rewards:reward_archive", args=[self.reward.pk])

        self.client.post(archive_url, {"confirm": "yes"})
        self.reward.refresh_from_db()
        self.assertIsNotNone(self.reward.archived_at)
        self.client.force_login(self.child.user)
        response = self.client.get(reverse("rewards:shop"))
        self.assertNotContains(response, "Choisir le film</h2>")
        self.assertContains(response, "Choisir le film</h3>")
        self.assertTrue(
            RewardRequest.objects.filter(pk=reward_request.pk).exists()
        )

    def test_seed_command_is_idempotent_for_selected_family(self):
        initial_count = Reward.objects.filter(family=self.family).count()
        call_command("seed_rewards", family_id=self.family.pk)
        call_command("seed_rewards", family_id=self.family.pk)

        self.assertEqual(
            Reward.objects.filter(family=self.family).count(),
            initial_count + 20,
        )
        self.assertEqual(
            Reward.objects.filter(family=self.other_family).count(), 0
        )
