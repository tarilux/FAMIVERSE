from django.conf import settings
from django.db import models
from django.db.models import Q


class FamilyMessage(models.Model):
    family = models.ForeignKey(
        "core.Family",
        on_delete=models.PROTECT,
        related_name="messages",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="family_messages",
    )
    content = models.TextField(max_length=2000)
    content_ar = models.TextField(max_length=2000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"{self.author} — {self.created_at:%Y-%m-%d}"


class MessageRecipient(models.Model):
    message = models.ForeignKey(
        FamilyMessage,
        on_delete=models.PROTECT,
        related_name="recipients",
    )
    child = models.ForeignKey(
        "accounts.ChildProfile",
        on_delete=models.PROTECT,
        related_name="family_messages",
    )
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-message__created_at", "-pk"]
        indexes = [models.Index(fields=("child", "read_at"))]
        constraints = [
            models.UniqueConstraint(
                fields=("message", "child"),
                name="unique_message_recipient",
            )
        ]


class Notification(models.Model):
    class Kind(models.TextChoices):
        MISSION_ASSIGNED = "mission_assigned", "Mission attribuée"
        MISSION_SUBMITTED = "mission_submitted", "Mission soumise"
        MISSION_APPROVED = "mission_approved", "Mission validée"
        MISSION_REJECTED = "mission_rejected", "Mission refusée"
        HABIT_SUBMITTED = "habit_submitted", "Habitude soumise"
        HABIT_APPROVED = "habit_approved", "Habitude validée"
        HABIT_REJECTED = "habit_rejected", "Habitude refusée"
        REWARD_REQUESTED = "reward_requested", "Récompense demandée"
        REWARD_ACCEPTED = "reward_accepted", "Récompense acceptée"
        REWARD_REJECTED = "reward_rejected", "Récompense refusée"
        NEW_MESSAGE = "new_message", "Nouveau message"

    family = models.ForeignKey(
        "core.Family",
        on_delete=models.PROTECT,
        related_name="notifications",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="notifications",
    )
    kind = models.CharField(max_length=24, choices=Kind.choices)
    title = models.CharField(max_length=140)
    title_ar = models.CharField(max_length=140)
    body = models.CharField(max_length=240, blank=True)
    body_ar = models.CharField(max_length=240, blank=True)
    source_key = models.CharField(max_length=180)
    message = models.ForeignKey(
        FamilyMessage,
        on_delete=models.PROTECT,
        related_name="notifications",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=("recipient", "read_at", "created_at"))]
        constraints = [
            models.UniqueConstraint(
                fields=("recipient", "source_key"),
                name="unique_notification_per_recipient_source",
            ),
            models.CheckConstraint(
                condition=(
                    Q(message__isnull=True)
                    | Q(kind="new_message")
                ),
                name="message_notification_kind",
            ),
        ]

    def __str__(self):
        return self.title
