# Assess Module

Assess syncs monitoring data from **ODK Central** into the platform and lets users browse
projects, forms, and submissions in the web UI.

## Status

| Area | State |
|------|--------|
| ODK project sync → `assess_projects` | Available |
| Forms & submissions UI | Available (`/assess`) |
| Module `/status` endpoint | Still returns `not_implemented` (placeholder) |
| Metabase signed embed | Config keys exist (`METABASE_EMBED_SECRET_KEY`, dashboard id); router not shipped yet |

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

## Data

`assess_projects` (see [database.md](database.md)):

- `name`, `owner_id`, `description`, `status` (`draft` \| `active` \| `archived`)
- `odk_project_id` (unique per owner)

## API

See [api.md](api.md) — Assess section.

## Not in scope yet

- Metabase dashboard iframe / signed embed endpoint
- Linking Assess projects to Diagnose watersheds
- Write-back or form editing inside this app (read / sync from ODK only)
