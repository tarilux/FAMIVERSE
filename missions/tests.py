from datetime import date

from django.test import TestCase
from django.urls import reverse
from django.core.management import call_command

from accounts.models import Account, ChildProfile
from core.models import Family
from progression.models import CoinTransaction, XpTransaction

from .models import MissionCategory, MissionOccurrence, MissionTemplate


class MissionWorkflowTests(TestCase):
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
        self.child_one = self.create_child(self.family, "lea", "Léa")
        self.child_two = self.create_child(self.family, "adam", "Adam")
        self.other_child = self.create_child(
            self.other_family, "sara", "Sara"
        )
        self.template = MissionTemplate.objects.create(
            family=self.family,
            created_by=self.parent,
            title="Ranger sa chambre",
            description="Ranger les livres et les jouets.",
            coins_reward=10,
            xp_reward=15,
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

    def create_occurrence(self, child, status=MissionOccurrence.Status.ASSIGNED):
        return MissionOccurrence.objects.create(
            template=self.template,
            child=child,
            assigned_by=self.parent,
            title=self.template.title,
            description=self.template.description,
            status=status,
        )

    def test_parent_can_assign_template_to_multiple_children(self):
        self.client.force_login(self.parent)

        response = self.client.post(
            reverse("missions:assign", args=[self.template.pk]),
            {"children": [self.child_one.pk, self.child_two.pk], "due_date": "2026-11-20"},
        )

        self.assertRedirects(response, reverse("missions:template_list"))
        occurrences = MissionOccurrence.objects.order_by("child_id")
        self.assertEqual(occurrences.count(), 2)
        self.assertEqual(
            set(occurrences.values_list("child__first_name", flat=True)),
            {"Adam", "Léa"},
        )
        self.assertEqual(occurrences.first().title, "Ranger sa chambre")

    def test_parent_can_create_a_mission_with_arabic_translation(self):
        self.client.force_login(self.parent)

        response = self.client.post(
            reverse("missions:template_create"),
            {
                "title": "Lire",
                "title_ar": "اقرأ",
                "description": "Lire pendant quinze minutes.",
                "description_ar": "اقرأ لمدة خمس عشرة دقيقة.",
                "category": "",
                "suggested_age_band": "all",
                "coins_reward": 15,
                "xp_reward": 25,
            },
        )

        self.assertRedirects(response, reverse("missions:template_list"))
        mission = MissionTemplate.objects.get(title="Lire")
        self.assertEqual(mission.title_ar, "اقرأ")
        self.assertEqual(mission.family, self.family)
        self.assertEqual(mission.created_by, self.parent)

    def test_editing_template_preserves_assigned_mission_text(self):
        occurrence = self.create_occurrence(self.child_one)
        self.client.force_login(self.parent)

        response = self.client.post(
            reverse("missions:template_edit", args=[self.template.pk]),
            {
                "title": "Nouvelle mission",
                "title_ar": "مهمة جديدة",
                "description": "Description modifiée",
                "description_ar": "وصف جديد",
                "category": "",
                "suggested_age_band": "all",
                "coins_reward": 20,
                "xp_reward": 30,
            },
        )

        self.assertRedirects(response, reverse("missions:template_list"))
        occurrence.refresh_from_db()
        self.template.refresh_from_db()
        self.assertEqual(self.template.title, "Nouvelle mission")
        self.assertEqual(occurrence.title, "Ranger sa chambre")

    def test_archiving_template_requires_confirmation_and_preserves_history(self):
        occurrence = self.create_occurrence(self.child_one)
        self.client.force_login(self.parent)
        archive_url = reverse("missions:template_archive", args=[self.template.pk])

        preview = self.client.post(archive_url)
        self.assertContains(preview, "son historique sera conservé")
        self.template.refresh_from_db()
        self.assertIsNone(self.template.archived_at)

        response = self.client.post(archive_url, {"confirm": "yes"})

        self.assertRedirects(response, reverse("missions:template_list"))
        occurrence.refresh_from_db()
        self.template.refresh_from_db()
        self.assertIsNotNone(self.template.archived_at)
        self.assertEqual(occurrence.title, "Ranger sa chambre")

    def test_mission_form_renders_in_arabic_rtl(self):
        MissionCategory.objects.create(
            family=self.family,
            name="Maison",
            name_ar="المنزل",
        )
        self.client.force_login(self.parent)

        response = self.client.get(
            reverse("missions:template_create"),
            HTTP_ACCEPT_LANGUAGE="ar",
        )

        self.assertContains(response, 'dir="rtl"')
        self.assertContains(response, "اسم المهمة")
        self.assertContains(response, "المنزل")

    def test_suggested_age_does_not_block_assignment(self):
        self.template.suggested_age_band = MissionTemplate.SuggestedAgeBand.AGES_3_5
        self.template.save()
        self.client.force_login(self.parent)

        response = self.client.post(
            reverse("missions:assign", args=[self.template.pk]),
            {"children": [self.child_one.pk]},
        )

        self.assertRedirects(response, reverse("missions:template_list"))
        self.assertTrue(
            MissionOccurrence.objects.filter(child=self.child_one).exists()
        )

    def test_initial_library_seed_is_idempotent(self):
        call_command("seed_missions", family_id=self.family.pk)
        first_count = MissionTemplate.objects.filter(family=self.family).count()
        call_command("seed_missions", family_id=self.family.pk)
        second_count = MissionTemplate.objects.filter(family=self.family).count()

        self.assertEqual(first_count, 22)
        self.assertEqual(second_count, first_count)

    def test_child_cannot_view_or_submit_sibling_mission(self):
        occurrence = self.create_occurrence(self.child_two)
        self.client.force_login(self.child_one.user)

        list_response = self.client.get(reverse("missions:my_missions"))
        submit_response = self.client.post(
            reverse("missions:submit", args=[occurrence.pk]),
            {"note": "Fait"},
        )

        self.assertNotContains(list_response, "Ranger sa chambre")
        self.assertEqual(submit_response.status_code, 404)
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.status, MissionOccurrence.Status.ASSIGNED)

    def test_approval_requires_confirmation_and_awards_once(self):
        occurrence = self.create_occurrence(self.child_one)
        self.client.force_login(self.child_one.user)
        submit_response = self.client.post(
            reverse("missions:submit", args=[occurrence.pk]),
            {"note": "J'ai tout rangé"},
        )
        self.assertRedirects(submit_response, reverse("missions:my_missions"))
        self.template.coins_reward = 20
        self.template.xp_reward = 25
        self.template.save()

        self.client.force_login(self.parent)
        decision_url = reverse("missions:decide")
        data = {"decision": "approve", "occurrence_ids": [occurrence.pk]}
        preview = self.client.post(decision_url, data)
        self.assertContains(preview, "Confirmer la décision")
        self.assertEqual(CoinTransaction.objects.count(), 0)
        self.assertEqual(XpTransaction.objects.count(), 0)

        approved = self.client.post(
            decision_url,
            {**data, "confirm": "yes", "parent_note": "Bravo"},
        )

        self.assertRedirects(approved, reverse("missions:validation_list"))
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.status, MissionOccurrence.Status.APPROVED)
        self.assertEqual(occurrence.coins_awarded, 20)
        self.assertEqual(occurrence.xp_awarded, 25)
        self.assertEqual(CoinTransaction.objects.get().amount_delta, 20)
        self.assertEqual(XpTransaction.objects.get().amount_delta, 25)

        self.template.coins_reward = 80
        self.template.xp_reward = 90
        self.template.save()
        self.assertEqual(CoinTransaction.objects.get().amount_delta, 20)
        self.assertEqual(XpTransaction.objects.get().amount_delta, 25)

        duplicate = self.client.post(
            decision_url,
            {**data, "confirm": "yes"},
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(CoinTransaction.objects.count(), 1)
        self.assertEqual(XpTransaction.objects.count(), 1)

    def test_rejection_does_not_change_coin_or_xp_balances(self):
        occurrence = self.create_occurrence(
            self.child_one, status=MissionOccurrence.Status.SUBMITTED
        )
        self.client.force_login(self.parent)
        decision_url = reverse("missions:decide")
        data = {"decision": "reject", "occurrence_ids": [occurrence.pk]}
        self.client.post(decision_url, data)

        response = self.client.post(
            decision_url, {**data, "confirm": "yes", "parent_note": "À refaire"}
        )

        self.assertRedirects(response, reverse("missions:validation_list"))
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.status, MissionOccurrence.Status.REJECTED)
        self.assertEqual(CoinTransaction.objects.count(), 0)
        self.assertEqual(XpTransaction.objects.count(), 0)

    def test_parent_cannot_access_another_familys_template(self):
        self.client.force_login(self.other_parent)

        response = self.client.get(
            reverse("missions:assign", args=[self.template.pk])
        )

        self.assertEqual(response.status_code, 404)
