"""Remove orphaned S3 objects for projects."""

from __future__ import annotations

import logging
import re
import uuid

from app.shared.config import settings
from app.shared.database import db_cursor
from app.shared import s3_storage

logger = logging.getLogger(__name__)

_UUID_PREFIX_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _referenced_media_keys(project_id: str) -> set[str]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT photo_path, audio_path
            FROM field_notes
            WHERE project_id = %(project_id)s
              AND (photo_path IS NOT NULL OR audio_path IS NOT NULL)
            """,
            {"project_id": project_id},
        )
        rows = cur.fetchall()

    referenced: set[str] = set()
    for row in rows:
        for val in row.values():
            if val:
                referenced.add(val)
    return referenced


def _keys_byte_size(keys: list[str]) -> int:
    if not keys:
        return 0
    client = s3_storage.s3_client()
    total = 0
    for key in keys:
        try:
            head = client.head_object(Bucket=settings.aws_s3_bucket, Key=key)
            total += head.get("ContentLength", 0)
        except Exception:
            pass
    return total


def _active_project_ids() -> set[str]:
    with db_cursor() as cur:
        cur.execute("SELECT id::text AS id FROM diagnosis")
        return {row["id"] for row in cur.fetchall()}


def cleanup_project_s3(project_id: str, *, dry_run: bool = False) -> dict:
    """
    Delete orphaned media in {project_id}/media/ that is no longer referenced by field notes.

    Package artifacts are kept in sync via mirror upload during QField packaging; use
    cleanup_orphan_projects() for prefixes left behind after project deletion.
    """
    if not s3_storage.is_s3_enabled():
        return _empty_result(dry_run)

    referenced = _referenced_media_keys(project_id)
    to_delete: list[str] = []

    media_prefix = f"{project_id}/media/"
    for key in s3_storage.list_keys(media_prefix):
        if key not in referenced:
            to_delete.append(key)

    return _delete_keys_report(to_delete, dry_run=dry_run, label=f"project {project_id}")


def cleanup_orphan_projects(*, dry_run: bool = False) -> dict:
    """Delete entire S3 prefixes for project UUIDs that no longer exist in the database."""
    if not s3_storage.is_s3_enabled():
        return {**_empty_result(dry_run), "orphan_prefixes": []}

    active = _active_project_ids()
    to_delete_prefixes: list[str] = []
    orphan_keys: list[str] = []

    for prefix in s3_storage.list_top_level_prefixes():
        if not _UUID_PREFIX_RE.match(prefix):
            continue
        try:
            uuid.UUID(prefix)
        except ValueError:
            continue
        if prefix in active:
            continue
        to_delete_prefixes.append(prefix)
        orphan_keys.extend(s3_storage.list_keys(s3_storage.project_prefix(prefix)))

    if not orphan_keys:
        return {**_empty_result(dry_run), "orphan_prefixes": []}

    freed_bytes = _keys_byte_size(orphan_keys)
    if not dry_run:
        for prefix in to_delete_prefixes:
            s3_storage.delete_prefix(s3_storage.project_prefix(prefix))
        logger.info(
            "Removed %d orphan object(s) across %d deleted project prefix(es)",
            len(orphan_keys),
            len(to_delete_prefixes),
        )

    return {
        "deleted": len(orphan_keys) if not dry_run else 0,
        "would_delete": len(orphan_keys) if dry_run else 0,
        "freed_bytes": freed_bytes,
        "freed_kb": round(freed_bytes / 1024, 1),
        "dry_run": dry_run,
        "keys": orphan_keys,
        "orphan_prefixes": to_delete_prefixes,
    }


def _empty_result(dry_run: bool) -> dict:
    return {
        "deleted": 0,
        "would_delete": 0,
        "freed_bytes": 0,
        "freed_kb": 0.0,
        "dry_run": dry_run,
        "keys": [],
    }


def _delete_keys_report(keys: list[str], *, dry_run: bool, label: str) -> dict:
    if not keys:
        return _empty_result(dry_run)

    freed_bytes = _keys_byte_size(keys)
    if not dry_run:
        s3_storage.delete_keys(keys)
        logger.info("Cleaned up %d object(s) (%.1f KB) for %s", len(keys), freed_bytes / 1024, label)

    return {
        "deleted": len(keys) if not dry_run else 0,
        "would_delete": len(keys) if dry_run else 0,
        "freed_bytes": freed_bytes,
        "freed_kb": round(freed_bytes / 1024, 1),
        "dry_run": dry_run,
        "keys": keys,
    }
