-- Migration: assess per-project Metabase dashboards + shared membership
--
-- init.sql only runs on a fresh database. Run this once against any existing
-- database to bring it up to date:
--   psql "$DATABASE_URL" -f db/migrations/001_assess_metabase_sharing.sql
--
-- Idempotent: safe to run more than once.

BEGIN;

-- Per-project dashboard mapping.
ALTER TABLE assess_projects
    ADD COLUMN IF NOT EXISTS metabase_dashboard_id INTEGER;

-- Direct user grants.
CREATE TABLE IF NOT EXISTS assess_project_users (
    project_id    UUID NOT NULL REFERENCES assess_projects(id) ON DELETE CASCADE,
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role          TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin', 'member')),
    added_by      UUID REFERENCES users(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, user_id)
);

-- Org grants.
CREATE TABLE IF NOT EXISTS assess_project_orgs (
    project_id    UUID NOT NULL REFERENCES assess_projects(id) ON DELETE CASCADE,
    org_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    added_by      UUID REFERENCES users(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, org_id)
);

CREATE INDEX IF NOT EXISTS assess_project_users_user_id_idx ON assess_project_users (user_id);
CREATE INDEX IF NOT EXISTS assess_project_orgs_org_id_idx ON assess_project_orgs (org_id);

COMMIT;
