"""Unit tests for watershed geometry helpers (no S3)."""

from __future__ import annotations

import pytest
from shapely.geometry import mapping, shape

from app.shared.watersheds import (
    custom_aoi_from_geometry,
    parse_geojson_polygon,
    union_geometries,
)


SQUARE_A = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
}
SQUARE_B = {
    "type": "Polygon",
    "coordinates": [[[0.5, 0.5], [0.5, 1.5], [1.5, 1.5], [1.5, 0.5], [0.5, 0.5]]],
}


def test_parse_geojson_polygon_accepts_polygon():
    geom = parse_geojson_polygon(SQUARE_A)
    assert geom.geom_type == "Polygon"
    assert geom.area > 0


def test_parse_geojson_polygon_rejects_point():
    with pytest.raises(ValueError, match="Polygon or MultiPolygon"):
        parse_geojson_polygon({"type": "Point", "coordinates": [1, 2]})


def test_parse_geojson_polygon_rejects_huge_bbox():
    huge = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [0, 20], [20, 20], [20, 0], [0, 0]]],
    }
    with pytest.raises(ValueError, match="bbox exceeds"):
        parse_geojson_polygon(huge)


def test_custom_aoi_from_geometry():
    result = custom_aoi_from_geometry(SQUARE_A, name="My AOI")
    assert result["watershed_id"] == "custom"
    assert result["watershed_name"] == "My AOI"
    assert result["source"] == "custom"
    assert result["parts"] == []
    assert "seed_lng" in result and "seed_lat" in result


def test_union_geometries_merges_parts():
    features = [
        {
            "watershed_id": "a",
            "watershed_name": "A",
            "geometry": SQUARE_A,
            "bounds": [0, 0, 1, 1],
        },
        {
            "watershed_id": "b",
            "watershed_name": "B",
            "geometry": SQUARE_B,
            "bounds": [0.5, 0.5, 1.5, 1.5],
        },
    ]
    result = union_geometries(features, village_name="Demo Village")
    assert result["source"] == "village"
    assert "Demo Village" in result["watershed_name"]
    assert len(result["parts"]) == 2
    assert "a" in result["watershed_id"] and "b" in result["watershed_id"]
    merged = shape(result["geometry"])
    assert merged.area > 1.0  # larger than a single unit square
    assert mapping(merged)["type"] in ("Polygon", "MultiPolygon")


def test_lookup_with_village_context_attaches_all_union(monkeypatch):
    from app.shared import watersheds as ws
    from shapely.geometry import box

    point_hit = {
        "watershed_id": "a",
        "watershed_name": "A",
        "geometry": SQUARE_A,
        "bounds": [0, 0, 1, 1],
    }
    parts = [
        point_hit,
        {
            "watershed_id": "b",
            "watershed_name": "B",
            "geometry": SQUARE_B,
            "bounds": [0.5, 0.5, 1.5, 1.5],
        },
    ]
    village = box(0, 0, 1.2, 1.2)

    monkeypatch.setattr(ws, "lookup_watershed", lambda lng, lat: dict(point_hit))
    monkeypatch.setattr(
        ws,
        "village_containing_point",
        lambda lng, lat: (village, {"Village Na": "Demo Village"}),
    )
    monkeypatch.setattr(ws, "watersheds_intersecting", lambda geom: parts)

    result = ws.lookup_watershed_with_village_context(0.2, 0.2)
    assert result["watershed_id"] == "a"
    assert result["village_name"] == "Demo Village"
    assert result["village_geometry"] is not None
    assert len(result["parts"]) == 2
    assert result["all_watershed_id"]
    assert "a" in result["all_watershed_id"] and "b" in result["all_watershed_id"]
    assert shape(result["all_geometry"]).area > shape(result["geometry"]).area


def test_union_geometries_requires_features():
    with pytest.raises(ValueError, match="No watershed"):
        union_geometries([])


def test_list_cascade_helpers_filter_index(monkeypatch):
    from app.shared import watersheds as ws

    fake = [
        {
            "id": "1",
            "name": "alpha",
            "name_l": "alpha",
            "district": "mandya",
            "state": "karnataka",
        },
        {
            "id": "2",
            "name": "beta",
            "name_l": "beta",
            "district": "tumkur",
            "state": "karnataka",
        },
        {
            "id": "3",
            "name": "gamma",
            "name_l": "gamma",
            "district": "madurai",
            "state": "tamil nadu",
        },
    ]
    monkeypatch.setattr(ws, "ensure_village_name_index", lambda **_: fake)
    ws._set_village_indexes(list(fake))
    assert ws.list_village_states() == ["karnataka", "tamil nadu"]
    assert ws.list_village_districts("Karnataka") == ["mandya", "tumkur"]
    villages = ws.list_villages_for_district("karnataka", "mandya")
    assert len(villages) == 1 and villages[0]["id"] == "1"
