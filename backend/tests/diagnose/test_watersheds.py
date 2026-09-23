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


def test_geom_from_cell_skips_truncated_wkb():
    from shapely.geometry import Point

    from app.shared.watersheds import _geom_from_cell

    assert _geom_from_cell(None) is None
    assert _geom_from_cell(b"\x01") is None
    assert _geom_from_cell(b"") is None
    assert _geom_from_cell(Point(1, 2)).equals(Point(1, 2))


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


def test_village_id_str_keeps_hex_fgb_ids():
    from app.shared.watersheds import _village_id_str

    assert _village_id_str("001e0000000000000051") == "001e0000000000000051"
    assert _village_id_str("573906.0") == "573906"
    assert _village_id_str(None) == ""


def test_village_lookup_s3_candidate_keys_prefer_new_then_legacy():
    from app.shared.watersheds import _village_lookup_s3_candidate_keys

    keys = _village_lookup_s3_candidate_keys()
    assert keys[0] == "vector/Village_pan_India_lookup.jsonl"
    assert "vector/villages_lookup.jsonl" in keys


def test_index_state_count_skips_numeric_junk():
    from app.shared.watersheds import _index_state_count

    rows = [
        {"state": "andhra pradesh"},
        {"state": "Assam"},
        {"state": "0.0"},
        {"state": "28"},
        {"state": None},
        {"state": "andhra pradesh"},
    ]
    assert _index_state_count(rows) == 2


def test_resolve_village_from_point_uses_fgb_then_union(monkeypatch):
    from shapely.geometry import box

    from app.shared import watersheds as ws

    village = box(0, 0, 2, 2)
    monkeypatch.setattr(
        ws,
        "village_containing_point",
        lambda lng, lat, quick=False: (village, {"Village Na": "Demo Village", "id": "v1"}),
    )
    monkeypatch.setattr(
        ws,
        "watersheds_intersecting",
        lambda _g: [
            {
                "watershed_id": "a",
                "watershed_name": "A",
                "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
                "bounds": [0, 0, 1, 1],
            },
            {
                "watershed_id": "b",
                "watershed_name": "B",
                "geometry": {"type": "Polygon", "coordinates": [[[1, 0], [2, 0], [2, 1], [1, 1], [1, 0]]]},
                "bounds": [1, 0, 2, 1],
            },
        ],
    )
    result = ws.resolve_village_from_point(0.5, 0.5)
    assert result["source"] == "village"
    assert result["village_name"] == "Demo Village"
    assert result["village_id"] == "v1"
    assert result["seed_lng"] == 0.5
    assert result["seed_lat"] == 0.5
    assert result["village_geometry"] is not None
    assert len(result["parts"]) == 2
    from shapely.geometry import Point

    from app.shared import watersheds as ws

    meta = {
        "id": "abc",
        "name": "Demo",
        "district": "medak",
        "state": "telangana",
        "lng": 78.5,
        "lat": 17.6,
    }
    monkeypatch.setattr(ws, "_village_record_by_id", lambda _vid: meta)
    monkeypatch.setattr(ws, "_configure_gdal_aws", lambda: None)
    monkeypatch.setattr(ws, "_villages_vsis3_path", lambda: "/vsis3/bucket/villages.fgb")

    def boom(*_a, **_k):
        raise TimeoutError("timed out")

    monkeypatch.setattr(ws, "_read_bbox_timed", boom)
    geom, props = ws.village_geometry_by_id("abc")
    assert props["name"] == "Demo"
    assert geom.geom_type == "Polygon"
    assert Point(78.5, 17.6).within(geom) or geom.contains(Point(78.5, 17.6))


def test_village_place_labels_from_pc11_codes():
    from app.shared.watersheds import _village_district_label, _village_state_label

    props = {
        "name": "Vailal",
        "id": "001e0000000000000051",
        "pc11_state_id": 28.0,
        "pc11_district_id": 535.0,
        "state": 28.0,
        "district": 4.0,
    }
    assert _village_state_label(props) == "andhra pradesh"
    assert _village_district_label(props) == "medak"


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
