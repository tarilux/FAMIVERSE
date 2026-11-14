from datetime import date
import tempfile
import zipfile
from pathlib import Path

from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse

from accounts.models import Account, ChildProfile
from core.models import Family

from .models import BackupRun, BackupSettings
from .services import (
    BackupOperationError,
    create_backup,
    import_backup,
    restore_backup,
    verify_backup,
)


class BackupCenterTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.temp_root = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_root.cleanup)
        self.backup_root = Path(self.temp_root.name) / "backups"
        self.media_root = Path(self.temp_root.name) / "media"
        self.settings_override = override_settings(
            BACKUP_ROOT=self.backup_root,
            MEDIA_ROOT=self.media_root,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.family = Family.objects.create(name="Famille Test")
        self.parent = Account.objects.create_user(
            username="parent",
            password="4826",
            role=Account.Role.PARENT,
            family=self.family,
        )
        self.child_user = Account.objects.create_user(
            username="lea",
            password="7315",
            role=Account.Role.CHILD,
            family=self.family,
        )
        self.child = ChildProfile.objects.create(
            user=self.child_user,
            first_name="Léa",
            date_of_birth=date(2017, 5, 10),
        )
        self.client = Client()

    def test_manual_backup_contains_data_and_passes_integrity_check(self):
        avatar = self.media_root / "avatars" / "lea" / "avatar.png"
        avatar.parent.mkdir(parents=True)
        avatar.write_bytes(b"avatar data")

        run = create_backup(
            self.family,
            kind=BackupRun.Kind.MANUAL,
            created_by=self.parent,
        )

        manifest = verify_backup(
            self.backup_root / run.file_name,
            expected_sha256=run.sha256,
        )
        self.assertEqual(manifest["media_files"][0]["path"], "avatars/lea/avatar.png")
        with zipfile.ZipFile(self.backup_root / run.file_name) as archive:
            fixture = archive.read("database.json").decode("utf-8")
        self.assertIn("Famille Test", fixture)
        self.assertEqual(run.status, BackupRun.Status.COMPLETED)

    def test_modified_archive_is_rejected(self):
        run = create_backup(self.family, kind=BackupRun.Kind.MANUAL)
        path = self.backup_root / run.file_name
        contents = {}
        with zipfile.ZipFile(path) as source:
            for name in source.namelist():
                contents[name] = source.read(name)
        contents["database.json"] = b"[]"
        corrupt_path = self.backup_root / "famiverse-corrupt.zip"
        with zipfile.ZipFile(corrupt_path, "w") as archive:
            for name, value in contents.items():
                archive.writestr(name, value)

        with self.assertRaises(BackupOperationError):
            verify_backup(corrupt_path)

    def test_exported_archive_can_be_imported_for_restore(self):
        run = create_backup(self.family, kind=BackupRun.Kind.MANUAL)
        exported = (self.backup_root / run.file_name).read_bytes()

        imported = import_backup(
            SimpleUploadedFile("famiverse-export.zip", exported),
            self.family,
            actor=self.parent,
        )

        self.assertEqual(imported.kind, BackupRun.Kind.IMPORTED)
        self.assertEqual(imported.source_file_name, "famiverse-export.zip")
        verify_backup(
            self.backup_root / imported.file_name,
            expected_sha256=imported.sha256,
        )

    def test_restore_creates_protection_and_restores_database_and_media(self):
        avatar = self.media_root / "avatars" / "lea" / "avatar.png"
        avatar.parent.mkdir(parents=True)
        avatar.write_bytes(b"before restore")
        run = create_backup(
            self.family,
            kind=BackupRun.Kind.MANUAL,
            created_by=self.parent,
        )
        self.family.name = "Changed after backup"
        self.family.save(update_fields=("name",))
        avatar.write_bytes(b"changed after backup")

        restore_run = restore_backup(run, actor=self.parent)

        self.assertEqual(
            Family.objects.get(pk=self.family.pk).name,
            "Famille Test",
        )
        self.assertEqual(avatar.read_bytes(), b"before restore")
        self.assertEqual(restore_run.status, BackupRun.Status.COMPLETED)
        self.assertTrue(
            BackupRun.objects.filter(
                kind=BackupRun.Kind.PRE_RESTORE,
                status=BackupRun.Status.COMPLETED,
            ).exists()
        )

    def test_parent_can_download_but_child_cannot_access_backup_center(self):
        self.client.force_login(self.parent)
        self.assertEqual(self.client.get(reverse("backupcenter:center")).status_code, 200)

        response = self.client.post(reverse("backupcenter:create_manual"))

        self.assertEqual(response.status_code, 302)
        response = self.client.get(response.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        response.close()
        self.client.force_login(self.child_user)
        self.assertEqual(self.client.get(reverse("backupcenter:center")).status_code, 403)

    def test_parent_backup_access_is_blocked_for_multiple_families(self):
        Family.objects.create(name="Autre famille")
        self.client.force_login(self.parent)

        self.assertEqual(self.client.get(reverse("backupcenter:center")).status_code, 403)
        with self.assertRaises(PermissionDenied):
            create_backup(self.family, kind=BackupRun.Kind.MANUAL)

    def test_backup_settings_default_to_daily_at_two_with_thirty_versions(self):
        backup_settings = BackupSettings.objects.create(family=self.family)

        self.assertTrue(backup_settings.enabled)
        self.assertEqual(backup_settings.frequency, BackupSettings.Frequency.DAILY)
        self.assertEqual(backup_settings.schedule_time.strftime("%H:%M"), "02:00")
        self.assertEqual(backup_settings.retention_count, 30)

    def test_scheduled_backup_retention_keeps_recent_versions_only(self):
        BackupSettings.objects.create(family=self.family, retention_count=1)

        older = create_backup(self.family, kind=BackupRun.Kind.SCHEDULED)
        newer = create_backup(self.family, kind=BackupRun.Kind.SCHEDULED)

        older.refresh_from_db()
        self.assertEqual(older.status, BackupRun.Status.PRUNED)
        self.assertFalse((self.backup_root / older.file_name).exists())
        self.assertTrue((self.backup_root / newer.file_name).exists())

    def test_parent_can_change_schedule_and_disable_automatic_backups(self):
        self.client.force_login(self.parent)

        response = self.client.post(
            reverse("backupcenter:save_settings"),
            {
                "frequency": BackupSettings.Frequency.WEEKLY,
                "weekday": "3",
                "schedule_time": "01:45",
                "retention_count": "12",
            },
        )

        self.assertEqual(response.status_code, 302)
        backup_settings = BackupSettings.objects.get(family=self.family)
        self.assertFalse(backup_settings.enabled)
        self.assertEqual(backup_settings.frequency, BackupSettings.Frequency.WEEKLY)
        self.assertEqual(backup_settings.weekday, 3)
        self.assertEqual(backup_settings.schedule_time.strftime("%H:%M"), "01:45")
        self.assertEqual(backup_settings.retention_count, 12)

    def test_restore_requires_explicit_confirmation(self):
        run = create_backup(self.family, kind=BackupRun.Kind.MANUAL)
        self.client.force_login(self.parent)

        response = self.client.post(
            reverse("backupcenter:restore"),
            {
                "backup": run.pk,
                "confirmation": "yes",
                "confirm_overwrite": "on",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Family.objects.get(pk=self.family.pk).name, "Famille Test")
        self.assertFalse(
            BackupRun.objects.filter(kind=BackupRun.Kind.PRE_RESTORE).exists()
        )

    def test_failed_integrity_check_is_logged_without_restoring(self):
        run = create_backup(self.family, kind=BackupRun.Kind.MANUAL)
        path = self.backup_root / run.file_name
        path.write_bytes(b"corrupted")
        self.client.force_login(self.parent)

        response = self.client.post(
            reverse("backupcenter:restore"),
            {
                "backup": run.pk,
                "confirmation": "RESTAURER",
                "confirm_overwrite": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Family.objects.get(pk=self.family.pk).name, "Famille Test")
        self.assertTrue(
            BackupRun.objects.filter(
                kind=BackupRun.Kind.RESTORE,
                status=BackupRun.Status.FAILED,
                source_file_name=run.file_name,
            ).exists()
        )
