"""Build ODK XForms XML for MEL indicator collection."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from xml.sax.saxutils import escape

_XMLNS = "http://www.w3.org/2002/xforms"
_OPENROSA = "http://openrosa.org/xforms"
_JR = "http://openrosa.org/javarosa"

# Supported ODK Collect input types for MEL fields.
INPUT_TYPES = {
    "decimal": {
        "label": "Decimal number",
        "bind_type": "decimal",
        "control": "input",
        "appearance": "",
        "needs_choices": False,
        "collect_label": "Number (decimal)",
        "description": "Numeric keypad entry in ODK Collect.",
    },
    "integer": {
        "label": "Whole number",
        "bind_type": "int",
        "control": "input",
        "appearance": "",
        "needs_choices": False,
        "collect_label": "Number (integer)",
        "description": "Whole-number entry in ODK Collect.",
    },
    "text": {
        "label": "Text",
        "bind_type": "string",
        "control": "input",
        "appearance": "",
        "needs_choices": False,
        "collect_label": "Text",
        "description": "Single-line text in ODK Collect.",
    },
    "long_text": {
        "label": "Long text",
        "bind_type": "string",
        "control": "input",
        "appearance": "multiline",
        "needs_choices": False,
        "collect_label": "Long text",
        "description": "Multi-line text box in ODK Collect.",
    },
    "select_one": {
        "label": "Single select",
        "bind_type": "string",
        "control": "select1",
        "appearance": "",
        "needs_choices": True,
        "collect_label": "Select one",
        "description": "Choose one option from a list in ODK Collect.",
    },
    "select_multiple": {
        "label": "Multi select",
        "bind_type": "string",
        "control": "select",
        "appearance": "",
        "needs_choices": True,
        "collect_label": "Select multiple",
        "description": "Choose one or more options in ODK Collect.",
    },
    "geopoint": {
        "label": "Coordinates",
        "bind_type": "geopoint",
        "control": "input",
        "appearance": "",
        "needs_choices": False,
        "collect_label": "GPS / coordinates",
        "description": "Capture latitude/longitude in ODK Collect.",
    },
    "date": {
        "label": "Date",
        "bind_type": "date",
        "control": "input",
        "appearance": "",
        "needs_choices": False,
        "collect_label": "Date",
        "description": "Calendar date entry in ODK Collect.",
    },
    "select_one_yes_no": {
        "label": "Yes / No",
        "bind_type": "string",
        "control": "select1",
        "appearance": "",
        "needs_choices": False,
        "collect_label": "Select one (Yes / No)",
        "description": "Yes/No choice list in ODK Collect.",
    },
}

_DEFAULT_INPUT_TYPE = "decimal"
_DEFAULT_YES_NO = ["Yes", "No"]

REQUIRED_META_FIELDS = (
    {
        "id": "__meta_observation_date",
        "field_name": "observation_date",
        "label": "Date",
        "hint": "Date of this observation or survey.",
        "input_type": "date",
        "indicator": "Date",
        "outcome": "",
        "category_label": "Metadata",
        "assumptions": "",
        "custom": False,
        "locked": True,
        "required": True,
        "options": [],
    },
    {
        "id": "__meta_coordinates",
        "field_name": "coordinates",
        "label": "Coordinates",
        "hint": "Capture GPS location at the observation site.",
        "input_type": "geopoint",
        "indicator": "Coordinates",
        "outcome": "",
        "category_label": "Metadata",
        "assumptions": "",
        "custom": False,
        "locked": True,
        "required": True,
        "options": [],
    },
)


def required_meta_fields() -> list[dict]:
    """Date + coordinates collected on every MEL form."""
    return [dict(field) for field in REQUIRED_META_FIELDS]


def ensure_required_meta_fields(fields: list[dict] | None) -> list[dict]:
    """Prepend required date/coordinates fields when missing."""
    existing = list(fields or [])
    names = {
        _slugify(str(item.get("field_name") or item.get("label") or ""))
        for item in existing
    }
    types = {str(item.get("input_type") or "") for item in existing}
    missing: list[dict] = []
    for meta in required_meta_fields():
        name = meta["field_name"]
        input_type = meta["input_type"]
        if name in names or input_type in types:
            continue
        missing.append(meta)
    return missing + existing


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    if not slug:
        slug = "field"
    if slug[0].isdigit():
        slug = f"f_{slug}"
    return slug[:50]


def _xml_form_id(intervention_slug: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return _slugify(f"mel_{intervention_slug}_{stamp}")[:63]


def _choice_value(label: str, index: int) -> str:
    value = _slugify(label) or f"option_{index}"
    return value[:40]


def normalize_options(raw) -> list[dict]:
    """Normalize choice options to ``{value, label}`` pairs."""
    if raw is None:
        return []
    if isinstance(raw, str):
        return [
            {"value": _choice_value(part.strip(), i), "label": part.strip()}
            for i, part in enumerate(re.split(r"[\n,;]+", raw), start=1)
            if part.strip()
        ]
    if not isinstance(raw, list):
        return []

    options: list[dict] = []
    for index, part in enumerate(raw, start=1):
        if isinstance(part, dict):
            label = str(part.get("label") or part.get("value") or "").strip()
            value = str(part.get("value") or "").strip() or _choice_value(label, index)
            if label or value:
                options.append({"value": value[:40] or f"option_{index}", "label": label or value})
            continue
        label = str(part).strip()
        if label:
            options.append({"value": _choice_value(label, index), "label": label})
    return options


def normalize_choices(raw) -> list[str]:
    """Back-compat helper: return display labels only."""
    return [opt["label"] for opt in normalize_options(raw)]


def infer_input_type(indicator_text: str) -> str:
    """Pick a sensible default ODK type from the indicator wording."""
    text = (indicator_text or "").lower()
    if any(token in text for token in ("yes/no", "y/n", "true/false")):
        return "select_one_yes_no"
    if any(token in text for token in ("coordinate", "gps", "lat/long", "latitude", "geopoint", "location")):
        return "geopoint"
    if re.search(r"\b(number of|no\. of|count of|months?|fillings)\b", text):
        return "integer"
    if any(
        token in text
        for token in (
            "change in crop mix",
            "crop mix",
            "livelihoods adopted",
            "position",
            "describe",
            "remarks",
            "comment",
        )
    ):
        return "text"
    if any(
        token in text
        for token in (
            "m3",
            "rs",
            "revenue",
            "profit",
            "yield",
            "volumetric",
            "volume",
            "water",
            "acreage",
            "income",
        )
    ):
        return "decimal"
    return _DEFAULT_INPUT_TYPE


def build_hint(item: dict) -> str:
    hint = f"{item.get('category_label') or ''}: {item.get('outcome') or ''}".strip(": ")
    assumptions = (item.get("assumptions") or "").strip()
    if assumptions:
        hint = f"{hint} | Assumptions: {assumptions[:240]}" if hint else f"Assumptions: {assumptions[:240]}"
    return hint


def enrich_indicators_for_odk(indicators: list[dict]) -> list[dict]:
    """Attach editable ODK field metadata used by preview UI and form publish."""
    enriched: list[dict] = []
    for index, item in enumerate(ensure_required_meta_fields(indicators), start=1):
        input_type = item.get("input_type") or infer_input_type(item.get("indicator") or item.get("label") or "")
        if input_type not in INPUT_TYPES:
            input_type = _DEFAULT_INPUT_TYPE
        meta = INPUT_TYPES[input_type]
        label = (item.get("label") or item.get("indicator") or "").strip()
        hint = item.get("hint")
        if hint is None:
            hint = build_hint(item) if not item.get("custom") else ""
        hint = (hint or "").strip()
        # Locked meta fields keep stable names; all others derive from label.
        if item.get("locked") and item.get("field_name"):
            field_name = _slugify(str(item["field_name"])) or f"ind_{index:03d}"
        else:
            field_name = _slugify(label) or f"ind_{index:03d}"
        options = normalize_options(item.get("options") if item.get("options") is not None else item.get("choices"))
        if input_type == "select_one_yes_no" and not options:
            options = [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]
        if meta["needs_choices"] and not options:
            options = [
                {"value": "option_a", "label": "Option A"},
                {"value": "option_b", "label": "Option B"},
            ]
        enriched.append(
            {
                **item,
                "field_name": field_name,
                "label": label,
                "hint": hint,
                "input_type": input_type,
                "options": options,
                "choices": [opt["label"] for opt in options],
                "custom": bool(item.get("custom")),
                "locked": bool(item.get("locked")),
                "required": bool(item.get("required") or item.get("locked")),
                "input_type_label": meta["label"],
                "odk_bind_type": meta["bind_type"],
                "odk_control": meta["control"],
                "odk_collect_label": meta["collect_label"],
                "odk_description": meta["description"],
                "needs_choices": meta["needs_choices"] or input_type == "select_one_yes_no",
            }
        )
    return enriched


def list_input_types() -> list[dict]:
    return [
        {
            "id": key,
            "label": value["label"],
            "collect_label": value["collect_label"],
            "description": value["description"],
            "needs_choices": value["needs_choices"] or key == "select_one_yes_no",
        }
        for key, value in INPUT_TYPES.items()
    ]


def _control_xml(field_name: str, label: str, hint: str, input_type: str, options: list[dict]) -> list[str]:
    meta = INPUT_TYPES.get(input_type, INPUT_TYPES[_DEFAULT_INPUT_TYPE])
    appearance = meta.get("appearance") or ""
    open_tag = f'      <{meta["control"]} ref="/data/{field_name}"'
    if appearance:
        open_tag += f' appearance="{escape(appearance)}"'
    open_tag += ">"
    lines = [
        open_tag,
        f"        <label>{escape(label)}</label>",
    ]
    if hint:
        lines.append(f"        <hint>{escape(hint)}</hint>")

    if meta["control"] in {"select1", "select"}:
        option_rows = options or (
            [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]
            if input_type == "select_one_yes_no"
            else [
                {"value": "option_a", "label": "Option A"},
                {"value": "option_b", "label": "Option B"},
            ]
        )
        for index, option in enumerate(option_rows, start=1):
            value = str(option.get("value") or _choice_value(str(option.get("label") or ""), index))
            opt_label = str(option.get("label") or value)
            lines.extend(
                [
                    "        <item>",
                    f"          <label>{escape(opt_label)}</label>",
                    f"          <value>{escape(value)}</value>",
                    "        </item>",
                ]
            )

    lines.append(f"      </{meta['control']}>")
    return lines


def build_mel_form_xml(
    *,
    intervention_name: str,
    intervention_slug: str,
    indicators: list[dict],
    form_title: str | None = None,
    xml_form_id: str | None = None,
    version: str | None = None,
) -> tuple[str, str]:
    """Return (xml_form_id, xml_body).

    When ``xml_form_id`` is provided it is kept as-is (needed for ODK draft
    version updates). Otherwise a new timestamped id is generated.
    """
    if not indicators:
        raise ValueError("At least one indicator is required to build a form")

    fields = enrich_indicators_for_odk(indicators)
    if xml_form_id:
        form_id = str(xml_form_id).strip()[:63]
        if not form_id:
            form_id = _xml_form_id(intervention_slug)
    else:
        form_id = _xml_form_id(intervention_slug)
    title = form_title or f"MEL · {intervention_name}"
    version = version or datetime.now(UTC).strftime("%Y.%m.%d.%H%M%S")

    body_lines: list[str] = []
    bind_lines: list[str] = [
        '      <bind nodeset="/data/meta/instanceID" type="string" readonly="true()" jr:preload="uid"/>',
        '      <bind nodeset="/data/meta/instanceName" type="string"/>',
    ]
    instance_lines = [
        "      <meta>",
        "        <instanceID/>",
        "        <instanceName/>",
        "      </meta>",
    ]

    used_names: set[str] = set()
    for index, item in enumerate(fields, start=1):
        label = item.get("label") or item.get("indicator") or f"Question {index}"
        if item.get("locked") and item.get("field_name"):
            field_name = _slugify(str(item["field_name"])) or f"ind_{index:03d}"
        else:
            field_name = _slugify(label) or f"ind_{index:03d}"
        if field_name in used_names:
            field_name = f"{field_name}_{index:03d}"[:50]
            if field_name in used_names:
                field_name = f"ind_{index:03d}"
        used_names.add(field_name)

        input_type = item["input_type"]
        bind_type = INPUT_TYPES.get(input_type, INPUT_TYPES[_DEFAULT_INPUT_TYPE])["bind_type"]
        required_attr = (
            ' required="true()"'
            if item.get("required")
            or item.get("locked")
            or item.get("input_type") in {"date", "geopoint"}
            else ""
        )
        body_lines.extend(
            _control_xml(
                field_name=field_name,
                label=label,
                hint=item.get("hint") or "",
                input_type=input_type,
                options=item.get("options") or [],
            )
        )
        bind_lines.append(
            f'      <bind nodeset="/data/{field_name}" type="{bind_type}"{required_attr}/>'
        )
        instance_lines.append(f"      <{field_name}/>")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<h:html xmlns="{_XMLNS}" xmlns:h="http://www.w3.org/1999/xhtml" xmlns:jr="{_JR}" xmlns:orx="{_OPENROSA}">
  <h:head>
    <h:title>{escape(title)}</h:title>
    <model>
      <instance>
        <data id="{escape(form_id)}" version="{escape(version)}">
{chr(10).join(instance_lines)}
        </data>
      </instance>
{chr(10).join(bind_lines)}
    </model>
  </h:head>
  <h:body>
{chr(10).join(body_lines)}
  </h:body>
</h:html>
"""
    return form_id, xml
