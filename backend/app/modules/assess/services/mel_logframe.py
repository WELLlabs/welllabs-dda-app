"""Log-frame MEL plan content derived from MEL Plan Export Doc templates."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.modules.assess.services.mel_playbooks import enrich_methodology_playbooks

_JSON_PATH = Path(__file__).resolve().parent.parent / "data" / "mel_logframe.json"
_catalog_mtime: float | None = None
_catalog_cache: dict[str, Any] | None = None

_SLUG_ALIASES = {
    "farm-pond": "farm-pond",
    "farm_pond": "farm-pond",
    "farmpond": "farm-pond",
    "farm-ponds": "farm-pond",
    "farm-ponds-unlined": "farm-pond",
    "farm-ponds-lined": "farm-pond",
    "pmds": "pmds",
    "pre-monsoon-dry-sowing": "pmds",
    "bio-mulching": "bio-mulching",
    "biomulching": "bio-mulching",
    "raised-bed-farming": "pmds",
}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _load_catalog() -> dict[str, Any]:
    global _catalog_mtime, _catalog_cache
    if not _JSON_PATH.exists():
        return {"shared_intro": [], "shared_outro": [], "interventions": {}}
    mtime = _JSON_PATH.stat().st_mtime
    if _catalog_cache is not None and _catalog_mtime == mtime:
        return _catalog_cache
    _catalog_cache = json.loads(_JSON_PATH.read_text(encoding="utf-8"))
    _catalog_mtime = mtime
    return _catalog_cache


def resolve_logframe_slug(slug: str) -> str | None:
    key = _SLUG_ALIASES.get((slug or "").strip().lower())
    catalog = _load_catalog()
    if key and key in catalog.get("interventions", {}):
        return key
    return None


def get_logframe_intervention(slug: str) -> dict[str, Any] | None:
    key = resolve_logframe_slug(slug)
    if not key:
        return None
    return _load_catalog()["interventions"].get(key)


def _outcome_id(slug_key: str, title: str) -> str:
    """Stable selectable id for a log-frame outcome title."""
    base = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-") or "outcome"
    return f"{slug_key}-lf-{base}"[:96]


def selectable_outcomes(slug: str) -> list[dict[str, Any]]:
    """All doc (log-frame) outcomes for selection UI — not the sparse mapping CSV set."""
    key = resolve_logframe_slug(slug)
    base = get_logframe_intervention(slug)
    if not key or not base:
        return []
    out: list[dict[str, Any]] = []
    for row in base.get("outcomes") or []:
        if (row.get("kind") or "outcome").lower() != "outcome":
            continue
        title = (row.get("title") or "").strip()
        if not title:
            continue
        oid = _outcome_id(key, title)
        indicators = []
        for j, ind in enumerate(row.get("indicators") or []):
            name = ind if isinstance(ind, str) else str(ind.get("title") or ind)
            if not name.strip():
                continue
            indicators.append({"id": f"{oid}-i{j}", "title": name.strip()})
        out.append(
            {
                "id": oid,
                "title": title,
                "assumptions": row.get("assumptions") or "",
                "outcome_type": row.get("outcome_type"),
                "label": row.get("label") or "",
                "indicators": indicators,
                "from_logframe": True,
            }
        )
    return out


def resolve_selectable_outcomes(slug: str, outcome_ids: list[str] | None) -> list[dict[str, Any]]:
    """Filter selectable log-frame outcomes by id; empty ids → all."""
    all_outs = selectable_outcomes(slug)
    wanted = {x for x in (outcome_ids or []) if x}
    if not wanted:
        return list(all_outs)
    matched = [o for o in all_outs if o["id"] in wanted]
    return matched if matched else list(all_outs)


def _titles_match(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    # Shared significant token overlap
    ta = set(re.findall(r"[a-z]{4,}", (a or "").lower()))
    tb = set(re.findall(r"[a-z]{4,}", (b or "").lower()))
    if not ta or not tb:
        return False
    overlap = ta & tb
    return len(overlap) >= min(2, len(ta), len(tb)) and len(overlap) / max(len(ta), len(tb)) >= 0.4


def _indicator_match(a: str, b: str) -> bool:
    return _titles_match(a, b)


def build_logframe_plan(
    *,
    intervention_slug: str,
    selected_outcome_titles: list[str] | None = None,
    selected_outcome_ids: list[str] | None = None,
    selected_outcomes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build filtered log-frame payload for UI + export.

    Always keeps Goal / Output rows. Outcome rows are filtered to the user's
    selection when titles/ids can be matched; otherwise all catalog outcomes
    are returned so the template stays usable.
    """
    catalog = _load_catalog()
    base = get_logframe_intervention(intervention_slug)
    if not base:
        raise KeyError(f"No log-frame template for intervention '{intervention_slug}'")

    titles: list[str] = []
    for t in selected_outcome_titles or []:
        if t:
            titles.append(str(t))
    # Resolve stable log-frame outcome ids → titles
    if selected_outcome_ids:
        by_id = {o["id"]: o for o in selectable_outcomes(intervention_slug)}
        for oid in selected_outcome_ids:
            o = by_id.get(oid)
            if o and o.get("title"):
                titles.append(str(o["title"]))
    for o in selected_outcomes or []:
        t = o.get("title") or o.get("outcome") or ""
        if t:
            titles.append(str(t))
        for ind in o.get("indicators") or []:
            if isinstance(ind, dict):
                it = ind.get("title") or ind.get("indicator") or ""
            else:
                it = str(ind)
            if it:
                titles.append(it)

    selected_norms = [_norm(t) for t in titles if _norm(t)]
    want_filter = bool(selected_norms or selected_outcome_ids)

    kept_outcomes: list[dict[str, Any]] = []
    selected_indicator_names: list[str] = []

    for row in base.get("outcomes") or []:
        kind = (row.get("kind") or "outcome").lower()
        if kind in {"goal", "output"}:
            kept_outcomes.append(dict(row))
            continue
        title = row.get("title") or ""
        matched = False
        if want_filter:
            matched = any(_titles_match(title, t) for t in titles)
            if not matched:
                # Match via shared indicators with selected outcomes' indicator lists
                for ind in row.get("indicators") or []:
                    if any(_indicator_match(ind, t) for t in titles):
                        matched = True
                        break
        else:
            matched = True
        if matched:
            kept_outcomes.append(dict(row))
            selected_indicator_names.extend(row.get("indicators") or [])

    # If nothing matched besides goal/output, fall back to all outcomes
    if want_filter and not any((r.get("kind") or "") == "outcome" for r in kept_outcomes):
        kept_outcomes = [dict(r) for r in (base.get("outcomes") or [])]
        selected_indicator_names = []
        for r in kept_outcomes:
            if (r.get("kind") or "") == "outcome":
                selected_indicator_names.extend(r.get("indicators") or [])

    methodology: list[dict[str, Any]] = []
    seen = set()
    for row in base.get("methodology") or []:
        ind = row.get("indicator") or ""
        if not ind:
            continue
        if selected_indicator_names:
            if not any(_indicator_match(ind, name) for name in selected_indicator_names):
                continue
        key = _norm(ind)
        if key in seen:
            continue
        seen.add(key)
        methodology.append(dict(row))

    # If filter removed everything, show full methodology for kept outcomes' indicators
    if not methodology and selected_indicator_names:
        for row in base.get("methodology") or []:
            methodology.append(dict(row))

    return {
        "slug": base.get("slug") or intervention_slug,
        "name": base.get("name") or intervention_slug,
        "log_frame_title": base.get("log_frame_title") or f"Log Frame - {base.get('name')}",
        "intro": list(base.get("intro") or catalog.get("shared_intro") or []),
        "note": base.get("note") or "",
        "methodology_heading": base.get("methodology_heading")
        or "Data and Methodology for Indicators",
        "outro": list(base.get("outro") or catalog.get("shared_outro") or []),
        "outcomes": kept_outcomes,
        "methodology": enrich_methodology_playbooks(methodology),
        "has_outcome_type": any((r.get("outcome_type") or "").strip() for r in kept_outcomes),
    }
