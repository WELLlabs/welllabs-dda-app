"""Unit tests for watershed analysis helpers (no network / geopandas required for normalize)."""

from __future__ import annotations

from app.modules.diagnose.services.layer_analysis import (
    _normalize_gw,
    _normalize_rank,
    wiser_rank_source_columns,
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


def test_wiser_rank_source_columns_are_distinct():
    assert wiser_rank_source_columns("__wiser_irrigation_access_class") == ("Irr_access",)
    assert wiser_rank_source_columns("__wiser_kharif_resilience_class") == ("Kharif_res",)
    assert wiser_rank_source_columns("__wiser_rabi_resilience_class") == ("Rabi_res",)
    # Must not share a single preferred source or map layers look identical.
    assert len({wiser_rank_source_columns(c)[0] for c in (
        "__wiser_irrigation_access_class",
        "__wiser_kharif_resilience_class",
        "__wiser_rabi_resilience_class",
    )}) == 3

