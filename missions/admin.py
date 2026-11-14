from django.contrib import admin

from .models import MissionCategory, MissionOccurrence, MissionTemplate


@admin.register(MissionCategory)
class MissionCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "family", "archived_at")
    list_filter = ("family", "archived_at")
    search_fields = ("name", "name_ar")


@admin.register(MissionTemplate)
class MissionTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "family",
        "category",
        "coins_reward",
        "xp_reward",
        "archived_at",
    )
    list_filter = ("family", "category", "archived_at")
    search_fields = ("title", "title_ar", "description")
    readonly_fields = ("created_at", "updated_at")


@admin.register(MissionOccurrence)
class MissionOccurrenceAdmin(admin.ModelAdmin):
    list_display = ("title", "child", "status", "due_date", "submitted_at", "decided_at")
    list_filter = ("status", "due_date")
    search_fields = ("title", "title_ar", "child__first_name")
    readonly_fields = tuple(field.name for field in MissionOccurrence._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
