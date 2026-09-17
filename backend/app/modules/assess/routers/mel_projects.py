"""MEL project + plan CRUD — project owns many one-intervention plans."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.modules.assess.access import (
    assess_access_where,
    get_mel_plan,
    get_mel_project,
    mel_asset_to_dict,
    mel_plan_to_dict,
    mel_project_to_dict,
    require_assess_access,
    require_assess_admin,
    require_assess_owner,
)
from app.modules.assess.services.collect_qr import build_mel_collect_qr
from app.modules.assess.services.mel_analyses import (
    asset_label_from_answers,
    compute_asset_metrics,
    is_asset_select_field,
    is_plot_intervention,
)
from app.modules.assess.services.mel_catalog import get_intervention
from app.modules.assess.services.mel_mapping_catalog import (
    get_mapping_intervention,
    resolve_mapping_outcomes,
)
from app.modules.assess.services.mel_plan_docx import (
    _apply_question_overrides,
    build_mel_plan_docx,
)
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


class MelProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class MelPlanCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    intervention_slug: str = Field(..., min_length=1, max_length=120)
    kind: str = Field(default="plan", pattern=r"^(plan|implementation)$")


class MelPlanSave(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    outcome_ids: list[str] | None = None
    plan_json: dict | None = None


class MelAssetCreate(BaseModel):
    ot_answers: dict = Field(default_factory=dict)
    label: str = Field(default="", max_length=300)


class MelAssetUpdate(BaseModel):
    ot_answers: dict | None = None
    label: str | None = Field(default=None, max_length=300)


def _resolve_intervention(slug: str) -> dict | None:
    """Prefer mapping catalog (Farm pond); fall back to legacy outcomes catalog."""
    mapped = get_mapping_intervention(slug)
    if mapped:
        return mapped
    return get_intervention(slug)

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


@router.patch("/{project_id}")
def update_mel_project(
    project_id: str,
    body: MelProjectUpdate,
    user: dict = Depends(require_assess_admin),
):
    existing = get_mel_project(project_id)
    if body.name is None and body.description is None:
        return mel_project_to_dict(existing)
    name = existing["name"]
    description = existing.get("description") or ""
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "Name is required")
    if body.description is not None:
        description = body.description.strip()

    with db_cursor() as cur:
        cur.execute(
            """
            UPDATE assess_projects
            SET name = %(name)s, description = %(description)s, updated_at = now()
            WHERE id = %(id)s AND kind = 'mel'
            RETURNING id
            """,
            {"id": project_id, "name": name, "description": description},
        )
        if not cur.fetchone():
            raise HTTPException(404, "MEL project not found")
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
def list_mel_plans(
    project_id: str,
    kind: str | None = None,
    user: dict = Depends(require_assess_access),
):
    get_mel_project(project_id)
    params: dict = {"project_id": project_id}
    kind_sql = ""
    if kind in ("plan", "implementation"):
        kind_sql = "AND mp.kind = %(kind)s"
        params["kind"] = kind
    with db_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                mp.id,
                mp.project_id,
                mp.name,
                mp.intervention_slug,
                mp.kind,
                mp.plan_json,
                mp.created_by,
                mp.created_at,
                mp.updated_at,
                (
                    SELECT COUNT(*)::int FROM mel_forms mf WHERE mf.plan_id = mp.id
                ) AS form_count,
                (
                    SELECT COUNT(*)::int FROM mel_assets ma WHERE ma.plan_id = mp.id
                ) AS asset_count
            FROM mel_plans mp
            WHERE mp.project_id = %(project_id)s
            {kind_sql}
            ORDER BY mp.updated_at DESC
            """,
            params,
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
    intervention = _resolve_intervention(body.intervention_slug)
    if intervention is None:
        raise HTTPException(404, "Intervention not found in catalog")

    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Name is required")
    kind = body.kind if body.kind in ("plan", "implementation") else "plan"

    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO mel_plans (
                project_id, name, intervention_slug, kind, created_by
            )
            VALUES (
                %(project_id)s, %(name)s, %(intervention_slug)s, %(kind)s, %(created_by)s
            )
            RETURNING
                id, project_id, name, intervention_slug, kind, plan_json,
                created_by, created_at, updated_at
            """,
            {
                "project_id": project_id,
                "name": name,
                "intervention_slug": intervention.get("slug") or body.intervention_slug,
                "kind": kind,
                "created_by": user["id"],
            },
        )
        row = cur.fetchone()
        cur.execute(
            "UPDATE assess_projects SET updated_at = now() WHERE id = %(id)s",
            {"id": project_id},
        )

    row = {**row, "form_count": 0, "asset_count": 0}
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
    existing = get_mel_plan(plan_id, project_id=project_id)
    assignments = ["updated_at = now()"]
    params: dict = {"id": plan_id, "project_id": project_id}

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "Name is required")
        assignments.append("name = %(name)s")
        params["name"] = name

    if body.plan_json is not None or body.outcome_ids is not None:
        plan_json = body.plan_json if body.plan_json is not None else dict(existing.get("plan_json") or {})
        if body.outcome_ids is not None:
            plan_json = {**plan_json, "outcome_ids": body.outcome_ids}
        elif "outcome_ids" not in plan_json:
            plan_json = {**plan_json, "outcome_ids": []}
        assignments.append("plan_json = %(plan_json)s::jsonb")
        params["plan_json"] = json.dumps(plan_json)

    if len(assignments) == 1:
        return mel_plan_to_dict(existing)

    with db_cursor() as cur:
        cur.execute(
            f"""
            UPDATE mel_plans
            SET {", ".join(assignments)}
            WHERE id = %(id)s AND project_id = %(project_id)s
            RETURNING id
            """,
            params,
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


class AddOrgAccess(BaseModel):
    org_id: str


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


@router.get("/{project_id}/access/orgs")
def list_org_access(project_id: str, user: dict = Depends(require_assess_admin)):
    get_mel_project(project_id)
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT o.id, o.name, apo.created_at
            FROM assess_project_orgs apo
            JOIN organizations o ON o.id = apo.org_id
            WHERE apo.project_id = %(id)s
            ORDER BY apo.created_at ASC
            """,
            {"id": project_id},
        )
        rows = cur.fetchall()
    return {
        "organizations": [
            {"id": str(r["id"]), "name": r["name"], "created_at": r["created_at"].isoformat()}
            for r in rows
        ]
    }


