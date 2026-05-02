import json

from fastapi.testclient import TestClient

from backend import hermes_client, storage
from backend.app import app


def read_trace_records(trace_path):
    if not trace_path.exists():
        return []
    return [json.loads(line) for line in trace_path.read_text().splitlines()]


def test_intent_trace_stores_redacted_context(tmp_path, monkeypatch):
    trace_path = tmp_path / "traces.jsonl"
    monkeypatch.setattr(storage, "TRACE_PATH", trace_path)
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    client = TestClient(app)
    secret = "sk-" + "a" * 24

    response = client.post(
        "/intent",
        json={
            "url": "https://docs.example.com/api/auth",
            "title": "API Auth",
            "visibleText": f"Use this API key {secret} for OAuth docs and pricing limits.",
        },
    )

    assert response.status_code == 200
    records = read_trace_records(trace_path)
    intent_record = next(record for record in records if record["type"] == "intent")
    dumped = json.dumps(intent_record)
    assert secret not in dumped
    assert "[SECRET:OPENAI_KEY_1]" in dumped
    assert intent_record["privacy"]["sensitivity"] == "secret"
    assert intent_record["privacy"]["route"] == "local"


def test_privacy_preview_returns_redacted_context_and_route():
    client = TestClient(app)
    secret = "sk-" + "a" * 24

    response = client.post(
        "/privacy/preview",
        json={
            "url": "https://docs.example.com/api/auth",
            "title": "API Auth",
            "visibleText": f"Email ops@example.com and keep API key {secret} local.",
            "recentEvents": [{"type": "selection", "text": f"Use {secret}"}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    dumped = json.dumps(payload)
    assert secret not in dumped
    assert "ops@example.com" not in dumped
    assert payload["redactionCount"] >= 2
    assert payload["route"] == "local"
    assert not payload["cloudAllowed"]
    assert "[SECRET:OPENAI_KEY_1]" in dumped
    assert "[EMAIL_1]" in dumped


def test_execute_uses_sanitized_context_and_logs_privacy(tmp_path, monkeypatch):
    trace_path = tmp_path / "traces.jsonl"
    monkeypatch.setattr(storage, "TRACE_PATH", trace_path)
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(hermes_client, "HERMES_ENABLED", False)
    client = TestClient(app)
    password = "password: hunter2"

    response = client.post(
        "/execute",
        json={
            "traceId": "trace-1",
            "actionId": "extract_key_facts",
            "context": {
                "url": "https://crm.example.com/customer",
                "title": "Customer dashboard",
                "visibleText": f"{password}. Invoice INV-99999 should be reviewed.",
            },
        },
    )

    assert response.status_code == 200
    records = read_trace_records(trace_path)
    dumped = json.dumps(records)
    assert "hunter2" not in dumped
    assert "[SECRET:PASSWORD_1]" in dumped
    execution = next(record for record in records if record["type"] == "execution")
    assert execution["metadata"]["privacy"]["sensitivity"] == "secret"
    assert execution["metadata"]["privacy"]["route"] == "local"


def test_execute_rejects_disallowed_action_without_logging(tmp_path, monkeypatch):
    trace_path = tmp_path / "traces.jsonl"
    monkeypatch.setattr(storage, "TRACE_PATH", trace_path)
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    client = TestClient(app)

    response = client.post(
        "/execute",
        json={
            "traceId": "trace-unsafe",
            "actionId": "delete_account",
            "context": {"url": "https://example.com", "title": "Settings", "visibleText": "Delete account"},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown or disallowed actionId"
    assert read_trace_records(trace_path) == []


def test_feedback_rejects_disallowed_action_without_logging(tmp_path, monkeypatch):
    trace_path = tmp_path / "traces.jsonl"
    monkeypatch.setattr(storage, "TRACE_PATH", trace_path)
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    client = TestClient(app)

    response = client.post(
        "/feedback",
        json={"traceId": "trace-unsafe", "event": "accepted", "actionId": "delete_account"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown or disallowed actionId"
    assert read_trace_records(trace_path) == []


def test_low_confidence_intent_returns_no_actions_or_shown_feedback(tmp_path, monkeypatch):
    trace_path = tmp_path / "traces.jsonl"
    monkeypatch.setattr(storage, "TRACE_PATH", trace_path)
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    client = TestClient(app)

    response = client.post("/intent", json={"url": "", "title": "", "visibleText": ""})

    assert response.status_code == 200
    payload = response.json()
    assert payload["confidence"] < 0.65
    assert payload["actions"] == []

    records = read_trace_records(trace_path)
    assert [record["type"] for record in records] == ["intent"]
    assert not any(record.get("event") == "shown" for record in records)
