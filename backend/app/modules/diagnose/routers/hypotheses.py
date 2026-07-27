"""Hypotheses: create, link to observation zones, validate with field-note evidence."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.shared.access import assert_diagnosis_access
from app.shared.auth import get_current_user
from app.shared.database import db_cursor

router = APIRouter()

VALID_STATUSES = frozenset({"untested", "validated", "invalidated", "discarded"})
EVIDENCE_STATUSES = frozenset({"validated", "invalidated"})


class HypothesisCreate(BaseModel):
    project_id: str
    hypothesis: str = Field(min_length=1)
    observation_zone_ids: list[str] = Field(default_factory=list)


class HypothesisUpdate(BaseModel):
    hypothesis: str | None = None
    root_cause: str | None = None
    status: str | None = None
    observation_zone_ids: list[str] | None = None


def _row_to_dict(row: dict, zone_ids: list[str], field_note_count: int) -> dict:
    return {
        "id": str(row["id"]),
        "project_id": str(row["project_id"]),
        "hypothesis": row["hypothesis"],
        "root_cause": row["root_cause"],
        "status": row["status"],
        "observation_zone_ids": zone_ids,
        "field_note_count": field_note_count,
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


def _hypothesis_project_id(cur, hypothesis_id: str) -> str:
    cur.execute("SELECT project_id FROM hypotheses WHERE id = %(id)s", {"id": hypothesis_id})
    row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Hypothesis not found")
    return str(row["project_id"])


def _fetch_zone_ids(cur, hypothesis_id: str) -> list[str]:
    cur.execute(
        "SELECT zone_id FROM hypothesis_observation_zones WHERE hypothesis_id = %(id)s",
        {"id": hypothesis_id},
    )
    return [str(r["zone_id"]) for r in cur.fetchall()]


def _fetch_field_note_count(cur, hypothesis_id: str) -> int:
    cur.execute(
        "SELECT COUNT(*)::int AS n FROM field_notes WHERE hypothesis_id = %(id)s",
        {"id": hypothesis_id},
    )
    return cur.fetchone()["n"]


def _validate_zone_ids(cur, project_id: str, zone_ids: list[str]) -> None:
    if not zone_ids:
        return
    cur.execute(
        """
        SELECT id FROM observation_zones
        WHERE project_id = %(project_id)s AND id = ANY(%(zone_ids)s::uuid[])
        """,
        {"project_id": project_id, "zone_ids": zone_ids},
    )
    found = {str(r["id"]) for r in cur.fetchall()}
    missing = [z for z in zone_ids if z not in found]
    if missing:
        raise HTTPException(400, f"Observation zone(s) not in this project: {', '.join(missing)}")


def _set_zone_links(cur, hypothesis_id: str, zone_ids: list[str]) -> None:
    cur.execute(
        "DELETE FROM hypothesis_observation_zones WHERE hypothesis_id = %(id)s",
        {"id": hypothesis_id},
    )
    for zone_id in zone_ids:
        cur.execute(
            """
            INSERT INTO hypothesis_observation_zones (hypothesis_id, zone_id)
            VALUES (%(hypothesis_id)s, %(zone_id)s)
            """,
            {"hypothesis_id": hypothesis_id, "zone_id": zone_id},
        )


@router.get("")
def list_hypotheses(project_id: str = Query(...), user: dict = Depends(get_current_user)):
    assert_diagnosis_access(user["id"], project_id)
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, project_id, hypothesis, root_cause, status, created_at, updated_at
            FROM hypotheses
            WHERE project_id = %(project_id)s
            ORDER BY created_at DESC
            """,
            {"project_id": project_id},
        )
        rows = cur.fetchall()
        result = []
        for row in rows:
            hid = str(row["id"])
            zone_ids = _fetch_zone_ids(cur, hid)
            note_count = _fetch_field_note_count(cur, hid)
            result.append(_row_to_dict(row, zone_ids, note_count))
    return {"hypotheses": result}


