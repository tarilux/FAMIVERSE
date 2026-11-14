from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class HabitTemplate(models.Model):
    class Frequency(models.TextChoices):
        DAILY = "daily", "Quotidienne"
        WEEKLY = "weekly", "Hebdomadaire"

    class TimeOfDay(models.TextChoices):
        ANYTIME = "anytime", "À tout moment"
        MORNING = "morning", "Matin"
        AFTERNOON = "afternoon", "Après-midi"
        EVENING = "evening", "Soir"

    family = models.ForeignKey(
        "core.Family", on_delete=models.PROTECT, related_name="habit_templates"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_habit_templates",
    )
    children = models.ManyToManyField(
        "accounts.ChildProfile", related_name="habit_templates"
    )
    title = models.CharField(max_length=160)
    title_ar = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    description_ar = models.TextField(blank=True)
    frequency = models.CharField(
        max_length=8, choices=Frequency.choices, default=Frequency.DAILY
    )
    weekdays = models.JSONField(default=list, blank=True)
    time_of_day = models.CharField(
        max_length=10, choices=TimeOfDay.choices, default=TimeOfDay.ANYTIME
    )
    scheduled_time = models.TimeField(null=True, blank=True)
    coins_reward = models.PositiveIntegerField(default=0)
    xp_reward = models.PositiveIntegerField(default=0)
    starts_on = models.DateField(default=timezone.localdate)
    suspended_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title", "id"]
        indexes = [models.Index(fields=("family", "archived_at", "suspended_at"))]

    def __str__(self):
        return self.title

    def clean(self):
        if (
            self.created_by_id
            and self.family_id
            and self.created_by.family_id != self.family_id
        ):
            raise ValidationError(
                {"created_by": "Le créateur doit appartenir à la famille."}
            )
        if self.frequency == self.Frequency.WEEKLY:
            if (
                not isinstance(self.weekdays, list)
                or not self.weekdays
                or any(
                    type(day) is not int or day not in range(7)
                    for day in self.weekdays
                )
                or len(set(self.weekdays)) != len(self.weekdays)
            ):
                raise ValidationError(
                    {"weekdays": "Sélectionnez au moins un jour valide."}
                )
        elif self.weekdays:
            raise ValidationError(
                {
                    "weekdays": (
                        "Les jours ne s'appliquent qu'à une récurrence hebdomadaire."
                    )
                }
            )


class HabitOccurrence(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Prévue"
        SUBMITTED = "submitted", "À valider"
        APPROVED = "approved", "Validée"
        REJECTED = "rejected", "Refusée"
        CANCELLED = "cancelled", "Annulée"

    template = models.ForeignKey(
        HabitTemplate, on_delete=models.PROTECT, related_name="occurrences"
    )
    child = models.ForeignKey(
        "accounts.ChildProfile",
        on_delete=models.PROTECT,
        related_name="habit_occurrences",
    )
    scheduled_date = models.DateField()
    title = models.CharField(max_length=160)
    title_ar = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    description_ar = models.TextField(blank=True)
    time_of_day = models.CharField(
        max_length=10,
        choices=HabitTemplate.TimeOfDay.choices,
        default=HabitTemplate.TimeOfDay.ANYTIME,
    )
    scheduled_time = models.TimeField(null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PLANNED
    )
    child_note = models.CharField(max_length=500, blank=True)
    parent_note = models.CharField(max_length=500, blank=True)
    coins_awarded = models.PositiveIntegerField(null=True, blank=True)
    xp_awarded = models.PositiveIntegerField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="decided_habits",
        null=True,
        blank=True,
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["scheduled_date", "scheduled_time", "created_at", "id"]
        indexes = [
            models.Index(fields=("child", "scheduled_date")),
            models.Index(fields=("status", "scheduled_date")),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("template", "child", "scheduled_date"),
                name="unique_habit_occurrence_per_child_date",
            ),
            models.CheckConstraint(
                condition=Q(coins_awarded__isnull=True) | Q(coins_awarded__gte=0),
                name="habit_coins_awarded_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(xp_awarded__isnull=True) | Q(xp_awarded__gte=0),
                name="habit_xp_awarded_nonnegative",
            ),
        ]

    def __str__(self):
        return f"{self.title} — {self.scheduled_date}"
