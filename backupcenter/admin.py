from django.contrib import admin

from .models import BackupRun, BackupSettings


@admin.register(BackupSettings)
class BackupSettingsAdmin(admin.ModelAdmin):
    list_display = ("family", "enabled", "frequency", "schedule_time", "retention_count")


@admin.register(BackupRun)
class BackupRunAdmin(admin.ModelAdmin):
    list_display = ("family", "kind", "status", "file_name", "created_at")
    list_filter = ("kind", "status", "family")
    readonly_fields = (
        "family",
        "kind",
        "status",
        "file_name",
        "source_file_name",
        "sha256",
        "size_bytes",
        "error_message",
        "actor_username",
        "created_by",
        "created_at",
        "completed_at",
    )
