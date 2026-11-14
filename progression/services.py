import unicodedata
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from accounts.models import Account, ChildProfile

from .models import (
    BadgeAward,
    BadgeDefinition,
    CoinTransaction,
    LevelDefinition,
    XpTransaction,
)

MAX_TRANSACTION_AMOUNT = 9223372036854775807


def get_level_progress(xp):
    levels = list(LevelDefinition.objects.order_by("xp_required"))
    if not levels:
        raise RuntimeError("Les niveaux de progression ne sont pas initialisés.")
    current = levels[0]
    next_level = None
    for index, level in enumerate(levels):
        if xp >= level.xp_required:
            current = level
            next_level = levels[index + 1] if index + 1 < len(levels) else None
    if next_level is None:
        return {
            "current_level": current,
            "next_level": None,
            "progress_percent": 100,
            "xp_remaining": 0,
        }
    span = next_level.xp_required - current.xp_required
    progress = max(0, xp - current.xp_required)
    return {
        "current_level": current,
        "next_level": next_level,
        "progress_percent": min(100, round(progress * 100 / span)),
        "xp_remaining": max(0, next_level.xp_required - xp),
    }


def get_progress_summary(child, balances=None):
    balances = balances or get_balances(child)
    return {
        "balances": balances,
        "level": get_level_progress(balances["xp"]),
        "badge_awards": BadgeAward.objects.filter(child=child)
        .select_related("badge")
        .order_by("-awarded_at", "pk"),
        "coin_history": CoinTransaction.objects.filter(child=child)
        .select_related("actor")
        .order_by("-created_at", "-pk"),
        "xp_history": XpTransaction.objects.filter(child=child)
        .select_related("actor")
        .order_by("-created_at", "-pk"),
    }


def _normalized(text):
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(character)
    )


def _longest_streak(submission_dates):
    longest = current = 0
    previous = None
    for submitted_date in sorted(set(submission_dates)):
        is_consecutive = (
            previous is not None
            and submitted_date == previous + timedelta(days=1)
        )
        current = current + 1 if is_consecutive else 1
        longest = max(longest, current)
        previous = submitted_date
    return longest


@transaction.atomic
def evaluate_badges(child, actor=None):
    from habits.models import HabitOccurrence
    from missions.models import MissionOccurrence

    missions = MissionOccurrence.objects.filter(
        child=child, status=MissionOccurrence.Status.APPROVED
    )
    mission_count = missions.count()
    submission_dates = [
        timezone.localtime(value).date()
        for value in missions.exclude(submitted_at__isnull=True).values_list(
            "submitted_at", flat=True
        )
    ]
    submission_dates.extend(
        timezone.localtime(value).date()
        for value in HabitOccurrence.objects.filter(
            child=child,
            status=HabitOccurrence.Status.APPROVED,
        )
        .exclude(submitted_at__isnull=True)
        .values_list("submitted_at", flat=True)
    )
    streak_days = _longest_streak(submission_dates)
    category_names = [
        _normalized(name)
        for name in missions.values_list("category_name", flat=True)
    ]
    category_counts = {
        "rangement": sum("rangement" in name for name in category_names),
        "education": sum(
            any(term in name for term in ("education", "scolaire", "pedagogique"))
            for name in category_names
        ),
    }
    on_time_count = sum(
        timezone.localtime(submitted_at).date() <= due_date
        for due_date, submitted_at in missions.filter(
            due_date__isnull=False, submitted_at__isnull=False
        ).values_list("due_date", "submitted_at")
    )
    earned_coins = (
        CoinTransaction.objects.filter(
            child=child,
            kind__in=(CoinTransaction.Kind.MISSION, CoinTransaction.Kind.HABIT),
            amount_delta__gt=0,
        ).aggregate(total=Sum("amount_delta"))["total"]
        or 0
    )
    saved_coins = get_balances(child)["coins"]
    metrics = {
        BadgeDefinition.Rule.MISSION_COUNT: mission_count,
        BadgeDefinition.Rule.STREAK_DAYS: streak_days,
        BadgeDefinition.Rule.CATEGORY_COUNT: category_counts,
        BadgeDefinition.Rule.ON_TIME_MISSIONS: on_time_count,
        BadgeDefinition.Rule.FIRST_COIN: int(earned_coins > 0),
        BadgeDefinition.Rule.COINS_SAVED: saved_coins,
        BadgeDefinition.Rule.COINS_EARNED: earned_coins,
    }
    created = []
    for badge in BadgeDefinition.objects.filter(manual_only=False):
        if badge.rule == BadgeDefinition.Rule.CATEGORY_COUNT:
            value = category_counts.get(badge.criteria_value, 0)
        else:
            value = metrics.get(badge.rule, 0)
        if value < badge.threshold:
            continue
        award, was_created = BadgeAward.objects.get_or_create(
            child=child, badge=badge, defaults={"actor": actor}
        )
        if was_created:
            created.append(award)
    return created


