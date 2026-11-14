from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Account, ChildProfile
from core.models import Family
from progression.models import CoinTransaction, XpTransaction

from .models import HabitOccurrence, HabitTemplate
from .services import decide_habit, generate_habit_occurrences, submit_habit


class HabitPlanningTests(TestCase):
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

    def create_habit(self, children=None, **values):
        defaults = {
            "family": self.family,
            "created_by": self.parent,
            "title": "Lire dix minutes",
            "title_ar": "اقرأ عشر دقائق",
            "description": "Lire un livre.",
            "frequency": HabitTemplate.Frequency.DAILY,
            "starts_on": timezone.localdate(),
            "coins_reward": 5,
            "xp_reward": 8,
        }
        defaults.update(values)
        habit = HabitTemplate.objects.create(**defaults)
        habit.children.set(children or [self.child_one])
        return habit

    def test_weekly_schedule_generates_selected_days_once_per_child(self):
        monday = date(2026, 11, 9)
        habit = self.create_habit(
            frequency=HabitTemplate.Frequency.WEEKLY,
            weekdays=[0, 2, 4],
            starts_on=monday,
            children=[self.child_one, self.child_two],
        )

        created = generate_habit_occurrences(
            self.family.pk, monday, monday + timedelta(days=6)
        )
        repeated = generate_habit_occurrences(
            self.family.pk, monday, monday + timedelta(days=6)
        )

        self.assertEqual(len(created), 6)
        self.assertEqual(repeated, [])
        self.assertEqual(
            set(
                HabitOccurrence.objects.filter(template=habit).values_list(
                    "scheduled_date", flat=True
                )
            ),
            {
                monday,
                monday + timedelta(days=2),
                monday + timedelta(days=4),
            },
        )
        self.assertEqual(
            HabitOccurrence.objects.filter(template=habit).count(), 6
        )

    def test_parent_can_create_weekly_habit_with_selected_children(self):
        self.client.force_login(self.parent)
        url = reverse("habits:template_create")
        data = {
            "title": "Ranger ses affaires",
            "title_ar": "ترتيب الأغراض",
            "description": "",
            "description_ar": "",
            "frequency": "weekly",
            "time_of_day": "evening",
            "scheduled_time": "19:30",
            "coins_reward": 2,
            "xp_reward": 3,
            "children": [self.child_two.pk],
        }

        invalid = self.client.post(url, data)
        self.assertEqual(invalid.status_code, 200)
        self.assertFalse(HabitTemplate.objects.exists())

        response = self.client.post(
            url, {**data, "weekdays": ["1", "4"]}
        )

        self.assertRedirects(response, reverse("habits:template_list"))
        habit = HabitTemplate.objects.get(title="Ranger ses affaires")
        self.assertEqual(habit.weekdays, [1, 4])
        self.assertEqual(list(habit.children.all()), [self.child_two])
        self.assertEqual(habit.scheduled_time.strftime("%H:%M"), "19:30")

    def test_child_planning_and_submission_are_limited_to_own_profile(self):
        habit = self.create_habit(children=[self.child_two])
        scheduled_date = timezone.localdate()
        generate_habit_occurrences(
            self.family.pk, scheduled_date, scheduled_date
        )
        occurrence = HabitOccurrence.objects.get(
            template=habit, child=self.child_two
        )

        self.client.force_login(self.child_one.user)
        response = self.client.get(
            reverse("habits:my_planning"),
            {"view": "day", "date": scheduled_date.isoformat()},
        )
        self.assertNotContains(response, habit.title)

        with self.assertRaises(ValidationError):
            submit_habit(occurrence.pk, self.child_one.user)
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.status, HabitOccurrence.Status.PLANNED)

        self.client.force_login(self.child_two.user)
        response = self.client.get(
            reverse("habits:my_planning"),
            {"view": "day", "date": scheduled_date.isoformat()},
            HTTP_ACCEPT_LANGUAGE="ar",
        )
        self.assertContains(response, habit.title_ar)
        self.assertContains(response, 'dir="rtl"')

    def test_parent_approval_awards_coins_and_xp_once(self):
        today = timezone.localdate()
        habit = self.create_habit(starts_on=today)
        occurrence = generate_habit_occurrences(
            self.family.pk, today, today
        )[0]
        submit_habit(occurrence.pk, self.child_one.user, "Terminé")
        self.client.force_login(self.parent)
        decision_url = reverse(
            "habits:decide", args=[occurrence.pk, "approve"]
        )

        preview = self.client.get(decision_url)
        self.assertContains(preview, "Confirmez-vous")
        unconfirmed = self.client.post(
            decision_url, {"confirm": "", "parent_note": ""}
        )
        self.assertEqual(unconfirmed.status_code, 400)

        response = self.client.post(
            decision_url,
            {"confirm": "yes", "parent_note": "Bravo"},
        )

        self.assertRedirects(response, reverse("habits:validation_list"))
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.status, HabitOccurrence.Status.APPROVED)
        self.assertEqual(occurrence.coins_awarded, 5)
        self.assertEqual(occurrence.xp_awarded, 8)
        self.assertEqual(
            CoinTransaction.objects.filter(
                habit_occurrence=occurrence, amount_delta=5
            ).count(),
            1,
        )
        self.assertEqual(
            XpTransaction.objects.filter(
                habit_occurrence=occurrence, amount_delta=8
            ).count(),
            1,
        )
        self.assertEqual(
            self.client.post(decision_url, {"confirm": "yes"}).status_code,
            404,
        )

    def test_rejection_does_not_change_balances_and_cross_family_is_denied(self):
        today = timezone.localdate()
        self.create_habit(starts_on=today)
        occurrence = generate_habit_occurrences(
            self.family.pk, today, today
        )[0]
        submit_habit(occurrence.pk, self.child_one.user)

        with self.assertRaises(ValidationError):
            decide_habit(occurrence.pk, self.other_parent, approve=True)

        decide_habit(
            occurrence.pk,
            self.parent,
            approve=False,
            parent_note="Essayons encore.",
        )

        occurrence.refresh_from_db()
        self.assertEqual(occurrence.status, HabitOccurrence.Status.REJECTED)
        self.assertIsNone(occurrence.coins_awarded)
        self.assertFalse(CoinTransaction.objects.filter(child=self.child_one).exists())
        self.assertFalse(XpTransaction.objects.filter(child=self.child_one).exists())

    def test_suspension_cancels_prebuilt_future_occurrences(self):
        today = timezone.localdate()
        habit = self.create_habit(starts_on=today)
        tomorrow = today + timedelta(days=1)
        generate_habit_occurrences(
            self.family.pk, tomorrow, tomorrow + timedelta(days=2)
        )
        self.client.force_login(self.parent)

        response = self.client.post(
            reverse("habits:template_toggle_suspension", args=[habit.pk])
        )

        self.assertRedirects(response, reverse("habits:template_list"))
        habit.refresh_from_db()
        self.assertIsNotNone(habit.suspended_at)
        self.assertEqual(habit.starts_on, tomorrow)
        self.assertEqual(
            HabitOccurrence.objects.filter(
                template=habit,
                scheduled_date__gte=tomorrow,
                status=HabitOccurrence.Status.CANCELLED,
            ).count(),
            3,
        )
        self.assertEqual(
            generate_habit_occurrences(
                self.family.pk, tomorrow, tomorrow
            ),
            [],
        )
        plan = self.client.get(
            reverse("habits:planning"),
            {"view": "day", "date": tomorrow.isoformat()},
        )
        self.assertContains(plan, habit.title)
        self.assertContains(plan, "Annulée")

    def test_parent_cannot_edit_another_familys_habit(self):
        foreign_habit = HabitTemplate.objects.create(
            family=self.other_family,
            created_by=self.other_parent,
            title="Habitude privée",
            starts_on=timezone.localdate(),
        )
        foreign_habit.children.add(self.other_child)
        self.client.force_login(self.parent)

        response = self.client.get(
            reverse("habits:template_edit", args=[foreign_habit.pk])
        )

        self.assertEqual(response.status_code, 404)
