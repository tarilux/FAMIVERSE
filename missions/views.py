from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.models import Account

from .forms import (
    MissionAssignmentForm,
    MissionCategoryForm,
    MissionSubmissionForm,
    MissionTemplateForm,
)
from .models import MissionOccurrence, MissionTemplate
from .services import assign_mission, create_category, decide_missions, submit_mission


def _require_parent(user):
    if user.role != Account.Role.PARENT or user.family_id is None:
        raise PermissionDenied


@login_required
def template_list(request):
    _require_parent(request.user)
    templates = MissionTemplate.objects.filter(
        family_id=request.user.family_id,
        archived_at__isnull=True,
    ).select_related("category")
    return render(request, "missions/template_list.html", {"templates": templates})


@login_required
@require_http_methods(["GET", "POST"])
def category_create(request):
    _require_parent(request.user)
    form = MissionCategoryForm(request.POST or None)
    error = None
    if request.method == "POST" and form.is_valid():
        try:
            create_category(
                form.cleaned_data["name"],
                form.cleaned_data["name_ar"],
                request.user.family,
                request.user,
            )
        except ValidationError as exc:
            error = exc.messages
        else:
            return redirect("missions:template_list")
    return render(
        request, "missions/category_form.html", {"form": form, "error": error}
    )


@login_required
@require_http_methods(["GET", "POST"])
def template_create(request):
    _require_parent(request.user)
    form = MissionTemplateForm(
        request.POST or None,
        family=request.user.family,
        language=request.LANGUAGE_CODE,
    )
    if request.method == "POST" and form.is_valid():
        form.save(created_by=request.user)
        return redirect("missions:template_list")
    return render(request, "missions/template_form.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def template_edit(request, template_id):
    _require_parent(request.user)
    template = get_object_or_404(
        MissionTemplate,
        pk=template_id,
        family_id=request.user.family_id,
        archived_at__isnull=True,
    )
    form = MissionTemplateForm(
        request.POST or None,
        family=request.user.family,
        language=request.LANGUAGE_CODE,
        instance=template,
    )
    if request.method == "POST" and form.is_valid():
        form.save(created_by=request.user)
        return redirect("missions:template_list")
    return render(
        request,
        "missions/template_form.html",
        {"form": form, "editing": True},
    )


@login_required
@require_POST
def template_archive(request, template_id):
    _require_parent(request.user)
    template = get_object_or_404(
        MissionTemplate,
        pk=template_id,
        family_id=request.user.family_id,
        archived_at__isnull=True,
    )
    if request.POST.get("confirm") != "yes":
        return render(
            request,
            "missions/archive_confirm.html",
            {"template": template},
        )
    MissionTemplate.objects.filter(
        pk=template.pk,
        family_id=request.user.family_id,
        archived_at__isnull=True,
    ).update(archived_at=timezone.now())
    return redirect("missions:template_list")


@login_required
@require_http_methods(["GET", "POST"])
def assign(request, template_id):
    _require_parent(request.user)
    template = get_object_or_404(
        MissionTemplate,
        pk=template_id,
        family_id=request.user.family_id,
        archived_at__isnull=True,
    )
    form = MissionAssignmentForm(
        request.POST or None, family=request.user.family
    )
    error = None
    if request.method == "POST" and form.is_valid():
        try:
            assign_mission(
                template,
                [child.pk for child in form.cleaned_data["children"]],
                request.user,
                form.cleaned_data["due_date"],
            )
        except ValidationError as exc:
            error = exc.messages
        else:
            return redirect("missions:template_list")
    return render(
        request,
        "missions/assignment_form.html",
        {"form": form, "template": template, "error": error},
    )


@login_required
def my_missions(request):
    if request.user.role != Account.Role.CHILD:
        raise PermissionDenied
    occurrences = MissionOccurrence.objects.filter(
        child__user=request.user,
        child__archived_at__isnull=True,
    )
    return render(
        request,
        "missions/my_missions.html",
        {"occurrences": occurrences, "submission_form": MissionSubmissionForm()},
    )


@login_required
@require_POST
def submit(request, occurrence_id):
    if request.user.role != Account.Role.CHILD:
        raise PermissionDenied
    occurrence = get_object_or_404(
        MissionOccurrence,
        pk=occurrence_id,
        child__user=request.user,
        child__archived_at__isnull=True,
    )
    form = MissionSubmissionForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest("Le message dépasse la longueur autorisée.")
    try:
        submit_mission(occurrence.pk, request.user, form.cleaned_data["note"])
    except ValidationError as exc:
        return render(
            request,
            "missions/my_missions.html",
            {
                "occurrences": MissionOccurrence.objects.filter(
                    child__user=request.user,
                    child__archived_at__isnull=True,
                ),
                "submission_form": MissionSubmissionForm(),
                "error": exc.messages,
            },
            status=409,
        )
    return redirect("missions:my_missions")


@login_required
def validation_list(request):
    _require_parent(request.user)
    occurrences = MissionOccurrence.objects.filter(
        child__user__family_id=request.user.family_id,
        status=MissionOccurrence.Status.SUBMITTED,
    ).select_related("child", "template")
    return render(request, "missions/validation_list.html", {"occurrences": occurrences})


def _selected_ids(values):
    try:
        ids = sorted({int(value) for value in values})
    except (TypeError, ValueError):
        raise ValueError("Sélection invalide.") from None
    if not ids or len(ids) > 100 or any(value < 1 for value in ids):
        raise ValueError("Sélectionnez entre 1 et 100 missions.")
    return ids


@login_required
@require_POST
def decide(request):
    _require_parent(request.user)
    try:
        ids = _selected_ids(request.POST.getlist("occurrence_ids"))
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))

    decision = request.POST.get("decision")
    if decision not in ("approve", "reject"):
        return HttpResponseBadRequest("Décision invalide.")

    selected = list(
        MissionOccurrence.objects.filter(
            pk__in=ids,
            child__user__family_id=request.user.family_id,
            status=MissionOccurrence.Status.SUBMITTED,
        ).select_related("child")
    )
    if len(selected) != len(ids):
        return HttpResponseBadRequest(
            "Une ou plusieurs missions ne sont plus disponibles."
        )

    if request.POST.get("confirm") != "yes":
        return render(
            request,
            "missions/decision_confirm.html",
            {"occurrences": selected, "ids": ids, "decision": decision},
        )

    parent_note = request.POST.get("parent_note", "").strip()
    if len(parent_note) > 500:
        return HttpResponseBadRequest("Le message ne peut pas dépasser 500 caractères.")

    try:
        decide_missions(
            ids,
            request.user,
            approve=decision == "approve",
            parent_note=parent_note,
        )
    except ValidationError as exc:
        return render(
            request,
            "missions/validation_list.html",
            {
                "occurrences": MissionOccurrence.objects.filter(
                    child__user__family_id=request.user.family_id,
                    status=MissionOccurrence.Status.SUBMITTED,
                ).select_related("child"),
                "error": exc.messages,
            },
            status=409,
        )
    return redirect("missions:validation_list")
