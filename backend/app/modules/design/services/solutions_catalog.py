"""Parse site_suitability.csv into GIS suitability rules per solution.

The sheet has two header rows (a generic one, then the real labels), so columns
are read by position:

  0 Sl · 1 Solution name · 2 GIS check · 3 Solution type · 4 Slope range (%)
  5 Stream order · 6 LULC · 7 Water source type · 8 Min catchment area
  9 Soil thickness · 10 Summer groundwater depth

Only slope, stream order and LULC have GIS data behind them. The remaining
columns are surfaced as field-check notes.
"""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "site_suitability.csv"

# LULC 250k 2023-24 class values (see diagnose/config/layers.yaml → lulc250k).
# "Agriculture" is active crops only — Current Fallow (6) is deliberately excluded.
LULC_TERM_CLASSES: dict[str, frozenset[int]] = {
    "agriculture": frozenset({2, 3, 4, 5}),
    "plantation": frozenset({7}),
    "barren": frozenset({14}),
    "wasteland": frozenset({14}),
    "waterbody": frozenset({16, 17}),
}

LULC_CLASS_LABELS: dict[int, str] = {
    0: "No data",
    1: "Built-up",
    2: "Kharif Crop",
    3: "Rabi Crop",
    4: "Zaid Crop",
    5: "Double/Triple Crop",
    6: "Current Fallow",
    7: "Plantation",
    8: "Evergreen Forest",
    9: "Deciduous Forest",
    10: "Degraded/Scrub Forest",
    11: "Littoral Swamp",
    12: "Grassland",
    13: "Shifting Cultivation",
    14: "Wasteland",
    15: "Rann",
    16: "Waterbodies max",
    17: "Waterbodies min",
    18: "Snow Cover",
}

# Land where no area solution is sited unless its sheet row explicitly targets it
# (e.g. waterbody desiltation). The sheet leaves LULC blank for slope-only solutions
# such as field bunds; without this they would cover villages and tanks.
HARD_EXCLUDE_LULC: frozenset[int] = frozenset({1, 15, 16, 17, 18})

SOLUTION_TYPES = ("Areal", "Instream", "Point")

_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:st|nd|rd|th)?\s*[-–to]+\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_SINGLE_RE = re.compile(r"(\d+(?:\.\d+)?)")


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or "solution"


def parse_range(text: str | None) -> tuple[float, float] | None:
    """Parse '5 - 15 %', '0 - 15%', '1st - 2nd', '3th - 5th' → (lo, hi)."""
    raw = (text or "").strip()
    if not raw:
        return None
    m = _RANGE_RE.search(raw)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return (min(lo, hi), max(lo, hi))
    m = _SINGLE_RE.search(raw)
    if m:
        v = float(m.group(1))
        return (v, v)
    return None


def parse_lulc(text: str | None) -> tuple[frozenset[int] | None, list[str]]:
    """'Agriculture, Plantation' → ({2,3,4,5,7}, ['Agriculture', 'Plantation'])."""
    raw = (text or "").strip()
    if not raw:
        return None, []
    terms = [t.strip() for t in raw.split(",") if t.strip()]
    classes: set[int] = set()
    unknown: list[str] = []
    for term in terms:
        hit = LULC_TERM_CLASSES.get(term.lower())
        if hit is None:
            unknown.append(term)
        else:
            classes |= hit
    if unknown:
        raise ValueError(f"Unmapped LULC term(s) in site_suitability.csv: {unknown}")
    return frozenset(classes), terms


def slope_pct_to_deg(pct: float) -> float:
    """Slope percent → degrees (the slope COG stores degrees)."""
    return math.degrees(math.atan(pct / 100.0))


