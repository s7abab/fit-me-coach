import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

import app.main as main
import app.mcp_auth as mcp_auth
import app.mcp_server as mcp_server

REDIRECT_URI = "http://localhost:9999/callback"
VERIFIER = "v" * 64
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).decode().rstrip("=")
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


class MemoryStore:
    """The same five methods as mcp_auth.Store, kept in a dict instead of Postgres."""

    def __init__(self):
        self.rows = {}

    def put(self, kind, key, data, ttl=None, user_id=None, grant_id=None):
        self.rows[kind, key] = {"data": json.loads(json.dumps(data)), "grant_id": grant_id,
                                "expires": time.time() + ttl if ttl else None}

    def get(self, kind, key):
        row = self.rows.get((kind, key))
        if row is None or (row["expires"] and row["expires"] < time.time()):
            return None
        return json.loads(json.dumps(row["data"]))

    def pop(self, kind, key):
        data = self.get(kind, key)
        self.rows.pop((kind, key), None)
        return data

    def delete_grant(self, grant_id):
        self.rows = {k: row for k, row in self.rows.items() if row["grant_id"] != grant_id}

    def delete_expired(self):
        pass


@pytest.fixture(scope="module")
def client():
    # One client for the whole file: the MCP session manager can only be started once
    with TestClient(main.app, base_url="http://localhost:8000", follow_redirects=False) as c:
        yield c


@pytest.fixture(autouse=True)
def fakes(monkeypatch, client):
    client.cookies.clear()
    monkeypatch.setattr(mcp_auth, "store", MemoryStore())
    # Google says whoever's "code" this is: the code doubles as the user's name in these tests
    monkeypatch.setattr(mcp_auth, "google_identity", lambda code: {
        "sub": f"google-{code}", "email": f"{code}@example.com", "name": code, "email_verified": code != "unverified"})
    monkeypatch.setattr(mcp_auth, "get_or_create_user", lambda conn, sub, email, name: {"asha": 5, "ben": 6}[name])
    monkeypatch.setattr(mcp_auth, "get_conn", FakeConn)
    monkeypatch.setattr(mcp_server, "get_conn", FakeConn)
    # A tool that just reports whose data it was asked for
    monkeypatch.setattr(mcp_server, "run_tool", lambda conn, user_id, name, args: json.dumps({"user_id": user_id}))


class FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def register(client, **changes):
    body = {"client_name": "Test App", "redirect_uris": [REDIRECT_URI], "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"], **changes}
    return client.post("/register", json=body)


def start(client, client_id, **changes):
    """Step 1 and 2: /authorize, then come back from Google. Returns the request id and the consent page."""
    params = {"client_id": client_id, "response_type": "code", "redirect_uri": REDIRECT_URI, "state": "xyz",
              "code_challenge": CHALLENGE, "code_challenge_method": "S256", "resource": mcp_auth.RESOURCE_URL, **changes}
    r = client.get("/authorize", params=params)
    assert r.status_code == 302, r.text
    return parse_qs(urlparse(r.headers["location"]).query)


def sign_in(client, who="asha"):
    """The whole flow for one user. Returns the token response."""
    client_id = register(client).json()["client_id"]
    google = start(client, client_id)
    request_id = google["state"][0]
    assert client.get("/oauth/google/callback", params={"state": request_id, "code": who}).status_code == 200
    r = client.post("/oauth/consent", data={"request_id": request_id, "action": "allow"})
    back = parse_qs(urlparse(r.headers["location"]).query)
    assert back["state"] == ["xyz"]
    r = client.post("/token", data={"grant_type": "authorization_code", "code": back["code"][0], "client_id": client_id,
                                    "redirect_uri": REDIRECT_URI, "code_verifier": VERIFIER})
    assert r.status_code == 200, r.text
    return {**r.json(), "client_id": client_id, "code": back["code"][0]}


