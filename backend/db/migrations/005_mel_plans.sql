-- MEL plans: a project can have many plans; each plan is one intervention.
-- Forms belong to a plan (and still carry project_id for project-scoped queries).

CREATE TABLE IF NOT EXISTS mel_plans (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL REFERENCES assess_projects(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    intervention_slug   TEXT NOT NULL,
    plan_json           JSONB,
    created_by          UUID REFERENCES users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS mel_plans_project_id_idx ON mel_plans (project_id);
CREATE INDEX IF NOT EXISTS mel_plans_intervention_slug_idx ON mel_plans (intervention_slug);

-- Backfill: one plan per legacy MEL project that had a bound intervention.
INSERT INTO mel_plans (project_id, name, intervention_slug, plan_json, created_by, created_at, updated_at)
SELECT
    p.id,
    COALESCE(NULLIF(TRIM(p.name), ''), 'MEL plan'),
    p.intervention_slug,
    p.plan_json,
    p.owner_id,
    p.created_at,
    p.updated_at
FROM assess_projects p
WHERE p.kind = 'mel'
  AND p.intervention_slug IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM mel_plans mp WHERE mp.project_id = p.id
  );

ALTER TABLE mel_forms
    ADD COLUMN IF NOT EXISTS plan_id UUID REFERENCES mel_plans(id) ON DELETE CASCADE;

-- Attach existing forms to the (single) backfilled plan for their project.
UPDATE mel_forms mf
SET plan_id = mp.id
FROM mel_plans mp
WHERE mf.plan_id IS NULL
  AND mf.project_id = mp.project_id;

-- Any remaining orphans: create a placeholder plan from project name.
INSERT INTO mel_plans (project_id, name, intervention_slug, created_by)
SELECT DISTINCT
    mf.project_id,
    COALESCE(NULLIF(TRIM(p.name), ''), 'MEL plan') || ' (legacy)',
    COALESCE(p.intervention_slug, 'unknown'),
    p.owner_id
FROM mel_forms mf
JOIN assess_projects p ON p.id = mf.project_id
WHERE mf.plan_id IS NULL;

UPDATE mel_forms mf
SET plan_id = mp.id
FROM mel_plans mp
WHERE mf.plan_id IS NULL
  AND mf.project_id = mp.project_id;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'mel_forms' AND column_name = 'plan_id'
    ) THEN
        ALTER TABLE mel_forms ALTER COLUMN plan_id SET NOT NULL;
    END IF;
END $$;

ALTER TABLE mel_forms DROP CONSTRAINT IF EXISTS mel_forms_project_id_xml_form_id_key;
ALTER TABLE mel_forms DROP CONSTRAINT IF EXISTS mel_forms_plan_id_xml_form_id_key;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'mel_forms_plan_id_xml_form_id_key'
    ) THEN
        ALTER TABLE mel_forms
            ADD CONSTRAINT mel_forms_plan_id_xml_form_id_key UNIQUE (plan_id, xml_form_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS mel_forms_plan_id_idx ON mel_forms (plan_id);

-- Project no longer owns a single intervention; keep columns for history but clear
-- them on MEL rows so new code does not treat them as authoritative.
UPDATE assess_projects
SET intervention_slug = NULL, plan_json = NULL
WHERE kind = 'mel';
