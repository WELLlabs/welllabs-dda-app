-- Migrate existing databases: observation_zones columns + hypotheses tables.
-- Safe to run multiple times (uses IF NOT EXISTS / conditional checks).

-- observation_zones: replace description with observations + questions
ALTER TABLE observation_zones ADD COLUMN IF NOT EXISTS observations TEXT NOT NULL DEFAULT '';
ALTER TABLE observation_zones ADD COLUMN IF NOT EXISTS questions TEXT NOT NULL DEFAULT '';

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'observation_zones'
          AND column_name = 'description'
    ) THEN
        UPDATE observation_zones
        SET observations = COALESCE(description, '')
        WHERE observations = '' AND description IS NOT NULL AND description <> '';
        ALTER TABLE observation_zones DROP COLUMN description;
    END IF;
END $$;

-- hypotheses
CREATE TABLE IF NOT EXISTS hypotheses (
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

CREATE INDEX IF NOT EXISTS hypotheses_project_id_idx ON hypotheses (project_id);

CREATE TABLE IF NOT EXISTS hypothesis_observation_zones (
    hypothesis_id  UUID NOT NULL REFERENCES hypotheses(id) ON DELETE CASCADE,
    zone_id        UUID NOT NULL REFERENCES observation_zones(id) ON DELETE CASCADE,
    PRIMARY KEY (hypothesis_id, zone_id)
);

CREATE INDEX IF NOT EXISTS hypothesis_observation_zones_zone_id_idx
    ON hypothesis_observation_zones (zone_id);

ALTER TABLE field_notes
    ADD COLUMN IF NOT EXISTS hypothesis_id UUID REFERENCES hypotheses(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS field_notes_hypothesis_id_idx ON field_notes (hypothesis_id);

DROP TRIGGER IF EXISTS hypotheses_updated_at ON hypotheses;
CREATE TRIGGER hypotheses_updated_at
    BEFORE UPDATE ON hypotheses
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
