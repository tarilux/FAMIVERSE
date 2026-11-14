import calendar
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.models import Account, ChildProfile
from missions.models import MissionOccurrence

from .forms import HabitTemplateForm, WEEKDAY_LABELS
from .models import HabitOccurrence, HabitTemplate
from .services import decide_habit, generate_habit_occurrences, submit_habit


def _require_parent(user):
    if user.role != Account.Role.PARENT or user.family_id is None:
        raise PermissionDenied


def _plan_period(request):
    view_mode = request.GET.get("view", "day")
    if view_mode not in ("day", "week", "month"):
        raise ValueError("Vue de planning invalide.")
    try:
        selected_date = date.fromisoformat(
            request.GET.get("date", timezone.localdate().isoformat())
        )
    except (ValueError, OverflowError):
        raise ValueError("Date de planning invalide.") from None

    try:
        if view_mode == "week":
            start_date = selected_date - timedelta(days=selected_date.weekday())
            end_date = start_date + timedelta(days=6)
        elif view_mode == "month":
            start_date = selected_date.replace(day=1)
            end_date = selected_date.replace(
                day=calendar.monthrange(selected_date.year, selected_date.month)[1]
            )
        else:
            start_date = end_date = selected_date
    except OverflowError:
        raise ValueError("Date de planning invalide.") from None
    return view_mode, selected_date, start_date, end_date


def _render_plan(request, child=None):
    try:
        view_mode, selected_date, start_date, end_date = _plan_period(request)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))

    family_id = request.user.family_id
    child_id = child.pk if child else None
    if child is None and request.user.role == Account.Role.PARENT:
        requested_child = request.GET.get("child", "")
        if requested_child:
            try:
                child_id = int(requested_child)
            except ValueError:
                return HttpResponseBadRequest("Profil enfant invalide.")
            child = get_object_or_404(
                ChildProfile,
                pk=child_id,
                user__family_id=family_id,
                user__is_active=True,
                archived_at__isnull=True,
            )

    generate_habit_occurrences(
        family_id, start_date, end_date, child_id=child_id
    )

    missions = MissionOccurrence.objects.filter(
        child__user__family_id=family_id,
        child__user__is_active=True,
        child__archived_at__isnull=True,
        due_date__range=(start_date, end_date),
    ).exclude(status=MissionOccurrence.Status.CANCELLED)
    habits = HabitOccurrence.objects.filter(
        child__user__family_id=family_id,
        child__user__is_active=True,
        child__archived_at__isnull=True,
        scheduled_date__range=(start_date, end_date),
    ).filter(
        Q(
            template__archived_at__isnull=True,
            template__suspended_at__isnull=True,
        )
        | Q(scheduled_date__lt=F("template__starts_on"))
        | Q(status=HabitOccurrence.Status.CANCELLED)
    )
    upcoming = MissionOccurrence.objects.filter(
        child__user__family_id=family_id,
        child__user__is_active=True,
        child__archived_at__isnull=True,
        due_date__gt=end_date,
        status__in=(
            MissionOccurrence.Status.ASSIGNED,
            MissionOccurrence.Status.SUBMITTED,
        ),
    ).select_related("child")
    if child_id is not None:
        missions = missions.filter(child_id=child_id)
        habits = habits.filter(child_id=child_id)
        upcoming = upcoming.filter(child_id=child_id)
    missions = list(missions.select_related("child").order_by("due_date", "created_at"))
    habits = list(habits.select_related("child").order_by("scheduled_time", "title"))
    upcoming = list(upcoming.order_by("due_date", "created_at")[:20])

    missions_by_date = {}
    habits_by_date = {}
    for mission in missions:
        missions_by_date.setdefault(mission.due_date, []).append(mission)
    for habit in habits:
        habits_by_date.setdefault(habit.scheduled_date, []).append(habit)

    days = []
    current_date = start_date
    while current_date <= end_date:
        days.append(
            {
                "date": current_date,
                "missions": missions_by_date.get(current_date, []),
                "habits": habits_by_date.get(current_date, []),
            }
        )
        current_date += timedelta(days=1)

    children = ()
    if request.user.role == Account.Role.PARENT:
        children = ChildProfile.objects.filter(
            user__family_id=family_id,
            user__is_active=True,
            archived_at__isnull=True,
        ).order_by("first_name", "pk")
    return render(
        request,
        "habits/planning.html",
        {
            "days": days,
            "children": children,
            "selected_child": child,
            "view_mode": view_mode,
            "selected_date": selected_date,
            "start_date": start_date,
            "end_date": end_date,
            "upcoming_missions": upcoming,
            "child_planning": request.user.role == Account.Role.CHILD,
        },
    )


@login_required
def planning(request):
    _require_parent(request.user)
    return _render_plan(request)


@login_required
def my_planning(request):
    if request.user.role != Account.Role.CHILD or request.user.family_id is None:
        raise PermissionDenied
    child = get_object_or_404(
        ChildProfile,
        user=request.user,
        archived_at__isnull=True,
    )
    return _render_plan(request, child=child)


