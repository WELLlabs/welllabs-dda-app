#!/usr/bin/env python3
"""Delete all forms in ODK Central project 17 and clear local mel_forms rows."""

from __future__ import annotations

import asyncio
import sys

from app.shared.config import settings
from app.shared.database import db_cursor, init_pool, close_pool
from app.shared.integrations.odk import ODKClient
from app.shared.integrations.odk.exceptions import ODKAPIError


async def delete_odk_forms(project_id: int) -> int:
    client = ODKClient()
    forms = await client.get(f"/v1/projects/{project_id}/forms")
    if not isinstance(forms, list):
        print(f"Unexpected forms response: {forms!r}", file=sys.stderr)
        return 0

    deleted = 0
    for form in forms:
        xml_form_id = form.get("xmlFormId") or form.get("xmlFormID")
        if not xml_form_id:
            continue
        try:
            await client.delete(f"/v1/projects/{project_id}/forms/{xml_form_id}")
            deleted += 1
            print(f"Deleted ODK form: {xml_form_id}")
        except ODKAPIError as exc:
            print(f"Failed to delete {xml_form_id}: {exc}", file=sys.stderr)
    return deleted


def clear_local_mel_forms() -> int:
    with db_cursor() as cur:
        cur.execute("DELETE FROM mel_forms RETURNING id")
        rows = cur.fetchall()
    return len(rows or [])


async def main() -> None:
    project_id = int(settings.odk_project_id or 17)
    print(f"ODK base: {settings.odk_base_url}")
    print(f"Deleting all forms in ODK project {project_id}…")
    init_pool()
    try:
        deleted = await delete_odk_forms(project_id)
        print(f"Deleted {deleted} ODK form(s).")
        cleared = clear_local_mel_forms()
        print(f"Cleared {cleared} local mel_forms row(s).")
    finally:
        close_pool()


if __name__ == "__main__":
    asyncio.run(main())
