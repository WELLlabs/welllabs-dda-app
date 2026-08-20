"""Parse the MEL outcomes/indicators catalog CSV."""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "outcomes_indicators.csv"

_CATEGORIES = (
    ("biophysical", 2, 3, "Biophysical (plot / structure level)"),
    ("socioeconomic", 4, 5, "Socio-economic"),
    ("watershed", 8, 9, "Watershed-level"),
)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "item"


def _split_indicators(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []

    parts = re.split(r"\n(?=\d+\.\s)|\n(?=\d+\)\s)", text)
    indicators: list[str] = []
    for part in parts:
        cleaned = re.sub(r"^\d+[\.)]\s*", "", part.strip())
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            indicators.append(cleaned)

    if not indicators and text:
        indicators = [re.sub(r"\s+", " ", text)]

    return indicators


def _parse_outcome_text(text: str) -> tuple[str, str, str]:
    """Return (title, assumptions, full_text)."""
    full_text = (text or "").strip()
    if not full_text:
        return "", "", ""

    parts = re.split(r"\n*\s*Assumptions?:\s*", full_text, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        title_part, assumptions = parts[0].strip(), parts[1].strip()
    else:
        title_part, assumptions = full_text, ""

    title = re.sub(r"\s+", " ", title_part).strip()
    assumptions = re.sub(r"\n{3,}", "\n\n", assumptions).strip()
    return title, assumptions, full_text


def _outcome_id(intervention_slug: str, category: str, outcome_text: str) -> str:
    title, _, _ = _parse_outcome_text(outcome_text)
    key = title or outcome_text
    return _slugify(f"{intervention_slug}-{category}-{key}")[:80]


def _indicator_id(outcome_id: str, index: int, indicator: str) -> str:
    """Stable unique ID for an indicator within an outcome.

    Index is required: many catalog rows share long similar labels
    (e.g. \"Revenue/Profit…\"), so slug-only IDs collide after truncation.
    Keep ``outcome_id`` + index in the ID before any length cut.
    """
    head = _slugify(outcome_id)[:55]
    mid = f"i{index:03d}"
    tail = _slugify(indicator)
    combined = f"{head}-{mid}-{tail}" if tail else f"{head}-{mid}"
    return combined[:80]


def _ensure_unique_id(candidate: str, seen: set[str]) -> str:
    if candidate not in seen:
        return candidate
    suffix = 2
    while True:
        trimmed = candidate[: max(1, 80 - len(str(suffix)) - 1)]
        next_id = f"{trimmed}-{suffix}"
        if next_id not in seen:
            return next_id
        suffix += 1


def _parse_rows(rows: list[list[str]]) -> list[dict]:
    interventions: list[dict] = []
    current: dict | None = None

    for row in rows[1:]:
        while len(row) < 11:
            row.append("")

        name = (row[0] or "").strip()
        requirement = (row[1] or "").strip()
        row_must_measure = requirement.lower().startswith("must measure")

        if name:
            if name.lower() == "intervention":
                current = None
                continue
            current = {
                "name": name,
                "slug": _slugify(name),
                "requirement": requirement,
                "outcomes": [],
            }
            interventions.append(current)
        elif current is None:
            continue

        for category, outcome_col, indicator_col, category_label in _CATEGORIES:
            outcome_text = (row[outcome_col] or "").strip()
            indicator_text = (row[indicator_col] or "").strip()

            if outcome_text.lower().startswith("optional:"):
                continue
            if not outcome_text and not indicator_text:
                continue

            if not outcome_text and indicator_text:
                # Watershed (and similar) rows often put the measurable text only in
                # the indicator column — treat it as both outcome title and indicator.
                outcome_text = indicator_text

            indicators = _split_indicators(indicator_text)
            title, assumptions, full_text = _parse_outcome_text(outcome_text)
            outcome_key = _outcome_id(current["slug"], category, outcome_text)
            existing = next(
                (item for item in current["outcomes"] if item["id"] == outcome_key),
                None,
            )
            if existing:
                for indicator in indicators:
                    if indicator not in existing["indicators"]:
                        existing["indicators"].append(indicator)
                continue

            current["outcomes"].append(
                {
                    "id": outcome_key,
                    "category": category,
                    "category_label": category_label,
                    "title": title or full_text,
                    "assumptions": assumptions,
                    "outcome": title or full_text,
                    "indicators": indicators,
                    "must_measure": row_must_measure,
                }
            )

    return [item for item in interventions if item["outcomes"]]


@lru_cache(maxsize=1)
def load_mel_catalog() -> list[dict]:
    if not _CSV_PATH.is_file():
        raise FileNotFoundError(f"MEL catalog not found at {_CSV_PATH}")

    with _CSV_PATH.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))

    return _parse_rows(rows)


def list_interventions() -> list[dict]:
    return [
        {
            "slug": item["slug"],
            "name": item["name"],
            "outcome_count": len(item["outcomes"]),
        }
        for item in load_mel_catalog()
    ]


def get_intervention(slug: str) -> dict | None:
    for item in load_mel_catalog():
        if item["slug"] == slug:
            return item
    return None


def resolve_selected_outcomes(slug: str, selected_outcome_ids: list[str]) -> dict:
    intervention = get_intervention(slug)
    if intervention is None:
        raise KeyError(slug)

    must_ids = {o["id"] for o in intervention["outcomes"] if o["must_measure"]}
    selected = set(selected_outcome_ids) | must_ids

    chosen_outcomes = [o for o in intervention["outcomes"] if o["id"] in selected]
    indicators: list[dict] = []
    seen: set[str] = set()

    for outcome in chosen_outcomes:
        for index, indicator in enumerate(outcome["indicators"]):
            indicator_id = _ensure_unique_id(
                _indicator_id(outcome["id"], index, indicator),
                seen,
            )
            seen.add(indicator_id)
            indicators.append(
                {
                    "id": indicator_id,
                    "outcome_id": outcome["id"],
                    "outcome": outcome["title"],
                    "assumptions": outcome["assumptions"],
                    "category": outcome["category"],
                    "category_label": outcome["category_label"],
                    "indicator": indicator,
                    "must_measure": outcome["must_measure"],
                }
            )

    return {
        "intervention": {
            "slug": intervention["slug"],
            "name": intervention["name"],
        },
        "outcomes": chosen_outcomes,
        "indicators": indicators,
    }
