"""Shared pytest fixtures."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """FastAPI test client with DB pool startup disabled (no Postgres required)."""
    with (
        patch("app.shared.database.init_pool"),
        patch("app.shared.database.close_pool"),
    ):
        from app.main import app

        with TestClient(app, raise_server_exceptions=True) as test_client:
            yield test_client
