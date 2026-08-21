"""User lookup by email — the "verify a user exists before adding them" step,
shared by both diagnosis sharing and org member invites.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.shared.auth import get_current_user
from app.shared.database import db_cursor

router = APIRouter()


@router.get("/lookup")
def lookup_user(email: str = Query(..., min_length=1), _user: dict = Depends(get_current_user)):
    normalized = email.lower().strip()
    with db_cursor() as cur:
        cur.execute("SELECT id, email, name FROM users WHERE email = %(email)s", {"email": normalized})
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "No account found with that email")
    return {"id": str(row["id"]), "email": row["email"], "name": row["name"]}
