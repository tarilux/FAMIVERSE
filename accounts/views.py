import re
import mimetypes

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from .forms import ChildCreateForm, LoginForm
from .models import Account, ChildProfile
from .security import clear_attempts, is_locked, login_attempt_key, record_failure
from progression.services import (
    get_balances,
    get_family_balances,
    get_level_progress,
    get_progress_summary,
)


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:home")

    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        username = form.cleaned_data["username"].strip()
        key = login_attempt_key(username, request.META.get("REMOTE_ADDR"))
        if is_locked(key):
            form.add_error(None, "locked")
        else:
            pin = form.cleaned_data["pin"]
            user = None
            if re.fullmatch(r"\d{4,6}", pin):
                user = authenticate(request, username=username, password=pin)
            if user is not None and user.family_id is not None:
                clear_attempts(key)
                login(request, user)
                next_url = request.POST.get("next", "")
                if url_has_allowed_host_and_scheme(
                    next_url, allowed_hosts={request.get_host()}
                ):
                    return redirect(next_url)
                return redirect("accounts:home")
            record_failure(key)
            form.add_error(None, "invalid")

    return render(request, "accounts/login.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("accounts:login")


@login_required
def home(request):
    if request.user.family_id is None:
        raise PermissionDenied

    if request.user.role == Account.Role.PARENT:
        children = list(ChildProfile.objects.filter(
            user__family_id=request.user.family_id,
            archived_at__isnull=True,
        ).select_related("user"))
        balances = get_family_balances(child.pk for child in children)
        for child in children:
            child.balances = balances[child.pk]
            child.level = get_level_progress(child.balances["xp"])
        return render(
            request,
            "accounts/home.html",
            {
                "children": children,
                "profile": None,
            },
        )

    profile = get_object_or_404(
        ChildProfile.objects.select_related("user"),
        user=request.user,
        archived_at__isnull=True,
    )
    return render(
        request,
        "accounts/home.html",
        {
            "children": (),
            "profile": profile,
            "progress": get_progress_summary(profile),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def child_create(request):
    if not request.user.is_parent or request.user.family_id is None:
        raise PermissionDenied

    form = ChildCreateForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save(request.user.family)
        return redirect("accounts:home")
    return render(request, "accounts/child_create.html", {"form": form})


@login_required
def child_avatar(request, profile_id):
    profiles = ChildProfile.objects.select_related("user")
    if request.user.role == Account.Role.CHILD:
        profiles = profiles.filter(user=request.user)
    elif request.user.role == Account.Role.PARENT and request.user.family_id:
        profiles = profiles.filter(user__family_id=request.user.family_id)
    else:
        raise PermissionDenied

    profile = get_object_or_404(
        profiles.filter(archived_at__isnull=True, avatar__gt=""),
        pk=profile_id,
    )
    content_type = mimetypes.guess_type(profile.avatar.name)[0] or "application/octet-stream"
    response = FileResponse(profile.avatar.open("rb"), content_type=content_type)
    response["Cache-Control"] = "private, no-store"
    return response
