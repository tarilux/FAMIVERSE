from datetime import timedelta
import hashlib
import hmac

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import LoginAttempt

MAX_FAILURES = 5
WINDOW = timedelta(minutes=15)
LOCKOUT = timedelta(minutes=15)


def login_attempt_key(username, remote_addr):
    value = f"{username.strip().casefold()}:{remote_addr or 'unknown'}"
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def is_locked(key):
    now = timezone.now()
    attempt = LoginAttempt.objects.filter(key=key).first()
    if not attempt:
        return False
    if attempt.locked_until and attempt.locked_until > now:
        return True
    if attempt.window_started_at + WINDOW <= now:
        attempt.delete()
    return False


@transaction.atomic
def record_failure(key):
    now = timezone.now()
    attempt, _ = LoginAttempt.objects.select_for_update().get_or_create(
        key=key,
        defaults={"window_started_at": now},
    )
    if attempt.window_started_at + WINDOW <= now:
        attempt.failures = 0
        attempt.window_started_at = now
        attempt.locked_until = None
    attempt.failures += 1
    if attempt.failures >= MAX_FAILURES:
        attempt.locked_until = now + LOCKOUT
    attempt.save(update_fields=("failures", "window_started_at", "locked_until"))


def clear_attempts(key):
    LoginAttempt.objects.filter(key=key).delete()
