"""Smoke tests: OpenAPI catalog matches registered routes; key endpoints respond."""

from __future__ import annotations

import re
from uuid import uuid4

from fastapi.routing import APIRoute

_DUMMY_PARAMS = {
    "org_id": str(uuid4()),
    "member_id": str(uuid4()),
    "project_id": str(uuid4()),
    "user_id": str(uuid4()),
    "note_id": str(uuid4()),
    "hypothesis_id": str(uuid4()),
    "zone_id": str(uuid4()),
    "layer_id": "lulc",
    "z": "0",
    "x": "0",
    "y": "0",
    "filename": "test.jpg",
    "xml_form_id": "baseline",
    "instance_id": "1",
    "plan_id": str(uuid4()),
    "slug": "farm-ponds",
}


def _normalize_path(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path)


def _fill_path(path: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return _DUMMY_PARAMS.get(match.group(1), "test")

    return re.sub(r"\{(\w+)\}", repl, path)


def _app_route_paths(app) -> set[str]:
    paths: set[str] = set()

    def walk(routes, prefix: str = "") -> None:
        for route in routes:
            if isinstance(route, APIRoute):
                paths.add(_normalize_path(f"{prefix}{route.path}"))
            elif type(route).__name__ == "_IncludedRouter":
                ctx = route.include_context
                walk(route.original_router.routes, f"{prefix}{ctx.prefix}")
            else:
                nested = getattr(route, "routes", None)
                if nested:
                    walk(nested, prefix)

    walk(app.routes)
    return paths


def test_openapi_paths_are_registered(client):
    """Every documented API path is mounted on the FastAPI app."""
    from app.main import app

    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    openapi_paths = {_normalize_path(p) for p in spec.json()["paths"]}
    registered = _app_route_paths(app)
    missing = sorted(openapi_paths - registered)
    assert not missing, f"OpenAPI paths missing from app routes: {missing}"


def test_unknown_api_path_returns_not_found(client):
    response = client.get("/api/this-route-does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_status_endpoints_respond(client):
    for path in ("/health", "/api/assess/status", "/api/design/status"):
        response = client.get(path)
        assert response.status_code == 200, path


def test_protected_endpoints_require_auth(client):
    for path in (
        "/api/accounts/auth/me",
        "/api/diagnose/projects",
        "/api/assess/projects",
        "/api/accounts/orgs",
    ):
        response = client.get(path)
        assert response.status_code == 401, path


def test_get_endpoints_do_not_return_unregistered_404(client):
    """GET each OpenAPI path — resource 404s are OK; unregistered routes are not."""
    spec = client.get("/openapi.json").json()
    unregistered: list[str] = []

    for path, operations in spec["paths"].items():
        if "get" not in operations:
            continue
        filled = _fill_path(path)
        if "google/callback" in filled:
            url = f"{filled}?error=smoke_test"
        else:
            url = filled
        response = client.get(url)
        if response.status_code == 404 and response.json().get("detail") == "Not Found":
            unregistered.append(f"GET {url}")

    assert not unregistered, "Unregistered GET routes:\n" + "\n".join(unregistered)
