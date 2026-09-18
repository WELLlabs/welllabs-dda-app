from app.modules.assess.services.mel_analyses import compute_pmds_metrics
from app.modules.assess.services.mel_analyses_catalog import (
    analyses_for_intervention,
    load_analyses_catalog,
)
from app.modules.assess.services.mel_mapping_catalog import load_mapping_catalog


def _ridge_row(asset_id: str, date: str, ridge: float, furrow: float, hours: float, rain: float) -> dict:
    data = {
        "bm_cm_select_the_asset_id": asset_id,
        "bm_cm_date_of_reading": date,
        "bm_cm_raised_bed_farming": "Yes",
        "bm_cm_has_flow_meter": "No",
        "bm_cm_number_of_hours_of_pumping": hours,
        "bm_cm_rainfall_recorded_since_last_irrigation": rain,
    }
    for key in (
        "bm_cm_soil_moisture_raised_r_corner_a",
        "bm_cm_soil_moisture_raised_r_corner_b",
        "bm_cm_soil_moisture_raised_r_corner_c",
        "bm_cm_soil_moisture_raised_r_corner_d",
        "bm_cm_soil_moisture_raised_r_centre",
    ):
        data[key] = ridge
    for key in (
        "bm_cm_soil_moisture_raised_f_corner_a",
        "bm_cm_soil_moisture_raised_f_corner_b",
        "bm_cm_soil_moisture_raised_f_corner_c",
        "bm_cm_soil_moisture_raised_f_corner_d",
        "bm_cm_soil_moisture_raised_f_centre",
    ):
        data[key] = furrow
    return {"data": data}


def test_pmds_mapping_catalog_has_outcomes_and_cm_fields():
    load_mapping_catalog.cache_clear()
    catalog = load_mapping_catalog()
    pmds = next(i for i in catalog["interventions"] if i["slug"] == "pmds")
    assert pmds["outcomes"]
    vars_ = {q.get("variable_name") for q in pmds["one_time_questions"] + pmds["cm_questions"]}
    assert "bm_ot_area_under_the_crop" in vars_
    assert "bm_cm_select_the_asset_id" in vars_
    assert "bm_cm_soil_moisture_raised_r_centre" in vars_


def test_pmds_analyses_catalog_includes_savings_and_irrigation():
    load_analyses_catalog.cache_clear()
    keys = {a["analysis_variable_name"] for a in analyses_for_intervention("pmds")}
    assert "sm_diff_pct" in keys
    assert "sm_water_savings_m3" in keys
    assert "irrigation_applied_m3" in keys
    assert "volumetric_savings_kpi_progress_pct" in keys
    assert any(a["category"] == "visual" for a in analyses_for_intervention("pmds"))


def test_compute_pmds_metrics_raised_bed():
    ot = {
        "bm_ot_area_under_the_crop": 1,
        "bm_ot_area_unit": "bigha",
        "bm_ot_what_is_the_volumetric_water_savings_kpi_decided_": 100,
        "bm_ot_has_flow_meter": "No",
        "bm_ot_what_is_the_rate_of_discharge_through_an_irrigati": 5,
    }
    result = compute_pmds_metrics(
        ot_answers=ot,
        cm_submissions=[_ridge_row("plot-1", "2026-07-01", 20, 12, 2, 10)],
        asset_id="plot-1",
    )
    calcs = result["calculations"]
    assert calcs["plot_layout"] == "raised"
    assert calcs["sm_diff_pct"] == 8
    assert calcs["area_m2"] == 2529.0
    assert abs(calcs["sm_water_savings_m3"] - 0.40 * 2529.0 * 0.08) < 1e-6
    assert calcs["irrigation_applied_m3"] == 2 * 5 * 3.6
    assert calcs["cumulative_rainfall_mm"] == 10
    assert abs(calcs["volumetric_savings_kpi_progress_pct"] - calcs["sm_water_savings_m3"]) < 1e-6
    assert result["reading_count"] == 1
    assert result["visual"]["series"][0]["sm_t_pct"] == 20
    assert result["visual"]["series"][0]["sm_c_pct"] == 12


