# Database Schema

The backend uses PostgreSQL 16 with the PostGIS extension. The schema is defined in
`backend/db/init.sql` and applied automatically when the PostGIS container starts for the
first time. Auth cutovers may use `backend/db/migrations/` (prefer `docker compose down -v`
for local clean slate).

## Entity Relationship

```
users ──┬──── oauth_account
        ├──── user_qfield_credentials
        ├──── organizations ──── org_members (role: admin|member)
        ├──── assess_projects (odk_project_id)
        └──── diagnosis ──┬──── diagnosis_users (role: admin|member)
                          ├──── diagnosis_orgs
                          ├──── observation_zones ──┬──── hypothesis_observation_zones
                          ├──── hypotheses ─────────┘
                          └──── field_notes (optional FK → hypotheses)
```

Session auth is a JWT in the HttpOnly `dda_session` cookie (no `sessions` table).
QField tokens live in `user_qfield_credentials`. ODK Central uses env-level service credentials.

## Tables

### users

FastAPI Users identity. Email/password users have `hashed_password`; Google-only users may
have a generated hash or null depending on cutover. Display name is `name`.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK, auto-generated |
| email | TEXT | Unique |
| hashed_password | TEXT | Nullable for OAuth-oriented installs |
| is_active | BOOLEAN | Default true |
| is_superuser | BOOLEAN | Default false |
| is_verified | BOOLEAN | Email verified / Google default true |
| name | TEXT | Display name (default `''`) |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | Auto-trigger |

### oauth_account

OAuth provider linkage (e.g. Google) for FastAPI Users.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| user_id | UUID | FK → users, CASCADE |
| oauth_name | TEXT | e.g. `google` |
| access_token | TEXT | |
| expires_at | INTEGER | Nullable |
| refresh_token | TEXT | Nullable |
| account_id | TEXT | Provider subject |
| account_email | TEXT | |

Unique on `(oauth_name, account_id)`.

### user_qfield_credentials

Per-user QField Cloud connector secrets.

| Column | Type | Notes |
|--------|------|-------|
| user_id | UUID | PK, FK → users, CASCADE |
| qfield_username | TEXT | Nullable |
| qfield_token | TEXT | Nullable |
| qfield_token_expires_at | TIMESTAMPTZ | Nullable |
| updated_at | TIMESTAMPTZ | |

### organizations

User-created groups for team-based project sharing.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| name | TEXT | |
| created_by | UUID | FK → users |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | Auto-trigger |

### org_members

Many-to-many between organizations and users, with a role.

| Column | Type | Notes |
|--------|------|-------|
| org_id | UUID | PK part, FK → organizations, CASCADE |
| user_id | UUID | PK part, FK → users, CASCADE |
| role | TEXT | `admin` or `member` |
| added_by | UUID | FK → users |
| created_at | TIMESTAMPTZ | |

**Rules:** Only admins can add/remove other members. Any member can leave (self-remove). The last admin cannot leave without promoting someone else first.
### assess_projects

ODK Central projects synced into the Assess module.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| name | TEXT | |
| owner_id | UUID | FK → users |
| description | TEXT | Default `''` |
| status | TEXT | `draft`, `active`, or `archived` |
| odk_project_id | TEXT | Nullable; unique per `(owner_id, odk_project_id)` |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | Auto-trigger |

### diagnosis

A diagnosis project, scoped to a watershed boundary. Each project is owned by a single user.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| name | TEXT | |
| owner_id | UUID | FK → users |
| watershed_id | TEXT | External watershed identifier |
| watershed_name | TEXT | |
| watershed_geom | GEOMETRY(Geometry, 4326) | Watershed polygon, GIST indexed |
| seed_lng | DOUBLE PRECISION | Original click point longitude |
| seed_lat | DOUBLE PRECISION | Original click point latitude |
| qfield_project_id | TEXT | QField Cloud project ID (set after first package) |
| qfield_project_owner | UUID | FK → users, the user who created the QFC project |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | Auto-trigger |

### diagnosis_users

Direct user access grants on a diagnosis project. Each granted user has a role.

