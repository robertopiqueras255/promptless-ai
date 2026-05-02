"""FastAPI app entry point for Promptless AI MVP."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .actions import is_allowed_action
from .hermes_client import execute_text_action
from .intent import rank_actions
from .privacy import PrivacyMode, SanitizedContext, route_context, sanitize_context
from .schemas import ExecuteRequest, ExecuteResponse, FeedbackRequest, IntentRequest, IntentResponse
from .storage import log_execution, log_feedback, log_intent, new_trace_id

app = FastAPI(title="Promptless AI Intent Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Local MVP only. Tighten before distribution.
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/privacy/preview")
def privacy_preview(request: IntentRequest) -> dict[str, object]:
    sanitized = sanitize_context(request)
    route = route_context(sanitized, PrivacyMode.REDACTED_CLOUD)
    return {
        **privacy_metadata(sanitized, route),
        "context": sanitized.context,
    }


@app.post("/intent", response_model=IntentResponse)
def infer_intent(request: IntentRequest) -> IntentResponse:
    trace_id = new_trace_id()
    sanitized = sanitize_context(request)
    route = route_context(sanitized, PrivacyMode.REDACTED_CLOUD)

    # Deterministic ranking runs locally. Future cloud rerankers must use
    # sanitized.context only and honor route.cloud_allowed.
    intent, confidence, actions = rank_actions(request)

    # Backend-side enforcement: low-risk, known IDs only, max 3.
    safe_actions = [action for action in actions if is_allowed_action(action.id) and action.risk == "low"][:3]
    if confidence < 0.65:
        safe_actions = []

    response = IntentResponse(
        traceId=trace_id,
        intent=intent,
        confidence=round(confidence, 3),
        actions=safe_actions,
    )
    log_intent(trace_id, sanitized.context, response.model_dump(), privacy=privacy_metadata(sanitized, route))
    if safe_actions:
        log_feedback(trace_id, "shown", metadata={"actionIds": [action.id for action in safe_actions]})
    return response


@app.post("/execute", response_model=ExecuteResponse)
def execute_action(request: ExecuteRequest) -> ExecuteResponse:
    if not is_allowed_action(request.actionId):
        raise HTTPException(status_code=400, detail="Unknown or disallowed actionId")

    sanitized = sanitize_context(request.context) if request.context else None
    route = route_context(sanitized, PrivacyMode.REDACTED_CLOUD) if sanitized else None
    safe_context = IntentRequest.model_validate(sanitized.context) if sanitized else None
    privacy = privacy_metadata(sanitized, route) if sanitized and route else {}

    # Execution adapters receive redacted context by default. If a future local
    # model truly needs raw context, it must explicitly use the local-only route.
    outcome = execute_text_action(request.actionId, safe_context, trace_id=request.traceId)
    metadata = {
        "status": outcome.status,
        "hermesUsed": outcome.hermes_used,
        "fallbackUsed": outcome.fallback_used,
        "durationMs": outcome.duration_ms,
        "error": outcome.error,
    }
    if privacy:
        metadata["privacy"] = privacy
    log_execution(
        request.traceId,
        request.actionId,
        outcome.result,
        metadata=metadata,
    )
    if outcome.status == "done":
        log_feedback(request.traceId, "executed", action_id=request.actionId)
    return ExecuteResponse(status=outcome.status, result=outcome.result, privacy=privacy)


@app.post("/feedback")
def feedback(request: FeedbackRequest) -> dict[str, str]:
    if request.actionId is not None and not is_allowed_action(request.actionId):
        raise HTTPException(status_code=400, detail="Unknown or disallowed actionId")
    log_feedback(request.traceId, request.event, request.actionId, request.metadata)
    return {"status": "ok"}


def privacy_metadata(sanitized: SanitizedContext, route) -> dict[str, object]:
    return {
        "sensitivity": sanitized.sensitivity,
        "redactionCount": sanitized.redaction_count,
        "findingKinds": sorted({finding.kind for finding in sanitized.findings}),
        "route": route.route,
        "cloudAllowed": route.cloud_allowed,
        "routeReason": route.reason,
    }
