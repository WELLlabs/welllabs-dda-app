"""Import field notes from QField Cloud offline GeoPackage and migrate media to S3."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from qfieldcloud_sdk import sdk

from app.shared.config import settings
from app.shared.database import db_cursor
from app.shared import s3_storage
from app.modules.diagnose.services.s3_cleanup import cleanup_project_s3

logger = logging.getLogger(__name__)

S3_MEDIA_KEY_RE = re.compile(r"^[0-9a-f-]{36}/media/")
ATTACHMENT_PREFIXES = ("DCIM/", "audio/", "video/", "photos/")


def is_cloud_media_path(path: str | None) -> bool:
    """True if path is already stored in S3 or legacy local photos/."""
    if not path:
        return True
    if path.startswith("photos/"):
        return True
    return bool(S3_MEDIA_KEY_RE.match(path))


def _normalize_note_id(raw: str | None) -> str:
    if not raw or not str(raw).strip():
        raise ValueError("Missing note_id")
    value = str(raw).strip().strip("{}")
    try:
        return str(uuid.UUID(value))
    except ValueError:
        if len(value) == 32 and re.fullmatch(r"[0-9a-f]+", value, re.I):
            return str(uuid.UUID(hex=value))
        raise ValueError(f"Invalid note_id: {raw}") from None


def _find_field_notes_gpkg(project_root: Path) -> Path | None:
    direct = project_root / "field_notes.gpkg"
    if direct.is_file():
        return direct
    matches = list(project_root.rglob("field_notes.gpkg"))
    return matches[0] if matches else None


def _resolve_media_path(existing: str | None, incoming: str | None) -> str | None:
    """
    Choose the right media path when merging GPKG data into the DB.
    - If DB already has an S3 key and QField still reports a relative path, keep the S3 key.
    - Otherwise use whatever the GPKG says (could be a new relative path that needs uploading).
    """
    if existing and is_cloud_media_path(existing) and incoming and not is_cloud_media_path(incoming):
        return existing
    return incoming


def _round_coords(obj, precision: int = 6):
    """Recursively round all floats in a GeoJSON coordinates structure."""
    if isinstance(obj, list):
        return [_round_coords(v, precision) for v in obj]
    if isinstance(obj, float):
        return round(obj, precision)
    return obj


def _geojson_eq(a: str, b: str) -> bool:
    """Loose equality: compare rounded coordinates, ignoring precision differences."""
    try:
        da, db = json.loads(a), json.loads(b)
        return _round_coords(da.get("coordinates")) == _round_coords(db.get("coordinates"))
    except (ValueError, AttributeError):
        return a == b


def import_field_notes_from_gpkg(project_id: str, project_root: Path) -> dict:
    """Upsert field notes from the QField offline GeoPackage into PostGIS."""
    gpkg_path = _find_field_notes_gpkg(project_root)
    if not gpkg_path:
        return {"imported": 0, "updated": 0, "skipped": 0}

    result = subprocess.run(
        ["ogr2ogr", "-f", "GeoJSON", "/vsistdout/", str(gpkg_path), "field_notes"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to read field_notes.gpkg: {result.stderr or result.stdout}")

    payload = json.loads(result.stdout)
    imported = 0
    updated = 0
    skipped = 0

    with db_cursor() as cur:
        for feature in payload.get("features", []):
            props = feature.get("properties") or {}
            try:
                note_id = _normalize_note_id(props.get("note_id"))
            except ValueError as exc:
                logger.warning("Skipping field note row: %s", exc)
                skipped += 1
                continue

            gpkg_project_id = str(props.get("project_id") or project_id).strip()
            if gpkg_project_id and gpkg_project_id != project_id:
                logger.warning("Skipping note %s for project %s", note_id, gpkg_project_id)
                skipped += 1
                continue

            geometry = feature.get("geometry")
            if not geometry:
                skipped += 1
                continue

            cur.execute(
                """
                SELECT ST_AsGeoJSON(geom)::text AS geojson, title, text, photo_path, audio_path, hypothesis_id
                FROM field_notes WHERE id = %(id)s
                """,
                {"id": note_id},
            )
            existing = cur.fetchone()
            exists = existing is not None

            incoming_title = props.get("title") or ""
            incoming_text = props.get("text") or ""
            incoming_hypothesis = props.get("hypothesis_id")
            if incoming_hypothesis is not None:
                incoming_hypothesis = str(incoming_hypothesis).strip() or None
            incoming_geojson = json.dumps(geometry)
            photo_path = _resolve_media_path(
                existing.get("photo_path") if existing else None,
                props.get("photo_path"),
            )
            audio_path = _resolve_media_path(
                existing.get("audio_path") if existing else None,
                props.get("audio_path"),
            )

            if incoming_hypothesis:
                cur.execute(
                    "SELECT 1 FROM hypotheses WHERE id = %(id)s AND project_id = %(project_id)s",
                    {"id": incoming_hypothesis, "project_id": project_id},
                )
                if not cur.fetchone():
                    logger.warning(
                        "Clearing invalid hypothesis_id %s on note %s",
                        incoming_hypothesis,
                        note_id,
                    )
                    incoming_hypothesis = None

            if exists:
                existing_hypothesis = (
                    str(existing["hypothesis_id"]) if existing.get("hypothesis_id") else None
                )
                # Skip write if nothing actually changed
                existing_geojson = existing.get("geojson") or ""
                no_change = (
                    (existing.get("title") or "") == incoming_title
                    and existing.get("text") == incoming_text
                    and existing_hypothesis == incoming_hypothesis
                    and photo_path == existing.get("photo_path")
                    and audio_path == existing.get("audio_path")
                    and _geojson_eq(existing_geojson, incoming_geojson)
                )
                if no_change:
                    skipped += 1
                    continue
                cur.execute(
                    """
                    UPDATE field_notes SET
                        geom          = ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326),
                        title         = %(title)s,
                        text          = %(text)s,
                        photo_path    = %(photo_path)s,
                        audio_path    = %(audio_path)s,
                        hypothesis_id = %(hypothesis_id)s,
                        updated_at    = now()
                    WHERE id = %(id)s AND project_id = %(project_id)s
                    """,
                    {
                        "id": note_id,
                        "project_id": project_id,
                        "geojson": incoming_geojson,
                        "title": incoming_title,
                        "text": incoming_text,
                        "photo_path": photo_path,
                        "audio_path": audio_path,
                        "hypothesis_id": incoming_hypothesis,
                    },
                )
                updated += 1
            else:
                cur.execute(
                    """
                    INSERT INTO field_notes (
                        id, project_id, geom, title, text, photo_path, audio_path, hypothesis_id
                    )
                    VALUES (
                        %(id)s,
                        %(project_id)s,
                        ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326),
                        %(title)s,
                        %(text)s,
                        %(photo_path)s,
                        %(audio_path)s,
                        %(hypothesis_id)s
                    )
                    """,
                    {
                        "id": note_id,
                        "project_id": project_id,
                        "geojson": incoming_geojson,
                        "title": incoming_title,
                        "text": incoming_text,
                        "photo_path": photo_path,
                        "audio_path": audio_path,
                        "hypothesis_id": incoming_hypothesis,
                    },
                )
                imported += 1

    return {"imported": imported, "updated": updated, "skipped": skipped}


def _normalize_relative_path(path: str) -> str:
    return path.lstrip("./").replace("\\", "/")


def _find_attachment_file(project_root: Path, relative_path: str) -> Path | None:
    rel = _normalize_relative_path(relative_path)
    candidates = [
        project_root / rel,
        project_root / Path(rel).name,
    ]
    for prefix in ATTACHMENT_PREFIXES:
        if rel.startswith(prefix):
            continue
        candidates.append(project_root / prefix / Path(rel).name)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _upload_attachment(project_id: str, local_file: Path) -> str:
    ext = local_file.suffix or ""
    filename = f"{uuid.uuid4()}{ext}"
    key = s3_storage.media_key(project_id, filename)
    s3_storage.upload_file(local_file, key)
    return key


def migrate_field_note_media(project_id: str, project_root: Path) -> dict:
    """Upload relative attachment paths to S3 and update field_notes rows.

    Returns ``pending_paths`` — relative paths that couldn't be resolved to a
    local file.  The caller can retry the download and call this function again;
    notes already migrated to S3 will be skipped on the second pass.
    """
    updated_photos = 0
    updated_audio = 0
    skipped = 0
    pending_paths: list[str] = []

    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, photo_path, audio_path
            FROM field_notes
            WHERE project_id = %(project_id)s
            """,
            {"project_id": project_id},
        )
        rows = cur.fetchall()

    for row in rows:
        updates: dict[str, str] = {}
        for column, counter_name in (("photo_path", "photo"), ("audio_path", "audio")):
            path = row.get(column)
            if not path:
                continue
            if is_cloud_media_path(path):
                if s3_storage.object_exists(path):
                    continue
                logger.warning("Cloud media missing in S3 for %s: %s", row["id"], path)
            local_file = _find_attachment_file(project_root, path)
            if not local_file:
                if not is_cloud_media_path(path):
                    # File should have been downloaded but wasn't — track for retry
                    logger.warning(
                        "Attachment not found after download for note %s (%s): %s",
                        row["id"],
                        column,
                        path,
                    )
                    pending_paths.append(path)
                skipped += 1
                continue
            try:
                new_key = _upload_attachment(project_id, local_file)
                updates[column] = new_key
                if counter_name == "photo":
                    updated_photos += 1
                else:
                    updated_audio += 1
            except Exception as exc:
                logger.warning("Failed to upload %s for note %s: %s", column, row["id"], exc)
                skipped += 1

        if updates:
            sets = ", ".join(f"{col} = %({col})s" for col in updates)
            params = {"id": row["id"], **updates}
            with db_cursor() as cur:
                cur.execute(f"UPDATE field_notes SET {sets} WHERE id = %(id)s", params)

    return {
        "photos_uploaded": updated_photos,
        "audio_uploaded": updated_audio,
        "skipped": skipped,
        "pending_paths": pending_paths,
    }