| Column | Type | Notes |
|--------|------|-------|
| diagnosis_id | UUID | PK part, FK → diagnosis, CASCADE |
| user_id | UUID | PK part, FK → users, CASCADE |
| role | TEXT | `admin` or `member` |
| added_by | UUID | FK → users |
| created_at | TIMESTAMPTZ | |

**Access tiers:**
- **Owner** (`diagnosis.owner_id`): full control, including delete
- **Admin** (role = `admin`): can manage sharing (add/remove users and orgs)
- **Member** (role = `member`): can view project, create zones and notes

### diagnosis_orgs

Organization-level access grants. All members of the granted org get access to the project.

| Column | Type | Notes |
|--------|------|-------|
| diagnosis_id | UUID | PK part, FK → diagnosis, CASCADE |
| org_id | UUID | PK part, FK → organizations, CASCADE |
| added_by | UUID | FK → users |
| created_at | TIMESTAMPTZ | |

Deleting an organization cascades to remove its `diagnosis_orgs` rows but does **not** delete the diagnosis projects.

### observation_zones

Polygon features drawn on the map within a diagnosis project.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| project_id | UUID | FK → diagnosis, CASCADE |
| geom | GEOMETRY(Geometry, 4326) | Must be POLYGON or MULTIPOLYGON |
| text | TEXT | Label |
| observations | TEXT | Field observations |
| questions | TEXT | Questions arising from observations |
| color | TEXT | Hex color (default: `#0d983b`) |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | Auto-trigger |
| created_by | TEXT | |

### hypotheses

Testable statements linked to observation zones. Field notes provide evidence for validation.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| project_id | UUID | FK → diagnosis, CASCADE |
| hypothesis | TEXT | The hypothesis statement |
| root_cause | TEXT | Populated after field testing |
| status | TEXT | `untested`, `validated`, `invalidated`, or `discarded` |
| created_by | UUID | FK → users |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | Auto-trigger |

### hypothesis_observation_zones

Many-to-many link between hypotheses and observation zones.

| Column | Type | Notes |
|--------|------|-------|
| hypothesis_id | UUID | PK part, FK → hypotheses, CASCADE |
| zone_id | UUID | PK part, FK → observation_zones, CASCADE |

### field_notes

Geotagged point features with optional photo and audio attachments.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| project_id | UUID | FK → diagnosis, CASCADE |
| hypothesis_id | UUID | FK → hypotheses, SET NULL on delete |
| geom | GEOMETRY(Point, 4326) | |
| title | TEXT | Short label |
| text | TEXT | Note content |
| photo_path | TEXT | S3 key or legacy local path |
| audio_path | TEXT | S3 key |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | Auto-trigger |
| created_by | TEXT | |

## Indexes

- `oauth_account_user_id_idx` on `oauth_account(user_id)`
- Unique `(oauth_name, account_id)` on `oauth_account`
- `org_members_user_id_idx` on `org_members(user_id)`
- `diagnosis_watershed_geom_idx` GIST on `diagnosis(watershed_geom)`
- `diagnosis_owner_id_idx` on `diagnosis(owner_id)`
- `assess_projects_owner_id_idx` on `assess_projects(owner_id)`
- Unique `(owner_id, odk_project_id)` on `assess_projects`
- `diagnosis_users_user_id_idx` on `diagnosis_users(user_id)`
- `diagnosis_orgs_org_id_idx` on `diagnosis_orgs(org_id)`
- `observation_zones_geom_idx` GIST on `observation_zones(geom)`
- `observation_zones_project_id_idx` on `observation_zones(project_id)`
- `hypotheses_project_id_idx` on `hypotheses(project_id)`
- `hypothesis_observation_zones_zone_id_idx` on `hypothesis_observation_zones(zone_id)`
- `field_notes_geom_idx` GIST on `field_notes(geom)`
- `field_notes_project_id_idx` on `field_notes(project_id)`
- `field_notes_hypothesis_id_idx` on `field_notes(hypothesis_id)`

## Triggers

All tables with an `updated_at` column have a `BEFORE UPDATE` trigger that sets `updated_at = now()` via the `set_updated_at()` function.
