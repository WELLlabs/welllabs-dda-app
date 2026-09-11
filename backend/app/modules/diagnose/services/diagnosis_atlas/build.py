"""Build the full Problem Diagnosis atlas PDF (clinton page order + field entities)."""

from __future__ import annotations

import logging
import math
import re
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.lines as mlines  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from shapely.geometry import shape  # noqa: E402

from app.modules.diagnose.services.diagnosis_atlas.appendix import append_epra_pack  # noqa: E402
from app.modules.diagnose.services.diagnosis_atlas.clip import (  # noqa: E402
    ATLAS_LAYER_ORDER,
    COMPARISON_PAIRS,
    STANDALONE_ATLAS_LAYERS,
    get_state_context,
    load_india_states,
    load_level12_subbasins,
    load_level12_within,
    load_level7_parent,
    process_layers,
    state_context_names,
)
from app.modules.diagnose.services.diagnosis_atlas.climate import load_climate_trend  # noqa: E402
from app.modules.diagnose.services.diagnosis_atlas.theme import (  # noqa: E402
    FIELD_HANDOFF_ROWS,
    MAP_GUIDE,
    footer,
    metric_card,
    page_setup,
    report_header,
    rounded_panel,
    setup_map_page,
    theme,
    wrapped,
)
from app.modules.diagnose.services.package_progress import PackageProgress  # noqa: E402

log = logging.getLogger(__name__)


def _safe_name(text: str) -> str:
    return re.sub(r"[^\w\-]+", "_", (text or "diagnosis").strip())[:60] or "diagnosis"


def _stat(results: dict, layer_id: str, *keys: str) -> str:
    entry = results.get(layer_id) or {}
    stats = entry.get("stats") or {}
    for key in keys:
        val = stats.get(key)
        if val is not None and str(val).strip():
            text = str(val).strip()
            if text.lower() not in {"n/a", "na", "none", "nan", "unknown", "data not available"}:
                return text
    return ""


def _morphometry(watershed_geom: dict) -> dict[str, str]:
    """Area (ha) and perimeter (km) for cover KPI cards."""
    try:
        from app.modules.diagnose.services.layer_analysis import _area_m2

        geom = shape(watershed_geom)
        area_m2 = _area_m2(geom)
        # Approximate perimeter via equal-area projection used in _area_m2 path, else geodesic.
        try:
            import pyproj
            from shapely.ops import transform as shp_transform

            project = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True).transform
            projected = shp_transform(project, geom)
            perim_m = float(projected.length)
        except Exception:
            # crude degree→m at mid-lat
            minx, miny, maxx, maxy = geom.bounds
            lat = (miny + maxy) / 2
            perim_m = float(geom.length) * 111_319.49 * math.cos(math.radians(lat))
        return {
            "area": f"{area_m2 / 10_000:.2f}",
            "perimeter": f"{perim_m / 1000:.2f} km",
        }
    except Exception:
        return {"area": "—", "perimeter": "—"}


def _cover_metric_cards(project: dict, results: dict) -> list[tuple[str, str, str]]:
    morph = _morphometry(project.get("watershed_geometry") or {})
    relief = _stat(results, "dem", "Relief (m)", "Elevation Relief", "Relief")
    if relief and "m" not in relief.lower():
        relief = f"{relief} m"
    drainage = _stat(results, "drainage", "Drainage Density", "Total length (km)", "Total Length")
    rainfall = _stat(results, "climate_trend", "Rainfall Mean (1950+)", "Rainfall Mean", "Mean rainfall")
    pop = _stat(results, "baseline_population", "Population in AOI", "Total population")
    return [
        ("Area", f"{morph['area']} ha", "green"),
        ("Perimeter", morph["perimeter"], "blue"),
        ("Relief", relief or "—", "amber"),
        ("Drainage", drainage or "—", "blue"),
        ("Rainfall", rainfall or "—", "green"),
        ("Pop. in AOI", pop or "—", "amber"),
    ]


def _draw_watershed_outline(ax, watershed_geom: dict, *, edge="#00306d", lw=2.0, fill=None, alpha=0.0, set_limits: bool = True):
    try:
        import geopandas as gpd

        gdf = gpd.GeoDataFrame(geometry=[shape(watershed_geom)], crs=4326)
        if fill:
            gdf.plot(ax=ax, facecolor=fill, edgecolor=edge, linewidth=lw, alpha=alpha, zorder=5)
        gdf.boundary.plot(ax=ax, color=edge, linewidth=lw, zorder=6)
        if set_limits:
            minx, miny, maxx, maxy = gdf.total_bounds
            pad_x = (maxx - minx) * 0.08 or 0.01
            pad_y = (maxy - miny) * 0.08 or 0.01
            ax.set_xlim(minx - pad_x, maxx + pad_x)
            ax.set_ylim(miny - pad_y, maxy + pad_y)
            ax.set_aspect("equal", adjustable="box")
        return gdf
    except Exception:
        ax.text(0.5, 0.5, "Watershed outline unavailable", ha="center", va="center", transform=ax.transAxes)
        return None


def _add_scale_bar(ax, watershed_geom: dict):
    try:
        from matplotlib_scalebar.scalebar import ScaleBar

        geom = shape(watershed_geom)
        minx, miny, maxx, maxy = geom.bounds
        center_lat = (miny + maxy) / 2
        dx = 111_319.49 * math.cos(math.radians(center_lat))
        scalebar = ScaleBar(
            dx=dx,
            units="m",
            fixed_units="m",
            location="lower right",
            box_alpha=0.7,
            scale_loc="bottom",
            color="#00306d",
            box_color="#ffffff",
            border_pad=0.5,
        )
        ax.add_artist(scalebar)
    except Exception as exc:
        log.debug("scale bar skipped: %s", exc)


def _add_basemap(ax, *, kind: str = "access") -> bool:
    """Add tiles in EPSG:3857. Prefer Esri — OSM Mapnik is blocked; CartoDB needs an API key."""
    try:
        import contextily as ctx
    except Exception as exc:
        log.warning("basemap deps missing: %s", exc)
        return False

    if kind == "satellite":
        sources = [
            {
                "url": "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2020_3857/default/g/{z}/{y}/{x}.jpg",
                "attribution": "Sentinel-2 cloudless by EOX",
                "name": "Sentinel-2",
                "max_zoom": 14,
            },
            getattr(ctx.providers, "Esri", None) and ctx.providers.Esri.WorldImagery,
        ]
    else:
        sources = [
            getattr(ctx.providers, "Esri", None) and ctx.providers.Esri.WorldStreetMap,
            getattr(ctx.providers, "Esri", None) and ctx.providers.Esri.WorldTopoMap,
            getattr(ctx.providers, "OpenStreetMap", None) and getattr(ctx.providers.OpenStreetMap, "HOT", None),
        ]

    last_error = None
    for source in sources:
        if not source:
            continue
        try:
            ctx.add_basemap(ax, source=source, crs="EPSG:3857", attribution_size=4, zoom="auto")
            return True
        except TypeError:
            try:
                ctx.add_basemap(ax, source=source, crs="EPSG:3857", attribution=False)
                return True
            except Exception as exc:
                last_error = exc
        except Exception as exc:
            last_error = exc
    if last_error:
        log.warning("basemap failed (%s): %s", kind, last_error)
    return False


def _get_cmap(name: str = "GnBu"):
    """Matplotlib 3.9+ removed ``plt.cm.get_cmap``; support both APIs."""
    try:
        return plt.colormaps[name]
    except Exception:
        try:
            from matplotlib import colormaps

            return colormaps[name]
        except Exception:
            return plt.cm.get_cmap(name)


def _as_bbox_tuple(bounds) -> tuple[float, float, float, float]:
    """geopandas ``total_bounds`` is a numpy ndarray; pyogrio/fiona want a tuple."""
    b = list(bounds)
    return (float(b[0]), float(b[1]), float(b[2]), float(b[3]))


def _choropleth_color(value, stops) -> str:
    try:
        fv = float(value)
    except (TypeError, ValueError):
        return "#94a3b8"
    if not stops:
        return "#94a3b8"
    for i, stop in enumerate(stops):
        lo, hi = float(stop.min), float(stop.max)
        if i == len(stops) - 1:
            if lo <= fv <= hi:
                return stop.color
        elif lo <= fv < hi:
            return stop.color
    return stops[-1].color