@login_required
def template_list(request):
    _require_parent(request.user)
    habits = list(
        HabitTemplate.objects.filter(
            family_id=request.user.family_id,
            archived_at__isnull=True,
        )
        .prefetch_related("children")
        .order_by("title", "pk")
    )
    labels = WEEKDAY_LABELS.get(request.LANGUAGE_CODE, WEEKDAY_LABELS["fr"])
    for habit in habits:
        habit.weekday_labels = [
            labels[day]
            for day in habit.weekdays
            if type(day) is int and day in range(len(labels))
        ]
    return render(request, "habits/template_list.html", {"habits": habits})


@login_required
@require_http_methods(["GET", "POST"])
def template_create(request):
    _require_parent(request.user)
    form = HabitTemplateForm(
        request.POST or None,
        family=request.user.family,
        language=request.LANGUAGE_CODE,
    )
    if request.method == "POST" and form.is_valid():
        form.save(created_by=request.user)
        return redirect("habits:template_list")
    return render(request, "habits/template_form.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def template_edit(request, template_id):
    _require_parent(request.user)
    habit = get_object_or_404(
        HabitTemplate,
        pk=template_id,
        family_id=request.user.family_id,
        archived_at__isnull=True,
    )
    form = HabitTemplateForm(
        request.POST or None,
        family=request.user.family,
        language=request.LANGUAGE_CODE,
        instance=habit,
    )
    if request.method == "POST" and form.is_valid():
        form.save(created_by=request.user)
        return redirect("habits:template_list")
    return render(
        request,
        "habits/template_form.html",
        {"form": form, "editing": True},
    )


@login_required
@require_POST
@transaction.atomic
def template_toggle_suspension(request, template_id):
    _require_parent(request.user)
    habit = get_object_or_404(
        HabitTemplate,
        pk=template_id,
        family_id=request.user.family_id,
        archived_at__isnull=True,
    )
    if habit.suspended_at:
        habit.suspended_at = None
        habit.starts_on = timezone.localdate()
        habit.save(update_fields=("suspended_at", "starts_on", "updated_at"))
    else:
        today = timezone.localdate()
        habit.suspended_at = timezone.now()
        habit.starts_on = today + timedelta(days=1)
        habit.save(update_fields=("suspended_at", "starts_on", "updated_at"))
        HabitOccurrence.objects.filter(
            template=habit,
            status=HabitOccurrence.Status.PLANNED,
            scheduled_date__gt=today,
        ).update(status=HabitOccurrence.Status.CANCELLED)
    return redirect("habits:template_list")


@login_required
@require_POST
@transaction.atomic
def template_archive(request, template_id):
    _require_parent(request.user)
    habit = get_object_or_404(
        HabitTemplate,
        pk=template_id,
        family_id=request.user.family_id,
        archived_at__isnull=True,
    )
    habit.archived_at = timezone.now()
    habit.starts_on = timezone.localdate() + timedelta(days=1)
    habit.save(update_fields=("archived_at", "starts_on", "updated_at"))
    HabitOccurrence.objects.filter(
        template=habit,
        status=HabitOccurrence.Status.PLANNED,
        scheduled_date__gt=timezone.localdate(),
    ).update(status=HabitOccurrence.Status.CANCELLED)
    return redirect("habits:template_list")


@login_required
def validation_list(request):
    _require_parent(request.user)
    occurrences = (
        HabitOccurrence.objects.filter(
            child__user__family_id=request.user.family_id,
            status=HabitOccurrence.Status.SUBMITTED,
        )
        .select_related("child", "template")
        .order_by("submitted_at", "pk")
    )
    return render(
        request,
        "habits/validation_list.html",
        {"occurrences": occurrences},
    )


@login_required
@require_POST
def submit(request, occurrence_id):
    if request.user.role != Account.Role.CHILD:
        raise PermissionDenied
    note = request.POST.get("note", "").strip()
    if len(note) > 500:
        return HttpResponseBadRequest("Le message ne peut pas dépasser 500 caractères.")
    try:
        submit_habit(occurrence_id, request.user, note)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("habits:my_planning")


@login_required
@require_http_methods(["GET", "POST"])
def decide(request, occurrence_id, decision):
    _require_parent(request.user)
    if decision not in ("approve", "reject"):
        return HttpResponseBadRequest("Décision invalide.")
    occurrence = get_object_or_404(
        HabitOccurrence.objects.select_related("child"),
        pk=occurrence_id,
        child__user__family_id=request.user.family_id,
        status=HabitOccurrence.Status.SUBMITTED,
    )
    if request.method == "POST":
        if request.POST.get("confirm") != "yes":
            return HttpResponseBadRequest("La confirmation est obligatoire.")
        parent_note = request.POST.get("parent_note", "").strip()
        if len(parent_note) > 500:
            return HttpResponseBadRequest(
                "Le message ne peut pas dépasser 500 caractères."
            )
        try:
            decide_habit(
                occurrence.pk,
                request.user,
                approve=decision == "approve",
                parent_note=parent_note,
            )
        except ValidationError as exc:
            return render(
                request,
                "habits/decision_confirm.html",
                {
                    "occurrence": occurrence,
                    "decision": decision,
                    "error": exc.messages,
                },
                status=409,
            )
        return redirect("habits:validation_list")
    return render(
        request,
        "habits/decision_confirm.html",
        {"occurrence": occurrence, "decision": decision},
    )
