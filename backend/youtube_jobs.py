"""Small local queue for YouTube transcript enrichment."""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass

from .memory import update_entry, update_youtube_memory
from .youtube import classify_youtube_content, detect_actionable_subtype, fetch_transcript_with_source


TRANSCRIPTION_GRACE_SECONDS = 10.0


@dataclass(frozen=True)
class YouTubeTranscriptJob:
    memory_id: str
    video_id: str
    title: str
    channel: str
    url: str
    start_after_seconds: float = TRANSCRIPTION_GRACE_SECONDS


_jobs: queue.Queue[YouTubeTranscriptJob] = queue.Queue()
_pending_jobs: dict[str, YouTubeTranscriptJob] = {}
_lock = threading.Lock()
_worker_started = False


def enqueue_transcript_job(job: YouTubeTranscriptJob) -> str:
    """Queue one transcript enrichment job per video ID."""
    global _worker_started
    with _lock:
        if job.video_id in _pending_jobs:
            return "queued"
        _pending_jobs[job.video_id] = job
        _jobs.put(job)
        if not _worker_started:
            threading.Thread(target=_worker_loop, name="youtube-transcript-worker", daemon=True).start()
            _worker_started = True
    return "queued"


def cancel_transcript_job(video_id: str) -> bool:
    """Cancel a pending transcript job before expensive work starts."""
    with _lock:
        job = _pending_jobs.pop(video_id, None)
    if job:
        update_entry(
            job.memory_id,
            {
                "metadata": {
                    "transcription_status": "canceled",
                    "error": "quick_exit",
                }
            },
        )
    return job is not None


def _worker_loop() -> None:
    while True:
        job = _jobs.get()
        try:
            if _wait_until_ready(job):
                _run_job(job)
        finally:
            with _lock:
                _pending_jobs.pop(job.video_id, None)
            _jobs.task_done()


def _wait_until_ready(job: YouTubeTranscriptJob) -> bool:
    deadline = time.monotonic() + max(job.start_after_seconds, 0.0)
    while True:
        with _lock:
            if _pending_jobs.get(job.video_id) != job:
                return False
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return True
        time.sleep(min(remaining, 0.25))


def _run_job(job: YouTubeTranscriptJob) -> None:
    with _lock:
        if _pending_jobs.get(job.video_id) != job:
            return
        _pending_jobs.pop(job.video_id, None)

    result = fetch_transcript_with_source(job.video_id, allow_ytdlp=True, allow_asr=True)
    metadata = {"title": job.title, "channel": job.channel, "url": job.url, "video_id": job.video_id}
    if not result.text:
        update_youtube_memory(
            job.memory_id,
            classification="UNKNOWN",
            summary=f"Video pending transcript enrichment. No captions or local transcription available. Reason: {result.error}",
            transcription_status=result.status if result.status != "missing" else "failed",
            transcript_source=result.source,
            error=result.error,
            tags=["transcript-missing"],
        )
        return

    classification = classify_youtube_content(result.text, metadata)
    subtype = detect_actionable_subtype(result.text, metadata) if classification == "ACTIONABLE" else ""
    update_youtube_memory(
        job.memory_id,
        classification=classification,
        summary=f"{'Actionable' if classification == 'ACTIONABLE' else 'Leisure' if classification == 'LEISURE' else 'Unknown'} video. "
        f"Subtype: {subtype}. Transcript preview: {result.text[:300]}",
        transcript_preview=result.text[:2000],
        extracted_content=result.text[:24000],
        transcription_status="done",
        transcript_source=result.source,
        tags=[subtype] if subtype else [],
    )
