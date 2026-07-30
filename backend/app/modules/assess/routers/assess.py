"""Boilerplate router for the Assess module.

Assess owns its own data model (kept separate from Diagnose's `diagnosis`
table per the module split) — fill in schema and endpoints as the Assess
flow is built out.
"""

import anyio
from uuid import UUID

from app.shared.auth import get_current_user
from app.shared.database import db_cursor
from app.shared.integrations.odk import ODKClient
from app.shared.integrations.odk.exceptions import ODKAuthFailed, ODKConnectionError, ODKAPIError
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()

_UPSERT_ASSESS_PROJECT = """
    INSERT INTO assess_projects (name, owner_id, odk_project_id, status)
    VALUES (%(name)s, %(owner_id)s, %(odk_project_id)s, 'active')
    ON CONFLICT (owner_id, odk_project_id)
    DO UPDATE SET
        name = EXCLUDED.name,
        updated_at = now()
    RETURNING id, name, odk_project_id
"""

_GET_ASSESS_PROJECT_ODK_ID = """
    SELECT odk_project_id
    FROM assess_projects
    WHERE id = %(project_id)s
      AND owner_id = %(owner_id)s
"""

_LIST_ASSESS_PROJECTS = """
    SELECT
        id,
        name,
        owner_id,
        description,
        status,
        odk_project_id,
        created_at,
        updated_at
    FROM assess_projects
    WHERE owner_id = %(owner_id)s
    ORDER BY created_at DESC
"""


def _assess_project_to_dict(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "owner_id": str(row["owner_id"]),
        "description": row["description"],
        "status": row["status"],
        "odk_project_id": row["odk_project_id"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


def _sync_projects_to_db(projects: list[dict], owner_id: str) -> list[dict]:
    """Blocking DB work — run off the event loop via anyio.to_thread."""
    synced = []
    with db_cursor() as cur:
        for project in projects:
            odk_id = str(project["id"])
            name = project.get("name") or f"ODK Project {odk_id}"
            cur.execute(
                _UPSERT_ASSESS_PROJECT,
                {"name": name, "owner_id": owner_id, "odk_project_id": odk_id},
            )
            synced.append(cur.fetchone())
    return synced


def _get_assess_project_odk_id(project_id: UUID, owner_id: str) -> dict | None:
    """Blocking DB lookup — run off the event loop via anyio.to_thread."""
    with db_cursor() as cur:
        cur.execute(
            _GET_ASSESS_PROJECT_ODK_ID,
            {"project_id": project_id, "owner_id": owner_id},
        )
        return cur.fetchone()


@router.get("/status")
def assess_status():
    return {"module": "assess", "status": "not_implemented"}


@router.get("/odk/projects")
async def odk_projects(user: dict = Depends(get_current_user)):
    """Fetch ODK Central projects and sync them into assess_projects.

    This endpoint is temporary and intended for manual verification only.
    """
    client = ODKClient()

    try:
        result = await client.get("/v1/projects")
    except ODKConnectionError:
        raise HTTPException(502, "Could not reach ODK Central. Try again later.")
    except ODKAuthFailed:
        raise HTTPException(502, "ODK Central authentication failed.")
    except ODKAPIError as exc:
        raise HTTPException(exc.status_code, "ODK API error")

    synced = await anyio.to_thread.run_sync(_sync_projects_to_db, result, user["id"])

    return {"ok": True, "data": result, "synced": synced}


@router.get("/projects")
def list_assess_projects(user: dict = Depends(get_current_user)):
    with db_cursor() as cur:
        cur.execute(_LIST_ASSESS_PROJECTS, {"owner_id": user["id"]})
        rows = cur.fetchall()
    return {"projects": [_assess_project_to_dict(r) for r in rows]}


@router.get("/projects/{project_id}/forms")
async def list_project_forms(project_id: UUID, user: dict = Depends(get_current_user)):
    row = await anyio.to_thread.run_sync(_get_assess_project_odk_id, project_id, user["id"])
    if not row:
        raise HTTPException(404, "Project not found")

    client = ODKClient()
    odk_project_id = row["odk_project_id"]

    try:
        result = await client.get(f"/v1/projects/{odk_project_id}/forms")
    except ODKConnectionError:
        raise HTTPException(502, "Could not reach ODK Central. Try again later.")
    except ODKAuthFailed:
        raise HTTPException(502, "ODK Central authentication failed.")
    except ODKAPIError as exc:
        raise HTTPException(exc.status_code, "ODK API error")

    return result


@router.get("/projects/{project_id}/forms/{xml_form_id}/submissions")
async def list_form_submissions(
    project_id: UUID,
    xml_form_id: str,
    user: dict = Depends(get_current_user),
):
    row = await anyio.to_thread.run_sync(_get_assess_project_odk_id, project_id, user["id"])
    if not row:
        raise HTTPException(404, "Project not found")

    client = ODKClient()
    odk_project_id = row["odk_project_id"]

    try:
        result = await client.get(
            f"/v1/projects/{odk_project_id}/forms/{xml_form_id}.svc/Submissions"
        )
    except ODKConnectionError:
        raise HTTPException(502, "Could not reach ODK Central. Try again later.")
    except ODKAuthFailed:
        raise HTTPException(502, "ODK Central authentication failed.")
    except ODKAPIError as exc:
        raise HTTPException(exc.status_code, "ODK API error")

    return result


@router.get("/projects/{project_id}/forms/{xml_form_id}/submissions/{instance_id}")
async def get_form_submission(
    project_id: UUID,
    xml_form_id: str,
    instance_id: str,
    user: dict = Depends(get_current_user),
):
    row = await anyio.to_thread.run_sync(_get_assess_project_odk_id, project_id, user["id"])
    if not row:
        raise HTTPException(404, "Project not found")

    client = ODKClient()
    odk_project_id = row["odk_project_id"]

    try:
        result = await client.get(
            f"/v1/projects/{odk_project_id}/forms/{xml_form_id}/submissions/{instance_id}"
        )
    except ODKConnectionError:
        raise HTTPException(502, "Could not reach ODK Central. Try again later.")
    except ODKAuthFailed:
        raise HTTPException(502, "ODK Central authentication failed.")
    except ODKAPIError as exc:
        raise HTTPException(exc.status_code, "ODK API error")

    return result