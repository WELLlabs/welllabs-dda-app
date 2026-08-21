"""Shared users package (FastAPI Users)."""

from app.shared.users.auth_setup import (
    auth_backend,
    current_active_user,
    current_active_verified_user,
    fastapi_users,
    google_oauth_client,
)
from app.shared.users.db import User

__all__ = [
    "User",
    "auth_backend",
    "current_active_user",
    "current_active_verified_user",
    "fastapi_users",
    "google_oauth_client",
]
