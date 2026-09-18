#!/usr/bin/env python3
"""Seed PMDS farm plots from medak-pmds.csv into Thupran - Medak.

Assets stay in MEL. CM rows are posted to the plan's published ODK form.
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent
while ROOT.name not in {"geo-field-pipeline", "/"} and ROOT.parent != ROOT:
    if (ROOT / "medak-pmds.csv").is_file() or (ROOT / "backend").is_dir():
        break
    ROOT = ROOT.parent
def _csv_path() -> Path:
    env = os.environ.get("MEDAK_PMDS_CSV")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent
    for candidate in (
        here / "data" / "medak-pmds.csv",
        here.parent.parent.parent / "medak-pmds.csv",
        Path.cwd() / "medak-pmds.csv",
    ):
        if candidate.is_file():
            return candidate
    return here / "data" / "medak-pmds.csv"


CSV_PATH = _csv_path()
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://geofield:geofield@postgis:5432/dda_product"
)
ACCESS_EMAILS = (
    "abhiramjois02@gmail.com",
    "abhiram.jois@ifmr.ac.in",
)
PROJECT_NAME = "Thupran - Medak"
IMPL_NAME = "PMDS in Medak"
SUBMIT_CONCURRENCY = 5
SUBMISSION_BATCH = 25
INSTANCE_NS = uuid.UUID("3e0d9c7b-1a54-4f88-9d21-6c4e8f0a2b17")

PLOT_ORDER = ("Control 1", "Control 2", "Treatment 1", "Treatment 2")
PAIRS = {"Treatment 1": "Control 1", "Treatment 2": "Control 2"}
FLAT_KEYS = (
    "bm_cm_soil_moisture_flat_corner_a",
    "bm_cm_soil_moisture_flat_corner_b",
    "bm_cm_soil_moisture_flat_corner_c",
    "bm_cm_soil_moisture_flat_corner_d",
    "bm_cm_soil_moisture_flat_centre",
)
F_COLS = ("1-F", "2-F", "3-F", "4-F", "5-F")


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
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})$", s)
    if not m:
        return None
    day, month, year = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if year < 100:
        year += 2000
    try:
        return datetime(year, month, day).date()
    except ValueError:
        return None


def _geopoint(lat: str, lon: str) -> str:
    return f"{float(lat)} {float(lon)} 0 0"


def _coord_key(lat: str, lon: str) -> tuple[str, str]:
    try:
        return f"{float(lat):.5f}", f"{float(lon):.5f}"
    except (TypeError, ValueError):
        return str(lat).strip(), str(lon).strip()


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


def load_plots() -> dict[str, dict]:
    plots: dict[str, dict] = {}
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        field_map = {h: h.strip() for h in (reader.fieldnames or [])}
        for raw in reader:
            r = {
                field_map.get(k, k.strip()): (v.strip() if isinstance(v, str) else v)
                for k, v in raw.items()
            }
            name = (r.get("Plot") or "").strip()
            if not name:
                continue
            rec = plots.setdefault(
                name,
                {
                    "name": name,
                    "lat": r.get("Latitude") or "",
                    "lon": r.get("Longitude") or "",
                    "district": r.get("District") or "Medak",
                    "rows": [],
                },
            )
            rec["rows"].append(r)
    missing = [n for n in PLOT_ORDER if n not in plots]
    if missing:
        raise SystemExit(f"CSV missing plots: {missing}")
    return plots


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


def seed_db(plots: dict[str, dict]) -> dict:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            user = _owner_user(cur)
            cur.execute(
                """
                SELECT id, owner_id, name FROM assess_projects
                WHERE kind = 'mel' AND name = %s
                """,
                (PROJECT_NAME,),
            )
            project = cur.fetchone()
            if not project:
                project_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO assess_projects (id, name, description, kind, owner_id)
                    VALUES (%s, %s, %s, 'mel', %s)
                    RETURNING id, owner_id, name
                    """,
                    (
                        project_id,
                        PROJECT_NAME,
                        "Sample MEL project for Thupran / Medak farm ponds and PMDS plots.",
                        user["id"],
                    ),
                )
                project = cur.fetchone()
            project_id = str(project["id"])
            owner_id = str(project["owner_id"])
            _grant_mel_access(cur, project_id, owner_id)

            cur.execute(
                """
                SELECT id, name, plan_json FROM mel_plans
                WHERE project_id = %s AND kind = 'implementation'
                  AND intervention_slug = 'pmds'
                ORDER BY CASE WHEN name = %s THEN 0 ELSE 1 END, created_at ASC
                LIMIT 1
                """,
                (project_id, IMPL_NAME),
            )
            impl = cur.fetchone()
            if not impl:
                plan_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO mel_plans (
                        id, project_id, name, intervention_slug, kind, plan_json, created_by
                    ) VALUES (%s, %s, %s, 'pmds', 'implementation', %s::jsonb, %s)
                    """,
                    (
                        plan_id,
                        project_id,
                        IMPL_NAME,
                        json.dumps({"outcome_ids": [], "seed": "medak-pmds.csv"}),
                        owner_id,
                    ),
                )
                plan_json = {}
            else:
                plan_id = str(impl["id"])
                plan_json = impl.get("plan_json") if isinstance(impl.get("plan_json"), dict) else {}

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
            by_label = {str(a["label"] or ""): str(a["id"]) for a in existing_assets}
            by_coord = {}
            for asset in existing_assets:
                loc = str((asset.get("ot_answers") or {}).get("bm_ot_location") or "")
                parts = [p.strip() for p in loc.replace(",", " ").split() if p.strip()]
                if len(parts) >= 2:
                    by_coord[_coord_key(parts[0], parts[1])] = str(asset["id"])

            created: dict[str, dict] = {}
            for name in PLOT_ORDER:
                info = plots[name]
                label = f"{name} — Thupran"
                coord = _coord_key(info["lat"], info["lon"])
                asset_id = by_label.get(label) or by_coord.get(coord)
                role = "control" if name.startswith("Control") else "treatment"
                ot = {
                    "bm_ot_location": f"{info['lat']},{info['lon']}",
                    "bm_ot_date": "2025-08-26",
                    "bm_ot_district_name": "Medak",
                    "bm_ot_block_name": "Medak",
                    "bm_ot_village_name": "Thupran",
                    "bm_ot_farmer_name": name,
                    "bm_ot_agriculture_season": "Kharif",
                    "bm_ot_crop_grown": "PMDS",
                    "bm_ot_year_month_of_adoption": "2025-08-01",
                    "bm_ot_area_under_the_crop": 1,
                    "bm_ot_area_unit": "acre",
                    "bm_ot_source_of_irrigation_water": ["Rainfed"],
                    "bm_ot_has_flow_meter": "No",
                    "bm_ot_method_of_irrigation": ["Raised bed farming"]
                    if role == "treatment"
                    else ["Flood irrigation"],
                    "bm_ot_last_irrigation_applied": "No",
                    "bm_ot_plot_role": role,
                }
                if not asset_id:
                    asset_id = str(uuid.uuid4())
                    cur.execute(
                        """
                        INSERT INTO mel_assets (
                            id, project_id, plan_id, intervention_slug, label, ot_answers, created_by
                        ) VALUES (%s, %s, %s, 'pmds', %s, %s::jsonb, %s)
                        """,
                        (asset_id, project_id, plan_id, label, json.dumps(ot), owner_id),
                    )
                created[name] = {
                    "id": asset_id,
                    "label": label,
                    "lat": info["lat"],
                    "lon": info["lon"],
                    "rows": info["rows"],
                    "role": role,
                }

            for treat, control in PAIRS.items():
                treat_id = created[treat]["id"]
                control_id = created[control]["id"]
                cur.execute(
                    "SELECT ot_answers FROM mel_assets WHERE id = %s",
                    (treat_id,),
                )
                row = cur.fetchone() or {}
                answers = dict(row.get("ot_answers") or {})
                answers["bm_ot_paired_control_asset_id"] = control_id
                answers["bm_ot_plot_role"] = "treatment"
                cur.execute(
                    """
                    UPDATE mel_assets
                    SET ot_answers = %s::jsonb, updated_at = now()
                    WHERE id = %s
                    """,
                    (json.dumps(answers), treat_id),
                )
                created[treat]["paired_control_asset_id"] = control_id

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
        "project_name": project["name"],
        "plan_id": plan_id,
        "plan_json": plan_json,
        "owner_id": owner_id,
        "assets": [created[n] for n in PLOT_ORDER],
        "xml_form_id": (form or {}).get("xml_form_id") if form else None,
        "form_name": (form or {}).get("name") if form else None,
    }


def _cm_fields(assets: list[dict]) -> list[dict]:
    from app.modules.assess.routers.mel import _map_input_type as map_type
    from app.modules.assess.services.mel_analyses import is_asset_select_field
    from app.modules.assess.services.mel_mapping_catalog import get_mapping_intervention

    intervention = get_mapping_intervention("pmds")
    if not intervention:
        raise SystemExit("PMDS mapping catalog not found")
    asset_options = [
        {"value": str(a["id"]), "label": a["label"] or str(a["id"])} for a in assets
    ]
    fields = []
    for q in intervention["cm_questions"]:
        var = q.get("variable_name") or ""
        if not var:
            continue
        input_type = map_type(q.get("input_type") or "text")
        choices = list(q.get("selectors") or [])
        options = [{"value": c, "label": c} for c in choices]
        if is_asset_select_field(var):
            options = asset_options
            choices = [o["label"] for o in asset_options]
            input_type = "select_one"
        fields.append(
            {
                "id": var,
                "field_name": var,
                "label": q.get("question") or var,
                "input_type": input_type,
                "choices": choices,
                "options": options,
                "required": is_asset_select_field(var),
                "hint": q.get("skip_logic") or "",
                "custom": False,
            }
        )
    return fields


async def publish_cm_form(ctx: dict) -> str:
    from datetime import timezone as tz

    from app.modules.assess.routers.mel import format_odk_form_title
    from app.modules.assess.services.odk_form_builder import build_mel_form_xml
    from app.shared.config import settings
    from app.shared.integrations.odk import ODKClient
    from app.shared.integrations.odk.exceptions import ODKAPIError

    if settings.odk_project_id is None:
        raise SystemExit("ODK_PROJECT_ID is not configured")

    fields = _cm_fields(ctx["assets"])
    form_title = ctx.get("form_name") or format_odk_form_title(
        ctx["project_name"], IMPL_NAME, "CM"
    )
    existing_xml_id = (ctx.get("xml_form_id") or "").strip() or None
    version = datetime.now(tz.utc).strftime("%Y.%m.%d.%H%M%S")
    xml_form_id, xml_body = build_mel_form_xml(
        intervention_name="PMDS",
        intervention_slug="pmds_cm",
        indicators=fields,
        form_title=form_title,
        xml_form_id=existing_xml_id,
        version=version,
    )

    client = ODKClient()
    odk_project_id = int(settings.odk_project_id)
    try:
        if existing_xml_id:
            try:
                await client.post_xml(
                    f"/v1/projects/{odk_project_id}/forms/{existing_xml_id}/draft",
                    xml_body,
                    params={"ignoreWarnings": "true"},
                )
            except ODKAPIError as exc:
                if exc.status_code not in {409, 400}:
                    raise
                await client.post_empty(
                    f"/v1/projects/{odk_project_id}/forms/{existing_xml_id}/draft"
                )
                await client.post_xml(
                    f"/v1/projects/{odk_project_id}/forms/{existing_xml_id}/draft",
                    xml_body,
                    params={"ignoreWarnings": "true"},
                )
            await client.post_empty(
                f"/v1/projects/{odk_project_id}/forms/{existing_xml_id}/draft/publish",
                params={"version": version},
            )
            stored_xml_id = existing_xml_id
        else:
            created = await client.post_xml(
                f"/v1/projects/{odk_project_id}/forms",
                xml_body,
                params={"publish": "true", "ignoreWarnings": "true"},
            )
            stored_xml_id = str((created or {}).get("xmlFormId") or xml_form_id)
    except ODKAPIError as exc:
        raise SystemExit(f"Failed to publish PMDS CM form: {exc}") from exc

    import psycopg

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO mel_forms (
                    project_id, plan_id, xml_form_id, name, package_id, package_title, created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (plan_id, xml_form_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    package_id = EXCLUDED.package_id,
                    package_title = EXCLUDED.package_title
                """,
                (
                    ctx["project_id"],
                    ctx["plan_id"],
                    stored_xml_id,
                    form_title,
                    "cm-mapping",
                    "PMDS — continuous monitoring",
                    ctx["owner_id"],
                ),
            )
        conn.commit()
    ctx["xml_form_id"] = stored_xml_id
    ctx["form_name"] = form_title
    print(f"Published CM form {stored_xml_id} v={version}")
    return stored_xml_id


