"""Boilerplate router for the Assess module.

Assess owns its own data model (kept separate from Diagnose's `diagnosis`
table per the module split) — fill in schema and endpoints as the Assess
flow is built out.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.shared.auth import get_current_user
from app.shared.integrations.odk import ODKClient
from app.shared.integrations.odk.exceptions import ODKAuthFailed, ODKConnectionError, ODKAPIError

router = APIRouter()


@router.get("/status")
def assess_status():
    return {"module": "assess", "status": "not_implemented"}


@router.get("/odk/projects")
async def odk_projects(user: dict = Depends(get_current_user)):
    """Temporary demo endpoint to verify ODK integration.

    Calls ODK Central `/v1/projects` using the backend-configured integration
    account. This endpoint is temporary and intended for manual verification only.
    """
    client = ODKClient()

    
    try:
        result = await client.get("/v1/projects")
    except ODKConnectionError:
        raise HTTPException(502, "Could not reach ODK Central. Try again later.")
    except ODKAuthFailed:
        raise HTTPException(502, "ODK Central authentication failed.")
    except ODKAPIError as exc:
        raise HTTPException(exc.status_code, "ODK API error")

    # Do not return tokens or credentials — the client returns only the API data.
    return {"ok": True, "data": result}
