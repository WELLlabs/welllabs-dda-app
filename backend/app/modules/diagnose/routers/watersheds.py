from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.shared.auth import get_current_user
from app.shared.watersheds import (
    custom_aoi_from_geometry,
    list_village_districts,
    list_village_states,
    list_villages_for_district,
    lookup_watershed_with_village_context,
    resolve_village_watersheds,
    search_villages,
)

router = APIRouter()


class WatershedLookup(BaseModel):
    lng: float = Field(..., ge=-180, le=180)
    lat: float = Field(..., ge=-90, le=90)


class FromVillageBody(BaseModel):
    village_id: str | None = None
    geometry: dict[str, Any] | None = None


class FromGeometryBody(BaseModel):
    geometry: dict[str, Any]
    name: str | None = Field(default=None, max_length=200)


@router.post("/lookup")
def watershed_lookup(body: WatershedLookup, user: dict = Depends(get_current_user)):
    """Return the L12 under the coordinate, with village multi-micro context when available."""
    try:
        return lookup_watershed_with_village_context(body.lng, body.lat)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Watershed lookup failed: {exc}") from exc


@router.get("/villages/search")
def villages_search(
    q: str = Query(..., min_length=4, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    bbox: str | None = Query(
        None,
        description="Ignored (kept for clients); search uses a national name index",
    ),
    user: dict = Depends(get_current_user),
):
    """National village typeahead (cached name index from vector/villages.fgb). Min 4 chars."""
    del bbox
    try:
        hits = search_villages(q, limit=limit)
        return {"villages": hits}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Village search failed: {exc}") from exc


@router.get("/villages/states")
def villages_states(user: dict = Depends(get_current_user)):
    """List distinct states from the village name index."""
    try:
        return {"states": list_village_states()}
    except Exception as exc:
        raise HTTPException(502, f"Failed to list states: {exc}") from exc


@router.get("/villages/districts")
def villages_districts(
    state: str = Query(..., min_length=1, max_length=120),
    user: dict = Depends(get_current_user),
):
    """List districts for a state."""
    try:
        return {"districts": list_village_districts(state)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Failed to list districts: {exc}") from exc


@router.get("/villages/by-district")
def villages_by_district(
    state: str = Query(..., min_length=1, max_length=120),
    district: str = Query(..., min_length=1, max_length=120),
    q: str = Query("", max_length=100),
    limit: int | None = Query(
        None,
        ge=1,
        le=10000,
        description="Optional cap; omit to return every village in the district.",
    ),
    user: dict = Depends(get_current_user),
):
    """List villages in a state + district (optional name filter)."""
    try:
        return {
            "villages": list_villages_for_district(state, district, q=q, limit=limit)
        }
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Failed to list villages: {exc}") from exc


@router.post("/from-village")
def watersheds_from_village(body: FromVillageBody, user: dict = Depends(get_current_user)):
    """Union all Level-12 basins intersecting a village polygon."""
    if not body.village_id and not body.geometry:
        raise HTTPException(400, "Provide village_id or geometry")
    try:
        return resolve_village_watersheds(village_id=body.village_id, geometry=body.geometry)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Village watershed resolve failed: {exc}") from exc


@router.post("/from-geometry")
def watersheds_from_geometry(body: FromGeometryBody, user: dict = Depends(get_current_user)):
    """Treat an uploaded polygon as the clip AOI (custom watershed)."""
    try:
        return custom_aoi_from_geometry(body.geometry, name=body.name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Custom AOI validation failed: {exc}") from exc


class PreviewContextBody(BaseModel):
    geometry: dict[str, Any]


@router.post("/preview-context")
async def watershed_preview_context(body: PreviewContextBody, user: dict = Depends(get_current_user)):
    """Return rivers / basin / sub-basin / L7 layers clipped to a preview AOI."""
    del user
    import asyncio

    from app.modules.diagnose.services.preview_context import preview_context_layers

    try:
        layers = await asyncio.wait_for(
            asyncio.to_thread(preview_context_layers, body.geometry),
            timeout=55.0,
        )
        return {"layers": layers}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            504, "Preview context timed out — retry; basin layers may still be warming on the server."
        ) from exc
    except Exception as exc:
        raise HTTPException(502, f"Preview context failed: {exc}") from exc
