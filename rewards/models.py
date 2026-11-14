from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class Reward(models.Model):
    class Category(models.TextChoices):
        SCREENS = "screens", "Écrans et divertissement"
        FOOD = "food", "Gourmandises"
        PRIVILEGES = "privileges", "Privilèges"
        OUTINGS = "outings", "Sorties"
        MATERIAL = "material", "Matériel"

    family = models.ForeignKey(
        "core.Family", on_delete=models.PROTECT, related_name="rewards"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_rewards",
    )
    category = models.CharField(max_length=12, choices=Category.choices)
    name = models.CharField(max_length=160)
    name_ar = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    description_ar = models.TextField(blank=True)
    price_coins = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "price_coins", "name", "pk"]
        indexes = [models.Index(fields=("family", "archived_at"))]

    def __str__(self):
        return self.name


class RewardRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        ACCEPTED = "accepted", "Validée"
        REJECTED = "rejected", "Refusée"

    child = models.ForeignKey(
        "accounts.ChildProfile",
        on_delete=models.PROTECT,
        related_name="reward_requests",
    )
    reward = models.ForeignKey(
        Reward, on_delete=models.PROTECT, related_name="requests"
    )
    price_coins = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="decided_reward_requests",
        null=True,
        blank=True,
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    parent_note = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-requested_at", "pk"]
        indexes = [
            models.Index(fields=("child", "status")),
            models.Index(fields=("status", "requested_at")),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("child", "reward"),
                condition=Q(status="pending"),
                name="unique_pending_reward_request_per_child",
            )
        ]

    def __str__(self):
        return f"{self.child} — {self.reward}"
