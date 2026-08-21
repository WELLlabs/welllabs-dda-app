"""Auth routes: FastAPI Users register / login / verify / reset / Google OAuth."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.shared.auth import get_current_user
from app.shared.config import settings
from app.shared.users.auth_setup import (
    auth_backend,
    fastapi_users,
    google_oauth_client,
    oauth_auth_backend,
)
from app.shared.users.schemas import UserCreate, UserRead, UserUpdate

router = APIRouter()

# Email/password registration (no session until verify + login)
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
)

# Cookie JWT login / logout (form: username=email, password=...)
# requires_verification=True → unverified users cannot obtain a session cookie
router.include_router(
    fastapi_users.get_auth_router(auth_backend, requires_verification=True),
)

# Email verification
router.include_router(
    fastapi_users.get_verify_router(UserRead),
)

# Forgot / reset password
router.include_router(
    fastapi_users.get_reset_password_router(),
)

# Optional user self-service
router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
)


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    """Stable session probe used by the frontend."""
    return user


if google_oauth_client is not None:
    # Production: pin callback to FRONTEND_ORIGIN so Cloudflare/nginx Host/proto
    # quirks cannot produce redirect_uri_mismatch (saw http://dda.welllabs.org/...).
    # Local: omit redirect_url so Vite :5173/:5174 both work via X-Forwarded-Host.
    oauth_kwargs: dict = {
        "associate_by_email": True,
        "is_verified_by_default": True,
        "csrf_token_cookie_secure": settings.session_cookie_secure,
    }
    if settings.public_app_origin.startswith("https://"):
        oauth_kwargs["redirect_url"] = (
            f"{settings.public_app_origin}/api/accounts/auth/google/callback"
        )
    router.include_router(
        fastapi_users.get_oauth_router(
            google_oauth_client,
            oauth_auth_backend,
            settings.auth_jwt_secret,
            **oauth_kwargs,
        ),
        prefix="/google",
    )
