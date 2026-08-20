"""MEL plan design endpoints for the Assess module."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.modules.assess.access import (
    assess_access_where,
    get_mel_plan,
    get_mel_project,
    _assert_assess_gate,
)
from app.modules.assess.services.collect_qr import build_mel_collect_qr
from app.modules.assess.services.mel_catalog import (
    get_intervention,
    list_interventions,
    resolve_selected_outcomes,
)
from app.modules.assess.services.mel_measurement_catalog import build_schedule_packages
from app.modules.assess.services.odk_form_builder import (
    build_mel_form_xml,
    enrich_indicators_for_odk,
    list_input_types,
    normalize_options,
)
from app.shared.auth import get_current_user
from app.shared.config import settings
from app.shared.database import db_cursor
from app.shared.integrations.odk import ODKClient
from app.shared.integrations.odk.exceptions import ODKAPIError, ODKAuthFailed, ODKConnectionError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mel", tags=["assess:mel"])

_INPUT_TYPE_IDS = {
    "decimal",
    "integer",
    "text",
    "long_text",
    "select_one",
    "select_multiple",
    "geopoint",
    "date",
    "select_one_yes_no",
}


class MelPlanPreviewRequest(BaseModel):
    intervention_slug: str | None = None
    outcome_ids: list[str] = Field(default_factory=list)
    project_id: str | None = None
    plan_id: str | None = None


class MelFieldOption(BaseModel):
    value: str = ""
    label: str = ""


class MelFieldSpec(BaseModel):
    id: str
    label: str | None = None
    hint: str | None = None
    input_type: str | None = None
    field_name: str | None = None
    choices: list[str] | str | None = None
    options: list[MelFieldOption] | None = None
    indicator: str | None = None
    outcome: str | None = None
    category_label: str | None = None
    assumptions: str | None = None
    custom: bool = False
    locked: bool = False
    required: bool = False


class MelPlanCreateRequest(MelPlanPreviewRequest):
    form_title: str | None = None
    fields: list[MelFieldSpec] = Field(default_factory=list)
    project_id: str
    plan_id: str
    package_id: str | None = None
    package_title: str | None = None


class MelPackagePublishSpec(BaseModel):
    package_id: str
    form_title: str | None = None
    fields: list[MelFieldSpec] = Field(default_factory=list)
    # When set, publish a new draft version of this existing ODK form instead of creating one.
    xml_form_id: str | None = None


class MelPlanCreateFormsRequest(MelPlanPreviewRequest):
    project_id: str
    plan_id: str
    packages: list[MelPackagePublishSpec] = Field(default_factory=list)


def _handle_odk_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, ODKConnectionError):
        return HTTPException(502, "Could not reach ODK Central. Try again later.")
    if isinstance(exc, ODKAuthFailed):
        return HTTPException(502, "ODK Central authentication failed.")
    if isinstance(exc, ODKAPIError):
        return HTTPException(exc.status_code, f"ODK request failed: {exc.detail}")
    raise exc


def _assert_project_access(project_id: str, user_id: str) -> dict:
    """Ensure the user can access this MEL project; return project row."""
    _assert_assess_gate(
        project_id,
        user_id,
        forbidden_message="You do not have access to this project",
        access_sql=assess_access_where("p"),
    )
    return get_mel_project(project_id)


def _assert_plan_access(project_id: str, plan_id: str, user_id: str) -> tuple[dict, dict]:
    """Ensure access to project and that plan belongs to it; return (project, plan)."""
    project = _assert_project_access(project_id, user_id)
    plan = get_mel_plan(plan_id, project_id=project_id)
    return project, plan


def format_odk_form_title(project_name: str, plan_name: str, package_label: str) -> str:
    """ODK form display name: Project - Plan - Continuous Monthly."""
    package_part = (package_label or "Form").replace(" · ", " ").replace("·", " ")
    package_part = " ".join(package_part.split()).strip() or "Form"
    return f"{project_name} - {plan_name} - {package_part}"


def _insert_mel_form(
    *,
    project_id: str,
    plan_id: str,
    xml_form_id: str,
    name: str,
    package_id: str | None,
    package_title: str | None,
    created_by: str,
) -> dict:
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO mel_forms (
                project_id, plan_id, xml_form_id, name, package_id, package_title, created_by
            )
            VALUES (
                %(project_id)s, %(plan_id)s, %(xml_form_id)s, %(name)s,
                %(package_id)s, %(package_title)s, %(created_by)s
            )
            ON CONFLICT (plan_id, xml_form_id) DO UPDATE SET
                name = EXCLUDED.name,
                package_id = EXCLUDED.package_id,
                package_title = EXCLUDED.package_title
            RETURNING id, xml_form_id, name, package_id, package_title, created_at
            """,
            {
                "project_id": project_id,
                "plan_id": plan_id,
                "xml_form_id": xml_form_id,
                "name": name,
                "package_id": package_id,
                "package_title": package_title,
                "created_by": created_by,
            },
        )
        return cur.fetchone()


