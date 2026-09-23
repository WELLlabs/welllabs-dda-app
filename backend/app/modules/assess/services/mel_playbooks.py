"""Resolve MEL toolkit playbook names to public URLs."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

# Continuous-monitoring instrument playbooks (EDF–WST shared Drive folder).
_PLAYBOOK_FOLDER = "https://drive.google.com/drive/folders/1-39V-l2lJuFZRT3U1JsNXb1fctY_xIBQ"

# Published MEL Toolbox guides on welllabs.org.
_STAFF_GAUGE_PDF = (
    "https://welllabs.org/wp-content/uploads/2025/05/"
    "Staff-Gauge_A-Guide-to-Measuring-Aquifer-Recharge-through-the-Water-Balance-Method.pdf"
)

_DRIVE_FILENAMES = {
    "flow meters": "Flow Meters_Playbook.pdf",
    "pressure transducers": "Pressure Transducers_Playbook.pdf",
    "soil moisture sensor": "Soil Moisture Sensor_Playbook.pdf",
    "rain gauge": "Rain Gauge_Playbook.pdf",
    "infiltration test": "Infiltration Test_Playbook.pdf",
    "paani pipe for awd": "Paani Pipe for AWD_Playbook.pdf",
}


def _playbook_file_url(filename: str) -> str:
    """Open the shared Drive folder filtered to a specific playbook PDF."""
    return f"{_PLAYBOOK_FOLDER}?q={quote(filename)}"


_PLAYBOOK_ALIASES: dict[str, tuple[str, str]] = {
    "staff gauge | well labs": ("Staff Gauge", _STAFF_GAUGE_PDF),
    "staff gauge": ("Staff Gauge", _STAFF_GAUGE_PDF),
    "staff gauge | welllabs": ("Staff Gauge", _STAFF_GAUGE_PDF),
    "flow meters_playbook.pdf": ("Flow Meters playbook", _playbook_file_url("Flow Meters_Playbook.pdf")),
    "flow meters_playbook": ("Flow Meters playbook", _playbook_file_url("Flow Meters_Playbook.pdf")),
    "pressure transducers_playbook.pdf": (
        "Pressure Transducers playbook",
        _playbook_file_url("Pressure Transducers_Playbook.pdf"),
    ),
    "pressure transducers_playbook": (
        "Pressure Transducers playbook",
        _playbook_file_url("Pressure Transducers_Playbook.pdf"),
    ),
    "soil moisture sensor_playbook.pdf": (
        "Soil Moisture Sensor playbook",
        _playbook_file_url("Soil Moisture Sensor_Playbook.pdf"),
    ),
    "soil moisture sensor_playbook": (
        "Soil Moisture Sensor playbook",
        _playbook_file_url("Soil Moisture Sensor_Playbook.pdf"),
    ),
    "rain gauge_playbook.pdf": ("Rain Gauge playbook", _playbook_file_url("Rain Gauge_Playbook.pdf")),
    "infiltration test_playbook.pdf": (
        "Infiltration Test playbook",
        _playbook_file_url("Infiltration Test_Playbook.pdf"),
    ),
    "paani pipe for awd_playbook.pdf": (
        "Paani Pipe for AWD playbook",
        _playbook_file_url("Paani Pipe for AWD_Playbook.pdf"),
    ),
}


def _norm_key(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _split_playbook_parts(raw: str) -> list[str]:
    """Split a playbooks cell into individual references."""
    text = (raw or "").strip()
    if not text:
        return []
    # Do not split on "|" — labels like "Staff Gauge | WELL LABS" use it.
    parts = re.split(r"[\n;]+", text)
    out: list[str] = []
    for part in parts:
        piece = part.strip(" \t\r-•")
        if piece:
            out.append(piece)
    return out


def resolve_playbook_ref(ref: str) -> dict[str, str] | None:
    """Return {label, url} for a single playbook reference, or None if not linkable."""
    raw = (ref or "").strip()
    if not raw:
        return None

    if re.match(r"^https?://", raw, re.I):
        label = raw
        if "folders/1-39V" in raw or raw.rstrip("/") == _PLAYBOOK_FOLDER:
            label = "Instrument playbooks (Drive)"
        return {"label": label, "url": raw}

    key = _norm_key(raw)
    if key in _PLAYBOOK_ALIASES:
        label, url = _PLAYBOOK_ALIASES[key]
        return {"label": label, "url": url}

    m = re.match(r"^(.+?)[ _]playbook\.pdf$", key, re.I)
    if m:
        base = m.group(1).strip()
        drive_name = _DRIVE_FILENAMES.get(base)
        if not drive_name:
            drive_name = " ".join(w.capitalize() for w in base.split()) + "_Playbook.pdf"
        pretty = re.sub(r"[ _]*[Pp]laybook\.pdf$", " playbook", raw).replace("_", " ").strip()
        return {"label": pretty or drive_name, "url": _playbook_file_url(drive_name)}

    return None


def parse_playbook_links(raw: str) -> list[dict[str, str]]:
    """Parse a playbooks cell into zero or more {label, url} dicts (deduped by url)."""
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for part in _split_playbook_parts(raw):
        resolved = resolve_playbook_ref(part)
        if not resolved:
            continue
        url = resolved["url"]
        if url in seen:
            continue
        seen.add(url)
        links.append(resolved)
    return links


def enrich_methodology_playbooks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach playbook_links to methodology rows for UI/export."""
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["playbook_links"] = parse_playbook_links(item.get("playbooks") or "")
        out.append(item)
    return out


def playbooks_as_reportlab_xml(raw: str) -> str:
    """HTML fragment for reportlab Paragraph with clickable playbook links."""
    links = parse_playbook_links(raw)
    if links:
        parts = []
        for link in links:
            label = (
                link["label"]
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            url = link["url"].replace("&", "&amp;")
            parts.append(f'<a href="{url}" color="#1B75E0"><u>{label}</u></a>')
        return "<br/>".join(parts)
    text = (raw or "").strip()
    if not text:
        return "—"
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )
