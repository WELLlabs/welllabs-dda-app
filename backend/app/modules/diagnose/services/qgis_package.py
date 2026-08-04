"""Run the PyQGIS project builder inside the official QGIS Docker image."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

QGIS_IMAGE = "qgis/qgis:release-3_34"
BUILD_SCRIPT_CONTAINER = Path("/app/qgis/build_qfield_project.py")
# services -> diagnose -> qgis/build_qfield_project.py
BUILD_SCRIPT_REPO = Path(__file__).resolve().parents[1] / "qgis" / "build_qfield_project.py"


def _host_path_for_container_path(container_path: str) -> Path | None:
    mountinfo = Path("/proc/self/mountinfo")
    if not mountinfo.is_file():
        return None
    for line in mountinfo.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[4] == container_path:
            return Path(parts[3])
    return None


def _normalize_host_path(path: Path) -> Path:
    text = str(path)
    if text.startswith("/abhiram/"):
        return Path("/Users") / Path(text).relative_to("/")
    return path


def _host_package_dir(package_dir: Path) -> Path:
    package_dir = package_dir.resolve()
    host_root = os.environ.get("HOST_PACKAGES_DIR")
    if host_root:
        return _normalize_host_path(Path(host_root) / package_dir.name)

    inferred = _host_path_for_container_path("/app/packages")
    if inferred:
        return _normalize_host_path(inferred / package_dir.name)

    return package_dir


def _build_script_mount() -> tuple[Path, str]:
    if BUILD_SCRIPT_CONTAINER.is_file():
        host_root = _host_path_for_container_path("/app/qgis")
        if host_root:
            return _normalize_host_path(host_root / "build_qfield_project.py"), "/build_qfield_project.py"
        return BUILD_SCRIPT_CONTAINER, "/build_qfield_project.py"
    if BUILD_SCRIPT_REPO.is_file():
        return BUILD_SCRIPT_REPO, "/build_qfield_project.py"
    raise RuntimeError("Missing QGIS build script (expected /app/qgis/build_qfield_project.py)")


def build_qfield_project_with_qgis(
    package_dir: Path,
    project_name: str,
    project_id: str,
    *,
    rasters: list[dict] | None = None,
    secondary_vectors: list[dict] | None = None,
    zone_colors: list[str],
    extent: list[float] | None,
    # Back-compat for older callers
    raster_filename: str | None = None,
) -> Path:
    package_dir = package_dir.resolve()
    host_package_dir = _host_package_dir(package_dir)
    build_script_host, build_script_container = _build_script_mount()

    raster_list = list(rasters or [])
    if not raster_list and raster_filename:
        raster_list = [{"filename": raster_filename, "name": Path(raster_filename).stem}]

    cmd = [
        "docker",
        "run",
        "--rm",
        "--platform",
        "linux/amd64",
        "-e",
        "QT_QPA_PLATFORM=offscreen",
        "-v",
        f"{host_package_dir}:/package",
        "-v",
        f"{build_script_host}:{build_script_container}:ro",
        QGIS_IMAGE,
        "python3",
        build_script_container,
        "/package",
        project_name,
        project_id,
        "--zone-colors",
        json.dumps(zone_colors),
        "--rasters",
        json.dumps(raster_list),
        "--secondary-vectors",
        json.dumps(secondary_vectors or []),
    ]
    if extent:
        cmd.extend(["--extent", json.dumps(extent)])

    logger.info("Running QGIS project builder for %s", host_package_dir)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"QGIS project build failed: {detail}")

    output = package_dir / f"{project_name}.qgs"
    if not output.is_file():
        raise RuntimeError("QGIS project builder finished without writing a .qgs file")
    return output
