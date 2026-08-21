"""Organizations: create/list/delete, and manage membership.

Only admins can add or remove other members. Any member can leave (self-remove).
Admins can promote other members to admin. Admins can delete the org (projects are preserved).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.shared.auth import get_current_user
from app.shared.database import db_cursor

router = APIRouter()


class OrgCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class MemberAdd(BaseModel):
    email: EmailStr


def _require_member(cur, org_id: str, user_id: str) -> str:
    """Returns the caller's role in the org, or raises 404/403."""
    cur.execute("SELECT 1 FROM organizations WHERE id = %(id)s", {"id": org_id})
    if not cur.fetchone():
        raise HTTPException(404, "Organization not found")

    cur.execute(
        "SELECT role FROM org_members WHERE org_id = %(org_id)s AND user_id = %(user_id)s",
        {"org_id": org_id, "user_id": user_id},
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(403, "You are not a member of this organization")
    return row["role"]


@router.get("")
def list_my_orgs(user: dict = Depends(get_current_user)):
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT o.id, o.name, o.created_at, om.role
            FROM organizations o
            JOIN org_members om ON om.org_id = o.id
            WHERE om.user_id = %(user_id)s
            ORDER BY o.created_at DESC
            """,
            {"user_id": user["id"]},
        )
        rows = cur.fetchall()
    return {
        "organizations": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "role": r["role"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
    }


@router.post("", status_code=201)
def create_org(body: OrgCreate, user: dict = Depends(get_current_user)):
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO organizations (name, created_by)
            VALUES (%(name)s, %(created_by)s)
            RETURNING id, name, created_at
            """,
            {"name": body.name.strip(), "created_by": user["id"]},
        )
        org = cur.fetchone()
        cur.execute(
            """
            INSERT INTO org_members (org_id, user_id, role, added_by)
            VALUES (%(org_id)s, %(user_id)s, 'admin', %(user_id)s)
            """,
            {"org_id": org["id"], "user_id": user["id"]},
        )
    return {
        "id": str(org["id"]),
        "name": org["name"],
        "role": "admin",
        "created_at": org["created_at"].isoformat(),
    }


@router.get("/{org_id}/members")
def list_members(org_id: str, user: dict = Depends(get_current_user)):
    with db_cursor() as cur:
        _require_member(cur, org_id, user["id"])
        cur.execute(
            """
            SELECT u.id, u.email, u.name, om.role, om.created_at
            FROM org_members om
            JOIN users u ON u.id = om.user_id
            WHERE om.org_id = %(org_id)s
            ORDER BY om.created_at ASC
            """,
            {"org_id": org_id},
        )
        rows = cur.fetchall()
    return {
        "members": [
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


@router.post("/{org_id}/members", status_code=201)
def add_member(org_id: str, body: MemberAdd, user: dict = Depends(get_current_user)):
    email = body.email.lower().strip()
    with db_cursor() as cur:
        role = _require_member(cur, org_id, user["id"])
        if role != "admin":
            raise HTTPException(403, "Only org admins can add members")

        cur.execute("SELECT id, email, name FROM users WHERE email = %(email)s", {"email": email})
        target = cur.fetchone()
        if not target:
            raise HTTPException(404, "No account found with that email")

        cur.execute(
            "SELECT 1 FROM org_members WHERE org_id = %(org_id)s AND user_id = %(user_id)s",
            {"org_id": org_id, "user_id": target["id"]},
        )
        if cur.fetchone():
            raise HTTPException(409, "That user is already a member")

        cur.execute(
            """
            INSERT INTO org_members (org_id, user_id, role, added_by)
            VALUES (%(org_id)s, %(user_id)s, 'member', %(added_by)s)
            """,
            {"org_id": org_id, "user_id": target["id"], "added_by": user["id"]},
        )
    return {"id": str(target["id"]), "email": target["email"], "name": target["name"], "role": "member"}


@router.delete("/{org_id}/members/{member_id}", status_code=204)
def remove_member(org_id: str, member_id: str, user: dict = Depends(get_current_user)):
    is_self = str(member_id) == str(user["id"])
    with db_cursor() as cur:
        role = _require_member(cur, org_id, user["id"])
        if not is_self and role != "admin":
            raise HTTPException(403, "Only org admins can remove other members")

        if is_self:
            cur.execute(
                "SELECT COUNT(*)::int AS admin_count FROM org_members WHERE org_id = %(org_id)s AND role = 'admin'",
                {"org_id": org_id},
            )
            if role == "admin" and cur.fetchone()["admin_count"] <= 1:
                raise HTTPException(400, "Cannot leave as the last admin; promote another member or delete the org")

        cur.execute(
            "DELETE FROM org_members WHERE org_id = %(org_id)s AND user_id = %(user_id)s RETURNING user_id",
            {"org_id": org_id, "user_id": member_id},
        )
        if not cur.fetchone():
            raise HTTPException(404, "Member not found")


@router.delete("/{org_id}", status_code=204)
def delete_org(org_id: str, user: dict = Depends(get_current_user)):
    with db_cursor() as cur:
        role = _require_member(cur, org_id, user["id"])
        if role != "admin":
            raise HTTPException(403, "Only org admins can delete an organization")
        cur.execute(
            "DELETE FROM organizations WHERE id = %(id)s RETURNING id",
            {"id": org_id},
        )
        if not cur.fetchone():
            raise HTTPException(404, "Organization not found")


@router.get("/{org_id}/projects")
def list_org_projects(org_id: str, user: dict = Depends(get_current_user)):
    with db_cursor() as cur:
        _require_member(cur, org_id, user["id"])
        cur.execute(
            """
            SELECT d.id, d.name, u.name AS owner_name, d.created_at
            FROM diagnosis_orgs dorg
            JOIN diagnosis d ON d.id = dorg.diagnosis_id
            JOIN users u ON u.id = d.owner_id
            WHERE dorg.org_id = %(org_id)s
            ORDER BY d.created_at DESC
            """,
            {"org_id": org_id},
        )
        rows = cur.fetchall()
    return {
        "projects": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "owner_name": r["owner_name"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
    }


class RoleUpdate(BaseModel):
    role: str = Field(..., pattern="^(admin|member)$")


@router.patch("/{org_id}/members/{member_id}/role")
def update_member_role(org_id: str, member_id: str, body: RoleUpdate, user: dict = Depends(get_current_user)):
    with db_cursor() as cur:
        caller_role = _require_member(cur, org_id, user["id"])
        if caller_role != "admin":
            raise HTTPException(403, "Only org admins can change roles")

        if member_id == user["id"] and body.role != "admin":
            cur.execute(
                "SELECT COUNT(*)::int AS admin_count FROM org_members WHERE org_id = %(org_id)s AND role = 'admin'",
                {"org_id": org_id},
            )
            if cur.fetchone()["admin_count"] <= 1:
                raise HTTPException(400, "Cannot demote the last admin")

        cur.execute(
            """
            UPDATE org_members SET role = %(role)s
            WHERE org_id = %(org_id)s AND user_id = %(user_id)s
            RETURNING user_id
            """,
            {"org_id": org_id, "user_id": member_id, "role": body.role},
        )
        if not cur.fetchone():
            raise HTTPException(404, "Member not found")
    return {"id": member_id, "role": body.role}
