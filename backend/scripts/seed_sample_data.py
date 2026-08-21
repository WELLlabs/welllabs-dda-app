#!/usr/bin/env python3
"""Seed ODK + app DB from soilmoisture.csv and waterlevel.csv.

Creates / reuses project \"sample data\" owned by abhiramjois02@gmail.com with:
  plan = intervention × district
  form = one Continuous Everyday form per plan
  title = \"{project} - {plan} - Continuous Everyday\"
  each CSV row → one ODK submission

Excludes PMDS/PMDC (not in MEL catalog).
"""

from __future__ import annotations

import asyncio
import csv
import os
import sys
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from app.modules.assess.services.odk_form_builder import (
    _slugify,
    build_mel_form_xml,
    enrich_indicators_for_odk,
)
from app.shared.config import settings
from app.shared.database import close_pool, db_cursor, init_pool
from app.shared.integrations.odk import ODKClient
from app.shared.integrations.odk.exceptions import ODKAPIError, ODKConnectionError

OWNER_EMAIL = "abhiramjois02@gmail.com"
PROJECT_NAME = "sample data"
PACKAGE_LABEL = "Continuous Everyday"
REPO_ROOT = Path(__file__).resolve().parents[2]
SOIL_CSV = Path(os.environ.get("SOIL_CSV", REPO_ROOT / "soilmoisture.csv"))
WATER_CSV = Path(os.environ.get("WATER_CSV", REPO_ROOT / "waterlevel.csv"))

PRACTICE_MAP = {
    "biomulching": ("bio-mulching", "Bio-mulching"),
    "bio-mulching": ("bio-mulching", "Bio-mulching"),
    "rbp": ("raised-bed-farming", "Raised-bed farming"),
    "raised-bed farming": ("raised-bed-farming", "Raised-bed farming"),
    "raised bed farming": ("raised-bed-farming", "Raised-bed farming"),
}
STRUCTURE_MAP = {
    "farm pond": ("farm-ponds-unlined", "Farm ponds"),
    "check dam": ("check-dams-earthen-dams", "Check dams/Earthen dams"),
    "earthen dam": ("check-dams-earthen-dams", "Check dams/Earthen dams"),
}
EXCLUDE_PRACTICES = {"pmds", "pmdc"}
SUBMISSION_BATCH = 25
SUBMIT_CONCURRENCY = 3


