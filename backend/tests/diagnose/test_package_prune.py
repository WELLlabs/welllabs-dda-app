"""Package directory pruning."""

from __future__ import annotations

from pathlib import Path

from app.modules.diagnose.services.qfield_sync import _prune_package_dir


def test_prune_package_dir_removes_build_artifacts(tmp_path: Path):
    package_dir = tmp_path / "pkg"
    package_dir.mkdir()
    (package_dir / "my-project.qgs").write_text("qgs")
    (package_dir / "field_notes.gpkg").write_bytes(b"gpkg")
    (package_dir / "observation_zones.gpkg").write_bytes(b"gpkg")
    (package_dir / "hypotheses.gpkg").write_bytes(b"gpkg")
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
        "IndiaSat_LULC_24_25.tif",
    }
