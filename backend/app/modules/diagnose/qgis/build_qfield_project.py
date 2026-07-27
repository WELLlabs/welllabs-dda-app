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
    QgsMapLayer,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsReferencedRectangle,
    QgsRendererCategory,
    QgsRuleBasedRenderer,
    QgsVectorLayer,
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


def build_project(
    package_dir: Path,
    project_name: str,
    project_id: str,
    *,
    raster_filename: str | None,
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
    if raster_filename:
        raster_path = package_dir / raster_filename
        raster = QgsRasterLayer(str(raster_path), Path(raster_filename).stem)
        if not raster.isValid():
            raise RuntimeError(f"Invalid raster layer: {raster_path} ({raster.error().message()})")
        _set_no_action(raster)
        _set_layer_capabilities(raster, read_only=True)
        layers.append(raster)

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
    parser.add_argument("--raster", default="")
    parser.add_argument("--zone-colors", default="[]")
    parser.add_argument("--extent", default="")
    args = parser.parse_args()

    zone_colors = json.loads(args.zone_colors)
    extent = json.loads(args.extent) if args.extent else None

    QgsApplication.setPrefixPath("/usr", True)
    qgs = QgsApplication([], False)
    qgs.initQgis()

    try:
        output = build_project(
            args.package_dir,
            args.project_name,
            args.project_id,
            raster_filename=args.raster or None,
            zone_colors=zone_colors,
            extent=extent,
        )
        print(output)
        return 0
    finally:
        qgs.exitQgis()


if __name__ == "__main__":
    sys.exit(main())
