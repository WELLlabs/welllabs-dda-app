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
    render_type: str  # categorical | continuous | choropleth
    nodata: int | float | None
    classes: tuple[LegendEntry, ...]
    analysis: tuple[LayerAnalysis, ...]
    continuous: dict[str, Any] = field(default_factory=dict)
    style_column: str | None = None
    choropleth_stops: tuple[ChoroplethStop, ...] = ()
    interpretation: str = ""
    meaning: str = ""
    uncertainty: str = ""
    field_check: str = ""
    analysis_type: str | None = None
    map_render: bool = True  # False → analysis-only, FGB not streamed to browser

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
        return tuple(l for l in self.layers if l.source == "vector_fgb")


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

    source = str(raw.get("source") or ("vector_fgb" if str(raw.get("s3_key", "")).endswith(".fgb") else "cog"))
    style_column = render.get("column")
    if style_column is not None:
        style_column = str(style_column)

    map_render_raw = raw.get("map_render")
    # strip any inline YAML comment before evaluating
    if isinstance(map_render_raw, str):
        map_render_raw = map_render_raw.split("#")[0].strip().lower()
        map_render = map_render_raw not in ("false", "0", "no")
    elif map_render_raw is None:
        map_render = True
    else:
        map_render = bool(map_render_raw)

    return LayerConfig(
        id=str(raw["id"]),
        s3_key=str(raw["s3_key"]),
        name=str(raw.get("name") or raw["id"]),
        source=source,
        render_type=render_type,
        nodata=nodata,
        classes=tuple(classes),
        analysis=tuple(analysis),
        continuous=continuous,
        style_column=style_column,
        choropleth_stops=choropleth_stops,
        interpretation=str(raw.get("interpretation") or raw.get("meaning") or "").strip(),
        meaning=str(raw.get("meaning") or raw.get("interpretation") or "").strip(),
        uncertainty=str(raw.get("uncertainty") or "").strip(),
        field_check=str(raw.get("field_check") or "").strip(),
        analysis_type=(str(raw["analysis_type"]) if raw.get("analysis_type") else None),
        map_render=map_render,
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
