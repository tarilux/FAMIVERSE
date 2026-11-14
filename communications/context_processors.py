from django.db.models import Q
from django.utils import timezone

from accounts.models import Account
from communications.models import MessageRecipient, Notification


def communication_counts(request):
    if not request.user.is_authenticated:
        return {"unread_notification_count": 0, "unread_message_count": 0}
    unread_messages = 0
    if request.user.role == Account.Role.CHILD:
        unread_messages = (
            MessageRecipient.objects.filter(
                child__user=request.user,
                message__family_id=request.user.family_id,
                child__archived_at__isnull=True,
                read_at__isnull=True,
            )
            .filter(
                Q(message__expires_at__isnull=True)
                | Q(message__expires_at__gt=timezone.now())
            )
            .count()
        )
    unread_notifications = Notification.objects.filter(
        recipient=request.user,
        family_id=request.user.family_id,
        read_at__isnull=True,
    ).filter(
        Q(message__isnull=True)
        | Q(message__expires_at__isnull=True)
        | Q(message__expires_at__gt=timezone.now())
    )
    return {
        "unread_notification_count": unread_notifications.count(),
        "unread_message_count": unread_messages,
    }
