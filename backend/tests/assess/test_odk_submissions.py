"""Unit tests for ODK submission normalization."""

from app.modules.assess.services.odk_submissions import normalize_submissions, parse_geopoint


def test_parse_geopoint():
    assert parse_geopoint("20.33 73.11 0 0") == (20.33, 73.11)
    assert parse_geopoint("") == (None, None)
    assert parse_geopoint(None) == (None, None)
    # OData GeoJSON Point is lon, lat
    assert parse_geopoint({"type": "Point", "coordinates": [81.05811, 27.2028959, 0]}) == (
        27.2028959,
        81.05811,
    )


def test_normalize_submissions_infers_types():
    raw = [
        {
            "__id": "uuid:1",
            "__system": {"submissionDate": "2025-08-01T00:00:00.000Z"},
            "observation_date": "2025-08-01",
            "coordinates": {"type": "Point", "coordinates": [73.11, 20.33, 0]},
            "water_level_m": "1.5",
            "rainfall_mm": "12",
            "village_name": "Jirval",
        },
        {
            "__id": "uuid:2",
            "observation_date": "2025-08-02",
            "coordinates": {"type": "Point", "coordinates": [73.11, 20.33, 0]},
            "water_level_m": "1.7",
            "rainfall_mm": "0",
            "village_name": "Jirval",
        },
    ]
    out = normalize_submissions(raw)
    assert out["count"] == 2
    types = {c["name"]: c["type"] for c in out["columns"]}
    assert types["observation_date"] == "date"
    assert types["coordinates"] == "geopoint"
    assert types["water_level_m"] == "number"
    assert types["village_name"] == "text"
    assert out["rows"][0]["lat"] == 20.33
    assert out["rows"][0]["lon"] == 73.11
    assert out["rows"][0]["water_level_m"] == 1.5
