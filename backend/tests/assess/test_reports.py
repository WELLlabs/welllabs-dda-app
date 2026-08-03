"""Assess project reports endpoint."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from app.main import app
from app.modules.assess.access import require_assess_access


def _user():
    return {"id": str(uuid4()), "email": "user@example.com", "name": "User"}


@pytest.fixture
def reports_client(client):
    user = _user()
    app.dependency_overrides[require_assess_access] = lambda: user
    yield client, user
    app.dependency_overrides.pop(require_assess_access, None)


class TestGetProjectReport:
    def test_returns_503_when_embed_secret_missing(self, reports_client):
        client, _user = reports_client
        project_id = str(uuid4())
        with patch("app.modules.assess.routers.reports.settings") as settings:
            settings.metabase_embed_secret_key = ""
            response = client.get(f"/api/assess/projects/{project_id}/reports")
        assert response.status_code == 503
        assert response.json()["detail"] == "Metabase embedding is not configured"

    def test_delegates_to_metabase_service(self, reports_client):
        client, _user = reports_client
        project_id = str(uuid4())
        report = {
            "project_id": project_id,
            "project_name": "Demo",
            "dashboard_id": 42,
            "configured": True,
            "resource": "dashboard",
            "instance_url": "http://localhost:3000",
            "token": "signed.jwt.token",
            "expires_at": 1_700_000_000,
        }
        with (
            patch("app.modules.assess.routers.reports.settings") as settings,
            patch(
                "app.modules.assess.routers.reports.metabase_service.get_project_report",
                return_value=report,
            ) as get_report,
        ):
            settings.metabase_embed_secret_key = "test-secret"
            response = client.get(f"/api/assess/projects/{project_id}/reports")
        assert response.status_code == 200
        assert response.json() == report
        get_report.assert_called_once_with(project_id)

    def test_returns_unconfigured_payload(self, reports_client):
        client, _user = reports_client
        project_id = str(uuid4())
        report = {
            "project_id": project_id,
            "project_name": "Demo",
            "dashboard_id": None,
            "configured": False,
        }
        with (
            patch("app.modules.assess.routers.reports.settings") as settings,
            patch(
                "app.modules.assess.routers.reports.metabase_service.get_project_report",
                return_value=report,
            ),
        ):
            settings.metabase_embed_secret_key = "test-secret"
            response = client.get(f"/api/assess/projects/{project_id}/reports")
        assert response.status_code == 200
        assert response.json()["configured"] is False
