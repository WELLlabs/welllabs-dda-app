-- Landscape objective selected when validating / invalidating a hypothesis.

ALTER TABLE hypotheses
    ADD COLUMN IF NOT EXISTS landscape_objective_id TEXT NOT NULL DEFAULT '';
