"""Parse intervention-analyses.csv into calculation and visual specs."""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "intervention_analyses.csv"


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or "item"


def _split_deps(text: str) -> list[str]:
    if not text or not str(text).strip():
        return []
    return [p.strip() for p in str(text).split(";") if p.strip()]


@lru_cache(maxsize=1)  # cleared on service restart; call load_analyses_catalog.cache_clear() if hot-reloading
def load_analyses_catalog() -> dict[str, Any]:
    if not _CSV_PATH.is_file():
        return {"analyses": []}

    analyses: list[dict[str, Any]] = []
    with _CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = (row.get("title") or "").strip()
            if not title:
                continue
            intervention = (row.get("intervention") or "").strip()
            slugs = [_slugify(part) for part in intervention.split(",") if part.strip()]
            if not slugs:
                continue
            category = (row.get("category") or "").strip().lower()
            analyses.append(
                {
                    "id": _slugify(title),
                    "title": title,
                    "description": (row.get("description") or "").strip(),
                    "intervention": intervention,
                    "intervention_slug": slugs[0],
                    "intervention_slugs": slugs,
                    "category": category,  # calculation | visual
                    "variable_dependency": _split_deps(row.get("variable_dependency") or ""),
                    "methodology": (row.get("methodology") or "").strip(),
                    "analysis_variable_name": (row.get("analysis_variable_name") or "").strip() or None,
                    "chart_description": (row.get("chart_description") or "").strip() or None,
                }
            )
    return {"analyses": analyses}


def analyses_for_intervention(slug: str) -> list[dict[str, Any]]:
    slug_n = _slugify(slug)
    return [
        a
        for a in load_analyses_catalog()["analyses"]
        if slug_n in (a.get("intervention_slugs") or [a["intervention_slug"]])
    ]
