"""Per-layer render catalog."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.diagnose.services.layer_catalog import (
    get_catalog,
    get_layer_for_key,
    load_catalog,
)


@pytest.fixture(autouse=True)
def _clear_catalog_cache():
    get_catalog.cache_clear()
    yield
    get_catalog.cache_clear()


def test_default_catalog_loads_lulc_palette():
    layer = get_layer_for_key("rasters/lulc250k_2023_24_classed_cog.tif")
    assert layer is not None
    assert layer.id == "lulc250k"
    assert layer.render_type == "categorical"
    assert layer.nodata == 0

    cmap = layer.titiler_colormap()
    assert cmap["0"] == "#00000000"
    assert cmap["1"] == "#ff0000"
    assert cmap["2"] == "#ffd100"
    assert cmap["7"] == "#00cc00"
    assert cmap["16"] == "#5ed1f2"
    assert cmap["17"] == "#009ede"
    assert cmap["18"] == "#ffbfc4"

    legend = layer.legend_entries()
    assert all(e.value != 0 for e in legend)
    assert legend[0].label == "Built-up"
    assert len(legend) == 18


def test_catalog_includes_wiser_and_dem_layers():
    catalog = get_catalog()
    ids = {layer.id for layer in catalog.layers}
    assert "dem" in ids
    assert "gw_stress_wiser" in ids
    assert "irrigation_access_wiser" in ids
    assert "kharif_resilience_wiser" in ids
    assert "rabi_resilience_wiser" in ids
    assert "aquifers" in ids
    assert "baseline_population" in ids
    assert "marginalized_scst" in ids
    assert "village_boundaries" in ids

    gw = catalog.by_id("gw_stress_wiser")
    assert gw is not None
    assert gw.source == "vector_fgb"
    assert gw.analysis_type == "wiser_gw_stress"
    assert gw.field_check
    assert gw.interpretation
    colors = {e.label: e.color for e in gw.legend_entries()}
    assert colors["Safe"] == "#1c7a1a"
    assert colors["Over-exploited"] == "#b5523a"

    dem = catalog.by_id("dem")
    assert dem is not None
    assert dem.render_type == "continuous"
    assert dem.continuous.get("colormap") == "gist_earth"

    pop = catalog.by_id("baseline_population")
    assert pop is not None
    assert pop.render_type == "choropleth"
    assert len(pop.choropleth_stops) == 5
    assert pop.legend_entries()[0].label == "< 500"

    boundaries = catalog.by_id("village_boundaries")
    assert boundaries is not None
    assert boundaries.render_type == "outline"
    assert boundaries.label_column == "Village Na"
    assert boundaries.s3_key == "vector/villages.fgb"
    assert boundaries.category == "Reference"

    assert catalog.by_id("lulc250k").category == "Hydrology & Landscape Controls"
    assert catalog.by_id("jrc_occurrence").category == "Surface Water Dynamics"
    assert catalog.by_id("gw_stress_wiser").category == "WISER Outcome Layers"
    assert catalog.by_id("baseline_population").category == "Social & Demographic Profile"


def test_gdaldem_file_covers_0_to_18(tmp_path: Path):
    layer = get_layer_for_key("rasters/lulc250k_2023_24_classed_cog.tif")
    assert layer is not None
    out = tmp_path / "colors.txt"
    layer.write_gdaldem_color_file(out)
    lines = out.read_text().strip().splitlines()
    assert lines[0].startswith("0 0 0 0 0")
    assert lines[-1].startswith("18 255 191 196 255")
    assert len(lines) == 19


def test_two_layers_keep_separate_colormaps(tmp_path: Path):
    yaml_text = """
colors:
  rust: "#b5523a"
  deep_blue: "#00306d"
layers:
  - id: layer_a
    s3_key: a.tif
    name: A
    render:
      type: categorical
      nodata: 0
      classes:
        - { value: 0, label: nodata, color: "#00000000" }
        - { value: 1, label: Built, color: rust }
  - id: layer_b
    s3_key: b.tif
    name: B
    render:
      type: categorical
      nodata: 0
      classes:
        - { value: 0, label: nodata, color: "#00000000" }
        - { value: 1, label: Water, color: deep_blue }
"""
    path = tmp_path / "layers.yaml"
    path.write_text(yaml_text)
    catalog = load_catalog(path)
    a = catalog.by_s3_key("a.tif")
    b = catalog.by_s3_key("b.tif")
    assert a is not None and b is not None
    assert a.titiler_colormap()["1"] == "#b5523a"
    assert b.titiler_colormap()["1"] == "#00306d"
    assert a.titiler_colormap() != b.titiler_colormap()


def test_unknown_color_name_raises(tmp_path: Path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
colors: {}
layers:
  - id: x
    s3_key: x.tif
    name: X
    render:
      type: categorical
      classes:
        - { value: 1, label: Bad, color: not_a_color }
"""
    )
    with pytest.raises(ValueError, match="Unknown color"):
        load_catalog(path)
