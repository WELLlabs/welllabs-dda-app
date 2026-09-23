"""Load Solutions Basket landscape objectives for hypothesis validation.

Picker uses L-01 … L-08 only. PDF lists every specific objective under the
selected landscape (excluding Purpose / Intended Outcome and Solution Design X MEL).
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Any

_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "landscape_objectives.csv"

# PDF table columns for specific objectives under a selected landscape.
PDF_OBJECTIVE_COLUMNS = (
    ("landscape_id", "Landscape ID"),
    ("landscape_objective", "Landscape Objective"),
    ("objective_id", "Objective ID"),
    ("previous_objective_id", "Previous Objective ID"),
    ("specific_objective", "Specific Objective"),
    ("wiser_dimension", "WISER Dimension"),
)


def _parse_specific_row(row: dict[str, str]) -> dict[str, Any] | None:
    landscape_id = (row.get("Landscape ID") or "").strip()
    objective_id = (row.get("Objective ID") or "").strip()
    if not landscape_id or not objective_id:
        return None
    return {
        "landscape_id": landscape_id,
        "landscape_objective": (row.get("Landscape Objective") or "").strip(),
        "objective_id": objective_id,
        "previous_objective_id": (row.get("Previous Objective ID") or "").strip(),
        "specific_objective": (row.get("Specific Objective") or "").strip(),
        "wiser_dimension": (row.get("WISER Dimension") or "").strip(),
    }


@lru_cache(maxsize=1)
def load_specific_objectives() -> list[dict[str, Any]]:
    """All specific / sub-objective rows from the Solutions Basket CSV."""
    if not _CSV_PATH.is_file():
        return []
    out: list[dict[str, Any]] = []
    with _CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            parsed = _parse_specific_row(row)
            if parsed:
                out.append(parsed)
    return out


@lru_cache(maxsize=1)
def load_landscape_objectives() -> list[dict[str, Any]]:
    """Unique landscape-level rows keyed by Landscape ID (L-01 … L-08) for the picker."""
    seen: dict[str, dict[str, Any]] = {}
    for row in load_specific_objectives():
        lid = row["landscape_id"]
        if lid in seen:
            continue
        seen[lid] = {
            # Stored on hypotheses.landscape_objective_id
            "objective_id": lid,
            "landscape_id": lid,
            "landscape_objective": row["landscape_objective"],
        }
    return list(seen.values())


def get_landscape_objective(objective_id: str | None) -> dict[str, Any] | None:
    if not objective_id:
        return None
    oid = str(objective_id).strip()
    for obj in load_landscape_objectives():
        if obj["objective_id"] == oid or obj["landscape_id"] == oid:
            return obj
    return None


def specific_objectives_for_landscape(landscape_id: str | None) -> list[dict[str, Any]]:
    """Specific objectives under a landscape (L-01 … L-08)."""
    if not landscape_id:
        return []
    lid = str(landscape_id).strip()
    return [r for r in load_specific_objectives() if r["landscape_id"] == lid]


def known_objective_ids() -> frozenset[str]:
    return frozenset(o["objective_id"] for o in load_landscape_objectives())
