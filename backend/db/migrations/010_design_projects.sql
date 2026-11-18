-- Design module: saved AOIs for solution site-suitability.
-- Idempotent (re-applied on every deploy).

CREATE TABLE IF NOT EXISTS design_projects (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                 TEXT NOT NULL,
    owner_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    aoi_name             TEXT NOT NULL DEFAULT '',
    aoi_geom             GEOMETRY(Geometry, 4326) NOT NULL,
    aoi_source           TEXT NOT NULL DEFAULT 'point'
                         CHECK (aoi_source IN ('point', 'village', 'custom', 'diagnosis')),
    source_diagnosis_id  UUID REFERENCES diagnosis(id) ON DELETE SET NULL,
    seed_lng             DOUBLE PRECISION NOT NULL,
    seed_lat             DOUBLE PRECISION NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS design_projects_aoi_geom_idx ON design_projects USING GIST (aoi_geom);
CREATE INDEX IF NOT EXISTS design_projects_owner_id_idx ON design_projects (owner_id);
