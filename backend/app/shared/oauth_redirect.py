"""OAuth callback URL helpers — align Google redirect_uri with the browser origin."""

from __future__ import annotations

from httpx_oauth.integrations.fastapi import OAuth2AuthorizeCallback
from starlette.requests import Request

from app.shared.config import settings


def _request_host(request: Request) -> str | None:
    """Public host from proxy headers or Host (beta vs prod on shared nginx)."""
    forwarded = request.headers.get("x-forwarded-host")
    host = request.headers.get("host")
    value = (forwarded or host or "").split(",")[0].strip()
    return value or None


def _request_proto(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-proto")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.url.scheme:
        return request.url.scheme
    return "https"


def request_public_app_base(request: Request) -> str:
    """Browser-visible app base (origin + /wst) for redirects after OAuth errors."""
    host = _request_host(request)
    if host:
        return f"{_request_proto(request)}://{host}{settings.frontend_base_path}"
    return settings.public_app_base


def oauth_callback_redirect_uri(request: Request | None = None) -> str:
    """Public Google OAuth callback URL (must match token exchange redirect_uri)."""
    path = f"{settings.api_public_prefix}/accounts/auth/google/callback"
    if request is not None:
        host = _request_host(request)
        if host:
            return f"{_request_proto(request)}://{host}{path}"
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
