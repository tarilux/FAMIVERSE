from datetime import datetime, time, timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, Sum
from django.utils import timezone

from accounts.models import Account
from communications.models import FamilyMessage
from missions.models import MissionOccurrence
from progression.models import CoinTransaction, LevelDefinition, XpTransaction
from progression.services import get_balances
from rewards.models import Reward

from .models import PrintJob, PrintSettings


def _day_bounds(day):
    start = timezone.make_aware(datetime.combine(day, time.min))
    end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))
    return start, end


def build_snapshot(child, kind):
    today = timezone.localdate()
    if kind == PrintJob.Kind.MISSIONS:
        missions = list(
            MissionOccurrence.objects.filter(
                child=child,
                due_date=today,
                status__in=(
                    MissionOccurrence.Status.ASSIGNED,
                    MissionOccurrence.Status.SUBMITTED,
                ),
            ).order_by("created_at", "pk")
        )
        if not missions:
            raise ValidationError(
                "Aucune mission active n’est prévue pour cet enfant aujourd’hui.",
                code="no_missions_today",
            )
        message = (
            FamilyMessage.objects.filter(
                family=child.user.family,
                recipients__child=child,
            )
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
            .order_by("-created_at", "-pk")
            .first()
        )
        return {
            "kind": kind,
            "date": today.isoformat(),
            "child_name": child.first_name,
            "missions": [
                {
                    "title": occurrence.title,
                    "title_ar": occurrence.title_ar,
                    "description": occurrence.description,
                    "description_ar": occurrence.description_ar,
                    "status": occurrence.status,
                }
                for occurrence in missions
            ],
            "parent_message": message.content if message else "",
            "parent_message_ar": message.content_ar if message else "",
        }
    if kind != PrintJob.Kind.PROGRESS:
        raise ValidationError("Type de ticket invalide.", code="invalid_ticket")

    balances = get_balances(child)
    start, end = _day_bounds(today)
    coins_today = (
        CoinTransaction.objects.filter(
            child=child, created_at__gte=start, created_at__lt=end
        ).aggregate(total=Sum("amount_delta"))["total"]
        or 0
    )
    xp_today = (
        XpTransaction.objects.filter(
            child=child, created_at__gte=start, created_at__lt=end
        ).aggregate(total=Sum("amount_delta"))["total"]
        or 0
    )
    level = LevelDefinition.objects.filter(
        xp_required__lte=balances["xp"]
    ).order_by("-xp_required").first()
    rewards = Reward.objects.filter(
        family=child.user.family, archived_at__isnull=True
    ).order_by("price_coins", "name", "pk")[:3]
    return {
        "kind": kind,
        "date": today.isoformat(),
        "child_name": child.first_name,
        "coins": balances["coins"],
        "xp": balances["xp"],
        "coins_today": coins_today,
        "xp_today": xp_today,
        "level": level.name if level else "",
        "level_ar": level.name_ar if level else "",
        "rewards": [
            {
                "name": reward.name,
                "name_ar": reward.name_ar,
                "price_coins": reward.price_coins,
            }
            for reward in rewards
        ],
    }


def request_ticket(user, child, kind):
    if child.archived_at is not None or child.user.family_id != user.family_id:
        raise PermissionDenied
    if user.role == Account.Role.CHILD:
        if child.user_id != user.pk:
            raise PermissionDenied
    elif user.role != Account.Role.PARENT:
        raise PermissionDenied
    if kind not in PrintJob.Kind.values:
        raise ValidationError("Type de ticket invalide.", code="invalid_ticket")

    snapshot = build_snapshot(child, kind)
    PrintSettings.objects.get_or_create(family=child.user.family)
    return PrintJob.objects.create(
        family=child.user.family,
        child=child,
        requested_by=user,
        kind=kind,
        status=PrintJob.Status.WAITING_PRINTER,
        snapshot=snapshot,
    )


def cancel_ticket(job, user):
    if job.status != PrintJob.Status.WAITING_PRINTER:
        raise ValidationError(
            "Seuls les tickets en attente de configuration peuvent être annulés.",
            code="not_waiting",
        )
    if user.role == Account.Role.CHILD:
        if job.child.user_id != user.pk:
            raise PermissionDenied
    elif user.role != Account.Role.PARENT or job.family_id != user.family_id:
        raise PermissionDenied
    job.status = PrintJob.Status.CANCELLED
    job.cancelled_at = timezone.now()
    job.save(update_fields=("status", "cancelled_at"))
    return job
