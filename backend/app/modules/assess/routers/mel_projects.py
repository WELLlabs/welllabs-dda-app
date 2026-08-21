"""MEL project + plan CRUD — project owns many one-intervention plans."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException

from app.modules.assess.access import (
    assess_access_where,
    get_mel_plan,
    get_mel_project,
    mel_plan_to_dict,
    mel_project_to_dict,
    require_assess_access,
    require_assess_admin,
    require_assess_owner,
)
from app.modules.assess.services.collect_qr import build_mel_collect_qr
from app.modules.assess.services.mel_catalog import get_intervention
from app.modules.assess.services.odk_submissions import normalize_submissions
from app.shared.auth import get_current_user
from app.shared.config import settings
from app.shared.database import db_cursor
from app.shared.integrations.odk import ODKClient
from app.shared.integrations.odk.exceptions import ODKAPIError, ODKAuthFailed, ODKConnectionError

router = APIRouter(prefix="/mel/projects", tags=["assess:mel-projects"])


class MelProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)


class MelPlanCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    intervention_slug: str = Field(..., min_length=1, max_length=120)


class MelPlanSave(BaseModel):
    outcome_ids: list[str] = Field(default_factory=list)
    plan_json: dict | None = None


def _form_dict(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "planId": str(row["plan_id"]) if row.get("plan_id") else None,
        "xmlFormId": row["xml_form_id"],
        "name": row["name"],
        "packageId": row.get("package_id"),
        "packageTitle": row.get("package_title"),
        "createdBy": str(row["created_by"]) if row.get("created_by") else None,
        "createdByName": row.get("created_by_name") or "",
        "createdAt": row["created_at"].isoformat(),
    }


@router.get("")
def list_mel_projects(user: dict = Depends(get_current_user)):
    with db_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                p.id,
                p.name,
                p.owner_id,
                p.description,
                p.status,
                p.kind,
                p.created_at,
                p.updated_at,
                owner_u.name AS owner_name,
                owner_u.email AS owner_email,
                (
                    SELECT COUNT(*)::int FROM mel_plans mp WHERE mp.project_id = p.id
                ) AS plan_count,
                (
                    SELECT COUNT(*)::int FROM mel_forms mf WHERE mf.project_id = p.id
                ) AS form_count
            FROM assess_projects p
            LEFT JOIN users owner_u ON owner_u.id = p.owner_id
            WHERE p.kind = 'mel'
              AND ({assess_access_where("p")})
            ORDER BY p.updated_at DESC
            """,
            {"current_user_id": user["id"]},
        )
        rows = cur.fetchall()
    return {"projects": [mel_project_to_dict(row) for row in rows]}


@router.post("", status_code=201)
def create_mel_project(body: MelProjectCreate, user: dict = Depends(get_current_user)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Name is required")

    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO assess_projects (
                name, owner_id, description, status, kind
            )
            VALUES (
                %(name)s, %(owner_id)s, %(description)s, 'active', 'mel'
            )
            RETURNING
                id, name, owner_id, description, status, kind, created_at, updated_at
            """,
            {
                "name": name,
                "owner_id": user["id"],
                "description": (body.description or "").strip(),
            },
        )
        row = cur.fetchone()

    row = {
        **row,
        "owner_name": user.get("name") or "",
        "owner_email": user.get("email") or "",
        "plan_count": 0,
        "form_count": 0,
    }
    return mel_project_to_dict(row)


@router.get("/{project_id}")
def get_mel_project_detail(project_id: str, user: dict = Depends(require_assess_access)):
    return mel_project_to_dict(get_mel_project(project_id))


@router.delete("/{project_id}", status_code=204)
def delete_mel_project(project_id: str, user: dict = Depends(require_assess_owner)):
    get_mel_project(project_id)
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM assess_projects WHERE id = %(id)s AND kind = 'mel' RETURNING id",
            {"id": project_id},
        )
        if not cur.fetchone():
            raise HTTPException(404, "MEL project not found")


@router.get("/{project_id}/plans")
def list_mel_plans(project_id: str, user: dict = Depends(require_assess_access)):
    get_mel_project(project_id)
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT
                mp.id,
                mp.project_id,
                mp.name,
                mp.intervention_slug,
                mp.plan_json,
                mp.created_by,
                mp.created_at,
                mp.updated_at,
                (
                    SELECT COUNT(*)::int FROM mel_forms mf WHERE mf.plan_id = mp.id
                ) AS form_count
            FROM mel_plans mp
            WHERE mp.project_id = %(project_id)s
            ORDER BY mp.updated_at DESC
            """,
            {"project_id": project_id},
        )
        rows = cur.fetchall()
    return {"plans": [mel_plan_to_dict(row) for row in rows]}


