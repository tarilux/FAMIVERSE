from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.models import Account, ChildProfile
from core.i18n import UI_MESSAGES
from progression.services import get_balances

from .forms import RewardForm
from .models import Reward, RewardRequest
from .services import decide_reward_request, request_reward


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


def _localized_validation_errors(error, language):
    translations = {
        "reward_unavailable": "reward_unavailable",
        "insufficient_coins": "insufficient_coins",
        "request_closed": "request_closed",
        "approval_insufficient": "approval_insufficient",
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
        return redirect("rewards:catalog")
    if request.user.role == Account.Role.CHILD:
        return redirect("rewards:shop")
    raise PermissionDenied


@login_required
def catalog(request):
    _require_parent(request.user)
    rewards = Reward.objects.filter(
        family_id=request.user.family_id,
        archived_at__isnull=True,
    )
    return render(request, "rewards/catalog.html", {"rewards": rewards})


@login_required
@require_http_methods(["GET", "POST"])
def reward_create(request):
    _require_parent(request.user)
    form = RewardForm(request.POST or None, language=request.LANGUAGE_CODE)
    if request.method == "POST" and form.is_valid():
        form.save(family=request.user.family, created_by=request.user)
        return redirect("rewards:catalog")
    return render(request, "rewards/reward_form.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def reward_edit(request, reward_id):
    _require_parent(request.user)
    reward = get_object_or_404(
        Reward,
        pk=reward_id,
        family_id=request.user.family_id,
        archived_at__isnull=True,
    )
    form = RewardForm(
        request.POST or None,
        instance=reward,
        language=request.LANGUAGE_CODE,
    )
    if request.method == "POST" and form.is_valid():
        form.save(family=request.user.family, created_by=request.user)
        return redirect("rewards:catalog")
    return render(
        request,
        "rewards/reward_form.html",
        {"form": form, "editing": True},
    )


@login_required
@require_http_methods(["GET", "POST"])
def reward_archive(request, reward_id):
    _require_parent(request.user)
    reward = get_object_or_404(
        Reward,
        pk=reward_id,
        family_id=request.user.family_id,
        archived_at__isnull=True,
    )
    if request.method == "POST":
        if request.POST.get("confirm") != "yes":
            return HttpResponseBadRequest("La confirmation est obligatoire.")
        reward.archived_at = timezone.now()
        reward.save(update_fields=("archived_at", "updated_at"))
        return redirect("rewards:catalog")
    return render(request, "rewards/archive_confirm.html", {"reward": reward})


@login_required
def shop(request):
    child = _require_child(request.user)
    balance = get_balances(child)["coins"]
    rewards = list(
        Reward.objects.filter(
            family_id=request.user.family_id,
            archived_at__isnull=True,
        )
    )
    pending_ids = set(
        RewardRequest.objects.filter(
            child=child,
            status=RewardRequest.Status.PENDING,
        ).values_list("reward_id", flat=True)
    )
    for reward in rewards:
        reward.already_requested = reward.pk in pending_ids
        reward.affordable = balance >= reward.price_coins
    history = RewardRequest.objects.filter(child=child).select_related(
        "reward", "decided_by"
    )
    return render(
        request,
        "rewards/shop.html",
        {"child": child, "balance": balance, "rewards": rewards, "history": history},
    )


@login_required
@require_POST
def request_reward_view(request, reward_id):
    _require_child(request.user)
    try:
        _, created = request_reward(reward_id, request.user)
    except ValidationError as exc:
        messages.error(
            request,
            " ".join(
                _localized_validation_errors(exc, request.LANGUAGE_CODE)
            ),
        )
    else:
        message = (
            "تم إرسال الطلب."
            if request.LANGUAGE_CODE == "ar"
            else "La demande a été envoyée."
        )
        if not created:
            message = (
                "هذا الطلب قيد الانتظار بالفعل."
                if request.LANGUAGE_CODE == "ar"
                else "Cette demande est déjà en attente."
            )
        messages.success(request, message)
    return redirect("rewards:shop")


@login_required
def request_list(request):
    _require_parent(request.user)
    requests = (
        RewardRequest.objects.filter(
            child__user__family_id=request.user.family_id,
        )
        .select_related("child", "reward")
        .order_by("status", "-requested_at", "pk")
    )
    return render(
        request,
        "rewards/request_list.html",
        {"reward_requests": requests},
    )


@login_required
@require_http_methods(["GET", "POST"])
def decide_request(request, request_id, decision):
    _require_parent(request.user)
    if decision not in ("approve", "reject"):
        return HttpResponseBadRequest("Décision invalide.")
    reward_request = get_object_or_404(
        RewardRequest.objects.select_related("child", "reward"),
        pk=request_id,
        child__user__family_id=request.user.family_id,
        status=RewardRequest.Status.PENDING,
    )
    if request.method == "POST":
        if request.POST.get("confirm") != "yes":
            return HttpResponseBadRequest("La confirmation est obligatoire.")
        note = request.POST.get("parent_note", "").strip()
        if len(note) > 500:
            return HttpResponseBadRequest(
                "Le message ne peut pas dépasser 500 caractères."
            )
        try:
            decide_reward_request(
                reward_request.pk,
                request.user,
                approve=decision == "approve",
                parent_note=note,
            )
        except ValidationError as exc:
            return render(
                request,
                "rewards/decision_confirm.html",
                {
                    "reward_request": reward_request,
                    "decision": decision,
                    "error": _localized_validation_errors(
                        exc, request.LANGUAGE_CODE
                    ),
                },
                status=409,
            )
        return redirect("rewards:request_list")
    return render(
        request,
        "rewards/decision_confirm.html",
        {"reward_request": reward_request, "decision": decision},
    )
