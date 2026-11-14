from django.contrib import admin

from .models import PrintCalendarBlock, PrintJob, PrintSettings


@admin.register(PrintSettings)
class PrintSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "family",
        "paper_width_mm",
        "printer_configured",
        "automatic_enabled",
    )
    readonly_fields = ("paper_width_mm", "printer_configured", "automatic_enabled")


@admin.register(PrintCalendarBlock)
class PrintCalendarBlockAdmin(admin.ModelAdmin):
    list_display = ("family", "kind", "label", "starts_on", "ends_on")
    list_filter = ("kind", "family")


@admin.register(PrintJob)
class PrintJobAdmin(admin.ModelAdmin):
    list_display = ("child", "kind", "status", "requested_by", "created_at")
    list_filter = ("status", "kind", "family")
    readonly_fields = (
        "family",
        "child",
        "requested_by",
        "kind",
        "status",
        "snapshot",
        "created_at",
        "cancelled_at",
    )
