-- Local CM readings for MEL implementations (sample / offline dashboards).
CREATE TABLE IF NOT EXISTS mel_cm_readings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES assess_projects(id) ON DELETE CASCADE,
    plan_id UUID NOT NULL REFERENCES mel_plans(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL REFERENCES mel_assets(id) ON DELETE CASCADE,
    reading_date DATE,
    rainfall_mm DOUBLE PRECISION,
    water_level_m DOUBLE PRECISION,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS mel_cm_readings_plan_id_idx ON mel_cm_readings (plan_id);
CREATE INDEX IF NOT EXISTS mel_cm_readings_asset_id_idx ON mel_cm_readings (asset_id);
CREATE INDEX IF NOT EXISTS mel_cm_readings_date_idx ON mel_cm_readings (reading_date);
