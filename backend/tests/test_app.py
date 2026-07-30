"""Application-level smoke tests."""

from __future__ import annotations


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_auth_me_requires_login(client):
    response = client.get("/api/accounts/auth/me")
    assert response.status_code == 401