@router.post("/{project_id}/plans", status_code=201)
def create_mel_plan(
    project_id: str,
    body: MelPlanCreate,
    user: dict = Depends(require_assess_access),
):
    get_mel_project(project_id)
    intervention = get_intervention(body.intervention_slug)
    if intervention is None:
        raise HTTPException(404, "Intervention not found in catalog")

    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Name is required")

    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO mel_plans (
                project_id, name, intervention_slug, created_by
            )
            VALUES (
                %(project_id)s, %(name)s, %(intervention_slug)s, %(created_by)s
            )
            RETURNING
                id, project_id, name, intervention_slug, plan_json,
                created_by, created_at, updated_at
            """,
            {
                "project_id": project_id,
                "name": name,
                "intervention_slug": body.intervention_slug,
                "created_by": user["id"],
            },
        )
        row = cur.fetchone()
        cur.execute(
            "UPDATE assess_projects SET updated_at = now() WHERE id = %(id)s",
            {"id": project_id},
        )

    row = {**row, "form_count": 0}
    return mel_plan_to_dict(row)


@router.get("/{project_id}/plans/{plan_id}")
def get_mel_plan_detail(
    project_id: str, plan_id: str, user: dict = Depends(require_assess_access)
):
    get_mel_project(project_id)
    return mel_plan_to_dict(get_mel_plan(plan_id, project_id=project_id))


@router.patch("/{project_id}/plans/{plan_id}")
def save_mel_plan(
    project_id: str,
    plan_id: str,
    body: MelPlanSave,
    user: dict = Depends(require_assess_access),
):
    get_mel_project(project_id)
    get_mel_plan(plan_id, project_id=project_id)
    plan_json = body.plan_json if body.plan_json is not None else {"outcome_ids": body.outcome_ids}
    if "outcome_ids" not in plan_json:
        plan_json = {**plan_json, "outcome_ids": body.outcome_ids}

    with db_cursor() as cur:
        cur.execute(
            """
            UPDATE mel_plans
            SET plan_json = %(plan_json)s::jsonb, updated_at = now()
            WHERE id = %(id)s AND project_id = %(project_id)s
            RETURNING id
            """,
            {
                "id": plan_id,
                "project_id": project_id,
                "plan_json": json.dumps(plan_json),
            },
        )
        if not cur.fetchone():
            raise HTTPException(404, "MEL plan not found")
        cur.execute(
            "UPDATE assess_projects SET updated_at = now() WHERE id = %(id)s",
            {"id": project_id},
        )
    return mel_plan_to_dict(get_mel_plan(plan_id, project_id=project_id))


@router.delete("/{project_id}/plans/{plan_id}", status_code=204)
def delete_mel_plan(
    project_id: str, plan_id: str, user: dict = Depends(require_assess_access)
):
    get_mel_project(project_id)
    get_mel_plan(plan_id, project_id=project_id)
    with db_cursor() as cur:
        cur.execute(
            """
            DELETE FROM mel_plans
            WHERE id = %(id)s AND project_id = %(project_id)s
            RETURNING id
            """,
            {"id": plan_id, "project_id": project_id},
        )
        if not cur.fetchone():
            raise HTTPException(404, "MEL plan not found")
        cur.execute(
            "UPDATE assess_projects SET updated_at = now() WHERE id = %(id)s",
            {"id": project_id},
        )


@router.get("/{project_id}/plans/{plan_id}/forms")
def list_mel_plan_forms(
    project_id: str, plan_id: str, user: dict = Depends(require_assess_access)
):
    get_mel_project(project_id)
    get_mel_plan(plan_id, project_id=project_id)
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT
                mf.id,
                mf.plan_id,
                mf.xml_form_id,
                mf.name,
                mf.package_id,
                mf.package_title,
                mf.created_by,
                mf.created_at,
                u.name AS created_by_name
            FROM mel_forms mf
            LEFT JOIN users u ON u.id = mf.created_by
            WHERE mf.plan_id = %(plan_id)s AND mf.project_id = %(project_id)s
            ORDER BY mf.created_at DESC
            """,
            {"plan_id": plan_id, "project_id": project_id},
        )
        rows = cur.fetchall()
    return {"projectId": project_id, "planId": plan_id, "forms": [_form_dict(r) for r in rows]}


