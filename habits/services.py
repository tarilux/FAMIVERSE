from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from accounts.models import Account, ChildProfile
from communications.models import Notification
from communications.services import notify_child, notify_family_parents
from progression.models import CoinTransaction, XpTransaction
from progression.services import evaluate_badges

from .models import HabitOccurrence, HabitTemplate


@transaction.atomic
def generate_habit_occurrences(family_id, start_date, end_date, child_id=None):
    if start_date > end_date or (end_date - start_date).days > 30:
        raise ValidationError("La période doit contenir entre 1 et 31 jours.")

    children = ChildProfile.objects.filter(
        user__family_id=family_id,
        user__is_active=True,
        archived_at__isnull=True,
    )
    if child_id is not None:
        children = children.filter(pk=child_id)
    templates = (
        HabitTemplate.objects.filter(
            family_id=family_id,
            archived_at__isnull=True,
            suspended_at__isnull=True,
            starts_on__lte=end_date,
            children__in=children,
        )
        .distinct()
        .prefetch_related(
            Prefetch(
                "children",
                queryset=children.order_by("pk"),
            )
        )
    )

    created = []
    for template in templates:
        for day_offset in range((end_date - start_date).days + 1):
            scheduled_date = start_date + timedelta(days=day_offset)
            if scheduled_date < template.starts_on:
                continue
            if (
                template.frequency == HabitTemplate.Frequency.WEEKLY
                and scheduled_date.weekday() not in template.weekdays
            ):
                continue
            for child in template.children.all():
                occurrence, was_created = HabitOccurrence.objects.get_or_create(
                    template=template,
                    child=child,
                    scheduled_date=scheduled_date,
                    defaults={
                        "title": template.title,
                        "title_ar": template.title_ar,
                        "description": template.description,
                        "description_ar": template.description_ar,
                        "time_of_day": template.time_of_day,
                        "scheduled_time": template.scheduled_time,
                    },
                )
                if was_created:
                    created.append(occurrence)
                elif occurrence.status == HabitOccurrence.Status.CANCELLED:
                    occurrence.status = HabitOccurrence.Status.PLANNED
                    occurrence.save(update_fields=("status",))
                    created.append(occurrence)
    return created


@transaction.atomic
def submit_habit(occurrence_id, actor, note=""):
    if actor.role != Account.Role.CHILD:
        raise PermissionDenied
    updated = HabitOccurrence.objects.filter(
        pk=occurrence_id,
        child__user=actor,
        child__archived_at__isnull=True,
        status=HabitOccurrence.Status.PLANNED,
    ).update(
        status=HabitOccurrence.Status.SUBMITTED,
        child_note=note,
        submitted_at=timezone.now(),
    )
    if updated != 1:
        raise ValidationError("Cette habitude n'est plus disponible.")
    occurrence = HabitOccurrence.objects.select_related("child").get(
        pk=occurrence_id
    )
    notify_family_parents(
        actor.family_id,
        Notification.Kind.HABIT_SUBMITTED,
        f"habit:{occurrence.pk}:submitted",
        occurrence.title,
        occurrence.title_ar or occurrence.title,
    )


@transaction.atomic
def decide_habit(occurrence_id, actor, approve, parent_note=""):
    if actor.role != Account.Role.PARENT or actor.family_id is None:
        raise PermissionDenied

    occurrence = (
        HabitOccurrence.objects.select_for_update()
        .filter(
            pk=occurrence_id,
            child__user__family_id=actor.family_id,
            status=HabitOccurrence.Status.SUBMITTED,
        )
        .select_related("child", "template")
        .first()
    )
    if occurrence is None:
        raise ValidationError(
            "Cette habitude a déjà été traitée ou n'est pas accessible."
        )

    ChildProfile.objects.select_for_update().get(pk=occurrence.child_id)
    occurrence.decided_by = actor
    occurrence.decided_at = timezone.now()
    occurrence.parent_note = parent_note
    if approve:
        habit = occurrence.template
        coins = habit.coins_reward if habit.family_id == actor.family_id else 0
        xp = habit.xp_reward if habit.family_id == actor.family_id else 0
        occurrence.coins_awarded = coins
        occurrence.xp_awarded = xp
        occurrence.status = HabitOccurrence.Status.APPROVED
        if coins:
            CoinTransaction.objects.create(
                child=occurrence.child,
                amount_delta=coins,
                kind=CoinTransaction.Kind.HABIT,
                reason=occurrence.title,
                habit_occurrence=occurrence,
                actor=actor,
            )
        if xp:
            XpTransaction.objects.create(
                child=occurrence.child,
                amount_delta=xp,
                kind=XpTransaction.Kind.HABIT,
                reason=occurrence.title,
                habit_occurrence=occurrence,
                actor=actor,
            )
    else:
        occurrence.status = HabitOccurrence.Status.REJECTED

    occurrence.save(
        update_fields=(
            "decided_by",
            "decided_at",
            "parent_note",
            "coins_awarded",
            "xp_awarded",
            "status",
        )
    )
    notify_child(
        occurrence.child,
        (
            Notification.Kind.HABIT_APPROVED
            if approve
            else Notification.Kind.HABIT_REJECTED
        ),
        f"habit:{occurrence.pk}:{'approved' if approve else 'rejected'}",
        occurrence.title,
        occurrence.title_ar or occurrence.title,
    )
    if approve:
        evaluate_badges(occurrence.child, actor=actor)
    return occurrence
