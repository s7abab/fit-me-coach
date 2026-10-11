"""Sign-in for the MCP server.

An MCP client (Claude, Cursor...) gets a token for one user with the standard OAuth flow:

  1. the client registers itself and sends the user's browser to /authorize
  2. we send the browser on to Google to sign in (the same Google client as the web app)
  3. Google sends it back to /oauth/google/callback, and we ask "allow <client> to read your data?"
  4. on "Allow" the client gets a one-time code, which it swaps at /token for an access + refresh token

The MCP SDK serves /authorize, /token, /register and /revoke and checks PKCE, redirect URIs and
expiry. This file is the part it leaves to us: what to remember, and who the user is.
"""
import hashlib
import hmac
import html
import logging
import secrets
import ssl
import time
from functools import partial
from urllib.parse import urlencode, urlparse

import anyio
import certifi
import httpx
import jwt
from mcp.server.auth.provider import (
    AccessToken, AuthorizationCode, AuthorizationParams, AuthorizeError, RefreshToken, RegistrationError,
    TokenError, construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from psycopg.types.json import Jsonb
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from app.auth import get_or_create_user
from app.config import settings
from app.db import get_conn
from app.google_health import TOKEN_URL, decrypt_token, encrypt_token

logger = logging.getLogger("fitmecoach.mcp")

PUBLIC_URL = settings.public_url.rstrip("/")
RESOURCE_URL = f"{PUBLIC_URL}/mcp"                             # what tokens are issued for
GOOGLE_CALLBACK_URL = f"{PUBLIC_URL}/oauth/google/callback"    # must be an authorised redirect URI of the Google client
SCOPE = "health:read"

REQUEST_TTL = 10 * 60
CODE_TTL = 5 * 60
ACCESS_TTL = 60 * 60
REFRESH_TTL = 30 * 24 * 60 * 60

CONSENT_COOKIE = "mcp_consent"
LOOPBACK = ("localhost", "127.0.0.1", "::1")


def _hash(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


def _same_url(a, b):
    return str(a).rstrip("/").lower() == str(b).rstrip("/").lower()


# ---------- Storage: one table, see db/007_mcp_oauth.sql ----------

class Store:
    def put(self, kind, key, data, ttl=None, user_id=None, grant_id=None):
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO mcp_oauth (kind, key_hash, data, user_id, grant_id, expires_at)
                VALUES (%s, %s, %s, %s, %s, now() + %s::double precision * interval '1 second')
                ON CONFLICT (kind, key_hash) DO UPDATE
                SET data = EXCLUDED.data, user_id = EXCLUDED.user_id, expires_at = EXCLUDED.expires_at
                """,
                (kind, _hash(key), Jsonb(data), user_id, grant_id, ttl),
            )

    def get(self, kind, key):
        with get_conn() as conn:
            row = conn.execute(
                "SELECT data FROM mcp_oauth WHERE kind = %s AND key_hash = %s AND (expires_at IS NULL OR expires_at > now())",
                (kind, _hash(key)),
            ).fetchone()
        return row[0] if row else None

    def pop(self, kind, key):
        """Read and delete in one step, so a code or refresh token can only ever be used once."""
        with get_conn() as conn:
            row = conn.execute(
                """
                DELETE FROM mcp_oauth WHERE kind = %s AND key_hash = %s AND (expires_at IS NULL OR expires_at > now())
                RETURNING data
                """,
                (kind, _hash(key)),
            ).fetchone()
        return row[0] if row else None

    def delete_grant(self, grant_id):
        with get_conn() as conn:
            conn.execute("DELETE FROM mcp_oauth WHERE grant_id = %s", (grant_id,))

    def delete_expired(self):
        with get_conn() as conn:
            conn.execute("DELETE FROM mcp_oauth WHERE expires_at < now()")


store = Store()


async def _db(fn, *args, **kwargs):
    # The database driver blocks: run it on a worker thread so other requests keep moving
    return await anyio.to_thread.run_sync(partial(fn, *args, **kwargs))


# ---------- What the MCP SDK calls ----------

class CoachOAuthProvider:
    async def get_client(self, client_id):
        data = await _db(store.get, "client", client_id)
        if data is None:
            return None
        if data.get("client_secret"):
            data["client_secret"] = decrypt_token(data["client_secret"])
        return OAuthClientInformationFull.model_validate(data)

    async def register_client(self, client_info):
        for uri in client_info.redirect_uris or []:
            # Apps on the user's own machine use http://localhost or their own scheme (cursor://...).
            # Anything on the web must be https.
            if uri.scheme in ("javascript", "data", "file") or (uri.scheme == "http" and uri.host not in LOOPBACK):
                raise RegistrationError("invalid_redirect_uri", f"Redirect URI {uri} must use https")
        data = client_info.model_dump(mode="json", exclude_none=True)
        if data.get("client_secret"):
            data["client_secret"] = encrypt_token(data["client_secret"])
        await _db(store.put, "client", client_info.client_id, data)

    async def authorize(self, client, params: AuthorizationParams):
        # Tokens only ever work for this server
        if params.resource and not _same_url(params.resource, RESOURCE_URL):
            raise AuthorizeError("invalid_target", f"This server only issues tokens for {RESOURCE_URL}")

        request_id = secrets.token_urlsafe(32)
        await _db(store.delete_expired)
        await _db(store.put, "request", request_id, {
            "client_id": client.client_id,
            "client_name": client.client_name,
            "state": params.state,
            "code_challenge": params.code_challenge,
            "redirect_uri": str(params.redirect_uri),
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
        }, ttl=REQUEST_TTL)

        # Only who they are: the MCP server reads data the web app has already synced
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
            "client_id": settings.google_client_id,
            "redirect_uri": GOOGLE_CALLBACK_URL,
            "response_type": "code",
            "scope": "openid email profile",
            "state": request_id,
        })

    async def load_authorization_code(self, client, authorization_code):
        data = await _db(store.get, "code", authorization_code)
        if data is None:
            return None
        return AuthorizationCode(
            code=authorization_code, scopes=[SCOPE], expires_at=data["expires_at"], client_id=data["client_id"],
            code_challenge=data["code_challenge"], redirect_uri=data["redirect_uri"],
            redirect_uri_provided_explicitly=data["redirect_uri_provided_explicitly"],
            resource=RESOURCE_URL, subject=str(data["user_id"]),
        )

    async def exchange_authorization_code(self, client, authorization_code):
        data = await _db(store.pop, "code", authorization_code.code)
        if data is None:
            raise TokenError("invalid_grant", "authorization code has already been used")
        return await self._issue_tokens(data["client_id"], data["user_id"])

    async def load_refresh_token(self, client, refresh_token):
        data = await _db(store.get, "refresh", refresh_token)
        if data is None:
            return None
        return RefreshToken(token=refresh_token, client_id=data["client_id"], scopes=[SCOPE],
                            expires_at=data["expires_at"], resource=RESOURCE_URL, subject=str(data["user_id"]))

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        data = await _db(store.pop, "refresh", refresh_token.token)
        if data is None:
            raise TokenError("invalid_grant", "refresh token has already been used")
        await _db(store.delete_grant, data["grant_id"])     # the old access token stops working too
        return await self._issue_tokens(data["client_id"], data["user_id"])

    async def load_access_token(self, token):
        data = await _db(store.get, "access", token)
        if data is None:
            return None
        return AccessToken(token=token, client_id=data["client_id"], scopes=[SCOPE], expires_at=data["expires_at"],
                           resource=RESOURCE_URL, subject=str(data["user_id"]))

    async def revoke_token(self, token):
        kind = "refresh" if isinstance(token, RefreshToken) else "access"
        data = await _db(store.get, kind, token.token)
        if data:
            await _db(store.delete_grant, data["grant_id"])

    async def _issue_tokens(self, client_id, user_id):
        access, refresh, grant_id = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(16)
        now = int(time.time())
        for kind, token, ttl in (("access", access, ACCESS_TTL), ("refresh", refresh, REFRESH_TTL)):
            data = {"client_id": client_id, "user_id": user_id, "grant_id": grant_id, "expires_at": now + ttl}
            await _db(store.put, kind, token, data, ttl=ttl, user_id=user_id, grant_id=grant_id)
        return OAuthToken(access_token=access, token_type="Bearer", expires_in=ACCESS_TTL, scope=SCOPE,
                          refresh_token=refresh)


# ---------- Google sign-in and the "Allow access?" page ----------

# certifi's certificates, like httpx uses: Python on macOS often has none of its own and the download fails
_google_keys = jwt.PyJWKClient("https://www.googleapis.com/oauth2/v3/certs",
                               ssl_context=ssl.create_default_context(cafile=certifi.where()))


def google_identity(code):
    """Swap Google's one-time code for who signed in. Returns Google's verified claims (sub, email, name...)."""
    res = httpx.post(TOKEN_URL, timeout=15, data={
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": GOOGLE_CALLBACK_URL,
    })
    res.raise_for_status()
    id_token = res.json()["id_token"]
    return jwt.decode(
        id_token, _google_keys.get_signing_key_from_jwt(id_token).key, algorithms=["RS256"],
        audience=settings.google_client_id, issuer=["https://accounts.google.com", "accounts.google.com"],
    )


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fit Me Coach</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #f6f7f9; color: #16181d; margin: 0; padding: 16px; }}
  main {{ max-width: 420px; margin: 12vh auto 0; background: #fff; border-radius: 12px; padding: 28px; box-shadow: 0 1px 4px #0002; }}
  h1 {{ font-size: 20px; margin: 0 0 12px; }} p {{ line-height: 1.5; margin: 0 0 12px; }} small {{ color: #667; }}
  form {{ display: flex; gap: 10px; margin-top: 20px; }}
  button {{ flex: 1; padding: 11px; border-radius: 8px; border: 1px solid #ccd; background: #fff; font-size: 15px; cursor: pointer; }}
  button.allow {{ background: #16181d; color: #fff; border-color: #16181d; }}
</style></head><body><main>{body}</main></body></html>"""

# Never let another site show these pages inside a frame and trick the user into clicking "Allow"
PAGE_HEADERS = {"Cache-Control": "no-store", "X-Frame-Options": "DENY", "Content-Security-Policy": "frame-ancestors 'none'"}


def _page(body, status=200):
    return HTMLResponse(PAGE.format(body=body), status_code=status, headers=PAGE_HEADERS)


def _error_page(message):
    return _page(f"<h1>Could not connect</h1><p>{html.escape(message)}</p>", status=400)


def _back_to_client(pending, **params):
    url = construct_redirect_uri(pending["redirect_uri"], state=pending["state"], **params)
    return RedirectResponse(url, status_code=302, headers={"Cache-Control": "no-store"})


async def google_callback(request: Request):
    """Google sends the browser here after sign-in. Work out who it is, then ask them to approve the client."""
    request_id = request.query_params.get("state", "")
    pending = await _db(store.get, "request", request_id)
    if pending is None:
        return _error_page("This sign-in link has expired. Go back to your app and connect again.")

    code = request.query_params.get("code")
    if not code:      # the user pressed "Cancel" on Google's screen
        await _db(store.pop, "request", request_id)
        return _back_to_client(pending, error="access_denied")

    try:
        identity = await _db(google_identity, code)
    except (httpx.HTTPError, jwt.PyJWTError, KeyError):
        logger.exception("Google sign-in failed")
        return _error_page("Google sign-in failed. Go back to your app and connect again.")
    if identity.get("email_verified") is not True:
        return _error_page("Your Google account has no verified email address.")

    def find_user():
        with get_conn() as conn:
            return get_or_create_user(conn, identity["sub"], identity["email"], identity.get("name"))

    user_id = await _db(find_user)
    if user_id is None:
        return _error_page("This email already belongs to another account.")

    # The cookie ties the "Allow" click to this browser: knowing the link alone is not enough
    consent = secrets.token_urlsafe(32)
    pending.update(user_id=user_id, consent_hash=_hash(consent))
    await _db(store.put, "request", request_id, pending, ttl=REQUEST_TTL)

    client_name = html.escape(pending["client_name"] or "An app")
    goes_to = html.escape(urlparse(pending["redirect_uri"]).netloc or pending["redirect_uri"])
    response = _page(f"""
        <h1>Allow access to your health data?</h1>
        <p><b>{client_name}</b> wants to read your Fit Me Coach profile, sleep, activity, heart and workout data.</p>
        <p><small>Signed in as {html.escape(identity["email"])}. You will be sent to {goes_to}.</small></p>
        <form method="post" action="/oauth/consent">
          <input type="hidden" name="request_id" value="{html.escape(request_id)}">
          <button name="action" value="deny">Cancel</button>
          <button name="action" value="allow" class="allow">Allow</button>
        </form>""")
    response.set_cookie(CONSENT_COOKIE, consent, max_age=REQUEST_TTL, path="/oauth", httponly=True,
                        samesite="lax", secure=PUBLIC_URL.startswith("https://"))
    return response


async def consent(request: Request):
    """The user pressed Allow or Cancel. On Allow, hand the client its one-time code."""
    form = await request.form()
    request_id = str(form.get("request_id", ""))
    pending = await _db(store.get, "request", request_id)

    cookie = request.cookies.get(CONSENT_COOKIE, "")
    approved_here = (
        pending is not None and pending.get("consent_hash")
        and hmac.compare_digest(_hash(cookie), pending["consent_hash"])
        and request.headers.get("origin", PUBLIC_URL) == PUBLIC_URL
    )
    # pop: the same approval can never be replayed
    if not approved_here or await _db(store.pop, "request", request_id) is None:
        return _error_page("This sign-in link has expired. Go back to your app and connect again.")

    if form.get("action") != "allow":
        response = _back_to_client(pending, error="access_denied")
    else:
        code = secrets.token_urlsafe(32)
        await _db(store.put, "code", code, {
            "client_id": pending["client_id"],
            "user_id": pending["user_id"],
            "code_challenge": pending["code_challenge"],
            "redirect_uri": pending["redirect_uri"],
            "redirect_uri_provided_explicitly": pending["redirect_uri_provided_explicitly"],
            "expires_at": time.time() + CODE_TTL,
        }, ttl=CODE_TTL, user_id=pending["user_id"])
        logger.info("mcp access granted user=%s client=%s", pending["user_id"], pending["client_id"])
        response = _back_to_client(pending, code=code)
    response.delete_cookie(CONSENT_COOKIE, path="/oauth")
    return response
