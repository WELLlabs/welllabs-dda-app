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
