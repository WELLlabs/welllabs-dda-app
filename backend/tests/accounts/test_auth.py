"""Accounts module: FastAPI Users schemas, routes, Brevo, CORS, forwarded host."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.modules.accounts.routers import auth as auth_router
from app.shared.config import Settings
from app.shared.forwarded_host import ForwardedHostMiddleware
from app.shared.users.brevo import send_email, send_verification_email
from app.shared.users.schemas import UserCreate, UserUpdate


def _collect_paths(routes) -> set[str]:
    paths: set[str] = set()

    def walk(rs):
        for r in rs:
            path = getattr(r, "path", None)
            if path:
                paths.add(path)
            nested = getattr(r, "routes", None)
            if nested is not None:
                walk(nested)
            original = getattr(r, "original_router", None)
            if original is not None and hasattr(original, "routes"):
                walk(original.routes)

    walk(routes)
    return paths


class TestUserCreate:
    def test_valid_register_payload(self):
        body = UserCreate(email="user@example.com", name="Test User", password="password123")
        assert body.email == "user@example.com"
        assert body.name == "Test User"

    def test_rejects_short_password(self):
        with pytest.raises(ValidationError):
            UserCreate(email="user@example.com", name="Test User", password="short")

    def test_rejects_invalid_email(self):
        with pytest.raises(ValidationError):
            UserCreate(email="not-an-email", name="Test User", password="password123")

    def test_rejects_empty_name(self):
        with pytest.raises(ValidationError):
            UserCreate(email="user@example.com", name="", password="password123")


class TestUserUpdate:
    def test_name_update(self):
        body = UserUpdate(name="New Name")
        assert body.name == "New Name"

    def test_rejects_empty_name(self):
        with pytest.raises(ValidationError):
            UserUpdate(name="")


class TestAuthRouterMount:
    def test_auth_routes_registered(self):
        paths = _collect_paths(auth_router.router.routes)
        assert "/register" in paths
        assert "/login" in paths
        assert "/logout" in paths
        assert "/me" in paths
        assert "/verify" in paths
        assert "/forgot-password" in paths
        assert "/reset-password" in paths
        assert "/request-verify-token" in paths


class TestCorsOrigins:
    def test_includes_vite_fallback_ports(self):
        s = Settings(frontend_origin="http://localhost:5173")
        origins = s.cors_origins
        assert "http://localhost:5173" in origins
        assert "http://localhost:5174" in origins
        assert "http://127.0.0.1:5173" in origins
        assert "http://127.0.0.1:5174" in origins


class TestForwardedHostMiddleware:
    def test_rewrites_host_from_x_forwarded_host(self):
        import asyncio

        seen = {}

        async def app(scope, receive, send):
            header_map = {k.decode(): v.decode() for k, v in scope["headers"]}
            seen["host"] = header_map.get("host")
            seen["server"] = scope.get("server")

        mw = ForwardedHostMiddleware(app)
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [
                (b"host", b"localhost:8080"),
                (b"x-forwarded-host", b"localhost:5174"),
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("localhost", 8080),
        }

        async def receive():
            return {"type": "http.disconnect"}

        async def send(_msg):
            return None

        asyncio.run(mw(scope, receive, send))
        assert seen["host"] == "localhost:5174"
        assert seen["server"] == ("localhost", 5174)


class TestBrevo:
    def test_skips_when_not_configured(self):
        import asyncio

        with patch("app.shared.users.brevo.settings") as mock_settings:
            mock_settings.brevo_api_key = ""
            mock_settings.brevo_sender_email = ""
            ok = asyncio.run(send_email(to_email="a@b.com", subject="Hi", html="<p>Hi</p>"))
            assert ok is False

    def test_send_posts_to_brevo(self):
        import asyncio

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"messageId": "<id@mail>"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.shared.users.brevo.settings") as mock_settings,
            patch("app.shared.users.brevo.httpx.AsyncClient", return_value=mock_client),
        ):
            mock_settings.brevo_api_key = "x-key"
            mock_settings.brevo_sender_email = "noreply@welllabs.org"
            mock_settings.brevo_sender_name = "Water Security Tool"
            mock_settings.frontend_origin = "http://localhost:5173"
            ok = asyncio.run(
                send_email(to_email="user@example.com", subject="Hi", html="<p>Hi</p>")
            )
            assert ok is True
            mock_client.post.assert_awaited_once()
            args, kwargs = mock_client.post.call_args
            assert args[0].endswith("/v3/smtp/email")
            assert kwargs["json"]["to"] == [{"email": "user@example.com"}]
            assert kwargs["headers"]["api-key"] == "x-key"

    def test_verification_email_includes_token_link(self):
        import asyncio

        with (
            patch("app.shared.users.brevo.settings") as mock_settings,
            patch(
                "app.shared.users.brevo.send_email", new_callable=AsyncMock
            ) as mock_send,
        ):
            mock_settings.frontend_origin = "http://localhost:5173"
            asyncio.run(send_verification_email("user@example.com", "tok123"))
            mock_send.assert_awaited_once()
            kwargs = mock_send.await_args.kwargs
            assert kwargs["to_email"] == "user@example.com"
            assert "tok123" in kwargs["html"]
            assert "/verify?token=tok123" in kwargs["html"]


class TestOpenApiAuthRoutes:
    def test_auth_paths_in_openapi(self, client):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        paths = response.json()["paths"]
        assert "/api/accounts/auth/register" in paths
        assert "/api/accounts/auth/login" in paths
        assert "/api/accounts/auth/logout" in paths
        assert "/api/accounts/auth/me" in paths
        assert "/api/accounts/auth/verify" in paths
        assert "/api/accounts/auth/forgot-password" in paths
        assert "/api/accounts/auth/reset-password" in paths

    def test_cors_allows_vite_5174(self, client):
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5174",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5174"
