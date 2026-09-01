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


def test_oauth_callback_redirect_uri_uses_wst_public_host_header():
    request = _FakeRequest(
        {
            "x-wst-public-host": "beta.welllabs.org",
            "host": "127.0.0.1:8080",
            "x-forwarded-proto": "https",
        }
    )
    uri = oauth_callback_redirect_uri(request)
    assert uri == "https://beta.welllabs.org/wst/backend/accounts/auth/google/callback"


def test_oauth_callback_redirect_uri_uses_host_when_forwarded_missing():
    request = _FakeRequest({"host": "beta.welllabs.org", "x-forwarded-proto": "https"})
    uri = oauth_callback_redirect_uri(request)
    assert uri == "https://beta.welllabs.org/wst/backend/accounts/auth/google/callback"


def test_oauth_callback_redirect_uri_falls_back_to_settings():
    uri = oauth_callback_redirect_uri(None)
    assert uri.endswith("/wst/backend/accounts/auth/google/callback")
