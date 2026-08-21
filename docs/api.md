# API Reference

Base URL (direct): `http://localhost:8080`  
Browser (dev): `http://localhost:5173` or `:5174` — `/api/*` proxied to FastAPI.

Authenticated endpoints require the HttpOnly JWT cookie `dda_session` (set on login /
Google OAuth callback). Register does **not** set a session until the user verifies and logs in.
Protected APIs require an **active and verified** user.

## Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Returns `{"status": "ok"}` |

---

## Accounts Module

### Auth — `/api/accounts/auth`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/register` | No | Create account. JSON `{email, name, password}` (password ≥ 8). Sends verification email via Brevo when configured. Does **not** set a session cookie. |
| POST | `/login` | No | Form body `username` (email) + `password` (`application/x-www-form-urlencoded`). Sets `dda_session` only if verified. Returns 204. |
| POST | `/logout` | No | Clears session cookie. |
| GET | `/me` | Yes | Current user `{id, email, name, created_at}`. |
| POST | `/request-verify-token` | No | JSON `{email}` — resend verification (202). |
| POST | `/verify` | No | JSON `{token}` — mark email verified. |
| POST | `/forgot-password` | No | JSON `{email}` — send reset email (202). |
| POST | `/reset-password` | No | JSON `{token, password}`. |
| PATCH | `/users/me` | Yes | Update profile (e.g. `{name}`). Used by `/complete-profile`. |
| GET | `/google/authorize` | No | Returns `{authorization_url}` when Google OAuth is configured. |
| GET | `/google/callback` | No | OAuth callback; sets cookie and redirects (`/complete-profile` for new Google users, else `/home`). |

### Users — `/api/accounts/users`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/lookup?email={email}` | Yes | Look up a user by email. Used before sharing or inviting. Returns `{id, email, name}`. |

### Organizations — `/api/accounts/orgs`

| Method | Path | Auth | Access | Description |
|--------|------|------|--------|-------------|
| GET | `/` | Yes | Any | List orgs the current user belongs to. |
| POST | `/` | Yes | Any | Create org. Body: `{name}`. Creator becomes admin. |
| DELETE | `/{org_id}` | Yes | Admin | Delete org. Cascades to remove membership and project access grants. Does not delete projects. |
| GET | `/{org_id}/members` | Yes | Member | List org members with roles. |
| POST | `/{org_id}/members` | Yes | Admin | Add member by email. Body: `{email}`. |
| DELETE | `/{org_id}/members/{member_id}` | Yes | Admin or self | Remove a member. Self-removal (leave) is allowed for any member. Last admin cannot leave. |
| PATCH | `/{org_id}/members/{member_id}/role` | Yes | Admin | Change role. Body: `{role}` (`admin` or `member`). Last admin cannot be demoted. |
| GET | `/{org_id}/projects` | Yes | Member | List diagnosis projects shared with this org. |

### QField Cloud — `/api/accounts/qfield`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/connect` | Yes | Link QField Cloud account. Body: `{username, password}`. Stores token in `user_qfield_credentials`. |
| GET | `/status` | Yes | Check connection status. Returns `{connected, qfield_username, expires_at}`. |
| DELETE | `/disconnect` | Yes | Remove stored QField Cloud token. |

---

## Diagnose Module

### Projects — `/api/diagnose/projects`

| Method | Path | Auth | Access | Description |
|--------|------|------|--------|-------------|
| GET | `/` | Yes | Any | List all projects accessible to the current user (owned, shared, or via org). |
| GET | `/{project_id}` | Yes | Access | Get project details including watershed geometry and counts. |
| POST | `/` | Yes | Any | Create project. Body: `{name, lng, lat}`. Looks up the watershed at the coordinates. |
| DELETE | `/{project_id}` | Yes | Owner | Delete project, its S3 media, and all related data. |

### Project Access — `/api/diagnose/projects/{project_id}/access`

All access management endpoints require the caller to be the project owner or a diagnosis admin.

| Method | Path | Access | Description |
|--------|------|--------|-------------|
| GET | `/users` | Admin | List users with direct access. Includes role. |
| POST | `/users` | Admin | Grant user access by email. Body: `{email, role?}`. Default role: `member`. |
| DELETE | `/users/{user_id}` | Admin | Revoke user access. |
| PATCH | `/users/{user_id}/role` | Admin | Change user role. Body: `{role}` (`admin` or `member`). |
| GET | `/orgs` | Admin | List orgs with access. |
| POST | `/orgs` | Admin | Grant org access. Body: `{org_id}`. Caller must be a member of the org. |
| DELETE | `/orgs/{org_id}` | Admin | Revoke org access. |

### Layers — `/api/diagnose/layers`

Enabled layers come from `COG_LAYERS` / `VECTOR_LAYERS`; styling and analysis metadata from `layers.yaml`.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/cog?bbox=&project_id=` | Yes | List COG raster layers with status, bounds, and catalog metadata. |
| GET | `/cog/{layer_id}/tiles/WebMercatorQuad/{z}/{x}/{y}` | Yes | Proxy a COG tile, optionally clipped to the project watershed. |
| GET | `/cog/{layer_id}/analysis?project_id=` | Yes + access | Watershed analysis for one COG layer. |
| GET | `/vector` | Yes | List configured FlatGeobuf vector layers from the catalog. |
| GET | `/vector/{layer_id}/data?project_id=` | Yes + access | Vector features clipped / filtered to the project watershed. |
| GET | `/vector/{layer_id}/analysis?project_id=` | Yes + access | Watershed analysis for one vector layer. |
| GET | `/analysis/batch?project_id=` | Yes + access | Batch analysis for all active secondary layers. |
| GET | `/dem/mesh?project_id=` | Yes + access | Downsampled DEM elevation grid (EPSG:4326) for the 3D viewer. |
| GET | `/{layer_id}/drape-grid?project_id=` | Yes + access | Layer values + colorscale sampled onto the DEM mesh for 3D draping. |
| GET | `/{layer_id}/drape?project_id=` | Yes + access | PNG drape texture aligned to the DEM mesh (legacy / alternate). |

### Watersheds — `/api/diagnose/watersheds`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/lookup` | Yes | Return the watershed polygon for a coordinate. Body: `{lng, lat}`. |

