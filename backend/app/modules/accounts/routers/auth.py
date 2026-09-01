"""Auth routes: FastAPI Users register / login / verify / reset / Google OAuth."""

from __future__ import annotations

import html
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi_users.router.oauth import (
    CSRF_TOKEN_COOKIE_NAME,
    CSRF_TOKEN_KEY,
    generate_csrf_token,
    generate_state_token,
)

from app.shared.auth import get_current_user
from app.shared.config import settings
from app.shared.oauth_redirect import oauth_callback_redirect_uri
from app.shared.users.auth_setup import (
    auth_backend,
    fastapi_users,
    google_oauth_client,
    oauth_auth_backend,
)
from app.shared.users.google_oauth_router import get_google_oauth_router
from app.shared.users.manager import get_user_manager
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
    # Browser-friendly OAuth entry (sets CSRF cookie + redirects to Google).
    # Prefer over /authorize JSON for sign-in buttons — avoids fetch/cookie edge cases.
    @router.get("/google/start")
    async def google_oauth_browser_start(request: Request) -> HTMLResponse:
        """Start Google OAuth in the browser.

        Returns HTML with a client-side redirect instead of HTTP 302.
        Cloudflare (and some other proxies) follow 302s to Google server-side
        and serve accounts.google.com HTML on our domain — that breaks the
        account picker and leaves the CSRF cookie unset.
        """
        redirect_uri = oauth_callback_redirect_uri(request)
        csrf_token = generate_csrf_token()
        state_data = {CSRF_TOKEN_KEY: csrf_token}
        state = generate_state_token(state_data, settings.auth_jwt_secret)
        authorization_url = await google_oauth_client.get_authorization_url(
            redirect_uri,
            state,
            None,
            extras_params={"prompt": "select_account"},
        )
        safe_meta_url = html.escape(authorization_url, quote=True)
        safe_js_url = json.dumps(authorization_url)
        response = HTMLResponse(
            content=f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0;url={safe_meta_url}">
<title>Redirecting to Google…</title>
</head><body>
<p>Redirecting to Google sign-in…</p>
<script>window.location.replace({safe_js_url});</script>
</body></html>""",
            status_code=200,
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["CDN-Cache-Control"] = "no-store"
        response.headers["X-OAuth-Redirect-Uri"] = redirect_uri
        response.set_cookie(
            CSRF_TOKEN_COOKIE_NAME,
            csrf_token,
            max_age=3600,
            path="/",
            secure=settings.session_cookie_secure,
            httponly=True,
            samesite="lax",
        )
        return response

    router.include_router(
        get_google_oauth_router(
            google_oauth_client,
            oauth_auth_backend,
            get_user_manager,
            settings.auth_jwt_secret,
            associate_by_email=True,
            is_verified_by_default=True,
            csrf_token_cookie_secure=settings.session_cookie_secure,
        ),
        prefix="/google",
    )
