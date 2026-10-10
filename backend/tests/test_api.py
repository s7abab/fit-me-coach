from fastapi.testclient import TestClient
import app.main as main

client = TestClient(main.app)


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