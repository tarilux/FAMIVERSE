from django.conf import settings
from django.db import models
from django.db.models import Q


class MissionCategory(models.Model):
    family = models.ForeignKey(
        "core.Family", on_delete=models.PROTECT, related_name="mission_categories"
    )
    name = models.CharField(max_length=80)
    name_ar = models.CharField(max_length=80, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=("family", "name"), name="unique_mission_category_per_family"
            )
        ]

    def __str__(self):
        return self.name


class MissionTemplate(models.Model):
    class Recurrence(models.TextChoices):
        NONE = "none", "Ponctuelle"
        DAILY = "daily", "Quotidienne"
        WEEKLY = "weekly", "Hebdomadaire"

    class SuggestedAgeBand(models.TextChoices):
        AGES_3_5 = "3-5", "3–5 ans"
        AGES_6_9 = "6-9", "6–9 ans"
        AGES_10_PLUS = "10+", "10 ans et plus"
        ALL_AGES = "all", "Tous âges"

    family = models.ForeignKey(
        "core.Family", on_delete=models.PROTECT, related_name="mission_templates"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_mission_templates",
    )
    category = models.ForeignKey(
        MissionCategory,
        on_delete=models.PROTECT,
        related_name="mission_templates",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=160)
    title_ar = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    description_ar = models.TextField(blank=True)
    coins_reward = models.PositiveIntegerField(default=0)
    xp_reward = models.PositiveIntegerField(default=0)
    suggested_age_band = models.CharField(
        max_length=4,
        choices=SuggestedAgeBand.choices,
        default=SuggestedAgeBand.ALL_AGES,
    )
    recurrence = models.CharField(
        max_length=8, choices=Recurrence.choices, default=Recurrence.NONE
    )
    weekdays = models.JSONField(default=list, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title", "id"]
        indexes = [models.Index(fields=("family", "archived_at"))]

    def __str__(self):
        return self.title

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.category_id and self.family_id and self.category.family_id != self.family_id:
            raise ValidationError({"category": "La catégorie doit appartenir à la famille."})
        if self.created_by_id and self.family_id and self.created_by.family_id != self.family_id:
            raise ValidationError({"created_by": "Le créateur doit appartenir à la famille."})
        if self.recurrence == self.Recurrence.WEEKLY:
            if not self.weekdays or any(day not in range(7) for day in self.weekdays):
                raise ValidationError({"weekdays": "Sélectionnez au moins un jour valide."})
        elif self.weekdays:
            raise ValidationError({"weekdays": "Les jours ne s'appliquent qu'à une récurrence hebdomadaire."})


class MissionOccurrence(models.Model):
    class Status(models.TextChoices):
        ASSIGNED = "assigned", "Attribuée"
        SUBMITTED = "submitted", "Soumise"
        APPROVED = "approved", "Validée"
        REJECTED = "rejected", "Refusée"
        CANCELLED = "cancelled", "Annulée"

    template = models.ForeignKey(
        MissionTemplate,
        on_delete=models.SET_NULL,
        related_name="occurrences",
        null=True,
        blank=True,
    )
    child = models.ForeignKey(
        "accounts.ChildProfile",
        on_delete=models.PROTECT,
        related_name="mission_occurrences",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="assigned_missions",
        null=True,
    )
    title = models.CharField(max_length=160)
    title_ar = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    description_ar = models.TextField(blank=True)
    category_name = models.CharField(max_length=80, blank=True)
    category_name_ar = models.CharField(max_length=80, blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ASSIGNED
    )
    coins_awarded = models.PositiveIntegerField(null=True, blank=True)
    xp_awarded = models.PositiveIntegerField(null=True, blank=True)
    child_note = models.CharField(max_length=500, blank=True)
    parent_note = models.CharField(max_length=500, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="decided_missions",
        null=True,
        blank=True,
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "created_at", "id"]
        indexes = [
            models.Index(fields=("child", "status")),
            models.Index(fields=("status", "created_at")),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(coins_awarded__isnull=True) | Q(coins_awarded__gte=0),
                name="mission_coins_awarded_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(xp_awarded__isnull=True) | Q(xp_awarded__gte=0),
                name="mission_xp_awarded_nonnegative",
            ),
        ]

    def __str__(self):
        return self.title
