from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Account, ChildProfile
from communications.models import FamilyMessage, MessageRecipient
from core.models import Family
from missions.models import MissionOccurrence

from .models import PrintCalendarBlock, PrintJob, PrintSettings
from .services import cancel_ticket, request_ticket


class PrintCenterTests(TestCase):
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
        self.sibling = self.create_child(self.family, "adam", "Adam")

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

    def create_mission(
        self, child, *, due_date=None, status=MissionOccurrence.Status.ASSIGNED
    ):
        return MissionOccurrence.objects.create(
            child=child,
            assigned_by=self.parent,
            title="Ranger sa chambre",
            title_ar="ترتيب الغرفة",
            description="Ranger les livres.",
            due_date=due_date,
            status=status,
        )

    def test_parent_can_create_a_mission_ticket_snapshot(self):
        today = timezone.localdate()
        self.create_mission(self.child, due_date=today)
        message = FamilyMessage.objects.create(
            family=self.family,
            author=self.parent,
            content="Bon courage !",
            content_ar="بالتوفيق!",
        )
        MessageRecipient.objects.create(message=message, child=self.child)
        self.client.force_login(self.parent)

        response = self.client.post(
            reverse("printcenter:create_ticket"),
            {"child": self.child.pk, "kind": PrintJob.Kind.MISSIONS},
        )

        job = PrintJob.objects.get()
        self.assertRedirects(
            response, reverse("printcenter:preview", args=[job.pk])
        )
        self.assertEqual(job.status, PrintJob.Status.WAITING_PRINTER)
        self.assertEqual(job.snapshot["missions"][0]["title"], "Ranger sa chambre")
        self.assertEqual(job.snapshot["parent_message"], "Bon courage !")
        self.assertFalse(PrintSettings.objects.get(family=self.family).automatic_enabled)
        preview = self.client.get(reverse("printcenter:preview", args=[job.pk]))
        self.assertContains(preview, "Ranger sa chambre")
        self.assertContains(preview, "Bon courage !")

    def test_child_can_create_only_own_progress_ticket(self):
        self.client.force_login(self.child.user)

        response = self.client.post(
            reverse("printcenter:create_ticket"),
            {"kind": PrintJob.Kind.PROGRESS, "child": self.sibling.pk},
        )

        job = PrintJob.objects.get()
        self.assertRedirects(
            response, reverse("printcenter:preview", args=[job.pk])
        )
        self.assertEqual(job.child, self.child)
        self.assertEqual(job.snapshot["child_name"], "Léa")

    def test_mission_ticket_requires_active_mission_today(self):
        self.create_mission(
            self.child,
            due_date=timezone.localdate() - timedelta(days=1),
        )
        self.client.force_login(self.parent)

        response = self.client.post(
            reverse("printcenter:create_ticket"),
            {"child": self.child.pk, "kind": PrintJob.Kind.MISSIONS},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(PrintJob.objects.exists())
        self.assertContains(response, "Aucune mission active")

    def test_preview_is_limited_to_the_same_family(self):
        job = request_ticket(self.parent, self.child, PrintJob.Kind.PROGRESS)
        self.client.force_login(self.other_parent)

        response = self.client.get(reverse("printcenter:preview", args=[job.pk]))

        self.assertEqual(response.status_code, 404)

    def test_print_center_uses_arabic_when_requested(self):
        self.client.force_login(self.child.user)

        response = self.client.get(
            reverse("printcenter:center"),
            HTTP_ACCEPT_LANGUAGE="ar",
        )

        self.assertContains(response, "الطباعة")
        self.assertContains(response, "مهام اليوم")

    def test_only_waiting_jobs_can_be_cancelled(self):
        job = request_ticket(self.parent, self.child, PrintJob.Kind.PROGRESS)
        self.client.force_login(self.other_parent)

        response = self.client.post(reverse("printcenter:cancel", args=[job.pk]))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(job.status, PrintJob.Status.WAITING_PRINTER)
        self.client.force_login(self.parent)
        response = self.client.post(reverse("printcenter:cancel", args=[job.pk]))
        self.assertRedirects(response, reverse("printcenter:center"))
        job.refresh_from_db()
        self.assertEqual(job.status, PrintJob.Status.CANCELLED)
        with self.assertRaises(ValidationError):
            cancel_ticket(job, self.parent)

    def test_automatic_printing_cannot_be_enabled_without_printer(self):
        settings = PrintSettings(
            family=self.family,
            calendar_confirmed=True,
            automatic_enabled=True,
        )

        with self.assertRaises(ValidationError):
            settings.full_clean()

    def test_parent_can_save_manual_schedule_and_calendar_periods(self):
        self.client.force_login(self.parent)

        response = self.client.post(
            reverse("printcenter:save_settings"),
            {
                "schedule_time": "16:15",
                "top_margin_mm": 4,
                "bottom_margin_mm": 8,
                "density": 4,
                "feed_lines": 3,
                "weekdays": ["0", "1", "2", "3", "4"],
                "calendar_confirmed": "on",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
            response.content.decode("utf-8", errors="replace"),
        )
        settings = PrintSettings.objects.get(family=self.family)
        self.assertEqual(settings.weekdays, [0, 1, 2, 3, 4])
        self.assertTrue(settings.calendar_confirmed)
        self.assertFalse(settings.automatic_enabled)
        response = self.client.post(
            reverse("printcenter:add_calendar_block"),
            {
                "kind": PrintCalendarBlock.Kind.SCHOOL_BREAK,
                "label": "Vacances d'été",
                "starts_on": "2026-07-01",
                "ends_on": "2026-08-31",
            },
        )
        self.assertRedirects(response, reverse("printcenter:settings"))
        block = self.family.print_calendar_blocks.get()
        self.assertEqual(block.label, "Vacances d'été")

    def test_invalid_calendar_range_is_rejected(self):
        self.client.force_login(self.parent)

        response = self.client.post(
            reverse("printcenter:add_calendar_block"),
            {
                "kind": PrintCalendarBlock.Kind.PUBLIC_HOLIDAY,
                "label": "Date invalide",
                "starts_on": "2026-05-02",
                "ends_on": "2026-05-01",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.family.print_calendar_blocks.exists())
