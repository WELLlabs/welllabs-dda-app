"""Parse measurement recipes from indicators_mel.csv and build schedule packages."""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

from app.modules.assess.services.odk_form_builder import infer_input_type

_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "indicators_mel.csv"

# Stable package ids used by API + UI
PACKAGE_SPECS = (
    {
        "id": "continuous_everyday",
        "family": "continuous",
        "schedule": "everyday",
        "title": "Continuous · Everyday",
        "description": "Daily / per-irrigation continuous monitoring form.",
    },
    {
        "id": "continuous_weekly",
        "family": "continuous",
        "schedule": "weekly",
        "title": "Continuous · Weekly",
        "description": "Weekly (or every few days) continuous monitoring form.",
    },
    {
        "id": "continuous_monthly",
        "family": "continuous",
        "schedule": "monthly",
        "title": "Continuous · Monthly",
        "description": "Monthly / seasonal continuous monitoring form.",
    },
    {
        "id": "one_time",
        "family": "one_time",
        "schedule": "one_time",
        "title": "One-time",
        "description": "One-time measurement form.",
    },
    {
        "id": "bme",
        "family": "bme",
        "schedule": "survey_rounds",
        "title": "BME survey",
        "description": "Single BME form reused across baseline, midline, and endline survey rounds.",
    },
)


def _norm(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text: str) -> set[str]:
    stop = {"of", "the", "in", "a", "an", "and", "or", "to", "for", "from", "by", "on", "at", "as"}
    return {t for t in _norm(text).split() if len(t) > 1 and t not in stop}


