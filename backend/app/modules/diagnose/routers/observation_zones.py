import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from geojson_pydantic import Feature, FeatureCollection
from pydantic import BaseModel, Field

from app.shared.access import assert_diagnosis_access
from app.shared.auth import get_current_user
from app.shared.database import db_cursor

router = APIRouter()

_TEXT_MAX = 10_000

_SELECT = """
    SELECT id, project_id, text, observations, questions, color, created_at, updated_at, created_by,
           ST_AsGeoJSON(geom)::json AS geojson
    FROM observation_zones
"""


class ObservationZoneCreate(BaseModel):
    project_id: UUID
    geometry: dict
    text: str = Field(default="", max_length=_TEXT_MAX)
    observations: str = Field(default="", max_length=_TEXT_MAX)
    questions: str = Field(default="", max_length=_TEXT_MAX)
    color: str = Field(default="#0d983b", max_length=32)


class ObservationZoneUpdate(BaseModel):
    geometry: dict | None = None
    text: str | None = Field(default=None, max_length=_TEXT_MAX)
    observations: str | None = Field(default=None, max_length=_TEXT_MAX)
    questions: str | None = Field(default=None, max_length=_TEXT_MAX)
    color: str | None = Field(default=None, max_length=32)


def _parse_geojson(value) -> dict:
    if isinstance(value, dict):
        return value
    return json.loads(value)


def _row_to_feature(row: dict) -> Feature:
    return Feature(
        type="Feature",
        id=str(row["id"]),
        geometry=_parse_geojson(row["geojson"]),
        properties={
            "project_id": str(row["project_id"]),
            "text": row["text"],
            "observations": row.get("observations") or "",
            "questions": row.get("questions") or "",
            "color": row.get("color") or "#0d983b",
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
            "created_by": row["created_by"],
        },
    )


def _zone_project_id(cur, zone_id: str) -> str:
    cur.execute("SELECT project_id FROM observation_zones WHERE id = %(id)s", {"id": zone_id})
    row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Observation zone not found")
    return str(row["project_id"])


@router.get("", response_model=FeatureCollection)
def list_observation_zones(project_id: str = Query(...), user: dict = Depends(get_current_user)):
    assert_diagnosis_access(user["id"], project_id)
    with db_cursor() as cur:
        cur.execute(
            f"{_SELECT} WHERE project_id = %(project_id)s ORDER BY created_at DESC",
            {"project_id": project_id},
        )
        rows = cur.fetchall()
    return FeatureCollection(type="FeatureCollection", features=[_row_to_feature(r) for r in rows])


@router.post("", response_model=Feature, status_code=201)
def create_observation_zone(body: ObservationZoneCreate, user: dict = Depends(get_current_user)):
    project_id = str(body.project_id)
    assert_diagnosis_access(user["id"], project_id)
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO observation_zones (project_id, geom, text, observations, questions, color, created_by)
            VALUES (
                %(project_id)s,
                ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326),
                %(text)s,
                %(observations)s,
                %(questions)s,
                %(color)s,
                %(created_by)s
            )
            RETURNING id, project_id, text, observations, questions, color, created_at, updated_at, created_by,
                      ST_AsGeoJSON(geom)::json AS geojson
            """,
            {
                "project_id": project_id,
                "geojson": json.dumps(body.geometry),
                "text": body.text,
                "observations": body.observations,
                "questions": body.questions,
                "color": body.color,
                "created_by": str(user["id"]),
            },
        )
        row = cur.fetchone()
    return _row_to_feature(row)


@router.patch("/{zone_id}", response_model=Feature)
def update_observation_zone(zone_id: str, body: ObservationZoneUpdate, user: dict = Depends(get_current_user)):
    sets = []
    params: dict = {"id": zone_id}
    if body.text is not None:
        sets.append("text = %(text)s")
        params["text"] = body.text
    if body.observations is not None:
        sets.append("observations = %(observations)s")
        params["observations"] = body.observations
    if body.questions is not None:
        sets.append("questions = %(questions)s")
        params["questions"] = body.questions
    if body.color is not None:
        sets.append("color = %(color)s")
        params["color"] = body.color
    if body.geometry is not None:
        sets.append("geom = ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326)")
        params["geojson"] = json.dumps(body.geometry)
    if not sets:
        raise HTTPException(400, "No fields to update")

    with db_cursor() as cur:
        assert_diagnosis_access(user["id"], _zone_project_id(cur, zone_id))
        cur.execute(
            f"""
            UPDATE observation_zones SET {", ".join(sets)}
            WHERE id = %(id)s
            RETURNING id, project_id, text, observations, questions, color, created_at, updated_at, created_by,
                      ST_AsGeoJSON(geom)::json AS geojson
            """,
            params,
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Observation zone not found")
    return _row_to_feature(row)


@router.delete("/{zone_id}", status_code=204)
def delete_observation_zone(zone_id: str, user: dict = Depends(get_current_user)):
    with db_cursor() as cur:
        assert_diagnosis_access(user["id"], _zone_project_id(cur, zone_id))
        cur.execute("DELETE FROM observation_zones WHERE id = %s RETURNING id", (zone_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Observation zone not found")
