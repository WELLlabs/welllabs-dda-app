"""FastAPI Users authentication backends."""

from __future__ import annotations

import html
import json
import logging
import uuid
from typing import Any, cast

from fastapi_users import FastAPIUsers
from fastapi_users.authentication import (
    AuthenticationBackend,
    CookieTransport,
    JWTStrategy,
)
from httpx_oauth.clients.google import GoogleOAuth2
from httpx_oauth.exceptions import GetIdEmailError
from starlette.responses import HTMLResponse, Response

from app.shared.config import settings
from app.shared.users.db import User
from app.shared.users.manager import get_user_manager, oauth_needs_name_setup

logger = logging.getLogger(__name__)

_COOKIE_MAX_AGE = settings.session_ttl_days * 24 * 60 * 60
_GOOGLE_USERINFO_URLS = (
    "https://www.googleapis.com/oauth2/v3/userinfo",
    "https://openidconnect.googleapis.com/v1/userinfo",
    "https://www.googleapis.com/oauth2/v2/userinfo",
)


class GoogleOAuth2UserInfo(GoogleOAuth2):
    """Resolve Google identity via OAuth2 userinfo (not People API)."""

    async def get_id_email(self, token: str) -> tuple[str, str | None]:
        last_response = None
        async with self.get_httpx_client() as client:
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            for url in _GOOGLE_USERINFO_URLS:
                response = await client.get(url, headers=headers)
                last_response = response
                if response.status_code >= 400:
                    logger.error(
                        "Google userinfo failed %s status=%s body=%s",
                        url,
                        response.status_code,
                        response.text[:400],
                    )
                    continue
                profile = cast(dict[str, Any], response.json())
                sub = profile.get("sub") or profile.get("id")
                if not sub:
                    logger.error("Google userinfo missing sub/id: %s", profile)
                    continue
                return str(sub), profile.get("email")

            # Last resort: tokeninfo endpoint
            response = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"access_token": token},
            )
            last_response = response
            if response.status_code < 400:
                profile = cast(dict[str, Any], response.json())
                sub = profile.get("sub") or profile.get("user_id")
                if sub:
                    return str(sub), profile.get("email")
            logger.error(
                "Google tokeninfo failed status=%s body=%s",
                response.status_code,
                response.text[:400],
            )

        raise GetIdEmailError(response=last_response)


cookie_transport = CookieTransport(
    cookie_name=settings.session_cookie_name,
    cookie_max_age=_COOKIE_MAX_AGE,
    cookie_secure=settings.session_cookie_secure,
    cookie_httponly=True,
    cookie_samesite="lax",
)


class RedirectCookieTransport(CookieTransport):
    """Cookie login that redirects to the app (browser OAuth callback)."""

    def __init__(self, *args, post_login_redirect_url: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.post_login_redirect_url = post_login_redirect_url

    async def get_login_response(self, token: str) -> Response:
        base = settings.frontend_base_path  # "/wst" (matches kit.paths.base)
        origin = settings.public_app_origin
        if oauth_needs_name_setup.get():
            dest = f"{origin}{base}/complete-profile"
        elif self.post_login_redirect_url.startswith("http"):
            dest = self.post_login_redirect_url
        else:
            dest = f"{origin}{self.post_login_redirect_url}"
        safe_meta_url = html.escape(dest, quote=True)
        safe_js_url = json.dumps(dest)
        response = HTMLResponse(
            content=f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0;url={safe_meta_url}">
<title>Signing you in…</title>
</head><body>
<p>Signing you in…</p>
<script>window.location.replace({safe_js_url});</script>
</body></html>""",
            status_code=200,
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["CDN-Cache-Control"] = "no-store"
        response.set_cookie(
            self.cookie_name,
            token,
            max_age=self.cookie_max_age,
            path=self.cookie_path,
            domain=self.cookie_domain,
            secure=self.cookie_secure,
            httponly=self.cookie_httponly,
            samesite=self.cookie_samesite,
        )
        return response


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(
        secret=settings.auth_jwt_secret,
        lifetime_seconds=_COOKIE_MAX_AGE,
    )


auth_backend = AuthenticationBackend(
    name="cookie",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

# Same JWT audience ("cookie") so /me works; redirect transport for Google only
_oauth_home = f"{settings.frontend_base_path}/home" if settings.frontend_base_path else "/home"
oauth_auth_backend = AuthenticationBackend(
    name="cookie",
    transport=RedirectCookieTransport(
        cookie_name=settings.session_cookie_name,
        cookie_max_age=_COOKIE_MAX_AGE,
        cookie_secure=settings.session_cookie_secure,
        cookie_httponly=True,
        cookie_samesite="lax",
        post_login_redirect_url=_oauth_home,
    ),
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

current_active_verified_user = fastapi_users.current_user(active=True, verified=True)
current_active_user = fastapi_users.current_user(active=True)

google_oauth_client: GoogleOAuth2 | None = None
if settings.google_oauth_client_id and settings.google_oauth_client_secret:
    google_oauth_client = GoogleOAuth2UserInfo(
        settings.google_oauth_client_id,
        settings.google_oauth_client_secret,
    )
