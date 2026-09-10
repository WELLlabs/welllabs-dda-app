"""OAuth callback URL helpers — align Google redirect_uri with the browser origin."""

from __future__ import annotations

from urllib.parse import urlparse

from httpx_oauth.integrations.fastapi import OAuth2AuthorizeCallback
from starlette.requests import Request

from app.shared.config import settings


def _hostname(host: str) -> str:
    return host.split(",")[0].strip().split(":")[0].lower()


def _is_local_hostname(host: str) -> bool:
    return _hostname(host) in ("localhost", "127.0.0.1")


def _is_local_dev_deployment() -> bool:
    return _is_local_hostname(urlparse(settings.public_app_origin).netloc or "")


def _request_host(request: Request) -> str | None:
    """Public host from nginx / proxy headers or Host."""
    for header in ("x-wst-public-host", "x-forwarded-host", "host"):
        raw = request.headers.get(header)
        if not raw:
            continue
        host = raw.split(",")[0].strip()
        if host:
            return host
    return None


def _request_proto(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-proto")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.url.scheme:
        return request.url.scheme
    return "https"


def _callback_path() -> str:
    return f"{settings.api_public_prefix}/accounts/auth/google/callback"


def oauth_callback_redirect_uri(request: Request | None = None) -> str:
    """Public Google OAuth callback URL (must match token exchange redirect_uri).

    Deployed environments: ``FRONTEND_ORIGIN`` in Secrets Manager / .env is the
    default (``settings.api_public_origin``). Local Vite and shared nginx boxes
    that serve multiple public hostnames use the incoming request Host instead.
    """
    path = _callback_path()
    configured = settings.api_public_origin

    if request is not None:
        host = _request_host(request)
        if host:
            proto = _request_proto(request)
            if _is_local_dev_deployment() or _is_local_hostname(host):
                return f"{proto}://{host}{path}"
            configured_host = urlparse(settings.public_app_origin).netloc
            if configured_host and _hostname(host) != _hostname(configured_host):
                return f"{proto}://{host}{path}"

    return f"{configured}/accounts/auth/google/callback"


def request_public_app_base(request: Request) -> str:
    """Browser-visible app base (origin + /wst) for redirects after OAuth errors."""
    callback = oauth_callback_redirect_uri(request)
    prefix = _callback_path()
    if callback.endswith(prefix):
        return callback[: -len(prefix)]
    return settings.public_app_base


class RequestAwareOAuth2AuthorizeCallback(OAuth2AuthorizeCallback):
    """Token exchange uses the same redirect_uri as /google/start."""

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
