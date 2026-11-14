from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Account, ChildProfile


@admin.register(Account)
class AccountAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Famille", {"fields": ("role", "family")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Famille", {"fields": ("role", "family")}),
    )
    list_display = ("username", "first_name", "role", "family", "is_active")
    list_filter = ("role", "is_active", "family")


@admin.register(ChildProfile)
class ChildProfileAdmin(admin.ModelAdmin):
    list_display = ("first_name", "user", "date_of_birth", "language", "archived_at")
    list_filter = ("language", "maturity", "archived_at")
    search_fields = ("first_name", "user__username")
    readonly_fields = ("created_at",)
