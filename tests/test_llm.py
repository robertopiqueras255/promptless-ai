import types

from backend import config
from backend.llm import fallback_models_for, get_llm_status, rerank_actions_with_metadata


def test_rerank_actions_with_metadata_uses_valid_ollama_json(monkeypatch):
    monkeypatch.setattr("backend.llm.get_available_model", lambda tier=None: "gemma:2b")

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def generate(self, **_kwargs):
            return {"response": '{"ranked": ["b", "a"]}'}

    fake_ollama = types.SimpleNamespace(Client=FakeClient)
    monkeypatch.setitem(__import__("sys").modules, "ollama", fake_ollama)
    candidates = [
        {"id": "a", "label": "A", "description": "First"},
        {"id": "b", "label": "B", "description": "Second"},
    ]

    result = rerank_actions_with_metadata("context", candidates)

    assert result.used is True
    assert result.model == "gemma:2b"
    assert [action["id"] for action in result.actions] == ["b", "a"]


def test_rerank_actions_with_metadata_falls_back_on_error(monkeypatch):
    monkeypatch.setattr("backend.llm.get_available_model", lambda tier=None: "gemma:2b")

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def generate(self, **_kwargs):
            raise RuntimeError("ollama unavailable")

    fake_ollama = types.SimpleNamespace(Client=FakeClient)
    monkeypatch.setitem(__import__("sys").modules, "ollama", fake_ollama)
    candidates = [{"id": "a", "label": "A", "description": "First"}]

    result = rerank_actions_with_metadata("context", candidates)

    assert result.used is False
    assert result.actions == candidates
    assert result.error == "RuntimeError"


def test_auto_fallback_models_start_at_selected_model(monkeypatch):
    monkeypatch.setattr(config.RerankConfig, "TIER", "auto")

    assert fallback_models_for("gemma:2b") == ["gemma:2b", "qwen2.5:1.5b", "qwen2.5:3b"]


def test_get_llm_status_reports_config(monkeypatch):
    monkeypatch.setattr(config.RerankConfig, "TIER", "fast")
    monkeypatch.setattr(config.RerankConfig, "TIMEOUT", 7)
    monkeypatch.setattr(config.RerankConfig, "MAX_CANDIDATES", 4)
    monkeypatch.setattr("backend.llm.get_available_model", lambda tier=None: "gemma:2b")
    monkeypatch.setattr("backend.llm.get_all_available_models", lambda: ["gemma:2b"])

    status = get_llm_status()

    assert status["tier"] == "fast"
    assert status["timeout"] == 7
    assert status["max_candidates"] == 4
    assert status["active_model"] == "gemma:2b"
    assert status["rerank_enabled"] is True
