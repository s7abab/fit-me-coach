import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.db import get_conn

# The Next.js server signs a token like this for every request it forwards (see frontend/lib/backend.ts)
ISSUER = "fit-me-coach-web"
AUDIENCE = "fit-me-coach-api"

bearer = HTTPBearer(auto_error=False)


def verify_token(token):
    """Check the signature and expiry. Returns the claims, or raises jwt.InvalidTokenError."""
    return jwt.decode(
        token, settings.api_jwt_secret, algorithms=["HS256"],
        issuer=ISSUER, audience=AUDIENCE, options={"require": ["exp", "sub", "email"]},
    )


def get_or_create_user(conn, google_sub, email, name):
    row = conn.execute("SELECT id FROM users WHERE google_sub = %s", (google_sub,)).fetchone()
    if row:
        return row[0]
    # First sign-in. If a row with this email exists and has no Google account yet, link it.
    row = conn.execute(
        """
        INSERT INTO users (name, email, google_sub) VALUES (%s, %s, %s)
        ON CONFLICT (email) DO UPDATE SET google_sub = EXCLUDED.google_sub WHERE users.google_sub IS NULL
        RETURNING id
        """,
        (name or email.split("@")[0], email, google_sub),
    ).fetchone()
    return row[0] if row else None


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> int:
    """FastAPI dependency: the id of the signed-in user. Every private route uses this."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    try:
        claims = verify_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Not signed in")

    with get_conn() as conn:
        user_id = get_or_create_user(conn, claims["sub"], claims["email"], claims.get("name"))
    if user_id is None:
        raise HTTPException(status_code=409, detail="This email already belongs to another account")
    return user_id