@dataclass(frozen=True)
class Solution:
    id: str
    sl: str
    name: str
    type: str
    slope_pct: tuple[float, float] | None
    stream_order: tuple[int, int] | None
    lulc_classes: frozenset[int] | None
    lulc_terms: tuple[str, ...]
    notes: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def uses_streams(self) -> bool:
        """Instream solutions, or any solution with a stream-order rule, sit on drainage lines.

        Solutions with no GIS criteria at all (e.g. desiltation of drainage channels)
        are treated as 'all streams in the AOI'.
        """
        if self.type == "Instream" or self.stream_order is not None:
            return True
        return self.slope_pct is None and self.lulc_classes is None

    @property
    def has_gis_criteria(self) -> bool:
        return self.slope_pct is not None or self.stream_order is not None or self.lulc_classes is not None

    @property
    def slope_deg(self) -> tuple[float, float] | None:
        if self.slope_pct is None:
            return None
        return (slope_pct_to_deg(self.slope_pct[0]), slope_pct_to_deg(self.slope_pct[1]))

    def criteria_summary(self) -> list[str]:
        parts: list[str] = []
        if self.slope_pct is not None:
            lo, hi = self.slope_pct
            parts.append(f"Slope {lo:g}–{hi:g} %")
        if self.stream_order is not None:
            lo, hi = self.stream_order
            parts.append(f"Stream order {lo}–{hi}" if lo != hi else f"Stream order {lo}")
        if self.lulc_terms:
            parts.append(", ".join(self.lulc_terms))
        if not parts and self.uses_streams:
            parts.append("All drainage lines")
        return parts

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sl": self.sl,
            "name": self.name,
            "type": self.type,
            "geometry_kind": "line" if self.uses_streams else "area",
            "criteria": {
                "slope_pct": list(self.slope_pct) if self.slope_pct else None,
                "stream_order": list(self.stream_order) if self.stream_order else None,
                "lulc": list(self.lulc_terms) or None,
                "lulc_classes": sorted(self.lulc_classes) if self.lulc_classes else None,
            },
            "criteria_summary": self.criteria_summary(),
            "has_gis_criteria": self.has_gis_criteria,
            "notes": [{"label": k, "value": v} for k, v in self.notes],
        }


_NOTE_COLUMNS = (
    (7, "Water source type"),
    (8, "Min catchment area"),
    (9, "Soil thickness"),
    (10, "Summer groundwater depth"),
)


def _parse_rows(rows: list[list[str]]) -> list[Solution]:
    solutions: list[Solution] = []
    seen: set[str] = set()
    for row in rows:
        row = row + [""] * (11 - len(row))
        sl, name, gis, stype = (c.strip() for c in row[:4])
        if not name or not sl or not sl[0].isdigit():
            continue  # header rows
        if gis.lower() != "yes":
            continue
        if stype not in SOLUTION_TYPES:
            raise ValueError(f"Unknown solution type {stype!r} for {name!r}")
        order = parse_range(row[5])
        lulc_classes, lulc_terms = parse_lulc(row[6])
        notes = tuple((label, row[i].strip()) for i, label in _NOTE_COLUMNS if row[i].strip())
        sid = _slugify(name)
        if sid in seen:
            sid = f"{sid}-{sl}"
        seen.add(sid)
        solutions.append(
            Solution(
                id=sid,
                sl=sl,
                name=name,
                type=stype,
                slope_pct=parse_range(row[4]),
                stream_order=(int(order[0]), int(order[1])) if order else None,
                lulc_classes=lulc_classes,
                lulc_terms=tuple(lulc_terms),
                notes=notes,
            )
        )
    return solutions


def parse_catalog_text(text: str) -> list[Solution]:
    return _parse_rows(list(csv.reader(text.splitlines())))


@lru_cache(maxsize=1)  # cleared on restart; call load_solutions.cache_clear() after editing the CSV
def load_solutions() -> tuple[Solution, ...]:
    with _CSV_PATH.open(newline="", encoding="utf-8-sig") as f:
        return tuple(_parse_rows(list(csv.reader(f))))


def get_solution(solution_id: str) -> Solution | None:
    for s in load_solutions():
        if s.id == solution_id:
            return s
    return None