@router.get("/{project_id}/forms")
def list_mel_project_forms(project_id: str, user: dict = Depends(require_assess_access)):
    get_mel_project(project_id)
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT
                mf.id,
                mf.plan_id,
                mf.xml_form_id,
                mf.name,
                mf.package_id,
                mf.package_title,
                mf.created_by,
                mf.created_at,
                u.name AS created_by_name,
                mp.name AS plan_name,
                mp.intervention_slug
            FROM mel_forms mf
            LEFT JOIN users u ON u.id = mf.created_by
            LEFT JOIN mel_plans mp ON mp.id = mf.plan_id
            WHERE mf.project_id = %(project_id)s
            ORDER BY mf.created_at DESC
            """,
            {"project_id": project_id},
        )
        rows = cur.fetchall()
    return {
        "projectId": project_id,
        "forms": [
            {
                **_form_dict(r),
                "planName": r.get("plan_name") or "",
                "interventionSlug": r.get("intervention_slug") or "",
            }
            for r in rows
        ],
    }


async def _fetch_all_odata_submissions(client: ODKClient, odk_project_id: int, xml_form_id: str) -> list[dict]:
    """Page OData Submissions until exhausted (cap pages for safety)."""
    path = f"/v1/projects/{odk_project_id}/forms/{xml_form_id}.svc/Submissions"
    rows: list[dict] = []
    skip = 0
    page_size = 500
    max_pages = 40
    for _ in range(max_pages):
        payload = await client.get(path, params={"$top": page_size, "$skip": skip})
        if not isinstance(payload, dict):
            break
        batch = payload.get("value")
        if not isinstance(batch, list):
            break
        rows.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < page_size:
            break
        skip += page_size
    return rows


@router.get("/{project_id}/plans/{plan_id}/forms/{xml_form_id}/submissions")
async def list_mel_form_submissions(
    project_id: str,
    plan_id: str,
    xml_form_id: str,
    user: dict = Depends(require_assess_access),
):
    """Fetch normalized ODK submissions for a MEL form from configured ODK_PROJECT_ID only."""
    if settings.odk_project_id is None:
        raise HTTPException(503, "ODK_PROJECT_ID is not configured")

    get_mel_project(project_id)
    get_mel_plan(plan_id, project_id=project_id)

    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, xml_form_id, name
            FROM mel_forms
            WHERE project_id = %(project_id)s
              AND plan_id = %(plan_id)s
              AND xml_form_id = %(xml_form_id)s
            """,
            {
                "project_id": project_id,
                "plan_id": plan_id,
                "xml_form_id": xml_form_id,
            },
        )
        form_row = cur.fetchone()
    if not form_row:
        raise HTTPException(404, "Form not found on this MEL plan")

    client = ODKClient()
    odk_project_id = int(settings.odk_project_id)
    try:
        odata_rows = await _fetch_all_odata_submissions(client, odk_project_id, xml_form_id)
    except ODKConnectionError:
        raise HTTPException(502, "Could not reach ODK Central. Try again later.")
    except ODKAuthFailed:
        raise HTTPException(502, "ODK Central authentication failed.")
    except ODKAPIError as exc:
        raise HTTPException(exc.status_code, f"ODK API error: {exc}")

    normalized = normalize_submissions(odata_rows)
    return {
        "projectId": project_id,
        "planId": plan_id,
        "xmlFormId": xml_form_id,
        "formName": form_row["name"],
        "odkProjectId": odk_project_id,
        **normalized,
    }


