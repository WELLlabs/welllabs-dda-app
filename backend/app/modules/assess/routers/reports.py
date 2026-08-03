"""Reports endpoint: GET /api/assess/projects/{id}/reports.

Enforces access here (single source of truth); Metabase work is delegated to
the service so this route survives future dashboard-creation automation.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.modules.assess.access import require_assess_access
from app.modules.assess.services import metabase as metabase_service
from app.shared.config import settings

router = APIRouter()


@router.get("/{project_id}/reports")
def get_project_report(project_id: str, _user: dict = Depends(require_assess_access)):
    if not settings.metabase_embed_secret_key:
        raise HTTPException(503, "Metabase embedding is not configured")

    return metabase_service.get_project_report(project_id)
