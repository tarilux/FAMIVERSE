from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import Account
from core.i18n import UI_MESSAGES

from .forms import BackupSettingsForm, RestoreBackupForm
from .models import BackupRun, BackupSettings
from .services import (
    BackupOperationError,
    _backup_path,
    create_backup,
    import_backup,
    require_single_family,
    restore_backup,
    verify_backup,
)


def _require_parent(request):
    if request.user.role != Account.Role.PARENT or request.user.family_id is None:
        raise PermissionDenied
    require_single_family(request.user.family)


def _ui(request, key):
    language = request.LANGUAGE_CODE if request.LANGUAGE_CODE in UI_MESSAGES else "fr"
    return UI_MESSAGES[language][key]


def _context(request, *, settings_form=None, restore_form=None):
    family = request.user.family
    backup_settings = BackupSettings.objects.get_or_create(family=family)[0]
    return {
        "backup_settings": backup_settings,
        "settings_form": settings_form
        or BackupSettingsForm(instance=backup_settings, language=request.LANGUAGE_CODE),
        "restore_form": restore_form
        or RestoreBackupForm(family=family, language=request.LANGUAGE_CODE),
        "runs": BackupRun.objects.filter(family=family),
    }


@login_required
def center(request):
    _require_parent(request)
    return render(request, "backupcenter/center.html", _context(request))


@login_required
@require_POST
def save_settings(request):
    _require_parent(request)
    instance = BackupSettings.objects.get_or_create(family=request.user.family)[0]
    form = BackupSettingsForm(
        request.POST, instance=instance, language=request.LANGUAGE_CODE
    )
    if form.is_valid():
        form.save()
        messages.success(request, _ui(request, "backup_settings_saved"))
        return redirect("backupcenter:center")
    return render(
        request,
        "backupcenter/center.html",
        _context(request, settings_form=form),
        status=400,
    )


@login_required
@require_POST
def create_manual(request):
    _require_parent(request)
    try:
        run = create_backup(
            request.user.family,
            kind=BackupRun.Kind.MANUAL,
            created_by=request.user,
        )
    except BackupOperationError:
        messages.error(request, _ui(request, "backup_create_failed"))
        return redirect("backupcenter:center")
    return redirect("backupcenter:download", run_id=run.pk)


@login_required
def download(request, run_id):
    _require_parent(request)
    run = get_object_or_404(
        BackupRun,
        pk=run_id,
        family=request.user.family,
        status=BackupRun.Status.COMPLETED,
    )
    try:
        path = _backup_path(run.file_name)
        verify_backup(path, expected_sha256=run.sha256)
    except BackupOperationError:
        run.status = BackupRun.Status.FAILED
        run.error_message = _ui(request, "backup_integrity_failed")
        run.save(update_fields=("status", "error_message"))
        messages.error(request, _ui(request, "backup_integrity_failed"))
        return redirect("backupcenter:center")
    return FileResponse(
        path.open("rb"),
        as_attachment=True,
        filename=run.file_name,
        content_type="application/zip",
    )


@login_required
@require_POST
def restore(request):
    _require_parent(request)
    form = RestoreBackupForm(
        request.POST,
        request.FILES,
        family=request.user.family,
        language=request.LANGUAGE_CODE,
    )
    if not form.is_valid():
        return render(
            request,
            "backupcenter/center.html",
            _context(request, restore_form=form),
            status=400,
        )
    try:
        run = form.cleaned_data["backup"]
        if form.cleaned_data["upload"]:
            run = import_backup(
                form.cleaned_data["upload"],
                request.user.family,
                actor=request.user,
            )
        restore_backup(run, actor=request.user)
    except BackupOperationError:
        messages.error(request, _ui(request, "backup_restore_failed"))
        return redirect("backupcenter:center")
    messages.success(request, _ui(request, "backup_restore_success"))
    return redirect("backupcenter:center")
