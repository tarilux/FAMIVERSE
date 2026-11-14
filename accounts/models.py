from pathlib import Path
import uuid

from django.contrib.auth.models import AbstractUser
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone


def avatar_upload_path(instance, filename):
    suffix = Path(filename).suffix.lower()
    return f"avatars/{instance.user.family_id}/{uuid.uuid4().hex}{suffix}"


class Account(AbstractUser):
    class Role(models.TextChoices):
        PARENT = "parent", "Parent"
        CHILD = "child", "Enfant"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.PARENT)
    family = models.ForeignKey(
        "core.Family",
        on_delete=models.PROTECT,
        related_name="accounts",
        null=True,
        blank=True,
    )

    @property
    def is_parent(self):
        return self.role == self.Role.PARENT

    @property
    def is_child(self):
        return self.role == self.Role.CHILD


class ChildProfile(models.Model):
    class Language(models.TextChoices):
        FRENCH = "fr", "Français"
        ARABIC = "ar", "العربية"

    class Maturity(models.TextChoices):
        STANDARD = "standard", "Standard"
        SIMPLIFIED = "simplified", "Simplifié"
        AUTONOMY = "autonomy", "Autonomie"

    user = models.OneToOneField(
        Account, on_delete=models.PROTECT, related_name="child_profile"
    )
    first_name = models.CharField(max_length=80)
    date_of_birth = models.DateField()
    avatar = models.ImageField(
        upload_to=avatar_upload_path,
        blank=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
    )
    language = models.CharField(
        max_length=2, choices=Language.choices, default=Language.FRENCH
    )
    maturity = models.CharField(
        max_length=12, choices=Maturity.choices, default=Maturity.STANDARD
    )
    preferences = models.JSONField(default=dict, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["first_name", "id"]

    def __str__(self):
        return self.first_name

    @property
    def age(self):
        today = timezone.localdate()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )

    @property
    def age_group(self):
        age = self.age
        if age <= 5:
            return "explorer"
        if age <= 8:
            return "adventurer"
        if age <= 11:
            return "confirmed"
        if age <= 14:
            return "strategist"
        return "young_adult"


class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, unique=True)
    failures = models.PositiveSmallIntegerField(default=0)
    window_started_at = models.DateTimeField(default=timezone.now)
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["locked_until"])]
