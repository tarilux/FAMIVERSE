from datetime import time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class BackupSettings(models.Model):
    class Frequency(models.TextChoices):
        DAILY = "daily", "Quotidienne"
        WEEKLY = "weekly", "Hebdomadaire"

    family = models.OneToOneField(
        "core.Family", on_delete=models.PROTECT, related_name="backup_settings"
    )
    enabled = models.BooleanField(default=True)
    frequency = models.CharField(
        max_length=8, choices=Frequency.choices, default=Frequency.DAILY
    )
    weekday = models.PositiveSmallIntegerField(default=6)
    schedule_time = models.TimeField(default=time(2, 0))
    retention_count = models.PositiveSmallIntegerField(default=30)

    def clean(self):
        if self.weekday not in range(7):
            raise ValidationError({"weekday": "Sélectionnez un jour valide."})
        if not 1 <= self.retention_count <= 365:
            raise ValidationError(
                {"retention_count": "La conservation doit être comprise entre 1 et 365 versions."}
            )


class BackupRun(models.Model):
    class Kind(models.TextChoices):
        MANUAL = "manual", "Manuelle"
        SCHEDULED = "scheduled", "Automatique"
        IMPORTED = "imported", "Importée"
        PRE_RESTORE = "pre_restore", "Protection avant restauration"
        RESTORE = "restore", "Restauration"

    class Status(models.TextChoices):
        RUNNING = "running", "En cours"
        COMPLETED = "completed", "Terminée"
        FAILED = "failed", "Échec"
        PRUNED = "pruned", "Fichier expiré"

    family = models.ForeignKey(
        "core.Family", on_delete=models.PROTECT, related_name="backup_runs"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.RUNNING
    )
    file_name = models.CharField(max_length=255, blank=True)
    source_file_name = models.CharField(max_length=255, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    error_message = models.CharField(max_length=500, blank=True)
    actor_username = models.CharField(max_length=150, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="backup_runs",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=("family", "created_at"))]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.created_at:%Y-%m-%d %H:%M}"
