from django.contrib import admin

from .models import FamilyMessage, MessageRecipient, Notification


@admin.register(FamilyMessage)
class FamilyMessageAdmin(admin.ModelAdmin):
    list_display = ("author", "family", "created_at", "expires_at")
    list_filter = ("family", "created_at")
    search_fields = ("content", "content_ar", "author__username")
    readonly_fields = tuple(field.name for field in FamilyMessage._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MessageRecipient)
class MessageRecipientAdmin(admin.ModelAdmin):
    list_display = ("child", "message", "read_at")
    list_filter = ("read_at",)
    readonly_fields = tuple(field.name for field in MessageRecipient._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "kind", "created_at", "read_at")
    list_filter = ("kind", "read_at")
    search_fields = ("title", "body", "recipient__username")
    readonly_fields = tuple(field.name for field in Notification._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
