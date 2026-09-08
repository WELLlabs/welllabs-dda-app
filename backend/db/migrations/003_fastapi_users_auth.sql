-- FastAPI Users auth cutover.
--
-- IMPORTANT: early versions of this file dropped `users` on every deploy.
-- That is no longer allowed. If the FastAPI Users schema is already present
-- (column users.is_verified), this migration is a no-op for data and only
-- ensures companion tables/triggers exist.
--
-- If a truly legacy users table is detected, refuse to run automatically so
-- accounts / projects on beta or prod cannot be wiped by CodeDeploy.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'users'
          AND column_name = 'is_verified'
    ) THEN
        RAISE NOTICE '003_fastapi_users_auth: FastAPI Users schema present — skipping destructive cutover';
        RETURN;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'users'
    ) THEN
        RAISE EXCEPTION
            '003_fastapi_users_auth: legacy users table detected without is_verified. '
            'Refusing automatic destructive auth cutover. Take a backup and run a one-shot '
            'manual cutover; never let CodeDeploy wipe accounts/projects.';
    END IF;

    -- Fresh DB without init.sql users table (should not happen on deploy hosts).
    CREATE TABLE users (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email            TEXT NOT NULL UNIQUE,
        hashed_password  TEXT,
        is_active        BOOLEAN NOT NULL DEFAULT true,
        is_superuser     BOOLEAN NOT NULL DEFAULT false,
        is_verified      BOOLEAN NOT NULL DEFAULT false,
        name             TEXT NOT NULL DEFAULT '',
        created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
    );
END $$;

CREATE TABLE IF NOT EXISTS oauth_account (
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

CREATE INDEX IF NOT EXISTS oauth_account_user_id_idx ON oauth_account (user_id);

CREATE TABLE IF NOT EXISTS user_qfield_credentials (
    user_id                  UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    qfield_username          TEXT,
    qfield_token             TEXT,
    qfield_token_expires_at  TIMESTAMPTZ,
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS users_updated_at ON users;
CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS user_qfield_credentials_updated_at ON user_qfield_credentials;
CREATE TRIGGER user_qfield_credentials_updated_at
    BEFORE UPDATE ON user_qfield_credentials
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