@router.post("/{project_id}/access/orgs", status_code=201)
def add_org_access(
    project_id: str, body: AddOrgAccess, user: dict = Depends(require_assess_admin)
):
    get_mel_project(project_id)
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT o.id, o.name
            FROM organizations o
            JOIN org_members om ON om.org_id = o.id
            WHERE o.id = %(org_id)s AND om.user_id = %(user_id)s
            """,
            {"org_id": body.org_id, "user_id": user["id"]},
        )
        org = cur.fetchone()
        if not org:
            raise HTTPException(404, "Organization not found, or you are not a member of it")
        cur.execute(
            """
            INSERT INTO assess_project_orgs (project_id, org_id, added_by)
            VALUES (%(project_id)s, %(org_id)s, %(added_by)s)
            ON CONFLICT (project_id, org_id) DO NOTHING
            RETURNING project_id
            """,
            {"project_id": project_id, "org_id": org["id"], "added_by": user["id"]},
        )
        if not cur.fetchone():
            raise HTTPException(409, "That organization already has access to this project")
    return {"id": str(org["id"]), "name": org["name"]}


@router.delete("/{project_id}/access/orgs/{org_id}", status_code=204)
def remove_org_access(project_id: str, org_id: str, user: dict = Depends(require_assess_admin)):
    get_mel_project(project_id)
    with db_cursor() as cur:
        cur.execute(
            """
            DELETE FROM assess_project_orgs
            WHERE project_id = %(project_id)s AND org_id = %(org_id)s
            RETURNING org_id
            """,
            {"project_id": project_id, "org_id": org_id},
        )
        if not cur.fetchone():
            raise HTTPException(404, "That organization does not have access to this project")


# --- Assets (one_time allocation) + dashboards + docx ---


@router.get("/{project_id}/plans/{plan_id}/assets")
def list_mel_assets(project_id: str, plan_id: str, user: dict = Depends(require_assess_access)):
    get_mel_project(project_id)
    get_mel_plan(plan_id, project_id=project_id)
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, project_id, plan_id, intervention_slug, label, ot_answers,
                   created_by, created_at, updated_at
            FROM mel_assets
            WHERE plan_id = %(plan_id)s AND project_id = %(project_id)s
            ORDER BY created_at ASC
            """,
            {"plan_id": plan_id, "project_id": project_id},
        )
        rows = cur.fetchall()
    return {"assets": [mel_asset_to_dict(r) for r in rows]}


