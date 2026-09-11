import json
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field, model_validator

from app.modules.diagnose.services.package_progress import PackageProgress
from app.shared.access import (
    diagnosis_access_where,
    require_diagnosis_access,
    require_diagnosis_admin,
    require_diagnosis_owner,
)
from app.shared.auth import get_current_user
from app.shared.config import settings
from app.shared.database import db_cursor
from app.shared import s3_storage
from app.shared.watersheds import (
    _dissolve_custom_aoi,
    _geojson_geom,
    custom_aoi_from_geometry,
    load_stashed_custom_aoi,
    lookup_watershed,
    parse_geojson_polygon,
)

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    lng: float | None = Field(default=None, ge=-180, le=180)
    lat: float | None = Field(default=None, ge=-90, le=90)
    geometry: dict[str, Any] | None = None
    create_token: str | None = Field(default=None, max_length=128)
    watershed_id: str | None = Field(default=None, max_length=500)
    watershed_name: str | None = Field(default=None, max_length=500)
    source: Literal["point", "village", "custom"] = "point"

    @model_validator(mode="after")
    def require_point_or_geometry(self):
        has_point = self.lng is not None and self.lat is not None
        has_geom = self.geometry is not None
        has_token = bool(self.create_token)
        if not has_point and not has_geom and not has_token:
            raise ValueError("Provide lng/lat, geometry, or create_token")
        return self


class AddUserAccess(BaseModel):
    email: EmailStr
    role: str = Field(default="member", pattern=r"^(admin|member)$")


class UpdateUserRole(BaseModel):
    role: str = Field(..., pattern=r"^(admin|member)$")


class AddOrgAccess(BaseModel):
    org_id: UUID


def _row_to_dict(row: dict) -> dict:
    bounds = None
    if row.get("bounds_geojson"):
        coords = row["bounds_geojson"]["coordinates"][0]
        lngs = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        bounds = [min(lngs), min(lats), max(lngs), max(lats)]

    watershed_geometry = row.get("watershed_geojson")
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "owner_id": str(row["owner_id"]),
        "owner_name": row.get("owner_name") or "",
        "owner_email": row.get("owner_email") or "",
        "watershed_id": row["watershed_id"],
        "watershed_name": row["watershed_name"],
        "seed_lng": row["seed_lng"],
        "seed_lat": row["seed_lat"],
        "bounds": bounds,
        "watershed_geometry": watershed_geometry,
        "observation_zone_count": int(row.get("observation_zone_count") or 0),
        "field_note_count": int(row.get("field_note_count") or 0),
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


# Shared metadata columns. Full-precision watershed_geom is ONLY for get_project —
# list_projects uses a heavily simplified thumb geom so navigating back to the
# project picker never serializes multi-MB MultiPolygons (Cloudflare 502 risk).
_META_COLS = """
    p.id,
    p.name,
    p.owner_id,
    owner_u.name  AS owner_name,
    owner_u.email AS owner_email,
    p.watershed_id,
    p.watershed_name,
    p.seed_lng,
    p.seed_lat,
    p.created_at,
    p.updated_at,
    ST_AsGeoJSON(ST_Envelope(p.watershed_geom))::json AS bounds_geojson,
    (
        SELECT COUNT(*)::int
        FROM observation_zones oz
        WHERE oz.project_id = p.id
    ) AS observation_zone_count,
    (
        SELECT COUNT(*)::int
        FROM field_notes fn
        WHERE fn.project_id = p.id
    ) AS field_note_count
"""

# Tiny thumb for project cards — envelope only (never run SimplifyPreserveTopology
# on large MultiPolygons at list time; that can lock PostGIS under load).
_LIST_SELECT = f"""
    SELECT
        {_META_COLS},
        ST_AsGeoJSON(ST_Envelope(p.watershed_geom), 5)::json AS watershed_geojson
    FROM diagnosis p
    JOIN users owner_u ON owner_u.id = p.owner_id
"""

