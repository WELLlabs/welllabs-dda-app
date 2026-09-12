"""Climate Trend timeseries from Annual_Rainfall_India_Master.nc (clinton notebook)."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_CLIMATE_S3_KEY = "Annual_Rainfall_India_Master.nc"
_LOCAL_CACHE = Path("/tmp/Annual_Rainfall_India_Master.nc")


def _bucket() -> str | None:
    return os.environ.get("AWS_S3_BUCKET") or os.environ.get("S3_BUCKET")


def _ensure_local_nc() -> Path | None:
    bucket = _bucket()
    if not bucket:
        return None
    if _LOCAL_CACHE.exists() and _LOCAL_CACHE.stat().st_size > 1000:
        return _LOCAL_CACHE
    try:
        import boto3

        s3 = boto3.client("s3", region_name=os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION") or "ap-south-1")
        s3.download_file(bucket, _CLIMATE_S3_KEY, str(_LOCAL_CACHE))
        return _LOCAL_CACHE
    except Exception as exc:
        log.warning("Could not download climate NetCDF: %s", exc)
        return None


def load_climate_trend(watershed_geom: dict, seed_lat: float | None = None, seed_lng: float | None = None) -> dict[str, Any]:
    """Point-sample annual rainfall at watershed centroid / seed; return clinton-style timeseries entry."""
    entry: dict[str, Any] = {
        "cfg": None,
        "name": "Climate Trend",
        "category": "Hydrology & Landscape Controls",
        "status": "failed",
        "stats": {},
        "type": "timeseries",
        "trend_data": [],
        "gdf": None,
        "raster": None,
        "error": None,
    }
    try:
        import numpy as np
        import xarray as xr
        from shapely.geometry import shape
    except ImportError as exc:
        entry["error"] = f"Climate deps missing: {exc}"
        return entry

    path = _ensure_local_nc()
    if path is None:
        entry["error"] = "Climate NetCDF unavailable"
        return entry

    try:
        if seed_lat is not None and seed_lng is not None:
            lat, lon = float(seed_lat), float(seed_lng)
        else:
            c = shape(watershed_geom).centroid
            lon, lat = float(c.x), float(c.y)

        ds = xr.open_dataset(path)
        var_name = "rain" if "rain" in ds.data_vars else list(ds.data_vars)[0]
        try:
            point_data = ds.sel(lat=lat, lon=lon, method="nearest")
        except Exception:
            point_data = ds.sel(LATITUDE=lat, LONGITUDE=lon, method="nearest")
        df = point_data.to_dataframe().reset_index()
        df = df.dropna(subset=[var_name])
        if "year" in df.columns:
            try:
                df["year"] = df["year"].astype(int)
            except Exception:
                try:
                    df["year"] = df["year"].dt.year
                except Exception:
                    pass
            df = df[df["year"] >= 1950]

        if len(df) > 0:
            entry["trend_data"] = df[["year", var_name]].to_dict("records")
        if len(df) > 10:
            mean_rain = float(df[var_name].mean())
            std_rain = float(df[var_name].std())
            cv = (std_rain / mean_rain) * 100 if mean_rain > 0 else 0
            deficit_years = int(len(df[df[var_name] < (0.8 * mean_rain)]))
            excess_years = int(len(df[df[var_name] > (1.2 * mean_rain)]))
            recent_10_avg = float(df[var_name].tail(10).mean())
            recent_shift = ((recent_10_avg - mean_rain) / mean_rain) * 100 if mean_rain > 0 else 0
            z = np.polyfit(df["year"].astype(float), df[var_name].astype(float), 1)
            slope = float(z[0])
            entry["stats"] = {
                "Rainfall Mean (1950+)": f"{mean_rain:.1f} mm",
                "Rainfall Variability (CV)": f"{cv:.1f}%",
                "Drought Years (<80% normal)": f"{deficit_years} years",
                "Excess Years (>120% normal)": f"{excess_years} years",
                "Recent Decade vs Normal": f"{recent_shift:+.1f}%",
                "Trend (1950+)": f"{slope:.2f} mm/year",
                "Trend Period": f"{int(df['year'].min())}-{int(df['year'].max())}",
            }
            entry["status"] = "success"
        elif len(df) > 0:
            entry["status"] = "success"
            entry["stats"] = {"Trend Period": f"{int(df['year'].min())}-{int(df['year'].max())}"}
        else:
            entry["error"] = "No rainfall samples at point"
        ds.close()
    except Exception as exc:
        entry["error"] = str(exc)
        log.warning("Climate trend failed: %s", exc)
    return entry
