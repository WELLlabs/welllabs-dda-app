"""Assess module router tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.main import app
from app.modules.assess.routers import assess as assess_router
from app.shared.auth import get_current_user
from app.shared.integrations.odk.exceptions import ODKAPIError, ODKAuthFailed, ODKConnectionError


def _user():
    return {"id": str(uuid4()), "email": "user@example.com", "name": "User"}


def _db_cursor_mock(fetchone=None, fetchall=None, fetchone_side_effect=None):
    mock_cur = MagicMock()
    if fetchone_side_effect is not None:
        mock_cur.fetchone.side_effect = fetchone_side_effect
    else:
        mock_cur.fetchone.return_value = fetchone
    mock_cur.fetchall.return_value = fetchall or []
    ctx = MagicMock()
    ctx.__enter__.return_value = mock_cur
    ctx.__exit__.return_value = False
    return ctx, mock_cur


@pytest.fixture
def auth_client(client):
    user = _user()
    app.dependency_overrides[get_current_user] = lambda: user
    yield client, user
    app.dependency_overrides.pop(get_current_user, None)


class TestAssessStatus:
    def test_assess_status(self, client):
        response = client.get("/api/assess/status")
        assert response.status_code == 200
        data = response.json()
        assert data["module"] == "assess"
        assert data["status"] == "not_implemented"


class TestAssessProjectToDict:
    def test_serializes_row(self):
        project_id = uuid4()
        owner_id = uuid4()
        created = datetime(2024, 3, 1, 10, 0, tzinfo=timezone.utc)
        updated = datetime(2024, 3, 2, 11, 0, tzinfo=timezone.utc)
        row = {
            "id": project_id,
            "name": "Watershed A",
            "owner_id": owner_id,
            "description": "desc",
            "status": "active",
            "odk_project_id": "42",
            "metabase_dashboard_id": 7,
            "created_at": created,
            "updated_at": updated,
        }
        assert assess_router._assess_project_to_dict(row) == {
            "id": str(project_id),
            "name": "Watershed A",
            "owner_id": str(owner_id),
            "description": "desc",
            "status": "active",
            "odk_project_id": "42",
            "metabase_dashboard_id": 7,
            "created_at": created.isoformat(),
            "updated_at": updated.isoformat(),
        }

    def test_metabase_dashboard_id_defaults_to_none(self):
        created = datetime(2024, 3, 1, 10, 0, tzinfo=timezone.utc)
        row = {
            "id": uuid4(),
            "name": "P",
            "owner_id": uuid4(),
            "description": None,
            "status": "active",
            "odk_project_id": "1",
            "created_at": created,
            "updated_at": created,
        }
        assert assess_router._assess_project_to_dict(row)["metabase_dashboard_id"] is None


class TestSyncProjectsToDb:
    def test_upserts_each_project(self):
        owner_id = str(uuid4())
        synced_row = {"id": uuid4(), "name": "Alpha", "odk_project_id": "10"}
        ctx, cur = _db_cursor_mock(fetchone=synced_row)
        with patch("app.modules.assess.routers.assess.db_cursor", return_value=ctx):
            result = assess_router._sync_projects_to_db(
                [{"id": 10, "name": "Alpha"}, {"id": 11}],
                owner_id,
            )
        assert result == [synced_row, synced_row]
        assert cur.execute.call_count == 2
        second_params = cur.execute.call_args_list[1].args[1]
        assert second_params["name"] == "ODK Project 11"
        assert second_params["odk_project_id"] == "11"
        assert second_params["owner_id"] == owner_id


class TestGetAssessProjectOdkId:
    def test_returns_row(self):
        project_id = uuid4()
        owner_id = str(uuid4())
        row = {"odk_project_id": "55"}
        ctx, _cur = _db_cursor_mock(fetchone=row)
        with patch("app.modules.assess.routers.assess.db_cursor", return_value=ctx):
            assert assess_router._get_assess_project_odk_id(project_id, owner_id) == row

    def test_returns_none_when_missing(self):
        ctx, _cur = _db_cursor_mock(fetchone=None)
        with patch("app.modules.assess.routers.assess.db_cursor", return_value=ctx):
            assert assess_router._get_assess_project_odk_id(uuid4(), str(uuid4())) is None


class TestOdkProjectsEndpoint:
    def test_syncs_odk_projects(self, auth_client):
        client, user = auth_client
        odk_data = [{"id": 1, "name": "P1"}]
        synced = [{"id": str(uuid4()), "name": "P1", "odk_project_id": "1"}]
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=odk_data)
        # Patch the DB helper (not anyio.to_thread.run_sync) so FastAPI sync
        # dependency resolution keeps using real anyio.
        with (
            patch("app.modules.assess.routers.assess.ODKClient", return_value=mock_client),
            patch(
                "app.modules.assess.routers.assess._sync_projects_to_db",
                return_value=synced,
            ) as sync_mock,
        ):
            response = client.get("/api/assess/odk/projects")
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["data"] == odk_data
        assert body["synced"] == synced
        sync_mock.assert_called_once_with(odk_data, user["id"])

    @pytest.mark.parametrize(
        "exc,status,detail",
        [
            (ODKConnectionError("down"), 502, "Could not reach ODK Central. Try again later."),
            (ODKAuthFailed("bad creds"), 502, "ODK Central authentication failed."),
            (ODKAPIError(404, "missing"), 404, "ODK API error"),
        ],
    )
    def test_maps_odk_errors(self, auth_client, exc, status, detail):
        client, _user = auth_client
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=exc)
        with patch("app.modules.assess.routers.assess.ODKClient", return_value=mock_client):
            response = client.get("/api/assess/odk/projects")
        assert response.status_code == status
        assert response.json()["detail"] == detail


class TestListAssessProjects:
    def test_returns_accessible_projects(self, auth_client):
        client, user = auth_client
        project_id = uuid4()
        created = datetime(2024, 4, 1, tzinfo=timezone.utc)
        ctx, cur = _db_cursor_mock(
            fetchall=[
                {
                    "id": project_id,
                    "name": "Accessible",
                    "owner_id": user["id"],
                    "description": None,
                    "status": "active",
                    "odk_project_id": "9",
                    "metabase_dashboard_id": None,
                    "created_at": created,
                    "updated_at": created,
                }
            ]
        )
        with patch("app.modules.assess.routers.assess.db_cursor", return_value=ctx):
            response = client.get("/api/assess/projects")
        assert response.status_code == 200
        projects = response.json()["projects"]
        assert len(projects) == 1
        assert projects[0]["id"] == str(project_id)
        assert projects[0]["name"] == "Accessible"
        assert cur.execute.call_args.args[1] == {"current_user_id": user["id"]}


class TestListProjectForms:
    def test_raises_404_when_project_missing(self, auth_client):
        client, _user = auth_client
        with patch(
            "app.modules.assess.routers.assess._get_assess_project_odk_id",
            return_value=None,
        ):
            response = client.get(f"/api/assess/projects/{uuid4()}/forms")
        assert response.status_code == 404
        assert response.json()["detail"] == "Project not found"

    def test_returns_forms(self, auth_client):
        client, _user = auth_client
        forms = [{"xmlFormId": "baseline", "name": "Baseline"}]
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=forms)
        with (
            patch(
                "app.modules.assess.routers.assess._get_assess_project_odk_id",
                return_value={"odk_project_id": "77"},
            ),
            patch("app.modules.assess.routers.assess.ODKClient", return_value=mock_client),
        ):
            response = client.get(f"/api/assess/projects/{uuid4()}/forms")
        assert response.status_code == 200
        assert response.json() == forms
        mock_client.get.assert_awaited_once_with("/v1/projects/77/forms")

    @pytest.mark.parametrize(
        "exc,status",
        [
            (ODKConnectionError("down"), 502),
            (ODKAuthFailed("bad"), 502),
            (ODKAPIError(500, "boom"), 500),
        ],
    )
    def test_maps_odk_errors(self, auth_client, exc, status):
        client, _user = auth_client
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=exc)
        with (
            patch(
                "app.modules.assess.routers.assess._get_assess_project_odk_id",
                return_value={"odk_project_id": "1"},
            ),
            patch("app.modules.assess.routers.assess.ODKClient", return_value=mock_client),
        ):
            response = client.get(f"/api/assess/projects/{uuid4()}/forms")
        assert response.status_code == status


class TestListFormSubmissions:
    def test_raises_404_when_project_missing(self, auth_client):
        client, _user = auth_client
        with patch(
            "app.modules.assess.routers.assess._get_assess_project_odk_id",
            return_value=None,
        ):
            response = client.get(f"/api/assess/projects/{uuid4()}/forms/baseline/submissions")
        assert response.status_code == 404

    def test_returns_submissions(self, auth_client):
        client, _user = auth_client
        payload = {"value": [{"instanceId": "uuid-1"}]}
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=payload)
        with (
            patch(
                "app.modules.assess.routers.assess._get_assess_project_odk_id",
                return_value={"odk_project_id": "12"},
            ),
            patch("app.modules.assess.routers.assess.ODKClient", return_value=mock_client),
        ):
            response = client.get(f"/api/assess/projects/{uuid4()}/forms/baseline/submissions")
        assert response.status_code == 200
        assert response.json() == payload
        mock_client.get.assert_awaited_once_with("/v1/projects/12/forms/baseline.svc/Submissions")

    @pytest.mark.parametrize(
        "exc,status",
        [
            (ODKConnectionError("down"), 502),
            (ODKAuthFailed("bad"), 502),
            (ODKAPIError(403, "denied"), 403),
        ],
    )
    def test_maps_odk_errors(self, auth_client, exc, status):
        client, _user = auth_client
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=exc)
        with (
            patch(
                "app.modules.assess.routers.assess._get_assess_project_odk_id",
                return_value={"odk_project_id": "1"},
            ),
            patch("app.modules.assess.routers.assess.ODKClient", return_value=mock_client),
        ):
            response = client.get(f"/api/assess/projects/{uuid4()}/forms/baseline/submissions")
        assert response.status_code == status


class TestGetFormSubmission:
    def test_raises_404_when_project_missing(self, auth_client):
        client, _user = auth_client
        with patch(
            "app.modules.assess.routers.assess._get_assess_project_odk_id",
            return_value=None,
        ):
            response = client.get(
                f"/api/assess/projects/{uuid4()}/forms/baseline/submissions/inst-1"
            )
        assert response.status_code == 404

    def test_returns_submission(self, auth_client):
        client, _user = auth_client
        payload = {"instanceId": "inst-1", "submitterId": 3}
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=payload)
        with (
            patch(
                "app.modules.assess.routers.assess._get_assess_project_odk_id",
                return_value={"odk_project_id": "12"},
            ),
            patch("app.modules.assess.routers.assess.ODKClient", return_value=mock_client),
        ):
            response = client.get(
                f"/api/assess/projects/{uuid4()}/forms/baseline/submissions/inst-1"
            )
        assert response.status_code == 200
        assert response.json() == payload
        mock_client.get.assert_awaited_once_with(
            "/v1/projects/12/forms/baseline/submissions/inst-1"
        )

    @pytest.mark.parametrize(
        "exc,status",
        [
            (ODKConnectionError("down"), 502),
            (ODKAuthFailed("bad"), 502),
            (ODKAPIError(404, "gone"), 404),
        ],
    )
    def test_maps_odk_errors(self, auth_client, exc, status):
        client, _user = auth_client
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=exc)
        with (
            patch(
                "app.modules.assess.routers.assess._get_assess_project_odk_id",
                return_value={"odk_project_id": "1"},
            ),
            patch("app.modules.assess.routers.assess.ODKClient", return_value=mock_client),
        ):
            response = client.get(
                f"/api/assess/projects/{uuid4()}/forms/baseline/submissions/inst-1"
            )
        assert response.status_code == status
