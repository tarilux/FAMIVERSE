from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from accounts.models import Account, ChildProfile
from communications.models import Notification
from communications.services import notify_child, notify_family_parents
from progression.models import CoinTransaction

from .models import Reward, RewardRequest


def _coin_balance(child):
    return (
        CoinTransaction.objects.filter(child=child).aggregate(
            total=Sum("amount_delta")
        )["total"]
        or 0
    )


@transaction.atomic
def request_reward(reward_id, actor):
    if actor.role != Account.Role.CHILD or actor.family_id is None:
        raise PermissionDenied
    child = (
        ChildProfile.objects.select_for_update()
        .filter(user=actor, archived_at__isnull=True)
        .first()
    )
    if child is None:
        raise PermissionDenied
    reward = (
        Reward.objects.select_for_update()
        .filter(
            pk=reward_id,
            family_id=actor.family_id,
            archived_at__isnull=True,
        )
        .first()
    )
    if reward is None:
        raise ValidationError(
            "Cette récompense n'est plus disponible.",
            code="reward_unavailable",
        )

    existing = RewardRequest.objects.filter(
        child=child,
        reward=reward,
        status=RewardRequest.Status.PENDING,
    ).first()
    if existing:
        return existing, False
    if _coin_balance(child) < reward.price_coins:
        raise ValidationError(
            "Solde de pièces insuffisant.",
            code="insufficient_coins",
        )
    reward_request, created = RewardRequest.objects.get_or_create(
        child=child,
        reward=reward,
        status=RewardRequest.Status.PENDING,
        defaults={"price_coins": reward.price_coins},
    )
    if created:
        notify_family_parents(
            actor.family_id,
            Notification.Kind.REWARD_REQUESTED,
            f"reward:{reward_request.pk}:requested",
            f"{child.first_name} — {reward.name}",
            f"{child.first_name} — {reward.name_ar or reward.name}",
        )
    return reward_request, created


@transaction.atomic
def decide_reward_request(request_id, actor, approve, parent_note=""):
    if actor.role != Account.Role.PARENT or actor.family_id is None:
        raise PermissionDenied
    reward_request = (
        RewardRequest.objects.select_for_update()
        .filter(
            pk=request_id,
            child__user__family_id=actor.family_id,
            status=RewardRequest.Status.PENDING,
        )
        .select_related("child", "reward")
        .first()
    )
    if reward_request is None:
        raise ValidationError(
            "Cette demande a déjà été traitée ou n'est pas accessible.",
            code="request_closed",
        )
    child = ChildProfile.objects.select_for_update().get(
        pk=reward_request.child_id
    )
    if approve:
        if _coin_balance(child) < reward_request.price_coins:
            raise ValidationError(
                "Le solde actuel est insuffisant pour accepter cette demande.",
                code="approval_insufficient",
            )
        CoinTransaction.objects.create(
            child=child,
            amount_delta=-reward_request.price_coins,
            kind=CoinTransaction.Kind.REWARD,
            reason=reward_request.reward.name,
            reward_request=reward_request,
            actor=actor,
        )
        reward_request.status = RewardRequest.Status.ACCEPTED
    else:
        reward_request.status = RewardRequest.Status.REJECTED
    reward_request.decided_by = actor
    reward_request.decided_at = timezone.now()
    reward_request.parent_note = parent_note
    reward_request.save(
        update_fields=(
            "status",
            "decided_by",
            "decided_at",
            "parent_note",
        )
    )
    notify_child(
        reward_request.child,
        (
            Notification.Kind.REWARD_ACCEPTED
            if approve
            else Notification.Kind.REWARD_REJECTED
        ),
        f"reward:{reward_request.pk}:{'accepted' if approve else 'rejected'}",
        reward_request.reward.name,
        reward_request.reward.name_ar or reward_request.reward.name,
    )
    return reward_request
