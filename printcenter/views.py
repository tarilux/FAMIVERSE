from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import Account, ChildProfile
from core.i18n import UI_MESSAGES

from .forms import PrintCalendarBlockForm, PrintRequestForm, PrintSettingsForm
from .models import PrintCalendarBlock, PrintJob, PrintSettings
from .services import cancel_ticket, request_ticket


def _require_parent(user):
    if user.role != Account.Role.PARENT or user.family_id is None:
        raise PermissionDenied


def _ui(request, key):
    language = request.LANGUAGE_CODE if request.LANGUAGE_CODE in UI_MESSAGES else "fr"
    return UI_MESSAGES[language][key]


def _settings_context(request, settings, *, settings_form=None, calendar_form=None):
    language = request.LANGUAGE_CODE
    return {
        "settings": settings,
        "settings_form": settings_form
        or PrintSettingsForm(instance=settings, language=language),
        "calendar_form": calendar_form
        or PrintCalendarBlockForm(language=language),
        "calendar_blocks": PrintCalendarBlock.objects.filter(
            family=request.user.family
        ),
    }


def _center_context(request, *, request_form=None):
    user = request.user
    if user.role not in (Account.Role.PARENT, Account.Role.CHILD) or not user.family_id:
        raise PermissionDenied
    family = user.family
    children = ChildProfile.objects.filter(
        user__family=family, archived_at__isnull=True
    )
    child_only = user.role == Account.Role.CHILD
    return {
        "request_form": request_form
        or PrintRequestForm(
            family=family,
            language=request.LANGUAGE_CODE,
            child_only=child_only,
        ),
        "jobs": PrintJob.objects.filter(family=family)
        if not child_only
        else PrintJob.objects.filter(child__user=user),
        "children": children,
        "settings": PrintSettings.objects.get_or_create(family=family)[0],
    }


@login_required
def center(request):
    return render(request, "printcenter/center.html", _center_context(request))


@login_required
@require_POST
def create_ticket(request):
    form = PrintRequestForm(
        request.POST,
        family=request.user.family,
        language=request.LANGUAGE_CODE,
        child_only=request.user.role == Account.Role.CHILD,
    )
    if not form.is_valid():
        return render(
            request,
            "printcenter/center.html",
            _center_context(request, request_form=form),
            status=400,
        )
    child = (
        request.user.child_profile
        if request.user.role == Account.Role.CHILD
        else form.cleaned_data["child"]
    )
    try:
        job = request_ticket(request.user, child, form.cleaned_data["kind"])
    except ValidationError as exc:
        codes = {error.code for error in exc.error_list}
        key = (
            "print_no_missions_today"
            if "no_missions_today" in codes
            else "print_invalid_ticket"
        )
        messages.error(request, _ui(request, key))
        return redirect("printcenter:center")
    return redirect("printcenter:preview", job_id=job.pk)


@login_required
def preview(request, job_id):
    job = get_object_or_404(
        PrintJob.objects.select_related("child", "family"),
        pk=job_id,
        family_id=request.user.family_id,
    )
    if request.user.role == Account.Role.CHILD and job.child.user_id != request.user.pk:
        raise PermissionDenied
    if request.user.role not in (Account.Role.PARENT, Account.Role.CHILD):
        raise PermissionDenied
    return render(request, "printcenter/preview.html", {"job": job})


@login_required
@require_POST
def cancel(request, job_id):
    job = get_object_or_404(
        PrintJob.objects.select_related("child"),
        pk=job_id,
        family_id=request.user.family_id,
    )
    try:
        cancel_ticket(job, request.user)
    except ValidationError as exc:
        codes = {error.code for error in exc.error_list}
        key = "print_cancel_unavailable" if "not_waiting" in codes else "print_invalid_ticket"
        messages.error(request, _ui(request, key))
    return redirect("printcenter:center")


@login_required
def settings_view(request):
    _require_parent(request.user)
    settings = PrintSettings.objects.get_or_create(family=request.user.family)[0]
    context = _settings_context(request, settings)
    return render(request, "printcenter/settings.html", context)


@login_required
@require_POST
def save_settings(request):
    _require_parent(request.user)
    settings = PrintSettings.objects.get_or_create(family=request.user.family)[0]
    form = PrintSettingsForm(
        request.POST, instance=settings, language=request.LANGUAGE_CODE
    )
    if form.is_valid():
        form.save()
        messages.success(request, _ui(request, "print_settings_saved"))
        return redirect("printcenter:settings")
    context = _settings_context(request, settings, settings_form=form)
    return render(request, "printcenter/settings.html", context, status=400)


@login_required
@require_POST
def add_calendar_block(request):
    _require_parent(request.user)
    form = PrintCalendarBlockForm(request.POST, language=request.LANGUAGE_CODE)
    if form.is_valid():
        block = form.save(commit=False)
        block.family = request.user.family
        try:
            block.full_clean()
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            block.save()
            messages.success(request, _ui(request, "print_calendar_added"))
            return redirect("printcenter:settings")
    settings = PrintSettings.objects.get_or_create(family=request.user.family)[0]
    context = _settings_context(request, settings, calendar_form=form)
    return render(request, "printcenter/settings.html", context, status=400)


@login_required
@require_POST
def delete_calendar_block(request, block_id):
    _require_parent(request.user)
    block = get_object_or_404(
        PrintCalendarBlock, pk=block_id, family=request.user.family
    )
    block.delete()
    messages.success(request, _ui(request, "print_calendar_removed"))
    return redirect("printcenter:settings")
