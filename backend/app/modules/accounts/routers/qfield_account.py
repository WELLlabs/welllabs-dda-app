"""Connect / disconnect a user's QField Cloud account (tokens stored on users)."""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.shared.auth import get_current_user
from app.shared.config import settings
from app.shared.database import db_cursor

logger = logging.getLogger(__name__)

router = APIRouter()


class QFieldConnectRequest(BaseModel):
    username: str
    password: str


@router.post("/connect")
def connect_qfield(body: QFieldConnectRequest, user: dict = Depends(get_current_user)):
    """Authenticate against QField Cloud and store the token on the user row."""
    login_url = settings.qfield_cloud_url.rstrip("/") + "/auth/login/"
    try:
        resp = httpx.post(
            login_url,
            json={"username": body.username, "password": body.password},
            headers={"User-Agent": "sdk|dda-product/1.0.0"},
            timeout=15,
        )
    except httpx.HTTPError as exc:
        logger.error("QField Cloud login request failed: %s", exc)
        raise HTTPException(502, "Could not reach QField Cloud. Try again later.") from exc

    if resp.status_code == 401:
        raise HTTPException(401, "Invalid QField Cloud username or password.")
    if resp.status_code != 200:
        logger.warning("QField Cloud login returned %d: %s", resp.status_code, resp.text[:300])
        raise HTTPException(502, f"QField Cloud returned status {resp.status_code}.")

    data = resp.json()
    token = data.get("token", "")
    expires_at = data.get("expires_at")

    if not token:
        raise HTTPException(502, "QField Cloud did not return a token.")

    with db_cursor() as cur:
        cur.execute(
            """
            UPDATE users
            SET qfield_username = %(qfu)s,
                qfield_token = %(tok)s,
                qfield_token_expires_at = %(exp)s
            WHERE id = %(uid)s
            """,
            {"uid": user["id"], "qfu": body.username, "tok": token, "exp": expires_at},
        )

    return {"connected": True, "qfield_username": body.username}


@router.get("/status")
def qfield_status(user: dict = Depends(get_current_user)):
    """Return whether the current user has a linked QField Cloud account."""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT qfield_username, qfield_token, qfield_token_expires_at AS expires_at
            FROM users WHERE id = %(uid)s
            """,
            {"uid": user["id"]},
        )
        row = cur.fetchone()

    if not row or not row.get("qfield_token"):
        return {"connected": False}

    return {
        "connected": True,
        "qfield_username": row["qfield_username"],
        "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
    }


@router.delete("/disconnect")
def disconnect_qfield(user: dict = Depends(get_current_user)):
    """Remove the stored QField Cloud token for this user."""
    with db_cursor() as cur:
        cur.execute(
            """
            UPDATE users
            SET qfield_username = NULL,
                qfield_token = NULL,
                qfield_token_expires_at = NULL
            WHERE id = %(uid)s
            """,
            {"uid": user["id"]},
        )
    return {"connected": False}
