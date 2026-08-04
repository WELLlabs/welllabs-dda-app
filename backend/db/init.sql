CREATE EXTENSION IF NOT EXISTS postgis;

-- Users: FastAPI Users identity (email/password + OAuth). QField tokens live elsewhere.
CREATE TABLE users (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email            TEXT NOT NULL UNIQUE,
    hashed_password  TEXT,  -- NULL for Google/OAuth-only users
    is_active        BOOLEAN NOT NULL DEFAULT true,
    is_superuser     BOOLEAN NOT NULL DEFAULT false,
    is_verified      BOOLEAN NOT NULL DEFAULT false,
    name             TEXT NOT NULL DEFAULT '',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- OAuth account linkage (Google, etc.) — FastAPI Users
CREATE TABLE oauth_account (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    oauth_name         TEXT NOT NULL,
    access_token       TEXT NOT NULL,
    expires_at         INTEGER,
    refresh_token      TEXT,
    account_id         TEXT NOT NULL,
    account_email      TEXT NOT NULL,
    CONSTRAINT oauth_account_oauth_name_account_id_key UNIQUE (oauth_name, account_id)
);

CREATE INDEX oauth_account_user_id_idx ON oauth_account (user_id);

-- Per-user QField Cloud credentials (connector secrets, not auth identity)
CREATE TABLE user_qfield_credentials (
    user_id                  UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    qfield_username          TEXT,
    qfield_token             TEXT,
    qfield_token_expires_at  TIMESTAMPTZ,
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Organizations: a user can create/belong to many
CREATE TABLE organizations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    created_by  UUID NOT NULL REFERENCES users(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Org membership: any member can add users, only admins can remove them
CREATE TABLE org_members (
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin', 'member')),
    added_by    UUID REFERENCES users(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, user_id)
);

CREATE INDEX org_members_user_id_idx ON org_members (user_id);

-- Diagnosis: named work areas tied to a watershed boundary (owned by the Diagnose module)
CREATE TABLE diagnosis (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                  TEXT NOT NULL,
    owner_id              UUID NOT NULL REFERENCES users(id),
    watershed_id          TEXT NOT NULL DEFAULT '',
    watershed_name        TEXT NOT NULL DEFAULT '',
    watershed_geom        GEOMETRY(Geometry, 4326),
    seed_lng              DOUBLE PRECISION NOT NULL,
    seed_lat              DOUBLE PRECISION NOT NULL,
    qfield_project_id     TEXT,
    qfield_project_owner  UUID REFERENCES users(id),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX diagnosis_watershed_geom_idx ON diagnosis USING GIST (watershed_geom);
CREATE INDEX diagnosis_owner_id_idx ON diagnosis (owner_id);

-- Assess projects: named work areas owned by the Assess module
CREATE TABLE assess_projects (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL,
    owner_id      UUID NOT NULL REFERENCES users(id),
    description   TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'draft'
                  CHECK (status IN ('draft', 'active', 'archived')),
    odk_project_id TEXT,
    -- Metabase dashboard to embed for this project. Each project's dashboard is
    -- built on that project's form data; NULL falls back to the app default.
    metabase_dashboard_id INTEGER,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX assess_projects_owner_id_idx ON assess_projects (owner_id);

ALTER TABLE assess_projects
    ADD CONSTRAINT assess_projects_owner_odk_project_id_key
    UNIQUE (owner_id, odk_project_id);

-- Assess sharing: direct user grants and org grants (mirrors the diagnosis
-- sharing model). A user can view an assess project if they own it, were
-- granted direct access, or belong to an org that was granted access.
CREATE TABLE assess_project_users (
    project_id    UUID NOT NULL REFERENCES assess_projects(id) ON DELETE CASCADE,
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role          TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin', 'member')),
    added_by      UUID REFERENCES users(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, user_id)
);

CREATE TABLE assess_project_orgs (
    project_id    UUID NOT NULL REFERENCES assess_projects(id) ON DELETE CASCADE,
    org_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    added_by      UUID REFERENCES users(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, org_id)
);

CREATE INDEX assess_project_users_user_id_idx ON assess_project_users (user_id);
CREATE INDEX assess_project_orgs_org_id_idx ON assess_project_orgs (org_id);

-- Diagnosis sharing: direct user grants and org grants (owner manages both)
CREATE TABLE diagnosis_users (
    diagnosis_id  UUID NOT NULL REFERENCES diagnosis(id) ON DELETE CASCADE,
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role          TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin', 'member')),
    added_by      UUID REFERENCES users(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (diagnosis_id, user_id)
);

CREATE TABLE diagnosis_orgs (
    diagnosis_id  UUID NOT NULL REFERENCES diagnosis(id) ON DELETE CASCADE,
    org_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    added_by      UUID REFERENCES users(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (diagnosis_id, org_id)
);

CREATE INDEX diagnosis_users_user_id_idx ON diagnosis_users (user_id);
CREATE INDEX diagnosis_orgs_org_id_idx ON diagnosis_orgs (org_id);

-- Observation zones: polygon with text label, observations, and questions (scoped to a diagnosis project)
CREATE TABLE observation_zones (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id    UUID NOT NULL REFERENCES diagnosis(id) ON DELETE CASCADE,
    geom          GEOMETRY(Geometry, 4326) NOT NULL,
    text          TEXT NOT NULL DEFAULT '',
    observations  TEXT NOT NULL DEFAULT '',
    questions     TEXT NOT NULL DEFAULT '',
    color         TEXT NOT NULL DEFAULT '#0d983b',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by    TEXT,
    CONSTRAINT observation_zones_geom_is_polygon CHECK (
        GeometryType(geom) IN ('POLYGON', 'MULTIPOLYGON')
    )
);

CREATE INDEX observation_zones_geom_idx ON observation_zones USING GIST (geom);
CREATE INDEX observation_zones_project_id_idx ON observation_zones (project_id);

-- Hypotheses: testable statements linked to observation zones and field notes
CREATE TABLE hypotheses (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   UUID NOT NULL REFERENCES diagnosis(id) ON DELETE CASCADE,
    hypothesis   TEXT NOT NULL DEFAULT '',
    root_cause   TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'untested'
                 CHECK (status IN ('untested', 'validated', 'invalidated', 'discarded')),
    created_by   UUID REFERENCES users(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX hypotheses_project_id_idx ON hypotheses (project_id);

-- Many-to-many: hypotheses ↔ observation zones
CREATE TABLE hypothesis_observation_zones (
    hypothesis_id  UUID NOT NULL REFERENCES hypotheses(id) ON DELETE CASCADE,
    zone_id        UUID NOT NULL REFERENCES observation_zones(id) ON DELETE CASCADE,
    PRIMARY KEY (hypothesis_id, zone_id)
);

CREATE INDEX hypothesis_observation_zones_zone_id_idx ON hypothesis_observation_zones (zone_id);

-- Field notes: geotagged point with title, text, and optional media (scoped to a diagnosis project)
CREATE TABLE field_notes (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id     UUID NOT NULL REFERENCES diagnosis(id) ON DELETE CASCADE,
    hypothesis_id  UUID REFERENCES hypotheses(id) ON DELETE SET NULL,
    geom           GEOMETRY(Point, 4326) NOT NULL,
    title          TEXT NOT NULL DEFAULT '',
    text           TEXT NOT NULL DEFAULT '',
    photo_path     TEXT,
    audio_path     TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by     TEXT
);

CREATE INDEX field_notes_geom_idx ON field_notes USING GIST (geom);
CREATE INDEX field_notes_project_id_idx ON field_notes (project_id);
CREATE INDEX field_notes_hypothesis_id_idx ON field_notes (hypothesis_id);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER user_qfield_credentials_updated_at
    BEFORE UPDATE ON user_qfield_credentials
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER organizations_updated_at
    BEFORE UPDATE ON organizations
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER diagnosis_updated_at
    BEFORE UPDATE ON diagnosis
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER assess_projects_updated_at
    BEFORE UPDATE ON assess_projects
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER observation_zones_updated_at
    BEFORE UPDATE ON observation_zones
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER hypotheses_updated_at
    BEFORE UPDATE ON hypotheses
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER field_notes_updated_at
    BEFORE UPDATE ON field_notes
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();