### Observation Zones — `/api/diagnose/observation-zones`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/?project_id={id}` | Yes + access | List zones as GeoJSON FeatureCollection. |
| POST | `/` | Yes + access | Create zone. Body: `{project_id, geometry, text, observations, questions, color}`. |
| PATCH | `/{zone_id}` | Yes + access | Update zone properties. |
| DELETE | `/{zone_id}` | Yes + access | Delete zone. |

### Field Notes — `/api/diagnose/field-notes`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/?project_id={id}` | Yes + access | List notes as GeoJSON FeatureCollection. |
| POST | `/` | Yes + access | Create note. Multipart form: `project_id`, `geometry` (JSON), `title`, `text`, optional `photo`, optional `audio`, optional `hypothesis_id`. |
| PATCH | `/{note_id}` | Yes + access | Update note `title`, `text`, geometry, or `hypothesis_id`. |
| DELETE | `/{note_id}` | Yes + access | Delete note and its media from S3. |
| GET | `/media?key={s3_key}` | Yes | Serve media file (redirects to S3 or streams from local). |
| GET | `/media/thumbnail?key={s3_key}&size={48-256}` | Yes | Square JPEG thumbnail for card previews (default size 128). |

### Hypotheses — `/api/diagnose/hypotheses`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/?project_id={id}` | Yes + access | List hypotheses with linked zone IDs and field note count. |
| GET | `/{hypothesis_id}` | Yes + access | Get a single hypothesis. |
| POST | `/` | Yes + access | Create hypothesis. Body: `{project_id, hypothesis, observation_zone_ids?}`. Status defaults to `untested`. |
| PATCH | `/{hypothesis_id}` | Yes + access | Update hypothesis, root cause, status, or zone links. `validated`/`invalidated` require at least one linked field note. |
| DELETE | `/{hypothesis_id}` | Yes + access | Delete hypothesis. |

### QField Sync — `/api/diagnose/qfield`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/package` | Yes + access | Build QGIS project and upload to QField Cloud. Uses the caller's QField token. |
| POST | `/package/stream` | Yes + access | Same as above but returns Server-Sent Events for progress tracking. |
| POST | `/sync` | Yes + access | Pull changes from QField Cloud, migrate media to S3. |
| POST | `/sync/stream` | Yes + access | Same as above with SSE progress. |
| POST | `/cleanup` | Yes + access | Remove orphaned S3 media for a project. |

---

## Design Module (stub)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/design/status` | No | Returns `{"module": "design", "status": "not_implemented"}` |

## Assess Module — `/api/assess`

ODK Central-backed monitoring. See [assess.md](assess.md).

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/status` | No | Placeholder: `{"module": "assess", "status": "not_implemented"}` |
| GET | `/odk/projects` | Yes | Sync ODK Central projects into `assess_projects` and return them. |
| GET | `/projects` | Yes | List Assess projects stored in PostGIS. |
| GET | `/projects/{project_id}/forms` | Yes | List ODK forms for a project. |
| GET | `/projects/{project_id}/forms/{xml_form_id}/submissions` | Yes | List submissions (OData). |
| GET | `/projects/{project_id}/forms/{xml_form_id}/submissions/{instance_id}` | Yes | Fetch one submission. |
| GET | `/projects/{project_id}/access/users` | Yes | List direct user grants for an Assess project. |
| POST | `/projects/{project_id}/access/users` | Yes | Grant a user access. Body: `{email, role?}`. |
| PATCH | `/projects/{project_id}/access/users/{user_id}/role` | Yes | Update a user grant role. Body: `{role}`. |
| DELETE | `/projects/{project_id}/access/users/{user_id}` | Yes | Revoke a user grant. |
| GET | `/projects/{project_id}/access/orgs` | Yes | List org grants for an Assess project. |
| POST | `/projects/{project_id}/access/orgs` | Yes | Grant org access. Body: `{org_id}`. |
| DELETE | `/projects/{project_id}/access/orgs/{org_id}` | Yes | Revoke org access. |
| GET | `/metabase/projects/{project_id}/token` | Yes | Generate a short-lived Metabase embed token for the project dashboard. |

---

## Access Control Model

A user can access a diagnosis project if any of these hold:

1. They are the **owner** (`diagnosis.owner_id`)
2. They have a direct grant in `diagnosis_users`
3. They belong to an org that has a grant in `diagnosis_orgs`

Management permissions:

| Action | Required |
|--------|----------|
| View project, create zones/notes | Any access |
| Manage sharing (add/remove users/orgs) | Owner or diagnosis admin |
| Delete project | Owner only |

## Authentication

- FastAPI Users cookie JWT (`CookieTransport` + `JWTStrategy`)
- Cookie name: `dda_session` (configurable)
- Default TTL: 30 days (`SESSION_TTL_DAYS`)
- Email login requires verification; Google users are verified by default
- Set `SESSION_COOKIE_SECURE=true` in production (requires HTTPS)
- Details: [auth.md](auth.md)
