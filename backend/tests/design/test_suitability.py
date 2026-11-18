"""Suitability engine on synthetic inputs (no files, no S3)."""

from __future__ import annotations

import numpy as np
import pytest
import shapely
from shapely.geometry import LineString, box, mapping

pytest.importorskip("rasterio")

from app.modules.design.services import suitability as s  # noqa: E402
from app.modules.design.services.solutions_catalog import Solution  # noqa: E402

AOI = box(78.0, 18.0, 78.01, 18.01)


def _sol(**kw) -> Solution:
    base = dict(
        id="t", sl="1", name="T", type="Areal", slope_pct=None, stream_order=None,
        lulc_classes=None, lulc_terms=(),
    )
    base.update(kw)
    return Solution(**base)


@pytest.fixture
def ctx(monkeypatch):
    grid = s.grid_for_aoi(AOI)
    h, w = grid.height, grid.width
    # Left half gentle (2°), right half steep (20°). Top half crop (2), bottom half wasteland (14).
    slope = np.full((h, w), 2.0, dtype="float32")
    slope[:, w // 2 :] = 20.0
    lulc = np.full((h, w), 2, dtype="uint8")
    lulc[h // 2 :, :] = 14
    monkeypatch.setattr(s, "read_slope", lambda g: np.ma.masked_array(slope))
    monkeypatch.setattr(s, "read_lulc", lambda g: np.ma.masked_array(lulc))
    # One order-1 stream across the gentle half, one order-3 across the steep half (both full height).
    lines = np.array(
        [LineString([(78.002, 18.0), (78.002, 18.01)]), LineString([(78.008, 18.0), (78.008, 18.01)])],
        dtype=object,
    )
    monkeypatch.setattr(s, "read_streams", lambda aoi: (lines, np.array([1, 3], dtype=np.int16)))
    s._cache.clear()
    return mapping(AOI)


def test_area_rule_slope_and_lulc(ctx):
    gentle_crop = _sol(slope_pct=(0, 10), lulc_classes=frozenset({2, 3, 4, 5}))  # 10 % ≈ 5.7°
    r = s._evaluate(gentle_crop, s.get_context(ctx))
    assert r["kind"] == "area"
    assert r["pct"] == pytest.approx(25, abs=3)  # one quadrant


def test_line_rule_order_and_slope(ctx):
    c = s.get_context(ctx)
    low_order_gentle = _sol(type="Instream", slope_pct=(0, 10), stream_order=(1, 2))
    r = s._evaluate(low_order_gentle, c)
    assert r["kind"] == "line"
    assert r["pct"] == pytest.approx(50, abs=3)  # the order-1 stream on gentle ground
    steep_only = _sol(type="Instream", slope_pct=(0, 10), stream_order=(3, 5))
    assert s._evaluate(steep_only, c)["suitable_km"] == 0
    assert s._evaluate(_sol(type="Point"), c)["pct"] == pytest.approx(100)  # no criteria → all streams


def test_ranking_sorts_feasible_first(ctx):
    out = s.rank_solutions(ctx)
    scores = [
        r["metrics"]["score"]
        for r in out["solutions"]
        if r["metrics"]["status"] == "ok" and r["has_gis_criteria"]
    ]
    assert scores == sorted(scores, reverse=True)
    assert out["solutions"][0]["metrics"]["score"] > 0


def test_geojson_geometry_within_aoi(ctx):
    sol = _sol(slope_pct=(0, 10))
    fc = s.solution_geojson(ctx, sol)
    geom = shapely.geometry.shape(fc["features"][0]["geometry"])
    assert geom.geom_type == "MultiPolygon"
    # Raster edges snap to the pixel grid: allow half a pixel of slack.
    assert AOI.buffer(s.SLOPE_RES_DEG / 2).contains(geom)
    lines = s.solution_geojson(ctx, _sol(id="l", type="Instream", stream_order=(1, 1)))
    assert lines["features"][0]["geometry"]["type"] == "MultiLineString"


def test_missing_drainage_marks_line_solutions_unavailable(monkeypatch, ctx):
    def boom(aoi):
        raise s.SuitabilityInputError("Drainage lines is not configured")

    monkeypatch.setattr(s, "read_streams", boom)
    s._cache.clear()
    r = s._evaluate(_sol(type="Instream", stream_order=(1, 2)), s.get_context(ctx))
    assert r["status"] == "unavailable"


def test_solutions_without_criteria_rank_after_scored_ones(ctx):
    rows = [r for r in s.rank_solutions(ctx)["solutions"] if r["metrics"]["status"] == "ok"]
    flags = [r["has_gis_criteria"] for r in rows]
    # All criteria-bearing solutions come before any criteria-less one.
    assert flags == sorted(flags, reverse=True)
    assert rows[0]["has_gis_criteria"]


def test_slope_margin_open_lower_bound_prefers_flattest():
    sol = _sol(slope_pct=(0, 10))
    hi = sol.slope_deg[1]
    m = s.slope_margin(sol, np.array([0.0, hi / 2, hi, hi + 1]))
    assert m[0] == pytest.approx(1.0) and m[1] == pytest.approx(0.5) and m[2] == pytest.approx(0.0)
    assert m[3] == 0.0  # outside the range clips to 0


def test_slope_margin_closed_range_prefers_middle():
    sol = _sol(slope_pct=(5, 15))
    lo, hi = sol.slope_deg
    m = s.slope_margin(sol, np.array([lo, (lo + hi) / 2, hi]))
    assert m[0] == pytest.approx(0) and m[1] == pytest.approx(1) and m[2] == pytest.approx(0)


def test_aptness_classes_quarters():
    assert s.aptness_class(np.array([0.0, 0.24, 0.25, 0.5, 0.74, 0.75, 1.0])).tolist() == [1, 1, 2, 3, 3, 4, 4]


def test_area_classes_sum_to_suitable_area(ctx):
    r = s._evaluate(_sol(slope_pct=(0, 10)), s.get_context(ctx))
    assert sum(c["ha"] for c in r["classes"]) == pytest.approx(r["suitable_ha"], abs=0.5)
    # Synthetic gentle half is a uniform 2° (≈3.5 %) on a 0–10 % rule → margin ≈ 0.65 → "Good".
    # (Grading uses 3×3-smoothed slope, so the column beside the 20° half grades lower.)
    good = next(c["ha"] for c in r["classes"] if c["apt"] == 3)
    assert good > 0.9 * r["suitable_ha"]


def test_geojson_is_binary_suitable_layer(ctx):
    """The map layer is suitable / not suitable only: one area feature, no aptness grades."""
    fc = s.solution_geojson(ctx, _sol(id="a", slope_pct=(0, 10)))
    assert len(fc["features"]) == 1
    assert fc["features"][0]["geometry"]["type"] == "MultiPolygon"
    assert "apt" not in fc["features"][0]["properties"]
    lines = s.solution_geojson(ctx, _sol(id="b", type="Instream", slope_pct=(0, 10), stream_order=(1, 1)))
    assert lines["features"] and all("apt" not in f["properties"] for f in lines["features"])


def test_slope_only_area_rules_exclude_built_up(monkeypatch):
    grid = s.grid_for_aoi(AOI)
    h, w = grid.height, grid.width
    lulc = np.full((h, w), 5, dtype="uint8")
    lulc[:, : w // 2] = 1  # left half built-up
    monkeypatch.setattr(s, "read_slope", lambda g: np.ma.masked_array(np.full((h, w), 1.0, dtype="float32")))
    monkeypatch.setattr(s, "read_lulc", lambda g: np.ma.masked_array(lulc))
    monkeypatch.setattr(s, "read_streams", lambda aoi: (np.empty(0, dtype=object), np.empty(0, dtype=np.int16)))
    s._cache.clear()
    r = s._evaluate(_sol(slope_pct=(0, 15)), s.get_context(mapping(AOI)))
    assert r["pct"] == pytest.approx(50, abs=3)


def test_inspect_point_explains_each_criterion(ctx):
    gentle_crop = _sol(slope_pct=(0, 10), lulc_classes=frozenset({2}), lulc_terms=("Agriculture",))
    ok = s.inspect_point(ctx, gentle_crop, 78.0025, 18.0075)  # gentle (2°) + crop
    assert ok["inside_aoi"] and ok["suitable"]
    assert {c["criterion"] for c in ok["checks"]} == {"Slope", "Land use"}
    assert ok["aptness"]["label"] == "Good"
    steep = s.inspect_point(ctx, gentle_crop, 78.0075, 18.0075)  # steep (20°)
    assert not steep["suitable"]
    assert [c["pass"] for c in steep["checks"] if c["criterion"] == "Slope"] == [False]
    outside = s.inspect_point(ctx, gentle_crop, 78.5, 18.5)
    assert not outside["inside_aoi"] and not outside["suitable"]


def test_inspect_point_on_stream(ctx):
    sol = _sol(type="Instream", slope_pct=(0, 10), stream_order=(1, 2))
    on = s.inspect_point(ctx, sol, 78.0021, 18.005)  # ~10 m from the order-1 stream
    assert on["suitable"], on["checks"]
    off = s.inspect_point(ctx, sol, 78.005, 18.005)  # ~300 m from either stream
    assert not off["suitable"]
    assert off["checks"][0]["criterion"] == "On a drainage line" and not off["checks"][0]["pass"]


def test_aoi_stats_summarise_three_layers(ctx):
    st = s.aoi_stats(ctx)
    ws = st["watershed"]
    assert ws["area_ha"] == pytest.approx(118, rel=0.05)  # ~1.06 km × 1.11 km at 18° N
    assert ws["centroid"] == {"lng": pytest.approx(78.005), "lat": pytest.approx(18.005)}

    slope = st["slope"]
    assert slope["status"] == "ok"
    by_label = {c["label"]: c["pct"] for c in slope["classes"]}
    assert by_label["Gentle"] == pytest.approx(50, abs=3)  # 2° ≈ 3.5 %
    assert by_label["Very steep"] == pytest.approx(50, abs=3)  # 20° ≈ 36 %
    assert sum(c["pct"] for c in slope["classes"]) == pytest.approx(100, abs=0.5)

    lulc = st["lulc"]
    assert {c["label"] for c in lulc["classes"]} == {"Kharif Crop", "Wasteland"}
    assert sum(c["pct"] for c in lulc["classes"]) == pytest.approx(100, abs=0.5)

    dr = st["drainage"]
    assert dr["reaches"] == 2 and dr["max_order"] == 3
    assert [o["order"] for o in dr["by_order"]] == [1, 3]
    assert dr["density_km_per_km2"] == pytest.approx(dr["total_km"] / (ws["area_ha"] / 100), rel=0.01)
    assert s.aoi_stats(ctx) is st  # cached on the context