_DETAIL_SELECT = f"""
    SELECT
        {_META_COLS},
        ST_AsGeoJSON(
            ST_SimplifyPreserveTopology(p.watershed_geom, 0.00025),
            6
        )::json AS watershed_geojson
    FROM diagnosis p
    JOIN users owner_u ON owner_u.id = p.owner_id
"""

# Back-compat alias for create_project RETURNING / internal uses.
_SELECT = _DETAIL_SELECT


@router.get("")
def list_projects(user: dict = Depends(get_current_user)):
    with db_cursor() as cur:
        cur.execute(
            f"{_LIST_SELECT} WHERE {diagnosis_access_where('p')} ORDER BY created_at DESC",
            {"current_user_id": user["id"]},
        )
        rows = cur.fetchall()
    return {"projects": [_row_to_dict(r) for r in rows]}


@router.get("/{project_id}")
def get_project(project_id: str, user: dict = Depends(require_diagnosis_access)):
    with db_cursor() as cur:
        cur.execute(f"{_DETAIL_SELECT} WHERE p.id = %(id)s", {"id": project_id})
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Project not found")
    return _row_to_dict(row)


@router.post("", status_code=201)
async def create_project(body: ProjectCreate, user: dict = Depends(get_current_user)):
    import asyncio
    import logging

    log = logging.getLogger("uvicorn.error")

    def _build_row():
        # Prefer create_token from /watersheds/from-geometry — avoids re-running
        # GEOS on dense GP multipolygons (can crash the worker → CF Host 502).
        # Fall back to body.geometry when the token is missing (multi-host /tmp)
        # or expired — client always re-sends the already-validated preview geom.
        if body.create_token:
            try:
                watershed = load_stashed_custom_aoi(body.create_token)
            except ValueError:
                watershed = None
            if watershed is not None:
                if body.watershed_name:
                    watershed["watershed_name"] = (
                        body.watershed_name.strip()[:500] or watershed["watershed_name"]
                    )
                # Re-dissolve in case the stash predates the GP-union fix.
                try:
                    geom = _dissolve_custom_aoi(
                        parse_geojson_polygon(watershed["geometry"], repair=False)
                    )
                    watershed["geometry"] = _geojson_geom(geom)
                    watershed["bounds"] = list(geom.bounds)
                    centroid = geom.representative_point()
                    watershed["seed_lng"] = float(centroid.x)
                    watershed["seed_lat"] = float(centroid.y)
                except Exception:
                    pass
                seed_lng = body.lng if body.lng is not None else watershed["seed_lng"]
                seed_lat = body.lat if body.lat is not None else watershed["seed_lat"]
                return watershed, seed_lng, seed_lat
            if body.geometry is None:
                raise ValueError(
                    "Custom AOI create token expired or missing — re-upload the file"
                )

        if body.geometry is not None:
            # Client-supplied clip (village union or custom AOI) — validate, do not re-lookup.
            if body.source == "custom" or (body.watershed_id or "") == "custom":
                watershed = custom_aoi_from_geometry(body.geometry, name=body.watershed_name)
            else:
                from app.shared.watersheds import _geojson_geom, _simplify_for_storage

                geom = parse_geojson_polygon(body.geometry, repair=False)
                # Large multi-micro unions can stall PostGIS / CF if left unsimplified.
                geom = _simplify_for_storage(geom)
                if geom.is_empty:
                    raise ValueError("Watershed geometry is empty after simplify")
                centroid = geom.representative_point()
                watershed = {
                    "watershed_id": (body.watershed_id or f"union:geom").strip()[:500],
                    "watershed_name": (body.watershed_name or "Watershed union").strip()[:500],
                    "geometry": _geojson_geom(geom),
                    "bounds": list(geom.bounds),
                    "seed_lng": float(centroid.x),
                    "seed_lat": float(centroid.y),
                }
            seed_lng = body.lng if body.lng is not None else watershed["seed_lng"]
            seed_lat = body.lat if body.lat is not None else watershed["seed_lat"]
        else:
            watershed = lookup_watershed(body.lng, body.lat)
            seed_lng = body.lng
            seed_lat = body.lat
        return watershed, seed_lng, seed_lat

    try:
        watershed, seed_lng, seed_lat = await asyncio.wait_for(
            asyncio.to_thread(_build_row),
            timeout=20.0,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            503,
            "Project create timed out while preparing the AOI — simplify the boundary and retry.",
        ) from exc
    except ValueError as exc:
        # Token/geometry validation errors are client-fixable (400), not 404.
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        log.exception("Watershed resolve failed during project create")
        raise HTTPException(502, f"Watershed resolve failed: {exc}") from exc

    def _insert():
        # Minimal RETURNING — never ST_AsGeoJSON the full AOI here (CF HTML 502 risk).
        # Skip ST_MakeValid for custom AOIs: overlapping GP MultiPolygons can become
        # GeometryCollections or stall PostGIS on beta (CF HTML Host Error 502).
        # custom_aoi_from_geometry already dissolves to a valid Polygon/MultiPolygon.
        bounds = watershed.get("bounds")
        skip_make_valid = (
            body.source == "custom"
            or (watershed.get("watershed_id") or "") == "custom"
            or watershed.get("source") == "custom"
        )
        geom_sql = (
            "ST_SetSRID(ST_GeomFromGeoJSON(%(watershed_geom)s), 4326)"
            if skip_make_valid
            else "ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%(watershed_geom)s), 4326))"
        )
        with db_cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '15000'")
            cur.execute(
                f"""
                INSERT INTO diagnosis (
                    name, owner_id, watershed_id, watershed_name, watershed_geom, seed_lng, seed_lat
                )
                VALUES (
                    %(name)s,
                    %(owner_id)s,
                    %(watershed_id)s,
                    %(watershed_name)s,
                    ST_Multi(ST_CollectionExtract({geom_sql}, 3)),
                    %(seed_lng)s,
                    %(seed_lat)s
                )
                RETURNING id, created_at, updated_at
                """,
                {
                    "name": body.name.strip(),
                    "owner_id": user["id"],
                    "watershed_id": watershed["watershed_id"],
                    "watershed_name": watershed["watershed_name"],
                    "watershed_geom": json.dumps(watershed["geometry"]),
                    "seed_lng": seed_lng,
                    "seed_lat": seed_lat,
                },
            )
            row = cur.fetchone()
            return row, bounds

    try:
        row, bounds = await asyncio.wait_for(asyncio.to_thread(_insert), timeout=25.0)
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            503,
            "Project create timed out writing to the database — retry in a moment.",
        ) from exc
    except Exception as exc:
        log.exception("Project create insert failed")
        raise HTTPException(502, f"Project create failed: {exc}") from exc

    if body.create_token:
        try:
            from app.shared.watersheds import _aoi_cache_path

            _aoi_cache_path(body.create_token).unlink(missing_ok=True)
        except Exception:
            pass

    # Build the create response in Python (envelope thumb only). Full geom loads on get_project.
    if bounds and len(bounds) == 4:
        minx, miny, maxx, maxy = (float(v) for v in bounds)
        envelope = {
            "type": "Polygon",
            "coordinates": [[
                [minx, miny],
                [maxx, miny],
                [maxx, maxy],
                [minx, maxy],
                [minx, miny],
            ]],
        }
    else:
        envelope = watershed.get("geometry")
        bounds = None

    return {
        "id": str(row["id"]),
        "name": body.name.strip(),
        "owner_id": str(user["id"]),
        "owner_name": user.get("name") or "",
        "owner_email": user.get("email") or "",
        "watershed_id": watershed["watershed_id"],
        "watershed_name": watershed["watershed_name"],
        "seed_lng": seed_lng,
        "seed_lat": seed_lat,
        "bounds": bounds,
        "watershed_geometry": envelope,
        "observation_zone_count": 0,
        "field_note_count": 0,
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, user: dict = Depends(require_diagnosis_owner)):
    with db_cursor() as cur:
        cur.execute(
            "SELECT photo_path FROM field_notes WHERE project_id = %(id)s AND photo_path IS NOT NULL",
            {"id": project_id},
        )
        legacy_photo_paths = [
            row["photo_path"]
            for row in cur.fetchall()
            if row["photo_path"] and row["photo_path"].startswith("photos/")
        ]
        cur.execute("DELETE FROM diagnosis WHERE id = %(id)s RETURNING id", {"id": project_id})
        if not cur.fetchone():
            raise HTTPException(404, "Project not found")

    for photo_path in legacy_photo_paths:
        local = Path(settings.packages_dir) / "photos" / Path(photo_path).name
        if local.is_file():
            local.unlink()

    s3_storage.delete_project_storage(project_id)


