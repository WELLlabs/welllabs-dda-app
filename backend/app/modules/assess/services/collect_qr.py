"""ODK Collect QR helpers for MEL forms.

Collect expects a zlib-compressed, base64-encoded JSON settings blob.
App Users yield a /v1/key/{token}/projects/{id} server URL that Collect can use
without embedding Central admin credentials.
"""

from __future__ import annotations

import base64
import json
import logging
import zlib
from typing import Any

from app.shared.config import settings
from app.shared.database import db_cursor
from app.shared.integrations.odk import ODKClient
from app.shared.integrations.odk.exceptions import ODKAPIError

logger = logging.getLogger(__name__)

MEL_APP_USER_NAME = "WELL Labs MEL Collect"
APP_USER_ROLE_NAMES = {"App User", "app user"}


def encode_collect_settings(settings_dict: dict[str, Any]) -> str:
    raw = json.dumps(settings_dict, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.b64encode(zlib.compress(raw)).decode("ascii")


def build_collect_settings(
    *,
    token: str,
    odk_project_id: int,
    project_name: str,
    base_url: str | None = None,
) -> dict[str, Any]:
    base = (base_url or settings.odk_base_url or "").rstrip("/")
    server_url = f"{base}/v1/key/{token}/projects/{odk_project_id}"
    name = (project_name or "WELL Labs MEL").strip()[:64] or "WELL Labs MEL"
    return {
        "general": {
            "server_url": server_url,
            "form_update_mode": "match_exactly",
            "autosend": "wifi_and_cellular",
        },
        "project": {
            "name": name,
            "icon": "M",
            "color": "#16a34a",
        },
        "admin": {},
    }


def _load_stored_app_user(odk_project_id: int) -> dict | None:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT odk_project_id, app_user_id, display_name, token
            FROM mel_odk_app_users
            WHERE odk_project_id = %(odk_project_id)s
            """,
            {"odk_project_id": odk_project_id},
        )
        return cur.fetchone()


def _store_app_user(
    *,
    odk_project_id: int,
    app_user_id: int,
    display_name: str,
    token: str,
) -> None:
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO mel_odk_app_users (
                odk_project_id, app_user_id, display_name, token, updated_at
            )
            VALUES (
                %(odk_project_id)s, %(app_user_id)s, %(display_name)s, %(token)s, now()
            )
            ON CONFLICT (odk_project_id) DO UPDATE SET
                app_user_id = EXCLUDED.app_user_id,
                display_name = EXCLUDED.display_name,
                token = EXCLUDED.token,
                updated_at = now()
            """,
            {
                "odk_project_id": odk_project_id,
                "app_user_id": app_user_id,
                "display_name": display_name,
                "token": token,
            },
        )


async def _resolve_app_user_role_id(client: ODKClient) -> int | None:
    try:
        roles = await client.get("/v1/roles")
    except ODKAPIError as exc:
        logger.warning("Could not list ODK roles: %s", exc)
        return None
    if not isinstance(roles, list):
        return None
    for role in roles:
        if not isinstance(role, dict):
            continue
        name = str(role.get("name") or "").strip()
        if name in APP_USER_ROLE_NAMES or name.lower() == "app user":
            try:
                return int(role["id"])
            except (KeyError, TypeError, ValueError):
                continue
    # Central's built-in App User role is commonly id=2
    return 2


async def ensure_mel_app_user(client: ODKClient, odk_project_id: int) -> dict:
    """Return {appUserId, token, displayName} for the shared MEL Collect app user."""
    stored = _load_stored_app_user(odk_project_id)
    if stored and stored.get("token"):
        return {
            "appUserId": int(stored["app_user_id"]),
            "token": stored["token"],
            "displayName": stored.get("display_name") or MEL_APP_USER_NAME,
        }

    created = await client.post(
        f"/v1/projects/{odk_project_id}/app-users",
        json={"displayName": MEL_APP_USER_NAME},
    )
    if not isinstance(created, dict) or not created.get("token"):
        raise ODKAPIError(502, "ODK did not return an App User token")

    app_user_id = int(created["id"])
    token = str(created["token"])
    display_name = str(created.get("displayName") or MEL_APP_USER_NAME)
    _store_app_user(
        odk_project_id=odk_project_id,
        app_user_id=app_user_id,
        display_name=display_name,
        token=token,
    )
    return {"appUserId": app_user_id, "token": token, "displayName": display_name}


async def assign_form_to_app_user(
    client: ODKClient,
    *,
    odk_project_id: int,
    xml_form_id: str,
    app_user_id: int,
    role_id: int | None = None,
) -> None:
    role = role_id if role_id is not None else await _resolve_app_user_role_id(client)
    if role is None:
        logger.warning("No App User role id; skipping form assignment for %s", xml_form_id)
        return
    path = f"/v1/projects/{odk_project_id}/forms/{xml_form_id}/assignments/{role}/{app_user_id}"
    try:
        await client.post(path)
    except ODKAPIError as exc:
        # Already assigned / conflict is fine
        if getattr(exc, "status_code", None) in (409, 403):
            logger.info("Form assignment skipped (%s): %s", exc.status_code, xml_form_id)
            return
        # Some Central versions return 409 as generic error text
        msg = str(exc).lower()
        if "already" in msg or "conflict" in msg:
            return
        logger.warning("Form assignment failed for %s: %s", xml_form_id, exc)


async def build_mel_collect_qr(
    client: ODKClient,
    *,
    odk_project_id: int,
    project_name: str,
    xml_form_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Ensure app user, optionally assign forms, return Collect QR payload + metadata."""
    if not settings.odk_base_url:
        raise ODKAPIError(503, "ODK_BASE_URL is not configured")

    app_user = await ensure_mel_app_user(client, odk_project_id)
    role_id = await _resolve_app_user_role_id(client)
    for xml_form_id in xml_form_ids or []:
        await assign_form_to_app_user(
            client,
            odk_project_id=odk_project_id,
            xml_form_id=xml_form_id,
            app_user_id=app_user["appUserId"],
            role_id=role_id,
        )

    settings_dict = build_collect_settings(
        token=app_user["token"],
        odk_project_id=odk_project_id,
        project_name=project_name,
    )
    payload = encode_collect_settings(settings_dict)
    return {
        "payload": payload,
        "serverUrl": settings_dict["general"]["server_url"],
        "projectName": settings_dict["project"]["name"],
        "odkProjectId": odk_project_id,
        "appUserId": app_user["appUserId"],
        "appUserName": app_user["displayName"],
        "instructions": (
            "Open ODK Collect → Projects → QR code → scan this code. "
            "Then use Get Blank Form and open the form listed above."
        ),
    }
