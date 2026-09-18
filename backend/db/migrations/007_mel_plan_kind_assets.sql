-- MEL plan vs implementation + farm-pond assets (one_time allocation).

ALTER TABLE mel_plans
    ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'plan'
        CHECK (kind IN ('plan', 'implementation'));

CREATE INDEX IF NOT EXISTS mel_plans_kind_idx ON mel_plans (kind);

CREATE TABLE IF NOT EXISTS mel_assets (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL REFERENCES assess_projects(id) ON DELETE CASCADE,
    plan_id             UUID NOT NULL REFERENCES mel_plans(id) ON DELETE CASCADE,
    intervention_slug   TEXT NOT NULL,
    label               TEXT NOT NULL DEFAULT '',
    ot_answers          JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by          UUID REFERENCES users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS mel_assets_project_id_idx ON mel_assets (project_id);
CREATE INDEX IF NOT EXISTS mel_assets_plan_id_idx ON mel_assets (plan_id);

DROP TRIGGER IF EXISTS mel_assets_updated_at ON mel_assets;
CREATE TRIGGER mel_assets_updated_at
    BEFORE UPDATE ON mel_assets
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
