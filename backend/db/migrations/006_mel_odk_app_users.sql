-- Store ODK Central App User tokens for MEL Collect QR codes.
-- Tokens are only returned by Central when the app user is created.

CREATE TABLE IF NOT EXISTS mel_odk_app_users (
    odk_project_id  INTEGER PRIMARY KEY,
    app_user_id     INTEGER NOT NULL,
    display_name    TEXT NOT NULL,
    token           TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
