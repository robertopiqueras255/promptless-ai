"""FastAPI app entry point for Promptless AI MVP."""

from __future__ import annotations

import concurrent.futures
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .actions import is_allowed_action
from .config import RerankConfig
from .hermes_client import execute_text_action
from .intent import rank_actions_detailed
from .llm import rerank_actions_with_metadata
from .memory import for_hermes, store_youtube
from .privacy import PrivacyMode, SanitizedContext, route_context, sanitize_context
from .schemas import ExecuteRequest, ExecuteResponse, FeedbackRequest, IntentRequest, IntentResponse, MemoryStoreRequest, YouTubeRequest
from .storage import log_execution, log_feedback, log_intent, new_trace_id
from .youtube import (
    build_context_patch,
    classify_youtube_content,
    detect_actionable_subtype,
    extract_video_id,
    fetch_transcript_with_source,
    get_youtube_intervention,
)
from .youtube_jobs import YouTubeTranscriptJob, cancel_transcript_job, enqueue_transcript_job

app = FastAPI(title="Promptless AI Intent Backend", version="0.1.0")
rerank_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="ollama-rerank")

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
    ranking = rank_actions_detailed(request)
    intent, confidence, actions = ranking.intent, ranking.confidence, ranking.actions

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
    rerank_requested = bool(safe_actions) and os.getenv("PROMPTLESS_OLLAMA_RERANK", "1").lower() not in {"0", "false", "off"}
    log_intent(
        trace_id,
        sanitized.context,
        {
            **response.model_dump(),
            "rerank_requested": rerank_requested,
            "rerank_used": False,
            "rerank_model": None,
        },
        privacy=privacy_metadata(sanitized, route),
    )
    if rerank_requested:
        rerank_executor.submit(rerank_if_needed, trace_id, ranking.context_summary, ranking.rerank_candidates)
    if safe_actions:
        log_feedback(trace_id, "shown", metadata={"actionIds": [action.id for action in safe_actions]})
    return response


def rerank_if_needed(trace_id: str, context_summary: str, candidates) -> None:
    model = os.getenv("PROMPTLESS_OLLAMA_RERANK_MODEL") or None
    candidate_dicts = [
        candidate.model_dump()
        for candidate in candidates[: RerankConfig.MAX_CANDIDATES]
        if is_allowed_action(candidate.id) and candidate.risk == "low"
    ]
    if not candidate_dicts:
        return
    result = rerank_actions_with_metadata(context_summary, candidate_dicts, model=model, timeout=RerankConfig.TIMEOUT)
    reranked_ids = [candidate["id"] for candidate in result.actions]
    original_ids = [candidate["id"] for candidate in candidate_dicts]
    log_feedback(
        trace_id,
        "intent_rerank_completed",
        metadata={
            "rerank_used": result.used,
            "rerank_model": result.model,
            "rerank_error": result.error,
            "rankedActionIds": reranked_ids,
            "originalActionIds": original_ids,
        },
    )


@app.get("/llm/status")
def llm_status() -> dict:
    """Return LLM availability and current configuration."""
    from .llm import get_llm_status

    return get_llm_status()


@app.post("/youtube/intervene")
def youtube_intervene(request: YouTubeRequest) -> dict[str, object]:
    trace_id = new_trace_id()
    video_id = request.videoId or extract_video_id(request.url)
    if not video_id:
        raise HTTPException(status_code=400, detail="Missing YouTube video id")

    transcript_result = fetch_transcript_with_source(video_id, allow_ytdlp=False, allow_asr=False)
    transcript = transcript_result.text
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
        "transcriptionStatus": transcript_result.status,
        "transcriptSource": transcript_result.source,
    }
    log_intent(
        trace_id,
        {"workflow": "youtube", "url": request.url, "title": request.title, "videoId": video_id},
        {
            "workflow": "youtube",
            "classification": classification,
            "interventionShown": intervention is not None,
            "transcriptLength": len(transcript),
            "transcriptionStatus": transcript_result.status,
            "transcriptSource": transcript_result.source,
            "actionIds": [action.get("id") for action in actions if isinstance(action, dict)],
        },
        privacy={"sensitivity": "public", "route": "local", "cloudAllowed": False, "redactionCount": 0, "findingKinds": []},
    )
    if actions:
        log_feedback(trace_id, "shown", metadata={"actionIds": [action["id"] for action in actions]})

    # Store a lightweight memory immediately; enrich it later if captions are absent.
    if request.url:
        subtype = detect_actionable_subtype(transcript, metadata) if classification == "ACTIONABLE" else ""
        transcript_preview = transcript[:2000] if transcript else ""
        should_queue_transcription = not transcript and request.min_watch_time_ms >= 10000
        transcription_status = transcript_result.status if transcript else "queued" if should_queue_transcription else "deferred"
        classification_label = "Actionable" if classification == "ACTIONABLE" else "Leisure" if classification == "LEISURE" else "Unknown"
        memory_entry = store_youtube(
            url=request.url,
            title=request.title,
            channel=request.channel,
            classification=classification,
            summary=f"{classification_label} video. Subtype: {subtype}. "
                    f"Transcript preview: {transcript[:300] if transcript else 'No captions available'}",
            transcript_preview=transcript_preview,
            extracted_content=transcript[:24000] if transcript else None,
            video_id=video_id,
            transcription_status=transcription_status,
            transcript_source=transcript_result.source,
        )
        response["memoryId"] = memory_entry.get("id", "")
        response["transcriptionStatus"] = transcription_status
        if should_queue_transcription:
            response["transcriptionStatus"] = enqueue_transcript_job(
                YouTubeTranscriptJob(
                    memory_id=memory_entry.get("id", ""),
                    video_id=video_id,
                    title=request.title,
                    channel=request.channel,
                    url=request.url,
                    start_after_seconds=0.0,
                )
            )

    return response


@app.post("/youtube/cancel/{video_id}")
def youtube_cancel(video_id: str) -> dict[str, object]:
    canceled = cancel_transcript_job(video_id)
    log_feedback(
        None,
        "youtube_transcription_canceled",
        metadata={"videoId": video_id, "canceled": canceled},
    )
    return {"status": "ok", "video_id": video_id, "canceled": canceled}


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
def memory_store(request: MemoryStoreRequest) -> dict:
    """Manually store a memory entry (for testing or manual use)."""
    from .memory import store
    entry = store(
        entry_type=request.entry_type,
        title=request.title,
        summary=request.summary,
        url=request.url or None,
        workflow=request.workflow or None,
        action_taken=request.action_taken or None,
        extracted_content=request.extracted_content or None,
        tags=request.tags,
        user_id=request.user_id,
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
