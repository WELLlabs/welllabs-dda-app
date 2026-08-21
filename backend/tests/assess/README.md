# Assess & App Test Suite

Documentation for the unit/API tests covering the Assess module and application entrypoint.

These tests are designed to run **without** Postgres, ODK Central, or Metabase. Database access, ODK calls, and Metabase signing are mocked. Auth is bypassed via FastAPI dependency overrides where endpoints require a logged-in user or project admin.

## How to run

From the backend root (Docker, matches CI/prod deps):

```bash
./scripts/run_tests.sh tests/assess tests/test_app.py -v
```

Or a single file:

```bash
./scripts/run_tests.sh tests/assess/test_metabase.py -v
```

Shared fixture: `tests/conftest.py` provides `client` — a FastAPI `TestClient` with DB pool startup/shutdown patched out.

---

## File map

| Test file | Source under test | Style |
|---|---|---|
| [`tests/test_app.py`](../test_app.py) | `app/main.py` | HTTP smoke + lifespan |
| [`test_access.py`](test_access.py) | `app/modules/assess/access.py` | Unit (mocked DB) |
| [`test_access_router.py`](test_access_router.py) | `app/modules/assess/routers/access.py` | HTTP + mocked DB |
| [`test_assess.py`](test_assess.py) | `app/modules/assess/routers/assess.py` | Unit + HTTP + mocked ODK/DB |
| [`test_reports.py`](test_reports.py) | `app/modules/assess/routers/reports.py` | HTTP + mocked service |
| [`test_metabase.py`](test_metabase.py) | `app/modules/assess/services/metabase.py` | Unit (JWT + mocked DB) |

---

## `tests/test_app.py` — application entrypoint

Covers `app/main.py`:

| Test | What it checks |
|---|---|
| `test_health` | `GET /health` returns `{"status": "ok"}` |
| `test_auth_me_requires_login` | Unauthenticated `GET /api/accounts/auth/me` → 401 |
| `test_openapi_includes_assess_routes` | OpenAPI documents Assess status, projects, reports, and access routes |
| `test_cors_allows_configured_frontend_origin` | CORS preflight allows the configured frontend origin with credentials |
| `test_lifespan_initializes_and_closes_pool` | App lifespan calls `init_pool(min_size=2, max_size=10)` on start and `close_pool` on shutdown |

---

## `test_access.py` — Assess access helpers

Covers the SQL filter and FastAPI dependencies used to gate Assess project routes.

### `TestAssessAccessWhere`

Asserts `assess_access_where(alias)` builds a predicate that includes:

- owner check (`alias.owner_id = %(current_user_id)s`)
- direct grants via `assess_project_users`
- org grants via `assess_project_orgs` + `org_members`
- correct table alias substitution

### `TestRequireAssessAccess`

Mocks `db_cursor` to simulate the single-round-trip exists/has_access query:

- **404** when the project does not exist
- **403** when the project exists but the user cannot access it
- returns the current user when access is granted

### `TestRequireAssessAdmin`

Same pattern for admin/owner-only actions:

- **404** / **403** with admin-specific message (`Only project admins can do this`)
- returns the user when admin access is granted

---

## `test_access_router.py` — sharing management API

Covers `GET/POST/PATCH/DELETE` under `/api/assess/projects/{project_id}/access/...`.

**Fixture:** `access_client` overrides `require_assess_admin` so tests do not re-test the gate; they focus on route logic and DB interactions.

### Request models

- `AddUserAccess` defaults `role` to `"member"`; rejects invalid emails
- `UpdateUserRole` accepts a role string

### User access endpoints

| Area | Cases |
|---|---|
| List users | Serializes id/email/name/role/`created_at` ISO strings |
| Add user | Rejects invalid role; 404 unknown email; 400 adding self; 409 already granted; 201 success; email lowercased for lookup |
| Update role | Rejects invalid role; 404 if user not on project; 200 on success |
| Remove user | 404 if missing; 204 on success |

### Org access endpoints

| Area | Cases |
|---|---|
| List orgs | Serializes id/name/`created_at` |
| Add org | 404 unknown org; 409 already granted; 201 success |
| Remove org | 404 if missing; 204 on success |

---

## `test_assess.py` — Assess core router

Covers status, project listing, ODK sync, forms, and submissions.

**Fixture:** `auth_client` overrides `get_current_user`.

### Status & serializers

- `GET /api/assess/status` → `{module: assess, status: not_implemented}`
- `_assess_project_to_dict` stringifies UUIDs/datetimes and defaults missing `metabase_dashboard_id` to `None`

### DB helpers

- `_sync_projects_to_db` upserts each ODK project; names unnamed projects as `ODK Project {id}`
- `_get_assess_project_odk_id` returns the row or `None`

### `GET /api/assess/odk/projects`

- Success: returns ODK payload plus synced rows
- Error mapping:
  - `ODKConnectionError` → 502
  - `ODKAuthFailed` → 502
  - `ODKAPIError` → ODK status code with `"ODK API error"`

### `GET /api/assess/projects`

- Lists projects visible to the current user (access SQL + `current_user_id` param)

### Forms & submissions

For forms list, submissions list, and single submission:

- **404** when the assess project (owner-scoped ODK id lookup) is missing
- Success path mocks `ODKClient.get` and asserts the correct ODK URL
- Same ODK error → HTTP status mapping as above

---

## `test_reports.py` — Reports endpoint

Covers `GET /api/assess/projects/{project_id}/reports`.

**Fixture:** `reports_client` overrides `require_assess_access` (access is tested in `test_access.py`).

| Test | What it checks |
|---|---|
| Secret missing | **503** `"Metabase embedding is not configured"` when embed secret is empty |
| Configured report | Delegates to `metabase_service.get_project_report` and returns its payload as-is |
| Unconfigured report | Passes through `configured: False` empty-state payload |

This keeps the HTTP contract thin: auth + config gate here; JWT/dashboard logic in the service.

---

## `test_metabase.py` — Metabase embed service

Covers the only module that builds Metabase guest-embed JWTs.

### `_resolve_project_dashboard`

- Missing project → `(None, None)`
- Found project → `(name, metabase_dashboard_id)`

### `_sign_dashboard_token`

- Raises `RuntimeError` if embed secret is unset
- Signs HS256 JWT with `resource.dashboard`, empty `params`, and short-lived `exp` (10 minutes)

### `get_project_report`

- No / falsy dashboard id → `{configured: False, dashboard_id: None, ...}`
- Mapped dashboard → `{configured: True, token, instance_url, expires_at, ...}`

---

## Testing conventions

1. **No real services** — patch `db_cursor`, `ODKClient`, `anyio.to_thread.run_sync`, and `settings` as needed.
2. **Dependency overrides** — use `app.dependency_overrides[...]` for `get_current_user`, `require_assess_access`, or `require_assess_admin`; always clear overrides after the test/fixture.
3. **Mirror diagnose/shared style** — class-grouped tests, `MagicMock` context managers for `db_cursor`, parametrize repeated error-mapping cases.
4. **Access vs route** — gate logic lives in `test_access.py`; routers assume the dependency already passed when overridden.

## Related source layout

```
app/main.py
app/modules/assess/
  access.py                 ← test_access.py
  routers/
    access.py               ← test_access_router.py
    assess.py               ← test_assess.py
    reports.py              ← test_reports.py
  services/
    metabase.py             ← test_metabase.py
```