def _plot_vector_layer(
    ax,
    entry: dict,
    watershed_geom: dict,
    *,
    overlay_only: bool = False,
    fig=None,
    layout: str = "standalone",
):
    import matplotlib.lines as mlines
    import matplotlib.patches as mpatches

    cfg = entry.get("cfg")
    gdf = entry.get("gdf")
    legend_handles: list = []
    layout_cfg = _RASTER_LAYOUTS.get(layout) or _RASTER_LAYOUTS["standalone"]
    pair_layout = str(layout).startswith("pair_")
    if not overlay_only:
        _draw_watershed_outline(ax, watershed_geom, lw=1.6)
        # Pair pages already show the outline on both maps — skip the long
        # "Watershed boundary" label so legends stay inside the panel gutter.
        if not pair_layout:
            legend_handles.append(
                mpatches.Patch(facecolor="none", edgecolor="#00306d", linewidth=1.6, label="Watershed boundary")
            )
    if gdf is None or getattr(gdf, "empty", True):
        if not overlay_only:
            ax.text(0.5, 0.5, "No features in watershed", ha="center", va="center", transform=ax.transAxes)
            ax.set_axis_off()
            if legend_handles:
                _place_map_legend(
                    ax,
                    fig,
                    legend_handles,
                    **_legend_kwargs(layout_cfg, fig=fig),
                )
        return
    try:
        plot_gdf = gdf
        if plot_gdf.crs is None:
            plot_gdf = plot_gdf.set_crs(4326)
        else:
            plot_gdf = plot_gdf.to_crs(4326)

        col = getattr(cfg, "style_column", None) if cfg else None
        render_type = getattr(cfg, "render_type", None) if cfg else None
        is_line = (
            getattr(cfg, "geometry_kind", None) == "line"
            or render_type == "line"
        )
        if is_line:
            color = "#00306d"
            if cfg and cfg.line_color:
                color = str(cfg.line_color)
            if cfg and cfg.id == "canals":
                color = "#b5523a"
            plot_gdf.plot(ax=ax, color=color, linewidth=getattr(cfg, "line_width", 1.5) or 1.5, zorder=12)
            legend_handles.append(mlines.Line2D([], [], color=color, linewidth=2.0, label=(cfg.name if cfg else "Lines")))
        elif render_type == "choropleth" and cfg and cfg.choropleth_stops and col and col in plot_gdf.columns:
            stops = list(cfg.choropleth_stops)
            colors = [_choropleth_color(v, stops) for v in plot_gdf[col]]
            plot_gdf.plot(ax=ax, color=colors, linewidth=0.25, edgecolor="#334155", alpha=0.88, zorder=4)
            for stop in stops:
                legend_handles.append(mpatches.Patch(facecolor=stop.color, edgecolor="#334155", label=stop.label))
        elif col and col in plot_gdf.columns:
            legend_entries = cfg.legend_entries() if cfg else []
            if legend_entries:
                color_map = {}
                for e in legend_entries:
                    if not e.color:
                        continue
                    color_map[e.value] = e.color
                    color_map[str(e.value)] = e.color
                    if e.label:
                        color_map[e.label] = e.color
                colors = [color_map.get(v, color_map.get(str(v), "#94a3b8")) for v in plot_gdf[col]]
                plot_gdf.plot(ax=ax, color=colors, linewidth=0.2, edgecolor="#334155", alpha=0.85, zorder=4)
                seen = set()
                for e in legend_entries:
                    key = e.label or str(e.value)
                    if key in seen or not e.color:
                        continue
                    if str(e.color).lower().endswith("00") and len(str(e.color).lstrip("#")) == 8:
                        continue
                    legend_handles.append(mpatches.Patch(facecolor=e.color, edgecolor="#334155", label=key))
                    seen.add(key)
            else:
                plot_gdf.plot(ax=ax, column=col, legend=False, cmap="viridis", linewidth=0.2, alpha=0.85, zorder=4)
                legend_handles.append(mpatches.Patch(facecolor="#440154", label=str(col)))
        else:
            plot_gdf.plot(ax=ax, facecolor="#1c75e9", edgecolor="#00306d", linewidth=0.3, alpha=0.55, zorder=4)
            legend_handles.append(
                mpatches.Patch(facecolor="#1c75e9", edgecolor="#00306d", label=(cfg.name if cfg else "Features"))
            )
        if legend_handles:
            _place_map_legend(
                ax,
                fig,
                legend_handles[:16],
                **_legend_kwargs(layout_cfg, fig=fig),
            )
        ax.set_axis_off()
    except Exception as exc:
        ax.text(0.5, 0.5, f"Map error: {exc}", ha="center", va="center", transform=ax.transAxes, fontsize=8)


def _load_line_overlay_gdf(layer_id: str, watershed_geom: dict, results: dict | None, *, pad_deg: float = 0.02):
    """Return line overlay features that intersect the AOI.

    Distant canals must not expand the map extent — that shrinks the watershed
    to a speck. Prefer the already-clipped result; always re-filter to the AOI
    (tiny pad only for load bbox / floating-point edge touches).
    """
    try:
        import geopandas as gpd
        from shapely.geometry import shape as shp

        from app.modules.diagnose.services.layer_analysis import _vsis3_path
        from app.modules.diagnose.services.layer_catalog import get_catalog
    except Exception:
        return None

    try:
        geom = shp(watershed_geom)
        # Tiny pad for numeric edge touches only — not a soft search halo.
        soft = geom.buffer(max(0.001, min(float(pad_deg), 0.005)))
        hit = None
        entry = (results or {}).get(layer_id) or {}
        gdf = entry.get("gdf")
        if gdf is not None and not getattr(gdf, "empty", True):
            hit = gdf.copy()
            if hit.crs is None:
                hit = hit.set_crs(4326)
            else:
                hit = hit.to_crs(4326)
        else:
            cfg = next((c for c in get_catalog().layers if c.id == layer_id), None)
            if not cfg or not cfg.s3_key:
                return None
            minx, miny, maxx, maxy = soft.bounds
            raw = gpd.read_file(_vsis3_path(cfg.s3_key), bbox=_as_bbox_tuple((minx, miny, maxx, maxy)))
            if raw is None or raw.empty:
                return None
            if raw.crs is None:
                raw = raw.set_crs(4326)
            else:
                raw = raw.to_crs(4326)
            hit = raw

        hit = hit[hit.geometry.notna() & ~hit.geometry.is_empty & hit.intersects(soft)].copy()
        if hit.empty:
            return None
        # Keep only segments that actually meet the watershed (not outside-only stubs).
        try:
            hit["geometry"] = hit.geometry.intersection(soft)
            hit = hit[hit.geometry.notna() & ~hit.geometry.is_empty]
            # Drop speck fragments that only kiss the soft buffer outside the AOI.
            core = hit[hit.intersects(geom)].copy()
            hit = core if not core.empty else hit.iloc[0:0].copy()
        except Exception:
            pass
        return hit if hit is not None and not hit.empty else None
    except Exception as exc:
        log.debug("overlay load %s failed: %s", layer_id, exc)
        return None


# Layout presets: standalone map+stats, or left/right comparison panels.
_RASTER_LAYOUTS = {
    "standalone": {
        "cbar": [0.690, 0.300, 0.016, 0.480],
        # Right margin under header; stats start lower (~0.68).
        "legend_anchor": (0.755, 0.84),
        "legend_loc": "upper left",
        "legend_ncol": 1,
        "legend_fontsize": 6.5,
        "legend_on_axes": False,
        "clear_fig_legends": True,
        "legend_rect": None,
    },
    "pair_left": {
        "cbar": [0.430, 0.28, 0.012, 0.48],
        "legend_anchor": None,
        "legend_loc": "upper left",
        "legend_ncol": 3,
        "legend_fontsize": 5.4,
        "legend_on_axes": True,
        "clear_fig_legends": False,
        # Dedicated legend axes under each panel (above footer rule at y=0.052).
        "legend_rect": [0.100, 0.058, 0.300, 0.125],
    },
    "pair_right": {
        "cbar": [0.930, 0.28, 0.012, 0.48],
        "legend_anchor": None,
        "legend_loc": "upper left",
        "legend_ncol": 3,
        "legend_fontsize": 5.4,
        "legend_on_axes": True,
        "clear_fig_legends": False,
        "legend_rect": [0.590, 0.058, 0.300, 0.125],
    },
}


def _legend_kwargs(layout_cfg: dict, *, fig) -> dict:
    return {
        "loc": str(layout_cfg.get("legend_loc") or "upper left"),
        "bbox_to_anchor": layout_cfg.get("legend_anchor") if fig is not None else None,
        "ncol": int(layout_cfg.get("legend_ncol") or 1),
        "fontsize": float(layout_cfg.get("legend_fontsize") or 7.0),
        "on_axes": bool(layout_cfg.get("legend_on_axes")),
        "clear_fig_legends": bool(layout_cfg.get("clear_fig_legends")),
        "legend_rect": layout_cfg.get("legend_rect"),
    }


def _place_map_legend(
    ax,
    fig,
    handles: list,
    *,
    loc: str = "upper left",
    bbox_to_anchor: tuple[float, float] | None = None,
    ncol: int = 1,
    fontsize: float = 7.0,
    on_axes: bool = False,
    clear_fig_legends: bool = False,
    legend_rect: list[float] | tuple[float, float, float, float] | None = None,
):
    """Place overlay legend in the figure margin (never over the map axes).

    Comparison pages use a dedicated legend axes under each panel so the left
    legend is not wiped by the right panel and cannot clip off the page edge.
    """
    if not handles:
        return
    if clear_fig_legends and fig is not None:
        for leg in list(getattr(fig, "legends", []) or []):
            try:
                leg.remove()
            except Exception:
                pass

    common = dict(
        handles=handles[:14],
        loc=loc,
        framealpha=0.95,
        fontsize=fontsize,
        borderpad=0.35,
        handlelength=1.3,
        labelspacing=0.25,
        ncol=ncol,
        columnspacing=0.7,
    )
    if fig is not None and legend_rect is not None:
        lax = fig.add_axes(list(legend_rect))
        lax.set_axis_off()
        lax.set_facecolor("none")
        lax.patch.set_alpha(0.0)
        # Center inside the dedicated axes so wide 2/3-col legends stay on-page.
        lax.legend(**{**common, "loc": "center"})
        return
    if fig is not None and bbox_to_anchor is not None:
        if on_axes:
            ax.legend(
                **common,
                bbox_to_anchor=bbox_to_anchor,
                bbox_transform=fig.transFigure,
            )
        else:
            fig.legend(
                **common,
                bbox_to_anchor=bbox_to_anchor,
                bbox_transform=fig.transFigure,
            )
        return
    if fig is not None and not on_axes:
        fig.legend(
            **common,
            bbox_to_anchor=(0.755, 0.84),
            bbox_transform=fig.transFigure,
        )
        return
    ax.legend(**common)


def _draw_lulc_underlay(ax, watershed_geom: dict, results: dict | None, extent: tuple):
    """Muted LULC under CI so NaN gaps do not look like a failed raster load."""
    try:
        import matplotlib.colors as mcolors
        import numpy as np

        from app.modules.diagnose.services.diagnosis_atlas.clip import _clip_raster_array
        from app.modules.diagnose.services.layer_catalog import get_catalog

        lulc_entry = (results or {}).get("lulc250k") or {}
        raster = lulc_entry.get("raster")
        cfg = lulc_entry.get("cfg")
        if raster is None or cfg is None:
            cfg = next((c for c in get_catalog().layers if c.id == "lulc250k"), None)
            if not cfg:
                return False
            raster = _clip_raster_array(cfg, watershed_geom)
        if not raster or not cfg or not getattr(cfg, "classes", None):
            return False

        arr = np.ma.array(raster["array"])
        rgba = np.zeros((arr.shape[0], arr.shape[1], 4), dtype=float)
        for entry_cls in cfg.classes:
            val = entry_cls.value
            if val is None or (cfg.nodata is not None and val == cfg.nodata):
                continue
            color = entry_cls.color or "#888888"
            if str(color).lower().endswith("00") and len(str(color).lstrip("#")) == 8:
                continue
            try:
                rgb = list(mcolors.to_rgba(color))
            except ValueError:
                continue
            # Desaturate + lower alpha so CI remains the focus.
            rgb[3] = 0.55
            mask = arr == val
            if np.any(mask):
                rgba[mask] = rgb
        lulc_extent = raster.get("extent") or extent
        ax.imshow(rgba, extent=lulc_extent, origin="upper", interpolation="nearest", zorder=1)
        return True
    except Exception as exc:
        log.debug("LULC underlay failed: %s", exc)
        return False