@router.post("/{project_id}/plans/{plan_id}/assets", status_code=201)
def create_mel_asset(
    project_id: str,
    plan_id: str,
    body: MelAssetCreate,
    user: dict = Depends(require_assess_access),
):
    get_mel_project(project_id)
    plan = get_mel_plan(plan_id, project_id=project_id)
    if (plan.get("kind") or "plan") != "implementation":
        raise HTTPException(400, "Assets can only be added to an implementation")

    answers = body.ot_answers or {}
    fallback = "Farm plot" if is_plot_intervention(plan.get("intervention_slug")) else "Farm pond"
    label = (body.label or "").strip() or asset_label_from_answers(answers, fallback)

    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO mel_assets (
                project_id, plan_id, intervention_slug, label, ot_answers, created_by
            )
            VALUES (
                %(project_id)s, %(plan_id)s, %(intervention_slug)s,
                %(label)s, %(ot_answers)s::jsonb, %(created_by)s
            )
            RETURNING id, project_id, plan_id, intervention_slug, label, ot_answers,
                      created_by, created_at, updated_at
            """,
            {
                "project_id": project_id,
                "plan_id": plan_id,
                "intervention_slug": plan["intervention_slug"],
                "label": label,
                "ot_answers": json.dumps(answers),
                "created_by": user["id"],
            },
        )
        row = cur.fetchone()
        cur.execute(
            "UPDATE assess_projects SET updated_at = now() WHERE id = %(id)s",
            {"id": project_id},
        )
    return mel_asset_to_dict(row)


@router.get("/{project_id}/plans/{plan_id}/assets/{asset_id}")
def get_mel_asset(
    project_id: str, plan_id: str, asset_id: str, user: dict = Depends(require_assess_access)
):
    get_mel_project(project_id)
    get_mel_plan(plan_id, project_id=project_id)
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, project_id, plan_id, intervention_slug, label, ot_answers,
                   created_by, created_at, updated_at
            FROM mel_assets
            WHERE id = %(id)s AND plan_id = %(plan_id)s AND project_id = %(project_id)s
            """,
            {"id": asset_id, "plan_id": plan_id, "project_id": project_id},
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Asset not found")
    return mel_asset_to_dict(row)


