"""Assess project access-control helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.assess.access import (
    assess_access_where,
    require_assess_access,
    require_assess_admin,
)


class TestAssessAccessWhere:
    def test_includes_owner_check(self):
        sql = assess_access_where("p")
        assert "p.owner_id = %(current_user_id)s" in sql

    def test_includes_direct_user_grant(self):
        sql = assess_access_where("p")
        assert "assess_project_users" in sql
        assert "apu.user_id = %(current_user_id)s" in sql

    def test_includes_org_grant(self):
        sql = assess_access_where("p")
        assert "assess_project_orgs" in sql
        assert "org_members" in sql

    def test_respects_custom_alias(self):
        sql = assess_access_where("proj")
        assert "proj.owner_id = %(current_user_id)s" in sql
        assert "apo.project_id = proj.id" in sql


class TestRequireAssessAccess:
    def _mock_db(self, exists: bool, has_access: bool):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = {"exists": exists, "has_access": has_access}
        return patch(
            "app.modules.assess.access.db_cursor",
            return_value=MagicMock(__enter__=MagicMock(return_value=mock_cur), __exit__=MagicMock()),
        )

    def test_raises_404_when_project_missing(self):
        user = {"id": str(uuid4())}
        project_id = str(uuid4())
        with self._mock_db(exists=False, has_access=False):
            with pytest.raises(HTTPException) as exc:
                require_assess_access(project_id, user)
        assert exc.value.status_code == 404
        assert exc.value.detail == "Project not found"

    def test_raises_403_when_no_access(self):
        user = {"id": str(uuid4())}
        project_id = str(uuid4())
        with self._mock_db(exists=True, has_access=False):
            with pytest.raises(HTTPException) as exc:
                require_assess_access(project_id, user)
        assert exc.value.status_code == 403
        assert exc.value.detail == "You do not have access to this project"

    def test_returns_user_when_access_granted(self):
        user = {"id": str(uuid4()), "email": "user@example.com"}
        project_id = str(uuid4())
        with self._mock_db(exists=True, has_access=True):
            assert require_assess_access(project_id, user) is user


class TestRequireAssessAdmin:
    def _mock_db(self, exists: bool, has_access: bool):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = {"exists": exists, "has_access": has_access}
        return patch(
            "app.modules.assess.access.db_cursor",
            return_value=MagicMock(__enter__=MagicMock(return_value=mock_cur), __exit__=MagicMock()),
        )

    def test_raises_404_when_project_missing(self):
        user = {"id": str(uuid4())}
        project_id = str(uuid4())
        with self._mock_db(exists=False, has_access=False):
            with pytest.raises(HTTPException) as exc:
                require_assess_admin(project_id, user)
        assert exc.value.status_code == 404

    def test_raises_403_when_not_admin(self):
        user = {"id": str(uuid4())}
        project_id = str(uuid4())
        with self._mock_db(exists=True, has_access=False):
            with pytest.raises(HTTPException) as exc:
                require_assess_admin(project_id, user)
        assert exc.value.status_code == 403
        assert exc.value.detail == "Only project admins can do this"

    def test_returns_user_when_admin(self):
        user = {"id": str(uuid4())}
        project_id = str(uuid4())
        with self._mock_db(exists=True, has_access=True):
            assert require_assess_admin(project_id, user) is user
