"""Assess module API smoke tests."""

from __future__ import annotations


def test_assess_status(client):
    response = client.get("/api/assess/status")
    assert response.status_code == 200
    data = response.json()
    assert data["module"] == "assess"
    assert data["status"] == "not_implemented"
