import logging
import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from backupcenter.models import BackupRun, BackupSettings
from backupcenter.services import BackupOperationError, create_backup
from core.models import Family

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run scheduled application backups."

    def handle(self, *args, **options):
        while True:
            family_count = Family.objects.count()
            if family_count == 1:
                family = Family.objects.first()
                backup_settings = BackupSettings.objects.get_or_create(
                    family=family
                )[0]
                now = timezone.localtime()
                scheduled_day = (
                    backup_settings.frequency == BackupSettings.Frequency.DAILY
                    or now.weekday() == backup_settings.weekday
                )
                due = (
                    backup_settings.enabled
                    and scheduled_day
                    and now.time() >= backup_settings.schedule_time
                )
                already_attempted = BackupRun.objects.filter(
                    family=family,
                    kind=BackupRun.Kind.SCHEDULED,
                    status__in=(
                        BackupRun.Status.COMPLETED,
                        BackupRun.Status.FAILED,
                    ),
                    created_at__date=now.date(),
                ).exists()
                if due and not already_attempted:
                    try:
                        run = create_backup(
                            family,
                            kind=BackupRun.Kind.SCHEDULED,
                        )
                    except BackupOperationError:
                        logger.exception("La sauvegarde automatique a échoué.")
                    else:
                        logger.info("Sauvegarde automatique terminée : %s", run.file_name)
            elif family_count > 1:
                logger.error(
                    "Sauvegarde automatique suspendue : plusieurs familles sont "
                    "présentes dans la même installation."
                )
                time.sleep(60)
                continue
            time.sleep(30)