def _parse_date(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    for fmt in ("%d-%m-%Y", "%d-%m-%y", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _num(raw: str) -> str:
    text = (raw or "").strip().replace(",", "")
    if text == "":
        return ""
    try:
        return str(float(text))
    except ValueError:
        return text


def _geopoint(lat: str, lon: str) -> str:
    return f"{float(lat)} {float(lon)} 0 0"


def _field(label: str, input_type: str) -> dict:
    return {
        "id": _slugify(label),
        "label": label,
        "hint": "",
        "input_type": input_type,
        "indicator": label,
        "outcome": "",
        "category_label": "Sample data",
        "assumptions": "",
        "custom": True,
        "options": [],
    }


def soil_fields() -> list[dict]:
    return [
        _field("District", "text"),
        _field("Plot", "text"),
        _field("Practice", "text"),
        _field("Rainfall on day (mm)", "decimal"),
        _field("Average soil moisture (%)", "decimal"),
    ]


def water_fields() -> list[dict]:
    return [
        _field("District", "text"),
        _field("Structure", "text"),
        _field("Village name", "text"),
        _field("Area of pond (m2)", "decimal"),
        _field("Maximum water level height (m)", "decimal"),
        _field("Rainfall (mm)", "decimal"),
        _field("Water level (m)", "decimal"),
    ]


def form_title(plan_name: str) -> str:
    return f"{PROJECT_NAME} - {plan_name} - {PACKAGE_LABEL}"


def form_xml_id(plan_name: str) -> str:
    return _slugify(f"sample_{plan_name}_everyday")[:63]


def label_to_field_names(fields: list[dict]) -> dict[str, str]:
    enriched = enrich_indicators_for_odk(fields)
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for index, item in enumerate(enriched, start=1):
        label = item.get("label") or item.get("indicator") or f"Question {index}"
        if item.get("locked") and item.get("field_name"):
            name = _slugify(str(item["field_name"])) or f"ind_{index:03d}"
        else:
            name = _slugify(label) or f"ind_{index:03d}"
        if name in used:
            name = f"{name}_{index:03d}"[:50]
        used.add(name)
        mapping[label] = name
    return mapping


def build_submission_xml(*, xml_form_id: str, version: str, values: dict[str, str]) -> str:
    instance_id = f"uuid:{uuid.uuid4()}"
    parts = [
        f'<data id="{escape(xml_form_id)}" version="{escape(version)}">',
        "  <meta>",
        f"    <instanceID>{escape(instance_id)}</instanceID>",
        f"    <instanceName>{escape(values.get('instance_name') or xml_form_id)}</instanceName>",
        "  </meta>",
    ]
    for key, val in values.items():
        if key == "instance_name" or val == "":
            continue
        parts.append(f"  <{key}>{escape(val)}</{key}>")
    parts.append("</data>")
    return "\n".join(parts)


def load_soil_by_plan() -> dict[tuple[str, str, str], list[dict]]:
    """key = (slug, intervention_name, district) → rows"""
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    with SOIL_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            practice = (row.get("Practice") or "").strip()
            if practice.lower() in EXCLUDE_PRACTICES:
                continue
            mapped = PRACTICE_MAP.get(practice.lower())
            if not mapped:
                print(f"Skipping unknown soil practice: {practice!r}", file=sys.stderr)
                continue
            district = (row.get("District") or "").strip()
            groups[(mapped[0], mapped[1], district)].append(row)
    return groups


def load_water_by_plan() -> dict[tuple[str, str, str], list[dict]]:
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    with WATER_CSV.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        field_map = {name: name.strip() for name in (reader.fieldnames or [])}
        for raw in reader:
            row = {field_map.get(k, k): v for k, v in raw.items()}
            structure = (row.get("Structure") or "").strip()
            mapped = STRUCTURE_MAP.get(structure.lower())
            if not mapped:
                print(f"Skipping unknown structure: {structure!r}", file=sys.stderr)
                continue
            district = (row.get("District") or "").strip()
            groups[(mapped[0], mapped[1], district)].append(row)
    return groups


def ensure_owner() -> dict:
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, email, name FROM users WHERE email = %(email)s",
            {"email": OWNER_EMAIL.lower()},
        )
        row = cur.fetchone()
    if not row:
        raise SystemExit(f"Owner user not found: {OWNER_EMAIL}")
    return row


def ensure_project(owner_id) -> dict:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, name, owner_id, description, status, kind, created_at, updated_at
            FROM assess_projects
            WHERE kind = 'mel' AND lower(name) = lower(%(name)s) AND owner_id = %(owner_id)s
            """,
            {"name": PROJECT_NAME, "owner_id": owner_id},
        )
        row = cur.fetchone()
        if row:
            return row
        cur.execute(
            """
            INSERT INTO assess_projects (name, owner_id, description, status, kind)
            VALUES (%(name)s, %(owner_id)s, %(description)s, 'active', 'mel')
            RETURNING id, name, owner_id, description, status, kind, created_at, updated_at
            """,
            {
                "name": PROJECT_NAME,
                "owner_id": owner_id,
                "description": "Sample MEL forms and submissions from soil moisture and water level CSVs.",
            },
        )
        return cur.fetchone()


def ensure_plan(project_id, *, name: str, intervention_slug: str, created_by) -> dict:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, project_id, name, intervention_slug, plan_json, created_by, created_at, updated_at
            FROM mel_plans
            WHERE project_id = %(project_id)s
              AND intervention_slug = %(intervention_slug)s
              AND lower(name) = lower(%(name)s)
            """,
            {
                "project_id": project_id,
                "intervention_slug": intervention_slug,
                "name": name,
            },
        )
        row = cur.fetchone()
        if row:
            return row
        cur.execute(
            """
            INSERT INTO mel_plans (project_id, name, intervention_slug, created_by)
            VALUES (%(project_id)s, %(name)s, %(intervention_slug)s, %(created_by)s)
            RETURNING id, project_id, name, intervention_slug, plan_json, created_by, created_at, updated_at
            """,
            {
                "project_id": project_id,
                "name": name,
                "intervention_slug": intervention_slug,
                "created_by": created_by,
            },
        )
        return cur.fetchone()


