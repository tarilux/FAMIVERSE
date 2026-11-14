from django.conf import settings
from django.db import models
from django.db.models import Q


class CoinTransaction(models.Model):
    class Kind(models.TextChoices):
        MISSION = "mission", "Mission"
        HABIT = "habit", "Habitude"
        ADJUSTMENT = "adjustment", "Ajustement parent"
        REWARD = "reward", "Récompense"
        CORRECTION = "correction", "Correction"

    child = models.ForeignKey(
        "accounts.ChildProfile",
        on_delete=models.PROTECT,
        related_name="coin_transactions",
    )
    amount_delta = models.BigIntegerField()
    kind = models.CharField(max_length=12, choices=Kind.choices)
    reason = models.CharField(max_length=240)
    mission_occurrence = models.OneToOneField(
        "missions.MissionOccurrence",
        on_delete=models.PROTECT,
        related_name="coin_transaction",
        null=True,
        blank=True,
    )
    habit_occurrence = models.OneToOneField(
        "habits.HabitOccurrence",
        on_delete=models.PROTECT,
        related_name="coin_transaction",
        null=True,
        blank=True,
    )
    reward_request = models.OneToOneField(
        "rewards.RewardRequest",
        on_delete=models.PROTECT,
        related_name="coin_transaction",
        null=True,
        blank=True,
    )
    corrects = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="corrections",
        null=True,
        blank=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="coin_transactions",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=("child", "created_at"))]
        constraints = [
            models.CheckConstraint(
                condition=~Q(amount_delta=0), name="coin_transaction_nonzero"
            )
        ]


class XpTransaction(models.Model):
    class Kind(models.TextChoices):
        MISSION = "mission", "Mission"
        HABIT = "habit", "Habitude"
        ADJUSTMENT = "adjustment", "Ajustement parent"
        CORRECTION = "correction", "Correction"

    child = models.ForeignKey(
        "accounts.ChildProfile",
        on_delete=models.PROTECT,
        related_name="xp_transactions",
    )
    amount_delta = models.BigIntegerField()
    kind = models.CharField(max_length=12, choices=Kind.choices)
    reason = models.CharField(max_length=240)
    mission_occurrence = models.OneToOneField(
        "missions.MissionOccurrence",
        on_delete=models.PROTECT,
        related_name="xp_transaction",
        null=True,
        blank=True,
    )
    habit_occurrence = models.OneToOneField(
        "habits.HabitOccurrence",
        on_delete=models.PROTECT,
        related_name="xp_transaction",
        null=True,
        blank=True,
    )
    corrects = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="corrections",
        null=True,
        blank=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="xp_transactions",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=("child", "created_at"))]
        constraints = [
            models.CheckConstraint(
                condition=~Q(amount_delta=0), name="xp_transaction_nonzero"
            )
        ]


class LevelDefinition(models.Model):
    level = models.PositiveSmallIntegerField(unique=True)
    name = models.CharField(max_length=80)
    name_ar = models.CharField(max_length=80)
    xp_required = models.PositiveIntegerField(unique=True)

    class Meta:
        ordering = ["xp_required", "level"]

    def __str__(self):
        return f"{self.level}. {self.name}"


class BadgeDefinition(models.Model):
    class Category(models.TextChoices):
        REGULARITY = "regularity", "Régularité"
        MISSIONS = "missions", "Missions"
        AUTONOMY = "autonomy", "Autonomie"
        FAMILY = "family", "Famille et entraide"
        SAVINGS = "savings", "Épargne et récompenses"
        SPECIAL = "special", "Spéciaux"

    class Rule(models.TextChoices):
        MANUAL = "manual", "Attribution manuelle"
        MISSION_COUNT = "mission_count", "Missions validées"
        STREAK_DAYS = "streak_days", "Jours consécutifs"
        CATEGORY_COUNT = "category_count", "Missions d'une catégorie"
        ON_TIME_MISSIONS = "on_time_missions", "Missions rendues à temps"
        FIRST_COIN = "first_coin", "Première pièce gagnée"
        COINS_SAVED = "coins_saved", "Solde de pièces"
        COINS_EARNED = "coins_earned", "Pièces gagnées cumulées"

    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=100)
    name_ar = models.CharField(max_length=100)
    description = models.CharField(max_length=240)
    description_ar = models.CharField(max_length=240)
    category = models.CharField(max_length=12, choices=Category.choices)
    rule = models.CharField(max_length=24, choices=Rule.choices)
    threshold = models.PositiveIntegerField(default=1)
    criteria_value = models.CharField(max_length=32, blank=True)
    manual_only = models.BooleanField(default=False)
    icon = models.CharField(max_length=24, default="star")

    class Meta:
        ordering = ["category", "threshold", "slug"]

    def __str__(self):
        return self.name


class BadgeAward(models.Model):
    child = models.ForeignKey(
        "accounts.ChildProfile",
        on_delete=models.PROTECT,
        related_name="badge_awards",
    )
    badge = models.ForeignKey(
        BadgeDefinition, on_delete=models.PROTECT, related_name="awards"
    )
    awarded_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="awarded_badges",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-awarded_at", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=("child", "badge"), name="unique_badge_per_child"
            )
        ]

    def __str__(self):
        return f"{self.child} — {self.badge}"
