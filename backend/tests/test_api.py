import time

import jwt
import pytest
from fastapi.testclient import TestClient

import app.auth as auth
import app.main as main
from app.config import settings

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def signed_in():
    # Most tests are about what the routes do, not about signing in: pretend user 1 is signed in
    main.app.dependency_overrides[auth.current_user] = lambda: 1
    yield
    main.app.dependency_overrides.clear()


def make_token(secret=None, **changes):
    claims = {"sub": "google-123", "email": "a@example.com", "name": "A", "iss": auth.ISSUER,
              "aud": auth.AUDIENCE, "exp": int(time.time()) + 60, **changes}
    return jwt.encode(claims, secret or settings.api_jwt_secret, algorithm="HS256")


def fake_agent(question, user_id, conversation_id=None):
    return {
        "answer": "You slept 5.1 hours last night [1].",
        "sources": [{"n": 1, "title": "NHLBI: Your Guide to Healthy Sleep", "page": 27, "url": None}],
        "safety": "ok",
        "conversation_id": conversation_id or 99,
        "tool_calls": [{"tool": "get_sleep", "args": {"days": 1}}],
    }


def test_empty_question_is_rejected():
    assert client.post("/ask", json={"question": "   "}).status_code == 422


def test_too_long_question_is_rejected():
    assert client.post("/ask", json={"question": "a" * 1001}).status_code == 422


def test_answer_has_sources_and_conversation(monkeypatch):
    monkeypatch.setattr(main, "run_agent", fake_agent)     # swap the real agent for the fake one
    body = client.post("/ask", json={"question": "How did I sleep?"}).json()
    assert body["sources"][0]["page"] == 27
    assert body["conversation_id"] == 99
    assert body["tool_calls"][0]["tool"] == "get_sleep"


def test_conversation_id_is_passed_to_agent(monkeypatch):
    monkeypatch.setattr(main, "run_agent", fake_agent)
    body = client.post("/ask", json={"question": "And the night before?", "conversation_id": 42}).json()
    assert body["conversation_id"] == 42


def test_agent_failure_returns_503(monkeypatch):
    def broken(question, user_id, conversation_id=None):
        raise RuntimeError("Bedrock is down")

    monkeypatch.setattr(main, "run_agent", broken)
    r = client.post("/ask", json={"question": "How did I sleep?"})
    assert r.status_code == 503
    assert "try again" in r.json()["detail"]

def test_dashboard_rejects_bad_days():
    assert client.get("/dashboard?days=99").status_code == 422


# ---------- Signing in ----------

def test_private_routes_need_a_token():
    main.app.dependency_overrides.clear()
    assert client.get("/dashboard").status_code == 401
    assert client.post("/ask", json={"question": "How did I sleep?"}).status_code == 401
    assert client.put("/connections/google-health", json={"refresh_token": "x", "scope": ""}).status_code == 401


@pytest.mark.parametrize("token", [
    "not-a-token",
    make_token(secret="x" * 44),                    # signed by someone else
    make_token(exp=int(time.time()) - 5),           # expired
    make_token(aud="another-app"),
])
def test_bad_tokens_are_rejected(token):
    main.app.dependency_overrides.clear()
    assert client.get("/dashboard", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_valid_token_identifies_the_user(monkeypatch):
    main.app.dependency_overrides.clear()
    seen = {}

    def fake_get_or_create(conn, google_sub, email, name):
        seen.update(sub=google_sub, email=email)
        return 5

    def agent(question, user_id, conversation_id=None):
        return {**fake_agent(question, user_id, conversation_id), "answer": f"user {user_id}"}

    monkeypatch.setattr(auth, "get_or_create_user", fake_get_or_create)
    monkeypatch.setattr(main, "run_agent", agent)
    r = client.post("/ask", json={"question": "Hi"}, headers={"Authorization": f"Bearer {make_token()}"})
    assert r.json()["answer"] == "user 5"
    assert seen == {"sub": "google-123", "email": "a@example.com"}