def upsert_mel_form(
    *,
    project_id,
    plan_id,
    xml_form_id: str,
    name: str,
    created_by,
) -> dict:
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO mel_forms (
                project_id, plan_id, xml_form_id, name, package_id, package_title, created_by
            )
            VALUES (
                %(project_id)s, %(plan_id)s, %(xml_form_id)s, %(name)s,
                'continuous_everyday', %(package_title)s, %(created_by)s
            )
            ON CONFLICT (plan_id, xml_form_id) DO UPDATE SET
                name = EXCLUDED.name,
                package_title = EXCLUDED.package_title
            RETURNING id, xml_form_id, name
            """,
            {
                "project_id": project_id,
                "plan_id": plan_id,
                "xml_form_id": xml_form_id,
                "name": name,
                "package_title": PACKAGE_LABEL,
                "created_by": created_by,
            },
        )
        return cur.fetchone()


async def with_retries(coro_factory, *, attempts: int = 6, label: str = "ODK"):
    delay = 2.0
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await coro_factory()
        except (ODKConnectionError, ODKAPIError) as exc:
            last_exc = exc
            status = getattr(exc, "status_code", None)
            retryable = isinstance(exc, ODKConnectionError) or status in {408, 429, 500, 502, 503, 504}
            if not retryable or attempt == attempts:
                raise
            print(f"  retry {attempt}/{attempts} {label}: {exc}", file=sys.stderr)
            await asyncio.sleep(delay)
            delay = min(delay * 1.8, 30)
    raise last_exc  # pragma: no cover


async def publish_or_get_form(
    client: ODKClient,
    odk_project_id: int,
    *,
    xml_form_id: str,
    xml_body: str,
    title: str,
) -> tuple[str, str]:
    """Return (xml_form_id, version). Publishes if missing; else reads existing version."""
    try:
        created = await with_retries(
            lambda: client.post_xml(
                f"/v1/projects/{odk_project_id}/forms",
                xml_body,
                params={"publish": "true", "ignoreWarnings": "true"},
            ),
            label=f"publish {xml_form_id}",
        )
        fid = str((created or {}).get("xmlFormId") or xml_form_id)
        version = str((created or {}).get("version") or "")
        if not version:
            form = await with_retries(
                lambda: client.get(f"/v1/projects/{odk_project_id}/forms/{fid}"),
                label=f"get form {fid}",
            )
            version = str((form or {}).get("version") or "")
        print(f"Published: {title} ({fid}) v={version}")
        return fid, version
    except ODKAPIError as exc:
        print(f"Publish note for {xml_form_id}: {exc}", file=sys.stderr)
        form = await with_retries(
            lambda: client.get(f"/v1/projects/{odk_project_id}/forms/{xml_form_id}"),
            label=f"get existing {xml_form_id}",
        )
        version = str((form or {}).get("version") or "")
        if not version:
            raise
        print(f"Using existing: {title} ({xml_form_id}) v={version}")
        return xml_form_id, version


async def push_rows(
    *,
    client: ODKClient,
    odk_project_id: int,
    xml_form_id: str,
    version: str,
    fields: list[dict],
    rows: list[dict],
    row_to_values,
    sem: asyncio.Semaphore,
) -> int:
    label_to_name = label_to_field_names(fields)
    existing = await with_retries(
        lambda: client.get(f"/v1/projects/{odk_project_id}/forms/{xml_form_id}/submissions"),
        label=f"list {xml_form_id}",
    )
    existing_count = len(existing) if isinstance(existing, list) else 0
    if existing_count >= len(rows):
        print(f"  skip submissions — already {existing_count} (>= {len(rows)})")
        return 0

    needed = len(rows) - existing_count
    todo = rows[-needed:]
    print(f"  pushing {len(todo)} submissions (existing={existing_count}/{len(rows)})")

    submitted = 0
    errors = 0
    lock = asyncio.Lock()

    async def _one(row: dict) -> None:
        nonlocal submitted, errors
        values = row_to_values(row, label_to_name)
        if not values.get(label_to_name["Date"]):
            async with lock:
                errors += 1
            return
        xml = build_submission_xml(xml_form_id=xml_form_id, version=version, values=values)

        async def _post():
            async with sem:
                await client.post_xml(
                    f"/v1/projects/{odk_project_id}/forms/{xml_form_id}/submissions",
                    xml,
                )

        try:
            await with_retries(_post, attempts=5, label=f"submit {xml_form_id}")
            async with lock:
                submitted += 1
        except Exception as exc:  # noqa: BLE001
            async with lock:
                errors += 1
                if errors <= 10:
                    print(f"  submission error: {exc}", file=sys.stderr)

    for start in range(0, len(todo), SUBMISSION_BATCH):
        batch = todo[start : start + SUBMISSION_BATCH]
        await asyncio.gather(*[_one(row) for row in batch])
        done = min(start + len(batch), len(todo))
        print(f"  … {done}/{len(todo)} (ok={submitted} err={errors})")

    print(f"  done: {submitted}/{len(todo)} (errors={errors})")
    return submitted


def soil_row_values(row: dict, label_to_name: dict[str, str]) -> dict[str, str]:
    date = _parse_date(row.get("Date") or "")
    return {
        "instance_name": f"{row.get('Plot')} {row.get('Date')}",
        label_to_name["Date"]: date or "",
        label_to_name["Coordinates"]: _geopoint(row["Latitude"], row["Longitude"]),
        label_to_name["District"]: (row.get("District") or "").strip(),
        label_to_name["Plot"]: (row.get("Plot") or "").strip(),
        label_to_name["Practice"]: (row.get("Practice") or "").strip(),
        label_to_name["Rainfall on day (mm)"]: _num(row.get("Rainfall_on_day_mm") or ""),
        label_to_name["Average soil moisture (%)"]: _num(row.get("Avg_Soil_Moist_%") or ""),
    }


def water_row_values(row: dict, label_to_name: dict[str, str]) -> dict[str, str]:
    date_raw = row.get("Date of reading") or row.get("Date of reading ") or ""
    rain_raw = row.get("Rainfall (mm)") or row.get("Rainfall (mm) ") or ""
    date = _parse_date(date_raw)
    return {
        "instance_name": f"{row.get('Village name')} {date_raw}",
        label_to_name["Date"]: date or "",
        label_to_name["Coordinates"]: _geopoint(row["Latitude"], row["Longitude"]),
        label_to_name["District"]: (row.get("District") or "").strip(),
        label_to_name["Structure"]: (row.get("Structure") or "").strip(),
        label_to_name["Village name"]: (row.get("Village name") or "").strip(),
        label_to_name["Area of pond (m2)"]: _num(row.get("Area of pond (m2)") or ""),
        label_to_name["Maximum water level height (m)"]: _num(row.get("Maximum WL height (m)") or ""),
        label_to_name["Rainfall (mm)"]: _num(rain_raw),
        label_to_name["Water level (m)"]: _num(row.get("Water level (m)") or ""),
    }


async def seed_plan(
    *,
    client: ODKClient,
    odk_project_id: int,
    project,
    owner,
    slug: str,
    intervention_name: str,
    district: str,
    fields: list[dict],
    rows: list[dict],
    row_to_values,
    sem: asyncio.Semaphore,
) -> int:
    plan_name = f"{intervention_name} – {district}"
    plan = ensure_plan(
        project["id"],
        name=plan_name,
        intervention_slug=slug,
        created_by=owner["id"],
    )
    title = form_title(plan_name)
    xml_id = form_xml_id(plan_name)
    xml_form_id, xml_body = build_mel_form_xml(
        intervention_name=intervention_name,
        intervention_slug=f"{slug}_everyday",
        indicators=fields,
        form_title=title,
        xml_form_id=xml_id,
    )
    xml_form_id, version = await publish_or_get_form(
        client,
        odk_project_id,
        xml_form_id=xml_form_id,
        xml_body=xml_body,
        title=title,
    )
    upsert_mel_form(
        project_id=project["id"],
        plan_id=plan["id"],
        xml_form_id=xml_form_id,
        name=title,
        created_by=owner["id"],
    )
    return await push_rows(
        client=client,
        odk_project_id=odk_project_id,
        xml_form_id=xml_form_id,
        version=version,
        fields=fields,
        rows=rows,
        row_to_values=row_to_values,
        sem=sem,
    )


async def main() -> None:
    if settings.odk_project_id is None:
        raise SystemExit("ODK_PROJECT_ID is not configured")
    if not SOIL_CSV.exists() or not WATER_CSV.exists():
        raise SystemExit(f"CSV files missing: {SOIL_CSV} / {WATER_CSV}")

    init_pool()
    try:
        owner = ensure_owner()
        project = ensure_project(owner["id"])
        print(f"Project: {project['name']} ({project['id']}) owner={owner['email']}")

        client = ODKClient()
        odk_project_id = int(settings.odk_project_id)
        sem = asyncio.Semaphore(SUBMIT_CONCURRENCY)
        total = 0

        soil = load_soil_by_plan()
        print(f"Soil plans: {len(soil)}")
        for (slug, intervention_name, district), rows in sorted(soil.items(), key=lambda i: (i[0][1], i[0][2])):
            print(f"\n== {intervention_name} – {district} ({len(rows)} rows) ==")
            try:
                total += await seed_plan(
                    client=client,
                    odk_project_id=odk_project_id,
                    project=project,
                    owner=owner,
                    slug=slug,
                    intervention_name=intervention_name,
                    district=district,
                    fields=soil_fields(),
                    rows=rows,
                    row_to_values=soil_row_values,
                    sem=sem,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"FAILED soil plan {district}/{intervention_name}: {exc}", file=sys.stderr)

        water = load_water_by_plan()
        print(f"\nWater plans: {len(water)}")
        for (slug, intervention_name, district), rows in sorted(water.items(), key=lambda i: (i[0][1], i[0][2])):
            print(f"\n== {intervention_name} – {district} ({len(rows)} rows) ==")
            try:
                total += await seed_plan(
                    client=client,
                    odk_project_id=odk_project_id,
                    project=project,
                    owner=owner,
                    slug=slug,
                    intervention_name=intervention_name,
                    district=district,
                    fields=water_fields(),
                    rows=rows,
                    row_to_values=water_row_values,
                    sem=sem,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"FAILED water plan {district}/{intervention_name}: {exc}", file=sys.stderr)

        with db_cursor() as cur:
            cur.execute(
                "UPDATE assess_projects SET updated_at = now() WHERE id = %(id)s",
                {"id": project["id"]},
            )
        print(f"\nDone. New submissions pushed: {total}")
    finally:
        close_pool()


if __name__ == "__main__":
    asyncio.run(main())
