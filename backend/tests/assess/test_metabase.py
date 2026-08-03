"""Assess Metabase embed service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import jwt
import pytest

from app.modules.assess.services import metabase as metabase_service


def _db_cursor_mock(fetchone=None):
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = fetchone
    return MagicMock(__enter__=MagicMock(return_value=mock_cur), __exit__=MagicMock()), mock_cur


class TestResolveProjectDashboard:
    def test_returns_none_tuple_when_project_missing(self):
        ctx, _cur = _db_cursor_mock(fetchone=None)
        with patch("app.modules.assess.services.metabase.db_cursor", return_value=ctx):
            assert metabase_service._resolve_project_dashboard(str(uuid4())) == (None, None)

    def test_returns_name_and_dashboard_id(self):
        project_id = str(uuid4())
        ctx, cur = _db_cursor_mock(fetchone={"name": "Watershed", "metabase_dashboard_id": 99})
        with patch("app.modules.assess.services.metabase.db_cursor", return_value=ctx):
            assert metabase_service._resolve_project_dashboard(project_id) == ("Watershed", 99)
        cur.execute.assert_called_once()
        assert cur.execute.call_args.args[1] == {"id": project_id}


class TestSignDashboardToken:
    def test_raises_when_secret_missing(self):
        with patch("app.modules.assess.services.metabase.settings") as settings:
            settings.metabase_embed_secret_key = ""
            with pytest.raises(RuntimeError, match="Metabase embedding is not configured"):
                metabase_service._sign_dashboard_token(10)

    def test_signs_jwt_with_dashboard_resource(self):
        secret = "unit-test-embed-secret-key-32b!"
        frozen_now = 1_700_000_000
        with (
            patch("app.modules.assess.services.metabase.settings") as settings,
            patch("app.modules.assess.services.metabase.time.time", return_value=frozen_now),
        ):
            settings.metabase_embed_secret_key = secret
            token, expires_at = metabase_service._sign_dashboard_token(42)

        assert expires_at == frozen_now + metabase_service._TOKEN_TTL_SECONDS
        # Token was signed under a frozen clock; skip exp check against wall time.
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"verify_exp": False},
        )
        assert payload["resource"] == {"dashboard": 42}
        assert payload["params"] == {}
        assert payload["exp"] == expires_at


class TestGetProjectReport:
    def test_returns_unconfigured_when_no_dashboard(self):
        project_id = str(uuid4())
        with patch(
            "app.modules.assess.services.metabase._resolve_project_dashboard",
            return_value=("Demo Project", None),
        ):
            result = metabase_service.get_project_report(project_id)
        assert result == {
            "project_id": project_id,
            "project_name": "Demo Project",
            "dashboard_id": None,
            "configured": False,
        }

    def test_returns_signed_embed_when_dashboard_mapped(self):
        project_id = str(uuid4())
        with (
            patch(
                "app.modules.assess.services.metabase._resolve_project_dashboard",
                return_value=("Demo Project", 15),
            ),
            patch(
                "app.modules.assess.services.metabase._sign_dashboard_token",
                return_value=("signed.token", 1_700_000_600),
            ),
            patch("app.modules.assess.services.metabase.settings") as settings,
        ):
            settings.metabase_public_url = "https://metabase.example"
            result = metabase_service.get_project_report(project_id)

        assert result == {
            "project_id": project_id,
            "project_name": "Demo Project",
            "dashboard_id": 15,
            "configured": True,
            "resource": "dashboard",
            "instance_url": "https://metabase.example",
            "token": "signed.token",
            "expires_at": 1_700_000_600,
        }

    def test_treats_zero_dashboard_id_as_unconfigured(self):
        project_id = str(uuid4())
        with patch(
            "app.modules.assess.services.metabase._resolve_project_dashboard",
            return_value=("Demo", 0),
        ):
            result = metabase_service.get_project_report(project_id)
        assert result["configured"] is False
        assert result["dashboard_id"] is None
