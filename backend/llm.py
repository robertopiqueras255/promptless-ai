"""Local LLM reranking via Ollama with model tiering support."""

from __future__ import annotations

import json
from dataclasses import dataclass
from .config import RerankConfig, TIER_MODELS, get_all_available_models, get_available_model


@dataclass(frozen=True)
class RerankResult:
    actions: list[dict]
    used: bool
    model: str | None = None
    error: str = ""


def rerank_actions(
    context: str,
    candidates: list[dict],
    model: str | None = None,
    timeout: int | None = None,
) -> list[dict]:
    """
    Ask a local Ollama model to rank candidate actions for page context.

    Returns candidates in ranked order. If Ollama is unavailable, the model is
    not pulled, the call times out, or the response is malformed, returns the
    original deterministic order.
    """
    return rerank_actions_with_metadata(context, candidates, model=model, timeout=timeout).actions


def rerank_actions_with_metadata(
    context: str,
    candidates: list[dict],
    model: str | None = None,
    timeout: int | None = None,
) -> RerankResult:
    """Rerank actions and report whether Ollama produced a valid result."""
    if not candidates:
        return RerankResult([], used=False)

    selected_model = model or get_available_model()
    if not selected_model:
        return RerankResult(candidates, used=False, error="no_available_model")

    models_to_try = fallback_models_for(selected_model)
    timeout_seconds = timeout or RerankConfig.TIMEOUT
    last_error = ""
    for model_name in models_to_try:
        try:
            ranked = _call_ollama(model_name, context, candidates, timeout_seconds)
            return RerankResult(ranked, used=True, model=model_name)
        except Exception as exc:
            last_error = exc.__class__.__name__
            continue

    return RerankResult(candidates, used=False, error=last_error or "rerank_failed")


def fallback_models_for(model: str) -> list[str]:
    """Return model fallback chain for the configured tier."""
    if RerankConfig.TIER == "auto":
        tier_order = TIER_MODELS["auto"]
        try:
            idx = tier_order.index(model)
            return tier_order[idx:]
        except ValueError:
            return [model]
    return [model]


def _call_ollama(model: str, context: str, candidates: list[dict], timeout: int) -> list[dict]:
    import ollama

    candidate_block = "\n".join(
        f"- {candidate['id']}: {candidate['label']} - {candidate['description']}"
        for candidate in candidates
    )
    prompt = f"""You are a helpful browser assistant. Given the user's current page context,
rank these suggested actions from most to least useful for this situation.

Context:
{context[:2000]}

Actions:
{candidate_block}

Respond with a JSON object containing action IDs in ranked order, most useful first:
{{"ranked": ["action_id_1", "action_id_2"]}}"""

    client = ollama.Client(timeout=timeout)
    response = client.generate(
        model=model,
        prompt=prompt,
        format="json",
        options={"temperature": 0.1, "num_predict": 200},
    )
    result = json.loads(response.get("response") or "{}")
    ranked_ids = result.get("ranked")
    if not isinstance(ranked_ids, list):
        raise ValueError("missing_ranked_array")

    id_to_candidate = {candidate["id"]: candidate for candidate in candidates}
    ranked = [id_to_candidate[action_id] for action_id in ranked_ids if action_id in id_to_candidate]
    ranked.extend(candidate for candidate in candidates if candidate["id"] not in {item["id"] for item in ranked})
    return ranked


def get_llm_status() -> dict:
    """Return current LLM availability and config for settings UI."""
    available = get_all_available_models()
    active_model = get_available_model()

    return {
        "tier": RerankConfig.TIER,
        "timeout": RerankConfig.TIMEOUT,
        "max_candidates": RerankConfig.MAX_CANDIDATES,
        "active_model": active_model,
        "models_in_tier": TIER_MODELS.get(RerankConfig.TIER, []),
        "all_available_models": available,
        "rerank_enabled": active_model is not None,
        "tier_options": {
            "fast": {"models": TIER_MODELS["fast"], "description": "Fast reranking, uses less memory"},
            "quality": {"models": TIER_MODELS["quality"], "description": "Better reasoning, slower"},
            "auto": {"models": TIER_MODELS["auto"], "description": "Use best available model"},
        },
    }