def _slugify_field(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    if not slug:
        slug = "field"
    if slug[0].isdigit():
        slug = f"f_{slug}"
    return slug[:50]


@lru_cache(maxsize=1)
def load_measurement_catalog() -> list[dict]:
    if not _CSV_PATH.is_file():
        raise FileNotFoundError(f"Measurement catalog not found at {_CSV_PATH}")

    with _CSV_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []
        headers = [h.strip() for h in reader.fieldnames]
        rows = list(reader)

    # Field-level usable catalog (Indicator, Field, Input type, Options, Usable, …)
    if "Field" in headers and "Input type" in headers:
        return _load_field_level_catalog(rows)

    # Legacy one-row-per-indicator catalog
    catalog: list[dict] = []
    for index, row in enumerate(rows, start=1):
        indicator = (row.get("Indicator") or row.get(headers[0]) or "").strip()
        if not indicator:
            continue
        family_raw = (row.get("CM or BME") or "").strip().lower()
        catalog.append(
            {
                "id": f"meas_{index}",
                "indicator": indicator,
                "family_raw": family_raw,
                "unit": (row.get("Unit") or "").strip(),
                "data": (row.get("Data") or "").strip(),
                "fields": [],
                "method": (row.get("Method of data collection") or "").strip(),
                "frequency": (row.get("Frequency") or "").strip(),
                "analysis": (row.get("Method of analysis") or "").strip(),
                "playbooks": (row.get("Playbooks") or "").strip(),
                "usable": True,
                "norm": _norm(indicator),
                "tokens": frozenset(_tokens(indicator)),
            }
        )
    return catalog


def _parse_options(raw: str) -> list[dict]:
    text = (raw or "").strip()
    if not text:
        return []
    options: list[dict] = []
    for part in re.split(r"\s*\|\s*", text):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            value, label = part.split("=", 1)
            value, label = value.strip(), label.strip()
        else:
            value = _slugify_field(part)[:40]
            label = part
        if value or label:
            options.append({"value": value or _slugify_field(label)[:40], "label": label or value})
    return options


def _load_field_level_catalog(rows: list[dict]) -> list[dict]:
    """Collapse field rows into one catalog entry per usable Indicator."""
    grouped: dict[str, dict] = {}
    order: list[str] = []

    for row in rows:
        indicator = (row.get("Indicator") or "").strip()
        if not indicator:
            continue
        usable_raw = (row.get("Usable") or "yes").strip().lower()
        usable = usable_raw in {"yes", "y", "true", "1"}
        if indicator.startswith("(Excluded)"):
            continue
        if indicator not in grouped:
            grouped[indicator] = {
                "indicator": indicator,
                "family_raw": (row.get("CM or BME") or "").strip().lower(),
                "method": (row.get("Method of data collection") or "").strip(),
                "frequency": (row.get("Frequency") or "").strip(),
                "analysis": (row.get("Method of analysis") or "").strip(),
                "playbooks": (row.get("Playbooks") or "").strip(),
                "fields": [],
                "usable": False,
            }
            order.append(indicator)

        entry = grouped[indicator]
        # Prefer non-empty metadata from any row
        for key, col in (
            ("family_raw", "CM or BME"),
            ("method", "Method of data collection"),
            ("frequency", "Frequency"),
            ("analysis", "Method of analysis"),
            ("playbooks", "Playbooks"),
        ):
            val = (row.get(col) or "").strip()
            if val and not entry[key]:
                entry[key] = val.lower() if key == "family_raw" else val

        field_label = (row.get("Field") or "").strip()
        input_type = (row.get("Input type") or "").strip().lower()
        if not usable or not field_label or input_type in {"", "derived"}:
            continue

        entry["usable"] = True
        entry["fields"].append(
            {
                "label": field_label,
                "input_type": input_type,
                "unit": (row.get("Unit") or "").strip(),
                "options": _parse_options(row.get("Options") or ""),
                "notes": (row.get("Notes") or "").strip(),
            }
        )

    catalog: list[dict] = []
    for index, name in enumerate(order, start=1):
        entry = grouped[name]
        if not entry["usable"] or not entry["fields"]:
            continue
        fields = entry["fields"]
        catalog.append(
            {
                "id": f"meas_{index}",
                "indicator": entry["indicator"],
                "family_raw": entry["family_raw"],
                "unit": fields[0]["unit"] if len(fields) == 1 else "",
                "data": "\n".join(f["label"] for f in fields),
                "fields": fields,
                "method": entry["method"],
                "frequency": entry["frequency"],
                "analysis": entry["analysis"],
                "playbooks": entry["playbooks"],
                "usable": True,
                "norm": _norm(entry["indicator"]),
                "tokens": frozenset(_tokens(entry["indicator"])),
            }
        )
    return catalog


def classify_family(family_raw: str, frequency: str) -> str | None:
    raw = (family_raw or "").strip().lower()
    freq = (frequency or "").lower()
    if raw in {"cm", "continuous"}:
        return "continuous"
    if raw in {"one-time", "onetime", "one time"}:
        return "one_time"
    if raw in {"bme"}:
        return "bme"
    if "baseline" in freq or "midline" in freq or "endline" in freq or "survey round" in freq:
        return "bme"
    if "one-time" in freq or "after monsoon" in freq or "seasonal or one" in freq:
        return "one_time"
    if raw == "cm" or "daily" in freq or "weekly" in freq or "monthly" in freq or "irrigation" in freq:
        return "continuous"
    return None


def continuous_schedule(frequency: str) -> str:
    freq = (frequency or "").lower()
    if "weekly" in freq or "3-4 days" in freq or "every 3" in freq:
        return "weekly"
    if "monthly" in freq or "seasonal" in freq:
        return "monthly"
    # Daily, each irrigation application, and default CM → everyday
    return "everyday"


def package_ids_for_row(row: dict) -> list[str]:
    family = classify_family(row.get("family_raw", ""), row.get("frequency", ""))
    if family == "continuous":
        schedule = continuous_schedule(row.get("frequency", ""))
        return [f"continuous_{schedule}"]
    if family == "one_time":
        return ["one_time"]
    if family == "bme":
        return ["bme"]
    return []


def match_measurement_row(indicator_text: str, *, min_score: float = 0.45) -> dict | None:
    """Fuzzy-match a plan indicator to a measurement catalog row."""
    catalog = load_measurement_catalog()
    needle = _norm(indicator_text)
    needle_tokens = _tokens(indicator_text)
    if not needle:
        return None

    best: dict | None = None
    best_score = 0.0
    for row in catalog:
        hay = row["norm"]
        if not hay:
            continue
        if needle == hay or needle in hay or hay in needle:
            score = 1.0 if needle == hay else 0.92
        else:
            overlap = needle_tokens & set(row["tokens"])
            if not overlap:
                continue
            score = (2 * len(overlap)) / (len(needle_tokens) + len(row["tokens"]) or 1)
            # Prefer longer shared phrases
            if needle[:20] and needle[:20] in hay:
                score = max(score, 0.7)
        if score > best_score:
            best_score = score
            best = row

    if best is None or best_score < min_score:
        return None
    return best


def _split_data_items(data_text: str) -> list[str]:
    text = (data_text or "").strip()
    if not text:
        return []

    # Checkbox / radio survey items: "1. …" or "☐ 1. …" / "◯ 1. …"
    numbered = re.findall(
        r"(?:^|\n)\s*(?:[☐◯○●]\s*)?\d+[\.)]\s*(.+?)(?=(?:\n\s*(?:[☐◯○●]\s*)?\d+[\.)])|\Z)",
        text,
        flags=re.S,
    )
    if len(numbered) >= 2:
        return [re.sub(r"\s+", " ", item).strip(" -•\t") for item in numbered if item.strip()]

    parts = re.split(r"\n+|;\s*|\s+OR\s+", text)
    items: list[str] = []
    for part in parts:
        cleaned = re.sub(r"\s+", " ", part).strip(" -•\t")
        cleaned = re.sub(r"^[☐◯○●]\s*", "", cleaned)
        if cleaned and cleaned.upper() != "OR":
            items.append(cleaned)
    if not items and text:
        items = [re.sub(r"\s+", " ", text)]
    return items


def survey_round_field(package_id: str = "bme") -> dict:
    """Metadata field so one BME form can be reused across survey intervals."""
    return {
        "id": f"{package_id}_survey_round",
        "field_name": "survey_round",
        "label": "Survey round",
        "hint": "Select which interval this submission is for (baseline, midline, or endline).",
        "input_type": "select_one",
        "indicator": "Survey round",
        "outcome": "",
        "category_label": "BME",
        "assumptions": "",
        "custom": False,
        "measurement_id": None,
        "options": [
            {"value": "baseline", "label": "Baseline"},
            {"value": "midline", "label": "Midline"},
            {"value": "endline", "label": "Endline"},
        ],
    }


def suggested_fields_for_row(row: dict, *, package_id: str, indicator_meta: dict | None = None) -> list[dict]:
    """Build default ODK field specs from a measurement catalog row."""
    outcome = (indicator_meta or {}).get("outcome") or ""
    category_label = (indicator_meta or {}).get("category_label") or ""
    method = (row.get("method") or "").strip()
    frequency = (row.get("frequency") or "").strip()

    structured = row.get("fields") or []
    if structured:
        fields: list[dict] = []
        for index, item in enumerate(structured):
            label = item.get("label") or "Measurement"
            unit = (item.get("unit") or "").strip()
            input_type = (item.get("input_type") or infer_input_type(label)).strip()
            if input_type not in {
                "decimal",
                "integer",
                "text",
                "long_text",
                "select_one",
                "select_multiple",
                "geopoint",
                "select_one_yes_no",
            }:
                input_type = infer_input_type(label)
            options = item.get("options") or []
            if input_type == "select_one_yes_no" and not options:
                options = [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]
            hint_parts = [
                p
                for p in (
                    method,
                    f"Frequency: {frequency}" if frequency else "",
                    f"Unit: {unit}" if unit else "",
                    item.get("notes") or "",
                )
                if p
            ]
            field_id = f"{package_id}_{_slugify_field(row['indicator'])}_{index:02d}"
            fields.append(
                {
                    "id": field_id,
                    "field_name": f"{_slugify_field(package_id)[:12]}_{index + 1:03d}",
                    "label": label[:240],
                    "hint": " | ".join(hint_parts)[:400],
                    "input_type": input_type,
                    "indicator": row["indicator"],
                    "outcome": outcome,
                    "category_label": category_label or row.get("family_raw") or "",
                    "assumptions": "",
                    "custom": False,
                    "measurement_id": row["id"],
                    "options": options,
                }
            )
        return fields

    data_items = _split_data_items(row.get("data") or "")
    if not data_items:
        data_items = [row.get("indicator") or "Measurement"]

    unit = (row.get("unit") or "").strip()
    fields = []
    for index, item in enumerate(data_items):
        label = item
        if unit and unit.lower() not in label.lower() and len(data_items) == 1:
            label = f"{label} ({unit})" if "(" not in label else label
        hint_parts = [p for p in (method, f"Frequency: {frequency}" if frequency else "", f"Unit: {unit}" if unit else "") if p]
        hint = " | ".join(hint_parts)[:400]
        input_type = infer_input_type(label)
        if "categorical" in (unit or "").lower() and input_type == "decimal":
            input_type = "text"
        options: list[dict] = []
        # ☐ checkbox lists → multi; ◯ radio lists → single (not yes/no unless only Yes/No)
        if re.search(r"☐", item) or re.search(r"\b(multi select|multiselect)\b", item, re.I):
            input_type = "select_multiple"
        elif re.search(r"[◯○]", item) or re.search(r"\b(single select)\b", item, re.I):
            input_type = "select_one"
        if re.search(r"\byes\s*/\s*no\b|\byes\s*or\s*no\b", item, re.I):
            input_type = "select_one_yes_no"

        field_id = f"{package_id}_{_slugify_field(row['indicator'])}_{index:02d}"
        fields.append(
            {
                "id": field_id,
                "field_name": f"{_slugify_field(package_id)[:12]}_{index + 1:03d}",
                "label": label[:240],
                "hint": hint,
                "input_type": input_type,
                "indicator": row["indicator"],
                "outcome": outcome,
                "category_label": category_label or row.get("family_raw") or "",
                "assumptions": "",
                "custom": False,
                "measurement_id": row["id"],
                "options": options,
            }
        )
    return fields


def attach_measurements(plan_indicators: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (matched_enriched, unmatched) plan indicators."""
    matched: list[dict] = []
    unmatched: list[dict] = []
    for item in plan_indicators:
        text = item.get("indicator") or item.get("label") or ""
        row = match_measurement_row(text)
        if row is None:
            unmatched.append({**item, "measurement": None})
            continue
        matched.append(
            {
                **item,
                "measurement": {
                    "id": row["id"],
                    "indicator": row["indicator"],
                    "family_raw": row["family_raw"],
                    "unit": row["unit"],
                    "data": row["data"],
                    "fields": row.get("fields") or [],
                    "method": row["method"],
                    "frequency": row["frequency"],
                    "analysis": row["analysis"],
                    "playbooks": row["playbooks"],
                    "package_ids": package_ids_for_row(row),
                },
            }
        )
    return matched, unmatched


def build_schedule_packages(plan_indicators: list[dict]) -> dict:
    """Build Continuous / One-time / BME packages from plan indicators."""
    matched, unmatched = attach_measurements(plan_indicators)
    by_package: dict[str, dict] = {
        spec["id"]: {
            **spec,
            "indicators": [],
            "suggested_fields": [],
            "frequency_labels": set(),
        }
        for spec in PACKAGE_SPECS
    }

    for item in matched:
        measurement = item["measurement"]
        for package_id in measurement["package_ids"]:
            package = by_package.get(package_id)
            if not package:
                continue
            package["indicators"].append(
                {
                    "id": item.get("id"),
                    "indicator": item.get("indicator"),
                    "outcome": item.get("outcome"),
                    "category_label": item.get("category_label"),
                    "measurement": measurement,
                }
            )
            if measurement.get("frequency"):
                package["frequency_labels"].add(measurement["frequency"])
            # Avoid duplicating fields if same measurement lands twice
            existing_meas = {f.get("measurement_id") for f in package["suggested_fields"]}
            if measurement["id"] in existing_meas:
                continue
            package["suggested_fields"].extend(
                suggested_fields_for_row(
                    {
                        "id": measurement["id"],
                        "indicator": measurement["indicator"],
                        "unit": measurement["unit"],
                        "data": measurement["data"],
                        "fields": measurement.get("fields") or [],
                        "method": measurement["method"],
                        "frequency": measurement["frequency"],
                        "family_raw": measurement["family_raw"],
                    },
                    package_id=package_id,
                    indicator_meta=item,
                )
            )

    packages = []
    for spec in PACKAGE_SPECS:
        package = by_package[spec["id"]]
        if not package["indicators"]:
            continue
        fields = package["suggested_fields"]
        if package["family"] == "bme" and fields:
            # One reusable form: collectors pick baseline / midline / endline per submission
            if not any(f.get("field_name") == "survey_round" for f in fields):
                fields = [survey_round_field(package["id"]), *fields]
        packages.append(
            {
                "id": package["id"],
                "family": package["family"],
                "schedule": package["schedule"],
                "title": package["title"],
                "description": package["description"],
                "frequency_label": "; ".join(sorted(package["frequency_labels"])) or package["title"],
                "indicators": package["indicators"],
                "suggested_fields": fields,
                "form_title": package["title"].replace(" · ", " ").replace("·", " "),
            }
        )

    return {
        "packages": packages,
        "matched_indicators": matched,
        "unmatched_indicators": unmatched,
    }
