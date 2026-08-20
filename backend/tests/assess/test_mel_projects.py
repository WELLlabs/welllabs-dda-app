"""MEL project + plan CRUD and membership-scoped access."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.main import app
from app.modules.assess.access import (
    require_assess_access,
    require_assess_admin,
    require_assess_owner,
)
from app.shared.auth import get_current_user


def _user(**overrides):
    base = {
        "id": str(uuid4()),
        "email": "owner@example.com",
        "name": "Owner",
    }
    base.update(overrides)
    return base


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


def _mel_row(owner_id, *, name="Kolar watershed MEL"):
    now = datetime.now(timezone.utc)
    return {
        "id": uuid4(),
        "name": name,
        "owner_id": owner_id,
        "description": "",
        "status": "active",
        "kind": "mel",
        "created_at": now,
        "updated_at": now,
        "owner_name": "Owner",
        "owner_email": "owner@example.com",
        "plan_count": 0,
        "form_count": 0,
    }


def _plan_row(project_id, *, name="Check dams", intervention_slug="check-dams-earthen-dams"):
    now = datetime.now(timezone.utc)
    return {
        "id": uuid4(),
        "project_id": project_id,
        "name": name,
        "intervention_slug": intervention_slug,
        "plan_json": None,
        "created_by": uuid4(),
        "created_at": now,
        "updated_at": now,
        "form_count": 0,
    }


@pytest.fixture
def auth_client(client):
    user = _user()
    app.dependency_overrides[get_current_user] = lambda: user
    yield client, user
    app.dependency_overrides.pop(get_current_user, None)


class TestRequireAssessOwner:
    def _mock_db(self, exists: bool, has_access: bool):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = {"exists": exists, "has_access": has_access}
        return patch(
            "app.modules.assess.access.db_cursor",
            return_value=MagicMock(
                __enter__=MagicMock(return_value=mock_cur),
                __exit__=MagicMock(return_value=False),
            ),
        )

    def test_raises_403_when_not_owner(self):
        user = {"id": str(uuid4())}
        project_id = str(uuid4())
        with self._mock_db(exists=True, has_access=False):
            with pytest.raises(HTTPException) as exc:
                require_assess_owner(project_id, user)
        assert exc.value.status_code == 403

    def test_returns_user_when_owner(self):
        user = {"id": str(uuid4())}
        project_id = str(uuid4())
        with self._mock_db(exists=True, has_access=True):
            assert require_assess_owner(project_id, user) is user


class TestListMelProjects:
    def test_lists_only_accessible_mel_projects(self, auth_client):
        client, user = auth_client
        row = _mel_row(user["id"])
        ctx, _cur = _db_cursor_mock(fetchall=[row])
        with patch("app.modules.assess.routers.mel_projects.db_cursor", return_value=ctx):
            response = client.get("/api/assess/mel/projects")
        assert response.status_code == 200
        body = response.json()
        assert len(body["projects"]) == 1
        assert body["projects"][0]["kind"] == "mel"
        assert "intervention_slug" not in body["projects"][0]
        assert body["projects"][0]["plan_count"] == 0


class TestCreateMelProject:
    def test_creates_mel_project_without_intervention(self, auth_client):
        client, user = auth_client
        row = _mel_row(user["id"])
        ctx, _cur = _db_cursor_mock(fetchone=row)
        with patch("app.modules.assess.routers.mel_projects.db_cursor", return_value=ctx):
            response = client.post(
                "/api/assess/mel/projects",
                json={"name": "Kolar watershed MEL"},
            )
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Kolar watershed MEL"
        assert body["kind"] == "mel"
        assert body["owner_id"] == str(user["id"])
        assert body["plan_count"] == 0


class TestMelPlans:
    def test_create_plan_under_project(self, auth_client):
        client, user = auth_client
        project_id = str(uuid4())
        plan = _plan_row(project_id)
        ctx, _cur = _db_cursor_mock(fetchone=plan)
        app.dependency_overrides[require_assess_access] = lambda: user
        try:
            with (
                patch(
                    "app.modules.assess.routers.mel_projects.get_mel_project",
                    return_value=_mel_row(user["id"]),
                ),
                patch(
                    "app.modules.assess.routers.mel_projects.get_intervention",
                    return_value={"slug": "check-dams-earthen-dams", "name": "Check dams"},
                ),
                patch("app.modules.assess.routers.mel_projects.db_cursor", return_value=ctx),
            ):
                response = client.post(
                    f"/api/assess/mel/projects/{project_id}/plans",
                    json={
                        "name": "Check dams",
                        "intervention_slug": "check-dams-earthen-dams",
                    },
                )
            assert response.status_code == 201
            body = response.json()
            assert body["intervention_slug"] == "check-dams-earthen-dams"
            assert body["project_id"] == str(plan["project_id"])
        finally:
            app.dependency_overrides.pop(require_assess_access, None)

    def test_create_plan_404_unknown_intervention(self, auth_client):
        client, user = auth_client
        project_id = str(uuid4())
        app.dependency_overrides[require_assess_access] = lambda: user
        try:
            with (
                patch(
                    "app.modules.assess.routers.mel_projects.get_mel_project",
                    return_value=_mel_row(user["id"]),
                ),
                patch(
                    "app.modules.assess.routers.mel_projects.get_intervention",
                    return_value=None,
                ),
            ):
                response = client.post(
                    f"/api/assess/mel/projects/{project_id}/plans",
                    json={"name": "Bad", "intervention_slug": "no-such-thing"},
                )
            assert response.status_code == 404
        finally:
            app.dependency_overrides.pop(require_assess_access, None)

    def test_list_plans(self, auth_client):
        client, user = auth_client
        project_id = str(uuid4())
        plan = _plan_row(project_id)
        ctx, _cur = _db_cursor_mock(fetchall=[plan])
        app.dependency_overrides[require_assess_access] = lambda: user
        try:
            with (
                patch(
                    "app.modules.assess.routers.mel_projects.get_mel_project",
                    return_value=_mel_row(user["id"]),
                ),
                patch("app.modules.assess.routers.mel_projects.db_cursor", return_value=ctx),
            ):
                response = client.get(f"/api/assess/mel/projects/{project_id}/plans")
            assert response.status_code == 200
            assert len(response.json()["plans"]) == 1
        finally:
            app.dependency_overrides.pop(require_assess_access, None)

    def test_list_plan_forms(self, auth_client):
        client, user = auth_client
        project_id = str(uuid4())
        plan_id = str(uuid4())
        now = datetime.now(timezone.utc)
        form_row = {
            "id": uuid4(),
            "plan_id": plan_id,
            "xml_form_id": "mel_a",
            "name": "Form A",
            "package_id": "bme",
            "package_title": "BME",
            "created_by": user["id"],
            "created_at": now,
            "created_by_name": "Owner",
        }
        ctx, _cur = _db_cursor_mock(fetchall=[form_row])
        app.dependency_overrides[require_assess_access] = lambda: user
        try:
            with (
                patch(
                    "app.modules.assess.routers.mel_projects.get_mel_project",
                    return_value=_mel_row(user["id"]),
                ),
                patch(
                    "app.modules.assess.routers.mel_projects.get_mel_plan",
                    return_value=_plan_row(project_id),
                ),
                patch("app.modules.assess.routers.mel_projects.db_cursor", return_value=ctx),
            ):
                response = client.get(
                    f"/api/assess/mel/projects/{project_id}/plans/{plan_id}/forms"
                )
            assert response.status_code == 200
            body = response.json()
            assert body["planId"] == plan_id
            assert body["forms"][0]["xmlFormId"] == "mel_a"
        finally:
            app.dependency_overrides.pop(require_assess_access, None)

    def test_delete_plan(self, auth_client):
        client, user = auth_client
        project_id = str(uuid4())
        plan_id = str(uuid4())
        ctx, _cur = _db_cursor_mock(fetchone={"id": plan_id})
        app.dependency_overrides[require_assess_access] = lambda: user
        try:
            with (
                patch(
                    "app.modules.assess.routers.mel_projects.get_mel_project",
                    return_value=_mel_row(user["id"]),
                ),
                patch(
                    "app.modules.assess.routers.mel_projects.get_mel_plan",
                    return_value=_plan_row(project_id),
                ),
                patch("app.modules.assess.routers.mel_projects.db_cursor", return_value=ctx),
            ):
                response = client.delete(
                    f"/api/assess/mel/projects/{project_id}/plans/{plan_id}"
                )
            assert response.status_code == 204
        finally:
            app.dependency_overrides.pop(require_assess_access, None)


class TestDeleteMelProject:
    def test_owner_deletes_project(self, auth_client):
        client, user = auth_client
        project_id = str(uuid4())
        row = _mel_row(user["id"])
        ctx, _cur = _db_cursor_mock(fetchone={"id": project_id})
        app.dependency_overrides[require_assess_owner] = lambda: user
        try:
            with (
                patch(
                    "app.modules.assess.routers.mel_projects.get_mel_project",
                    return_value=row,
                ),
                patch("app.modules.assess.routers.mel_projects.db_cursor", return_value=ctx),
            ):
                response = client.delete(f"/api/assess/mel/projects/{project_id}")
            assert response.status_code == 204
        finally:
            app.dependency_overrides.pop(require_assess_owner, None)


class TestMelProjectAccessUsers:
    def test_add_member_by_email(self, auth_client):
        client, user = auth_client
        project_id = str(uuid4())
        target = {"id": uuid4(), "email": "member@example.com", "name": "Member"}
        ctx, _cur = _db_cursor_mock(
            fetchone_side_effect=[
                target,
                {"owner_id": user["id"]},
                {"project_id": project_id},
            ]
        )
        app.dependency_overrides[require_assess_admin] = lambda: user
        try:
            with (
                patch(
                    "app.modules.assess.routers.mel_projects.get_mel_project",
                    return_value=_mel_row(user["id"]),
                ),
                patch("app.modules.assess.routers.mel_projects.db_cursor", return_value=ctx),
            ):
                response = client.post(
                    f"/api/assess/mel/projects/{project_id}/access/users",
                    json={"email": "Member@Example.com", "role": "member"},
                )
            assert response.status_code == 201
            assert response.json()["email"] == "member@example.com"
        finally:
            app.dependency_overrides.pop(require_assess_admin, None)
