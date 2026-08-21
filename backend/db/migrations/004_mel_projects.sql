-- MEL projects: extend assess_projects + track published forms per project.
-- MEL rows keep odk_project_id NULL so UNIQUE(owner_id, odk_project_id) allows
-- multiple MEL projects per owner while all forms publish to env ODK_PROJECT_ID.

ALTER TABLE assess_projects
    ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'odk_sync';

ALTER TABLE assess_projects
    DROP CONSTRAINT IF EXISTS assess_projects_kind_check;

ALTER TABLE assess_projects
    ADD CONSTRAINT assess_projects_kind_check
    CHECK (kind IN ('odk_sync', 'mel'));

ALTER TABLE assess_projects
    ADD COLUMN IF NOT EXISTS intervention_slug TEXT;

ALTER TABLE assess_projects
    ADD COLUMN IF NOT EXISTS plan_json JSONB;

-- Existing rows with an ODK id stay odk_sync; leave intervention_slug null.
UPDATE assess_projects
SET kind = 'odk_sync'
WHERE odk_project_id IS NOT NULL AND kind IS DISTINCT FROM 'odk_sync';

CREATE TABLE IF NOT EXISTS mel_forms (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES assess_projects(id) ON DELETE CASCADE,
    xml_form_id     TEXT NOT NULL,
    name            TEXT NOT NULL,
    package_id      TEXT,
    package_title   TEXT,
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, xml_form_id)
);

CREATE INDEX IF NOT EXISTS mel_forms_project_id_idx ON mel_forms (project_id);
CREATE INDEX IF NOT EXISTS assess_projects_kind_idx ON assess_projects (kind);
CREATE INDEX IF NOT EXISTS assess_projects_intervention_slug_idx
    ON assess_projects (intervention_slug)
    WHERE intervention_slug IS NOT NULL;
