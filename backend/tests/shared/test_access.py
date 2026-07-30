"""Shared access control helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.shared.access import (
    assert_diagnosis_access,
    diagnosis_access_where,
)


class TestDiagnosisAccessWhere:
    def test_includes_owner_check(self):
        sql = diagnosis_access_where("p")
        assert "p.owner_id = %(current_user_id)s" in sql

    def test_includes_direct_user_grant(self):
        sql = diagnosis_access_where("d")
        assert "diagnosis_users" in sql

    def test_includes_org_grant(self):
        sql = diagnosis_access_where("d")
        assert "diagnosis_orgs" in sql
        assert "org_members" in sql


class TestAssertDiagnosisAccess:
    def _mock_db(self, exists: bool, has_access: bool):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = {"exists": exists, "has_access": has_access}
        return patch(
            "app.shared.access.db_cursor",
            return_value=MagicMock(__enter__=MagicMock(return_value=mock_cur), __exit__=MagicMock()),
        )

    def test_raises_404_when_project_missing(self):
        user_id = str(uuid4())
        project_id = str(uuid4())
        with self._mock_db(exists=False, has_access=False):
            with pytest.raises(HTTPException) as exc:
                assert_diagnosis_access(user_id, project_id)
        assert exc.value.status_code == 404
        assert exc.value.detail == "Project not found"

    def test_raises_403_when_no_access(self):
        user_id = str(uuid4())
        project_id = str(uuid4())
        with self._mock_db(exists=True, has_access=False):
            with pytest.raises(HTTPException) as exc:
                assert_diagnosis_access(user_id, project_id)
        assert exc.value.status_code == 403

    def test_passes_when_access_granted(self):
        user_id = str(uuid4())
        project_id = str(uuid4())
        with self._mock_db(exists=True, has_access=True):
            assert_diagnosis_access(user_id, project_id) is None
