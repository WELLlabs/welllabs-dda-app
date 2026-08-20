from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.main import app
from app.modules.assess.services.mel_catalog import (
    get_intervention,
    list_interventions,
    load_mel_catalog,
    resolve_selected_outcomes,
)
from app.modules.assess.services.mel_measurement_catalog import (
    build_schedule_packages,
    continuous_schedule,
    load_measurement_catalog,
    match_measurement_row,
    package_ids_for_row,
)
from app.modules.assess.services.mel_plan_pdf import build_mel_plan_pdf
from app.modules.assess.services.odk_form_builder import build_mel_form_xml
from app.shared.auth import get_current_user


def _user():
    return {"id": str(uuid4()), "email": "user@example.com", "name": "User"}


@pytest.fixture
def auth_client(client):
    user = _user()
    app.dependency_overrides[get_current_user] = lambda: user
    yield client, user
    app.dependency_overrides.pop(get_current_user, None)


def test_load_mel_catalog_has_interventions():
    load_mel_catalog.cache_clear()
    catalog = load_mel_catalog()
    assert len(catalog) >= 10
    assert all(item["outcomes"] for item in catalog)


def test_list_interventions_excludes_empty_catalog_rows():
    load_mel_catalog.cache_clear()
    slugs = {item["slug"] for item in list_interventions()}
    assert "intervention" not in slugs
    assert "check-dams-earthen-dams" in slugs


def test_must_measure_outcomes_are_auto_selected():
    load_mel_catalog.cache_clear()
    resolved = resolve_selected_outcomes("check-dams-earthen-dams", [])
    must_ids = [o["id"] for o in resolved["outcomes"] if o["must_measure"]]
    assert must_ids
    assert resolved["indicators"]


def test_build_mel_form_xml_includes_required_date_and_coordinates():
    from app.modules.assess.services.odk_form_builder import build_mel_form_xml

    _form_id, xml = build_mel_form_xml(
        intervention_name="Test",
        intervention_slug="test",
        indicators=[
            {
                "id": "a",
                "label": "Water depth",
                "indicator": "Water depth",
                "input_type": "decimal",
                "hint": "",
                "options": [],
            }
        ],
    )
    assert 'nodeset="/data/observation_date" type="date" required="true()"' in xml
    assert 'nodeset="/data/coordinates" type="geopoint" required="true()"' in xml
    assert '<input ref="/data/observation_date">' in xml
    assert '<input ref="/data/coordinates">' in xml
    assert '<input ref="/data/water_depth">' in xml


def test_build_mel_form_xml_respects_input_types():
    indicators = [
        {
            "id": "a",
            "indicator": "Volume (m3)",
            "outcome": "Availability",
            "category_label": "Biophysical",
            "assumptions": "",
            "input_type": "decimal",
            "label": "Volume harvested",
        },
        {
            "id": "b",
            "indicator": "Notes",
            "outcome": "Availability",
            "category_label": "Biophysical",
            "assumptions": "",
            "input_type": "long_text",
            "label": "Field notes",
        },
        {
            "id": "c",
            "indicator": "Crop mix",
            "outcome": "CWP",
            "category_label": "Socio-economic",
            "assumptions": "",
            "input_type": "select_one",
            "label": "Primary crop",
            "choices": ["Wheat", "Paddy", "Other"],
            "options": [
                {"value": "wheat", "label": "Wheat"},
                {"value": "paddy", "label": "Paddy"},
                {"value": "other", "label": "Other"},
            ],
        },
        {
            "id": "d",
            "indicator": "Livelihoods",
            "outcome": "Resilience",
            "category_label": "Socio-economic",
            "assumptions": "",
            "input_type": "select_multiple",
            "label": "Livelihoods practiced",
            "options": [
                {"value": "livestock", "label": "Livestock"},
                {"value": "fisheries", "label": "Fisheries"},
                {"value": "poultry", "label": "Poultry"},
            ],
        },        {
            "id": "e",
            "indicator": "Location",
            "outcome": "Plot",
            "category_label": "Biophysical",
            "assumptions": "",
            "input_type": "geopoint",
            "label": "Structure location",
        },
    ]
    _, xml = build_mel_form_xml(
        intervention_name="Test",
        intervention_slug="test",
        indicators=indicators,
    )
    assert 'type="decimal"' in xml
    assert 'appearance="multiline"' in xml
    assert "<select1 ref=" in xml
    assert "<select ref=" in xml
    assert 'type="geopoint"' in xml
    assert "<value>wheat</value>" in xml
    assert "Livelihoods practiced" in xml


