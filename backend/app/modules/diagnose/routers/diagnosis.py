import json
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.shared.access import (
    diagnosis_access_where,
    require_diagnosis_access,
    require_diagnosis_admin,
    require_diagnosis_owner,
)
from app.shared.auth import get_current_user
from app.shared.config import settings
from app.shared.database import db_cursor
from app.shared import s3_storage
from app.shared.watersheds import lookup_watershed

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    lng: float = Field(..., ge=-180, le=180)
    lat: float = Field(..., ge=-90, le=90)


class AddUserAccess(BaseModel):
    email: EmailStr
    role: str = Field(default="member", pattern=r"^(admin|member)$")


class UpdateUserRole(BaseModel):
    role: str = Field(..., pattern=r"^(admin|member)$")


class AddOrgAccess(BaseModel):
    org_id: UUID


def _row_to_dict(row: dict) -> dict:
    bounds = None
    if row.get("bounds_geojson"):
        coords = row["bounds_geojson"]["coordinates"][0]
        lngs = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        bounds = [min(lngs), min(lats), max(lngs), max(lats)]

    watershed_geometry = row.get("watershed_geojson")
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "owner_id": str(row["owner_id"]),
        "owner_name": row.get("owner_name") or "",
        "owner_email": row.get("owner_email") or "",
        "watershed_id": row["watershed_id"],
        "watershed_name": row["watershed_name"],
        "seed_lng": row["seed_lng"],
        "seed_lat": row["seed_lat"],
        "bounds": bounds,
        "watershed_geometry": watershed_geometry,
        "observation_zone_count": int(row.get("observation_zone_count") or 0),
        "field_note_count": int(row.get("field_note_count") or 0),
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


_SELECT = """
    SELECT
        p.id,
        p.name,
        p.owner_id,
        owner_u.name  AS owner_name,
        owner_u.email AS owner_email,
        p.watershed_id,
        p.watershed_name,
        p.seed_lng,
        p.seed_lat,
        p.created_at,
        p.updated_at,
        ST_AsGeoJSON(p.watershed_geom, 9)::json AS watershed_geojson,
        ST_AsGeoJSON(ST_Envelope(p.watershed_geom))::json AS bounds_geojson,
        (
            SELECT COUNT(*)::int
            FROM observation_zones oz
            WHERE oz.project_id = p.id
        ) AS observation_zone_count,
        (
            SELECT COUNT(*)::int
            FROM field_notes fn
            WHERE fn.project_id = p.id
        ) AS field_note_count
    FROM diagnosis p
    JOIN users owner_u ON owner_u.id = p.owner_id
"""


@router.get("")
def list_projects(user: dict = Depends(get_current_user)):
    with db_cursor() as cur:
        cur.execute(
            f"{_SELECT} WHERE {diagnosis_access_where('p')} ORDER BY created_at DESC",
            {"current_user_id": user["id"]},
        )
        rows = cur.fetchall()
    return {"projects": [_row_to_dict(r) for r in rows]}


@router.get("/{project_id}")
def get_project(project_id: str, user: dict = Depends(require_diagnosis_access)):
    with db_cursor() as cur:
        cur.execute(f"{_SELECT} WHERE p.id = %(id)s", {"id": project_id})
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Project not found")
    return _row_to_dict(row)


