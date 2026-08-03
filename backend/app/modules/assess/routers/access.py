"""Assess sharing management. Only the project owner or an admin can grant/revoke access."""

from pydantic import BaseModel, EmailStr

from fastapi import APIRouter, Depends, HTTPException

from app.modules.assess.access import require_assess_admin
from app.shared.database import db_cursor

router = APIRouter()


class AddUserAccess(BaseModel):
    email: EmailStr
    role: str = "member"


class UpdateUserRole(BaseModel):
    role: str


@router.get("/{project_id}/access/users")
def list_user_access(project_id: str, user: dict = Depends(require_assess_admin)):
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
def add_user_access(project_id: str, body: AddUserAccess, user: dict = Depends(require_assess_admin)):
    if body.role not in ("admin", "member"):
        raise HTTPException(400, "role must be 'admin' or 'member'")
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
            INSERT INTO assess_project_users (project_id, user_id, role, added_by)
            VALUES (%(project_id)s, %(user_id)s, %(role)s, %(added_by)s)
            ON CONFLICT (project_id, user_id) DO NOTHING
            RETURNING project_id
            """,
            {"project_id": project_id, "user_id": target["id"], "role": body.role, "added_by": user["id"]},
        )
        if not cur.fetchone():
            raise HTTPException(409, "That user already has access to this project")
    return {"id": str(target["id"]), "email": target["email"], "name": target["name"], "role": body.role}


@router.patch("/{project_id}/access/users/{user_id}/role")
def update_user_role(
    project_id: str, user_id: str, body: UpdateUserRole, user: dict = Depends(require_assess_admin)
):
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
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM assess_project_users WHERE project_id = %(project_id)s AND user_id = %(user_id)s RETURNING user_id",
            {"project_id": project_id, "user_id": user_id},
        )
        if not cur.fetchone():
            raise HTTPException(404, "That user does not have access to this project")


@router.get("/{project_id}/access/orgs")
def list_org_access(project_id: str, user: dict = Depends(require_assess_admin)):
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
            {"id": str(r["id"]), "name": r["name"], "created_at": r["created_at"].isoformat()} for r in rows
        ]
    }


@router.post("/{project_id}/access/orgs", status_code=201)
def add_org_access(project_id: str, org_id: str, user: dict = Depends(require_assess_admin)):
    with db_cursor() as cur:
        cur.execute("SELECT id, name FROM organizations WHERE id = %(id)s", {"id": org_id})
        org = cur.fetchone()
        if not org:
            raise HTTPException(404, "Organization not found")
        cur.execute(
            """
            INSERT INTO assess_project_orgs (project_id, org_id, added_by)
            VALUES (%(project_id)s, %(org_id)s, %(added_by)s)
            ON CONFLICT (project_id, org_id) DO NOTHING
            RETURNING project_id
            """,
            {"project_id": project_id, "org_id": org_id, "added_by": user["id"]},
        )
        if not cur.fetchone():
            raise HTTPException(409, "That organization already has access to this project")
    return {"id": str(org["id"]), "name": org["name"]}


@router.delete("/{project_id}/access/orgs/{org_id}", status_code=204)
def remove_org_access(project_id: str, org_id: str, user: dict = Depends(require_assess_admin)):
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM assess_project_orgs WHERE project_id = %(project_id)s AND org_id = %(org_id)s RETURNING org_id",
            {"project_id": project_id, "org_id": org_id},
        )
        if not cur.fetchone():
            raise HTTPException(404, "That organization does not have access to this project")
