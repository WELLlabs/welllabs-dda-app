# Assess Module

Assess syncs monitoring data from **ODK Central** into the platform and lets users browse
projects, forms, and submissions in the web UI.

## Status

| Area | State |
|------|--------|
| ODK project sync → `assess_projects` | Available |
| Forms & submissions UI | Available (`/assess`) |
| Project sharing and access control | Available (user + org grants) |
| Metabase signed embed | Available via `/api/assess/metabase/projects/{project_id}/token` when the server is configured |
| Module `/status` endpoint | Still returns `not_implemented` (placeholder) |

## Capabilities

### ODK project sync

- `GET /api/assess/odk/projects` pulls projects from ODK Central and upserts rows into `assess_projects`
- Server uses `ODK_BASE_URL` / `ODK_USERNAME` / `ODK_PASSWORD` (see `.env.example`)
- Users can also store personal ODK credentials on `users` via Accounts connectors

### Browse forms and submissions

Frontend (`frontend/src/lib/modules/assess/`):

1. **AssessProjects** — list synced projects; import/refresh from ODK
2. **AssessForms** — forms for a selected project
3. **AssessSubmissions** — OData submission list and detail for a form

Route: `frontend/src/routes/(protected)/assess/+page.svelte`.

### Project sharing and access

Assess projects support their own sharing model, separate from Diagnose:

- The project owner or an assess admin can grant access to individual users.
- The project owner or an assess admin can grant access to organizations.
- Access is enforced server-side before exposing project data or generating embed tokens.
- Supported roles are `admin` and `member`.

These endpoints are available under `/api/assess/projects/{project_id}/access/...`:

- `/access/users` — list/add/update/remove user grants
- `/access/orgs` — list/add/remove org grants

### Metabase signed embed

Assess projects can expose a signed Metabase dashboard embed when the backend is configured with:

- `METABASE_EMBED_SECRET_KEY`
- `METABASE_PUBLIC_URL` (or the default `http://localhost:3000`)
- an optional per-project `metabase_dashboard_id`

The backend endpoint `/api/assess/metabase/projects/{project_id}/token` signs a short-lived embed token for the requested dashboard and checks that the caller has access to the project first.

## Data

`assess_projects` (see [database.md](database.md)):

- `name`, `owner_id`, `description`, `status` (`draft` \| `active` \| `archived`)
- `odk_project_id` (unique per owner)
- `metabase_dashboard_id` (optional per-project dashboard mapping)

## API

See [api.md](api.md) — Assess section.

## Not in scope yet

- Metabase dashboard iframe / signed embed endpoint
- Linking Assess projects to Diagnose watersheds
- Write-back or form editing inside this app (read / sync from ODK only)
