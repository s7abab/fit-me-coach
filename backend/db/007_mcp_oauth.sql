-- Everything the MCP server's OAuth flow has to remember (app/mcp_auth.py), one row per thing:
--   client   an app that registered itself (Claude, Cursor...)
--   request  a sign-in that is in progress: lives for 10 minutes
--   code     a one-time authorization code: lives for 5 minutes
--   access   an access token: lives for 1 hour
--   refresh  a refresh token: lives for 30 days, replaced every time it is used
CREATE TABLE IF NOT EXISTS mcp_oauth (
    kind        text NOT NULL CHECK (kind IN ('client', 'request', 'code', 'access', 'refresh')),
    key_hash    text NOT NULL,                 -- SHA-256 of the client id / code / token: the secret itself is never stored
    data        jsonb NOT NULL,
    user_id     bigint REFERENCES users(id) ON DELETE CASCADE,
    grant_id    text,                          -- an access token and its refresh token share one, so they are revoked together
    expires_at  timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (kind, key_hash)
);
CREATE INDEX IF NOT EXISTS mcp_oauth_grant_idx ON mcp_oauth (grant_id) WHERE grant_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS mcp_oauth_expires_idx ON mcp_oauth (expires_at) WHERE expires_at IS NOT NULL;
