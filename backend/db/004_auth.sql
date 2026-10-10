-- Google sign-in: "sub" is Google's permanent id for the account (emails can change)
ALTER TABLE users ADD COLUMN IF NOT EXISTS google_sub text UNIQUE;

-- One row per user who has connected Google Health
CREATE TABLE IF NOT EXISTS google_health_connections (
    user_id                  bigint PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    refresh_token_encrypted  text NOT NULL,                 -- encrypted with TOKEN_ENCRYPTION_KEY, never stored plain
    scopes                   text[] NOT NULL,               -- what the user actually agreed to share
    status                   text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'expired')),
    connected_at             timestamptz NOT NULL DEFAULT now(),
    last_synced_at           timestamptz,
    last_error               text
);

-- When the current/last sync began: stops two requests syncing the same user at once
ALTER TABLE google_health_connections ADD COLUMN IF NOT EXISTS sync_started_at timestamptz;
