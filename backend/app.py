"""FastAPI app entry point for Promptless AI MVP."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .actions import is_allowed_action
from .hermes_client import execute_text_action
from .intent import rank_actions
from .memory import for_hermes, store_youtube
from .privacy import PrivacyMode, SanitizedContext, route_context, sanitize_context
from .schemas import ExecuteRequest, ExecuteResponse, FeedbackRequest, IntentRequest, IntentResponse, YouTubeRequest
from .storage import log_execution, log_feedback, log_intent, new_trace_id
from .youtube import (
    build_context_patch,
    classify_youtube_content,
    detect_actionable_subtype,
    extract_video_id,
    fetch_transcript,
    get_youtube_intervention,
)

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


@app.post("/youtube/intervene")
def youtube_intervene(request: YouTubeRequest) -> dict[str, object]:
    trace_id = new_trace_id()
    video_id = request.videoId or extract_video_id(request.url)
    if not video_id:
        raise HTTPException(status_code=400, detail="Missing YouTube video id")

    transcript = fetch_transcript(video_id)
    metadata = {
        "title": request.title,
        "channel": request.channel,
        "url": request.url,
        "video_id": video_id,
    }
    classification = classify_youtube_content(transcript, metadata) if transcript else "UNKNOWN"
    intervention = get_youtube_intervention(classification, transcript, metadata)
    actions = intervention.get("actions", []) if intervention else []
    response = {
        "traceId": trace_id,
        "classification": classification,
        "intervention": intervention,
        "actions": actions,
        "intent": intervention.get("intent") if intervention else "",
        "contextPatch": build_context_patch(transcript, metadata, classification) if transcript else {},
        "transcriptPreview": transcript[:500],
    }
    log_intent(
        trace_id,
        {"workflow": "youtube", "url": request.url, "title": request.title, "videoId": video_id},
        {
            "workflow": "youtube",
            "classification": classification,
            "interventionShown": intervention is not None,
            "transcriptLength": len(transcript),
            "actionIds": [action.get("id") for action in actions if isinstance(action, dict)],
        },
        privacy={"sensitivity": "public", "route": "local", "cloudAllowed": False, "redactionCount": 0, "findingKinds": []},
    )
    if actions:
        log_feedback(trace_id, "shown", metadata={"actionIds": [action["id"] for action in actions]})

    # Store in promptless memory for Hermes context
    if transcript and classification != "UNKNOWN":
        subtype = detect_actionable_subtype(transcript, metadata) if classification == "ACTIONABLE" else ""
        memory_entry = store_youtube(
            url=request.url,
            title=request.title,
            channel=request.channel,
            classification=classification,
            summary=f"{'Actionable' if classification == 'ACTIONABLE' else 'Leisure'} video. Subtype: {subtype}. "
                    f"Transcript preview: {transcript[:300]}",
            transcript_preview=transcript[:2000],
        )
        response["memoryId"] = memory_entry.get("id", "")

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


@app.get("/memory/hermes")
def memory_for_hermes(q: str, limit: int = 5) -> dict[str, str]:
    """Retrieve memories relevant to a query and return as a Hermes-ready context block."""
    context = for_hermes(q, limit=limit)
    return {"context": context, "query": q}


@app.post("/memory/store")
def memory_store(
    entry_type: str,
    title: str,
    summary: str,
    url: str = "",
    workflow: str = "",
    action_taken: str = "",
    extracted_content: str = "",
    tags: str = "",
    user_id: str = "default",
) -> dict:
    """Manually store a memory entry (for testing or manual use)."""
    from .memory import store
    entry = store(
        entry_type=entry_type,
        title=title,
        summary=summary,
        url=url or None,
        workflow=workflow or None,
        action_taken=action_taken or None,
        extracted_content=extracted_content or None,
        tags=[t.strip() for t in tags.split(",") if t.strip()] if tags else None,
        user_id=user_id,
    )
    return {"id": entry["id"], "visit_count": entry["visit_count"]}


def privacy_metadata(sanitized: SanitizedContext, route) -> dict[str, object]:
    return {
        "sensitivity": sanitized.sensitivity,
        "redactionCount": sanitized.redaction_count,
        "findingKinds": sorted({finding.kind for finding in sanitized.findings}),
        "route": route.route,
        "cloudAllowed": route.cloud_allowed,
        "routeReason": route.reason,
    }
