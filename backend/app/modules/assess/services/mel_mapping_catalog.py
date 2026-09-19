"""Parse intervention-mapping.csv into interventions, outcomes, indicators, and questions.

Farm-pond-first catalog: each row is a survey question with optional outcome/indicator links.
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "intervention_mapping.csv"

# Normalize plan / UI slugs onto mapping CSV intervention names.
_MAPPING_SLUG_ALIASES = {
    "farm-pond": "farm-pond",
    "farm_pond": "farm-pond",
    "farmpond": "farm-pond",
    "farm-ponds": "farm-pond",
    "farm-ponds-unlined": "farm-pond",
    "farm-ponds-lined": "farm-pond",
    "pmds": "pmds",
    "pre-monsoon-dry-sowing": "pmds",
    "pre_monsoon_dry_sowing": "pmds",
    "raised-bed-farming": "pmds",
    "raised_bed_farming": "pmds",
    "bio-mulching": "pmds",  # share PMDS survey fields until a separate mapping exists
    "biomulching": "pmds",
}


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or "item"


def _split_semi(text: str) -> list[str]:
    if not text or not str(text).strip():
        return []
    return [p.strip() for p in re.split(r"\s*;\s*", str(text)) if p.strip()]


def _parse_selectors(text: str) -> list[str]:
    if not text or not str(text).strip():
        return []
    return [p.strip() for p in str(text).split("|") if p.strip()]


def _norm_category(raw: str) -> str:
    c = (raw or "").strip().lower().replace("_", " ")
    if c in ("one time", "onetime", "one-time", "ot"):
        return "one_time"
    if c in ("cm", "continuous monitoring", "continuous"):
        return "cm"
    return c or "other"


@lru_cache(maxsize=1)
def load_mapping_catalog() -> dict[str, Any]:
    """Return {interventions: [...]} keyed by slug, each with questions/outcomes."""
    if not _CSV_PATH.is_file():
        return {"interventions": []}

    by_slug: dict[str, dict[str, Any]] = {}

    with _CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("intervention") or "").strip()
            if not name:
                continue
            slug = _slugify(name)
            if slug not in by_slug:
                by_slug[slug] = {
                    "slug": slug,
                    "name": name,
                    "questions": [],
                    "outcomes": {},  # id -> outcome dict
                }

            category = _norm_category(row.get("category") or "")
            question = (row.get("question") or "").strip()
            variable_name = (row.get("variable_name") or "").strip()
            input_type = (row.get("input_type") or "").strip() or "text"
            metric = (row.get("metric") or "").strip()
            selectors = _parse_selectors(row.get("selectors") or "")
            skip_logic = (row.get("skip_logic") or "").strip()
            assumption = (row.get("assumption") or "").strip()

            outcome_titles = _split_semi(row.get("outcome") or "")
            indicator_titles = _split_semi(row.get("indicator") or "")

            q = {
                "question": question,
                "category": category,
                "variable_name": variable_name or None,
                "input_type": input_type,
                "metric": metric or None,
                "selectors": selectors,
                "skip_logic": skip_logic or None,
                "assumption": assumption or None,
                "outcome_titles": outcome_titles,
                "indicator_titles": indicator_titles,
            }
            by_slug[slug]["questions"].append(q)

            # Build outcomes / indicators from rows that declare them
            for ot in outcome_titles:
                oid = _slugify(f"{slug}-{ot}")[:80]
                if oid not in by_slug[slug]["outcomes"]:
                    by_slug[slug]["outcomes"][oid] = {
                        "id": oid,
                        "title": ot,
                        "assumptions": assumption,
                        "indicators": {},
                        "data_points": [],
                    }
                else:
                    if assumption and not by_slug[slug]["outcomes"][oid]["assumptions"]:
                        by_slug[slug]["outcomes"][oid]["assumptions"] = assumption

                for ind in indicator_titles:
                    iid = _slugify(f"{oid}-{ind}")[:80]
                    by_slug[slug]["outcomes"][oid]["indicators"][iid] = {
                        "id": iid,
                        "title": ind,
                    }

                if question:
                    by_slug[slug]["outcomes"][oid]["data_points"].append(
                        {
                            "question": question,
                            "category": category,
                            "variable_name": variable_name or None,
                            "input_type": input_type,
                            "metric": metric or None,
                        }
                    )

    interventions = []
    for slug, data in by_slug.items():
        outcomes = []
        for o in data["outcomes"].values():
            outcomes.append(
                {
                    "id": o["id"],
                    "title": o["title"],
                    "assumptions": o["assumptions"],
                    "indicators": list(o["indicators"].values()),
                    "data_points": o["data_points"],
                }
            )
        interventions.append(
            {
                "slug": slug,
                "name": data["name"],
                "outcomes": outcomes,
                "questions": data["questions"],
                "one_time_questions": [q for q in data["questions"] if q["category"] == "one_time"],
                "cm_questions": [q for q in data["questions"] if q["category"] == "cm"],
            }
        )

    interventions.sort(key=lambda x: x["name"].lower())
    return {"interventions": interventions}


def _has_outcomes_and_indicators(intervention: dict[str, Any]) -> bool:
    for outcome in intervention.get("outcomes") or []:
        if (outcome.get("title") or "").strip() and (outcome.get("indicators") or []):
            return True
    return False


def list_mapping_interventions() -> list[dict[str, Any]]:
    """Interventions available for new MEL plans / deployments.

    Prefer mapping CSV entries that have outcomes; enrich counts from log-frame
    docs when present so the UI shows the full selectable set.
    """
    from app.modules.assess.services.mel_logframe import (
        _load_catalog,
        selectable_outcomes,
    )

    by_slug: dict[str, dict[str, Any]] = {}
    for i in load_mapping_catalog()["interventions"]:
        if not _has_outcomes_and_indicators(i) and not selectable_outcomes(i["slug"]):
            continue
        lf_outs = selectable_outcomes(i["slug"])
        by_slug[i["slug"]] = {
            "slug": i["slug"],
            "name": i["name"],
            "outcome_count": len(lf_outs) if lf_outs else len(i["outcomes"]),
            "from_mapping": True,
        }

    # Include log-frame-only interventions (e.g. bio-mulching before mapping rows exist)
    for key, base in (_load_catalog().get("interventions") or {}).items():
        if key in by_slug:
            continue
        outs = selectable_outcomes(key)
        if not outs:
            continue
        by_slug[key] = {
            "slug": key,
            "name": base.get("name") or key,
            "outcome_count": len(outs),
            "from_mapping": False,
            "from_logframe": True,
        }

    return sorted(by_slug.values(), key=lambda x: x["name"].lower())


def get_mapping_intervention(slug: str) -> dict[str, Any] | None:
    raw = (slug or "").strip().lower()
    slug_n = _MAPPING_SLUG_ALIASES.get(raw) or _slugify(slug)
    for i in load_mapping_catalog()["interventions"]:
        if i["slug"] == slug_n:
            return i
    return None


def resolve_mapping_outcomes(slug: str, outcome_ids: list[str]) -> list[dict[str, Any]]:
    intervention = get_mapping_intervention(slug)
    if not intervention:
        return []
    wanted = set(outcome_ids or [])
    if not wanted:
        return list(intervention["outcomes"])
    return [o for o in intervention["outcomes"] if o["id"] in wanted]


def one_time_questions(slug: str) -> list[dict[str, Any]]:
    intervention = get_mapping_intervention(slug)
    return list(intervention["one_time_questions"]) if intervention else []


def cm_questions(slug: str) -> list[dict[str, Any]]:
    intervention = get_mapping_intervention(slug)
    return list(intervention["cm_questions"]) if intervention else []
