from django.contrib import admin

from .models import Reward, RewardRequest


@admin.register(Reward)
class RewardAdmin(admin.ModelAdmin):
    list_display = ("name", "family", "category", "price_coins", "archived_at")
    list_filter = ("category", "archived_at")
    search_fields = ("name", "family__name")


@admin.register(RewardRequest)
class RewardRequestAdmin(admin.ModelAdmin):
    list_display = ("child", "reward", "price_coins", "status", "requested_at")
    list_filter = ("status", "requested_at")
    search_fields = ("child__first_name", "reward__name")
    readonly_fields = tuple(field.name for field in RewardRequest._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