@router.post("", status_code=201)
def create_project(body: ProjectCreate, user: dict = Depends(get_current_user)):
    try:
        watershed = lookup_watershed(body.lng, body.lat)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Watershed lookup failed: {exc}") from exc

    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO diagnosis (
                name, owner_id, watershed_id, watershed_name, watershed_geom, seed_lng, seed_lat
            )
            VALUES (
                %(name)s,
                %(owner_id)s,
                %(watershed_id)s,
                %(watershed_name)s,
                ST_SetSRID(ST_GeomFromGeoJSON(%(watershed_geom)s), 4326),
                %(seed_lng)s,
                %(seed_lat)s
            )
            RETURNING id, name, owner_id,
                      %(owner_name)s AS owner_name,
                      %(owner_email)s AS owner_email,
                      watershed_id, watershed_name, seed_lng, seed_lat,
                      created_at, updated_at,
                      ST_AsGeoJSON(watershed_geom, 9)::json AS watershed_geojson,
                      ST_AsGeoJSON(ST_Envelope(watershed_geom))::json AS bounds_geojson,
                      0 AS observation_zone_count,
                      0 AS field_note_count
            """,
            {
                "name": body.name.strip(),
                "owner_id": user["id"],
                "owner_name": user["name"],
                "owner_email": user["email"],
                "watershed_id": watershed["watershed_id"],
                "watershed_name": watershed["watershed_name"],
                "watershed_geom": json.dumps(watershed["geometry"]),
                "seed_lng": body.lng,
                "seed_lat": body.lat,
            },
        )
        row = cur.fetchone()
    return _row_to_dict(row)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, user: dict = Depends(require_diagnosis_owner)):
    with db_cursor() as cur:
        cur.execute(
            "SELECT photo_path FROM field_notes WHERE project_id = %(id)s AND photo_path IS NOT NULL",
            {"id": project_id},
        )
        legacy_photo_paths = [
            row["photo_path"]
            for row in cur.fetchall()
            if row["photo_path"] and row["photo_path"].startswith("photos/")
        ]
        cur.execute("DELETE FROM diagnosis WHERE id = %(id)s RETURNING id", {"id": project_id})
        if not cur.fetchone():
            raise HTTPException(404, "Project not found")

    for photo_path in legacy_photo_paths:
        local = Path(settings.packages_dir) / "photos" / Path(photo_path).name
        if local.is_file():
            local.unlink()

    s3_storage.delete_prefix(s3_storage.project_prefix(project_id))


# --- Sharing: owner or diagnosis-admin management of user/org grants ---


@router.get("/{project_id}/access/users")
def list_user_access(project_id: str, user: dict = Depends(require_diagnosis_admin)):
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT u.id, u.email, u.name, du.role, du.created_at
            FROM diagnosis_users du
            JOIN users u ON u.id = du.user_id
            WHERE du.diagnosis_id = %(id)s
            ORDER BY du.created_at ASC
            """,
            {"id": project_id},
        )
        rows = cur.fetchall()
    return {
        "users": [
            {
                "id": str(r["id"]),
                "email": r["email"],
                "name": r["name"],
                "role": r["role"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
    }


@router.post("/{project_id}/access/users", status_code=201)
def add_user_access(project_id: str, body: AddUserAccess, user: dict = Depends(require_diagnosis_admin)):
    email = body.email.lower().strip()
    with db_cursor() as cur:
        cur.execute("SELECT id, email, name FROM users WHERE email = %(email)s", {"email": email})
        target = cur.fetchone()
        if not target:
            raise HTTPException(404, "No account found with that email")
        if str(target["id"]) == str(user["id"]):
            raise HTTPException(400, "You already have access to this project")

        cur.execute(
            """
            INSERT INTO diagnosis_users (diagnosis_id, user_id, role, added_by)
            VALUES (%(diagnosis_id)s, %(user_id)s, %(role)s, %(added_by)s)
            ON CONFLICT (diagnosis_id, user_id) DO NOTHING
            RETURNING diagnosis_id
            """,
            {"diagnosis_id": project_id, "user_id": target["id"], "role": body.role, "added_by": user["id"]},
        )
        if not cur.fetchone():
            raise HTTPException(409, "That user already has access to this project")
    return {"id": str(target["id"]), "email": target["email"], "name": target["name"], "role": body.role}


@router.delete("/{project_id}/access/users/{user_id}", status_code=204)
def remove_user_access(project_id: str, user_id: str, user: dict = Depends(require_diagnosis_admin)):
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM diagnosis_users WHERE diagnosis_id = %(diagnosis_id)s AND user_id = %(user_id)s RETURNING user_id",
            {"diagnosis_id": project_id, "user_id": user_id},
        )
        if not cur.fetchone():
            raise HTTPException(404, "That user does not have access to this project")


@router.patch("/{project_id}/access/users/{user_id}/role")
def update_user_role(
    project_id: str, user_id: str, body: UpdateUserRole, user: dict = Depends(require_diagnosis_admin)
):
    with db_cursor() as cur:
        cur.execute(
            """
            UPDATE diagnosis_users SET role = %(role)s
            WHERE diagnosis_id = %(diagnosis_id)s AND user_id = %(user_id)s
            RETURNING user_id
            """,
            {"diagnosis_id": project_id, "user_id": user_id, "role": body.role},
        )
        if not cur.fetchone():
            raise HTTPException(404, "That user does not have access to this project")
    return {"id": user_id, "role": body.role}


@router.get("/{project_id}/access/orgs")
def list_org_access(project_id: str, user: dict = Depends(require_diagnosis_admin)):
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT o.id, o.name, dorg.created_at
            FROM diagnosis_orgs dorg
            JOIN organizations o ON o.id = dorg.org_id
            WHERE dorg.diagnosis_id = %(id)s
            ORDER BY dorg.created_at ASC
            """,
            {"id": project_id},
        )
        rows = cur.fetchall()
    return {
        "organizations": [
            {"id": str(r["id"]), "name": r["name"], "created_at": r["created_at"].isoformat()} for r in rows
        ]
    }


@router.post("/{project_id}/access/orgs", status_code=201)
def add_org_access(project_id: str, body: AddOrgAccess, user: dict = Depends(require_diagnosis_admin)):
    with db_cursor() as cur:
        # Owner may only grant access to orgs they themselves belong to.
        cur.execute(
            """
            SELECT o.id, o.name
            FROM organizations o
            JOIN org_members om ON om.org_id = o.id
            WHERE o.id = %(org_id)s AND om.user_id = %(user_id)s
            """,
            {"org_id": str(body.org_id), "user_id": user["id"]},
        )
        org = cur.fetchone()
        if not org:
            raise HTTPException(404, "Organization not found, or you are not a member of it")

        cur.execute(
            """
            INSERT INTO diagnosis_orgs (diagnosis_id, org_id, added_by)
            VALUES (%(diagnosis_id)s, %(org_id)s, %(added_by)s)
            ON CONFLICT (diagnosis_id, org_id) DO NOTHING
            RETURNING diagnosis_id
            """,
            {"diagnosis_id": project_id, "org_id": str(body.org_id), "added_by": user["id"]},
        )
        if not cur.fetchone():
            raise HTTPException(409, "That organization already has access to this project")
    return {"id": str(org["id"]), "name": org["name"]}


@router.delete("/{project_id}/access/orgs/{org_id}", status_code=204)
def remove_org_access(project_id: str, org_id: str, user: dict = Depends(require_diagnosis_admin)):
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM diagnosis_orgs WHERE diagnosis_id = %(diagnosis_id)s AND org_id = %(org_id)s RETURNING org_id",
            {"diagnosis_id": project_id, "org_id": org_id},
        )
        if not cur.fetchone():
            raise HTTPException(404, "That organization does not have access to this project")
