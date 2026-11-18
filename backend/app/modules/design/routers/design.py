"""Design module API: saved AOIs and solution site-suitability.

Design owns its own table (`design_projects`), separate from Diagnose's
`diagnosis`. An AOI comes either from the same place-selection flows as PD
(point → micro-watershed, village, custom upload — resolved client-side via the
/api/diagnose/watersheds endpoints) or is imported from a PD project the user
can access.
"""

from __future__ import annotations

import gzip
import json
import logging
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, model_validator

from app.modules.design.services.solutions_catalog import get_solution, load_solutions
from app.modules.design.services.suitability import (
    SuitabilityInputError,
    aoi_stats,
    inspect_point,
    rank_solutions,
    solution_geojson,
)
from app.shared.access import assert_diagnosis_access, diagnosis_access_where, require_design_owner
from app.shared.auth import get_current_user
from app.shared.database import db_cursor

router = APIRouter()
log = logging.getLogger("uvicorn.error")

AoiSource = Literal["point", "village", "custom", "diagnosis"]


class DesignProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    source: AoiSource = "point"
    source_diagnosis_id: UUID | None = None
    geometry: dict[str, Any] | None = None
    create_token: str | None = Field(default=None, max_length=128)
    aoi_name: str | None = Field(default=None, max_length=500)
    lng: float | None = Field(default=None, ge=-180, le=180)
    lat: float | None = Field(default=None, ge=-90, le=90)

    @model_validator(mode="after")
    def require_aoi(self):
        if self.source == "diagnosis":
            if not self.source_diagnosis_id:
                raise ValueError("source_diagnosis_id is required when importing from a PD project")
            return self
        has_point = self.lng is not None and self.lat is not None
        if self.geometry is None and not self.create_token and not has_point:
            raise ValueError("Provide geometry, create_token, or lng/lat")
        return self


# --------------------------------------------------------------------------- SQL

_META_COLS = """
    p.id, p.name, p.owner_id, p.aoi_name, p.aoi_source, p.source_diagnosis_id,
    d.name AS source_diagnosis_name,
    p.seed_lng, p.seed_lat, p.created_at, p.updated_at,
    ST_AsGeoJSON(ST_Envelope(p.aoi_geom))::json AS bounds_geojson,
    ROUND((ST_Area(p.aoi_geom::geography) / 10000)::numeric, 1)::float AS area_ha
"""

_LIST_SELECT = f"""
    SELECT {_META_COLS},
           ST_AsGeoJSON(ST_SimplifyPreserveTopology(p.aoi_geom, 0.002), 5)::json AS aoi_geojson
    FROM design_projects p
    LEFT JOIN diagnosis d ON d.id = p.source_diagnosis_id
"""

_DETAIL_SELECT = f"""
    SELECT {_META_COLS},
           ST_AsGeoJSON(p.aoi_geom, 6)::json AS aoi_geojson
    FROM design_projects p
    LEFT JOIN diagnosis d ON d.id = p.source_diagnosis_id
"""


def _bounds(row: dict) -> list[float] | None:
    gj = row.get("bounds_geojson")
    if not gj:
        return None
    if gj.get("type") == "Point":
        x, y = gj["coordinates"]
        return [x, y, x, y]
    coords = gj["coordinates"][0]
    xs, ys = [c[0] for c in coords], [c[1] for c in coords]
    return [min(xs), min(ys), max(xs), max(ys)]


