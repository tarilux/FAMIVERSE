import hashlib
import io
import json
import logging
import os
import shutil
import stat
import tempfile
import zipfile
import zlib
from pathlib import Path, PurePosixPath

import django
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection, transaction
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from core.models import Family

from .models import BackupRun, BackupSettings

logger = logging.getLogger(__name__)
SIGNING_SALT = "famiverse.backup.manifest.v1"
MAX_ARCHIVE_BYTES = 1_000_000_000
MAX_ARCHIVE_MEMBERS = 20_000
MAX_MANIFEST_BYTES = 5_000_000


class BackupOperationError(Exception):
    pass


def require_single_family(family):
    if Family.objects.count() != 1 or family is None:
        raise PermissionDenied(
            "Les sauvegardes parentales nécessitent une seule famille par installation."
        )
    if family.pk != Family.objects.only("pk").first().pk:
        raise PermissionDenied


def _backup_root():
    return Path(settings.BACKUP_ROOT)


def _validate_storage_paths():
    backup_root = _backup_root().resolve()
    media_root = Path(settings.MEDIA_ROOT).resolve()
    if (
        backup_root == media_root
        or backup_root in media_root.parents
        or media_root in backup_root.parents
    ):
        raise BackupOperationError(
            "La destination des sauvegardes doit être séparée du stockage média."
        )


def _file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _backup_path(file_name):
    if not file_name or Path(file_name).name != file_name or not file_name.startswith(
        "famiverse-"
    ):
        raise BackupOperationError("Nom de fichier de sauvegarde invalide.")
    path = _backup_root() / file_name
    if path.is_symlink():
        raise BackupOperationError("Le fichier de sauvegarde ne peut pas être un lien symbolique.")
    return path


def _media_files():
    media_root = Path(settings.MEDIA_ROOT)
    if not media_root.exists():
        return []
    files = []
    for path in sorted(media_root.rglob("*")):
        if path.is_symlink():
            raise BackupOperationError("Le stockage média contient un lien symbolique.")
        if path.is_file():
            relative = path.relative_to(media_root).as_posix()
            files.append((path, relative, path.stat().st_size, _file_sha256(path)))
    return files


def _database_fixture():
    output = io.StringIO()
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        call_command(
            "dumpdata",
            natural_foreign=True,
            natural_primary=True,
            exclude=("contenttypes", "auth.permission", "sessions", "admin"),
            stdout=output,
            verbosity=0,
        )
    return output.getvalue().encode("utf-8")


def _runtime_config():
    database = settings.DATABASES["default"]
    return {
        "format_version": 1,
        "created_at": timezone.now().isoformat(),
        "django_version": django.get_version(),
        "database_engine": database["ENGINE"],
        "database_name": str(database.get("NAME", "")),
        "language_code": settings.LANGUAGE_CODE,
        "time_zone": settings.TIME_ZONE,
        "media_root": str(settings.MEDIA_ROOT),
        "migration_state": [
            list(migration)
            for migration in MigrationRecorder.Migration.objects.order_by(
                "app", "name"
            ).values_list("app", "name")
        ],
    }


def _prune_scheduled(family, retention_count):
    old_runs = BackupRun.objects.filter(
        family=family,
        kind=BackupRun.Kind.SCHEDULED,
        status=BackupRun.Status.COMPLETED,
    ).order_by("-created_at", "-pk")[retention_count:]
    for run in old_runs:
        path = _backup_path(run.file_name)
        if path.exists():
            try:
                path.unlink()
            except OSError:
                logger.exception("Impossible de supprimer l'ancienne sauvegarde %s", path)
                continue
        run.status = BackupRun.Status.PRUNED
        run.save(update_fields=("status",))