@router.get("/{project_id}/plans/{plan_id}/forms/{xml_form_id}/collect-qr")
async def get_mel_form_collect_qr(
    project_id: str,
    plan_id: str,
    xml_form_id: str,
    user: dict = Depends(require_assess_access),
):
    """Return an ODK Collect QR payload for a published MEL form."""
    if settings.odk_project_id is None:
        raise HTTPException(503, "ODK_PROJECT_ID is not configured")
    if not settings.odk_base_url:
        raise HTTPException(503, "ODK_BASE_URL is not configured")

    project = get_mel_project(project_id)
    get_mel_plan(plan_id, project_id=project_id)

    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, xml_form_id, name, package_title
            FROM mel_forms
            WHERE project_id = %(project_id)s
              AND plan_id = %(plan_id)s
              AND xml_form_id = %(xml_form_id)s
            """,
            {
                "project_id": project_id,
                "plan_id": plan_id,
                "xml_form_id": xml_form_id,
            },
        )
        form_row = cur.fetchone()
    if not form_row:
        raise HTTPException(404, "Form not found on this MEL plan")

    client = ODKClient()
    odk_project_id = int(settings.odk_project_id)
    try:
        collect_qr = await build_mel_collect_qr(
            client,
            odk_project_id=odk_project_id,
            project_name=project.get("name") or "WELL Labs MEL",
            xml_form_ids=[xml_form_id],
        )
    except ODKConnectionError:
        raise HTTPException(502, "Could not reach ODK Central. Try again later.")
    except ODKAuthFailed:
        raise HTTPException(502, "ODK Central authentication failed.")
    except ODKAPIError as exc:
        raise HTTPException(exc.status_code, f"ODK API error: {exc}")

    return {
        "projectId": project_id,
        "planId": plan_id,
        "xmlFormId": xml_form_id,
        "formName": form_row["name"],
        "packageTitle": form_row.get("package_title") or "",
        "collectQr": collect_qr,
    }


# --- Access management ---


class AddUserAccess(BaseModel):
    email: str
    role: str = "member"


class UpdateUserRole(BaseModel):
    role: str


@router.get("/{project_id}/access/users")
def list_user_access(project_id: str, user: dict = Depends(require_assess_admin)):
    get_mel_project(project_id)
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT u.id, u.email, u.name, apu.role, apu.created_at
            FROM assess_project_users apu
            JOIN users u ON u.id = apu.user_id
            WHERE apu.project_id = %(id)s
            ORDER BY apu.created_at ASC
            """,
            {"id": project_id},
        )
        rows = cur.fetchall()
        cur.execute(
            """
            SELECT id, email, name FROM users
            WHERE id = (SELECT owner_id FROM assess_projects WHERE id = %(id)s)
            """,
            {"id": project_id},
        )
        owner = cur.fetchone()
    return {
        "owner": (
            {
                "id": str(owner["id"]),
                "email": owner["email"],
                "name": owner["name"],
                "role": "owner",
            }
            if owner
            else None
        ),
        "users": [
            {
                "id": str(r["id"]),
                "email": r["email"],
                "name": r["name"],
                "role": r["role"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ],
    }


@router.post("/{project_id}/access/users", status_code=201)
def add_user_access(project_id: str, body: AddUserAccess, user: dict = Depends(require_assess_admin)):
    get_mel_project(project_id)
    if body.role not in ("admin", "member"):
        raise HTTPException(400, "role must be 'admin' or 'member'")
    email = body.email.lower().strip()
    with db_cursor() as cur:
        cur.execute("SELECT id, email, name FROM users WHERE email = %(email)s", {"email": email})
        target = cur.fetchone()
        if not target:
            raise HTTPException(404, "No account found with that email")
        cur.execute(
            "SELECT owner_id FROM assess_projects WHERE id = %(id)s",
            {"id": project_id},
        )
        proj = cur.fetchone()
        if proj and str(target["id"]) == str(proj["owner_id"]):
            raise HTTPException(400, "Owner already has access to this project")

        cur.execute(
            """
            INSERT INTO assess_project_users (project_id, user_id, role, added_by)
            VALUES (%(project_id)s, %(user_id)s, %(role)s, %(added_by)s)
            ON CONFLICT (project_id, user_id) DO NOTHING
            RETURNING project_id
            """,
            {
                "project_id": project_id,
                "user_id": target["id"],
                "role": body.role,
                "added_by": user["id"],
            },
        )
        if not cur.fetchone():
            raise HTTPException(409, "That user already has access to this project")
    return {
        "id": str(target["id"]),
        "email": target["email"],
        "name": target["name"],
        "role": body.role,
    }


@router.patch("/{project_id}/access/users/{user_id}/role")
def update_user_role(
    project_id: str, user_id: str, body: UpdateUserRole, user: dict = Depends(require_assess_admin)
):
    get_mel_project(project_id)
    if body.role not in ("admin", "member"):
        raise HTTPException(400, "role must be 'admin' or 'member'")
    with db_cursor() as cur:
        cur.execute(
            """
            UPDATE assess_project_users SET role = %(role)s
            WHERE project_id = %(project_id)s AND user_id = %(user_id)s
            RETURNING user_id
            """,
            {"project_id": project_id, "user_id": user_id, "role": body.role},
        )
        if not cur.fetchone():
            raise HTTPException(404, "That user does not have access to this project")
    return {"id": user_id, "role": body.role}


@router.delete("/{project_id}/access/users/{user_id}", status_code=204)
def remove_user_access(project_id: str, user_id: str, user: dict = Depends(require_assess_admin)):
    get_mel_project(project_id)
    with db_cursor() as cur:
        cur.execute(
            """
            DELETE FROM assess_project_users
            WHERE project_id = %(project_id)s AND user_id = %(user_id)s
            RETURNING user_id
            """,
            {"project_id": project_id, "user_id": user_id},
        )
        if not cur.fetchone():
            raise HTTPException(404, "That user does not have access to this project")