# --- Sharing: owner or diagnosis-admin management of user/org grants ---


@router.get("/{project_id}/access/users")
def list_user_access(project_id: str, user: dict = Depends(require_diagnosis_admin)):
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT u.id, u.email, u.name, du.role, du.created_at
            FROM diagnosis_users du
            JOIN users u ON u.id = du.user_id
            WHERE du.diagnosis_id = %(id)s
            ORDER BY du.created_at ASC
            """,
            {"id": project_id},
        )
        rows = cur.fetchall()
    return {
        "users": [
            {
                "id": str(r["id"]),
                "email": r["email"],
                "name": r["name"],
                "role": r["role"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
    }


@router.post("/{project_id}/access/users", status_code=201)
def add_user_access(project_id: str, body: AddUserAccess, user: dict = Depends(require_diagnosis_admin)):
    email = body.email.lower().strip()
    with db_cursor() as cur:
        cur.execute("SELECT id, email, name FROM users WHERE email = %(email)s", {"email": email})
        target = cur.fetchone()
        if not target:
            raise HTTPException(404, "No account found with that email")
        if str(target["id"]) == str(user["id"]):
            raise HTTPException(400, "You already have access to this project")

        cur.execute(
            """
            INSERT INTO diagnosis_users (diagnosis_id, user_id, role, added_by)
            VALUES (%(diagnosis_id)s, %(user_id)s, %(role)s, %(added_by)s)
            ON CONFLICT (diagnosis_id, user_id) DO NOTHING
            RETURNING diagnosis_id
            """,
            {"diagnosis_id": project_id, "user_id": target["id"], "role": body.role, "added_by": user["id"]},
        )
        if not cur.fetchone():
            raise HTTPException(409, "That user already has access to this project")
    return {"id": str(target["id"]), "email": target["email"], "name": target["name"], "role": body.role}


@router.delete("/{project_id}/access/users/{user_id}", status_code=204)
def remove_user_access(project_id: str, user_id: str, user: dict = Depends(require_diagnosis_admin)):
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM diagnosis_users WHERE diagnosis_id = %(diagnosis_id)s AND user_id = %(user_id)s RETURNING user_id",
            {"diagnosis_id": project_id, "user_id": user_id},
        )
        if not cur.fetchone():
            raise HTTPException(404, "That user does not have access to this project")


@router.patch("/{project_id}/access/users/{user_id}/role")
def update_user_role(
    project_id: str, user_id: str, body: UpdateUserRole, user: dict = Depends(require_diagnosis_admin)
):
    with db_cursor() as cur:
        cur.execute(
            """
            UPDATE diagnosis_users SET role = %(role)s
            WHERE diagnosis_id = %(diagnosis_id)s AND user_id = %(user_id)s
            RETURNING user_id
            """,
            {"diagnosis_id": project_id, "user_id": user_id, "role": body.role},
        )
        if not cur.fetchone():
            raise HTTPException(404, "That user does not have access to this project")
    return {"id": user_id, "role": body.role}


@router.get("/{project_id}/access/orgs")
def list_org_access(project_id: str, user: dict = Depends(require_diagnosis_admin)):
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT o.id, o.name, dorg.created_at
            FROM diagnosis_orgs dorg
            JOIN organizations o ON o.id = dorg.org_id
            WHERE dorg.diagnosis_id = %(id)s
            ORDER BY dorg.created_at ASC
            """,
            {"id": project_id},
        )
        rows = cur.fetchall()
    return {
        "organizations": [
            {"id": str(r["id"]), "name": r["name"], "created_at": r["created_at"].isoformat()} for r in rows
        ]
    }


