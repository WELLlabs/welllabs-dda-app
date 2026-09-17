#!/usr/bin/env python3
"""Seed Medak MEL sample project from medak.csv.

Assets stay in MEL. Continuous-monitoring rows are posted to the plan's
published ODK CM form — they are not stored in mel_cm_readings.
"""

from __future__ import annotations

import asyncio
import csv
import json
import math
import os
import sys
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent
while ROOT.name not in {"geo-field-pipeline", "/"} and ROOT.parent != ROOT:
    if (ROOT / "medak.csv").is_file() or (ROOT / "backend").is_dir():
        break
    ROOT = ROOT.parent
if not (ROOT / "medak.csv").is_file():
    ROOT = Path(__file__).resolve().parent
def _csv_path() -> Path:
    env = os.environ.get("MEDAK_CSV")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent
    for candidate in (
        here / "data" / "medak.csv",
        here.parent.parent.parent / "medak.csv",
        Path.cwd() / "medak.csv",
    ):
        if candidate.is_file():
            return candidate
    return here / "data" / "medak.csv"


CSV_PATH = _csv_path()
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://geofield:geofield@127.0.0.1:5432/dda_product"
)
ACCESS_EMAILS = (
    "abhiramjois02@gmail.com",
    "abhiram.jois@ifmr.ac.in",
)
PROJECT_NAME = "Thupran - Medak"
IMPL_NAME = "Medak monitoring 2025"
SQL_PATH = Path(__file__).with_name("008_mel_cm_readings.sql")
SUBMIT_CONCURRENCY = 5
SUBMISSION_BATCH = 25
INSTANCE_NS = uuid.UUID("7b2c1e4a-6d90-4f11-9c3a-a1b2c3d4e5f6")