def test_get_intervention_returns_outcomes_with_categories():
    load_mel_catalog.cache_clear()
    item = get_intervention("bio-mulching")
    assert item is not None
    categories = {o["category"] for o in item["outcomes"]}
    assert "biophysical" in categories

    check_dams = get_intervention("check-dams-earthen-dams")
    assert check_dams is not None
    check_cats = {o["category"] for o in check_dams["outcomes"]}
    assert "watershed" in check_cats
    watershed = [o for o in check_dams["outcomes"] if o["category"] == "watershed"]
    assert any("groundwater recharge" in o["title"].lower() for o in watershed)


def test_long_similar_indicator_names_are_not_collapsed():
    load_mel_catalog.cache_clear()
    intervention = get_intervention("farm-ponds-lined")
    assert intervention is not None
    outcome_ids = [
        o["id"]
        for o in intervention["outcomes"]
        if "rainfall runoff" in o["title"].lower()
        or "crop water productivity" in o["title"].lower()
    ]
    resolved = resolve_selected_outcomes("farm-ponds-lined", outcome_ids)
    assert len(resolved["indicators"]) == 11
    labels = [item["indicator"] for item in resolved["indicators"]]
    assert "Revenue/Profit (in Rs.) from livestock" in labels
    assert "Revenue/Profit (in Rs.) from poultry" in labels
    assert len({item["id"] for item in resolved["indicators"]}) == 11


def test_all_catalog_indicators_survive_resolve_and_form_build():
    """Every catalog indicator must appear in resolve + ODK XML (no silent drops)."""
    load_mel_catalog.cache_clear()
    catalog = load_mel_catalog()
    assert catalog

    for intervention in catalog:
        outcome_ids = [o["id"] for o in intervention["outcomes"]]
        expected = sum(len(o["indicators"]) for o in intervention["outcomes"])
        resolved = resolve_selected_outcomes(intervention["slug"], outcome_ids)
        assert len(resolved["indicators"]) == expected, intervention["slug"]
        assert len({item["id"] for item in resolved["indicators"]}) == expected, intervention[
            "slug"
        ]

        if expected == 0:
            continue

        _, xml = build_mel_form_xml(
            intervention_name=resolved["intervention"]["name"],
            intervention_slug=resolved["intervention"]["slug"],
            indicators=resolved["indicators"],
        )
        assert xml.count("<input ref=") == expected + 2, intervention["slug"]
        assert 'type="date" required="true()"' in xml
        assert 'type="geopoint" required="true()"' in xml
        for item in resolved["indicators"]:
            assert item["indicator"] in xml, (intervention["slug"], item["indicator"])


class TestMelListForms:
    def test_global_list_is_gone(self, auth_client):
        client, _user = auth_client
        response = client.get("/api/assess/mel/forms")
        assert response.status_code == 410
        assert "project" in response.json()["detail"].lower()