def _qfield_project_name(row: dict) -> str:
    return f"{settings.qfield_project_name}-{row['name']}".replace(" ", "-")[:80]


def _find_qfield_project(client: sdk.Client, name: str) -> dict:
    for project in client.list_projects():
        if project["name"] == name:
            return project
    raise ValueError(f"QField Cloud project not found: {name}. Package to QField first.")


def _resolve_qfield_token(user_id: str, project_id: str) -> str:
    """Return a QField Cloud token for sync: the user's own, or the project owner's."""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT qfield_token AS token FROM users
            WHERE id = %(uid)s AND qfield_token IS NOT NULL AND qfield_token <> ''
            """,
            {"uid": user_id},
        )
        row = cur.fetchone()
        if row:
            return row["token"]

        cur.execute(
            """
            SELECT u.qfield_token AS token FROM diagnosis d
            JOIN users u ON u.id = d.qfield_project_owner
            WHERE d.id = %(pid)s
              AND u.qfield_token IS NOT NULL
              AND u.qfield_token <> ''
            """,
            {"pid": project_id},
        )
        fallback = cur.fetchone()
        if fallback:
            return fallback["token"]

    raise ValueError(
        "Connect your QField Cloud account in Profile settings first."
    )


def sync_from_cloud(project_id: str, user_id: str, progress=None) -> dict:
    """
    After QField pushes offline edits to QField Cloud:
    1. Download project files (field_notes.gpkg + attachments)
    2. Import field notes from GeoPackage into PostGIS
    3. Upload relative media paths to S3 and update DB keys
    """
    def step(percent: int, message: str) -> None:
        if progress:
            progress.emit(percent, message)

    qfield_token = _resolve_qfield_token(user_id, project_id)

    step(5, "Loading project from database…")
    with db_cursor() as cur:
        cur.execute("SELECT name, watershed_name FROM diagnosis WHERE id = %(id)s", {"id": project_id})
        row = cur.fetchone()
    if not row:
        raise ValueError("Project not found")

    step(10, "Connecting to QField Cloud…")
    client = sdk.Client(url=settings.qfield_cloud_url, token=qfield_token)
    qfc_name = _qfield_project_name(row)
    qfc_project = _find_qfield_project(client, qfc_name)
    qfc_id = qfc_project["id"]
    step(15, f"QField project: {qfc_name}")

    def _fetch_and_download(tmp: str, log_prefix: str = "") -> list:
        """Re-fetch the remote file list and download everything.

        We always re-list rather than caching, because QField Cloud may still
        be processing the push when the first list call happens — attachment
        files that aren't indexed yet simply won't appear in a stale list.
        """
        files = client.list_remote_files(qfc_id)
        if files:
            if progress:
                progress.log(f"{log_prefix}Downloading {len(files)} file(s) from QField Cloud…")
            client.download_files(
                files,
                qfc_id,
                sdk.FileTransferType.PROJECT,
                tmp,
                filter_glob="*",
                throw_on_error=False,
                show_progress=False,
                force_download=True,
            )
        return files

    step(20, "Fetching file list from QField Cloud…")
    remote_files = client.list_remote_files(qfc_id)
    if not remote_files:
        step(100, "No files on QField Cloud yet.")
        return {
            "status": "synced",
            "message": "No files on QField Cloud yet. Push changes from the QField app first.",
            "photos_uploaded": 0,
            "audio_uploaded": 0,
            "skipped": 0,
        }

    with tempfile.TemporaryDirectory() as tmp:
        step(25, f"Downloading {len(remote_files)} file(s)…")
        _fetch_and_download(tmp)

        step(45, "Importing field notes from GeoPackage…")
        project_root = Path(tmp)
        note_stats = import_field_notes_from_gpkg(project_id, project_root)
        step(
            60,
            f"Notes: {note_stats['imported']} new, "
            f"{note_stats['updated']} updated, "
            f"{note_stats['skipped']} unchanged",
        )

        step(65, "Uploading media attachments to S3…")
        media_stats = migrate_field_note_media(project_id, project_root)

        # If any attachment files were missing, QField Cloud may still have been
        # indexing the push. Wait briefly, re-fetch the file list, and retry once.
        if media_stats.get("pending_paths"):
            missing = media_stats["pending_paths"]
            logger.info(
                "Attachment(s) missing after first download (%d), waiting 4 s "
                "then re-fetching file list from QField Cloud: %s",
                len(missing),
                missing,
            )
            step(
                70,
                f"{len(missing)} attachment(s) not found — waiting for QField Cloud to finish indexing…",
            )
            time.sleep(4)
            step(75, "Retrying download with fresh file list…")
            _fetch_and_download(tmp, log_prefix="[retry] ")
            retry_stats = migrate_field_note_media(project_id, project_root)
            # Notes already in S3 are skipped on the second pass; just accumulate new uploads.
            media_stats = {
                "photos_uploaded": media_stats["photos_uploaded"] + retry_stats["photos_uploaded"],
                "audio_uploaded": media_stats["audio_uploaded"] + retry_stats["audio_uploaded"],
                "skipped": retry_stats["skipped"],
                "pending_paths": retry_stats.get("pending_paths", []),
            }

    total_media = media_stats["photos_uploaded"] + media_stats["audio_uploaded"]
    still_pending = len(media_stats.get("pending_paths", []))

    step(90, f"Uploaded {total_media} media file(s) to S3")

    step(95, "Running S3 cleanup…")
    cleanup_stats = cleanup_project_s3(project_id)
    if cleanup_stats.get("deleted"):
        logger.info(
            "S3 cleanup after sync: removed %d object(s), freed %.1f KB",
            cleanup_stats["deleted"],
            cleanup_stats.get("freed_kb", 0),
        )
        if progress:
            progress.log(
                f"S3 cleanup: removed {cleanup_stats['deleted']} orphaned object(s), "
                f"freed {cleanup_stats.get('freed_kb', 0):.0f} KB"
            )

    message_parts = [
        "Synced from QField Cloud.",
        f"{note_stats['imported']} new field note(s) added,",
        f"{note_stats['updated']} updated,",
        f"{note_stats['skipped']} unchanged.",
        f"{total_media} media file(s) moved to S3.",
    ]
    if still_pending:
        message_parts.append(
            f"{still_pending} attachment(s) could not be downloaded from QField Cloud "
            "— sync again to retry."
        )

    step(100, message_parts[0] + " " + " ".join(message_parts[1:]))

    return {
        "status": "synced",
        "qfield_project_id": qfc_id,
        "qfield_project_name": qfc_name,
        **note_stats,
        **{k: v for k, v in media_stats.items() if k != "pending_paths"},
        "pending_media": still_pending,
        "message": " ".join(message_parts),
    }
