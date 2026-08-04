-- Clean-slate auth cutover for existing volumes.
-- Prefer `docker compose down -v` locally; this migration is destructive for auth rows.

DROP TABLE IF EXISTS sessions CASCADE;
DROP TABLE IF EXISTS oauth_account CASCADE;
DROP TABLE IF EXISTS user_qfield_credentials CASCADE;

-- Recreate users in FastAPI Users shape (destroys existing accounts)
DROP TABLE IF EXISTS users CASCADE;

CREATE TABLE users (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email            TEXT NOT NULL UNIQUE,
    hashed_password  TEXT,  -- NULL for Google/OAuth-only users
    is_active        BOOLEAN NOT NULL DEFAULT true,
    is_superuser     BOOLEAN NOT NULL DEFAULT false,
    is_verified      BOOLEAN NOT NULL DEFAULT false,
    name             TEXT NOT NULL DEFAULT '',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE oauth_account (
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

CREATE INDEX oauth_account_user_id_idx ON oauth_account (user_id);

CREATE TABLE user_qfield_credentials (
    user_id                  UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    qfield_username          TEXT,
    qfield_token             TEXT,
    qfield_token_expires_at  TIMESTAMPTZ,
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER user_qfield_credentials_updated_at
    BEFORE UPDATE ON user_qfield_credentials
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
