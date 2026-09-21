"""CM ODK rows remapped onto plan assets by coordinates."""

from app.modules.assess.routers.mel_projects import (
    _cm_form_discovery_score,
    remap_odk_cm_to_plan_assets,
)


def test_remap_odk_cm_rewrites_foreign_asset_ids_by_coord():
    known = {"beta-pond-1"}
    by_coord = {("17.84272", "78.54367"): "beta-pond-1"}
    rows = [
        {
            "fp_cm_select_the_asset_id": "local-pond-1",
            "coordinates": "17.84272 78.543675 0 0",
            "fp_cm_staff_gauge_reading": 1.2,
        },
        {
            # already on this plan — leave alone
            "fp_cm_select_the_asset_id": "beta-pond-1",
            "coordinates": "17.84272 78.543675 0 0",
            "fp_cm_staff_gauge_reading": 0.5,
        },
    ]
    out = remap_odk_cm_to_plan_assets(
        rows, known_asset_ids=known, assets_by_coord=by_coord
    )
    assert out[0]["fp_cm_select_the_asset_id"] == "beta-pond-1"
    assert out[0]["bm_cm_select_the_asset_id"] == "beta-pond-1"
    assert out[1]["fp_cm_select_the_asset_id"] == "beta-pond-1"
    assert out[0]["fp_cm_staff_gauge_reading"] == 1.2


def test_cm_form_discovery_prefers_farm_pond_cm():
    assert (
        _cm_form_discovery_score(
            "mel_farm_pond_cm_20260916040226",
            "Medak farm ponds - Medak monitoring 2025 - CM",
            intervention_slug="farm-pond",
        )
        >= 100
    )
    assert (
        _cm_form_discovery_score(
            "mel_farm_ponds_unlined_everyday_20260819",
            "other",
            intervention_slug="farm-pond",
        )
        < 100
    )