@router.post("/{project_id}/access/orgs", status_code=201)
def add_org_access(project_id: str, body: AddOrgAccess, user: dict = Depends(require_diagnosis_admin)):
    with db_cursor() as cur:
        # Owner may only grant access to orgs they themselves belong to.
        cur.execute(
            """
            SELECT o.id, o.name
            FROM organizations o
            JOIN org_members om ON om.org_id = o.id
            WHERE o.id = %(org_id)s AND om.user_id = %(user_id)s
            """,
            {"org_id": str(body.org_id), "user_id": user["id"]},
        )
        org = cur.fetchone()
        if not org:
            raise HTTPException(404, "Organization not found, or you are not a member of it")

        cur.execute(
            """
            INSERT INTO diagnosis_orgs (diagnosis_id, org_id, added_by)
            VALUES (%(diagnosis_id)s, %(org_id)s, %(added_by)s)
            ON CONFLICT (diagnosis_id, org_id) DO NOTHING
            RETURNING diagnosis_id
            """,
            {"diagnosis_id": project_id, "org_id": str(body.org_id), "added_by": user["id"]},
        )
        if not cur.fetchone():
            raise HTTPException(409, "That organization already has access to this project")
    return {"id": str(org["id"]), "name": org["name"]}


@router.delete("/{project_id}/access/orgs/{org_id}", status_code=204)
def remove_org_access(project_id: str, org_id: str, user: dict = Depends(require_diagnosis_admin)):
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM diagnosis_orgs WHERE diagnosis_id = %(diagnosis_id)s AND org_id = %(org_id)s RETURNING org_id",
            {"diagnosis_id": project_id, "org_id": org_id},
        )
        if not cur.fetchone():
            raise HTTPException(404, "That organization does not have access to this project")


