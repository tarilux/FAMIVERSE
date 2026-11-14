from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import Account, ChildProfile
from communications.models import Notification
from communications.services import notify_child, notify_family_parents
from progression.models import CoinTransaction, XpTransaction
from progression.services import evaluate_badges

from .models import MissionCategory, MissionOccurrence

MAX_BULK_DECISIONS = 100


@transaction.atomic
def assign_mission(template, child_ids, actor, due_date=None):
    if actor.role != Account.Role.PARENT or actor.family_id != template.family_id:
        raise PermissionDenied
    if template.archived_at is not None:
        raise ValidationError("Une mission archivée ne peut pas être attribuée.")

    requested_ids = set(child_ids)
    children = list(
        ChildProfile.objects.filter(
            pk__in=requested_ids,
            user__family_id=actor.family_id,
            user__is_active=True,
            archived_at__isnull=True,
        ).select_related("user")
    )
    if not requested_ids or len(children) != len(requested_ids):
        raise ValidationError("Sélectionnez au moins un profil actif de votre famille.")

    category_name = template.category.name if template.category_id else ""
    category_name_ar = template.category.name_ar if template.category_id else ""
    occurrences = [
        MissionOccurrence(
            template=template,
            child=child,
            assigned_by=actor,
            title=template.title,
            title_ar=template.title_ar,
            description=template.description,
            description_ar=template.description_ar,
            category_name=category_name,
            category_name_ar=category_name_ar,
            due_date=due_date,
        )
        for child in children
    ]
    created = MissionOccurrence.objects.bulk_create(occurrences)
    for occurrence in created:
        notify_child(
            occurrence.child,
            Notification.Kind.MISSION_ASSIGNED,
            f"mission:{occurrence.pk}:assigned",
            occurrence.title,
            occurrence.title_ar or occurrence.title,
        )
    return created


@transaction.atomic
def create_category(name, name_ar, family, actor):
    if actor.role != Account.Role.PARENT or actor.family_id != family.pk:
        raise PermissionDenied
    name = name.strip()
    if MissionCategory.objects.filter(family=family, name__iexact=name).exists():
        raise ValidationError("Cette catégorie existe déjà dans la famille.")
    return MissionCategory.objects.create(
        family=family, name=name, name_ar=name_ar.strip()
    )


@transaction.atomic
def submit_mission(occurrence_id, actor, note=""):
    if actor.role != Account.Role.CHILD:
        raise PermissionDenied
    updated = MissionOccurrence.objects.filter(
        pk=occurrence_id,
        child__user=actor,
        child__archived_at__isnull=True,
        status=MissionOccurrence.Status.ASSIGNED,
    ).update(
        status=MissionOccurrence.Status.SUBMITTED,
        child_note=note,
        submitted_at=timezone.now(),
    )
    if updated != 1:
        raise ValidationError("Cette mission n'est plus disponible pour soumission.")
    occurrence = MissionOccurrence.objects.select_related("child").get(
        pk=occurrence_id
    )
    notify_family_parents(
        actor.family_id,
        Notification.Kind.MISSION_SUBMITTED,
        f"mission:{occurrence.pk}:submitted",
        occurrence.title,
        occurrence.title_ar or occurrence.title,
    )


@transaction.atomic
def decide_missions(occurrence_ids, actor, approve, parent_note=""):
    if actor.role != Account.Role.PARENT or actor.family_id is None:
        raise PermissionDenied

    ids = sorted(set(occurrence_ids))
    if not ids or len(ids) > MAX_BULK_DECISIONS:
        raise ValidationError("Sélectionnez entre 1 et 100 missions.")

    scoped = MissionOccurrence.objects.filter(
        pk__in=ids,
        child__user__family_id=actor.family_id,
        status=MissionOccurrence.Status.SUBMITTED,
    )
    child_ids = sorted(set(scoped.values_list("child_id", flat=True)))
    if not child_ids:
        raise ValidationError("Aucune mission sélectionnée n'est disponible.")

    locked_children = list(
        ChildProfile.objects.select_for_update()
        .filter(pk__in=child_ids, user__family_id=actor.family_id)
        .order_by("pk")
    )
    if len(locked_children) != len(child_ids):
        raise ValidationError("Un profil sélectionné n'est plus disponible.")

    occurrences = list(
        MissionOccurrence.objects.select_for_update()
        .filter(
            pk__in=ids,
            child__user__family_id=actor.family_id,
            status=MissionOccurrence.Status.SUBMITTED,
        )
        .select_related("template", "child")
        .order_by("pk")
    )
    if len(occurrences) != len(ids):
        raise ValidationError(
            "Une ou plusieurs missions ont déjà été traitées ou ne sont pas accessibles."
        )

    now = timezone.now()
    for occurrence in occurrences:
        occurrence.decided_by = actor
        occurrence.decided_at = now
        occurrence.parent_note = parent_note
        if approve:
            template = occurrence.template
            coins = (
                template.coins_reward
                if template and template.family_id == actor.family_id
                else 0
            )
            xp = (
                template.xp_reward
                if template and template.family_id == actor.family_id
                else 0
            )
            occurrence.coins_awarded = coins
            occurrence.xp_awarded = xp
            occurrence.status = MissionOccurrence.Status.APPROVED
            if coins:
                CoinTransaction.objects.create(
                    child=occurrence.child,
                    amount_delta=coins,
                    kind=CoinTransaction.Kind.MISSION,
                    reason=occurrence.title,
                    mission_occurrence=occurrence,
                    actor=actor,
                )
            if xp:
                XpTransaction.objects.create(
                    child=occurrence.child,
                    amount_delta=xp,
                    kind=XpTransaction.Kind.MISSION,
                    reason=occurrence.title,
                    mission_occurrence=occurrence,
                    actor=actor,
                )
        else:
            occurrence.status = MissionOccurrence.Status.REJECTED

    MissionOccurrence.objects.bulk_update(
        occurrences,
        (
            "decided_by",
            "decided_at",
            "parent_note",
            "coins_awarded",
            "xp_awarded",
            "status",
        ),
    )
    for occurrence in occurrences:
        notify_child(
            occurrence.child,
            (
                Notification.Kind.MISSION_APPROVED
                if approve
                else Notification.Kind.MISSION_REJECTED
            ),
            f"mission:{occurrence.pk}:{'approved' if approve else 'rejected'}",
            occurrence.title,
            occurrence.title_ar or occurrence.title,
        )
    if approve:
        for child in locked_children:
            evaluate_badges(child, actor=actor)
    return occurrences
