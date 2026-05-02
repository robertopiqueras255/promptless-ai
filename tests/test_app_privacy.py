import json

from fastapi.testclient import TestClient

from backend import hermes_client, storage
from backend.app import app


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
    records = [json.loads(line) for line in trace_path.read_text().splitlines()]
    intent_record = next(record for record in records if record["type"] == "intent")
    dumped = json.dumps(intent_record)
    assert secret not in dumped
    assert "[SECRET:OPENAI_KEY_1]" in dumped
    assert intent_record["privacy"]["sensitivity"] == "secret"
    assert intent_record["privacy"]["route"] == "local"


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
    records = [json.loads(line) for line in trace_path.read_text().splitlines()]
    dumped = json.dumps(records)
    assert "hunter2" not in dumped
    assert "[SECRET:PASSWORD_1]" in dumped
    execution = next(record for record in records if record["type"] == "execution")
    assert execution["metadata"]["privacy"]["sensitivity"] == "secret"
    assert execution["metadata"]["privacy"]["route"] == "local"
