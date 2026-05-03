"""Promptless model and reranking configuration."""

from __future__ import annotations

import os


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


class RerankConfig:
    # Model tier: "auto", "fast", "quality"
    TIER = os.getenv("PROMPTLESS_RERANK_TIER", "auto")

    # Timeout per model attempt in seconds. The old Ollama-specific variable is
    # kept as a fallback for local installs from earlier builds.
    TIMEOUT = _env_int(
        "PROMPTLESS_RERANK_TIMEOUT",
        _env_int("PROMPTLESS_OLLAMA_RERANK_TIMEOUT_SECONDS", 15),
    )

    # Max candidates to send to LLM.
    MAX_CANDIDATES = _env_int("PROMPTLESS_MAX_CANDIDATES", 5)


TIER_MODELS = {
    "fast": ["gemma:2b", "qwen2.5:1.5b"],
    "quality": ["gemma:7b", "qwen2.5:3b"],
    "auto": ["gemma:7b", "gemma:2b", "qwen2.5:1.5b", "qwen2.5:3b"],
}


def get_available_model(tier: str | None = None) -> str | None:
    """Return the first available model for the tier, or None."""
    try:
        import ollama
    except ImportError:
        return None

    selected_tier = tier or RerankConfig.TIER
    models_to_try = TIER_MODELS.get(selected_tier, TIER_MODELS["auto"])
    for model in models_to_try:
        try:
            ollama.show(model)
            return model
        except Exception:
            continue
    return None


def get_all_available_models() -> list[str]:
    """Return all available Ollama models on this machine."""
    try:
        import ollama

        models = ollama.list().get("models", [])
    except Exception:
        return []

    names = []
    for model in models:
        if isinstance(model, dict):
            name = model.get("name") or model.get("model")
        else:
            name = getattr(model, "name", None) or getattr(model, "model", None)
        if name:
            names.append(str(name))
    return names