def call_tool(client, token, name="get_sleep"):
    r = client.post("/mcp", headers={**MCP_HEADERS, "Authorization": f"Bearer {token}"}, json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": {}}})
    return r


# ---------- Discovery ----------

def test_no_token_is_401_and_points_to_the_metadata(client):
    r = client.post("/mcp", headers=MCP_HEADERS, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert r.status_code == 401
    assert "/.well-known/oauth-protected-resource/mcp" in r.headers["www-authenticate"]


def test_metadata_describes_the_server(client):
    resource = client.get("/.well-known/oauth-protected-resource/mcp").json()
    assert resource["resource"] == mcp_auth.RESOURCE_URL
    server = client.get("/.well-known/oauth-authorization-server").json()
    assert server["registration_endpoint"].endswith("/register")
    assert server["code_challenge_methods_supported"] == ["S256"]


def test_the_api_routes_still_work(client):
    assert client.get("/dashboard").status_code == 401     # the API's own sign-in, not the MCP one


# ---------- Signing in ----------

def test_sign_in_then_tools_read_that_users_data(client):
    asha, ben = sign_in(client, "asha"), sign_in(client, "ben")
    for _ in range(2):     # alternate, to prove one user's request never leaks into the next
        assert '\\"user_id\\": 5' in call_tool(client, asha["access_token"]).text
        assert '\\"user_id\\": 6' in call_tool(client, ben["access_token"]).text


def test_tools_are_listed_as_read_only(client):
    token = sign_in(client)["access_token"]
    r = client.post("/mcp", headers={**MCP_HEADERS, "Authorization": f"Bearer {token}"},
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tools = r.json()["result"]["tools"]
    assert {t["name"] for t in tools} >= {"get_sleep", "search_guides"}
    assert all(t["annotations"]["readOnlyHint"] for t in tools)


def test_google_is_only_asked_who_the_user_is(client):
    google = start(client, register(client).json()["client_id"])
    assert google["scope"] == ["openid email profile"]
    assert google["redirect_uri"] == [mcp_auth.GOOGLE_CALLBACK_URL]


def test_a_made_up_token_is_rejected(client):
    assert call_tool(client, "not-a-real-token").status_code == 401


def test_a_code_works_only_once(client):
    tokens = sign_in(client)
    r = client.post("/token", data={"grant_type": "authorization_code", "code": tokens["code"],
                                    "client_id": tokens["client_id"], "redirect_uri": REDIRECT_URI,
                                    "code_verifier": VERIFIER})
    assert r.status_code == 400


def test_wrong_pkce_verifier_is_rejected(client):
    client_id = register(client).json()["client_id"]
    request_id = start(client, client_id)["state"][0]
    client.get("/oauth/google/callback", params={"state": request_id, "code": "asha"})
    r = client.post("/oauth/consent", data={"request_id": request_id, "action": "allow"})
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    r = client.post("/token", data={"grant_type": "authorization_code", "code": code, "client_id": client_id,
                                    "redirect_uri": REDIRECT_URI, "code_verifier": "w" * 64})
    assert r.status_code == 400


# ---------- The "Allow access?" page ----------

def test_consent_page_names_the_app_and_escapes_it(client):
    client_id = register(client, client_name="<script>alert(1)</script>").json()["client_id"]
    request_id = start(client, client_id)["state"][0]
    page = client.get("/oauth/google/callback", params={"state": request_id, "code": "asha"})
    assert "&lt;script&gt;" in page.text and "<script>" not in page.text
    assert "asha@example.com" in page.text and "localhost:9999" in page.text
    assert page.headers["x-frame-options"] == "DENY"


def test_allow_needs_the_cookie_from_the_consent_page(client):
    request_id = start(client, register(client).json()["client_id"])["state"][0]
    client.get("/oauth/google/callback", params={"state": request_id, "code": "asha"})
    client.cookies.clear()      # someone else, who only knows the request id
    r = client.post("/oauth/consent", data={"request_id": request_id, "action": "allow"})
    assert r.status_code == 400


def test_allow_from_another_site_is_rejected(client):
    request_id = start(client, register(client).json()["client_id"])["state"][0]
    client.get("/oauth/google/callback", params={"state": request_id, "code": "asha"})
    r = client.post("/oauth/consent", data={"request_id": request_id, "action": "allow"},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 400


def test_allow_before_signing_in_is_rejected(client):
    request_id = start(client, register(client).json()["client_id"])["state"][0]
    r = client.post("/oauth/consent", data={"request_id": request_id, "action": "allow"})
    assert r.status_code == 400


def test_cancel_sends_the_user_back_without_a_code(client):
    request_id = start(client, register(client).json()["client_id"])["state"][0]
    client.get("/oauth/google/callback", params={"state": request_id, "code": "asha"})
    r = client.post("/oauth/consent", data={"request_id": request_id, "action": "deny"})
    back = parse_qs(urlparse(r.headers["location"]).query)
    assert back == {"state": ["xyz"], "error": ["access_denied"]}


def test_unverified_google_email_is_rejected(client):
    request_id = start(client, register(client).json()["client_id"])["state"][0]
    r = client.get("/oauth/google/callback", params={"state": request_id, "code": "unverified"})
    assert r.status_code == 400 and "verified" in r.text


def test_unknown_sign_in_request_is_rejected(client):
    assert client.get("/oauth/google/callback", params={"state": "made-up", "code": "asha"}).status_code == 400


# ---------- Tokens over time ----------

def refresh(client, tokens):
    return client.post("/token", data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"],
                                       "client_id": tokens["client_id"]})


def test_refresh_replaces_both_tokens(client):
    old = sign_in(client)
    new = refresh(client, old).json()
    assert call_tool(client, new["access_token"]).status_code == 200
    assert call_tool(client, old["access_token"]).status_code == 401
    assert refresh(client, old).status_code == 400          # the old refresh token is spent


def test_revoke_ends_the_connection(client):
    tokens = sign_in(client)
    # The SDK's /revoke insists on a client_secret field, even from a client that has none
    r = client.post("/revoke", data={"token": tokens["refresh_token"], "client_id": tokens["client_id"],
                                     "client_secret": ""})
    assert r.status_code == 200
    assert call_tool(client, tokens["access_token"]).status_code == 401
    assert refresh(client, tokens).status_code == 400


def test_expired_access_token_is_rejected(client, monkeypatch):
    tokens = sign_in(client)
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + mcp_auth.ACCESS_TTL + 5)
    assert call_tool(client, tokens["access_token"]).status_code == 401


# ---------- Registering a client ----------

@pytest.mark.parametrize("uri", ["http://evil.example/callback", "javascript:alert(1)"])
def test_unsafe_redirect_uris_cannot_register(client, uri):
    assert register(client, redirect_uris=[uri]).status_code == 400


def test_app_scheme_and_https_redirects_can_register(client):
    assert register(client, redirect_uris=["cursor://anysphere.cursor-mcp/oauth/callback"]).status_code == 201
    assert register(client, redirect_uris=["https://claude.ai/api/mcp/auth_callback"]).status_code == 201


def test_client_secret_is_encrypted_at_rest(client):
    body = register(client, token_endpoint_auth_method="client_secret_post").json()
    stored = mcp_auth.store.rows["client", body["client_id"]]["data"]
    assert stored["client_secret"] != body["client_secret"]


def test_token_for_another_server_is_refused(client):
    client_id = register(client).json()["client_id"]
    r = client.get("/authorize", params={
        "client_id": client_id, "response_type": "code", "redirect_uri": REDIRECT_URI, "state": "xyz",
        "code_challenge": CHALLENGE, "code_challenge_method": "S256", "resource": "https://other.example/mcp"})
    assert "invalid_target" in r.headers["location"]


# ---------- Local stdio mode ----------

def test_no_token_and_no_local_user_fails_closed():
    with pytest.raises(RuntimeError):
        mcp_server._user_id()
