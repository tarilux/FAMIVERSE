from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import Account, ChildProfile

from .models import FamilyMessage, MessageRecipient, Notification


NOTIFICATION_TITLES = {
    Notification.Kind.MISSION_ASSIGNED: (
        "Nouvelle mission",
        "مهمة جديدة",
    ),
    Notification.Kind.MISSION_SUBMITTED: (
        "Mission à valider",
        "مهمة بانتظار الموافقة",
    ),
    Notification.Kind.MISSION_APPROVED: (
        "Mission validée",
        "تمت الموافقة على المهمة",
    ),
    Notification.Kind.MISSION_REJECTED: (
        "Mission refusée",
        "تم رفض المهمة",
    ),
    Notification.Kind.HABIT_SUBMITTED: (
        "Habitude à valider",
        "عادة بانتظار الموافقة",
    ),
    Notification.Kind.HABIT_APPROVED: (
        "Habitude validée",
        "تمت الموافقة على العادة",
    ),
    Notification.Kind.HABIT_REJECTED: (
        "Habitude refusée",
        "تم رفض العادة",
    ),
    Notification.Kind.REWARD_REQUESTED: (
        "Demande de récompense",
        "طلب مكافأة",
    ),
    Notification.Kind.REWARD_ACCEPTED: (
        "Récompense acceptée",
        "تم قبول المكافأة",
    ),
    Notification.Kind.REWARD_REJECTED: (
        "Récompense refusée",
        "تم رفض المكافأة",
    ),
    Notification.Kind.NEW_MESSAGE: (
        "Nouveau message",
        "رسالة جديدة",
    ),
}


def _create_notifications(
    recipients,
    family_id,
    kind,
    source_key,
    body="",
    body_ar="",
    message=None,
):
    title, title_ar = NOTIFICATION_TITLES[kind]
    notifications = [
        Notification(
            family_id=family_id,
            recipient=recipient,
            kind=kind,
            title=title,
            title_ar=title_ar,
            body=body[:240],
            body_ar=(body_ar or body)[:240],
            source_key=source_key,
            message=message,
        )
        for recipient in recipients
        if recipient.is_active and recipient.family_id == family_id
    ]
    Notification.objects.bulk_create(notifications, ignore_conflicts=True)


def notify_child(
    child,
    kind,
    source_key,
    body="",
    body_ar="",
):
    if child.user.is_active and child.archived_at is None:
        _create_notifications(
            [child.user],
            child.user.family_id,
            kind,
            source_key,
            body,
            body_ar,
        )


def notify_family_parents(
    family_id,
    kind,
    source_key,
    body="",
    body_ar="",
):
    parents = list(
        Account.objects.filter(
            family_id=family_id,
            role=Account.Role.PARENT,
            is_active=True,
        ).order_by("pk")
    )
    _create_notifications(
        parents,
        family_id,
        kind,
        source_key,
        body,
        body_ar,
    )


@transaction.atomic
def send_family_message(
    actor,
    recipient,
    content,
    content_ar="",
    expires_at=None,
):
    if actor.role != Account.Role.PARENT or actor.family_id is None:
        raise PermissionDenied
    content = content.strip()
    content_ar = content_ar.strip()
    if not content or len(content) > 2000 or len(content_ar) > 2000:
        raise ValidationError(
            "Le message doit contenir au maximum 2 000 caractères.",
            code="invalid_message",
        )
    if expires_at is not None and expires_at <= timezone.now():
        raise ValidationError(
            "La date d'expiration doit être dans le futur.",
            code="invalid_expiration",
        )

    children = ChildProfile.objects.filter(
        user__family_id=actor.family_id,
        user__is_active=True,
        archived_at__isnull=True,
    ).select_related("user")
    if recipient != "all":
        try:
            child_id = int(recipient)
        except (TypeError, ValueError):
            raise ValidationError(
                "Le destinataire sélectionné n'est pas disponible.",
                code="invalid_recipient",
            ) from None
        children = children.filter(pk=child_id)
    children = list(children.order_by("pk"))
    if not children:
        raise ValidationError(
            "Aucun enfant actif ne correspond au destinataire.",
            code="invalid_recipient",
        )

    message = FamilyMessage.objects.create(
        family_id=actor.family_id,
        author=actor,
        content=content,
        content_ar=content_ar,
        expires_at=expires_at,
    )
    MessageRecipient.objects.bulk_create(
        [
            MessageRecipient(message=message, child=child)
            for child in children
        ]
    )
    _create_notifications(
        [child.user for child in children],
        actor.family_id,
        Notification.Kind.NEW_MESSAGE,
        f"message:{message.pk}",
        actor.get_full_name() or actor.username,
        actor.get_full_name() or actor.username,
        message=message,
    )
    return message


@transaction.atomic
def set_message_read(message_recipient_id, actor, read):
    if actor.role != Account.Role.CHILD:
        raise PermissionDenied
    recipient = (
        MessageRecipient.objects.select_for_update()
        .filter(
            pk=message_recipient_id,
            child__user=actor,
            message__family_id=actor.family_id,
            child__archived_at__isnull=True,
        )
        .first()
    )
    if recipient is None:
        raise ValidationError(
            "Ce message n'est pas accessible.",
            code="message_unavailable",
        )
    recipient.read_at = timezone.now() if read else None
    recipient.save(update_fields=("read_at",))
    Notification.objects.filter(
        recipient=actor,
        family_id=actor.family_id,
        message=recipient.message,
        kind=Notification.Kind.NEW_MESSAGE,
    ).update(read_at=recipient.read_at)
    return recipient


@transaction.atomic
def set_notification_read(notification_id, actor, read):
    notification = (
        Notification.objects.select_for_update()
        .filter(
            pk=notification_id,
            recipient=actor,
            family_id=actor.family_id,
        )
        .first()
    )
    if notification is None:
        raise ValidationError(
            "Cette notification n'est pas accessible.",
            code="notification_unavailable",
        )
    notification.read_at = timezone.now() if read else None
    notification.save(update_fields=("read_at",))
    return notification
