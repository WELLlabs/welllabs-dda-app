"""Farm-pond analysis engine driven by intervention-analyses.csv specs."""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any

from app.modules.assess.services.mel_analyses_catalog import analyses_for_intervention

# Assumed daily evaporation (m) when computing recharge from WL declines.
DEFAULT_EVAPORATION_M = 0.005
ROOT_ZONE_DEPTH_M = 0.40
BIGHA_M2 = 2529.0
ACRE_M2 = 4046.8564224

ASSET_SELECT_KEYS = (
    "fp_cm_select_the_asset_id",
    "bm_cm_select_the_asset_id",
    "asset_id",
)
READING_DATE_KEYS = ("fp_cm_date_of_reading", "bm_cm_date_of_reading")

RIDGE_SM_KEYS = (
    "bm_cm_soil_moisture_raised_r_corner_a",
    "bm_cm_soil_moisture_raised_r_corner_b",
    "bm_cm_soil_moisture_raised_r_corner_c",
    "bm_cm_soil_moisture_raised_r_corner_d",
    "bm_cm_soil_moisture_raised_r_centre",
)
FURROW_SM_KEYS = (
    "bm_cm_soil_moisture_raised_f_corner_a",
    "bm_cm_soil_moisture_raised_f_corner_b",
    "bm_cm_soil_moisture_raised_f_corner_c",
    "bm_cm_soil_moisture_raised_f_corner_d",
    "bm_cm_soil_moisture_raised_f_centre",
)
FLAT_SM_KEYS = (
    "bm_cm_soil_moisture_flat_corner_a",
    "bm_cm_soil_moisture_flat_corner_b",
    "bm_cm_soil_moisture_flat_corner_c",
    "bm_cm_soil_moisture_flat_corner_d",
    "bm_cm_soil_moisture_flat_centre",
)