def _load_zones_for_pdf(project_id: str) -> list[dict]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, text, observations, questions, color,
                   ST_AsGeoJSON(geom)::json AS geometry
            FROM observation_zones
            WHERE project_id = %(project_id)s
            ORDER BY created_at ASC
            """,
            {"project_id": project_id},
        )
        return [
            {
                "id": str(r["id"]),
                "text": r.get("text") or "",
                "observations": r.get("observations") or "",
                "questions": r.get("questions") or "",
                "color": r.get("color") or "",
                "geometry": r.get("geometry"),
            }
            for r in cur.fetchall()
        ]


def _load_hypotheses_for_pdf(project_id: str) -> list[dict]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, hypothesis, root_cause, status, created_at
            FROM hypotheses
            WHERE project_id = %(project_id)s
            ORDER BY created_at ASC
            """,
            {"project_id": project_id},
        )
        rows = cur.fetchall()
        out = []
        for row in rows:
            hid = str(row["id"])
            cur.execute(
                "SELECT zone_id FROM hypothesis_observation_zones WHERE hypothesis_id = %(id)s",
                {"id": hid},
            )
            zone_ids = [str(r["zone_id"]) for r in cur.fetchall()]
            cur.execute(
                "SELECT COUNT(*)::int AS n FROM field_notes WHERE hypothesis_id = %(id)s",
                {"id": hid},
            )
            note_count = cur.fetchone()["n"]
            out.append(
                {
                    "id": hid,
                    "hypothesis": row.get("hypothesis") or "",
                    "root_cause": row.get("root_cause") or "",
                    "status": row.get("status") or "untested",
                    "observation_zone_ids": zone_ids,
                    "field_note_count": note_count,
                }
            )
        return out


