"""OAuth redirect URI helpers."""

from __future__ import annotations

from app.shared.config import settings
from app.shared.oauth_redirect import oauth_callback_redirect_uri


class _FakeRequest:
    def __init__(self, headers: dict[str, str]):
        self.headers = headers


def test_oauth_callback_redirect_uri_uses_forwarded_host_for_local_dev(monkeypatch):
    monkeypatch.setattr("app.shared.oauth_redirect.settings.frontend_origin", "http://localhost:5173")
    request = _FakeRequest(
        {
            "x-forwarded-host": "127.0.0.1:5174",
            "x-forwarded-proto": "http",
        }
    )
    uri = oauth_callback_redirect_uri(request)
    assert uri == "http://127.0.0.1:5174/wst/backend/accounts/auth/google/callback"


def test_oauth_callback_redirect_uri_uses_frontend_origin_for_deployed_env(monkeypatch):
    monkeypatch.setattr("app.shared.oauth_redirect.settings.frontend_origin", "https://beta.welllabs.org")
    request = _FakeRequest({"host": "beta.welllabs.org", "x-forwarded-proto": "https"})
    uri = oauth_callback_redirect_uri(request)
    assert uri == "https://beta.welllabs.org/wst/backend/accounts/auth/google/callback"


def test_oauth_callback_redirect_uri_overrides_frontend_origin_when_host_differs(monkeypatch):
    monkeypatch.setattr("app.shared.oauth_redirect.settings.frontend_origin", "https://ai.welllabs.org")
    request = _FakeRequest(
        {
            "x-wst-public-host": "beta.welllabs.org",
            "host": "127.0.0.1:8080",
            "x-forwarded-proto": "https",
        }
    )
    uri = oauth_callback_redirect_uri(request)
    assert uri == "https://beta.welllabs.org/wst/backend/accounts/auth/google/callback"


def test_oauth_callback_redirect_uri_without_request_uses_settings(monkeypatch):
    monkeypatch.setattr("app.shared.oauth_redirect.settings.frontend_origin", "https://ai.welllabs.org")
    uri = oauth_callback_redirect_uri(None)
    assert uri == "https://ai.welllabs.org/wst/backend/accounts/auth/google/callback"
