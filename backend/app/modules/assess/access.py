"""Assess project access control: owner, direct user grants, or org grants."""

from __future__ import annotations

from fastapi import Depends, HTTPException

from app.shared.auth import get_current_user
from app.shared.database import db_cursor


def assess_access_where(alias: str = "p") -> str:
    """SQL predicate matching projects accessible to %(current_user_id)s."""
    return f"""(
        {alias}.owner_id = %(current_user_id)s
        OR EXISTS (
            SELECT 1 FROM assess_project_users apu
            WHERE apu.project_id = {alias}.id AND apu.user_id = %(current_user_id)s
        )
        OR EXISTS (
            SELECT 1 FROM assess_project_orgs apo
            JOIN org_members om ON om.org_id = apo.org_id
            WHERE apo.project_id = {alias}.id AND om.user_id = %(current_user_id)s
        )
    )"""


def _assert_assess_gate(
    project_id: str,
    user_id: str,
    *,
    forbidden_message: str,
    access_sql: str,
) -> None:
    # One round-trip: 404 if the project is missing, 403 if the predicate fails.
    params = {"id": project_id, "current_user_id": user_id}
    with db_cursor() as cur:
        cur.execute(
            f"""
            SELECT
                EXISTS(SELECT 1 FROM assess_projects WHERE id = %(id)s) AS exists,
                EXISTS(
                    SELECT 1 FROM assess_projects p
                    WHERE p.id = %(id)s AND ({access_sql})
                ) AS has_access
            """,
            params,
        )
        row = cur.fetchone()

    if not row or not row["exists"]:
        raise HTTPException(404, "Project not found")
    if not row["has_access"]:
        raise HTTPException(403, forbidden_message)


def require_assess_access(project_id: str, user: dict = Depends(get_current_user)) -> dict:
    _assert_assess_gate(
        project_id,
        user["id"],
        forbidden_message="You do not have access to this project",
        access_sql=assess_access_where("p"),
    )
    return user


def require_assess_admin(project_id: str, user: dict = Depends(get_current_user)) -> dict:
    _assert_assess_gate(
        project_id,
        user["id"],
        forbidden_message="Only project admins can do this",
        access_sql="""
            p.owner_id = %(current_user_id)s
            OR EXISTS (
                SELECT 1 FROM assess_project_users apu
                WHERE apu.project_id = p.id
                  AND apu.user_id = %(current_user_id)s
                  AND apu.role = 'admin'
            )
        """,
    )
    return user


def require_assess_owner(project_id: str, user: dict = Depends(get_current_user)) -> dict:
    _assert_assess_gate(
        project_id,
        user["id"],
        forbidden_message="Only the project owner can do this",
        access_sql="p.owner_id = %(current_user_id)s",
    )
    return user


def get_mel_project(project_id: str) -> dict:
    """Load a MEL assess project or raise 404."""
    with db_cursor() as cur:
        cur.execute(
            """
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
            WHERE p.id = %(id)s AND p.kind = 'mel'
            """,
            {"id": project_id},
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "MEL project not found")
    return row


def mel_project_to_dict(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "owner_id": str(row["owner_id"]),
        "owner_name": row.get("owner_name") or "",
        "owner_email": row.get("owner_email") or "",
        "description": row.get("description") or "",
        "status": row["status"],
        "kind": row["kind"],
        "plan_count": int(row.get("plan_count") or 0),
        "form_count": int(row.get("form_count") or 0),
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


def get_mel_plan(plan_id: str, *, project_id: str | None = None) -> dict:
    """Load a MEL plan (optionally scoped to a project) or raise 404."""
    with db_cursor() as cur:
        if project_id:
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
                WHERE mp.id = %(id)s AND mp.project_id = %(project_id)s
                """,
                {"id": plan_id, "project_id": project_id},
            )
        else:
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
                WHERE mp.id = %(id)s
                """,
                {"id": plan_id},
            )
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "MEL plan not found")
    return row


def mel_plan_to_dict(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "project_id": str(row["project_id"]),
        "name": row["name"],
        "intervention_slug": row["intervention_slug"],
        "plan_json": row.get("plan_json"),
        "form_count": int(row.get("form_count") or 0),
        "created_by": str(row["created_by"]) if row.get("created_by") else None,
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }
