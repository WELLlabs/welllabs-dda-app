-- Move QField tokens onto users; add ODK token columns; add field_notes.title.
-- Safe to run multiple times.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS qfield_username TEXT,
    ADD COLUMN IF NOT EXISTS qfield_token TEXT,
    ADD COLUMN IF NOT EXISTS qfield_token_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS odk_username TEXT,
    ADD COLUMN IF NOT EXISTS odk_token TEXT,
    ADD COLUMN IF NOT EXISTS odk_token_expires_at TIMESTAMPTZ;

-- Copy existing QField tokens into users (if the old table still exists)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'qfield_tokens'
    ) THEN
        UPDATE users u
        SET
            qfield_username = qt.qfield_username,
            qfield_token = qt.token,
            qfield_token_expires_at = qt.expires_at
        FROM qfield_tokens qt
        WHERE qt.user_id = u.id
          AND (u.qfield_token IS NULL OR u.qfield_token = '');

        DROP TRIGGER IF EXISTS qfield_tokens_updated_at ON qfield_tokens;
        DROP TABLE qfield_tokens;
    END IF;
END $$;

ALTER TABLE field_notes
    ADD COLUMN IF NOT EXISTS title TEXT NOT NULL DEFAULT '';
