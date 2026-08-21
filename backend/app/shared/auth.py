"""Current-user dependency shared across modules.

Wraps FastAPI Users so callers keep receiving a plain dict:
`{id, email, name, created_at}`.
"""

from __future__ import annotations

from fastapi import Depends

from app.shared.users.auth_setup import current_active_verified_user
from app.shared.users.db import User


def user_to_dict(user: User) -> dict:
    created = getattr(user, "created_at", None)
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name or "",
        "created_at": created.isoformat() if created is not None else None,
    }


async def get_current_user(user: User = Depends(current_active_verified_user)) -> dict:
    """Require an active, email-verified user (Google users are verified by default)."""
    return user_to_dict(user)


CurrentUser = Depends(get_current_user)
