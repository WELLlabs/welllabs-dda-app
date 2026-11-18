"""site_suitability.csv parsing → GIS rules."""

from __future__ import annotations

import math

import pytest

from app.modules.design.services.solutions_catalog import (
    load_solutions,
    parse_catalog_text,
    parse_lulc,
    parse_range,
    slope_pct_to_deg,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("5 - 15 %", (5.0, 15.0)),
        ("0 - 15%", (0.0, 15.0)),
        ("1st - 2nd", (1.0, 2.0)),
        ("3th - 5th", (3.0, 5.0)),
        ("", None),
        (None, None),
    ],
)
def test_parse_range(text, expected):
    assert parse_range(text) == expected


def test_lulc_agriculture_excludes_fallow():
    classes, terms = parse_lulc("Agriculture, Plantation")
    assert classes == {2, 3, 4, 5, 7}
    assert 6 not in classes
    assert terms == ["Agriculture", "Plantation"]


def test_lulc_unknown_term_raises():
    with pytest.raises(ValueError):
        parse_lulc("Mangroves")


def test_slope_percent_to_degrees():
    assert slope_pct_to_deg(100) == pytest.approx(45.0)
    assert slope_pct_to_deg(10) == pytest.approx(math.degrees(math.atan(0.1)))


def test_bundled_catalog_parses_every_row():
    sols = load_solutions()
    assert len(sols) == 27
    assert len({s.id for s in sols}) == 27
    by_name = {s.name: s for s in sols}
    kt = by_name["Kolhapur Type weirs (K.T. Weirs)"]
    assert kt.type == "Instream" and kt.stream_order == (3, 5) and kt.slope_pct == (0.0, 5.0)
    assert kt.uses_streams
    pond = by_name["Farm pond (Unlined)"]
    assert pond.lulc_classes == {2, 3, 4, 5, 7} and not pond.uses_streams
    # No GIS criteria → all drainage lines.
    assert by_name["Desiltation of the drainage channels"].uses_streams


def test_header_rows_and_non_gis_rows_skipped():
    text = (
        "Sl,Solutions,GIS check,Solution type,a,b,c,d,e,f,g\n"
        "#,Solution Name,GIS Site suitability,Solution type,x,x,x,x,x,x,x\n"
        "1,Thing,Yes,Areal,0 - 5 %,,,,,>1 m,\n"
        "2,Other,No,Areal,0 - 5 %,,,,,,\n"
    )
    sols = parse_catalog_text(text)
    assert [s.name for s in sols] == ["Thing"]
    assert sols[0].notes == (("Soil thickness", ">1 m"),)
