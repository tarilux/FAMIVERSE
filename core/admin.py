from django.contrib import admin

from .models import Family


@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display = ("name", "timezone", "created_at")
    search_fields = ("name",)
    readonly_fields = ("created_at",)
