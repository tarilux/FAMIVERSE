from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.models import Account, ChildProfile
from core.i18n import UI_MESSAGES

from .forms import BalanceAdjustmentForm, ManualBadgeForm
from .services import (
    adjust_child_balance,
    award_manual_badge,
    get_balances,
    get_progress_summary,
)


def _adjustment_error(error, language):
    translations = {
        "invalid_adjustment": "adjustment_invalid",
        "invalid_reason": "adjustment_reason_invalid",
        "child_unavailable": "adjustment_child_unavailable",
        "insufficient_balance": "adjustment_insufficient_balance",
        "balance_limit": "adjustment_balance_limit",
    }
    ui = UI_MESSAGES.get(language, UI_MESSAGES["fr"])
    return [
        ui[translations[item.code]]
        if item.code in translations
        else item.message
        for item in error.error_list
    ]


@login_required
def my_progress(request):
    if request.user.role != Account.Role.CHILD:
        raise PermissionDenied
    child = get_object_or_404(
        ChildProfile.objects.select_related("user"),
        user=request.user,
        archived_at__isnull=True,
    )
    return render(
        request,
        "progression/child_progress.html",
        {
            "child": child,
            "summary": get_progress_summary(child),
            "can_award": False,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def child_progress(request, child_id):
    if request.user.role != Account.Role.PARENT or request.user.family_id is None:
        raise PermissionDenied
    child = get_object_or_404(
        ChildProfile.objects.select_related("user"),
        pk=child_id,
        user__family_id=request.user.family_id,
        user__is_active=True,
        archived_at__isnull=True,
    )
    form = ManualBadgeForm(
        request.POST or None,
        language=request.LANGUAGE_CODE,
    )
    if request.method == "POST" and form.is_valid():
        _, created = award_manual_badge(
            child.pk,
            form.cleaned_data["badge"].pk,
            request.user,
        )
        if created:
            message = (
                "تم منح الشارة."
                if request.LANGUAGE_CODE == "ar"
                else "Le badge a été attribué."
            )
            messages.success(request, message)
        else:
            message = (
                "حصل هذا الطفل على هذه الشارة من قبل."
                if request.LANGUAGE_CODE == "ar"
                else "Cet enfant possède déjà ce badge."
            )
            messages.info(request, message)
        return redirect("progression:child_progress", child_id=child.pk)
    return render(
        request,
        "progression/child_progress.html",
        {
            "child": child,
            "summary": get_progress_summary(child),
            "can_award": True,
            "form": form,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def adjust_balance(request, child_id):
    if request.user.role != Account.Role.PARENT or request.user.family_id is None:
        raise PermissionDenied
    child = get_object_or_404(
        ChildProfile.objects.select_related("user"),
        pk=child_id,
        user__family_id=request.user.family_id,
        user__is_active=True,
        archived_at__isnull=True,
    )
    form = BalanceAdjustmentForm(
        request.POST if request.method == "POST" else None,
        language=request.LANGUAGE_CODE,
    )
    if request.method == "POST" and form.is_valid():
        try:
            adjust_child_balance(
                child.pk,
                form.cleaned_data["currency"],
                form.cleaned_data["direction"],
                form.cleaned_data["amount"],
                form.cleaned_data["reason"],
                request.user,
            )
        except ValidationError as exc:
            for error in _adjustment_error(exc, request.LANGUAGE_CODE):
                form.add_error(None, error)
        else:
            ui = UI_MESSAGES.get(request.LANGUAGE_CODE, UI_MESSAGES["fr"])
            messages.success(request, ui["adjustment_success"])
            return redirect(
                "progression:child_progress",
                child_id=child.pk,
            )
    return render(
        request,
        "progression/balance_adjustment_form.html",
        {"child": child, "form": form, "balances": get_balances(child)},
    )
