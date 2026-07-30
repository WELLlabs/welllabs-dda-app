"""Unit tests for watershed analysis helpers (no network / geopandas required for normalize)."""

from __future__ import annotations

from app.modules.diagnose.services.layer_analysis import (
    _normalize_gw,
    _normalize_rank,
)


def test_normalize_gw_labels():
    assert _normalize_gw("safe") == "Safe"
    assert _normalize_gw("Semi-Critical") == "Semi-critical"
    assert _normalize_gw("over exploited") == "Over-exploited"
    assert _normalize_gw(None) == "Groundwater class unavailable"


def test_normalize_rank_labels():
    assert _normalize_rank("very low") == "Very low"
    assert _normalize_rank("MEDIUM") == "Moderate"
    assert _normalize_rank(None) == "NA"
    assert _normalize_rank("n/a") == "NA"
