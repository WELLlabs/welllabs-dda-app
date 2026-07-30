"""Design module API smoke tests."""

from __future__ import annotations


def test_design_status(client):
    response = client.get("/api/design/status")
    assert response.status_code == 200
    data = response.json()
    assert data["module"] == "design"
    assert data["status"] == "not_implemented"
