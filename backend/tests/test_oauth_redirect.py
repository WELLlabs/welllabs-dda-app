"""OAuth redirect URI helpers."""

from __future__ import annotations

from app.shared.oauth_redirect import oauth_callback_redirect_uri


class _FakeRequest:
    def __init__(self, headers: dict[str, str]):
        self.headers = headers


def test_oauth_callback_redirect_uri_uses_forwarded_host():
    request = _FakeRequest(
        {
            "x-forwarded-host": "127.0.0.1:5174",
            "x-forwarded-proto": "http",
        }
    )
    uri = oauth_callback_redirect_uri(request)
    assert uri == "http://127.0.0.1:5174/wst/backend/accounts/auth/google/callback"


def test_oauth_callback_redirect_uri_falls_back_to_settings():
    uri = oauth_callback_redirect_uri(None)
    assert uri.endswith("/wst/backend/accounts/auth/google/callback")
