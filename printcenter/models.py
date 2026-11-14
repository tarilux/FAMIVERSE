from datetime import time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


def default_print_weekdays():
    return [0, 1, 2, 3, 4]


class PrintSettings(models.Model):
    family = models.OneToOneField(
        "core.Family", on_delete=models.PROTECT, related_name="print_settings"
    )
    paper_width_mm = models.PositiveSmallIntegerField(default=80, editable=False)
    top_margin_mm = models.PositiveSmallIntegerField(default=4)
    bottom_margin_mm = models.PositiveSmallIntegerField(default=8)
    density = models.PositiveSmallIntegerField(default=4)
    feed_lines = models.PositiveSmallIntegerField(default=3)
    automatic_cut = models.BooleanField(default=True)
    schedule_time = models.TimeField(default=time(16, 15))
    weekdays = models.JSONField(default=default_print_weekdays)
    calendar_confirmed = models.BooleanField(default=False)
    printer_configured = models.BooleanField(default=False, editable=False)
    automatic_enabled = models.BooleanField(default=False, editable=False)

    def clean(self):
        if self.automatic_enabled and not (
            self.printer_configured and self.calendar_confirmed
        ):
            raise ValidationError(
                "L'impression automatique exige une imprimante configurée "
                "et un calendrier confirmé."
            )
        if not isinstance(self.weekdays, list) or any(
            type(day) is not int or day not in range(7) for day in self.weekdays
        ):
            raise ValidationError({"weekdays": "Sélectionnez des jours valides."})
        if len(set(self.weekdays)) != len(self.weekdays):
            raise ValidationError(
                {"weekdays": "Un jour ne peut être sélectionné deux fois."}
            )
        if self.density > 15:
            raise ValidationError(
                {"density": "La densité doit être comprise entre 0 et 15."}
            )
        if self.feed_lines > 20:
            raise ValidationError(
                {"feed_lines": "L'avance ne peut pas dépasser 20 lignes."}
            )
        if self.top_margin_mm > 50 or self.bottom_margin_mm > 50:
            raise ValidationError("Les marges ne peuvent pas dépasser 50 mm.")


class PrintCalendarBlock(models.Model):
    class Kind(models.TextChoices):
        SCHOOL_BREAK = "school_break", "Vacances scolaires"
        PUBLIC_HOLIDAY = "public_holiday", "Jour férié"

    family = models.ForeignKey(
        "core.Family", on_delete=models.PROTECT, related_name="print_calendar_blocks"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    label = models.CharField(max_length=120)
    starts_on = models.DateField()
    ends_on = models.DateField()

    class Meta:
        ordering = ["starts_on", "ends_on", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_on__gte=models.F("starts_on")),
                name="print_calendar_end_after_start",
            )
        ]

    def clean(self):
        if self.ends_on and self.starts_on and self.ends_on < self.starts_on:
            raise ValidationError(
                {"ends_on": "La fin doit être le même jour ou après le début."}
            )


class PrintJob(models.Model):
    class Kind(models.TextChoices):
        MISSIONS = "missions", "Missions du jour"
        PROGRESS = "progress", "Progression"

    class Status(models.TextChoices):
        WAITING_PRINTER = (
            "waiting_printer",
            "En attente de configuration de l’imprimante",
        )
        PRINTED = "printed", "Imprimé"
        FAILED = "failed", "Échec"
        CANCELLED = "cancelled", "Annulé"

    family = models.ForeignKey(
        "core.Family", on_delete=models.PROTECT, related_name="print_jobs"
    )
    child = models.ForeignKey(
        "accounts.ChildProfile", on_delete=models.PROTECT, related_name="print_jobs"
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requested_print_jobs",
    )
    kind = models.CharField(max_length=12, choices=Kind.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.WAITING_PRINTER
    )
    snapshot = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=("family", "status", "created_at"))]

    def __str__(self):
        return (
            f"{self.child} — {self.get_kind_display()} — "
            f"{self.created_at:%Y-%m-%d %H:%M}"
        )