def _row_values(asset: dict, row: dict, date_iso: str) -> dict[str, str]:
    values = {
        "instance_name": f"{asset['label']} {date_iso}",
        "observation_date": date_iso,
        "coordinates": _geopoint(asset["lat"], asset["lon"]),
        "bm_cm_select_the_asset_id": asset["id"],
        "bm_cm_date_of_reading": date_iso,
        "bm_cm_has_flow_meter": "No",
        "bm_cm_raised_bed_farming": "No",
    }
    rain = _num(row.get("Rainfall_on_day_mm"))
    if rain is not None:
        values["bm_cm_rainfall"] = str(rain)
    for col, key in zip(F_COLS, FLAT_KEYS):
        val = _num(row.get(col))
        if val is not None:
            values[key] = str(val)
    return values


async def push_cm_to_odk(ctx: dict) -> int:
    xml_form_id = ctx.get("xml_form_id")
    if not xml_form_id:
        raise SystemExit("No CM form id after publish")

    from app.shared.config import settings
    from app.shared.integrations.odk import ODKClient
    from app.shared.integrations.odk.exceptions import ODKAPIError, ODKConnectionError

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

    todo: list[tuple[str, dict[str, str]]] = []
    for asset in ctx["assets"]:
        for idx, row in enumerate(asset["rows"]):
            d = _parse_date(row.get("Date"))
            if d is None:
                print(f"  skip undated row for {asset['label']}: {row.get('Date')!r}", file=sys.stderr)
                continue
            date_iso = d.isoformat()
            instance_uuid = uuid.uuid5(
                INSTANCE_NS, f"{xml_form_id}:{asset['id']}:{date_iso}:{idx}"
            )
            instance_id = f"uuid:{instance_uuid}"
            if instance_id in existing_ids:
                continue
            todo.append((instance_id, _row_values(asset, row, date_iso)))

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
        await asyncio.gather(*[_one(instance_id, values) for instance_id, values in batch])
        done = min(start + len(batch), len(todo))
        print(f"  … {done}/{len(todo)} (ok={submitted} skip={skipped} err={errors})")

    print(f"  done: submitted={submitted} skipped={skipped} errors={errors}")
    if errors and submitted == 0:
        raise SystemExit("Failed to post PMDS CM readings to ODK")
    return submitted + skipped + len(existing_ids)


def main():
    if not CSV_PATH.is_file():
        raise SystemExit(f"Missing {CSV_PATH}")
    plots = load_plots()
    ctx = seed_db(plots)
    print(f"MEL project {PROJECT_NAME}")
    print(f"  project_id={ctx['project_id']}")
    print(f"  implementation_plan_id={ctx['plan_id']}")
    print(f"  assets={[a['label'] + '=' + a['id'] for a in ctx['assets']]}")
    xml_id = asyncio.run(publish_cm_form(ctx))
    print(f"  xml_form_id={xml_id}")
    posted = asyncio.run(push_cm_to_odk(ctx))
    print(f"ODK submissions on form: {posted}")


if __name__ == "__main__":
    main()
