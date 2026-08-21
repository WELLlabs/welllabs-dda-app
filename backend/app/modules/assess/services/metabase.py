"""Turns a project into an embeddable Metabase dashboard.

Guest embedding: the backend signs a short-lived JWT with the embedding secret
key, which never leaves the server. Routes go through get_project_report().
"""

from __future__ import annotations

import time

import jwt

from app.shared.config import settings
from app.shared.database import db_cursor

_TOKEN_TTL_SECONDS = 60 * 10  # 10 minutes


def _resolve_project_dashboard(project_id: str) -> tuple[str | None, int | None]:
    # Automatic dashboard creation would slot in here (create + persist when the
    # id is None) without changing callers, the endpoint, or the frontend.
    with db_cursor() as cur:
        cur.execute(
            "SELECT name, metabase_dashboard_id FROM assess_projects WHERE id = %(id)s",
            {"id": project_id},
        )
        row = cur.fetchone()
    if not row:
        return None, None
    return row["name"], row["metabase_dashboard_id"]


def _sign_dashboard_token(dashboard_id: int) -> tuple[str, int]:
    if not settings.metabase_embed_secret_key:
        raise RuntimeError("Metabase embedding is not configured")

    expires_at = round(time.time()) + _TOKEN_TTL_SECONDS
    payload = {
        "resource": {"dashboard": dashboard_id},
        "params": {},
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.metabase_embed_secret_key, algorithm="HS256")
    return token, expires_at


def get_project_report(project_id: str) -> dict:
    # Caller must have already authorized access. configured=False → the project
    # has no dashboard mapped yet and the frontend shows an empty state.
    project_name, dashboard_id = _resolve_project_dashboard(project_id)

    if not dashboard_id:
        return {
            "project_id": str(project_id),
            "project_name": project_name,
            "dashboard_id": None,
            "configured": False,
        }

    token, expires_at = _sign_dashboard_token(dashboard_id)
    return {
        "project_id": str(project_id),
        "project_name": project_name,
        "dashboard_id": dashboard_id,
        "configured": True,
        "resource": "dashboard",
        "instance_url": settings.metabase_public_url,
        "token": token,
        "expires_at": expires_at,
    }