@router.patch("/{project_id}/plans/{plan_id}/assets/{asset_id}")
def update_mel_asset(
    project_id: str,
    plan_id: str,
    asset_id: str,
    body: MelAssetUpdate,
    user: dict = Depends(require_assess_access),
):
    get_mel_project(project_id)
    get_mel_plan(plan_id, project_id=project_id)
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, ot_answers, label FROM mel_assets
            WHERE id = %(id)s AND plan_id = %(plan_id)s AND project_id = %(project_id)s
            """,
            {"id": asset_id, "plan_id": plan_id, "project_id": project_id},
        )
        existing = cur.fetchone()
        if not existing:
            raise HTTPException(404, "Asset not found")
        answers = body.ot_answers if body.ot_answers is not None else (existing.get("ot_answers") or {})
        label = (
            body.label.strip()
            if body.label is not None
            else (existing.get("label") or asset_label_from_answers(answers))
        )
        cur.execute(
            """
            UPDATE mel_assets
            SET ot_answers = %(ot_answers)s::jsonb, label = %(label)s, updated_at = now()
            WHERE id = %(id)s
            RETURNING id, project_id, plan_id, intervention_slug, label, ot_answers,
                      created_by, created_at, updated_at
            """,
            {"id": asset_id, "ot_answers": json.dumps(answers), "label": label},
        )
        row = cur.fetchone()
    return mel_asset_to_dict(row)


@router.delete("/{project_id}/plans/{plan_id}/assets/{asset_id}", status_code=204)
def delete_mel_asset(
    project_id: str, plan_id: str, asset_id: str, user: dict = Depends(require_assess_access)
):
    get_mel_project(project_id)
    get_mel_plan(plan_id, project_id=project_id)
    with db_cursor() as cur:
        cur.execute(
            """
            DELETE FROM mel_assets
            WHERE id = %(id)s AND plan_id = %(plan_id)s AND project_id = %(project_id)s
            RETURNING id
            """,
            {"id": asset_id, "plan_id": plan_id, "project_id": project_id},
        )
        if not cur.fetchone():
            raise HTTPException(404, "Asset not found")


def _empty_cm_stats() -> dict:
    return {
        "submission_count": 0,
        "last_submission_at": None,
        "first_reading_date": None,
        "last_reading_date": None,
        "source": "none",
    }


def _cm_stats_from_rows(
    rows: list[dict],
    *,
    source: str,
    last_submission_at: str | None = None,
) -> dict:
    dates: list[str] = []
    submitted: list[str] = []
    for row in rows:
        reading = row.get("fp_cm_date_of_reading") or row.get("observation_date")
        if reading:
            dates.append(str(reading)[:10])
        ts = row.get("_submittedAt")
        if ts:
            submitted.append(str(ts))
    dates.sort()
    last_at = last_submission_at
    if not last_at and submitted:
        last_at = max(submitted)
    return {
        "submission_count": len(rows),
        "last_submission_at": last_at,
        "first_reading_date": dates[0] if dates else None,
        "last_reading_date": dates[-1] if dates else None,
        "source": source,
    }


def _local_cm_rows(plan_id: str, project_id: str) -> list[dict]:
    rows: list[dict] = []
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT asset_id, reading_date, rainfall_mm, water_level_m, payload
            FROM mel_cm_readings
            WHERE plan_id = %(plan_id)s AND project_id = %(project_id)s
            ORDER BY reading_date ASC NULLS LAST, created_at ASC
            """,
            {"plan_id": plan_id, "project_id": project_id},
        )
        for row in cur.fetchall():
            payload = dict(row.get("payload") or {})
            asset_id = str(row["asset_id"])
            payload.setdefault("fp_cm_select_the_asset_id", asset_id)
            payload.setdefault("bm_cm_select_the_asset_id", asset_id)
            if row.get("reading_date") is not None:
                iso = row["reading_date"].isoformat()
                payload.setdefault("fp_cm_date_of_reading", iso)
                payload.setdefault("bm_cm_date_of_reading", iso)
            if row.get("rainfall_mm") is not None:
                payload.setdefault("fp_cm_rainfall", row["rainfall_mm"])
                payload.setdefault(
                    "bm_cm_rainfall_recorded_since_last_irrigation", row["rainfall_mm"]
                )
            if row.get("water_level_m") is not None:
                payload.setdefault("fp_cm_staff_gauge_reading", row["water_level_m"])
            rows.append(payload)
    return rows


async def _odk_cm_rows(plan_id: str, project_id: str) -> tuple[list[dict], str | None]:
    if settings.odk_project_id is None:
        return [], None

    with db_cursor() as cur:
        cur.execute(
            """
            SELECT xml_form_id, package_id
            FROM mel_forms
            WHERE plan_id = %(plan_id)s AND project_id = %(project_id)s
            ORDER BY created_at ASC
            """,
            {"plan_id": plan_id, "project_id": project_id},
        )
        forms = cur.fetchall()
    if not forms:
        return [], None

    preferred = [f for f in forms if (f.get("package_id") or "") == "cm-mapping"]
    to_fetch = preferred or forms

    client = ODKClient()
    odk_project_id = int(settings.odk_project_id)
    rows: list[dict] = []
    last_submission_at: str | None = None
    for form in to_fetch:
        try:
            odata_rows = await _fetch_all_odata_submissions(
                client, odk_project_id, form["xml_form_id"]
            )
        except Exception:
            continue
        for raw in odata_rows:
            system = raw.get("__system") if isinstance(raw, dict) else None
            ts = system.get("submissionDate") if isinstance(system, dict) else None
            if ts and (last_submission_at is None or str(ts) > last_submission_at):
                last_submission_at = str(ts)
        normalized = normalize_submissions(odata_rows)
        for sub in normalized.get("rows") or []:
            if isinstance(sub, dict):
                rows.append(sub)
    return rows, last_submission_at