def _row_to_dict(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "owner_id": str(row["owner_id"]),
        "aoi_name": row["aoi_name"],
        "aoi_source": row["aoi_source"],
        "source_diagnosis_id": str(row["source_diagnosis_id"]) if row["source_diagnosis_id"] else None,
        "source_diagnosis_name": row.get("source_diagnosis_name"),
        "seed_lng": row["seed_lng"],
        "seed_lat": row["seed_lat"],
        "bounds": _bounds(row),
        "area_ha": row.get("area_ha"),
        "aoi_geometry": row.get("aoi_geojson"),
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


def _load_aoi(project_id: str) -> dict:
    with db_cursor() as cur:
        cur.execute(
            "SELECT ST_AsGeoJSON(aoi_geom, 7)::json AS g FROM design_projects WHERE id = %(id)s",
            {"id": project_id},
        )
        row = cur.fetchone()
    if not row or not row["g"]:
        raise HTTPException(404, "Project not found")
    return row["g"]


# --------------------------------------------------------------------------- AOI resolution


def _resolve_aoi(body: DesignProjectCreate, user: dict) -> tuple[dict, str, float, float]:
    """Return (geometry, aoi_name, seed_lng, seed_lat) for the requested source."""
    from app.shared.watersheds import (
        _geojson_geom,
        _simplify_for_storage,
        custom_aoi_from_geometry,
        load_stashed_custom_aoi,
        lookup_watershed,
        parse_geojson_polygon,
    )

    if body.source == "diagnosis":
        diag_id = str(body.source_diagnosis_id)
        assert_diagnosis_access(user["id"], diag_id)
        with db_cursor() as cur:
            cur.execute(
                """
                SELECT name, watershed_name, seed_lng, seed_lat,
                       ST_AsGeoJSON(watershed_geom, 7)::json AS g
                FROM diagnosis WHERE id = %(id)s
                """,
                {"id": diag_id},
            )
            row = cur.fetchone()
        if not row or not row["g"]:
            raise ValueError("The PD project has no AOI geometry")
        name = body.aoi_name or row["watershed_name"] or row["name"]
        return row["g"], name, row["seed_lng"], row["seed_lat"]

    ws: dict | None = None
    if body.create_token:
        try:
            ws = load_stashed_custom_aoi(body.create_token)
        except ValueError:
            ws = None
    if ws is None and body.geometry is not None:
        if body.source == "custom":
            ws = custom_aoi_from_geometry(body.geometry, name=body.aoi_name)
        else:
            geom = _simplify_for_storage(parse_geojson_polygon(body.geometry, repair=False))
            if geom.is_empty:
                raise ValueError("AOI geometry is empty after simplify")
            c = geom.representative_point()
            ws = {
                "geometry": _geojson_geom(geom),
                "watershed_name": body.aoi_name or "Selected area",
                "seed_lng": float(c.x),
                "seed_lat": float(c.y),
            }
    if ws is None:
        if body.lng is None or body.lat is None:
            raise ValueError("AOI create token expired — re-select the area")
        ws = lookup_watershed(body.lng, body.lat)
    name = (body.aoi_name or ws.get("watershed_name") or "").strip()[:500]
    lng = body.lng if body.lng is not None else ws["seed_lng"]
    lat = body.lat if body.lat is not None else ws["seed_lat"]
    return ws["geometry"], name, lng, lat


# --------------------------------------------------------------------------- routes


@router.get("/status")
def design_status():
    return {"module": "design", "status": "ok"}


@router.get("/solutions")
def list_solution_catalog(user: dict = Depends(get_current_user)):
    """The solution catalog (site_suitability.csv) without AOI metrics."""
    return {"solutions": [s.to_dict() for s in load_solutions()]}


@router.get("/importable-aoi")
def list_importable_aoi(user: dict = Depends(get_current_user)):
    """PD projects the user can access, for 'import AOI from PD project'."""
    with db_cursor() as cur:
        cur.execute(
            f"""
            SELECT d.id, d.name, d.watershed_name, d.created_at,
                   ST_AsGeoJSON(ST_Envelope(d.watershed_geom))::json AS bounds_geojson,
                   ROUND((ST_Area(d.watershed_geom::geography) / 10000)::numeric, 1)::float AS area_ha
            FROM diagnosis d
            WHERE d.watershed_geom IS NOT NULL AND {diagnosis_access_where('d')}
            ORDER BY d.updated_at DESC
            """,
            {"current_user_id": user["id"]},
        )
        rows = cur.fetchall()
    return {
        "projects": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "watershed_name": r["watershed_name"],
                "area_ha": r["area_ha"],
                "bounds": _bounds(r),
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
    }


@router.get("/importable-aoi/{diagnosis_id}")
def get_importable_aoi(diagnosis_id: UUID, user: dict = Depends(get_current_user)):
    """Preview geometry of one PD project's AOI (simplified)."""
    diagnosis_id = str(diagnosis_id)
    assert_diagnosis_access(user["id"], diagnosis_id)
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT name, watershed_name,
                   ST_AsGeoJSON(ST_SimplifyPreserveTopology(watershed_geom, 0.00025), 6)::json AS g
            FROM diagnosis WHERE id = %(id)s
            """,
            {"id": diagnosis_id},
        )
        row = cur.fetchone()
    if not row or not row["g"]:
        raise HTTPException(404, "PD project has no AOI")
    return {"id": diagnosis_id, "name": row["name"], "watershed_name": row["watershed_name"], "geometry": row["g"]}


@router.get("/projects")
def list_projects(user: dict = Depends(get_current_user)):
    with db_cursor() as cur:
        cur.execute(
            f"{_LIST_SELECT} WHERE p.owner_id = %(uid)s ORDER BY p.updated_at DESC",
            {"uid": user["id"]},
        )
        rows = cur.fetchall()
    return {"projects": [_row_to_dict(r) for r in rows]}


@router.post("/projects", status_code=201)
def create_project(body: DesignProjectCreate, user: dict = Depends(get_current_user)):
    try:
        geometry, aoi_name, lng, lat = _resolve_aoi(body, user)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("Design AOI resolve failed")
        raise HTTPException(502, f"AOI resolve failed: {exc}") from exc

    with db_cursor() as cur:
        cur.execute("SET LOCAL statement_timeout = '15000'")
        cur.execute(
            """
            INSERT INTO design_projects
                (name, owner_id, aoi_name, aoi_geom, aoi_source, source_diagnosis_id, seed_lng, seed_lat)
            VALUES (
                %(name)s, %(owner_id)s, %(aoi_name)s,
                ST_Multi(ST_CollectionExtract(ST_MakeValid(
                    ST_Force2D(ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326))), 3)),
                %(source)s, %(diag)s, %(lng)s, %(lat)s
            )
            RETURNING id
            """,
            {
                "name": body.name.strip(),
                "owner_id": user["id"],
                "aoi_name": aoi_name,
                "geom": json.dumps(geometry),
                "source": body.source,
                "diag": str(body.source_diagnosis_id) if body.source == "diagnosis" else None,
                "lng": lng,
                "lat": lat,
            },
        )
        new_id = cur.fetchone()["id"]
        cur.execute(f"{_LIST_SELECT} WHERE p.id = %(id)s", {"id": new_id})
        row = cur.fetchone()

    if body.create_token:
        try:
            from app.shared.watersheds import _aoi_cache_path

            _aoi_cache_path(body.create_token).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
    return _row_to_dict(row)


@router.get("/projects/{project_id}")
def get_project(project_id: str, user: dict = Depends(require_design_owner)):
    with db_cursor() as cur:
        cur.execute(f"{_DETAIL_SELECT} WHERE p.id = %(id)s", {"id": project_id})
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Project not found")
    return _row_to_dict(row)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, user: dict = Depends(require_design_owner)):
    with db_cursor() as cur:
        cur.execute("DELETE FROM design_projects WHERE id = %(id)s", {"id": project_id})


@router.get("/projects/{project_id}/solutions")
def project_solutions(project_id: str, user: dict = Depends(require_design_owner)):
    """Catalog solutions with suitability metrics for the AOI, most feasible first."""
    aoi = _load_aoi(project_id)
    try:
        return rank_solutions(aoi)
    except SuitabilityInputError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/projects/{project_id}/stats")
def project_stats(project_id: str, user: dict = Depends(require_design_owner)):
    """Watershed-level stats for the AOI from the slope, LULC and drainage layers."""
    aoi = _load_aoi(project_id)
    try:
        return aoi_stats(aoi)
    except SuitabilityInputError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/projects/{project_id}/solutions/{solution_id}/geojson")
def project_solution_geojson(
    project_id: str, solution_id: str, request: Request, user: dict = Depends(require_design_owner)
):
    sol = get_solution(solution_id)
    if sol is None:
        raise HTTPException(404, "Unknown solution")
    aoi = _load_aoi(project_id)
    try:
        fc = solution_geojson(aoi, sol)
    except SuitabilityInputError as exc:
        raise HTTPException(503, str(exc)) from exc
    # Layers run to several MB of coordinates; gzip cuts the transfer ~4-5x.
    body = json.dumps(fc, separators=(",", ":")).encode()
    headers = {"Vary": "Accept-Encoding"}
    if "gzip" in request.headers.get("accept-encoding", "").lower():
        body = gzip.compress(body, compresslevel=5)
        headers["Content-Encoding"] = "gzip"
    return Response(body, media_type="application/json", headers=headers)


@router.get("/projects/{project_id}/inspect")
def project_inspect_point(
    project_id: str,
    solution_id: str = Query(..., max_length=200),
    lng: float = Query(..., ge=-180, le=180),
    lat: float = Query(..., ge=-90, le=90),
    user: dict = Depends(require_design_owner),
):
    """How one map location measures against a solution's criteria (for click popups)."""
    sol = get_solution(solution_id)
    if sol is None:
        raise HTTPException(404, "Unknown solution")
    aoi = _load_aoi(project_id)
    try:
        return inspect_point(aoi, sol, lng, lat)
    except SuitabilityInputError as exc:
        raise HTTPException(503, str(exc)) from exc