def create_backup(family, *, kind, created_by=None):
    require_single_family(family)
    if kind not in (
        BackupRun.Kind.MANUAL,
        BackupRun.Kind.SCHEDULED,
        BackupRun.Kind.PRE_RESTORE,
    ):
        raise BackupOperationError("Type de sauvegarde invalide.")

    root = _backup_root()
    temporary_path = None
    final_path = None
    try:
        _validate_storage_paths()
        root.mkdir(parents=True, exist_ok=True)
        database_payload = _database_fixture()
        media_files = _media_files()
        if len(media_files) + 3 > MAX_ARCHIVE_MEMBERS:
            raise BackupOperationError("La sauvegarde contient trop de fichiers média.")
        if sum(item[2] for item in media_files) + len(database_payload) > MAX_ARCHIVE_BYTES:
            raise BackupOperationError("Les données dépassent la taille maximale autorisée.")
        media_manifest = [
            {"path": relative, "size": size, "sha256": digest}
            for _, relative, size, digest in media_files
        ]
        manifest = {
            **_runtime_config(),
            "database_sha256": hashlib.sha256(database_payload).hexdigest(),
            "media_files": media_manifest,
        }
        manifest_payload = json.dumps(
            manifest, ensure_ascii=False, sort_keys=True
        ).encode("utf-8")
        if len(manifest_payload) > MAX_MANIFEST_BYTES:
            raise BackupOperationError("Le manifeste dépasse la taille maximale autorisée.")
        signature = signing.dumps(manifest, salt=SIGNING_SALT)
        stamp = timezone.now().strftime("%Y%m%dT%H%M%S%fZ")
        file_name = f"famiverse-{kind}-{stamp}.zip"
        final_path = root / file_name
        with tempfile.NamedTemporaryFile(
            prefix=".famiverse-", suffix=".tmp", dir=root, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        with zipfile.ZipFile(
            temporary_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as archive:
            archive.writestr("database.json", database_payload)
            archive.writestr("manifest.json", manifest_payload)
            archive.writestr("manifest.sig", signature.encode("ascii"))
            for path, relative, _, _ in media_files:
                archive.write(path, f"media/{relative}")
        if temporary_path.stat().st_size > MAX_ARCHIVE_BYTES:
            raise BackupOperationError("La sauvegarde dépasse la taille maximale autorisée.")
        verify_backup(temporary_path)
        os.replace(temporary_path, final_path)
        temporary_path = None
        try:
            os.chmod(final_path, 0o600)
        except OSError:
            logger.warning("Impossible de restreindre les permissions de %s", final_path)
        run = BackupRun.objects.create(
            family=family,
            kind=kind,
            status=BackupRun.Status.COMPLETED,
            file_name=file_name,
            sha256=_file_sha256(final_path),
            size_bytes=final_path.stat().st_size,
            actor_username=created_by.get_username() if created_by else "",
            created_by=created_by,
            completed_at=timezone.now(),
        )
        if kind == BackupRun.Kind.SCHEDULED:
            backup_settings = BackupSettings.objects.get_or_create(family=family)[0]
            _prune_scheduled(family, backup_settings.retention_count)
        return run
    except (
        BackupOperationError,
        OSError,
        DatabaseError,
        CommandError,
        TypeError,
        ValueError,
    ) as exc:
        if temporary_path and temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                logger.exception("Impossible de retirer le fichier temporaire %s", temporary_path)
        if final_path and final_path.exists():
            try:
                final_path.unlink()
            except OSError:
                logger.exception("Impossible de retirer le fichier temporaire %s", final_path)
        BackupRun.objects.create(
            family=family,
            kind=kind,
            status=BackupRun.Status.FAILED,
            error_message=str(exc)[:500],
            actor_username=created_by.get_username() if created_by else "",
            created_by=created_by,
            completed_at=timezone.now(),
        )
        if isinstance(exc, BackupOperationError):
            raise
        logger.exception("Échec de la sauvegarde FAMIVERSE.")
        raise BackupOperationError(
            "La sauvegarde a échoué ; consultez son journal."
        ) from exc


def import_backup(uploaded_file, family, *, actor):
    require_single_family(family)
    _validate_storage_paths()
    root = _backup_root()
    temporary_path = None
    final_path = None
    source_name = Path(uploaded_file.name).name[:255]
    actor_username = actor.get_username()
    try:
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=".famiverse-import-", suffix=".tmp", dir=root, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            size = 0
            for chunk in uploaded_file.chunks():
                size += len(chunk)
                if size > MAX_ARCHIVE_BYTES:
                    raise BackupOperationError(
                        "L'archive dépasse la taille maximale autorisée."
                    )
                temporary.write(chunk)
        manifest = verify_backup(temporary_path)
        if manifest.get("migration_state") != _runtime_config()["migration_state"]:
            raise BackupOperationError(
                "La version du schéma ne correspond pas à cette installation."
            )
        file_name = (
            f"famiverse-imported-{timezone.now().strftime('%Y%m%dT%H%M%S%fZ')}.zip"
        )
        final_path = root / file_name
        os.replace(temporary_path, final_path)
        temporary_path = None
        try:
            os.chmod(final_path, 0o600)
        except OSError:
            logger.warning("Impossible de restreindre les permissions de %s", final_path)
        return BackupRun.objects.create(
            family=family,
            kind=BackupRun.Kind.IMPORTED,
            status=BackupRun.Status.COMPLETED,
            file_name=file_name,
            source_file_name=source_name,
            sha256=_file_sha256(final_path),
            size_bytes=final_path.stat().st_size,
            actor_username=actor_username,
            created_by=actor,
            completed_at=timezone.now(),
        )
    except (
        BackupOperationError,
        OSError,
        DatabaseError,
        TypeError,
        ValueError,
        zipfile.BadZipFile,
    ) as exc:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()
        if final_path and final_path.exists():
            final_path.unlink()
        BackupRun.objects.create(
            family=family,
            kind=BackupRun.Kind.IMPORTED,
            status=BackupRun.Status.FAILED,
            source_file_name=source_name,
            error_message=str(exc)[:500],
            actor_username=actor_username,
            created_by=actor,
            completed_at=timezone.now(),
        )
        if isinstance(exc, BackupOperationError):
            raise
        logger.exception("Échec de l'import de sauvegarde FAMIVERSE.")
        raise BackupOperationError("L'archive n'a pas pu être importée.") from exc


def verify_backup(path, *, expected_sha256=""):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise BackupOperationError("Fichier de sauvegarde absent ou trop volumineux.")
    if expected_sha256 and _file_sha256(path) != expected_sha256:
        raise BackupOperationError("L'empreinte du fichier ne correspond pas au journal.")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            members = archive.infolist()
            if not 3 <= len(members) <= MAX_ARCHIVE_MEMBERS:
                raise BackupOperationError("Nombre de fichiers invalide dans la sauvegarde.")
            names = [member.filename for member in members]
            if len(names) != len(set(names)):
                raise BackupOperationError("La sauvegarde contient des chemins dupliqués.")
            total_size = 0
            for member in members:
                member_path = PurePosixPath(member.filename)
                mode = member.external_attr >> 16
                if (
                    member.filename.startswith("/")
                    or "\\" in member.filename
                    or ":" in member.filename
                    or "\x00" in member.filename
                    or str(member_path) != member.filename
                    or ".." in member_path.parts
                    or stat.S_ISLNK(mode)
                ):
                    raise BackupOperationError("Chemin non sûr dans la sauvegarde.")
                if member.filename not in (
                    "database.json",
                    "manifest.json",
                    "manifest.sig",
                ) and not member.filename.startswith("media/"):
                    raise BackupOperationError("Élément inattendu dans la sauvegarde.")
                total_size += member.file_size
                if total_size > MAX_ARCHIVE_BYTES:
                    raise BackupOperationError("Données décompressées trop volumineuses.")
            if archive.getinfo("manifest.json").file_size > MAX_MANIFEST_BYTES:
                raise BackupOperationError("Manifeste trop volumineux.")
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            if not isinstance(manifest, dict) or not isinstance(
                manifest.get("media_files"), list
            ):
                raise BackupOperationError("Structure de manifeste invalide.")
            if len(manifest["media_files"]) + 3 != len(members):
                raise BackupOperationError("Liste de fichiers média invalide.")
            for item in manifest["media_files"]:
                if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                    raise BackupOperationError("Entrée média invalide dans le manifeste.")
                relative = PurePosixPath(item["path"])
                if (
                    not item["path"]
                    or "\\" in item["path"]
                    or ":" in item["path"]
                    or "\x00" in item["path"]
                    or relative.is_absolute()
                    or str(relative) != item["path"]
                    or ".." in relative.parts
                    or not isinstance(item.get("size"), int)
                    or item["size"] < 0
                    or not isinstance(item.get("sha256"), str)
                    or len(item["sha256"]) != 64
                ):
                    raise BackupOperationError("Chemin ou empreinte média invalide.")
            signature = archive.read("manifest.sig").decode("ascii")
            signed_manifest = signing.loads(signature, salt=SIGNING_SALT)
            if signed_manifest != manifest or manifest.get("format_version") != 1:
                raise BackupOperationError("Signature ou version du manifeste invalide.")
            expected_names = {
                "database.json",
                "manifest.json",
                "manifest.sig",
                *(
                    f"media/{item['path']}"
                    for item in manifest.get("media_files", [])
                    if isinstance(item, dict)
                    and isinstance(item.get("path"), str)
                    and item.get("path")
                ),
            }
            if set(names) != expected_names:
                raise BackupOperationError("Le contenu ne correspond pas au manifeste.")
            database_digest = hashlib.sha256()
            with archive.open("database.json") as database_file:
                for chunk in iter(lambda: database_file.read(1024 * 1024), b""):
                    database_digest.update(chunk)
            if database_digest.hexdigest() != manifest.get("database_sha256"):
                raise BackupOperationError("L'intégrité de la base est invalide.")
            for item in manifest["media_files"]:
                member_name = f"media/{item['path']}"
                digest = hashlib.sha256()
                size = 0
                with archive.open(member_name) as media_file:
                    for chunk in iter(lambda: media_file.read(1024 * 1024), b""):
                        digest.update(chunk)
                        size += len(chunk)
                if size != item["size"] or digest.hexdigest() != item["sha256"]:
                    raise BackupOperationError(
                        f"L'intégrité du fichier média {item['path']} est invalide."
                    )
            json.loads(archive.read("database.json").decode("utf-8"))
            return manifest
    except (
        zipfile.BadZipFile,
        KeyError,
        AttributeError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        signing.BadSignature,
        zlib.error,
        OSError,
        ValueError,
    ) as exc:
        raise BackupOperationError("La sauvegarde est corrompue ou non vérifiable.") from exc


def _extract_media(archive, manifest, media_stage):
    for item in manifest["media_files"]:
        relative = PurePosixPath(item["path"])
        if relative.is_absolute() or ".." in relative.parts or "\\" in item["path"]:
            raise BackupOperationError("Chemin média non sûr.")
        target = media_stage.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(f"media/{item['path']}") as source, target.open("wb") as output:
            shutil.copyfileobj(source, output)


def _record_restore_failure(family, source_run, actor, error):
    BackupRun.objects.create(
        family=family,
        kind=BackupRun.Kind.RESTORE,
        status=BackupRun.Status.FAILED,
        source_file_name=source_run.file_name,
        sha256=source_run.sha256,
        size_bytes=source_run.size_bytes,
        error_message=str(error)[:500],
        actor_username=actor.get_username(),
        created_by=actor,
        completed_at=timezone.now(),
    )


def restore_backup(run, *, actor):
    family = run.family
    require_single_family(family)
    _validate_storage_paths()
    if run.status != BackupRun.Status.COMPLETED or run.kind not in (
        BackupRun.Kind.MANUAL,
        BackupRun.Kind.SCHEDULED,
        BackupRun.Kind.IMPORTED,
        BackupRun.Kind.PRE_RESTORE,
    ):
        raise BackupOperationError("Cette sauvegarde n'est pas restaurable.")
    try:
        source_path = _backup_path(run.file_name)
        manifest = verify_backup(source_path, expected_sha256=run.sha256)
        if manifest.get("migration_state") != _runtime_config()["migration_state"]:
            raise BackupOperationError(
                "La version du schéma ne correspond pas. Utilisez la version de "
                "l'application qui a créé cette sauvegarde."
            )
    except BackupOperationError as exc:
        _record_restore_failure(family, run, actor, exc)
        raise
    family_id = family.pk
    source_file_name = run.file_name
    source_sha256 = run.sha256
    source_size = run.size_bytes
    actor_username = actor.get_username()
    try:
        pre_restore = create_backup(
            family, kind=BackupRun.Kind.PRE_RESTORE, created_by=actor
        )
    except BackupOperationError as exc:
        _record_restore_failure(family, run, actor, exc)
        raise
    restore_run = BackupRun.objects.create(
        family=family,
        kind=BackupRun.Kind.RESTORE,
        status=BackupRun.Status.RUNNING,
        source_file_name=source_file_name,
        sha256=source_sha256,
        size_bytes=source_size,
        actor_username=actor_username,
        created_by=actor,
    )

    media_root = Path(settings.MEDIA_ROOT)
    media_root.parent.mkdir(parents=True, exist_ok=True)
    old_media = media_root.with_name(f"{media_root.name}.restore-{os.urandom(8).hex()}")
    media_replaced = False
    try:
        with tempfile.TemporaryDirectory(
            prefix="famiverse-restore-",
            dir=media_root.parent,
            ignore_cleanup_errors=True,
        ) as temporary_directory:
            temporary_root = Path(temporary_directory)
            media_stage = temporary_root / "media"
            media_stage.mkdir()
            fixture_path = temporary_root / "database.json"
            with zipfile.ZipFile(source_path, "r") as archive:
                _extract_media(archive, manifest, media_stage)
                with archive.open("database.json") as source, fixture_path.open("wb") as target:
                    shutil.copyfileobj(source, target)
            with transaction.atomic():
                call_command(
                    "flush",
                    interactive=False,
                    reset_sequences=False,
                    allow_cascade=True,
                    verbosity=0,
                )
                call_command("loaddata", str(fixture_path), verbosity=0)
                if media_root.exists():
                    os.replace(media_root, old_media)
                os.replace(media_stage, media_root)
                media_replaced = True
    except (
        BackupOperationError,
        OSError,
        DatabaseError,
        CommandError,
        ValueError,
        TypeError,
    ) as exc:
        recovery_error = None
        try:
            if media_replaced and media_root.exists():
                shutil.rmtree(media_root)
            if old_media.exists():
                os.replace(old_media, media_root)
        except OSError as recovery_exc:
            recovery_error = recovery_exc
            logger.exception("Échec de la récupération du dossier média après restauration.")
        restore_run.status = BackupRun.Status.FAILED
        restore_run.error_message = (
            "Récupération média à vérifier : " + str(recovery_error)[:300]
            if recovery_error
            else str(exc)[:500]
        )
        restore_run.completed_at = timezone.now()
        restore_run.save(
            update_fields=("status", "error_message", "completed_at")
        )
        if recovery_error:
            raise BackupOperationError(
                "La restauration a échoué et la récupération des médias nécessite une vérification."
            ) from recovery_error
        if isinstance(exc, BackupOperationError):
            raise
        logger.exception("Échec de la restauration FAMIVERSE.")
        raise BackupOperationError(
            "La restauration a échoué ; les données et médias actuels ont été conservés."
        ) from exc

    restored_family = Family.objects.get(pk=family_id)
    restored_actor = get_user_model().objects.filter(
        username=actor_username,
        family_id=family_id,
        role="parent",
    ).first()
    pre_restore_file_name = pre_restore.file_name
    if run.kind == BackupRun.Kind.IMPORTED:
        BackupRun.objects.get_or_create(
            family=restored_family,
            file_name=run.file_name,
            defaults={
                "kind": BackupRun.Kind.IMPORTED,
                "status": BackupRun.Status.COMPLETED,
                "source_file_name": run.source_file_name,
                "sha256": source_sha256,
                "size_bytes": source_size,
                "actor_username": actor_username,
                "created_by": restored_actor,
                "completed_at": run.completed_at,
            },
        )
    BackupRun.objects.get_or_create(
        family=restored_family,
        file_name=pre_restore_file_name,
        defaults={
            "kind": BackupRun.Kind.PRE_RESTORE,
            "status": BackupRun.Status.COMPLETED,
            "sha256": pre_restore.sha256,
            "size_bytes": pre_restore.size_bytes,
            "actor_username": actor_username,
            "created_by": restored_actor,
            "completed_at": pre_restore.completed_at,
        },
    )
    BackupSettings.objects.get_or_create(family=restored_family)
    restore_run = BackupRun.objects.create(
        family=restored_family,
        kind=BackupRun.Kind.RESTORE,
        status=BackupRun.Status.COMPLETED,
        source_file_name=source_file_name,
        sha256=source_sha256,
        size_bytes=source_size,
        actor_username=actor_username,
        created_by=restored_actor,
        completed_at=timezone.now(),
    )
    if old_media.exists():
        try:
            shutil.rmtree(old_media)
        except OSError as exc:
            logger.exception("Les anciens médias de restauration n'ont pas pu être retirés.")
            restore_run.error_message = str(exc)[:500]
            restore_run.save(update_fields=("error_message",))
    return restore_run