@router.get("/interventions")
def mel_interventions(_user: dict = Depends(get_current_user)):
    return {"interventions": list_interventions()}


@router.get("/interventions/{slug}")
def mel_intervention_detail(slug: str, _user: dict = Depends(get_current_user)):
    intervention = get_intervention(slug)
    if intervention is None:
        raise HTTPException(404, "Intervention not found")
    return intervention


@router.get("/forms")
def mel_list_forms_deprecated(_user: dict = Depends(get_current_user)):
    """Deprecated: use GET /mel/projects/{id}/forms (membership-scoped)."""
    raise HTTPException(
        410,
        "Global MEL form listing is disabled. Open a MEL project and use its forms list.",
    )


@router.get("/input-types")
def mel_input_types(_user: dict = Depends(get_current_user)):
    return {"input_types": list_input_types()}


def _resolve_intervention_slug(body: MelPlanPreviewRequest, user_id: str) -> str:
    """Resolve intervention from plan when plan_id is set, else from body."""
    if body.plan_id:
        if not body.project_id:
            raise HTTPException(400, "project_id is required when plan_id is set")
        _project, plan = _assert_plan_access(body.project_id, body.plan_id, user_id)
        return plan["intervention_slug"]
    if body.project_id:
        _assert_project_access(body.project_id, user_id)
    if not body.intervention_slug:
        raise HTTPException(400, "intervention_slug is required")
    return body.intervention_slug


@router.post("/plans/preview")
def mel_plan_preview(body: MelPlanPreviewRequest, user: dict = Depends(get_current_user)):
    intervention_slug = _resolve_intervention_slug(body, user["id"])
    try:
        resolved = resolve_selected_outcomes(intervention_slug, body.outcome_ids)
    except KeyError:
        raise HTTPException(404, "Intervention not found")

    resolved["indicators"] = enrich_indicators_for_odk(resolved["indicators"])
    resolved["input_types"] = list_input_types()
    return resolved


def _resolve_form_fields(catalog_indicators: list[dict], fields: list[MelFieldSpec]) -> list[dict]:
    if not fields:
        return enrich_indicators_for_odk(catalog_indicators)

    catalog_by_id = {item["id"]: item for item in catalog_indicators}
    merged: list[dict] = []
    for index, spec in enumerate(fields, start=1):
        input_type = spec.input_type or "decimal"
        if input_type not in _INPUT_TYPE_IDS:
            raise HTTPException(400, f"Unsupported input_type: {input_type}")

        base = dict(catalog_by_id.get(spec.id, {}))
        label = (spec.label if spec.label is not None else base.get("indicator") or "").strip()
        if not label:
            raise HTTPException(400, f"Field {index} is missing a label")

        choices = normalize_options(
            [opt.model_dump() for opt in spec.options]
            if spec.options is not None
            else (spec.choices if spec.choices is not None else base.get("options") or base.get("choices"))
        )
        if input_type in {"select_one", "select_multiple"} and len(choices) < 2:
            raise HTTPException(
                400,
                f"Field '{label}' needs at least two choices for {input_type}",
            )

        merged.append(
            {
                **base,
                "id": spec.id,
                "label": label,
                "indicator": spec.indicator or base.get("indicator") or label,
                "hint": (
                    spec.hint
                    if spec.hint is not None
                    else ("" if spec.custom else base.get("hint"))
                ),
                "input_type": input_type,
                # field_name is derived from label in enrich_indicators_for_odk / XML builder
                "field_name": "",
                "options": choices,
                "choices": [opt["label"] for opt in choices],
                "outcome": spec.outcome if spec.outcome is not None else base.get("outcome") or ("Custom" if spec.custom else ""),
                "category_label": spec.category_label
                if spec.category_label is not None
                else base.get("category_label") or ("Custom question" if spec.custom else ""),
                "assumptions": spec.assumptions if spec.assumptions is not None else base.get("assumptions") or "",
                "custom": bool(spec.custom or base.get("custom")),
                "locked": bool(spec.locked or base.get("locked")),
                "required": bool(spec.required or spec.locked or base.get("required") or base.get("locked")),
            }
        )

    return enrich_indicators_for_odk(merged)