def _plot_raster_layer(
    ax,
    fig,
    entry: dict,
    watershed_geom: dict,
    results: dict | None = None,
    *,
    layout: str = "standalone",
):
    raster = entry.get("raster")
    cfg = entry.get("cfg")
    layout_cfg = _RASTER_LAYOUTS.get(layout) or _RASTER_LAYOUTS["standalone"]
    _draw_watershed_outline(ax, watershed_geom, lw=1.2)
    if not raster:
        ax.text(0.5, 0.5, "Raster map unavailable", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()
        return

    try:
        import matplotlib.colors as mcolors
        import matplotlib.patches as mpatches
        import numpy as np

        arr = raster["array"]
        extent = raster.get("extent")
        if not extent:
            from rasterio.transform import array_bounds

            h, w = arr.shape
            west, south, east, north = array_bounds(h, w, raster["transform"])
            extent = (west, east, south, north)

        nodata = raster.get("nodata")
        data = np.ma.array(arr)
        if cfg and cfg.id == "cropping_intensity":
            # Clip already mapped NaN → 0.0 inside AOI; only keep outside mask.
            pass
        else:
            if nodata is not None:
                try:
                    import math

                    if isinstance(nodata, float) and math.isnan(nodata):
                        data = np.ma.masked_invalid(data)
                    else:
                        data = np.ma.masked_equal(data, nodata)
                except Exception:
                    pass
            try:
                if np.issubdtype(np.asanyarray(data).dtype, np.floating):
                    data = np.ma.masked_invalid(data)
            except Exception:
                pass

        legend_handles = []
        if cfg and cfg.render_type == "categorical" and cfg.classes:
            rgba = np.zeros((data.shape[0], data.shape[1], 4), dtype=float)
            seen = set()
            for entry_cls in cfg.classes:
                val = entry_cls.value
                if val is None:
                    continue
                if cfg.nodata is not None and val == cfg.nodata:
                    continue
                color = entry_cls.color or "#888888"
                if str(color).lower().endswith("00") and len(str(color).lstrip("#")) == 8:
                    continue
                try:
                    rgb = mcolors.to_rgba(color)
                except ValueError:
                    continue
                mask = data == val
                if not np.any(mask):
                    continue
                rgba[mask] = rgb
                label = entry_cls.label or str(val)
                if label not in seen and "Background" not in label and "No Data" not in label:
                    legend_handles.append(mpatches.Patch(color=color, label=label))
                    seen.add(label)
            ax.imshow(rgba, extent=extent, origin="upper", interpolation="nearest", zorder=2)
        else:
            cmap_name = "viridis"
            vmin = vmax = None
            if cfg and getattr(cfg, "continuous", None):
                cmap_name = str(cfg.continuous.get("colormap") or "viridis")
                if cfg.continuous.get("min") is not None:
                    vmin = float(cfg.continuous["min"])
                if cfg.continuous.get("max") is not None:
                    vmax = float(cfg.continuous["max"])
            elif cfg and cfg.id == "dem":
                cmap_name = "gist_earth"
            elif cfg and str(cfg.id).startswith("jrc"):
                cmap_name = "Blues"
            if cfg and cfg.id == "cropping_intensity":
                vmin, vmax = 0.0, 2.0
            cmap = _get_cmap(cmap_name)
            try:
                cmap = cmap.copy()
                # Outside-AOI cells stay transparent; NaN inside AOI already filled to vmin.
                cmap.set_bad((0, 0, 0, 0))
            except Exception:
                pass
            im = ax.imshow(
                data,
                cmap=cmap,
                extent=extent,
                origin="upper",
                interpolation="nearest",
                zorder=2,
                vmin=vmin,
                vmax=vmax,
            )
            cbar_rect = layout_cfg.get("cbar")
            if cbar_rect:
                cax = fig.add_axes(list(cbar_rect))
                cbar = fig.colorbar(im, cax=cax)
                cbar.ax.tick_params(labelsize=6.5, pad=1)

        # Overlays matching reference atlas habits
        rid = cfg.id if cfg else ""
        if results and rid == "dem" and layout == "standalone":
            try:
                dg = _load_line_overlay_gdf("drainage", watershed_geom, results, pad_deg=0.02)
                if dg is not None and not dg.empty:
                    plot = dg.to_crs(4326) if dg.crs else dg
                    plot.plot(ax=ax, color="#00306d", linewidth=1.0, alpha=0.85, zorder=12)
                    legend_handles.append(
                        mlines.Line2D([], [], color="#00306d", linewidth=1.2, label="Stream Network")
                    )
            except Exception:
                pass
        if results and rid == "cropping_intensity":
            try:
                # Strict AOI intersect only — do not expand the map for outside stubs.
                cg = _load_line_overlay_gdf("canals", watershed_geom, results, pad_deg=0.002)
                if cg is not None and not getattr(cg, "empty", True):
                    plot = cg.to_crs(4326) if cg.crs else cg
                    plot.plot(ax=ax, color="#b5523a", linewidth=2.0, zorder=12)
                    legend_handles.append(
                        mlines.Line2D([], [], color="#b5523a", linewidth=2.0, label="Canal Network")
                    )
                else:
                    fig._atlas_canal_note = "Canal Network: no canal features intersect this watershed AOI."
            except Exception as exc:
                log.warning("Canal overlay failed: %s", exc)

        legend_handles.append(
            mpatches.Patch(facecolor="none", edgecolor="#00306d", linewidth=1.4, label="Watershed boundary")
        )
        # Keep watershed extent — never zoom out for edge canals.
        _draw_watershed_outline(ax, watershed_geom, lw=1.4, set_limits=True)
        # Pair pages: outline is visible on both maps; omit redundant boundary legend entry.
        if str(layout).startswith("pair_"):
            legend_handles = [h for h in legend_handles if getattr(h, "get_label", lambda: "")() != "Watershed boundary"]
        _place_map_legend(
            ax,
            fig,
            legend_handles,
            **_legend_kwargs(layout_cfg, fig=fig),
        )
        _add_scale_bar(ax, watershed_geom)
        ax.set_axis_off()
    except Exception as exc:
        ax.text(0.5, 0.5, f"Raster error: {exc}", ha="center", va="center", transform=ax.transAxes, fontsize=8)


def _save_cover(pdf, project: dict, results: dict, zones: list, hypotheses: list, page_num: int):
    fig, ax = page_setup()
    generated = datetime.now().strftime("%d %b %Y, %I:%M %p")
    scale = project.get("watershed_name") or project.get("name") or "Watershed"
    ax.add_patch(plt.Rectangle((0, 0.70), 1, 0.30, facecolor=theme("green_dark"), edgecolor="none"))
    ax.text(0.055, 0.925, "WATER SECURITY ATLAS", fontsize=8, color=theme("sky"), fontweight="bold", ha="left", va="top")
    ax.text(0.055, 0.860, "Problem Diagnosis Report", fontsize=28, color=theme("white"), fontweight="bold", ha="left", va="top")
    ax.text(0.055, 0.805, scale, fontsize=18, color=theme("cream"), ha="left", va="top")
    ax.text(0.945, 0.920, generated, fontsize=9, color=theme("sky"), ha="right", va="top")
    if project.get("seed_lat") is not None and project.get("seed_lng") is not None:
        ax.text(
            0.945,
            0.890,
            f"Selected point: {float(project['seed_lat']):.5f}, {float(project['seed_lng']):.5f}",
            fontsize=8.5,
            color=theme("sky"),
            ha="right",
            va="top",
        )

    cards = _cover_metric_cards(project, results)
    x0, y0, w, h = 0.055, 0.575, 0.140, 0.085
    gap = 0.012
    for i, (label, value, accent) in enumerate(cards):
        metric_card(ax, x0 + i * (w + gap), y0, w, h, label, value, accent)

    left_patch = rounded_panel(ax, 0.045, 0.330, 0.425, 0.195, face="panel")
    ax.text(0.075, 0.492, "How to read this report", fontsize=12, color=theme("ink"), fontweight="bold", ha="left", va="top")
    bullets = [
        "Start with the map category guide and context maps.",
        "Read analytical layers as linked evidence, not standalone facts.",
        "Use the summary and ePRA appendix to validate field hypotheses.",
    ]
    y = 0.455
    for b in bullets:
        ax.plot(0.080, y - 0.004, "o", color=theme("green"), markersize=4)
        y = wrapped(ax, b, 0.102, y, width=46, fontsize=8.5, line_step=0.018) - 0.006

    rounded_panel(ax, 0.505, 0.330, 0.445, 0.195, face="panel_alt")
    ax.text(0.535, 0.492, "Reader path", fontsize=12, color=theme("ink"), fontweight="bold", ha="left", va="top")
    steps = [
        ("Locate", "context and satellite"),
        ("Read water", "terrain, LULC, aquifer, climate"),
        ("Read people", "population and inclusion"),
        ("Verify", "transect, FGD, ePRA"),
    ]
    step_gap = 0.010
    sx0 = 0.535
    sw = (0.385 - 3 * step_gap) / 4
    for idx, (label, desc) in enumerate(steps, start=1):
        x = sx0 + (idx - 1) * (sw + step_gap)
        rounded_panel(ax, x, 0.355, sw, 0.105, face="#ffffff", radius=0.010)
        ax.text(x + 0.010, 0.440, f"{idx}. {label}", fontsize=7.2, color=theme("green_dark"), fontweight="bold", ha="left", va="top")
        wrapped(ax, desc, x + 0.010, 0.415, width=14, fontsize=6.0, color="muted", line_step=0.013)

    ready = [r.get("name") for lid in ATLAS_LAYER_ORDER if (r := results.get(lid)) and r.get("status") == "success"]
    for lid, r in results.items():
        if lid not in ATLAS_LAYER_ORDER and r.get("status") == "success" and r.get("name") not in ready:
            ready.append(r.get("name"))
    rounded_panel(ax, 0.045, 0.145, 0.905, 0.130, face="panel")
    ax.text(0.070, 0.245, "Map sequence / checked layers", fontsize=9.3, color=theme("ink"), fontweight="bold", ha="left", va="top")
    wrapped(ax, ", ".join(ready[:14]) or "No layers clipped yet", 0.070, 0.215, width=130, fontsize=7.4, color="muted", line_step=0.015)

    # Keep zones/hypotheses counts visible without replacing morphometry KPIs
    note = f"Obs. zones: {len(zones)} · Hypotheses: {len(hypotheses)} · Validated: {sum(1 for h in hypotheses if h.get('status') == 'validated')}"
    ax.text(0.070, 0.160, note, fontsize=7.0, color=theme("brown"), ha="left", va="top")

    footer(ax, "Generated by the Problem Diagnosis toolbox", page_num)
    _ = left_patch
    pdf.savefig(fig)
    plt.close(fig)


def _save_guide(pdf, project: dict, page_num: int):
    fig, ax = page_setup()
    scale = project.get("watershed_name") or project.get("name") or "this watershed"
    report_header(ax, "Map Section Guide", f"Four map categories used for {scale}.", section="Map Guide")
    footer(ax, "Map categories shown before the map atlas begins", page_num)
    wrapped(
        ax,
        "Use this guide to read the atlas in order: first locate the area, then read physical water controls, then check who is affected.",
        0.070,
        0.815,
        width=118,
        fontsize=9.0,
        line_step=0.021,
    )
    y = 0.720
    for idx, (title, body) in enumerate(MAP_GUIDE, start=1):
        rounded_panel(ax, 0.070, y - 0.100, 0.860, 0.090, face="panel")
        ax.text(0.095, y - 0.028, f"{idx}. {title}", fontsize=10.8, color=theme("ink"), fontweight="bold", ha="left", va="top")
        wrapped(ax, body, 0.095, y - 0.055, width=120, fontsize=7.5, color="muted", line_step=0.015)
        y -= 0.115
    ax.text(
        0.070,
        0.115,
        "Paired maps are shown once as paired spreads; duplicate standalone pages are skipped.",
        fontsize=8.2,
        color=theme("brown"),
        ha="left",
        va="center",
    )
    pdf.savefig(fig)
    plt.close(fig)


def _save_location_context(pdf, project: dict, page_num: int):
    """India / state / watershed zoom triad using real state boundaries (clinton)."""
    fig, ax_bg = page_setup()
    scale = project.get("watershed_name") or project.get("name") or "Watershed"
    geom = project.get("watershed_geometry")
    context_states = get_state_context(geom) if geom else None
    state_names = state_context_names(context_states)
    state_label = ", ".join(state_names[:2]) if state_names else "state context"
    report_header(
        ax_bg,
        "Location Context",
        f"India to state to watershed hierarchy for {scale}.",
        section="Context Maps",
        right_label=state_label if state_names else "",
    )
    footer(ax_bg, "Location orientation before analytical layers", page_num)
    if state_names:
        ax_bg.text(
            0.500,
            0.086,
            f"State: {state_label}",
            fontsize=8.2,
            color=theme("ink"),
            ha="center",
            va="center",
            fontweight="bold",
        )

    ax_india = fig.add_axes([0.055, 0.160, 0.285, 0.665])
    ax_state = fig.add_axes([0.380, 0.160, 0.270, 0.665])
    ax_zoom = fig.add_axes([0.690, 0.160, 0.265, 0.665])
    for ax in (ax_india, ax_state, ax_zoom):
        ax.set_facecolor(theme("panel"))

    if not geom:
        for ax in (ax_india, ax_state, ax_zoom):
            ax.text(0.5, 0.5, "No geometry", ha="center", va="center", transform=ax.transAxes)
            ax.set_axis_off()
        pdf.savefig(fig)
        plt.close(fig)
        return

    try:
        import geopandas as gpd
        import matplotlib.patches as mpatches
        from shapely.geometry import shape as shp

        selected = gpd.GeoDataFrame(geometry=[shp(geom)], crs=4326)
        point = selected.geometry.iloc[0].representative_point()
        india = load_india_states()

        # --- India panel: all states, highlight intersecting state(s) ---
        try:
            if india is not None and not india.empty:
                india.plot(ax=ax_india, facecolor=theme("white"), edgecolor=theme("muted"), linewidth=0.55, alpha=0.88)
                if context_states is not None and not context_states.empty:
                    context_states.plot(ax=ax_india, facecolor="#74c0e8", edgecolor=theme("ink"), linewidth=1.05, alpha=0.96)
                ax_india.plot(
                    point.x,
                    point.y,
                    marker="o",
                    color=theme("rust"),
                    markersize=6.5,
                    markeredgecolor="white",
                    markeredgewidth=1.1,
                    zorder=10,
                )
                minx, miny, maxx, maxy = india.total_bounds
                ax_india.set_xlim(minx - 1.0, maxx + 1.0)
                ax_india.set_ylim(miny - 1.0, maxy + 1.0)
                ax_india.legend(
                    handles=[
                        mpatches.Patch(facecolor="#74c0e8", edgecolor=theme("ink"), label="State"),
                        mpatches.Patch(facecolor=theme("rust"), edgecolor=theme("brown"), label="Basin location"),
                    ],
                    loc="lower left",
                    framealpha=0.93,
                    fontsize=7.0,
                )
            else:
                ax_india.text(
                    0.5,
                    0.5,
                    "India boundary layer unavailable",
                    ha="center",
                    va="center",
                    color=theme("muted"),
                    fontsize=8,
                    transform=ax_india.transAxes,
                )
        except Exception as exc:
            ax_india.text(
                0.5,
                0.5,
                f"India context unavailable\n{exc}",
                ha="center",
                va="center",
                fontsize=7,
                transform=ax_india.transAxes,
                color=theme("muted"),
            )
        ax_india.set_title("India", fontsize=9, color=theme("ink"), pad=4, fontweight="bold")
        ax_india.text(
            0.5,
            -0.04,
            "State containing the selected basin",
            transform=ax_india.transAxes,
            ha="center",
            fontsize=7,
            color=theme("muted"),
        )
        ax_india.set_axis_off()

        # --- State zoom: intersecting state outline + selected AOI (or L7 parent if tiny) ---
        try:
            parent_for_state = load_level7_parent(geom)
            if context_states is not None and not context_states.empty:
                context_states.plot(ax=ax_state, facecolor=theme("panel_alt"), edgecolor=theme("brown"), linewidth=1.0)
                highlight = parent_for_state if parent_for_state is not None and not parent_for_state.empty else selected
                highlight_label = "Basin Level 7" if highlight is parent_for_state else f"Selected {scale}"
                highlight.plot(ax=ax_state, facecolor=theme("rust"), edgecolor=theme("brown"), linewidth=1.2, alpha=0.82, zorder=8)
                # Pin the exact AOI so micro-watersheds stay findable at state scale.
                ax_state.plot(
                    point.x,
                    point.y,
                    marker="o",
                    color=theme("ink"),
                    markersize=5.0,
                    markeredgecolor="white",
                    markeredgewidth=0.9,
                    zorder=11,
                )
                minx, miny, maxx, maxy = context_states.total_bounds
                pad_x = (maxx - minx) * 0.08 or 0.05
                pad_y = (maxy - miny) * 0.08 or 0.05
                ax_state.set_xlim(minx - pad_x, maxx + pad_x)
                ax_state.set_ylim(miny - pad_y, maxy + pad_y)
                ax_state.legend(
                    handles=[
                        mpatches.Patch(facecolor=theme("panel_alt"), edgecolor=theme("brown"), label="State boundary"),
                        mpatches.Patch(facecolor=theme("rust"), edgecolor=theme("brown"), label=highlight_label),
                    ],
                    loc="upper right",
                    framealpha=0.93,
                    fontsize=6.5,
                )
            else:
                selected.plot(ax=ax_state, facecolor=theme("rust"), edgecolor=theme("brown"), linewidth=1.4, alpha=0.82)
                minx, miny, maxx, maxy = selected.total_bounds
                pad_x = (maxx - minx) * 0.12 or 0.02
                pad_y = (maxy - miny) * 0.12 or 0.02
                ax_state.set_xlim(minx - pad_x, maxx + pad_x)
                ax_state.set_ylim(miny - pad_y, maxy + pad_y)
                ax_state.legend(
                    handles=[mpatches.Patch(facecolor=theme("rust"), edgecolor=theme("brown"), label=f"Selected {scale}")],
                    loc="upper right",
                    framealpha=0.93,
                    fontsize=6.5,
                )
        except Exception as exc:
            selected.plot(ax=ax_state, facecolor=theme("rust"), edgecolor=theme("brown"), linewidth=1.4, alpha=0.82)
            log.debug("state zoom fallback: %s", exc)
        ax_state.set_title("State Zoom", fontsize=9, color=theme("ink"), pad=4, fontweight="bold")
        ax_state.text(
            0.5,
            -0.04,
            f"{scale} within {state_label}",
            transform=ax_state.transAxes,
            ha="center",
            fontsize=7,
            color=theme("muted"),
        )
        ax_state.set_axis_off()

        # --- Watershed zoom: prefer L7 parent + selected; else nested L12 ---
        try:
            parent = load_level7_parent(geom)
            handles = []
            subtitle = "Selected analysis boundary"
            if parent is not None and not parent.empty:
                parent.plot(ax=ax_zoom, facecolor=theme("panel_alt"), edgecolor=theme("ink"), linewidth=1.6, alpha=0.92)
                selected.plot(ax=ax_zoom, facecolor=theme("rust"), edgecolor=theme("brown"), linewidth=1.5, alpha=0.82, zorder=9)
                bounds_src = parent
                handles = [
                    mpatches.Patch(facecolor=theme("panel_alt"), edgecolor=theme("ink"), label="Basin Level 7"),
                    mpatches.Patch(facecolor=theme("rust"), edgecolor=theme("brown"), label=f"Selected {scale}"),
                ]
                subtitle = f"{scale} inside Basin Level 7"
            else:
                l12 = load_level12_subbasins(geom)
                if l12 is not None and not l12.empty:
                    l12.plot(ax=ax_zoom, facecolor=theme("sky"), edgecolor=theme("line"), linewidth=0.45, alpha=0.78)
                    selected.plot(ax=ax_zoom, facecolor="none", edgecolor=theme("ink"), linewidth=2.0, zorder=9)
                    bounds_src = selected
                    handles = [
                        mpatches.Patch(facecolor=theme("sky"), edgecolor=theme("line"), label="Nested Basin Level 12"),
                        mpatches.Patch(facecolor="none", edgecolor=theme("ink"), label=f"Selected {scale}"),
                    ]
                    subtitle = "Nested Basin Level 12 units inside selected boundary"
                else:
                    selected.plot(ax=ax_zoom, facecolor=theme("rust"), edgecolor=theme("brown"), linewidth=1.5, alpha=0.82)
                    bounds_src = selected
                    handles = [mpatches.Patch(facecolor=theme("rust"), edgecolor=theme("brown"), label=f"Selected {scale}")]
            minx, miny, maxx, maxy = bounds_src.total_bounds
            pad_x = (maxx - minx) * 0.14 or 0.01
            pad_y = (maxy - miny) * 0.14 or 0.01
            ax_zoom.set_xlim(minx - pad_x, maxx + pad_x)
            ax_zoom.set_ylim(miny - pad_y, maxy + pad_y)
            ax_zoom.legend(handles=handles, loc="lower right", framealpha=0.93, fontsize=7.0)
            ax_zoom.set_title("Watershed Zoom", fontsize=9, color=theme("ink"), pad=4, fontweight="bold")
            ax_zoom.text(0.5, -0.04, subtitle, transform=ax_zoom.transAxes, ha="center", fontsize=6.5, color=theme("muted"))
        except Exception as exc:
            ax_zoom.text(
                0.5,
                0.5,
                f"Watershed zoom unavailable\n{exc}",
                ha="center",
                va="center",
                fontsize=7,
                transform=ax_zoom.transAxes,
            )
        ax_zoom.set_axis_off()
    except Exception as exc:
        ax_india.text(0.5, 0.5, str(exc), ha="center", va="center", transform=ax_india.transAxes, fontsize=8)
        ax_india.set_axis_off()
        ax_state.set_axis_off()
        ax_zoom.set_axis_off()

    pdf.savefig(fig)
    plt.close(fig)


def _save_level12_hierarchy(pdf, project: dict, page_num: int):
    fig, ax_bg, ax = setup_map_page(
        "Basin Level 12 Sub-basins & Level 7 Boundary",
        "Nested sub-basins, selected location, and upstream contributing area context.",
        section="Context Maps",
        footer_label="Basin level 12 and 7 drainage network relation map",
    )
    footer(ax_bg, "Basin level 12 and 7 drainage network relation map", page_num)
    # Leave right gutter for external legend so it never covers nested basins.
    ax.set_position([0.085, 0.265, 0.680, 0.555])

    geom = project.get("watershed_geometry")
    if not geom:
        ax.text(0.5, 0.5, "No watershed geometry", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()
        pdf.savefig(fig)
        plt.close(fig)
        return

    try:
        import matplotlib.colors as mcolors
        import matplotlib.patches as mpatches
        import numpy as np
        import geopandas as gpd
        from shapely.geometry import shape as shp

        selected = gpd.GeoDataFrame(geometry=[shp(geom)], crs=4326)
        l7 = load_level7_parent(geom)
        boundary = l7 if l7 is not None and not l7.empty else selected
        l12 = load_level12_within(boundary, clip_to_boundary=True)
        legend_handles = []

        if l12 is not None and not l12.empty:
            theme_col = next((c for c in ("UP_AREA", "SUB_AREA", "ORDER") if c in l12.columns), None)
            if theme_col:
                l12 = l12.copy()
                l12[theme_col] = np.array(
                    [
                        float(str(v).replace(",", "").strip())
                        if str(v).replace(",", "").strip() not in {"", "None", "nan", "NaN"}
                        else np.nan
                        for v in l12[theme_col]
                    ],
                    dtype=float,
                )
                cmap = _get_cmap("GnBu")
                valid = l12[theme_col][np.isfinite(l12[theme_col])]
                vmin = float(valid.min()) if len(valid) else 0.0
                vmax = float(valid.max()) if len(valid) and float(valid.max()) != vmin else vmin + 1.0
                norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
                l12.plot(ax=ax, column=theme_col, cmap=cmap, norm=norm, edgecolor="#00306d", linewidth=0.35, alpha=0.88, legend=False)
                cax = fig.add_axes([0.180, 0.125, 0.520, 0.032])
                sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
                sm.set_array([])
                labels = {
                    "UP_AREA": "Upstream contributing area (sq km)",
                    "SUB_AREA": "Nested sub-basin area (sq km)",
                    "ORDER": "Nested sub-basin stream order",
                }
                cbar = fig.colorbar(sm, cax=cax, orientation="horizontal")
                cbar.set_label(labels.get(theme_col, theme_col), fontsize=7.4, color="#00306d")
                cbar.ax.tick_params(labelsize=6.8, colors="#00306d")
            else:
                l12.plot(ax=ax, facecolor="#e6e9eb", edgecolor="#6e3f2e", linewidth=0.8)
                legend_handles.append(mpatches.Patch(facecolor="#e6e9eb", edgecolor="#6e3f2e", label="Basin Level 12"))
        else:
            ax.text(0.5, 0.55, "Level-12 sub-basins unavailable for this AOI", ha="center", va="center", transform=ax.transAxes, color=theme("muted"))

        # Hatch the project L12 (AOI), falling back to seed point containment.
        hatch_gdf = selected
        if project.get("seed_lat") is not None and project.get("seed_lng") is not None and l12 is not None and not l12.empty:
            from shapely.geometry import Point

            pt = Point(float(project["seed_lng"]), float(project["seed_lat"]))
            hit = l12[l12.contains(pt) | l12.covers(pt)]
            if hit.empty:
                hit = l12[l12.intersects(pt.buffer(1e-6))]
            if not hit.empty:
                hatch_gdf = hit
        hatch_gdf.plot(ax=ax, facecolor="#fcb912", edgecolor="#6e3f2e", linewidth=2.0, alpha=0.90, hatch="//", zorder=9)
        legend_handles.append(
            mpatches.Patch(facecolor="#fcb912", edgecolor="#6e3f2e", hatch="//", label="Selected Basin Level 12")
        )

        boundary.plot(ax=ax, facecolor="none", edgecolor="#00306d", linewidth=2.5, zorder=10)
        legend_handles.append(
            mpatches.Patch(facecolor="none", edgecolor="#00306d", linewidth=2.0, label="Basin Level 7 Boundary")
        )
        if l7 is None or getattr(l7, "empty", True):
            # Fallback note when parent L7 could not be resolved from S3/cache.
            fig.text(
                0.785,
                0.72,
                "Level-7 parent\nunavailable;\nshowing AOI\noutline.",
                ha="left",
                va="top",
                fontsize=6.2,
                color=theme("brown"),
            )

        if legend_handles:
            fig.legend(
                handles=legend_handles,
                loc="upper left",
                bbox_to_anchor=(0.785, 0.82),
                bbox_transform=fig.transFigure,
                framealpha=0.95,
                fontsize=7.0,
                borderpad=0.4,
                handlelength=1.5,
                labelspacing=0.4,
            )

        minx, miny, maxx, maxy = boundary.total_bounds
        pad_x = (maxx - minx) * 0.12 or 0.01
        pad_y = (maxy - miny) * 0.12 or 0.01
        ax.set_xlim(minx - pad_x, maxx + pad_x)
        ax.set_ylim(miny - pad_y, maxy + pad_y)
        ax.set_aspect("equal", adjustable="box")
        try:
            from shapely.geometry import mapping

            extent_geom = boundary.geometry.iloc[0]
            _add_scale_bar(ax, mapping(extent_geom))
        except Exception:
            _add_scale_bar(ax, geom)
        note = (
            "Darker nested basins have larger upstream contributing area: a proxy for accumulated-flow potential "
            "from upstream catchments, not guaranteed seasonal water availability. The hatched basin is the selected Level 12 location."
        )
        fig.text(
            0.5,
            0.198,
            "\n".join(textwrap.wrap(note, width=116)[:2]),
            ha="center",
            va="center",
            fontsize=7.2,
            color="#00306d",
            linespacing=1.08,
            bbox=dict(facecolor="white", edgecolor="#a3d8f4", linewidth=0.8, boxstyle="round,pad=0.34", alpha=0.96),
        )
        ax.set_axis_off()
    except Exception as exc:
        ax.text(0.5, 0.5, f"Hierarchy map error:\n{exc}", ha="center", va="center", transform=ax.transAxes, fontsize=8)
        ax.set_axis_off()
    pdf.savefig(fig)
    plt.close(fig)


def _save_climate_trend(pdf, climate: dict, page_num: int):
    fig, ax_bg, ax = setup_map_page(
        "Climate Trend (Historical Analysis)",
        "Annual rainfall trend shown from 1950 to the latest available year.",
        section="Hydrology & Landscape Controls",
        footer_label="Climate Trend historical chart page",
        # Leave right gutter for watershed stats (same pattern as layer maps).
        map_rect=(0.070, 0.178, 0.620, 0.640),
    )
    footer(ax_bg, "Climate Trend historical chart page", page_num)
    ax.set_axis_on()
    ax.set_aspect("auto")
    ax.set_facecolor(theme("cream"))
    ax.tick_params(axis="both", which="major", labelsize=8, colors=theme("ink"))
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color(theme("line"))
        spine.set_linewidth(0.8)

    trend_data = climate.get("trend_data") or []
    if not trend_data or climate.get("status") != "success":
        ax.text(0.5, 0.5, climate.get("error") or "Rainfall timeseries unavailable", ha="center", va="center", transform=ax.transAxes)
    else:
        import numpy as np

        years = [int(row["year"]) for row in trend_data]
        val_key = next(k for k in trend_data[0].keys() if k != "year")
        vals = [row[val_key] for row in trend_data]
        ax.plot(years, vals, color=theme("ink"), linewidth=1.45, alpha=0.72)
        ax.set_xlim(min(years), max(years))
        ax.margins(x=0.01, y=0.08)
        ax.text(
            0.012,
            0.965,
            f"Period shown: {min(years)}-{max(years)}",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=8.0,
            color=theme("ink"),
            bbox=dict(facecolor=theme("white"), edgecolor=theme("line"), boxstyle="round,pad=0.25", alpha=0.94),
        )
        if len(years) > 1:
            z = np.polyfit(years, vals, 1)
            p = np.poly1d(z)
            trend_value = (climate.get("stats") or {}).get("Trend (1950+)") or ""
            trend_label = f"Trend: {trend_value}" if trend_value else "Trend"
            ax.plot(years, p(years), color=theme("rust"), linestyle="--", linewidth=2.4, label=trend_label)
            ax.legend(loc="upper right", framealpha=0.92, fontsize=8.5)
        ax.set_ylabel(f"Annual {val_key.capitalize()} (mm)", fontsize=9.5, color=theme("ink"))
        ax.set_xlabel("Year (1950 to latest available)", fontsize=9.5, color=theme("ink"))
        ax.grid(True, linestyle=":", alpha=0.45, color=theme("muted"))

    # Stats in the right margin — clear of the chart axes.
    stats = climate.get("stats") or {}
    if stats:
        y = 0.78
        ax_bg.text(0.755, y, "Watershed stats", fontsize=8.5, color=theme("ink"), fontweight="bold", ha="left", va="top")
        y -= 0.030
        for k, v in list(stats.items())[:10]:
            for line in textwrap.wrap(f"{k}: {v}", width=28)[:2]:
                ax_bg.text(0.755, y, line, fontsize=6.2, color=theme("muted"), ha="left", va="top")
                y -= 0.018
            y -= 0.004
            if y < 0.18:
                break
    pdf.savefig(fig)
    plt.close(fig)


def _save_access_satellite_context(pdf, project: dict, page_num: int):
    """Dual OSM-style access + satellite spread (reference atlas)."""
    fig, ax_bg = page_setup()
    scale = project.get("watershed_name") or project.get("name") or "Watershed"
    report_header(
        ax_bg,
        f"Access & Built Environment Context: {scale}",
        "Roads, settlements, labels, and high-resolution imagery for orientation.",
        section="Context Maps",
    )
    footer(ax_bg, "Access and satellite context shown together; standalone terrain and satellite pages are omitted", page_num)

    geom = project.get("watershed_geometry")
    ax_access = fig.add_axes([0.055, 0.175, 0.405, 0.650])
    ax_satellite = fig.add_axes([0.540, 0.175, 0.405, 0.650])

    if not geom:
        for ax in (ax_access, ax_satellite):
            ax.text(0.5, 0.5, "No watershed geometry", ha="center", va="center", transform=ax.transAxes)
            ax.set_axis_off()
        pdf.savefig(fig)
        plt.close(fig)
        return

    try:
        import geopandas as gpd

        gdf = gpd.GeoDataFrame(geometry=[shape(geom)], crs=4326).to_crs(epsg=3857)
        bounds = gdf.total_bounds
        x_margin = (bounds[2] - bounds[0]) * 0.15 or 500
        y_margin = (bounds[3] - bounds[1]) * 0.15 or 500
        xlim = (bounds[0] - x_margin, bounds[2] + x_margin)
        ylim = (bounds[1] - y_margin, bounds[3] + y_margin)

        for ax, edge, fill_alpha, kind, title, caption in [
            (ax_access, "#b5523a", 0.08, "access", "Access & Built Environment", "Roads, settlements, labels, and nearby infrastructure"),
            (ax_satellite, "#fcb912", 0.08, "satellite", "High-Resolution Satellite", "Imagery reference for land cover and surface context"),
        ]:
            ax.set_xlim(*xlim)
            ax.set_ylim(*ylim)
            ax.set_aspect("equal")
            ax.set_axis_off()
            gdf.plot(ax=ax, facecolor=edge, edgecolor=edge, linewidth=2.4, alpha=fill_alpha, zorder=5)
            gdf.boundary.plot(ax=ax, color=edge, linewidth=2.4, zorder=6)
            ok = _add_basemap(ax, kind=kind)
            if not ok:
                ax.set_facecolor("#e8eef3" if kind == "access" else "#2d3a2e")
                ax.text(
                    0.5,
                    0.5,
                    "Basemap tiles unavailable\n(boundary shown)",
                    ha="center",
                    va="center",
                    transform=ax.transAxes,
                    color=theme("ink") if kind == "access" else "white",
                    fontsize=8,
                )
            ax.text(0.5, -0.04, caption, transform=ax.transAxes, ha="center", va="top", fontsize=7.5, color=theme("muted"))
            ax.set_title(title, fontsize=9, color=theme("ink"), pad=6)
            try:
                from matplotlib_scalebar.scalebar import ScaleBar

                # Web Mercator metres need latitude correction
                minx, miny, maxx, maxy = gdf.total_bounds
                # convert mid-y to lat
                import pyproj

                _, lat = pyproj.Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform(
                    (minx + maxx) / 2, (miny + maxy) / 2
                )
                dx = math.cos(math.radians(lat))
                ax.add_artist(
                    ScaleBar(
                        dx=dx,
                        units="m",
                        fixed_units="m",
                        location="lower right",
                        box_alpha=0.7,
                        color="#00306d",
                        box_color="#ffffff",
                    )
                )
            except Exception:
                pass
    except Exception as exc:
        ax_access.text(0.5, 0.5, f"Context map error:\n{exc}", ha="center", va="center", transform=ax_access.transAxes, fontsize=8)
        ax_access.set_axis_off()
        ax_satellite.set_axis_off()

    pdf.savefig(fig)
    plt.close(fig)


_ZONE_COLOR_FALLBACKS = (
    "#ef4444",
    "#f97316",
    "#eab308",
    "#186d13",
    "#1b75e0",
    "#a855f7",
    "#ec4899",
)
_ZONE_COLOR_IDS = {
    "red": "#ef4444",
    "orange": "#f97316",
    "amber": "#eab308",
    "green": "#186d13",
    "blue": "#1b75e0",
    "violet": "#a855f7",
    "pink": "#ec4899",
}
_HYP_STATUS_COLORS = {
    "validated": "#186d13",
    "rejected": "#b91c1c",
    "inconclusive": "#b45309",
    "untested": "#1b75e0",
    "open": "#1b75e0",
}


def _zone_hex(zone: dict, index: int = 0) -> str:
    raw = str(zone.get("color") or "").strip()
    if raw.startswith("#") and len(raw) >= 4:
        return raw
    if raw.lower() in _ZONE_COLOR_IDS:
        return _ZONE_COLOR_IDS[raw.lower()]
    return _ZONE_COLOR_FALLBACKS[index % len(_ZONE_COLOR_FALLBACKS)]


def _save_zones_page(pdf, project: dict, zones: list, hypotheses: list, page_num: int):
    """Color-coded observation zones over an OSM/street basemap + ask/observe table."""
    fig, ax_bg = page_setup()
    report_header(
        ax_bg,
        "Observation Zones",
        "Color-coded field zones on an access basemap, with what to ask and observe.",
        section="Field Entities",
    )
    footer(ax_bg, "Observation zones from the diagnose project", page_num)

    geom = project.get("watershed_geometry")
    # Leave ≥0.52 of page width for the ask/observe table (right margin ~0.04).
    ax_map = fig.add_axes([0.04, 0.16, 0.38, 0.66])
    ax_map.set_facecolor("#e8eef3")

    zone_colors: list[str] = [_zone_hex(z, i) for i, z in enumerate(zones)]
    try:
        import geopandas as gpd

        # Web Mercator for OSM/Esri street tiles
        if geom:
            ws_gdf = gpd.GeoDataFrame(geometry=[shape(geom)], crs=4326).to_crs(epsg=3857)
            minx, miny, maxx, maxy = ws_gdf.total_bounds
            pad_x = (maxx - minx) * 0.18 or 400
            pad_y = (maxy - miny) * 0.18 or 400
            ax_map.set_xlim(minx - pad_x, maxx + pad_x)
            ax_map.set_ylim(miny - pad_y, maxy + pad_y)
            ax_map.set_aspect("equal")
            _add_basemap(ax_map, kind="access")
            ws_gdf.boundary.plot(ax=ax_map, color="#00306d", linewidth=2.0, zorder=6)

        rows = []
        for i, z in enumerate(zones):
            g = z.get("geometry")
            if not g:
                continue
            rows.append(
                {
                    "text": z.get("text") or f"Zone {i + 1}",
                    "color": zone_colors[i] if i < len(zone_colors) else _zone_hex(z, i),
                    "geometry": shape(g) if isinstance(g, dict) else g,
                }
            )

        if rows:
            zgdf = gpd.GeoDataFrame(rows, crs=4326).to_crs(epsg=3857)
            for color in zgdf["color"].unique():
                subset = zgdf[zgdf["color"] == color]
                subset.plot(ax=ax_map, facecolor=color, edgecolor="#00306d", alpha=0.45, linewidth=1.4, zorder=7)
            # Expand view to include zones if they extend past watershed
            zminx, zminy, zmaxx, zmaxy = zgdf.total_bounds
            cur_x = ax_map.get_xlim()
            cur_y = ax_map.get_ylim()
            ax_map.set_xlim(min(cur_x[0], zminx - 200), max(cur_x[1], zmaxx + 200))
            ax_map.set_ylim(min(cur_y[0], zminy - 200), max(cur_y[1], zmaxy + 200))
        elif not zones:
            ax_map.text(
                0.5,
                0.5,
                "No observation zones marked yet",
                ha="center",
                va="center",
                transform=ax_map.transAxes,
                color=theme("muted"),
                fontsize=9,
            )
        ax_map.set_axis_off()
        ax_map.set_title("Zones on access basemap", fontsize=8.5, color=theme("ink"), pad=4)
        try:
            from matplotlib_scalebar.scalebar import ScaleBar

            ax_map.add_artist(
                ScaleBar(
                    dx=1,
                    units="m",
                    fixed_units="m",
                    location="lower right",
                    box_alpha=0.75,
                    color="#00306d",
                    box_color="#ffffff",
                )
            )
        except Exception:
            pass
    except Exception as exc:
        ax_map.text(0.5, 0.5, f"Zone map error:\n{exc}", ha="center", va="center", transform=ax_map.transAxes, fontsize=8)
        ax_map.set_axis_off()

    # Color-coded ask / observe table
    hyp_by_zone: dict[str, list[str]] = {}
    for h in hypotheses:
        label = (h.get("hypothesis") or "")[:50]
        for zid in h.get("observation_zone_ids") or []:
            hyp_by_zone.setdefault(str(zid), []).append(label)

    # Colored # | Zone | Observe | Ask | Linked hyp. — must fit within page (x ≤ 0.96).
    headers = ["#", "Zone", "What to\nobserve", "What to\nask", "Linked\nhypothesis"]
    col_w = [0.032, 0.088, 0.132, 0.132, 0.112]  # sum 0.496 → ends ~0.941
    x0, y = 0.445, 0.80
    x = x0
    for j, h in enumerate(headers):
        ax_bg.add_patch(
            plt.Rectangle((x, y - 0.046), col_w[j], 0.046, facecolor=theme("green_dark"), edgecolor=theme("line"), linewidth=0.5)
        )
        ax_bg.text(x + 0.004, y - 0.01, h, fontsize=5.8, color="white", fontweight="bold", va="top", linespacing=1.05)
        x += col_w[j]
    y -= 0.046

    table_rows = zones or []
    if not table_rows:
        table_rows = [{"text": "No zones marked yet", "observations": "—", "questions": "—", "id": ""}]

    for ri, z in enumerate(table_rows[:9]):
        color = zone_colors[ri] if ri < len(zone_colors) else _ZONE_COLOR_FALLBACKS[ri % len(_ZONE_COLOR_FALLBACKS)]
        zid = str(z.get("id") or "")
        linked = "; ".join(hyp_by_zone.get(zid, [])[:2]) or "—"
        vals = [
            str(ri + 1),
            (z.get("text") or f"Zone {ri + 1}")[:40],
            (z.get("observations") or "—")[:90],
            (z.get("questions") or "—")[:90],
            linked[:60],
        ]
        x = x0
        face = "#ffffff" if ri % 2 == 0 else theme("panel_alt")
        rh = 0.068
        for j, cell in enumerate(vals):
            face_cell = color if j == 0 else face
            text_color = "#ffffff" if j == 0 else theme("ink")
            ax_bg.add_patch(
                plt.Rectangle((x, y - rh), col_w[j], rh, facecolor=face_cell, edgecolor=theme("line"), linewidth=0.55)
            )
            wrap = [3, 14, 22, 22, 18][j]
            ax_bg.text(
                x + 0.003,
                y - 0.01,
                "\n".join(textwrap.wrap(str(cell), wrap)[:4]),
                fontsize=5.5,
                color=text_color,
                va="top",
                fontweight="bold" if j == 0 else "normal",
                clip_on=True,
            )
            x += col_w[j]
        y -= rh
        if y < 0.10:
            break

    pdf.savefig(fig)
    plt.close(fig)


def _save_hypotheses_page(pdf, zones: list, hypotheses: list, page_num: int):
    fig, ax = page_setup()
    report_header(
        ax,
        "Hypotheses",
        "Problem statements linked to zones, with status and root-cause notes.",
        section="Field Entities",
    )
    footer(ax, "Hypotheses from the diagnose project", page_num)
    zone_by_id = {str(z.get("id")): z for z in zones}
    zone_label = {zid: (z.get("text") or "Zone") for zid, z in zone_by_id.items()}
    headers = ["#", "Hypothesis", "Status", "Root cause", "Zones", "Notes"]
    col_w = [0.04, 0.28, 0.11, 0.23, 0.18, 0.06]
    x0, y = 0.045, 0.84
    x = x0
    for j, h in enumerate(headers):
        ax.add_patch(plt.Rectangle((x, y - 0.045), col_w[j], 0.045, facecolor=theme("green_dark"), edgecolor=theme("line")))
        ax.text(x + 0.005, y - 0.014, h, fontsize=7, color="white", fontweight="bold", va="top")
        x += col_w[j]
    y -= 0.045
    rows = hypotheses or []
    if not rows:
        rows = [{"hypothesis": "No hypotheses recorded yet", "status": "—", "root_cause": "", "observation_zone_ids": [], "field_note_count": 0}]
    for ri, h in enumerate(rows[:11]):
        zids = h.get("observation_zone_ids") or []
        znames = ", ".join(zone_label.get(str(zid), "Zone") for zid in zids[:4]) or "—"
        status = str(h.get("status") or "untested").lower()
        status_color = _HYP_STATUS_COLORS.get(status, theme("muted"))
        vals = [
            str(ri + 1),
            h.get("hypothesis") or "",
            status.title(),
            h.get("root_cause") or "—",
            znames,
            str(h.get("field_note_count") or 0),
        ]
        x = x0
        face = "#ffffff" if ri % 2 == 0 else theme("panel_alt")
        rh = 0.058
        zone_swatch = None
        if zids:
            z0 = zone_by_id.get(str(zids[0]))
            if z0:
                zone_swatch = _zone_hex(z0, ri)
        for j, cell in enumerate(vals):
            if j == 0 and zone_swatch:
                cell_face, text_color = zone_swatch, "#ffffff"
            elif j == 2 and status in _HYP_STATUS_COLORS:
                cell_face, text_color = status_color, "#ffffff"
            else:
                cell_face, text_color = face, theme("ink")
            ax.add_patch(plt.Rectangle((x, y - rh), col_w[j], rh, facecolor=cell_face, edgecolor=theme("line"), linewidth=0.5))
            wrap = [6, 36, 14, 28, 22, 6][j]
            ax.text(
                x + 0.004,
                y - 0.01,
                "\n".join(textwrap.wrap(str(cell), wrap)[:3]),
                fontsize=6.0,
                color=text_color,
                va="top",
                fontweight="bold" if j == 2 else "normal",
            )
            x += col_w[j]
        y -= rh
        if y < 0.10:
            break

    # Status legend
    lx = 0.045
    ax.text(lx, 0.08, "Status key:", fontsize=6.5, color=theme("muted"), va="center")
    lx += 0.08
    for label, hex_color in (("Validated", "#186d13"), ("Untested", "#1b75e0"), ("Inconclusive", "#b45309"), ("Rejected", "#b91c1c")):
        ax.add_patch(plt.Rectangle((lx, 0.065), 0.018, 0.028, facecolor=hex_color, edgecolor="none"))
        ax.text(lx + 0.022, 0.08, label, fontsize=6.2, color=theme("ink"), va="center")
        lx += 0.12

    pdf.savefig(fig)
    plt.close(fig)


def _draw_stats_panel(ax_bg, stats: dict, *, x: float = 0.755, note: str | None = None):
    if not stats and not note:
        return
    # Overlay legend sits near y=0.84; keep stats clearly below it.
    y = 0.68
    if stats:
        ax_bg.text(x, y, "Watershed stats", fontsize=8.5, color=theme("ink"), fontweight="bold", ha="left", va="top")
        y -= 0.030
        for k, v in list(stats.items())[:10]:
            line = f"{k}: {v}"
            for wrapped_line in textwrap.wrap(line, width=26)[:2]:
                ax_bg.text(x, y, wrapped_line, fontsize=6.4, color=theme("muted"), ha="left", va="top")
                y -= 0.018
            y -= 0.004
            if y < 0.18:
                break
    if note:
        y = min(y - 0.01, 0.28) if stats else 0.68
        for wrapped_line in textwrap.wrap(note, width=28)[:4]:
            ax_bg.text(x, y, wrapped_line, fontsize=6.2, color=theme("brown"), ha="left", va="top")
            y -= 0.016


def _interpretation_banner(ax_bg, cfg):
    if not cfg:
        return
    note = (getattr(cfg, "interpretation", None) or getattr(cfg, "meaning", None) or "")[:220]
    if not note:
        return
    rounded_panel(ax_bg, 0.18, 0.058, 0.64, 0.055, face="panel", edge="blue", radius=0.008)
    wrapped(ax_bg, note, 0.20, 0.100, width=95, fontsize=6.4, color="ink", line_step=0.014)


def _save_layer_map(pdf, entry: dict, watershed_geom: dict, page_num: int, results: dict | None = None):
    cfg = entry.get("cfg")
    name = entry.get("name") or (cfg.name if cfg else "Layer")
    if cfg and cfg.id == "cropping_intensity":
        title = "Cropping Intensity & Canal Network"
        subtitle = "Analytical water-security evidence layer; verify proxy signals in the field."
    else:
        title = name
        subtitle = (cfg.meaning or "")[:160] if cfg else "Analytical water-security evidence layer; verify proxy signals in the field."
    category = entry.get("category") or (cfg.category if cfg else "Analysis")
    status = entry.get("status")
    fig, ax_bg, ax_map = setup_map_page(
        title,
        subtitle,
        section=category or "Problem Diagnosis",
        footer_label=f"{name} diagnosis layer map",
    )
    footer(ax_bg, f"{name} diagnosis layer map", page_num)

    gdf = entry.get("gdf")
    raster = entry.get("raster")
    has_gdf = gdf is not None and not getattr(gdf, "empty", True)
    has_raster = raster is not None

    if status in {"failed", "empty"} and not has_gdf and not has_raster:
        ax_map.text(
            0.5,
            0.55,
            "Why this map is not drawn",
            ha="center",
            va="center",
            transform=ax_map.transAxes,
            fontsize=12,
            fontweight="bold",
            color=theme("ink"),
        )
        ax_map.text(
            0.5,
            0.42,
            entry.get("error") or "No overlap / source unavailable for this AOI.",
            ha="center",
            va="center",
            transform=ax_map.transAxes,
            fontsize=8,
            color=theme("muted"),
            wrap=True,
        )
        ax_map.set_axis_off()
    elif entry.get("type") == "vector":
        _plot_vector_layer(ax_map, entry, watershed_geom)
        _add_scale_bar(ax_map, watershed_geom)
    else:
        _plot_raster_layer(ax_map, fig, entry, watershed_geom, results=results)

    canal_note = getattr(fig, "_atlas_canal_note", None)
    _draw_stats_panel(ax_bg, entry.get("stats") or {}, note=canal_note)
    _interpretation_banner(ax_bg, cfg)
    pdf.savefig(fig)
    plt.close(fig)


def _comparison_meta(a_id: str, b_id: str, scale: str) -> tuple[str, str, str]:
    pair = (a_id, b_id)
    if pair == ("gw_stress_wiser", "irrigation_access_wiser"):
        return (
            f"{scale} WISER Groundwater Stress & Irrigation Access",
            "Village-level WISER outcome comparison; use patterns as field-verification prompts.",
            "WISER groundwater pressure and irrigation-access proxy shown together; standalone WISER stress and irrigation pages are omitted.",
        )
    if pair == ("kharif_resilience_wiser", "rabi_resilience_wiser"):
        return (
            f"{scale} Kharif & Rabi Crop Resilience (WISER)",
            "Village-level WISER outcome comparison; use patterns as field-verification prompts.",
            "Kharif and rabi dry-year resilience shown together for seasonal comparison; standalone crop-resilience pages are omitted.",
        )
    if pair == ("dem", "lulc250k"):
        return (
            f"{scale} DEM & Land Use / Land Cover",
            "Paired elevation and land-cover controls.",
            "Elevation and land-cover controls shown together; standalone DEM and LULC pages are omitted.",
        )
    if pair == ("baseline_population", "marginalized_scst"):
        return (
            f"{scale} Social & Demographic Profile",
            "Paired population and inclusion context.",
            "Population and marginalized-community context shown together; standalone demographic pages are omitted.",
        )
    return (f"{scale} Layer Comparison", "Paired comparison spread.", "Paired comparison")


def _save_comparison(pdf, left: dict | None, right: dict | None, watershed_geom: dict, page_num: int, results: dict | None = None, scale: str = "Watershed", pair_ids: tuple[str, str] = ("", "")):
    title, subtitle, foot = _comparison_meta(pair_ids[0], pair_ids[1], scale)
    left_name = (left or {}).get("name") or "Layer A"
    right_name = (right or {}).get("name") or "Layer B"
    section = "WISER Outcome Layers" if "wiser" in pair_ids[0] or "wiser" in pair_ids[1] else (
        "Social & Demographic Profile" if "population" in pair_ids[0] or "marginalized" in pair_ids[0] else "Hydrology & Landscape Controls"
    )
    fig, ax_bg = page_setup()
    report_header(ax_bg, title, subtitle, section=section)
    footer(ax_bg, foot, page_num)
    # Leave gutters for colorbars between/after panels and legend strips below maps.
    ax_l = fig.add_axes([0.04, 0.22, 0.38, 0.60])
    ax_r = fig.add_axes([0.54, 0.22, 0.38, 0.60])
    ax_l.set_title(left_name, fontsize=9, color=theme("ink"))
    ax_r.set_title(right_name, fontsize=9, color=theme("ink"))
    for ax, entry, layout in ((ax_l, left, "pair_left"), (ax_r, right, "pair_right")):
        if not entry:
            ax.text(0.5, 0.5, "Unavailable", ha="center", va="center", transform=ax.transAxes)
            ax.set_axis_off()
            continue
        if entry.get("type") == "vector":
            _plot_vector_layer(ax, entry, watershed_geom, fig=fig, layout=layout)
            _add_scale_bar(ax, watershed_geom)
        else:
            _plot_raster_layer(ax, fig, entry, watershed_geom, results=results, layout=layout)
    pdf.savefig(fig)
    plt.close(fig)


def _save_summary(pdf, project: dict, results: dict, page_num: int):
    fig, ax = page_setup()
    scale = project.get("watershed_name") or project.get("name") or "Watershed"
    report_header(ax, f"Diagnosis Summary — {scale}", "Evidence, interpretation, uncertainty, and field checks.", section="Summary")
    footer(ax, "Problem Diagnosis summary", page_num)

    def join_parts(*parts: str, fallback: str) -> str:
        clean = [p for p in parts if p]
        return "; ".join(clean) if clean else fallback

    relief = _stat(results, "dem", "Relief (m)", "Elevation min (m)")
    cropping = _stat(results, "cropping_intensity", "Mean", "Mean Intensity")
    irrig = _stat(results, "irrigation_access_wiser", "Dominant class")
    gw = _stat(results, "gw_stress_wiser", "Dominant class")
    pop = _stat(results, "baseline_population", "Population in AOI", "Total population")
    villages = _stat(results, "baseline_population", "Intersecting Villages", "Count")

    rows = [
        [
            "Terrain / runoff",
            join_parts(f"Relief {relief}" if relief else "", fallback="Use DEM and field walk to confirm slope and drainage."),
            "Elevation difference and drainage concentration help locate fast-runoff slopes and accumulation zones.",
            "DEM shows physical signals, not guaranteed seasonal flow.",
            "Verify flow paths, nala condition, erosion marks, and seasonal retention.",
        ],
        [
            "Farm water demand & resilience",
            join_parts(
                f"Cropping intensity {cropping}" if cropping else "",
                f"Irrigation access {irrig}" if irrig else "",
                fallback="Use crop and irrigation interviews to establish demand.",
            ),
            "Cropping intensity plus WISER access/resilience separates apparent access from dry-year vulnerability.",
            "Classes are proxies; they do not prove reliable or equal supply.",
            "Ask source of second crop, dry-year loss, and pumping change.",
        ],
        [
            "Groundwater setting",
            join_parts(f"WISER stress {gw}" if gw else "", fallback="Use well transects for reliability and recharge response."),
            "WISER stress and aquifer setting point to likely reliability differences.",
            "Regional classes may be outdated or too coarse for local wells.",
            "Check well depth, seasonal failure, yields, and recharge response.",
        ],
        [
            "People / inclusion",
            join_parts(
                f"Villages {villages}" if villages else "",
                f"Population {pop}" if pop else "",
                fallback="Use settlement checks to choose who must be heard.",
            ),
            "Use settlement signals to choose hamlets and excluded groups for validation.",
            "These are population-in-AOI figures, not impact estimates.",
            "Confirm weaker access, time burden, and exclusion from decisions.",
        ],
    ]
    headers = ["Key signal", "Evidence", "What it may mean", "Uncertainty", "Field check"]
    col_w = [0.12, 0.20, 0.22, 0.18, 0.18]
    x0, y = 0.045, 0.82
    x = x0
    for j, h in enumerate(headers):
        ax.add_patch(plt.Rectangle((x, y - 0.045), col_w[j], 0.045, facecolor=theme("green_dark"), edgecolor=theme("line")))
        ax.text(x + 0.005, y - 0.014, h, fontsize=6.8, color="white", fontweight="bold", va="top")
        x += col_w[j]
    y -= 0.045
    for ri, row in enumerate(rows):
        x = x0
        face = "#ffffff" if ri % 2 == 0 else theme("panel_alt")
        rh = 0.12
        for j, cell in enumerate(row):
            ax.add_patch(plt.Rectangle((x, y - rh), col_w[j], rh, facecolor=face, edgecolor=theme("line"), linewidth=0.5))
            ax.text(x + 0.005, y - 0.012, "\n".join(textwrap.wrap(str(cell), 28)[:6]), fontsize=5.8, color=theme("ink"), va="top")
            x += col_w[j]
        y -= rh
    rounded_panel(ax, 0.055, 0.10, 0.89, 0.07, face="panel_alt")
    wrapped(
        ax,
        "Use this as a hypothesis board: map evidence suggests where to look, while field validation decides what is true, uncertain, or locally important.",
        0.075,
        0.145,
        width=130,
        fontsize=8.0,
        line_step=0.018,
    )
    pdf.savefig(fig)
    plt.close(fig)


def _save_handoff(pdf, project: dict, page_num: int):
    fig, ax = page_setup()
    scale = project.get("watershed_name") or project.get("name") or "Watershed"
    report_header(
        ax,
        f"Field Verification Handoff — {scale}",
        "Fast field checklist. The full EPA/ePRA pack follows in the appendix.",
        section="Field Verification",
    )
    footer(ax, "Field verification handoff", page_num)
    headers, *rows = FIELD_HANDOFF_ROWS
    col_w = [0.22, 0.33, 0.35]
    x0, y = 0.045, 0.84
    x = x0
    for j, h in enumerate(headers):
        ax.add_patch(plt.Rectangle((x, y - 0.045), col_w[j], 0.045, facecolor=theme("green_dark"), edgecolor=theme("line")))
        ax.text(x + 0.006, y - 0.014, h, fontsize=7.5, color="white", fontweight="bold", va="top")
        x += col_w[j]
    y -= 0.045
    for ri, row in enumerate(rows):
        x = x0
        face = "#ffffff" if ri % 2 == 0 else theme("panel_alt")
        rh = 0.095
        for j, cell in enumerate(row):
            ax.add_patch(plt.Rectangle((x, y - rh), col_w[j], rh, facecolor=face, edgecolor=theme("line"), linewidth=0.5))
            ax.text(x + 0.006, y - 0.012, "\n".join(textwrap.wrap(str(cell), 42)[:5]), fontsize=6.2, color=theme("ink"), va="top")
            x += col_w[j]
        y -= rh
    pdf.savefig(fig)
    plt.close(fig)


def build_atlas_pdf(
    *,
    project: dict,
    observation_zones: list[dict],
    hypotheses: list[dict],
    output_path: str | Path,
    progress: PackageProgress | None = None,
) -> Path:
    """Clip layers and render the reference-notebook atlas page sequence."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    geom = project.get("watershed_geometry")
    if not geom:
        raise ValueError("Project has no watershed geometry")

    scale = project.get("watershed_name") or project.get("name") or "Watershed"

    if progress:
        progress.emit(5, "Starting atlas export…")

    results = process_layers(geom, progress=progress)
    if progress:
        progress.emit(55, "Loading climate trend…")
    climate = load_climate_trend(
        geom,
        seed_lat=project.get("seed_lat"),
        seed_lng=project.get("seed_lng"),
    )
    results["climate_trend"] = climate

    if progress:
        progress.emit(62, "Writing PDF pages…")

    page = 0
    with PdfPages(out) as pdf:
        page += 1
        if progress:
            progress.emit(64, "Cover page…")
        _save_cover(pdf, project, results, observation_zones, hypotheses, page)

        page += 1
        if progress:
            progress.emit(66, "Map section guide…")
        _save_guide(pdf, project, page)

        page += 1
        if progress:
            progress.emit(68, "Location context…")
        _save_location_context(pdf, project, page)

        page += 1
        if progress:
            progress.emit(70, "Access & satellite context…")
        _save_access_satellite_context(pdf, project, page)

        page += 1
        if progress:
            progress.emit(72, "Basin Level 12 hierarchy…")
        _save_level12_hierarchy(pdf, project, page)

        # Standalone analytical pages present in the reference (CI+canals, aquifers)
        for lid in STANDALONE_ATLAS_LAYERS:
            if lid not in results:
                continue
            page += 1
            if progress:
                progress.emit(74, f"Map: {results[lid].get('name')}…")
            _save_layer_map(pdf, results[lid], geom, page, results=results)

        page += 1
        if progress:
            progress.emit(78, "Climate Trend…")
        _save_climate_trend(pdf, climate, page)

        # Paired spreads only — no duplicate standalones for these layers
        for a, b in COMPARISON_PAIRS:
            if a not in results and b not in results:
                continue
            page += 1
            if progress:
                progress.emit(82, f"Comparison: {a} / {b}…")
            _save_comparison(
                pdf,
                results.get(a),
                results.get(b),
                geom,
                page,
                results=results,
                scale=scale,
                pair_ids=(a, b),
            )

        page += 1
        if progress:
            progress.emit(90, "Diagnosis summary…")
        _save_summary(pdf, project, results, page)

        page += 1
        if progress:
            progress.emit(91, "Observation zones…")
        _save_zones_page(pdf, project, observation_zones, hypotheses, page)

        page += 1
        if progress:
            progress.emit(92, "Hypotheses…")
        _save_hypotheses_page(pdf, observation_zones, hypotheses, page)

        page += 1
        if progress:
            progress.emit(93, "Field verification handoff…")
        _save_handoff(pdf, project, page)

        if progress:
            progress.emit(95, "EPA/ePRA appendix…")
        page = append_epra_pack(pdf, scale, page)

    if progress:
        progress.emit(100, "PDF ready")
    return out