def _reports_dir(project_id: str) -> Path:
    from app.shared.config import settings

    return Path(settings.packages_dir) / project_id / "reports"


def _run_atlas_export(project_id: str, progress: PackageProgress) -> dict:
    """Build atlas PDF on disk; return download metadata for SSE done event."""
    import re

    from app.modules.diagnose.services.diagnosis_atlas import build_atlas_pdf

    with db_cursor() as cur:
        cur.execute(f"{_DETAIL_SELECT} WHERE p.id = %(id)s", {"id": project_id})
        row = cur.fetchone()
    if not row:
        raise ValueError("Project not found")

    project = _row_to_dict(row)
    if not project.get("watershed_geometry"):
        raise ValueError("Project has no watershed geometry")

    zones = _load_zones_for_pdf(project_id)
    hypotheses = _load_hypotheses_for_pdf(project_id)

    safe = re.sub(r"[^\w\-]+", "_", (project.get("name") or "diagnosis").strip())[:60] or "diagnosis"
    filename = f"Diagnosis_Dashboard_{safe}.pdf"
    out_dir = _reports_dir(project_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / filename

    build_atlas_pdf(
        project=project,
        observation_zones=zones,
        hypotheses=hypotheses,
        output_path=out_path,
        progress=progress,
    )
    return {
        "filename": filename,
        "download_path": filename,
        "project_id": project_id,
        "message": f"Diagnosis atlas PDF ready ({filename}).",
    }


@router.post("/{project_id}/export-pdf/stream")
async def export_diagnosis_pdf_stream(
    project_id: str, user: dict = Depends(require_diagnosis_access)
):
    """Stream atlas PDF build progress (SSE), then download via /export-pdf/download."""
    import asyncio
    import json
    from datetime import UTC, datetime

    from fastapi.responses import StreamingResponse

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_progress(percent: int, message: str) -> None:
        loop.call_soon_threadsafe(
            queue.put_nowait,
            {
                "type": "progress",
                "percent": percent,
                "message": message,
                "time": datetime.now(UTC).isoformat(),
            },
        )

    async def run_export() -> None:
        progress = PackageProgress(on_event=on_progress)
        try:
            result = await loop.run_in_executor(
                None,
                lambda: _run_atlas_export(project_id, progress),
            )
            await queue.put({"type": "done", "percent": 100, "result": result})
        except ValueError as exc:
            await queue.put({"type": "error", "message": str(exc)})
        except Exception as exc:
            await queue.put({"type": "error", "message": f"PDF export failed: {exc}"})

    async def event_stream():
        task = asyncio.create_task(run_export())
        try:
            while True:
                item = await queue.get()
                yield f"data: {json.dumps(item)}\n\n"
                if item.get("type") in ("done", "error"):
                    break
        finally:
            await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{project_id}/export-pdf/download")
def download_diagnosis_pdf(
    project_id: str,
    file: str = Query(..., min_length=1, max_length=200),
    user: dict = Depends(require_diagnosis_access),
):
    """Download a previously generated atlas PDF for this project."""
    from fastapi.responses import FileResponse

    # Confine to reports dir — no path traversal
    safe = Path(file).name
    if not safe.lower().endswith(".pdf") or safe != file:
        raise HTTPException(400, "Invalid file name")
    path = _reports_dir(project_id) / safe
    if not path.is_file():
        raise HTTPException(404, "PDF not found — export again")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=safe,
        headers={"Cache-Control": "private, no-store"},
    )


@router.post("/{project_id}/export-pdf")
async def export_diagnosis_pdf(project_id: str, user: dict = Depends(require_diagnosis_access)):
    """Deprecated blocking export — prefer /export-pdf/stream. Still builds the atlas PDF."""
    import asyncio

    from fastapi.responses import FileResponse

    try:
        result = await asyncio.to_thread(_run_atlas_export, project_id, PackageProgress())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"PDF export failed: {exc}") from exc

    path = _reports_dir(project_id) / result["filename"]
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=result["filename"],
    )