@transaction.atomic
def award_manual_badge(child_id, badge_id, actor):
    if actor.role != Account.Role.PARENT or actor.family_id is None:
        raise PermissionDenied
    child = ChildProfile.objects.filter(
        pk=child_id,
        user__family_id=actor.family_id,
        user__is_active=True,
        archived_at__isnull=True,
    ).first()
    badge = BadgeDefinition.objects.filter(
        pk=badge_id, manual_only=True
    ).first()
    if child is None or badge is None:
        raise ValidationError("Le profil ou le badge n'est pas disponible.")
    return BadgeAward.objects.get_or_create(
        child=child, badge=badge, defaults={"actor": actor}
    )


def get_balances(child):
    coins = CoinTransaction.objects.filter(child=child).aggregate(
        total=Sum("amount_delta")
    )["total"]
    xp = XpTransaction.objects.filter(child=child).aggregate(
        total=Sum("amount_delta")
    )["total"]
    return {"coins": coins or 0, "xp": xp or 0}


@transaction.atomic
def adjust_child_balance(child_id, currency, direction, amount, reason, actor):
    if actor.role != Account.Role.PARENT or actor.family_id is None:
        raise PermissionDenied
    if currency not in ("coins", "xp") or direction not in ("add", "remove"):
        raise ValidationError(
            "L'ajustement demandé n'est pas valide.",
            code="invalid_adjustment",
        )
    if (
        not isinstance(amount, int)
        or isinstance(amount, bool)
        or amount <= 0
        or amount > MAX_TRANSACTION_AMOUNT
    ):
        raise ValidationError(
            "Le montant doit être un entier positif.",
            code="invalid_adjustment",
        )
    reason = reason.strip() if isinstance(reason, str) else ""
    if not reason or len(reason) > 240:
        raise ValidationError(
            "Indiquez un motif de 240 caractères au maximum.",
            code="invalid_reason",
        )

    child = (
        ChildProfile.objects.select_for_update()
        .filter(
            pk=child_id,
            user__family_id=actor.family_id,
            user__is_active=True,
            archived_at__isnull=True,
        )
        .first()
    )
    if child is None:
        raise ValidationError("Le profil n'est pas disponible.", code="child_unavailable")

    transaction_model, kind = (
        (CoinTransaction, CoinTransaction.Kind.ADJUSTMENT)
        if currency == "coins"
        else (XpTransaction, XpTransaction.Kind.ADJUSTMENT)
    )
    balance = (
        transaction_model.objects.filter(child=child).aggregate(
            total=Sum("amount_delta")
        )["total"]
        or 0
    )
    if direction == "remove" and amount > balance:
        raise ValidationError(
            "Le solde est insuffisant pour retirer ce montant.",
            code="insufficient_balance",
        )
    if direction == "add" and balance > MAX_TRANSACTION_AMOUNT - amount:
        raise ValidationError(
            "Le solde dépasserait la limite de stockage autorisée.",
            code="balance_limit",
        )
    amount_delta = amount if direction == "add" else -amount
    return transaction_model.objects.create(
        child=child,
        amount_delta=amount_delta,
        kind=kind,
        reason=reason,
        actor=actor,
    )


def get_family_balances(child_ids):
    child_ids = list(child_ids)
    if not child_ids:
        return {}
    balances = {
        child_id: {"coins": 0, "xp": 0}
        for child_id in child_ids
    }
    coin_totals = (
        CoinTransaction.objects.filter(child_id__in=child_ids)
        .values("child_id")
        .annotate(total=Sum("amount_delta"))
    )
    xp_totals = (
        XpTransaction.objects.filter(child_id__in=child_ids)
        .values("child_id")
        .annotate(total=Sum("amount_delta"))
    )
    for row in coin_totals:
        balances[row["child_id"]]["coins"] = row["total"] or 0
    for row in xp_totals:
        balances[row["child_id"]]["xp"] = row["total"] or 0
    return balances
