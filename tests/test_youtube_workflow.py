from fastapi.testclient import TestClient

import backend.app as app_module
from backend.hermes_client import build_hermes_task, execute_fallback_action
from backend.schemas import IntentRequest
from backend.youtube import (
    TranscriptResult,
    classify_youtube_content,
    detect_actionable_subtype,
    extract_video_id,
    get_youtube_intervention,
)


def test_extract_video_id_handles_watch_short_and_embed_urls():
    assert extract_video_id("https://www.youtube.com/watch?v=abc123&list=xyz") == "abc123"
    assert extract_video_id("https://youtu.be/xyz789?t=12") == "xyz789"
    assert extract_video_id("https://www.youtube.com/shorts/short123") == "short123"
    assert extract_video_id("https://www.youtube.com/embed/embed123") == "embed123"


def test_youtube_classifier_detects_actionable_coding_video():
    transcript = (
        "In this tutorial we will install the package, clone the GitHub repo, "
        "run npm install, configure the API key, and verify the setup works."
    )
    metadata = {"title": "How to build a coding assistant", "channel": "Dev Channel"}

    assert classify_youtube_content(transcript, metadata) == "ACTIONABLE"
    assert detect_actionable_subtype(transcript, metadata) == "coding"


def test_youtube_intervention_returns_specific_allowed_actions():
    transcript = "This tutorial shows npm install, git clone, and code setup step by step."
    metadata = {"title": "React setup tutorial", "channel": "Dev Channel"}

    intervention = get_youtube_intervention("ACTIONABLE", transcript, metadata)

    assert intervention is not None
    assert intervention["workflow"] == "youtube"
    assert intervention["intent"] == "watching a coding guide"
    assert [action["id"] for action in intervention["actions"]] == [
        "extract_code_snippets",
        "save_tutorial_checklist",
    ]


def test_youtube_intervene_route_uses_transcript_and_logs_trace(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "fetch_transcript_with_source",
        lambda _video_id, allow_ytdlp=True, allow_asr=False: TranscriptResult(
            text=(
                "This tutorial shows how to code a project step by step. "
                "Run npm install, git clone the repo, configure the API, and verify the setup."
            ),
            source="youtube_caption",
            status="done",
        ),
    )
    monkeypatch.setattr(app_module, "log_intent", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module, "log_feedback", lambda *args, **kwargs: None)
    client = TestClient(app_module.app)

    response = client.post(
        "/youtube/intervene",
        json={
            "url": "https://www.youtube.com/watch?v=abc123",
            "title": "Coding tutorial",
            "channel": "Dev Channel",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["classification"] == "ACTIONABLE"
    assert payload["contextPatch"]["workflow"] == "youtube"
    assert payload["contextPatch"]["youtube"]["videoId"] == "abc123"
    assert payload["actions"][0]["id"] == "extract_code_snippets"
    assert payload["transcriptionStatus"] == "done"
    assert payload["transcriptSource"] == "youtube_caption"


def test_youtube_intervene_stores_unknown_and_defers_short_watch_transcription(monkeypatch, tmp_path):
    from backend import memory

    monkeypatch.setattr(memory, "MEMORY_PATH", tmp_path / "memory.jsonl")
    monkeypatch.setattr(
        app_module,
        "fetch_transcript_with_source",
        lambda _video_id, allow_ytdlp=True, allow_asr=False: TranscriptResult(
            text="",
            status="missing",
            error="captions_unavailable",
        ),
    )
    queued = []
    monkeypatch.setattr(app_module, "enqueue_transcript_job", lambda job: queued.append(job) or "queued")
    monkeypatch.setattr(app_module, "log_intent", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module, "log_feedback", lambda *args, **kwargs: None)
    client = TestClient(app_module.app)

    response = client.post(
        "/youtube/intervene",
        json={
            "url": "https://www.youtube.com/watch?v=nocaps123",
            "title": "Video without captions",
            "channel": "No Captions Channel",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["classification"] == "UNKNOWN"
    assert payload["transcriptionStatus"] == "deferred"
    assert payload["actions"] == []
    assert queued == []

    results = memory.retrieve("nocaps123", user_id="default")
    assert len(results) == 1
    assert results[0]["type"] == "youtube_unknown"
    assert results[0]["metadata"]["classification"] == "UNKNOWN"
    assert results[0]["metadata"]["transcription_status"] == "deferred"


def test_youtube_intervene_enqueues_after_watch_threshold(monkeypatch, tmp_path):
    from backend import memory

    monkeypatch.setattr(memory, "MEMORY_PATH", tmp_path / "memory.jsonl")
    monkeypatch.setattr(
        app_module,
        "fetch_transcript_with_source",
        lambda _video_id, allow_ytdlp=True, allow_asr=False: TranscriptResult(text="", status="missing"),
    )
    queued = []
    monkeypatch.setattr(app_module, "enqueue_transcript_job", lambda job: queued.append(job) or "queued")
    monkeypatch.setattr(app_module, "log_intent", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module, "log_feedback", lambda *args, **kwargs: None)
    client = TestClient(app_module.app)

    response = client.post(
        "/youtube/intervene",
        json={
            "url": "https://www.youtube.com/watch?v=delay123",
            "title": "Threshold transcription",
            "channel": "Dev Channel",
            "min_watch_time_ms": 10000,
        },
    )

    assert response.status_code == 200
    assert response.json()["transcriptionStatus"] == "queued"
    assert queued[0].video_id == "delay123"
    assert queued[0].start_after_seconds == 0.0


def test_youtube_cancel_endpoint(monkeypatch):
    canceled = []
    feedback = []
    monkeypatch.setattr(app_module, "cancel_transcript_job", lambda video_id: canceled.append(video_id) or True)
    monkeypatch.setattr(app_module, "log_feedback", lambda *args, **kwargs: feedback.append((args, kwargs)))
    client = TestClient(app_module.app)

    response = client.post("/youtube/cancel/cancel123")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "video_id": "cancel123", "canceled": True}
    assert canceled == ["cancel123"]
    assert feedback == [
        (
            (None, "youtube_transcription_canceled"),
            {"metadata": {"videoId": "cancel123", "canceled": True}},
        )
    ]


def test_youtube_hermes_task_uses_transcript_not_generic_page_context():
    ctx = IntentRequest(
        url="https://www.youtube.com/watch?v=abc123",
        title="Coding tutorial",
        visibleText="YouTube page chrome",
        youtube={"videoId": "abc123", "title": "Coding tutorial", "channel": "Dev Channel"},
        youtubeTranscript="Run npm install, then create app.py and verify the server starts.",
    )

    task = build_hermes_task("extract_code_snippets", ctx)

    assert "YouTube context" in task
    assert "Run npm install" in task
    assert "Use only the redacted/compressed page context, transcript, and metadata below" in task
    assert '"visibleText"' not in task


def test_youtube_fallback_extracts_code_commands_from_transcript():
    ctx = IntentRequest(
        url="https://www.youtube.com/watch?v=abc123",
        title="Coding tutorial",
        youtubeTranscript="First run git clone the repo. Then run npm install. Start with python app.py.",
    )

    result = execute_fallback_action("extract_code_snippets", ctx)

    assert result.startswith("Code and commands")
    assert "git clone" in result
    assert "npm install" in result
