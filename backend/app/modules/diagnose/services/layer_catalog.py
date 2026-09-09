"""Per-layer render and analysis catalog loaded from layers.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CATALOG_PATH = Path(__file__).resolve().parent.parent / "config" / "layers.yaml"
_NODATA_TRANSPARENT = "#00000000"


@dataclass(frozen=True)
class LegendEntry:
    """Legend swatch. value may be int (raster class) or str (vector class key)."""

    label: str
    color: str
    value: int | str | None = None


@dataclass(frozen=True)
class ChoroplethStop:
    min: float
    max: float
    label: str
    color: str


@dataclass(frozen=True)
class LayerCompanion:
    """Vector layer drawn automatically when a primary layer is selected (PDF report pairing)."""

    id: str
    line_color: str | None = None
    line_width: float | None = None


@dataclass(frozen=True)
class LayerAnalysis:
    id: str
    type: str
    unit: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LayerConfig:
    id: str
    s3_key: str
    name: str
    source: str  # cog | vector_fgb
    render_type: str  # categorical | continuous | choropleth | outline | line
    nodata: int | float | None
    classes: tuple[LegendEntry, ...]
    analysis: tuple[LayerAnalysis, ...]
    continuous: dict[str, Any] = field(default_factory=dict)
    style_column: str | None = None
    label_column: str | None = None  # outline / label layers (e.g. village name)
    choropleth_stops: tuple[ChoroplethStop, ...] = ()
    line_color: str | None = None
    line_width: float = 1.5
    fill_opacity: float = 0.65
    geometry_kind: str = "polygon"  # polygon | line
    interpretation: str = ""
    meaning: str = ""
    uncertainty: str = ""
    field_check: str = ""
    analysis_type: str | None = None
    map_render: bool = True  # False → analysis-only, FGB not streamed to browser
    overlay: bool = False  # True → sidebar overlay toggles (villages, canals, streams)
    category: str | None = None  # Sidebar group (Clinton report categories)
    tile_strategy: str = "tiles"  # tiles | watershed_image (non-COG national rasters)
    analysis_batch: bool = True  # False → skip slow layers in batch preload
    # clip = cut geometries to watershed; intersect = keep full features that touch AOI
    clip_mode: str = "clip"
    line_dasharray: tuple[float, ...] | None = None
    companions: tuple[LayerCompanion, ...] = ()

    def titiler_colormap(self) -> dict[str, str]:
        """String-keyed colormap for Titiler / rio-tiler (nodata → transparent)."""
        cmap: dict[str, str] = {}
        for entry in self.classes:
            if entry.value is None:
                continue
            key = str(entry.value)
            if self.nodata is not None and entry.value == self.nodata:
                cmap[key] = _NODATA_TRANSPARENT
            else:
                cmap[key] = entry.color
        if self.nodata is not None and str(self.nodata) not in cmap:
            cmap[str(self.nodata)] = _NODATA_TRANSPARENT
        return cmap

    def rio_colormap(self) -> dict[int, tuple[int, int, int, int]]:
        out: dict[int, tuple[int, int, int, int]] = {}
        for k, v in self.titiler_colormap().items():
            try:
                out[int(k)] = _hex_to_rgba(v)
            except ValueError:
                continue
        return out

    def legend_entries(self) -> list[LegendEntry]:
        """UI legend: skip nodata / fully transparent classes; use choropleth stops when present."""
        if self.render_type == "choropleth" and self.choropleth_stops:
            return [
                LegendEntry(label=s.label, color=s.color, value=s.label)
                for s in self.choropleth_stops
            ]
        if self.render_type == "continuous":
            return []
        if self.render_type == "line" and not self.classes:
            if self.line_color:
                return [LegendEntry(label=self.name, color=self.line_color, value=self.name)]
            return []
        out: list[LegendEntry] = []
        for entry in self.classes:
            if self.nodata is not None and entry.value == self.nodata:
                continue
            if entry.color.lower().endswith("00") and len(entry.color.lstrip("#")) == 8:
                continue
            out.append(entry)
        return out

    def write_gdaldem_color_file(self, path: Path) -> None:
        lines: list[str] = []
        cmap = self.titiler_colormap()
        values = sorted(int(k) for k in cmap if k.lstrip("-").isdigit())
        for value in values:
            r, g, b, a = _hex_to_rgba(cmap[str(value)])
            lines.append(f"{value} {r} {g} {b} {a}")
        path.write_text("\n".join(lines) + "\n")


@dataclass(frozen=True)
class LayerCatalog:
    colors: dict[str, str]
    layers: tuple[LayerConfig, ...]

    def by_s3_key(self, s3_key: str) -> LayerConfig | None:
        for layer in self.layers:
            if layer.s3_key == s3_key:
                return layer
        return None

    def by_id(self, layer_id: str) -> LayerConfig | None:
        for layer in self.layers:
            if layer.id == layer_id:
                return layer
        return None

    def cog_layers(self) -> tuple[LayerConfig, ...]:
        return tuple(l for l in self.layers if l.source == "cog")

    def vector_layers(self) -> tuple[LayerConfig, ...]:
        return tuple(l for l in self.layers if l.source in ("vector_fgb", "watershed_hierarchy"))


def _hex_to_rgba(hex_color: str) -> tuple[int, int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 8:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255


def _resolve_color(raw: str, palette: dict[str, str]) -> str:
    if raw.startswith("#"):
        return raw
    if raw in palette:
        return palette[raw]
    raise ValueError(f"Unknown color '{raw}' (not a hex and not in catalog colors)")


def _parse_classes(raw_classes: list[dict[str, Any]], palette: dict[str, str]) -> list[LegendEntry]:
    classes: list[LegendEntry] = []
    for item in raw_classes or []:
        raw_value = item.get("value")
        if raw_value is None:
            value: int | str | None = None
        elif isinstance(raw_value, bool):
            value = str(raw_value)
        elif isinstance(raw_value, (int, float)):
            value = int(raw_value)
        else:
            value = str(raw_value)
        classes.append(
            LegendEntry(
                value=value,
                label=str(item["label"]),
                color=_resolve_color(str(item["color"]), palette),
            )
        )
    return classes


def _parse_stops(raw_stops: list[dict[str, Any]], palette: dict[str, str]) -> list[ChoroplethStop]:
    stops: list[ChoroplethStop] = []
    for item in raw_stops or []:
        stops.append(
            ChoroplethStop(
                min=float(item["min"]),
                max=float(item["max"]),
                label=str(item["label"]),
                color=_resolve_color(str(item["color"]), palette),
            )
        )
    return stops


def _parse_layer(raw: dict[str, Any], palette: dict[str, str]) -> LayerConfig:
    render = raw.get("render") or {}
    render_type = str(render.get("type") or "categorical")
    nodata = render.get("nodata")
    if nodata is not None:
        nodata = float(nodata) if isinstance(nodata, float) else int(nodata)

    classes = _parse_classes(render.get("classes") or [], palette)
    choropleth_stops = tuple(_parse_stops(render.get("stops") or [], palette))

    continuous: dict[str, Any] = {}
    if render_type == "continuous":
        continuous = {
            k: render[k]
            for k in ("min", "max", "ramp", "colormap")
            if k in render
        }

    analysis: list[LayerAnalysis] = []
    for item in raw.get("analysis") or []:
        extra = {k: v for k, v in item.items() if k not in ("id", "type", "unit")}
        analysis.append(
            LayerAnalysis(
                id=str(item["id"]),
                type=str(item["type"]),
                unit=item.get("unit"),
                extra=extra,
            )
        )

    source = str(raw.get("source") or "")
    if not source:
        s3_key = str(raw.get("s3_key") or "")
        if s3_key.endswith((".fgb", ".gpkg")):
            source = "vector_fgb"
        else:
            source = "cog"
    style_column = render.get("column")
    if style_column is not None:
        style_column = str(style_column)
    label_column = render.get("label_column")
    if label_column is not None:
        label_column = str(label_column)

    line_color_raw = render.get("line_color")
    line_color = _resolve_color(str(line_color_raw), palette) if line_color_raw else None
    line_width = float(render.get("line_width") or 1.5)
    fill_opacity = float(render.get("fill_opacity") or render.get("opacity") or 0.65)
    geometry_kind = str(render.get("geometry") or ("line" if render_type == "line" else "polygon"))

    map_render_raw = raw.get("map_render")
    # strip any inline YAML comment before evaluating
    if isinstance(map_render_raw, str):
        map_render_raw = map_render_raw.split("#")[0].strip().lower()
        map_render = map_render_raw not in ("false", "0", "no")
    elif map_render_raw is None:
        map_render = True
    else:
        map_render = bool(map_render_raw)

    overlay_raw = raw.get("overlay")
    if isinstance(overlay_raw, str):
        overlay_raw = overlay_raw.split("#")[0].strip().lower()
        overlay = overlay_raw in ("true", "1", "yes")
    elif overlay_raw is None:
        overlay = render_type == "outline"
    else:
        overlay = bool(overlay_raw)

    tile_strategy = str(raw.get("tile_strategy") or render.get("tile_strategy") or "tiles")
    analysis_batch_raw = raw.get("analysis_batch")
    if isinstance(analysis_batch_raw, str):
        analysis_batch_raw = analysis_batch_raw.split("#")[0].strip().lower()
        analysis_batch = analysis_batch_raw not in ("false", "0", "no")
    elif analysis_batch_raw is None:
        analysis_batch = True
    else:
        analysis_batch = bool(analysis_batch_raw)

    clip_mode = str(raw.get("clip_mode") or render.get("clip_mode") or "clip").strip().lower()
    if clip_mode not in ("clip", "intersect"):
        clip_mode = "clip"

    dash_raw = render.get("line_dasharray")
    line_dasharray: tuple[float, ...] | None = None
    if isinstance(dash_raw, (list, tuple)) and dash_raw:
        try:
            line_dasharray = tuple(float(v) for v in dash_raw)
        except (TypeError, ValueError):
            line_dasharray = None

    companions: list[LayerCompanion] = []
    for item in raw.get("companions") or []:
        comp_color_raw = item.get("line_color")
        companions.append(
            LayerCompanion(
                id=str(item["id"]),
                line_color=_resolve_color(str(comp_color_raw), palette) if comp_color_raw else None,
                line_width=float(item["line_width"]) if item.get("line_width") is not None else None,
            )
        )

    return LayerConfig(
        id=str(raw["id"]),
        s3_key=str(raw.get("s3_key") or ""),
        name=str(raw.get("name") or raw["id"]),
        source=source,
        render_type=render_type,
        nodata=nodata,
        classes=tuple(classes),
        analysis=tuple(analysis),
        continuous=continuous,
        style_column=style_column,
        label_column=label_column,
        choropleth_stops=choropleth_stops,
        line_color=line_color,
        line_width=line_width,
        fill_opacity=fill_opacity,
        geometry_kind=geometry_kind,
        interpretation=str(raw.get("interpretation") or raw.get("meaning") or "").strip(),
        meaning=str(raw.get("meaning") or raw.get("interpretation") or "").strip(),
        uncertainty=str(raw.get("uncertainty") or "").strip(),
        field_check=str(raw.get("field_check") or "").strip(),
        analysis_type=(str(raw["analysis_type"]) if raw.get("analysis_type") else None),
        map_render=map_render,
        overlay=overlay,
        category=(str(raw["category"]).strip() if raw.get("category") else None),
        tile_strategy=tile_strategy,
        analysis_batch=analysis_batch,
        clip_mode=clip_mode,
        line_dasharray=line_dasharray,
        companions=tuple(companions),
    )


def load_catalog(path: Path | None = None) -> LayerCatalog:
    catalog_path = path or _CATALOG_PATH
    data = yaml.safe_load(catalog_path.read_text()) or {}
    palette = {str(k): str(v) for k, v in (data.get("colors") or {}).items()}
    layers = tuple(_parse_layer(item, palette) for item in (data.get("layers") or []))
    return LayerCatalog(colors=palette, layers=layers)


@lru_cache(maxsize=1)
def get_catalog() -> LayerCatalog:
    return load_catalog()


def reload_catalog() -> LayerCatalog:
    """Clear cache and reload (useful after editing layers.yaml)."""
    get_catalog.cache_clear()
    return get_catalog()


def get_layer_for_key(s3_key: str) -> LayerConfig | None:
    return get_catalog().by_s3_key(s3_key)


def get_layer_by_id(layer_id: str) -> LayerConfig | None:
    return get_catalog().by_id(layer_id)


def display_name_for_key(s3_key: str) -> str:
    layer = get_layer_for_key(s3_key)
    if layer:
        return layer.name
    return s3_key.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def get_vector_catalog() -> tuple[LayerConfig, ...]:
    return get_catalog().vector_layers()


def catalog_vector_s3_keys() -> list[str]:
    """Unique vector s3_keys from layers.yaml (excludes watershed_hierarchy)."""
    keys: list[str] = []
    seen: set[str] = set()
    for layer in get_catalog().vector_layers():
        if layer.source != "vector_fgb" or not layer.s3_key:
            continue
        if layer.s3_key in seen:
            continue
        seen.add(layer.s3_key)
        keys.append(layer.s3_key)
    return keys


def catalog_cog_s3_keys() -> list[str]:
    """Unique COG s3_keys from layers.yaml."""
    keys: list[str] = []
    seen: set[str] = set()
    for layer in get_catalog().cog_layers():
        if not layer.s3_key or layer.s3_key in seen:
            continue
        seen.add(layer.s3_key)
        keys.append(layer.s3_key)
    return keys


def _parse_layer_key_csv(raw: str) -> list[str]:
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def resolve_enabled_vector_keys(raw: str | None = None) -> list[str]:
    """VECTOR_LAYERS allowlist, or every layers.yaml vector key when empty/all/*.

    Basin / Sub basin / L7 hierarchy FGBs are not catalog vector entries — they are
    used only by project-picker preview_context (and WATERSHEDS_FGB_KEY for L12 AOI).
    """
    from app.shared.config import settings

    value = settings.vector_layers if raw is None else raw
    text = (value or "").strip()
    if not text or text.lower() in {"*", "all"}:
        return catalog_vector_s3_keys()
    return _parse_layer_key_csv(text)


def resolve_enabled_cog_keys(raw: str | None = None) -> list[str]:
    """COG_LAYERS allowlist, or every layers.yaml COG key when empty/all/*."""
    from app.shared.config import settings

    value = settings.cog_layers if raw is None else raw
    text = (value or "").strip()
    if not text or text.lower() in {"*", "all"}:
        return catalog_cog_s3_keys()
    return _parse_layer_key_csv(text)