async def _collect_plan_cm_bundle(plan_id: str, project_id: str) -> tuple[list[dict], dict]:
    """Prefer ODK CM submissions; fall back to local readings if ODK is empty."""
    odk_rows, last_submission_at = await _odk_cm_rows(plan_id, project_id)
    if odk_rows:
        return odk_rows, _cm_stats_from_rows(
            odk_rows, source="odk", last_submission_at=last_submission_at
        )
    local = _local_cm_rows(plan_id, project_id)
    if local:
        return local, _cm_stats_from_rows(local, source="local")
    return [], _empty_cm_stats()


async def _collect_plan_cm_submissions(plan_id: str, project_id: str) -> list[dict]:
    rows, _stats = await _collect_plan_cm_bundle(plan_id, project_id)
    return rows


@router.get("/{project_id}/plans/{plan_id}/dashboard")
async def implementation_dashboard(
    project_id: str, plan_id: str, user: dict = Depends(require_assess_access)
):
    get_mel_project(project_id)
    plan = get_mel_plan(plan_id, project_id=project_id)
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, project_id, plan_id, intervention_slug, label, ot_answers,
                   created_by, created_at, updated_at
            FROM mel_assets
            WHERE plan_id = %(plan_id)s AND project_id = %(project_id)s
            ORDER BY created_at ASC
            """,
            {"plan_id": plan_id, "project_id": project_id},
        )
        assets = cur.fetchall()

    cm_data, cm_stats = await _collect_plan_cm_bundle(plan_id, project_id)
    asset_summaries = []
    for a in assets:
        sibling_ot = [
            (str(other["id"]), other.get("ot_answers") or {})
            for other in assets
            if str(other["id"]) != str(a["id"])
        ]
        metrics = compute_asset_metrics(
            a.get("intervention_slug") or plan.get("intervention_slug"),
            ot_answers=a.get("ot_answers") or {},
            cm_submissions=cm_data,
            asset_id=str(a["id"]),
            sibling_ot=sibling_ot,
        )
        asset_summaries.append(
            {
                **mel_asset_to_dict(a),
                "calculations": metrics["calculations"],
                "reading_count": metrics["reading_count"],
            }
        )

    totals = {
        "asset_count": len(asset_summaries),
        "volumetric_storage_m3": sum(
            (s["calculations"].get("volumetric_storage_m3") or 0) for s in asset_summaries
        ),
        "sm_water_savings_m3": sum(
            (s["calculations"].get("sm_water_savings_m3") or 0) for s in asset_summaries
        ),
        "irrigation_applied_m3": sum(
            (s["calculations"].get("irrigation_applied_m3") or 0) for s in asset_summaries
        ),
        "cumulative_rainfall_mm": sum(
            (s["calculations"].get("cumulative_rainfall_mm") or 0) for s in asset_summaries
        ),
        **cm_stats,
    }
    return {
        "plan": mel_plan_to_dict(plan),
        "assets": asset_summaries,
        "totals": totals,
    }


@router.get("/{project_id}/plans/{plan_id}/assets/{asset_id}/dashboard")
async def asset_dashboard(
    project_id: str,
    plan_id: str,
    asset_id: str,
    user: dict = Depends(require_assess_access),
):
    get_mel_project(project_id)
    plan = get_mel_plan(plan_id, project_id=project_id)
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, project_id, plan_id, intervention_slug, label, ot_answers,
                   created_by, created_at, updated_at
            FROM mel_assets
            WHERE plan_id = %(plan_id)s AND project_id = %(project_id)s
            ORDER BY created_at ASC
            """,
            {"plan_id": plan_id, "project_id": project_id},
        )
        assets = cur.fetchall()
    asset = next((a for a in assets if str(a["id"]) == str(asset_id)), None)
    if not asset:
        raise HTTPException(404, "Asset not found")

    cm_data = await _collect_plan_cm_submissions(plan_id, project_id)
    sibling_ot = [
        (str(other["id"]), other.get("ot_answers") or {})
        for other in assets
        if str(other["id"]) != str(asset["id"])
    ]
    metrics = compute_asset_metrics(
        asset.get("intervention_slug") or plan.get("intervention_slug"),
        ot_answers=asset.get("ot_answers") or {},
        cm_submissions=cm_data,
        asset_id=str(asset["id"]),
        sibling_ot=sibling_ot,
    )
    return {
        "plan": mel_plan_to_dict(plan),
        "asset": mel_asset_to_dict(asset),
        **metrics,
    }


