"""Diagnose module: observation zone request models."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.diagnose.routers.observation_zones import (
    ObservationZoneCreate,
    ObservationZoneUpdate,
)


class TestObservationZoneCreate:
    def test_valid_payload(self):
        project_id = uuid4()
        body = ObservationZoneCreate(
            project_id=project_id,
            geometry={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
            text="Zone A",
        )
        assert body.project_id == project_id
        assert body.color == "#0d983b"

    def test_rejects_invalid_project_id(self):
        with pytest.raises(ValidationError):
            ObservationZoneCreate(
                project_id="not-a-uuid",
                geometry={"type": "Point", "coordinates": [0, 0]},
            )

    def test_rejects_text_over_max_length(self):
        with pytest.raises(ValidationError):
            ObservationZoneCreate(
                project_id=uuid4(),
                geometry={"type": "Point", "coordinates": [0, 0]},
                text="x" * 10_001,
            )


class TestObservationZoneUpdate:
    def test_accepts_color_only(self):
        body = ObservationZoneUpdate(color="#ff0000")
        assert body.color == "#ff0000"
        assert body.text is None
