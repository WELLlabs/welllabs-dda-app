"""Application-level smoke tests for app.main."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_auth_me_requires_login(client):
    response = client.get("/api/accounts/auth/me")
    assert response.status_code == 401


def test_openapi_includes_assess_routes(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/health" in paths
    assert "/api/assess/status" in paths
    assert "/api/assess/projects" in paths
    assert "/api/assess/projects/{project_id}/reports" in paths
    assert "/api/assess/projects/{project_id}/access/users" in paths


def test_cors_allows_configured_frontend_origin(client):
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_lifespan_initializes_and_closes_pool():
    with (
        patch("app.main.init_pool") as init_pool,
        patch("app.main.close_pool") as close_pool,
    ):
        from app.main import app

        with TestClient(app, raise_server_exceptions=True):
            init_pool.assert_called_once_with(min_size=2, max_size=10)
        close_pool.assert_called_once()