@router.post("/plans/create-form")
async def mel_plan_create_form(body: MelPlanCreateRequest, user: dict = Depends(get_current_user)):
    if settings.odk_project_id is None:
        raise HTTPException(
            503,
            "ODK_PROJECT_ID is not configured. Set it in the backend environment to publish forms.",
        )

    project, plan = _assert_plan_access(body.project_id, body.plan_id, user["id"])
    intervention_slug = plan["intervention_slug"] or body.intervention_slug
    if not intervention_slug:
        raise HTTPException(400, "Plan is missing an intervention")

    try:
        resolved = resolve_selected_outcomes(intervention_slug, body.outcome_ids)
    except KeyError:
        raise HTTPException(404, "Intervention not found")

    indicators = _resolve_form_fields(resolved["indicators"], body.fields)
    if not indicators:
        raise HTTPException(400, "No indicators to collect for the selected outcomes")

    package_label = body.package_title or body.form_title or "Form"
    form_title = format_odk_form_title(project["name"], plan["name"], package_label)

    intervention = resolved["intervention"]
    xml_form_id, xml_body = build_mel_form_xml(
        intervention_name=intervention["name"],
        intervention_slug=intervention["slug"],
        indicators=indicators,
        form_title=form_title,
    )

    client = ODKClient()
    odk_project_id = settings.odk_project_id

    try:
        created = await client.post_xml(
            f"/v1/projects/{odk_project_id}/forms",
            xml_body,
            params={"publish": "true", "ignoreWarnings": "true"},
        )
    except (ODKConnectionError, ODKAuthFailed, ODKAPIError) as exc:
        raise _handle_odk_errors(exc)

    form_name = (created or {}).get("name") or form_title or xml_form_id
    stored_xml_id = str((created or {}).get("xmlFormId") or xml_form_id)
    stored = _insert_mel_form(
        project_id=body.project_id,
        plan_id=body.plan_id,
        xml_form_id=stored_xml_id,
        name=str(form_name),
        package_id=body.package_id,
        package_title=body.package_title or package_label,
        created_by=user["id"],
    )

    collect_qr = None
    try:
        collect_qr = await build_mel_collect_qr(
            client,
            odk_project_id=int(odk_project_id),
            project_name=project["name"],
            xml_form_ids=[stored_xml_id],
        )
    except Exception as exc:
        logger.warning("Could not build Collect QR after publish: %s", exc)

    return {
        "ok": True,
        "form": created,
        "melForm": {
            "id": str(stored["id"]),
            "xmlFormId": stored["xml_form_id"],
            "name": stored["name"],
        },
        "plan": {**resolved, "indicators": indicators},
        "xmlFormId": stored_xml_id,
        "odkProjectId": odk_project_id,
        "projectId": body.project_id,
        "planId": body.plan_id,
        "collectQr": collect_qr,
    }


@router.post("/plans/packages")
def mel_plan_packages(body: MelPlanPreviewRequest, user: dict = Depends(get_current_user)):
    intervention_slug = _resolve_intervention_slug(body, user["id"])
    try:
        resolved = resolve_selected_outcomes(intervention_slug, body.outcome_ids)
    except KeyError:
        raise HTTPException(404, "Intervention not found")

    packaged = build_schedule_packages(resolved["indicators"])
    for package in packaged["packages"]:
        package["suggested_fields"] = enrich_indicators_for_odk(package["suggested_fields"])

    return {
        "intervention": resolved["intervention"],
        "outcomes": resolved["outcomes"],
        "indicators": resolved["indicators"],
        "packages": packaged["packages"],
        "matched_indicators": packaged["matched_indicators"],
        "unmatched_indicators": packaged["unmatched_indicators"],
        "input_types": list_input_types(),
    }


