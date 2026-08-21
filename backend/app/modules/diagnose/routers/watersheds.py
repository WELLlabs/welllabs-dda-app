from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.shared.auth import get_current_user
from app.shared.watersheds import lookup_watershed

router = APIRouter()


class WatershedLookup(BaseModel):
    lng: float = Field(..., ge=-180, le=180)
    lat: float = Field(..., ge=-90, le=90)


@router.post("/lookup")
def watershed_lookup(body: WatershedLookup, user: dict = Depends(get_current_user)):
    """Return the watershed polygon containing the given coordinate."""
    try:
        return lookup_watershed(body.lng, body.lat)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Watershed lookup failed: {exc}") from exc