def test_compute_pmds_metrics_pairs_treatment_with_control():
    treat_ot = {
        "bm_ot_area_under_the_crop": 1,
        "bm_ot_area_unit": "acre",
        "bm_ot_paired_control_asset_id": "control-1",
    }
    treat_row = {
        "data": {
            "bm_cm_select_the_asset_id": "treat-1",
            "bm_cm_date_of_reading": "2025-09-13",
            "bm_cm_raised_bed_farming": "No",
            "bm_cm_soil_moisture_flat_corner_a": 20,
            "bm_cm_soil_moisture_flat_corner_b": 20,
            "bm_cm_soil_moisture_flat_corner_c": 20,
            "bm_cm_soil_moisture_flat_corner_d": 20,
            "bm_cm_soil_moisture_flat_centre": 20,
        }
    }
    control_row = {
        "data": {
            "bm_cm_select_the_asset_id": "control-1",
            "bm_cm_date_of_reading": "2025-09-13",
            "bm_cm_raised_bed_farming": "No",
            "bm_cm_soil_moisture_flat_corner_a": 12,
            "bm_cm_soil_moisture_flat_corner_b": 12,
            "bm_cm_soil_moisture_flat_corner_c": 12,
            "bm_cm_soil_moisture_flat_corner_d": 12,
            "bm_cm_soil_moisture_flat_centre": 12,
        }
    }
    result = compute_pmds_metrics(
        ot_answers=treat_ot,
        cm_submissions=[treat_row, control_row],
        asset_id="treat-1",
    )
    calcs = result["calculations"]
    assert calcs["sm_diff_pct"] == 8
    assert result["visual"]["series"][0]["sm_t_pct"] == 20
    assert result["visual"]["series"][0]["sm_c_pct"] == 12
    assert calcs["paired_control_asset_id"] == "control-1"


def test_compute_pmds_metrics_pairs_control_via_sibling():
    treat_ot = {
        "bm_ot_area_under_the_crop": 1,
        "bm_ot_area_unit": "acre",
        "bm_ot_paired_control_asset_id": "control-1",
    }
    treat_row = {
        "data": {
            "bm_cm_select_the_asset_id": "treat-1",
            "bm_cm_date_of_reading": "2025-09-13",
            "bm_cm_raised_bed_farming": "No",
            "bm_cm_soil_moisture_flat_corner_a": 20,
            "bm_cm_soil_moisture_flat_corner_b": 20,
            "bm_cm_soil_moisture_flat_corner_c": 20,
            "bm_cm_soil_moisture_flat_corner_d": 20,
            "bm_cm_soil_moisture_flat_centre": 20,
        }
    }
    control_row = {
        "data": {
            "bm_cm_select_the_asset_id": "control-1",
            "bm_cm_date_of_reading": "2025-09-13",
            "bm_cm_raised_bed_farming": "No",
            "bm_cm_soil_moisture_flat_corner_a": 12,
            "bm_cm_soil_moisture_flat_corner_b": 12,
            "bm_cm_soil_moisture_flat_corner_c": 12,
            "bm_cm_soil_moisture_flat_corner_d": 12,
            "bm_cm_soil_moisture_flat_centre": 12,
        }
    }
    result = compute_pmds_metrics(
        ot_answers={"bm_ot_plot_role": "control"},
        cm_submissions=[treat_row, control_row],
        asset_id="control-1",
        sibling_ot=[("treat-1", treat_ot)],
    )
    calcs = result["calculations"]
    assert calcs["sm_diff_pct"] == 8
    assert calcs["paired_treatment_asset_id"] == "treat-1"
    assert calcs["paired_control_asset_id"] == "control-1"
    assert result["visual"]["series"][0]["sm_t_pct"] == 20
    assert result["visual"]["series"][0]["sm_c_pct"] == 12
    keys = {c["variable"] for c in result["calculation_cards"]}
    assert keys == {"sm_diff_pct", "sm_diff_per_unit_area_pct", "sm_water_savings_m3"}
    assert result["visual"]["title"] == "Soil moisture treatment vs control"

