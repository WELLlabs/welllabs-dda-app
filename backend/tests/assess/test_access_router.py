"""Assess project sharing management endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.main import app
from app.modules.assess.access import require_assess_admin
from app.modules.assess.routers.access import AddUserAccess, UpdateUserRole


def _admin_user():
    return {
        "id": str(uuid4()),
        "email": "admin@example.com",
        "name": "Admin",
    }


def _db_cursor_mock(fetchone=None, fetchall=None, fetchone_side_effect=None):
    mock_cur = MagicMock()
    if fetchone_side_effect is not None:
        mock_cur.fetchone.side_effect = fetchone_side_effect
    else:
        mock_cur.fetchone.return_value = fetchone
    mock_cur.fetchall.return_value = fetchall or []
    ctx = MagicMock()
    ctx.__enter__.return_value = mock_cur
    # Must return False so exceptions raised inside `with db_cursor()` propagate.
    ctx.__exit__.return_value = False
    return ctx, mock_cur


@pytest.fixture
def access_client(client):
    user = _admin_user()
    app.dependency_overrides[require_assess_admin] = lambda: user
    yield client, user
    app.dependency_overrides.pop(require_assess_admin, None)


class TestAddUserAccessModel:
    def test_defaults_role_to_member(self):
        body = AddUserAccess(email="user@example.com")
        assert body.role == "member"

    def test_rejects_invalid_email(self):
        with pytest.raises(ValidationError):
            AddUserAccess(email="not-an-email")


class TestUpdateUserRoleModel:
    def test_accepts_role(self):
        body = UpdateUserRole(role="admin")
        assert body.role == "admin"


class TestListUserAccess:
    def test_returns_users(self, access_client):
        client, _user = access_client
        project_id = str(uuid4())
        user_id = uuid4()
        created = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
        ctx, _cur = _db_cursor_mock(
            fetchall=[
                {
                    "id": user_id,
                    "email": "member@example.com",
                    "name": "Member",
                    "role": "member",
                    "created_at": created,
                }
            ]
        )
        with patch("app.modules.assess.routers.access.db_cursor", return_value=ctx):
            response = client.get(f"/api/assess/projects/{project_id}/access/users")
        assert response.status_code == 200
        assert response.json() == {
            "users": [
                {
                    "id": str(user_id),
                    "email": "member@example.com",
                    "name": "Member",
                    "role": "member",
                    "created_at": created.isoformat(),
                }
            ]
        }


class TestAddUserAccessEndpoint:
    def test_rejects_invalid_role(self, access_client):
        client, _user = access_client
        project_id = str(uuid4())
        response = client.post(
            f"/api/assess/projects/{project_id}/access/users",
            json={"email": "user@example.com", "role": "owner"},
        )
        assert response.status_code == 400
        assert "admin" in response.json()["detail"]

    def test_raises_404_when_email_unknown(self, access_client):
        client, _user = access_client
        project_id = str(uuid4())
        ctx, _cur = _db_cursor_mock(fetchone=None)
        with patch("app.modules.assess.routers.access.db_cursor", return_value=ctx):
            response = client.post(
                f"/api/assess/projects/{project_id}/access/users",
                json={"email": "missing@example.com", "role": "member"},
            )
        assert response.status_code == 404
        assert response.json()["detail"] == "No account found with that email"

    def test_rejects_adding_self(self, access_client):
        client, user = access_client
        project_id = str(uuid4())
        ctx, _cur = _db_cursor_mock(
            fetchone={"id": user["id"], "email": user["email"], "name": user["name"]}
        )
        with patch("app.modules.assess.routers.access.db_cursor", return_value=ctx):
            response = client.post(
                f"/api/assess/projects/{project_id}/access/users",
                json={"email": user["email"], "role": "member"},
            )
        assert response.status_code == 400
        assert "already have access" in response.json()["detail"]

    def test_raises_409_when_already_granted(self, access_client):
        client, user = access_client
        project_id = str(uuid4())
        target_id = uuid4()
        ctx, _cur = _db_cursor_mock(
            fetchone_side_effect=[
                {"id": target_id, "email": "other@example.com", "name": "Other"},
                None,
            ]
        )
        with patch("app.modules.assess.routers.access.db_cursor", return_value=ctx):
            response = client.post(
                f"/api/assess/projects/{project_id}/access/users",
                json={"email": "other@example.com", "role": "admin"},
            )
        assert response.status_code == 409

    def test_adds_user_successfully(self, access_client):
        client, user = access_client
        project_id = str(uuid4())
        target_id = uuid4()
        ctx, _cur = _db_cursor_mock(
            fetchone_side_effect=[
                {"id": target_id, "email": "other@example.com", "name": "Other"},
                {"project_id": project_id},
            ]
        )
        with patch("app.modules.assess.routers.access.db_cursor", return_value=ctx):
            response = client.post(
                f"/api/assess/projects/{project_id}/access/users",
                json={"email": "Other@Example.com", "role": "member"},
            )
        assert response.status_code == 201
        assert response.json() == {
            "id": str(target_id),
            "email": "other@example.com",
            "name": "Other",
            "role": "member",
        }
        # Lookup email is normalized to lowercase before querying users.
        lookup_call = _cur.execute.call_args_list[0]
        assert lookup_call.args[1] == {"email": "other@example.com"}


class TestUpdateUserRoleEndpoint:
    def test_rejects_invalid_role(self, access_client):
        client, _user = access_client
        project_id = str(uuid4())
        response = client.patch(
            f"/api/assess/projects/{project_id}/access/users/{uuid4()}/role",
            json={"role": "viewer"},
        )
        assert response.status_code == 400

    def test_raises_404_when_user_not_on_project(self, access_client):
        client, _user = access_client
        project_id = str(uuid4())
        user_id = str(uuid4())
        ctx, _cur = _db_cursor_mock(fetchone=None)
        with patch("app.modules.assess.routers.access.db_cursor", return_value=ctx):
            response = client.patch(
                f"/api/assess/projects/{project_id}/access/users/{user_id}/role",
                json={"role": "admin"},
            )
        assert response.status_code == 404

    def test_updates_role(self, access_client):
        client, _user = access_client
        project_id = str(uuid4())
        user_id = str(uuid4())
        ctx, _cur = _db_cursor_mock(fetchone={"user_id": user_id})
        with patch("app.modules.assess.routers.access.db_cursor", return_value=ctx):
            response = client.patch(
                f"/api/assess/projects/{project_id}/access/users/{user_id}/role",
                json={"role": "admin"},
            )
        assert response.status_code == 200
        assert response.json() == {"id": user_id, "role": "admin"}


class TestRemoveUserAccess:
    def test_raises_404_when_missing(self, access_client):
        client, _user = access_client
        project_id = str(uuid4())
        user_id = str(uuid4())
        ctx, _cur = _db_cursor_mock(fetchone=None)
        with patch("app.modules.assess.routers.access.db_cursor", return_value=ctx):
            response = client.delete(f"/api/assess/projects/{project_id}/access/users/{user_id}")
        assert response.status_code == 404

    def test_removes_user(self, access_client):
        client, _user = access_client
        project_id = str(uuid4())
        user_id = str(uuid4())
        ctx, _cur = _db_cursor_mock(fetchone={"user_id": user_id})
        with patch("app.modules.assess.routers.access.db_cursor", return_value=ctx):
            response = client.delete(f"/api/assess/projects/{project_id}/access/users/{user_id}")
        assert response.status_code == 204


class TestListOrgAccess:
    def test_returns_organizations(self, access_client):
        client, _user = access_client
        project_id = str(uuid4())
        org_id = uuid4()
        created = datetime(2024, 2, 1, 8, 0, tzinfo=timezone.utc)
        ctx, _cur = _db_cursor_mock(
            fetchall=[{"id": org_id, "name": "WellLabs", "created_at": created}]
        )
        with patch("app.modules.assess.routers.access.db_cursor", return_value=ctx):
            response = client.get(f"/api/assess/projects/{project_id}/access/orgs")
        assert response.status_code == 200
        assert response.json() == {
            "organizations": [
                {"id": str(org_id), "name": "WellLabs", "created_at": created.isoformat()}
            ]
        }


class TestAddOrgAccess:
    def test_raises_404_when_org_missing(self, access_client):
        client, _user = access_client
        project_id = str(uuid4())
        org_id = str(uuid4())
        ctx, _cur = _db_cursor_mock(fetchone=None)
        with patch("app.modules.assess.routers.access.db_cursor", return_value=ctx):
            response = client.post(f"/api/assess/projects/{project_id}/access/orgs?org_id={org_id}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Organization not found"

    def test_raises_409_when_already_granted(self, access_client):
        client, _user = access_client
        project_id = str(uuid4())
        org_id = uuid4()
        ctx, _cur = _db_cursor_mock(
            fetchone_side_effect=[{"id": org_id, "name": "WellLabs"}, None]
        )
        with patch("app.modules.assess.routers.access.db_cursor", return_value=ctx):
            response = client.post(f"/api/assess/projects/{project_id}/access/orgs?org_id={org_id}")
        assert response.status_code == 409

    def test_adds_org(self, access_client):
        client, _user = access_client
        project_id = str(uuid4())
        org_id = uuid4()
        ctx, _cur = _db_cursor_mock(
            fetchone_side_effect=[
                {"id": org_id, "name": "WellLabs"},
                {"project_id": project_id},
            ]
        )
        with patch("app.modules.assess.routers.access.db_cursor", return_value=ctx):
            response = client.post(f"/api/assess/projects/{project_id}/access/orgs?org_id={org_id}")
        assert response.status_code == 201
        assert response.json() == {"id": str(org_id), "name": "WellLabs"}


class TestRemoveOrgAccess:
    def test_raises_404_when_missing(self, access_client):
        client, _user = access_client
        project_id = str(uuid4())
        org_id = str(uuid4())
        ctx, _cur = _db_cursor_mock(fetchone=None)
        with patch("app.modules.assess.routers.access.db_cursor", return_value=ctx):
            response = client.delete(f"/api/assess/projects/{project_id}/access/orgs/{org_id}")
        assert response.status_code == 404

    def test_removes_org(self, access_client):
        client, _user = access_client
        project_id = str(uuid4())
        org_id = str(uuid4())
        ctx, _cur = _db_cursor_mock(fetchone={"org_id": org_id})
        with patch("app.modules.assess.routers.access.db_cursor", return_value=ctx):
            response = client.delete(f"/api/assess/projects/{project_id}/access/orgs/{org_id}")
        assert response.status_code == 204