def _num(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_date(v):
    s = str(v or "").strip()
    if not s:
        return None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def load_ponds():
    ponds = defaultdict(list)
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        field_map = {h: h.strip() for h in (reader.fieldnames or [])}
        for raw in reader:
            r = {
                field_map.get(k, k.strip()): (v.strip() if isinstance(v, str) else v)
                for k, v in raw.items()
            }
            key = (
                r.get("Village name") or "",
                r.get("Latitude") or "",
                r.get("Longitude") or "",
                r.get("Area of pond (m2)") or "",
                r.get("Maximum WL height (m)") or "",
            )
            ponds[key].append(r)
    return ponds


def side_from_area(area: float | None) -> float:
    if not area or area <= 0:
        return 12.0
    return round(math.sqrt(area), 3)


def _geopoint(lat: str, lon: str) -> str:
    return f"{float(lat)} {float(lon)} 0 0"


def _grant_mel_access(cur, project_id: str, added_by) -> None:
    cur.execute(
        "SELECT id, email FROM users WHERE lower(email) = ANY(%s)",
        (list(ACCESS_EMAILS),),
    )
    found = {str(r["email"]).lower(): r for r in cur.fetchall()}
    for email in ACCESS_EMAILS:
        row = found.get(email.lower())
        if not row:
            print(f"  skip access for {email}: no account yet", file=sys.stderr)
            continue
        cur.execute(
            """
            INSERT INTO assess_project_users (project_id, user_id, role, added_by)
            VALUES (%s, %s, 'admin', %s)
            ON CONFLICT (project_id, user_id) DO UPDATE SET role = EXCLUDED.role
            """,
            (project_id, row["id"], added_by),
        )


def _owner_user(cur):
    cur.execute(
        "SELECT id, email FROM users WHERE lower(email) = ANY(%s)",
        (list(ACCESS_EMAILS),),
    )
    found = {str(r["email"]).lower(): r for r in cur.fetchall()}
    for email in ACCESS_EMAILS:
        if email.lower() in found:
            return found[email.lower()]
    raise SystemExit(
        f"None of {', '.join(ACCESS_EMAILS)} have an account — sign in once first"
    )


def build_submission_xml(*, xml_form_id: str, version: str, instance_id: str, values: dict[str, str]) -> str:
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


def _coord_key(lat: str, lon: str) -> tuple[str, str]:
    try:
        return f"{float(lat):.5f}", f"{float(lon):.5f}"
    except (TypeError, ValueError):
        return str(lat).strip(), str(lon).strip()


def seed_db(ponds: dict) -> dict:
    import psycopg
    from psycopg.rows import dict_row

    pond_items = list(ponds.items())[:2]
    if len(pond_items) < 2:
        raise SystemExit(f"Expected 2 ponds, found {len(ponds)}")

    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            user = _owner_user(cur)

            if SQL_PATH.is_file():
                cur.execute(SQL_PATH.read_text())

            cur.execute(
                """
                SELECT id FROM assess_projects
                WHERE kind = 'mel' AND name = %s
                """,
                (PROJECT_NAME,),
            )
            existing = cur.fetchone()
            if existing:
                project_id = str(existing["id"])
            else:
                project_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO assess_projects (id, name, description, kind, owner_id)
                    VALUES (%s, %s, %s, 'mel', %s)
                    """,
                    (
                        project_id,
                        PROJECT_NAME,
                        "Sample MEL project for Thupran / Medak farm ponds and PMDS plots.",
                        user["id"],
                    ),
                )

            _grant_mel_access(cur, project_id, user["id"])

            cur.execute(
                """
                SELECT id FROM mel_plans
                WHERE project_id = %s AND kind = 'implementation'
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (project_id,),
            )
            impl = cur.fetchone()
            if impl:
                plan_id = str(impl["id"])
            else:
                plan_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO mel_plans (
                        id, project_id, name, intervention_slug, kind, plan_json, created_by
                    ) VALUES (%s, %s, %s, 'farm-pond', 'implementation', %s::jsonb, %s)
                    """,
                    (plan_id, project_id, IMPL_NAME, json.dumps({"outcome_ids": [], "seed": "medak.csv"}), user["id"]),
                )

            cur.execute(
                """
                SELECT id FROM mel_plans
                WHERE project_id = %s AND kind = 'plan'
                LIMIT 1
                """,
                (project_id,),
            )
            if not cur.fetchone():
                cur.execute(
                    """
                    INSERT INTO mel_plans (
                        id, project_id, name, intervention_slug, kind, plan_json, created_by
                    ) VALUES (%s, %s, %s, 'farm-pond', 'plan', %s::jsonb, %s)
                    """,
                    (
                        str(uuid.uuid4()),
                        project_id,
                        "Medak MEL plan",
                        json.dumps({"outcome_ids": [], "seed": "medak.csv"}),
                        user["id"],
                    ),
                )

            cur.execute(
                """
                SELECT id, label, ot_answers
                FROM mel_assets
                WHERE plan_id = %s AND project_id = %s
                ORDER BY created_at ASC
                """,
                (plan_id, project_id),
            )
            existing_assets = list(cur.fetchall())
            assets_by_coord = {}
            for asset in existing_assets:
                loc = str((asset.get("ot_answers") or {}).get("fp_ot_location") or "")
                parts = [p.strip() for p in loc.replace(",", " ").split() if p.strip()]
                if len(parts) >= 2:
                    assets_by_coord[_coord_key(parts[0], parts[1])] = str(asset["id"])

            assets = []
            for i, ((village, lat, lon, area_s, height_s), rows) in enumerate(pond_items, start=1):
                area = _num(area_s) or 144.0
                height = _num(height_s) or 3.048
                side = side_from_area(area)
                label = f"Farm pond {i} — {village or 'Narsampally'}"
                coord = _coord_key(lat, lon)
                asset_id = assets_by_coord.get(coord)
                if not asset_id and i <= len(existing_assets):
                    asset_id = str(existing_assets[i - 1]["id"])
                if not asset_id:
                    ot = {
                        "fp_ot_location": f"{lat},{lon}",
                        "fp_ot_date": "2025-06-01",
                        "fp_ot_district_name": "Medak",
                        "fp_ot_block_name": "Medak",
                        "fp_ot_village_name": village or "Narsampally",
                        "fp_ot_farmer_name": f"Sample farmer {i}",
                        "fp_ot_farm_pond_type": "Individual",
                        "fp_ot_is_the_farm_pond_lined_or_unlined": "Unlined",
                        "fp_ot_structure_status": "New structure",
                        "fp_ot_date_of_construction_of_the_farm_pond": "2024-05-01",
                        "fp_ot_length": side,
                        "fp_ot_breadth": side,
                        "fp_ot_height": height,
                        "fp_ot_source_of_water_in_farm_pond": ["Rainfall runoff"],
                        "fp_ot_has_flow_meter": "No",
                        "fp_ot_use_of_farm_pond": ["Agriculture (irrigation)"],
                        "fp_ot_staff_gauge_installation_date": "2025-05-15",
                        "fp_ot_what_is_the_volumetric_water_savings_kpi_decided_": str(
                            round(area * height, 1)
                        ),
                        "fp_ot_farm_pond_filled": "Yes",
                    }
                    asset_id = str(uuid.uuid4())
                    cur.execute(
                        """
                        INSERT INTO mel_assets (
                            id, project_id, plan_id, intervention_slug, label, ot_answers, created_by
                        ) VALUES (%s, %s, %s, 'farm-pond', %s, %s::jsonb, %s)
                        """,
                        (asset_id, project_id, plan_id, label, json.dumps(ot), user["id"]),
                    )
                assets.append(
                    {
                        "id": asset_id,
                        "label": label,
                        "lat": lat,
                        "lon": lon,
                        "rows": rows,
                    }
                )

            cur.execute(
                """
                SELECT xml_form_id, name, package_id
                FROM mel_forms
                WHERE plan_id = %s AND project_id = %s
                ORDER BY CASE WHEN package_id = 'cm-mapping' THEN 0 ELSE 1 END, created_at ASC
                """,
                (plan_id, project_id),
            )
            form = cur.fetchone()

            conn.commit()

    return {
        "project_id": project_id,
        "plan_id": plan_id,
        "assets": assets,
        "xml_form_id": (form or {}).get("xml_form_id") if form else None,
        "form_name": (form or {}).get("name") if form else None,
    }


async def push_cm_to_odk(ctx: dict) -> int:
    xml_form_id = ctx.get("xml_form_id")
    if not xml_form_id:
        print(
            "No published CM form on this plan. Publish from Edit forms, then re-run this seed.",
            file=sys.stderr,
        )
        return 0

    from app.shared.config import settings
    from app.shared.integrations.odk import ODKClient
    from app.shared.integrations.odk.exceptions import ODKAPIError, ODKConnectionError

    if settings.odk_project_id is None:
        raise SystemExit("ODK_PROJECT_ID is not configured")

    client = ODKClient()
    odk_project_id = int(settings.odk_project_id)
    form = await client.get(f"/v1/projects/{odk_project_id}/forms/{xml_form_id}")
    version = str((form or {}).get("version") or "")
    if not version:
        raise SystemExit(f"ODK form {xml_form_id} has no published version")

    existing = await client.get(f"/v1/projects/{odk_project_id}/forms/{xml_form_id}/submissions")
    existing_ids = set()
    if isinstance(existing, list):
        for item in existing:
            if isinstance(item, dict):
                existing_ids.add(str(item.get("instanceId") or item.get("instanceID") or ""))

    todo: list[tuple[str, str, dict[str, str]]] = []
    for asset in ctx["assets"]:
        geopoint = _geopoint(asset["lat"], asset["lon"])
        for row in asset["rows"]:
            d = _parse_date(row.get("Date of reading"))
            if d is None:
                continue
            date_iso = d.isoformat()
            instance_uuid = uuid.uuid5(
                INSTANCE_NS, f"{xml_form_id}:{asset['id']}:{date_iso}"
            )
            instance_id = f"uuid:{instance_uuid}"
            if instance_id in existing_ids:
                continue
            values = {
                "instance_name": f"{asset['label']} {date_iso}",
                "coordinates": geopoint,
                "fp_cm_select_the_asset_id": asset["id"],
                "fp_cm_date_of_reading": date_iso,
                "fp_cm_water_source": "Rainfall",
            }
            rain = _num(row.get("Rainfall (mm)"))
            if rain is not None:
                values["fp_cm_rainfall"] = str(rain)
            wl = _num(row.get("Water level (m)"))
            if wl is not None:
                values["fp_cm_staff_gauge_reading"] = str(wl)
            todo.append((instance_id, date_iso, values))

    print(
        f"ODK form {xml_form_id} v={version}: "
        f"{len(existing_ids)} existing, pushing {len(todo)}"
    )
    if not todo:
        return len(existing_ids)

    sem = asyncio.Semaphore(SUBMIT_CONCURRENCY)
    submitted = 0
    skipped = 0
    errors = 0
    lock = asyncio.Lock()

    async def _one(instance_id: str, values: dict[str, str]) -> None:
        nonlocal submitted, skipped, errors
        xml = build_submission_xml(
            xml_form_id=xml_form_id,
            version=version,
            instance_id=instance_id,
            values=values,
        )
        try:
            async with sem:
                await client.post_xml(
                    f"/v1/projects/{odk_project_id}/forms/{xml_form_id}/submissions",
                    xml,
                )
            async with lock:
                submitted += 1
        except ODKAPIError as exc:
            async with lock:
                if exc.status_code in {409, 400} and "duplicate" in (exc.detail or "").lower():
                    skipped += 1
                else:
                    errors += 1
                    if errors <= 12:
                        print(f"  submission error: {exc}", file=sys.stderr)
        except ODKConnectionError as exc:
            async with lock:
                errors += 1
                if errors <= 12:
                    print(f"  submission error: {exc}", file=sys.stderr)

    for start in range(0, len(todo), SUBMISSION_BATCH):
        batch = todo[start : start + SUBMISSION_BATCH]
        await asyncio.gather(*[_one(instance_id, values) for instance_id, _date, values in batch])
        done = min(start + len(batch), len(todo))
        print(f"  … {done}/{len(todo)} (ok={submitted} skip={skipped} err={errors})")

    print(f"  done: submitted={submitted} skipped={skipped} errors={errors}")
    if errors and submitted == 0:
        raise SystemExit("Failed to post CM readings to ODK")
    return submitted + skipped + len(existing_ids)


def delete_local_readings(plan_id: str, project_id: str) -> int:
    import psycopg

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM mel_cm_readings
                WHERE plan_id = %s AND project_id = %s
                """,
                (plan_id, project_id),
            )
            deleted = cur.rowcount or 0
        conn.commit()
    return deleted


def main():
    if not CSV_PATH.is_file():
        raise SystemExit(f"Missing {CSV_PATH}")

    ponds = load_ponds()
    ctx = seed_db(ponds)
    print(f"MEL project {PROJECT_NAME}")
    print(f"  project_id={ctx['project_id']}")
    print(f"  implementation_plan_id={ctx['plan_id']}")
    print(f"  assets={[a['id'] for a in ctx['assets']]}")
    print(f"  xml_form_id={ctx.get('xml_form_id')}")

    posted = asyncio.run(push_cm_to_odk(ctx))
    deleted = delete_local_readings(ctx["plan_id"], ctx["project_id"])
    print(f"Cleared {deleted} local mel_cm_readings rows (ODK submissions={posted})")


if __name__ == "__main__":
    main()
