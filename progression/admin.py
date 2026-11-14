from django.contrib import admin

from .models import (
    BadgeAward,
    BadgeDefinition,
    CoinTransaction,
    LevelDefinition,
    XpTransaction,
)


class ImmutableTransactionAdmin(admin.ModelAdmin):
    list_display = ("child", "amount_delta", "kind", "reason", "actor", "created_at")
    list_filter = ("kind", "created_at")
    search_fields = ("child__first_name", "reason")
    readonly_fields = tuple(
        field.name for field in CoinTransaction._meta.fields
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CoinTransaction)
class CoinTransactionAdmin(ImmutableTransactionAdmin):
    pass


@admin.register(XpTransaction)
class XpTransactionAdmin(ImmutableTransactionAdmin):
    readonly_fields = tuple(field.name for field in XpTransaction._meta.fields)


@admin.register(LevelDefinition)
class LevelDefinitionAdmin(admin.ModelAdmin):
    list_display = ("level", "name", "xp_required")
    ordering = ("level",)


@admin.register(BadgeDefinition)
class BadgeDefinitionAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "rule", "threshold", "manual_only")
    list_filter = ("category", "manual_only")
    search_fields = ("name", "slug")
    readonly_fields = tuple(field.name for field in BadgeDefinition._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BadgeAward)
class BadgeAwardAdmin(admin.ModelAdmin):
    list_display = ("child", "badge", "awarded_at", "actor")
    list_filter = ("badge__category", "awarded_at")
    search_fields = ("child__first_name", "badge__name")
    readonly_fields = tuple(field.name for field in BadgeAward._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
