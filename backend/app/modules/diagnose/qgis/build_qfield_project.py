#!/usr/bin/env python3
"""Build a portable QField project with PyQGIS (forms, defaults, raster paths)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsAttributeEditorField,
    QgsCategorizedSymbolRenderer,
    QgsCoordinateReferenceSystem,
    QgsDefaultValue,
    QgsEditFormConfig,
    QgsEditorWidgetSetup,
    QgsFillSymbol,
    QgsGraduatedSymbolRenderer,
    QgsLineSymbol,
    QgsMapLayer,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsReferencedRectangle,
    QgsRendererCategory,
    QgsRendererRange,
    QgsRuleBasedRenderer,
    QgsSingleSymbolRenderer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsWkbTypes,
)


def _normalize_hex(value: str) -> str:
    color = (value or "#3b82f6").strip()
    if not color.startswith("#"):
        color = f"#{color}"
    return color.lower()


def _hex_to_rgba(value: str, alpha: int) -> str:
    normalized = _normalize_hex(value).lstrip("#")
    red = int(normalized[0:2], 16)
    green = int(normalized[2:4], 16)
    blue = int(normalized[4:6], 16)
    return f"{red},{green},{blue},{alpha}"


def _set_layer_capabilities(
    layer,
    *,
    identifiable: bool = True,
    searchable: bool = True,
    removable: bool = True,
    read_only: bool = False,
) -> None:
    flags = QgsMapLayer.LayerFlags()
    if identifiable:
        flags |= QgsMapLayer.Identifiable
    if searchable:
        flags |= QgsMapLayer.Searchable
    if removable:
        flags |= QgsMapLayer.Removable
    layer.setFlags(flags)
    if read_only and isinstance(layer, QgsVectorLayer):
        layer.setReadOnly(True)


def _configure_hidden(layer: QgsVectorLayer, field_name: str) -> None:
    index = layer.fields().indexFromName(field_name)
    if index >= 0:
        layer.setEditorWidgetSetup(index, QgsEditorWidgetSetup("Hidden", {}))


def _configure_text(layer: QgsVectorLayer, field_name: str) -> None:
    index = layer.fields().indexFromName(field_name)
    if index >= 0:
        layer.setEditorWidgetSetup(index, QgsEditorWidgetSetup("TextEdit", {}))


def _configure_external_resource(layer: QgsVectorLayer, field_name: str, viewer: int) -> None:
    index = layer.fields().indexFromName(field_name)
    if index >= 0:
        layer.setEditorWidgetSetup(
            index,
            QgsEditorWidgetSetup(
                "ExternalResource",
                {
                    "DocumentViewer": viewer,
                    "RelativeStorage": True,
                    "StorageMode": 0,
                    "FileWidget": True,
                    "UseLink": True,
                },
            ),
        )


def _configure_value_relation(
    layer: QgsVectorLayer,
    field_name: str,
    related_layer: QgsVectorLayer,
    key: str,
    value: str,
) -> None:
    index = layer.fields().indexFromName(field_name)
    if index < 0:
        return
    layer.setEditorWidgetSetup(
        index,
        QgsEditorWidgetSetup(
            "ValueRelation",
            {
                "AllowMulti": False,
                "AllowNull": True,
                "FilterExpression": "",
                "Key": key,
                "Layer": related_layer.id(),
                "NofColumns": 1,
                "OrderByValue": True,
                "UseCompleter": False,
                "Value": value,
            },
        ),
    )


def _configure_field_notes(
    layer: QgsVectorLayer,
    project_id: str,
    hypotheses_layer: QgsVectorLayer | None = None,
) -> None:
    for field_name, alias in (
        ("title", "Title"),
        ("text", "Notes"),
        ("photo_path", "Photo"),
        ("audio_path", "Audio"),
        ("hypothesis_id", "Hypothesis"),
    ):
        index = layer.fields().indexFromName(field_name)
        if index >= 0:
            layer.setFieldAlias(index, alias)

    visible_fields = ("title", "text", "hypothesis_id", "photo_path", "audio_path")
    for field in layer.fields():
        name = field.name()
        if name in visible_fields:
            continue
        _configure_hidden(layer, name)

    _configure_text(layer, "title")
    _configure_text(layer, "text")
    _configure_external_resource(layer, "photo_path", 1)
    _configure_external_resource(layer, "audio_path", 3)
    if hypotheses_layer is not None and hypotheses_layer.isValid():
        _configure_value_relation(
            layer, "hypothesis_id", hypotheses_layer, "hypothesis_id", "hypothesis"
        )
    else:
        _configure_text(layer, "hypothesis_id")

    project_idx = layer.fields().indexFromName("project_id")
    if project_idx >= 0:
        layer.setDefaultValueDefinition(
            project_idx,
            QgsDefaultValue(f"'{project_id}'", applyOnUpdate=True),
        )
    note_idx = layer.fields().indexFromName("note_id")
    if note_idx >= 0:
        layer.setDefaultValueDefinition(note_idx, QgsDefaultValue("uuid()", applyOnUpdate=False))

    layer.setDisplayExpression('coalesce(nullif("title", \'\'), nullif("text", \'\'), \'Field note\')')

    config = layer.editFormConfig()
    config.setLayout(QgsEditFormConfig.TabLayout)
    config.clearTabs()
    root = config.invisibleRootContainer()
    root.clear()
    for field_name in visible_fields:
        index = layer.fields().indexFromName(field_name)
        if index >= 0:
            root.addChildElement(QgsAttributeEditorField(field_name, index, root))
    layer.setEditFormConfig(config)


def _configure_hypotheses(layer: QgsVectorLayer) -> None:
    for field_name in ("fid", "project_id", "status"):
        _configure_hidden(layer, field_name)
    _configure_text(layer, "hypothesis")
    hyp_idx = layer.fields().indexFromName("hypothesis")
    if hyp_idx >= 0:
        layer.setFieldAlias(hyp_idx, "Hypothesis")
    layer.setDisplayExpression('coalesce("hypothesis", \'Untitled hypothesis\')')

    config = layer.editFormConfig()
    config.setLayout(QgsEditFormConfig.TabLayout)
    config.clearTabs()
    root = config.invisibleRootContainer()
    root.clear()
    index = layer.fields().indexFromName("hypothesis")
    if index >= 0:
        root.addChildElement(QgsAttributeEditorField("hypothesis", index, root))
    layer.setEditFormConfig(config)


def _zone_symbol(color: str) -> QgsFillSymbol:
    return QgsFillSymbol.createSimple(
        {
            "color": _hex_to_rgba(color, 102),
            "outline_color": _hex_to_rgba(color, 255),
            "outline_width": "0.8",
        }
    )


def _zone_colors_from_layer(layer: QgsVectorLayer, fallback: list[str]) -> list[str]:
    idx = layer.fields().indexFromName("color")
    colors: list[str] = []
    if idx >= 0:
        for raw in layer.uniqueValues(idx):
            if raw is None or str(raw).strip() == "":
                continue
            normalized = _normalize_hex(str(raw))
            if normalized not in colors:
                colors.append(normalized)
    for color in fallback:
        normalized = _normalize_hex(color)
        if normalized not in colors:
            colors.append(normalized)
    return colors or ["#3b82f6"]


def _configure_zone_renderer(layer: QgsVectorLayer, colors: list[str]) -> None:
    """Rule-based symbology works reliably on QField and labels each zone by title."""
    root_rule = QgsRuleBasedRenderer.Rule(None)
    for feature in layer.getFeatures():
        zone_id = feature["zone_id"]
        color = _normalize_hex(feature["color"])
        title = (feature["text"] or "Untitled zone").strip()
        rule = QgsRuleBasedRenderer.Rule(
            _zone_symbol(color),
            0,
            0,
            f"\"zone_id\" = '{zone_id}'",
            title,
        )
        root_rule.appendChild(rule)

    if root_rule.children():
        layer.setRenderer(QgsRuleBasedRenderer(root_rule))
        return

    categories = []
    for color in _zone_colors_from_layer(layer, colors):
        categories.append(QgsRendererCategory(color, _zone_symbol(color), color))
    layer.setRenderer(QgsCategorizedSymbolRenderer("color", categories))


def _configure_zones(layer: QgsVectorLayer, project_id: str, colors: list[str]) -> None:
    for field_name, alias in (
        ("text", "Title"),
        ("observations", "Observations"),
        ("questions", "Questions"),
    ):
        index = layer.fields().indexFromName(field_name)
        if index >= 0:
            layer.setFieldAlias(index, alias)

    for field_name in ("fid", "zone_id", "project_id", "color"):
        _configure_hidden(layer, field_name)

    _configure_text(layer, "text")
    if layer.fields().indexFromName("observations") >= 0:
        _configure_text(layer, "observations")
    if layer.fields().indexFromName("questions") >= 0:
        _configure_text(layer, "questions")

    project_idx = layer.fields().indexFromName("project_id")
    if project_idx >= 0:
        layer.setDefaultValueDefinition(
            project_idx,
            QgsDefaultValue(f"'{project_id}'", applyOnUpdate=True),
        )

    layer.setDisplayExpression('coalesce("text", \'Untitled zone\')')
    layer.setMapTipsEnabled(True)
    layer.setMapTipTemplate(
        'coalesce("text", \'Untitled zone\') || '
        'if(length(coalesce("observations", \'\')) > 0, '
        '\'\\nObservations: \' || "observations", \'\') || '
        'if(length(coalesce("questions", \'\')) > 0, '
        '\'\\nQuestions: \' || "questions", \'\')'
    )

    config = layer.editFormConfig()
    config.setLayout(QgsEditFormConfig.TabLayout)
    config.clearTabs()
    root = config.invisibleRootContainer()
    root.clear()
    for field_name in ("text", "observations", "questions"):
        index = layer.fields().indexFromName(field_name)
        if index >= 0:
            root.addChildElement(QgsAttributeEditorField(field_name, index, root))
    layer.setEditFormConfig(config)

    _configure_zone_renderer(layer, colors)


def _set_offline(layer) -> None:
    layer.setCustomProperty("QFieldSync/cloud_action", "offline")


def _set_no_action(layer) -> None:
    """Raster layers must use no_action — 'offline' is vector-only and breaks QField Cloud packaging."""
    layer.setCustomProperty("QFieldSync/cloud_action", "no_action")


FILL_ALPHA = 165  # ~0.65 map opacity
OUTLINE_RGBA = "15,23,42,230"


def _polygon_symbol(color: str, *, fill_alpha: int = FILL_ALPHA) -> QgsFillSymbol:
    return QgsFillSymbol.createSimple(
        {
            "color": _hex_to_rgba(color, fill_alpha),
            "outline_color": OUTLINE_RGBA,
            "outline_width": "0.35",
            "outline_style": "solid",
        }
    )


def _line_symbol(color: str) -> QgsLineSymbol:
    return QgsLineSymbol.createSimple(
        {
            "line_color": _hex_to_rgba(color, 230),
            "line_width": "0.6",
        }
    )


def _point_symbol(color: str) -> QgsMarkerSymbol:
    return QgsMarkerSymbol.createSimple(
        {
            "name": "circle",
            "color": _hex_to_rgba(color, FILL_ALPHA),
            "outline_color": OUTLINE_RGBA,
            "outline_width": "0.3",
            "size": "2.5",
        }
    )


def _symbol_for_layer(layer: QgsVectorLayer, color: str, *, fill_alpha: int = FILL_ALPHA):
    geom = layer.geometryType()
    if geom == QgsWkbTypes.LineGeometry:
        return _line_symbol(color)
    if geom == QgsWkbTypes.PointGeometry:
        return _point_symbol(color)
    return _polygon_symbol(color, fill_alpha=fill_alpha)


def _style_outline(layer: QgsVectorLayer, label_column: str | None = None) -> None:
    """Transparent fill + dark outline for reference boundary layers."""
    symbol = _symbol_for_layer(layer, "#000000", fill_alpha=0)
    if isinstance(symbol, QgsFillSymbol):
        # Ensure fully transparent fill even if hex helper clamps oddly
        symbol = QgsFillSymbol.createSimple(
            {
                "color": "0,0,0,0",
                "outline_color": OUTLINE_RGBA,
                "outline_width": "0.45",
                "outline_style": "solid",
            }
        )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    if label_column and layer.fields().indexFromName(label_column) >= 0:
        _enable_labels(layer, label_column)


def _enable_labels(layer: QgsVectorLayer, field_name: str) -> None:
    settings = QgsPalLayerSettings()
    settings.fieldName = field_name
    settings.isExpression = False
    settings.enabled = True
    text_format = QgsTextFormat()
    text_format.setSize(8)
    buffer = QgsTextBufferSettings()
    buffer.setEnabled(True)
    buffer.setSize(0.8)
    text_format.setBuffer(buffer)
    settings.setFormat(text_format)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def _style_categorical(layer: QgsVectorLayer, style: dict) -> None:
    column = style.get("style_column") or ""
    classes = style.get("classes") or []
    if not column or layer.fields().indexFromName(column) < 0 or not classes:
        _style_outline(layer, style.get("label_column"))
        return

    categories = []
    known: set[str] = set()
    for entry in classes:
        value = entry.get("value")
        label = entry.get("label") or str(value)
        color = entry.get("color") or "#94a3b8"
        categories.append(
            QgsRendererCategory(value, _symbol_for_layer(layer, color), label)
        )
        if value is not None:
            known.add(str(value))

    # Include any attribute values present in the package but missing from the catalog
    idx = layer.fields().indexFromName(column)
    for raw in layer.uniqueValues(idx):
        if raw is None or str(raw).strip() == "":
            continue
        if str(raw) in known:
            continue
        categories.append(
            QgsRendererCategory(raw, _symbol_for_layer(layer, "#e6e9eb"), str(raw))
        )
        known.add(str(raw))

    layer.setRenderer(QgsCategorizedSymbolRenderer(column, categories))


def _style_choropleth(layer: QgsVectorLayer, style: dict) -> None:
    column = style.get("style_column") or ""
    stops = style.get("choropleth_stops") or []
    if not column or layer.fields().indexFromName(column) < 0 or not stops:
        _style_outline(layer, style.get("label_column"))
        return

    ranges = []
    for stop in stops:
        try:
            lower = float(stop.get("min", 0))
            upper = float(stop.get("max", lower))
        except (TypeError, ValueError):
            continue
        label = stop.get("label") or f"{lower} – {upper}"
        color = stop.get("color") or "#94a3b8"
        ranges.append(
            QgsRendererRange(lower, upper, _symbol_for_layer(layer, color), label)
        )
    if not ranges:
        _style_outline(layer, style.get("label_column"))
        return
    layer.setRenderer(QgsGraduatedSymbolRenderer(column, ranges))


def _style_secondary_vector(layer: QgsVectorLayer, style: dict | None) -> None:
    """Apply catalog colors + legend labels so QField matches the web map."""
    style = style or {}
    render_type = (style.get("render_type") or "outline").lower()
    if render_type == "categorical":
        _style_categorical(layer, style)
    elif render_type == "choropleth":
        _style_choropleth(layer, style)
    else:
        _style_outline(layer, style.get("label_column"))


def build_project(
    package_dir: Path,
    project_name: str,
    project_id: str,
    *,
    rasters: list[dict] | None = None,
    secondary_vectors: list[dict] | None = None,
    raster_filename: str | None = None,
    zone_colors: list[str],
    extent: list[float] | None,
) -> Path:
    project = QgsProject.instance()
    project.clear()
    output_path = package_dir / f"{project_name}.qgs"
    project.setFileName(str(output_path))
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    project.writeEntry("Paths", "/Absolute", False)

    layers = []

    # OpenStreetMap base — matches Diagnose web map (needs network on device)
    osm_uri = (
        "type=xyz&url=https://tile.openstreetmap.org/%7Bz%7D/%7Bx%7D/%7By%7D.png"
        "&zmax=19&zmin=0"
    )
    basemap = QgsRasterLayer(osm_uri, "OpenStreetMap", "wms")
    if basemap.isValid():
        _set_no_action(basemap)
        _set_layer_capabilities(basemap, read_only=True)
        layers.append(basemap)
    else:
        # Offline-friendly light canvas if XYZ provider unavailable in builder
        from qgis.PyQt.QtGui import QColor

        project.setBackgroundColor(QColor(245, 245, 240))

    raster_list = list(rasters or [])
    if not raster_list and raster_filename:
        raster_list = [{"filename": raster_filename, "name": Path(raster_filename).stem}]

    for item in raster_list:
        filename = item.get("filename") or ""
        if not filename:
            continue
        label = item.get("name") or Path(filename).stem
        raster_path = package_dir / filename
        raster = QgsRasterLayer(str(raster_path), label)
        if not raster.isValid():
            raise RuntimeError(f"Invalid raster layer: {raster_path} ({raster.error().message()})")
        _set_no_action(raster)
        _set_layer_capabilities(raster, read_only=True)
        layers.append(raster)

    for item in secondary_vectors or []:
        filename = item.get("filename") or ""
        if not filename:
            continue
        label = item.get("name") or Path(filename).stem
        layername = item.get("layername") or Path(filename).stem.replace("secondary_", "")
        vector_path = package_dir / filename
        source = f"{vector_path}|layername={layername}"
        vector = QgsVectorLayer(source, label, "ogr")
        if not vector.isValid():
            # Fallback: open without explicit layername
            vector = QgsVectorLayer(str(vector_path), label, "ogr")
        if not vector.isValid():
            raise RuntimeError(f"Invalid secondary vector layer: {vector_path}")
        _style_secondary_vector(vector, item)
        _set_no_action(vector)
        _set_layer_capabilities(vector, read_only=True)
        layers.append(vector)

    zones_path = package_dir / "observation_zones.gpkg"
    zones = QgsVectorLayer(f"{zones_path}|layername=observation_zones", "Observation zones", "ogr")
    if not zones.isValid():
        raise RuntimeError(f"Invalid observation zones layer: {zones_path}")
    _configure_zones(zones, project_id, zone_colors)
    _set_offline(zones)
    _set_layer_capabilities(zones, read_only=True)
    layers.append(zones)

    hypotheses_path = package_dir / "hypotheses.gpkg"
    hypotheses = QgsVectorLayer(f"{hypotheses_path}|layername=hypotheses", "Hypotheses", "ogr")
    if not hypotheses.isValid():
        raise RuntimeError(f"Invalid hypotheses layer: {hypotheses_path}")
    _configure_hypotheses(hypotheses)
    _set_offline(hypotheses)
    _set_layer_capabilities(hypotheses, read_only=True)
    layers.append(hypotheses)

    notes_path = package_dir / "field_notes.gpkg"
    notes = QgsVectorLayer(f"{notes_path}|layername=field_notes", "Field notes", "ogr")
    if not notes.isValid():
        raise RuntimeError(f"Invalid field notes layer: {notes_path}")
    _set_offline(notes)
    _set_layer_capabilities(notes, read_only=False)
    layers.append(notes)

    for layer in layers:
        project.addMapLayer(layer, True)

    # Configure after both layers are in the project so ValueRelation can use the layer id.
    _configure_field_notes(notes, project_id, hypotheses)

    if extent and len(extent) == 4:
        xmin, ymin, xmax, ymax = extent
        project.viewSettings().setDefaultViewExtent(
            QgsReferencedRectangle(QgsRectangle(xmin, ymin, xmax, ymax), project.crs())
        )

    project.setProperty("QFieldSync/attachmentDirs", "DCIM,audio,video")

    if not project.write():
        raise RuntimeError(f"Failed to write {output_path}")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("project_name")
    parser.add_argument("project_id")
    parser.add_argument("--raster", default="")  # legacy single raster
    parser.add_argument("--rasters", default="[]")
    parser.add_argument("--secondary-vectors", default="[]")
    parser.add_argument("--zone-colors", default="[]")
    parser.add_argument("--extent", default="")
    args = parser.parse_args()

    zone_colors = json.loads(args.zone_colors)
    extent = json.loads(args.extent) if args.extent else None
    rasters = json.loads(args.rasters) if args.rasters else []
    secondary_vectors = json.loads(args.secondary_vectors) if args.secondary_vectors else []
    if not rasters and args.raster:
        rasters = [{"filename": args.raster, "name": Path(args.raster).stem}]

    QgsApplication.setPrefixPath("/usr", True)
    qgs = QgsApplication([], False)
    qgs.initQgis()

    try:
        output = build_project(
            args.package_dir,
            args.project_name,
            args.project_id,
            rasters=rasters,
            secondary_vectors=secondary_vectors,
            zone_colors=zone_colors,
            extent=extent,
        )
        print(output)
        return 0
    finally:
        qgs.exitQgis()


if __name__ == "__main__":
    sys.exit(main())