@router.get("/{hypothesis_id}")
def get_hypothesis(hypothesis_id: str, user: dict = Depends(get_current_user)):
    with db_cursor() as cur:
        project_id = _hypothesis_project_id(cur, hypothesis_id)
        assert_diagnosis_access(user["id"], project_id)
        cur.execute(
            """
            SELECT id, project_id, hypothesis, root_cause, status, created_at, updated_at
            FROM hypotheses WHERE id = %(id)s
            """,
            {"id": hypothesis_id},
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Hypothesis not found")
        zone_ids = _fetch_zone_ids(cur, hypothesis_id)
        note_count = _fetch_field_note_count(cur, hypothesis_id)
    return _row_to_dict(row, zone_ids, note_count)


@router.post("", status_code=201)
def create_hypothesis(body: HypothesisCreate, user: dict = Depends(get_current_user)):
    assert_diagnosis_access(user["id"], body.project_id)
    with db_cursor() as cur:
        _validate_zone_ids(cur, body.project_id, body.observation_zone_ids)
        cur.execute(
            """
            INSERT INTO hypotheses (project_id, hypothesis, created_by)
            VALUES (%(project_id)s, %(hypothesis)s, %(created_by)s)
            RETURNING id, project_id, hypothesis, root_cause, status, created_at, updated_at
            """,
            {
                "project_id": body.project_id,
                "hypothesis": body.hypothesis.strip(),
                "created_by": user["id"],
            },
        )
        row = cur.fetchone()
        hid = str(row["id"])
        _set_zone_links(cur, hid, body.observation_zone_ids)
        zone_ids = _fetch_zone_ids(cur, hid)
    return _row_to_dict(row, zone_ids, 0)


@router.patch("/{hypothesis_id}")
def update_hypothesis(hypothesis_id: str, body: HypothesisUpdate, user: dict = Depends(get_current_user)):
    with db_cursor() as cur:
        project_id = _hypothesis_project_id(cur, hypothesis_id)
        assert_diagnosis_access(user["id"], project_id)

        if body.status is not None and body.status not in VALID_STATUSES:
            raise HTTPException(400, f"Invalid status. Must be one of: {', '.join(sorted(VALID_STATUSES))}")

        if body.status in EVIDENCE_STATUSES:
            note_count = _fetch_field_note_count(cur, hypothesis_id)
            if note_count == 0:
                raise HTTPException(
                    400,
                    "At least one field note must be linked before validating or invalidating a hypothesis",
                )

        if body.observation_zone_ids is not None:
            _validate_zone_ids(cur, project_id, body.observation_zone_ids)

        sets = []
        params: dict = {"id": hypothesis_id}
        if body.hypothesis is not None:
            if not body.hypothesis.strip():
                raise HTTPException(400, "Hypothesis text cannot be empty")
            sets.append("hypothesis = %(hypothesis)s")
            params["hypothesis"] = body.hypothesis.strip()
        if body.root_cause is not None:
            note_count = _fetch_field_note_count(cur, hypothesis_id)
            if note_count == 0 and body.root_cause.strip():
                raise HTTPException(
                    400,
                    "Link at least one field note before adding a root cause",
                )
            sets.append("root_cause = %(root_cause)s")
            params["root_cause"] = body.root_cause.strip()
        if body.status is not None:
            sets.append("status = %(status)s")
            params["status"] = body.status

        if sets:
            cur.execute(
                f"UPDATE hypotheses SET {', '.join(sets)} WHERE id = %(id)s RETURNING id",
                params,
            )
            if not cur.fetchone():
                raise HTTPException(404, "Hypothesis not found")

        if body.observation_zone_ids is not None:
            _set_zone_links(cur, hypothesis_id, body.observation_zone_ids)

        if not sets and body.observation_zone_ids is None:
            raise HTTPException(400, "No fields to update")

        cur.execute(
            """
            SELECT id, project_id, hypothesis, root_cause, status, created_at, updated_at
            FROM hypotheses WHERE id = %(id)s
            """,
            {"id": hypothesis_id},
        )
        row = cur.fetchone()
        zone_ids = _fetch_zone_ids(cur, hypothesis_id)
        note_count = _fetch_field_note_count(cur, hypothesis_id)
    return _row_to_dict(row, zone_ids, note_count)


@router.delete("/{hypothesis_id}", status_code=204)
def delete_hypothesis(hypothesis_id: str, user: dict = Depends(get_current_user)):
    with db_cursor() as cur:
        project_id = _hypothesis_project_id(cur, hypothesis_id)
        assert_diagnosis_access(user["id"], project_id)
        cur.execute("DELETE FROM hypotheses WHERE id = %(id)s RETURNING id", {"id": hypothesis_id})
        if not cur.fetchone():
            raise HTTPException(404, "Hypothesis not found")
