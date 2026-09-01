"""OAuth callback URL helpers — align Google redirect_uri with the browser origin."""

from __future__ import annotations

from httpx_oauth.integrations.fastapi import OAuth2AuthorizeCallback
from starlette.requests import Request

from app.shared.config import settings


def oauth_callback_redirect_uri(request: Request | None = None) -> str:
    """Public Google OAuth callback URL (must match token exchange redirect_uri)."""
    path = f"{settings.api_public_prefix}/accounts/auth/google/callback"
    if request is not None:
        forwarded_host = request.headers.get("x-forwarded-host")
        if forwarded_host:
            proto = (request.headers.get("x-forwarded-proto") or "http").split(",")[0].strip()
            host = forwarded_host.split(",")[0].strip()
            return f"{proto}://{host}{path}"
    return f"{settings.api_public_origin}/accounts/auth/google/callback"


class RequestAwareOAuth2AuthorizeCallback(OAuth2AuthorizeCallback):
    """Token exchange uses the same redirect_uri as /google/start (Vite port/host)."""

    async def __call__(
        self,
        request: Request,
        code: str | None = None,
        code_verifier: str | None = None,
        state: str | None = None,
        error: str | None = None,
    ):
        self.redirect_url = oauth_callback_redirect_uri(request)
        return await super().__call__(request, code, code_verifier, state, error)