class TestMelCreateForm:
    def test_requires_configured_odk_project_id(self, auth_client):
        client, _user = auth_client
        with patch("app.modules.assess.routers.mel.settings") as mock_settings:
            mock_settings.odk_project_id = None
            response = client.post(
                "/api/assess/mel/plans/create-form",
                json={
                    "project_id": str(uuid4()),
                    "plan_id": str(uuid4()),
                    "intervention_slug": "micro-irrigation",
                    "outcome_ids": [],
                },
            )
        assert response.status_code == 503
        assert "ODK_PROJECT_ID" in response.json()["detail"]

    def test_publishes_form_to_configured_odk_project(self, auth_client):
        client, _user = auth_client
        load_mel_catalog.cache_clear()
        project_id = str(uuid4())
        plan_id = str(uuid4())
        mock_client = MagicMock()
        mock_client.post_xml = AsyncMock(
            return_value={"xmlFormId": "mel_test", "name": "Test Project - Test plan - Continuous Monthly"}
        )
        stored = {
            "id": uuid4(),
            "xml_form_id": "mel_test",
            "name": "Test Project - Test plan - Continuous Monthly",
        }
        mel_plan = {
            "id": plan_id,
            "project_id": project_id,
            "intervention_slug": "micro-irrigation",
            "name": "Test plan",
        }
        mel_project = {
            "id": project_id,
            "name": "Test Project",
            "kind": "mel",
        }
        with (
            patch("app.modules.assess.routers.mel.settings") as mock_settings,
            patch("app.modules.assess.routers.mel.ODKClient", return_value=mock_client),
            patch(
                "app.modules.assess.routers.mel._assert_plan_access",
                return_value=(mel_project, mel_plan),
            ),
            patch("app.modules.assess.routers.mel._insert_mel_form", return_value=stored),
        ):
            mock_settings.odk_project_id = 42
            response = client.post(
                "/api/assess/mel/plans/create-form",
                json={
                    "project_id": project_id,
                    "plan_id": plan_id,
                    "intervention_slug": "micro-irrigation",
                    "outcome_ids": [],
                    "package_title": "Continuous · Monthly",
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["odkProjectId"] == 42
        assert body["projectId"] == project_id
        assert body["planId"] == plan_id
        assert body["melForm"]["xmlFormId"] == "mel_test"
        mock_client.post_xml.assert_awaited_once()
        args, kwargs = mock_client.post_xml.await_args
        assert args[0] == "/v1/projects/42/forms"
        assert kwargs["params"] == {"publish": "true", "ignoreWarnings": "true"}
        xml_body = args[1]
        assert "Test Project - Test plan - Continuous Monthly" in xml_body


class TestMelMeasurementCatalog:
    def test_loads_measurement_rows(self):
        load_measurement_catalog.cache_clear()
        rows = load_measurement_catalog()
        assert len(rows) >= 15

    def test_frequency_maps_to_continuous_buckets(self):
        assert continuous_schedule("Daily") == "everyday"
        assert continuous_schedule("Weekly or how quickly water level changes") == "weekly"
        assert continuous_schedule("Every 3-4 days") == "weekly"
        assert continuous_schedule("Monthly/Seasonal") == "monthly"
        assert continuous_schedule("Each irrigation application") == "everyday"

    def test_package_ids_for_cm_bme_onetime(self):
        assert package_ids_for_row({"family_raw": "cm", "frequency": "Daily"}) == [
            "continuous_everyday"
        ]
        assert package_ids_for_row({"family_raw": "one-time", "frequency": "After monsoon"}) == [
            "one_time"
        ]
        assert package_ids_for_row(
            {"family_raw": "bme", "frequency": "Once per survey round (baseline/midline/endline)"}
        ) == ["bme"]

    def test_bme_is_single_package_with_survey_round(self):
        load_mel_catalog.cache_clear()
        load_measurement_catalog.cache_clear()
        # Crop yield is BME in the measurement catalog
        resolved = resolve_selected_outcomes("farm-ponds-lined", [])
        # Force-include a known BME-ish indicator text via attach path
        packaged = build_schedule_packages(resolved["indicators"])
        bme_packages = [pkg for pkg in packaged["packages"] if pkg["family"] == "bme"]
        if not bme_packages:
            # Build from a synthetic matched BME indicator
            packaged = build_schedule_packages(
                [
                    {
                        "id": "ind_bme",
                        "indicator": "Crop yield",
                        "outcome": "Test",
                        "category_label": "BME",
                    }
                ]
            )
            bme_packages = [pkg for pkg in packaged["packages"] if pkg["family"] == "bme"]
        assert len(bme_packages) == 1
        assert bme_packages[0]["id"] == "bme"
        round_fields = [
            f for f in bme_packages[0]["suggested_fields"] if f.get("field_name") == "survey_round"
        ]
        assert len(round_fields) == 1
        assert {o["value"] for o in round_fields[0]["options"]} == {"baseline", "midline", "endline"}

    def test_matches_known_indicator(self):
        load_measurement_catalog.cache_clear()
        row = match_measurement_row("Volume of water in the structure in monsoon (m3)")
        assert row is not None
        assert "monsoon" in row["indicator"].lower()

    def test_build_packages_for_farm_ponds(self):
        load_mel_catalog.cache_clear()
        load_measurement_catalog.cache_clear()
        resolved = resolve_selected_outcomes("farm-ponds-lined", [])
        packaged = build_schedule_packages(resolved["indicators"])
        assert packaged["matched_indicators"]
        ids = {pkg["id"] for pkg in packaged["packages"]}
        assert "continuous_everyday" in ids
        everyday = next(pkg for pkg in packaged["packages"] if pkg["id"] == "continuous_everyday")
        assert everyday["suggested_fields"]


class TestMelPackagesEndpoint:
    def test_returns_packages(self, auth_client):
        client, _user = auth_client
        load_mel_catalog.cache_clear()
        load_measurement_catalog.cache_clear()
        response = client.post(
            "/api/assess/mel/plans/packages",
            json={"intervention_slug": "farm-ponds-lined", "outcome_ids": []},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["intervention"]["slug"] == "farm-ponds-lined"
        assert isinstance(body["packages"], list)
        assert body["input_types"]


class TestMelCreateForms:
    def test_publishes_multiple_packages(self, auth_client):
        client, user = auth_client
        load_mel_catalog.cache_clear()
        load_measurement_catalog.cache_clear()
        project_id = str(uuid4())
        plan_id = str(uuid4())
        mock_client = MagicMock()
        mock_client.post_xml = AsyncMock(
            side_effect=[
                {"xmlFormId": "mel_a", "name": "A"},
                {"xmlFormId": "mel_b", "name": "B"},
                {"xmlFormId": "mel_c", "name": "C"},
            ]
        )
        packages_res = client.post(
            "/api/assess/mel/plans/packages",
            json={"intervention_slug": "farm-ponds-lined", "outcome_ids": []},
        )
        package_ids = [pkg["id"] for pkg in packages_res.json()["packages"]][:2]
        assert package_ids

        stored = {"id": uuid4(), "xml_form_id": "mel_a", "name": "A"}
        mel_plan = {
            "id": plan_id,
            "project_id": project_id,
            "intervention_slug": "farm-ponds-lined",
            "name": "Farm ponds",
        }
        mel_project = {
            "id": project_id,
            "name": "Watershed Project",
            "kind": "mel",
        }
        mock_cur = MagicMock()
        ctx = MagicMock()
        ctx.__enter__.return_value = mock_cur
        ctx.__exit__.return_value = False

        with (
            patch("app.modules.assess.routers.mel.settings") as mock_settings,
            patch("app.modules.assess.routers.mel.ODKClient", return_value=mock_client),
            patch(
                "app.modules.assess.routers.mel._assert_plan_access",
                return_value=(mel_project, mel_plan),
            ),
            patch("app.modules.assess.routers.mel._insert_mel_form", return_value=stored),
            patch("app.modules.assess.routers.mel.db_cursor", return_value=ctx),
        ):
            mock_settings.odk_project_id = 17
            response = client.post(
                "/api/assess/mel/plans/create-forms",
                json={
                    "project_id": project_id,
                    "plan_id": plan_id,
                    "intervention_slug": "farm-ponds-lined",
                    "outcome_ids": [],
                    "packages": [{"package_id": pid, "fields": []} for pid in package_ids],
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["projectId"] == project_id
        assert body["planId"] == plan_id
        assert len(body["forms"]) == len(package_ids)
        assert all(form.get("melFormId") for form in body["forms"])
        assert mock_client.post_xml.await_count == len(package_ids)
        # Verify naming: Project - Plan - Package
        first_xml = mock_client.post_xml.await_args_list[0].args[1]
        assert "Watershed Project - Farm ponds - " in first_xml


class TestMelExportPdf:
    def test_returns_pdf_bytes(self, auth_client):
        client, _user = auth_client
        load_mel_catalog.cache_clear()
        load_measurement_catalog.cache_clear()
        response = client.post(
            "/api/assess/mel/plans/export-pdf",
            json={"intervention_slug": "micro-irrigation", "outcome_ids": []},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/pdf")
        assert response.content[:4] == b"%PDF"
        assert len(response.content) > 500

    def test_pdf_builder_direct(self):
        load_mel_catalog.cache_clear()
        load_measurement_catalog.cache_clear()
        from app.modules.assess.services.mel_catalog import get_intervention

        resolved = resolve_selected_outcomes("micro-irrigation", [])
        full = get_intervention("micro-irrigation") or {}
        pdf = build_mel_plan_pdf(
            intervention={**resolved["intervention"], "requirement": full.get("requirement") or ""},
            outcomes=resolved["outcomes"],
            indicators=resolved["indicators"],
            all_outcomes=full.get("outcomes") or [],
        )
        assert pdf[:4] == b"%PDF"
        # Portrait multi-page document
        import re

        pages = len(re.findall(rb"/Type\s*/Page\b", pdf))
        assert pages >= 4
        # MediaBox should be portrait A4 (width < height)
        box = re.search(
            rb"/MediaBox\s*\[\s*([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s*\]",
            pdf,
        )
        assert box
        w = float(box.group(3)) - float(box.group(1))
        h = float(box.group(4)) - float(box.group(2))
        assert w < h

    def test_pdf_builder_handles_tall_field_checklist(self):
        """Regression: packages with many fields must not raise LayoutError."""
        load_mel_catalog.cache_clear()
        load_measurement_catalog.cache_clear()
        from app.modules.assess.services.mel_catalog import get_intervention

        # Prefer an intervention that yields a large BME / field checklist.
        for slug in ("check-dams-earthen-dams", "farm-ponds-unlined", "bio-mulching", "micro-irrigation"):
            full = get_intervention(slug) or {}
            all_ids = [o["id"] for o in full.get("outcomes") or []]
            resolved = resolve_selected_outcomes(slug, all_ids)
            if resolved.get("indicators"):
                break
        else:
            resolved = resolve_selected_outcomes("micro-irrigation", [])
            full = get_intervention("micro-irrigation") or {}

        pdf = build_mel_plan_pdf(
            intervention={**resolved["intervention"], "requirement": full.get("requirement") or ""},
            outcomes=resolved["outcomes"],
            indicators=resolved["indicators"],
            all_outcomes=full.get("outcomes") or [],
        )
        assert pdf[:4] == b"%PDF"
        assert len(pdf) > 500
