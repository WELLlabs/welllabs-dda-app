"""QField packaging helpers."""

from __future__ import annotations

from pathlib import Path

from app.modules.diagnose.services.qfield_sync import _clip_to_geotiff


def test_gdalwarp_omits_cutline_srs(tmp_path: Path, monkeypatch):
    """EC2 Ubuntu ships GDAL 3.4 — no -cutline_srs (added in later GDAL)."""
    calls: list[list[str]] = []

    def fake_run_gdal(cmd, progress=None, env=None):
        calls.append(cmd)

    cutline = tmp_path / "watershed.geojson"
    cutline.write_text(
        '{"type":"FeatureCollection","crs":{"type":"name","properties":{"name":"EPSG:4326"}},'
        '"features":[{"type":"Feature","geometry":{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}}]}'
    )
    colormap = tmp_path / "lulc_colors.txt"
    colormap.write_text("0 0 0 0\n")

    monkeypatch.setattr("app.modules.diagnose.services.qfield_sync._run_gdal", fake_run_gdal)
    monkeypatch.setattr(
        "app.modules.diagnose.services.qfield_sync._colorize_continuous_geotiff",
        lambda *args, **kwargs: (0.0, 1.0),
    )
    monkeypatch.setattr(
        "app.modules.diagnose.services.qfield_sync.settings.qfield_raster_max_pixels",
        512,
    )

    dest = tmp_path / "lulc.tif"
    try:
        _clip_to_geotiff(
            "/vsimem/fake.tif",
            dest,
            cutline,
            colormap,
            [0, 0, 1, 1],
            continuous=True,
        )
    except RuntimeError:
        pass

    warp_cmds = [cmd for cmd in calls if cmd and cmd[0] == "gdalwarp"]
    assert warp_cmds, "expected gdalwarp to run"
    assert "-cutline_srs" not in warp_cmds[0]
    assert "-t_srs" in warp_cmds[0]
