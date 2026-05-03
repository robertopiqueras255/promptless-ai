import time

from backend import youtube_jobs
from backend.youtube_jobs import YouTubeTranscriptJob


def test_cancel_transcript_job_skips_before_processing(monkeypatch, tmp_path):
    from backend import memory

    monkeypatch.setattr(memory, "MEMORY_PATH", tmp_path / "memory.jsonl")
    entry = memory.store_youtube(
        url="https://youtube.com/watch?v=cancel-before-run",
        title="Cancel before run",
        channel="Dev Channel",
        classification="UNKNOWN",
        summary="Pending",
        video_id="cancel-before-run",
        transcription_status="queued",
    )
    processed = []
    monkeypatch.setattr(youtube_jobs, "_run_job", lambda job: processed.append(job.video_id))

    youtube_jobs.enqueue_transcript_job(
        YouTubeTranscriptJob(
            memory_id=entry["id"],
            video_id="cancel-before-run",
            title="Cancel before run",
            channel="Dev Channel",
            url="https://youtube.com/watch?v=cancel-before-run",
            start_after_seconds=0.2,
        )
    )
    assert youtube_jobs.cancel_transcript_job("cancel-before-run") is True

    time.sleep(0.4)

    assert processed == []
    results = memory.retrieve("cancel-before-run")
    assert results[0]["metadata"]["transcription_status"] == "canceled"
    assert results[0]["metadata"]["error"] == "quick_exit"
