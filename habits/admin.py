from django.contrib import admin

from .models import HabitOccurrence, HabitTemplate


@admin.register(HabitTemplate)
class HabitTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "family",
        "frequency",
        "time_of_day",
        "suspended_at",
        "archived_at",
    )
    list_filter = ("frequency", "time_of_day", "suspended_at", "archived_at")
    search_fields = ("title", "family__name")


@admin.register(HabitOccurrence)
class HabitOccurrenceAdmin(admin.ModelAdmin):
    list_display = ("title", "child", "scheduled_date", "status")
    list_filter = ("status", "scheduled_date")
    search_fields = ("title", "child__first_name")
