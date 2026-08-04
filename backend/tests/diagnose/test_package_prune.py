"""Package directory pruning."""

from __future__ import annotations

from pathlib import Path

from app.modules.diagnose.services.qfield_sync import _prune_package_dir, _vector_style_payload
from app.modules.diagnose.services.layer_catalog import get_catalog


def test_prune_package_dir_removes_build_artifacts(tmp_path: Path):
    package_dir = tmp_path / "pkg"
    package_dir.mkdir()
    (package_dir / "my-project.qgs").write_text("qgs")
    (package_dir / "field_notes.gpkg").write_bytes(b"gpkg")
    (package_dir / "observation_zones.gpkg").write_bytes(b"gpkg")
    (package_dir / "hypotheses.gpkg").write_bytes(b"gpkg")
    (package_dir / "secondary_aquifers.gpkg").write_bytes(b"gpkg")
    (package_dir / "secondary_baseline_population.gpkg").write_bytes(b"gpkg")
    (package_dir / "IndiaSat_LULC_24_25.tif").write_bytes(b"tif")
    (package_dir / "watershed.geojson").write_text("{}")
    (package_dir / "layer_colors.txt").write_text("colors")
    (package_dir / "old-project.qgs").write_text("stale")
    stale_dir = package_dir / "rasters"
    stale_dir.mkdir()
    (stale_dir / "old.mbtiles").write_bytes(b"mb")

    _prune_package_dir(package_dir, "my-project")

    remaining = {p.name for p in package_dir.iterdir()}
    assert remaining == {
        "my-project.qgs",
        "field_notes.gpkg",
        "observation_zones.gpkg",
        "hypotheses.gpkg",
        "secondary_aquifers.gpkg",
        "secondary_baseline_population.gpkg",
        "IndiaSat_LULC_24_25.tif",
    }


def test_vector_style_payload_includes_colors_and_legend():
    catalog = get_catalog()
    aquifers = catalog.by_id("aquifers")
    assert aquifers is not None
    payload = _vector_style_payload(aquifers)
    assert payload["render_type"] == "categorical"
    assert payload["style_column"] == "aquifer"
    assert any(c["label"] == "Alluvium" and c["color"].startswith("#") for c in payload["classes"])

    pop = catalog.by_id("baseline_population")
    assert pop is not None
    pop_payload = _vector_style_payload(pop)
    assert pop_payload["render_type"] == "choropleth"
    assert pop_payload["choropleth_stops"]
    assert pop_payload["choropleth_stops"][0]["color"].startswith("#")

    villages = catalog.by_id("village_boundaries")
    assert villages is not None
    outline = _vector_style_payload(villages)
    assert outline["render_type"] == "outline"
    assert outline["label_column"] == "Village Na"