@router.post("/plans/create-forms")
async def mel_plan_create_forms(body: MelPlanCreateFormsRequest, user: dict = Depends(get_current_user)):
    import json

    if settings.odk_project_id is None:
        raise HTTPException(
            503,
            "ODK_PROJECT_ID is not configured. Set it in the backend environment to publish forms.",
        )
    if not body.packages:
        raise HTTPException(400, "Select at least one schedule package to publish.")

    project, plan = _assert_plan_access(body.project_id, body.plan_id, user["id"])
    intervention_slug = plan["intervention_slug"] or body.intervention_slug
    if not intervention_slug:
        raise HTTPException(400, "Plan is missing an intervention")

    try:
        resolved = resolve_selected_outcomes(intervention_slug, body.outcome_ids)
    except KeyError:
        raise HTTPException(404, "Intervention not found")

    packaged = build_schedule_packages(resolved["indicators"])
    package_by_id = {item["id"]: item for item in packaged["packages"]}

    client = ODKClient()
    odk_project_id = settings.odk_project_id
    created_forms = []

    for spec in body.packages:
        package = package_by_id.get(spec.package_id)
        if package is None:
            raise HTTPException(400, f"Unknown or empty package: {spec.package_id}")

        base_fields = package["suggested_fields"]
        fields = (
            _resolve_form_fields(base_fields, spec.fields)
            if spec.fields
            else enrich_indicators_for_odk(base_fields)
        )
        if not fields:
            raise HTTPException(400, f"Package '{package['title']}' has no fields to publish.")

        form_title = format_odk_form_title(
            project["name"],
            plan["name"],
            package.get("title") or package["id"],
        )
        if spec.form_title:
            form_title = spec.form_title.strip() or form_title

        existing_xml_id = (spec.xml_form_id or "").strip() or None
        version = datetime.now(timezone.utc).strftime("%Y.%m.%d.%H%M%S")
        xml_form_id, xml_body = build_mel_form_xml(
            intervention_name=resolved["intervention"]["name"],
            intervention_slug=f"{resolved['intervention']['slug']}_{package['schedule']}",
            indicators=fields,
            form_title=form_title,
            xml_form_id=existing_xml_id,
            version=version,
        )

        updated = False
        try:
            if existing_xml_id:
                await client.post_xml(
                    f"/v1/projects/{odk_project_id}/forms/{existing_xml_id}/draft",
                    xml_body,
                    params={"ignoreWarnings": "true"},
                )
                await client.post_empty(
                    f"/v1/projects/{odk_project_id}/forms/{existing_xml_id}/draft/publish",
                    params={"version": version},
                )
                created = {"xmlFormId": existing_xml_id, "name": form_title, "version": version}
                updated = True
            else:
                created = await client.post_xml(
                    f"/v1/projects/{odk_project_id}/forms",
                    xml_body,
                    params={"publish": "true", "ignoreWarnings": "true"},
                )
        except (ODKConnectionError, ODKAuthFailed, ODKAPIError) as exc:
            raise _handle_odk_errors(exc)

        stored_xml_id = str((created or {}).get("xmlFormId") or xml_form_id)
        form_name = str((created or {}).get("name") or form_title)
        stored = _insert_mel_form(
            project_id=body.project_id,
            plan_id=body.plan_id,
            xml_form_id=stored_xml_id,
            name=form_name,
            package_id=package["id"],
            package_title=package["title"],
            created_by=user["id"],
        )

        created_forms.append(
            {
                "packageId": package["id"],
                "packageTitle": package["title"],
                "xmlFormId": stored_xml_id,
                "form": created,
                "name": form_name,
                "melFormId": str(stored["id"]),
                "fieldCount": len(fields),
                "updated": updated,
                "version": version if updated else (created or {}).get("version"),
            }
        )

    collect_qr = None
    try:
        collect_qr = await build_mel_collect_qr(
            client,
            odk_project_id=int(odk_project_id),
            project_name=project["name"],
            xml_form_ids=[f["xmlFormId"] for f in created_forms],
        )
        for form in created_forms:
            form["collectQr"] = collect_qr
    except Exception as exc:
        logger.warning("Could not build Collect QR after publish: %s", exc)

    with db_cursor() as cur:
        cur.execute(
            """
            UPDATE mel_plans
            SET plan_json = %(plan_json)s::jsonb, updated_at = now()
            WHERE id = %(id)s AND project_id = %(project_id)s
            """,
            {
                "id": body.plan_id,
                "project_id": body.project_id,
                "plan_json": json.dumps(
                    {
                        "outcome_ids": body.outcome_ids,
                        "published_packages": [s.package_id for s in body.packages],
                    }
                ),
            },
        )
        cur.execute(
            "UPDATE assess_projects SET updated_at = now() WHERE id = %(id)s",
            {"id": body.project_id},
        )

    return {
        "ok": True,
        "odkProjectId": odk_project_id,
        "projectId": body.project_id,
        "planId": body.plan_id,
        "forms": created_forms,
        "collectQr": collect_qr,
        "plan": {
            "intervention": resolved["intervention"],
            "outcomes": resolved["outcomes"],
            "packages": packaged["packages"],
        },
    }


@router.post("/plans/export-pdf")
def mel_plan_export_pdf(body: MelPlanPreviewRequest, user: dict = Depends(get_current_user)):
    intervention_slug = _resolve_intervention_slug(body, user["id"])
    try:
        from app.modules.assess.services.mel_plan_pdf import build_mel_plan_pdf
    except ImportError as exc:
        raise HTTPException(503, f"PDF export unavailable: {exc}") from exc

    try:
        resolved = resolve_selected_outcomes(intervention_slug, body.outcome_ids)
    except KeyError:
        raise HTTPException(404, "Intervention not found")

    full = get_intervention(intervention_slug) or {}
    intervention = {
        **resolved["intervention"],
        "requirement": full.get("requirement") or "",
    }
    pdf_bytes = build_mel_plan_pdf(
        intervention=intervention,
        outcomes=resolved["outcomes"],
        indicators=resolved["indicators"],
        all_outcomes=full.get("outcomes") or [],
    )
    slug = resolved["intervention"]["slug"]
    filename = f"mel-plan-{slug}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