@router.get("/{project_id}/plans/{plan_id}/export-docx")
def export_mel_plan_docx(
    project_id: str, plan_id: str, user: dict = Depends(require_assess_access)
):
    project = get_mel_project(project_id)
    plan = get_mel_plan(plan_id, project_id=project_id)
    plan_json = plan.get("plan_json") or {}
    outcome_ids = plan_json.get("outcome_ids") or []
    outcomes = resolve_mapping_outcomes(plan["intervention_slug"], outcome_ids)
    intervention = get_mapping_intervention(plan["intervention_slug"])
    intervention_name = (
        intervention["name"] if intervention else plan["intervention_slug"]
    )
    ot_qs = _apply_question_overrides(
        (intervention or {}).get("one_time_questions") or [],
        plan_json.get("asset_allocation"),
    )
    cm_qs = _apply_question_overrides(
        (intervention or {}).get("cm_questions") or [],
        plan_json.get("cm_form"),
    )
    content = build_mel_plan_docx(
        project_name=project["name"],
        plan_name=plan["name"],
        intervention_name=intervention_name,
        outcomes=outcomes,
        one_time_questions=ot_qs,
        cm_questions=cm_qs,
    )
    filename = f"{plan['name'].replace(' ', '_')}_MEL_plan.docx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{project_id}/plans/{plan_id}/one-time-questions")
def list_one_time_questions(
    project_id: str, plan_id: str, user: dict = Depends(require_assess_access)
):
    get_mel_project(project_id)
    plan = get_mel_plan(plan_id, project_id=project_id)
    intervention = get_mapping_intervention(plan["intervention_slug"])
    if not intervention:
        raise HTTPException(404, "Mapping catalog not found for this intervention")
    return {
        "intervention_slug": intervention["slug"],
        "questions": intervention["one_time_questions"],
    }


@router.get("/{project_id}/plans/{plan_id}/cm-questions")
def list_cm_questions(
    project_id: str, plan_id: str, user: dict = Depends(require_assess_access)
):
    get_mel_project(project_id)
    plan = get_mel_plan(plan_id, project_id=project_id)
    intervention = get_mapping_intervention(plan["intervention_slug"])
    if not intervention:
        raise HTTPException(404, "Mapping catalog not found for this intervention")
    # Inject live asset choices into asset-id select
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, label FROM mel_assets
            WHERE plan_id = %(plan_id)s ORDER BY created_at ASC
            """,
            {"plan_id": plan_id},
        )
        assets = cur.fetchall()
    asset_choices = [f"{a['label']}|{a['id']}" for a in assets]  # unused format
    asset_options = [{"value": str(a["id"]), "label": a["label"] or str(a["id"])} for a in assets]

    questions = []
    for q in intervention["cm_questions"]:
        q2 = dict(q)
        if is_asset_select_field(q.get("variable_name")):
            q2["selectors"] = [o["label"] for o in asset_options]
            q2["options"] = asset_options
        questions.append(q2)
    return {
        "intervention_slug": intervention["slug"],
        "questions": questions,
        "assets": asset_options,
    }
