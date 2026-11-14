from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.models import Account, ChildProfile
from core.i18n import UI_MESSAGES

from .forms import FamilyMessageForm
from .models import FamilyMessage, MessageRecipient, Notification
from .services import (
    send_family_message,
    set_message_read,
    set_notification_read,
)


def _require_parent(user):
    if user.role != Account.Role.PARENT or user.family_id is None:
        raise PermissionDenied


def _require_child(user):
    if user.role != Account.Role.CHILD or user.family_id is None:
        raise PermissionDenied
    return get_object_or_404(
        ChildProfile.objects.select_related("user"),
        user=user,
        archived_at__isnull=True,
    )


def _message_error(error, language):
    translations = {
        "invalid_message": "message_invalid",
        "invalid_expiration": "message_expiration_invalid",
        "invalid_recipient": "message_recipient_invalid",
        "message_unavailable": "message_unavailable",
        "notification_unavailable": "notification_unavailable",
    }
    ui = UI_MESSAGES.get(language, UI_MESSAGES["fr"])
    return [
        ui[translations[item.code]]
        if item.code in translations
        else item.message
        for item in error.error_list
    ]


@login_required
def index(request):
    if request.user.role == Account.Role.PARENT:
        return redirect("communications:sent_messages")
    if request.user.role == Account.Role.CHILD:
        return redirect("communications:message_inbox")
    raise PermissionDenied


@login_required
@require_http_methods(["GET", "POST"])
def sent_messages(request):
    _require_parent(request.user)
    form = FamilyMessageForm(
        request.POST if request.method == "POST" else None,
        family=request.user.family,
        language=request.LANGUAGE_CODE,
    )
    if request.method == "POST" and form.is_valid():
        try:
            send_family_message(
                request.user,
                form.cleaned_data["recipient"],
                form.cleaned_data["content"],
                form.cleaned_data["content_ar"],
                form.cleaned_data["expires_at"],
            )
        except ValidationError as exc:
            for error in _message_error(exc, request.LANGUAGE_CODE):
                form.add_error(None, error)
        else:
            ui = UI_MESSAGES.get(request.LANGUAGE_CODE, UI_MESSAGES["fr"])
            messages.success(request, ui["message_sent"])
            return redirect("communications:sent_messages")

    sent = (
        FamilyMessage.objects.filter(family_id=request.user.family_id)
        .select_related("author")
        .prefetch_related("recipients__child")
    )
    return render(
        request,
        "communications/sent_messages.html",
        {"form": form, "sent_messages": sent},
    )


@login_required
def message_inbox(request):
    child = _require_child(request.user)
    deliveries = (
        MessageRecipient.objects.filter(
            child=child,
            message__family_id=request.user.family_id,
        )
        .select_related("message", "message__author")
        .order_by("-message__created_at", "-pk")
    )
    return render(
        request,
        "communications/inbox.html",
        {"deliveries": deliveries, "now": timezone.now()},
    )


@login_required
@require_POST
def message_read(request, recipient_id, action):
    child = _require_child(request.user)
    if action not in ("read", "unread"):
        return HttpResponseBadRequest("Action invalide.")
    get_object_or_404(
        MessageRecipient.objects.filter(
            child=child,
            message__family_id=request.user.family_id,
        ),
        pk=recipient_id,
    )
    try:
        set_message_read(recipient_id, request.user, read=action == "read")
    except ValidationError as exc:
        raise Http404 from exc
    return redirect("communications:message_inbox")


@login_required
def notification_list(request):
    if request.user.family_id is None:
        raise PermissionDenied
    notifications = Notification.objects.filter(
        recipient=request.user,
        family_id=request.user.family_id,
    )
    return render(
        request,
        "communications/notifications.html",
        {"notifications": notifications, "now": timezone.now()},
    )


@login_required
@require_POST
def notification_read(request, notification_id, action):
    if request.user.family_id is None:
        raise PermissionDenied
    if action not in ("read", "unread"):
        return HttpResponseBadRequest("Action invalide.")
    get_object_or_404(
        Notification.objects.filter(
            recipient=request.user,
            family_id=request.user.family_id,
        ),
        pk=notification_id,
    )
    try:
        set_notification_read(
            notification_id,
            request.user,
            read=action == "read",
        )
    except ValidationError as exc:
        raise Http404 from exc
    return redirect("communications:notification_list")
