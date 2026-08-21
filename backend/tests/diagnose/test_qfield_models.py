"""Diagnose module: QField request models."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.diagnose.routers.qfield import CleanupRequest, ProjectRequest


class TestProjectRequest:
    def test_accepts_uuid(self):
        project_id = uuid4()
        body = ProjectRequest(project_id=project_id)
        assert body.project_id == project_id

    def test_rejects_invalid_uuid(self):
        with pytest.raises(ValidationError):
            ProjectRequest(project_id="bad-id")


class TestCleanupRequest:
    def test_defaults_dry_run_false(self):
        body = CleanupRequest(project_id=uuid4())
        assert body.dry_run is False

    def test_accepts_dry_run_true(self):
        body = CleanupRequest(project_id=uuid4(), dry_run=True)
        assert body.dry_run is True