def _num(val: Any) -> float | None:
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return float(val)
    try:
        return float(str(val).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def _parse_date(val: Any) -> date | None:
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _ot(answers: dict[str, Any], key: str) -> Any:
    return answers.get(key)


def is_asset_select_field(variable_name: str | None) -> bool:
    var = (variable_name or "").strip().lower()
    return bool(var) and (var.endswith("select_the_asset_id") or var == "asset_id")


def is_plot_intervention(slug: str | None) -> bool:
    return (slug or "").strip().lower() in {"pmds", "bio-mulching"}


def _yes(val: Any) -> bool | None:
    if val is None or val == "":
        return None
    if isinstance(val, bool):
        return val
    key = str(val).strip().lower()
    if key in {"yes", "y", "true", "1"}:
        return True
    if key in {"no", "n", "false", "0"}:
        return False
    return None


def _mean(values: list[float | None]) -> float | None:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


def _row_asset_id(data: dict[str, Any]) -> str:
    for key in ASSET_SELECT_KEYS:
        val = data.get(key)
        if val not in (None, ""):
            return str(val)
    return ""


def _row_reading_date(data: dict[str, Any]) -> date | None:
    for key in READING_DATE_KEYS:
        parsed = _parse_date(data.get(key))
        if parsed is not None:
            return parsed
    return None


def _cm_rows(submissions: list[dict[str, Any]], asset_id: str) -> list[dict[str, Any]]:
    """Filter CM submissions for this asset and sort by reading date."""
    rows = []
    for sub in submissions or []:
        data = sub.get("data") if isinstance(sub.get("data"), dict) else sub
        if not isinstance(data, dict):
            continue
        sel = _row_asset_id(data)
        if sel and sel != str(asset_id):
            continue
        d = _row_reading_date(data)
        rows.append({**data, "_date": d})
    rows.sort(key=lambda r: (r["_date"] is None, r["_date"] or date.min))
    return rows


def _area_m2(area: float | None, unit: Any) -> float | None:
    if area is None or area <= 0:
        return None
    key = str(unit or "acre").strip().lower()
    if "bigha" in key:
        return area * BIGHA_M2
    return area * ACRE_M2


def _point_values(row: dict[str, Any], keys: tuple[str, ...]) -> list[float]:
    return [v for v in (_num(row.get(k)) for k in keys) if v is not None]


def _paired_sm_diff(treat_row: dict[str, Any], control_row: dict[str, Any]) -> float | None:
    """Mean of paired observation-point diffs; fall back to plot-mean difference."""
    for keys in (FLAT_SM_KEYS, RIDGE_SM_KEYS, FURROW_SM_KEYS):
        t_pts = _point_values(treat_row, keys)
        c_pts = _point_values(control_row, keys)
        if t_pts and c_pts and len(t_pts) == len(c_pts):
            return sum(a - b for a, b in zip(t_pts, c_pts)) / len(t_pts)
        if t_pts and c_pts:
            return (sum(t_pts) / len(t_pts)) - (sum(c_pts) / len(c_pts))
    t_sm = _plot_sm(treat_row)
    c_sm = _plot_sm(control_row)
    if t_sm["sm_plot_pct"] is not None and c_sm["sm_plot_pct"] is not None:
        return t_sm["sm_plot_pct"] - c_sm["sm_plot_pct"]
    return None


def _plot_sm(row: dict[str, Any]) -> dict[str, Any]:
    raised = _yes(row.get("bm_cm_raised_bed_farming"))
    ridge = _mean([_num(row.get(k)) for k in RIDGE_SM_KEYS])
    furrow = _mean([_num(row.get(k)) for k in FURROW_SM_KEYS])
    flat = _mean([_num(row.get(k)) for k in FLAT_SM_KEYS])
    if raised is True or (ridge is not None or furrow is not None):
        sm_t = ridge
        sm_c = furrow
        diff = (ridge - furrow) if ridge is not None and furrow is not None else None
        sm_plot = _mean([ridge, furrow])
        layout = "raised"
    else:
        sm_t = flat
        sm_c = None
        diff = None
        sm_plot = flat
        layout = "flat"
    return {
        "sm_t_pct": sm_t,
        "sm_c_pct": sm_c,
        "sm_plot_pct": sm_plot,
        "sm_diff_pct": diff,
        "layout": layout,
    }


def _irrigation_m3(row: dict[str, Any], discharge_lps: float | None) -> float | None:
    meter = _yes(row.get("bm_cm_has_flow_meter"))
    if meter is True:
        return _num(row.get("bm_cm_volume_of_irrigation_water_applied_through_flow_m"))
    hours = _num(row.get("bm_cm_number_of_hours_of_pumping"))
    if hours is not None and discharge_lps is not None:
        return hours * discharge_lps * 3.6
    return _num(row.get("bm_cm_volume_of_irrigation_water_applied_through_flow_m"))


def cum_wl_height_increase(readings: list[float]) -> float:
    total = 0.0
    for a, b in zip(readings, readings[1:]):
        delta = b - a
        if delta > 0:
            total += delta
    return total


def recharge_from_declines(readings: list[float], evaporation_m: float = DEFAULT_EVAPORATION_M) -> float:
    """Sum declines that exceed evaporation E (simplified v1)."""
    total = 0.0
    e = max(0.0, evaporation_m)
    for a, b in zip(readings, readings[1:]):
        delta = a - b  # decline positive when water drops
        if delta > e:
            total += delta - e
    return total


def compute_farm_pond_metrics(
    *,
    ot_answers: dict[str, Any],
    cm_submissions: list[dict[str, Any]],
    asset_id: str,
    evaporation_m: float = DEFAULT_EVAPORATION_M,
) -> dict[str, Any]:
    length = _num(_ot(ot_answers, "fp_ot_length"))
    breadth = _num(_ot(ot_answers, "fp_ot_breadth"))
    height = _num(_ot(ot_answers, "fp_ot_height"))
    kpi_raw = _ot(ot_answers, "fp_ot_what_is_the_volumetric_water_savings_kpi_decided_")
    kpi = _num(kpi_raw)

    surface_area = (length * breadth) if length is not None and breadth is not None else None

    rows = _cm_rows(cm_submissions, asset_id)
    wl_series = []
    rainfall_series = []
    for r in rows:
        d = r.get("_date")
        wl = _num(r.get("fp_cm_staff_gauge_reading"))
        rain = _num(r.get("fp_cm_rainfall"))
        if d is not None:
            wl_series.append({"date": d.isoformat(), "wl_m": wl, "rainfall_mm": rain})
            if rain is not None:
                rainfall_series.append(rain)

    wl_values = [p["wl_m"] for p in wl_series if p["wl_m"] is not None]
    cum_wl = cum_wl_height_increase(wl_values) if len(wl_values) >= 2 else 0.0
    fillings = (cum_wl / height) if height and height > 0 else None
    volumetric = (
        surface_area * height * fillings
        if surface_area is not None and height is not None and fillings is not None
        else None
    )
    recharge = recharge_from_declines(wl_values, evaporation_m) if len(wl_values) >= 2 else 0.0
    cum_rain = sum(rainfall_series) if rainfall_series else 0.0
    kpi_pct = (volumetric / kpi * 100.0) if volumetric is not None and kpi and kpi > 0 else None

    # Cumulative rainfall for chart
    running = 0.0
    chart_points = []
    for p in wl_series:
        rain = p["rainfall_mm"] or 0.0
        running += rain
        chart_points.append(
            {
                "date": p["date"],
                "water_level_m": p["wl_m"],
                "daily_rainfall_mm": p["rainfall_mm"],
                "cumulative_rainfall_mm": running,
            }
        )

    # Simple box volume (L × B × H) used for the "Volume m3" calculation card.
    volume_m3 = (
        surface_area * height
        if surface_area is not None and height is not None
        else None
    )

    calcs = {
        "volume_m3": volume_m3,
        "surface_area_m2": surface_area,
        "cum_wl_height_increase_m": cum_wl,
        "number_of_fillings": fillings,
        "volumetric_storage_m3": volumetric,
        "recharge_m": recharge,
        "volumetric_savings_kpi_progress_pct": kpi_pct,
        "cumulative_rainfall_mm": cum_rain,
        "max_pond_height_m": height,
        "evaporation_assumption_m": evaporation_m,
    }

    specs = analyses_for_intervention("farm-pond")
    return _pack_metrics(
        slug="farm-pond",
        calcs=calcs,
        specs=specs,
        series=chart_points,
        reading_count=len(wl_series),
        extra_visual={"max_pond_height_m": height},
    )


def _rows_by_date(submissions: list[dict[str, Any]], asset_id: str) -> dict[date, dict[str, Any]]:
    out: dict[date, dict[str, Any]] = {}
    for row in _cm_rows(submissions, asset_id):
        d0 = row.get("_date")
        if d0 is not None:
            out[d0] = row
    return out


def _resolve_plot_pair(
    asset_id: str,
    ot_answers: dict[str, Any],
    sibling_ot: list[tuple[str, dict[str, Any]]] | None = None,
) -> tuple[str | None, str | None]:
    """Return (treatment_asset_id, control_asset_id)."""
    control_id = str(_ot(ot_answers, "bm_ot_paired_control_asset_id") or "").strip() or None
    treat_id = str(_ot(ot_answers, "bm_ot_paired_treatment_asset_id") or "").strip() or None
    if control_id:
        return str(asset_id), control_id
    if treat_id:
        return treat_id, str(asset_id)
    for sid, sot in sibling_ot or []:
        if str(_ot(sot, "bm_ot_paired_control_asset_id") or "").strip() == str(asset_id):
            return str(sid), str(asset_id)
        if str(_ot(sot, "bm_ot_paired_treatment_asset_id") or "").strip() == str(asset_id):
            return str(asset_id), str(sid)
    role = str(_ot(ot_answers, "bm_ot_plot_role") or "").strip().lower()
    if role == "control":
        return None, str(asset_id)
    return str(asset_id), None


def _pmds_doc_specs() -> list[dict[str, Any]]:
    """Bio-mulching / PMDS analyses only (SM difference, per-area, savings, T vs C vis)."""
    return [
        spec
        for spec in analyses_for_intervention("pmds")
        if "bio-mulching" in (spec.get("intervention") or "").lower()
    ]


def compute_pmds_metrics(
    *,
    ot_answers: dict[str, Any],
    cm_submissions: list[dict[str, Any]],
    asset_id: str,
    sibling_ot: list[tuple[str, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    treat_id, control_id = _resolve_plot_pair(asset_id, ot_answers, sibling_ot)
    treat_ot = ot_answers
    if treat_id and str(treat_id) != str(asset_id):
        for sid, sot in sibling_ot or []:
            if str(sid) == str(treat_id):
                treat_ot = sot or ot_answers
                break
    area = _num(_ot(treat_ot, "bm_ot_area_under_the_crop"))
    if area is None:
        area = _num(_ot(ot_answers, "bm_ot_area_under_the_crop"))
    unit = _ot(treat_ot, "bm_ot_area_unit") or _ot(ot_answers, "bm_ot_area_unit")
    area_m2 = _area_m2(area, unit)
    kpi = _num(_ot(treat_ot, "bm_ot_what_is_the_volumetric_water_savings_kpi_decided_"))
    discharge = _num(_ot(ot_answers, "bm_ot_what_is_the_rate_of_discharge_through_an_irrigati"))

    this_rows = _cm_rows(cm_submissions, asset_id)
    treat_by_date = _rows_by_date(cm_submissions, treat_id) if treat_id else {}
    control_by_date = _rows_by_date(cm_submissions, control_id) if control_id else {}
    all_dates = sorted(set(treat_by_date) | set(control_by_date))
    if not all_dates:
        all_dates = [r["_date"] for r in this_rows if r.get("_date") is not None]

    chart_points = []
    diffs: list[float] = []
    irrigation_vals: list[float] = []
    rain_vals: list[float] = []
    rain_by_date: dict = {}
    latest_layout = "flat"
    latest_points: dict[str, float | None] = {}
    paired_assets = bool(treat_id and control_id and str(treat_id) != str(control_id))

    if _yes(_ot(ot_answers, "bm_ot_last_irrigation_applied")):
        ot_irr = _num(_ot(ot_answers, "bm_ot_duration_of_pumping_or_flow_meter_reading"))
        if ot_irr is not None:
            if _yes(_ot(ot_answers, "bm_ot_has_flow_meter")) is False and discharge:
                ot_irr = ot_irr * discharge * 3.6
            irrigation_vals.append(ot_irr)

    for r in this_rows:
        # Use bm_cm_rainfall (renamed from bm_cm_rainfall_recorded_since_last_irrigation).
        # Fall back to old key for existing ODK submissions that pre-date the rename.
        rain = _num(r.get("bm_cm_rainfall") or r.get("bm_cm_rainfall_recorded_since_last_irrigation"))
        irr = _irrigation_m3(r, discharge)
        if rain is not None:
            rain_vals.append(rain)
            d_key = r.get("_date")
            if d_key is not None:
                rain_by_date[d_key] = rain
        if irr is not None:
            irrigation_vals.append(irr)
        latest_layout = _plot_sm(r)["layout"] or latest_layout
        latest_points = {k: _num(r.get(k)) for k in (*RIDGE_SM_KEYS, *FURROW_SM_KEYS, *FLAT_SM_KEYS)}

    for d in all_dates:
        t_row = treat_by_date.get(d)
        c_row = control_by_date.get(d)
        inner_t = _plot_sm(t_row) if t_row else None
        inner_c = _plot_sm(c_row) if c_row else None
        if paired_assets:
            sm_t = inner_t["sm_plot_pct"] if inner_t else None
            sm_c = inner_c["sm_plot_pct"] if inner_c else None
            sm_diff_d = _paired_sm_diff(t_row, c_row) if t_row and c_row else None
            layout = (inner_t or inner_c or {}).get("layout") or latest_layout
        else:
            src = inner_t or inner_c
            sm_t = src["sm_t_pct"] if src else None
            sm_c = src["sm_c_pct"] if src else None
            sm_diff_d = src["sm_diff_pct"] if src else None
            layout = (src or {}).get("layout") or latest_layout
        if sm_diff_d is not None:
            diffs.append(sm_diff_d)
        if str(asset_id) == str(treat_id) and inner_t:
            plot_sm = inner_t["sm_plot_pct"] if paired_assets else inner_t["sm_t_pct"]
        elif str(asset_id) == str(control_id) and inner_c:
            plot_sm = inner_c["sm_plot_pct"] if paired_assets else inner_c.get("sm_c_pct") or inner_c["sm_plot_pct"]
        else:
            plot_sm = (inner_t or inner_c or {}).get("sm_plot_pct")
        chart_points.append(
            {
                "date": d.isoformat(),
                "sm_t_pct": sm_t,
                "sm_c_pct": sm_c,
                "sm_plot_pct": plot_sm,
                "sm_diff_pct": sm_diff_d,
                "layout": layout,
                "daily_rainfall_mm": rain_by_date.get(d),
            }
        )

    sm_diff = _mean(diffs)
    # Total SM water savings: root-zone depth × plot area × Σ(SM_Tn − SM_Cn) / 100.
    sm_savings = (
        ROOT_ZONE_DEPTH_M * area_m2 * (sum(diffs) / 100.0)
        if diffs and area_m2 is not None
        else None
    )
    # Normalized savings: SM water savings (m³) ÷ plot area in survey units.
    sm_diff_per_unit = (sm_savings / area) if sm_savings is not None and area and area > 0 else None
    irrigation_total = sum(irrigation_vals) if irrigation_vals else 0.0
    cum_rain = sum(rain_vals) if rain_vals else 0.0
    kpi_pct = (sm_savings / kpi * 100.0) if sm_savings is not None and kpi and kpi > 0 else None

    calcs = {
        "area_under_crop": area,
        "area_unit": (str(unit).strip() if unit else None),
        "area_m2": area_m2,
        "sm_diff_pct": sm_diff,
        "sm_diff_per_unit_area_pct": sm_diff_per_unit,
        "sm_water_savings_m3": sm_savings,
        "irrigation_applied_m3": irrigation_total,
        "cumulative_rainfall_mm": cum_rain,
        "volumetric_savings_kpi_progress_pct": kpi_pct,
        "root_zone_depth_m": ROOT_ZONE_DEPTH_M,
        "plot_layout": latest_layout,
        "latest_sm_points": latest_points,
        "paired_control_asset_id": control_id,
        "paired_treatment_asset_id": treat_id,
    }
    return _pack_metrics(
        slug="pmds",
        calcs=calcs,
        specs=_pmds_doc_specs(),
        series=chart_points,
        reading_count=len(this_rows),
        extra_visual={
            "plot_layout": latest_layout,
            "latest_sm_points": latest_points,
            "paired_control_asset_id": control_id,
            "paired_treatment_asset_id": treat_id,
        },
    )


def compute_asset_metrics(
    slug: str | None,
    *,
    ot_answers: dict[str, Any],
    cm_submissions: list[dict[str, Any]],
    asset_id: str,
    sibling_ot: list[tuple[str, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    if is_plot_intervention(slug):
        return compute_pmds_metrics(
            ot_answers=ot_answers,
            cm_submissions=cm_submissions,
            asset_id=asset_id,
            sibling_ot=sibling_ot,
        )
    return compute_farm_pond_metrics(
        ot_answers=ot_answers,
        cm_submissions=cm_submissions,
        asset_id=asset_id,
    )


def _pack_metrics(
    *,
    slug: str,
    calcs: dict[str, Any],
    specs: list[dict[str, Any]],
    series: list[dict[str, Any]],
    reading_count: int,
    extra_visual: dict[str, Any] | None = None,
) -> dict[str, Any]:
    calculation_cards = []
    visual = None
    for spec in specs:
        if spec["category"] == "calculation" and spec.get("analysis_variable_name"):
            key = spec["analysis_variable_name"]
            calculation_cards.append(
                {
                    "id": spec["id"],
                    "title": spec["title"],
                    "description": spec["description"],
                    "methodology": spec["methodology"],
                    "variable": key,
                    "value": calcs.get(key),
                }
            )
        elif spec["category"] == "visual" and visual is None:
            visual = {
                "id": spec["id"],
                "title": spec["title"],
                "description": spec["description"],
                "chart_description": spec.get("chart_description"),
                "series": series,
                **(extra_visual or {}),
            }
    if visual is None:
        visual = {"id": f"{slug}-series", "title": "Monitoring", "series": series, **(extra_visual or {})}
    return {
        "calculations": calcs,
        "calculation_cards": calculation_cards,
        "visual": visual,
        "reading_count": reading_count,
    }


def asset_label_from_answers(
    ot_answers: dict[str, Any], fallback: str = "Asset"
) -> str:
    farmer = (
        str(ot_answers.get("fp_ot_farmer_name") or ot_answers.get("bm_ot_farmer_name") or "")
        .strip()
    )
    village = (
        str(ot_answers.get("fp_ot_village_name") or ot_answers.get("bm_ot_village_name") or "")
        .strip()
    )
    crop = str(ot_answers.get("bm_ot_crop_grown") or "").strip()
    parts = [p for p in (farmer, crop or village) if p]
    if parts:
        return " — ".join(parts)
    return fallback
