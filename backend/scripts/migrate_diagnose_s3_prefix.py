#!/usr/bin/env python3
"""Move diagnose project folders from bucket root to diagnose/ prefix.

Usage:
  cd backend && python -m scripts.migrate_diagnose_s3_prefix [--dry-run] [--delete-legacy]

Copies {project_uuid}/... to diagnose/{project_uuid}/..., updates field_notes paths,
and optionally deletes the legacy prefixes.
"""

from __future__ import annotations

import argparse
import logging
import sys

from app.shared import s3_storage
from app.shared.config import settings
from app.shared.database import close_pool, db_cursor, init_pool

logger = logging.getLogger(__name__)


def _rewrite_db_media_paths(*, dry_run: bool) -> int:
    root = s3_storage.diagnose_root_prefix()
    if not root:
        return 0
    updated = 0
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, photo_path, audio_path
            FROM field_notes
            WHERE (photo_path IS NOT NULL AND photo_path NOT LIKE %(root)s)
               OR (audio_path IS NOT NULL AND audio_path NOT LIKE %(root)s)
            """,
            {"root": f"{root}%"},
        )
        rows = cur.fetchall()
        for row in rows:
            photo = row["photo_path"]
            audio = row["audio_path"]
            new_photo = s3_storage.canonicalize_diagnose_key(photo) if photo else photo
            new_audio = s3_storage.canonicalize_diagnose_key(audio) if audio else audio
            if new_photo == photo and new_audio == audio:
                continue
            updated += 1
            if dry_run:
                logger.info(
                    "Would update field_note %s paths photo=%s audio=%s",
                    row["id"],
                    new_photo,
                    new_audio,
                )
                continue
            cur.execute(
                """
                UPDATE field_notes
                SET photo_path = %(photo)s, audio_path = %(audio)s
                WHERE id = %(id)s
                """,
                {"id": row["id"], "photo": new_photo, "audio": new_audio},
            )
    return updated


def _copy_legacy_projects(*, dry_run: bool, delete_legacy: bool) -> tuple[int, int]:
    if not s3_storage.is_s3_enabled():
        raise RuntimeError("AWS_S3_BUCKET is not configured")

    client = s3_storage.s3_client()
    bucket = settings.aws_s3_bucket
    copied = 0
    deleted = 0

    for project_id in s3_storage.list_legacy_project_ids():
        legacy_prefix = s3_storage.legacy_project_prefix(project_id)
        target_prefix = s3_storage.project_prefix(project_id)
        keys = s3_storage.list_keys(legacy_prefix)
        if not keys:
            continue
        logger.info("Project %s: %d object(s) to migrate", project_id, len(keys))
        for key in keys:
            rel = key[len(legacy_prefix) :]
            dest = f"{target_prefix}{rel}"
            if dry_run:
                logger.info("Would copy s3://%s/%s -> s3://%s/%s", bucket, key, bucket, dest)
                copied += 1
                continue
            client.copy_object(
                Bucket=bucket,
                CopySource={"Bucket": bucket, "Key": key},
                Key=dest,
            )
            copied += 1
        if delete_legacy and not dry_run:
            deleted += s3_storage.delete_prefix(legacy_prefix)

    return copied, deleted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Log actions without writing")
    parser.add_argument(
        "--delete-legacy",
        action="store_true",
        help="Delete legacy {uuid}/ prefixes after successful copy",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    init_pool(min_size=1, max_size=2)
    try:
        copied, deleted = _copy_legacy_projects(dry_run=args.dry_run, delete_legacy=args.delete_legacy)
        db_updates = _rewrite_db_media_paths(dry_run=args.dry_run)
    finally:
        close_pool()

    logger.info(
        "Done: copied=%d deleted_legacy_objects=%d db_path_updates=%d dry_run=%s",
        copied,
        deleted,
        db_updates,
        args.dry_run,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
