"""YouTube workflow detection and transcript helpers."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .schemas import SuggestedAction

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CACHE_DIR = DATA_DIR / "youtube_cache"
Classification = Literal["ACTIONABLE", "LEISURE", "UNKNOWN"]


@dataclass(frozen=True)
class TranscriptResult:
    text: str
    source: str = ""
    status: str = "missing"
    error: str = ""

ACTIONABLE_TERMS = [
    "how to",
    "tutorial",
    "guide",
    "setup",
    "install",
    "configure",
    "fix",
    "debug",
    "build",
    "learn",
    "step by step",
    "recipe",
    "ingredients",
    "cook",
    "bake",
    "code",
    "programming",
    "github",
    "terminal",
    "command",
]
LEISURE_TERMS = [
    "music video",
    "official video",
    "trailer",
    "reaction",
    "vlog",
    "highlights",
    "comedy",
    "podcast",
    "live performance",
]


def extract_video_id(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    if host.endswith("youtu.be"):
        return parsed.path.strip("/").split("/", 1)[0]
    if "youtube.com" in host:
        query_id = urllib.parse.parse_qs(parsed.query).get("v", [""])[0]
        if query_id:
            return query_id
        match = re.search(r"/(?:shorts|embed)/([^/?#]+)", parsed.path)
        if match:
            return match.group(1)
    return ""


def fetch_transcript(video_id: str) -> str:
    """Fetch and cache public captions from YouTube's timedtext endpoint."""
    return fetch_transcript_with_source(video_id).text


def fetch_transcript_with_source(video_id: str, allow_ytdlp: bool = False, allow_asr: bool = False) -> TranscriptResult:
    """Fetch captions, then optionally fall back to yt-dlp captions or opt-in ASR."""
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "", video_id)
    if not safe_id:
        return TranscriptResult("", status="failed", error="invalid_video_id")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{safe_id}.txt"
    if cache_path.exists():
        return TranscriptResult(cache_path.read_text(encoding="utf-8"), source="cache", status="done")

    transcript = fetch_transcript_uncached(safe_id)
    if transcript:
        cache_path.write_text(transcript, encoding="utf-8")
        return TranscriptResult(transcript, source="youtube_caption", status="done")

    if allow_ytdlp:
        ytdlp_result = fetch_ytdlp_captions(safe_id)
        if ytdlp_result.text:
            cache_path.write_text(ytdlp_result.text, encoding="utf-8")
            return ytdlp_result
        if ytdlp_result.status == "failed":
            return ytdlp_result

    if allow_asr:
        asr_result = transcribe_audio_asr(safe_id)
        if asr_result.text:
            cache_path.write_text(asr_result.text, encoding="utf-8")
        return asr_result

    return TranscriptResult("", status="missing", error="captions_unavailable")


def fetch_transcript_uncached(video_id: str) -> str:
    list_url = "https://www.youtube.com/api/timedtext?" + urllib.parse.urlencode({"type": "list", "v": video_id})
    try:
        tracks_xml = http_get(list_url)
        tracks = ET.fromstring(tracks_xml)
    except (ET.ParseError, urllib.error.URLError, TimeoutError, OSError):
        return ""

    track = next(iter(tracks.findall("track")), None)
    if track is None:
        return ""

    params = {
        "v": video_id,
        "lang": track.attrib.get("lang_code", "en"),
        "name": track.attrib.get("name", ""),
    }
    transcript_url = "https://www.youtube.com/api/timedtext?" + urllib.parse.urlencode(params)
    try:
        transcript_xml = http_get(transcript_url)
        transcript = ET.fromstring(transcript_xml)
    except (ET.ParseError, urllib.error.URLError, TimeoutError, OSError):
        return ""

    chunks = []
    for node in transcript.findall("text"):
        if node.text:
            chunks.append(" ".join(node.text.split()))
    return "\n".join(chunks).strip()


def http_get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "PromptlessAI/0.1"})
    with urllib.request.urlopen(request, timeout=8) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_ytdlp_captions(video_id: str) -> TranscriptResult:
    """Try yt-dlp subtitle extraction without downloading media."""
    ytdlp_command = ytdlp_base_command()
    if not ytdlp_command:
        return TranscriptResult("", status="missing", error="yt_dlp_not_installed")

    url = f"https://www.youtube.com/watch?v={video_id}"
    with tempfile.TemporaryDirectory(prefix="promptless-youtube-") as temp_dir:
        output_template = str(Path(temp_dir) / "%(id)s.%(ext)s")
        command = [
            *ytdlp_command,
            "--skip-download",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs",
            "en.*",
            "--sub-format",
            "vtt",
            "--output",
            output_template,
            url,
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=45, check=False)
        except (subprocess.TimeoutExpired, OSError):
            return TranscriptResult("", status="failed", error="yt_dlp_caption_timeout")
        if result.returncode != 0:
            return TranscriptResult("", status="missing", error="yt_dlp_captions_unavailable")

        caption_files = sorted(Path(temp_dir).glob("*.vtt"))
        if not caption_files:
            return TranscriptResult("", status="missing", error="yt_dlp_captions_unavailable")
        transcript = parse_vtt(caption_files[0].read_text(encoding="utf-8", errors="replace"))
        return TranscriptResult(transcript, source="youtube_auto_caption", status="done") if transcript else TranscriptResult("", status="missing", error="empty_caption_file")


def transcribe_audio_asr(video_id: str) -> TranscriptResult:
    """Opt-in local ASR via faster-whisper after downloading audio with yt-dlp."""
    if not youtube_asr_enabled():
        return TranscriptResult("", status="skipped", error="asr_disabled")
    ytdlp_command = ytdlp_base_command()
    if not ytdlp_command:
        return TranscriptResult("", status="failed", error="yt_dlp_not_installed")
    os.environ.setdefault("HF_HOME", str(DATA_DIR / "huggingface"))

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return TranscriptResult("", status="failed", error="faster_whisper_not_installed")

    max_duration = int(os.getenv("PROMPTLESS_YOUTUBE_ASR_MAX_SECONDS", "1800"))
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        probe = subprocess.run([*ytdlp_command, "--dump-json", "--skip-download", url], capture_output=True, text=True, timeout=30, check=False)
    except (subprocess.TimeoutExpired, OSError):
        probe = None
    if probe and probe.returncode == 0:
        try:
            duration = int(float(json.loads(probe.stdout).get("duration") or 0))
        except (ValueError, json.JSONDecodeError, TypeError):
            duration = 0
        if duration and duration > max_duration:
            return TranscriptResult("", status="skipped", error="video_too_long")

    with tempfile.TemporaryDirectory(prefix="promptless-youtube-asr-") as temp_dir:
        audio_template = str(Path(temp_dir) / "%(id)s.%(ext)s")
        try:
            download = subprocess.run(
                [*ytdlp_command, "-f", "bestaudio[ext=m4a]/bestaudio", "--output", audio_template, url],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            return TranscriptResult("", status="failed", error="audio_download_timeout")
        if download.returncode != 0:
            return TranscriptResult("", status="failed", error="audio_download_failed")
        audio_files = [path for path in Path(temp_dir).iterdir() if path.is_file()]
        if not audio_files:
            return TranscriptResult("", status="failed", error="audio_file_missing")

        model_name = os.getenv("PROMPTLESS_YOUTUBE_ASR_MODEL", "base")
        model = WhisperModel(model_name, device="cpu", compute_type=os.getenv("PROMPTLESS_YOUTUBE_ASR_COMPUTE", "int8"))
        segments, _info = model.transcribe(str(audio_files[0]))
        transcript = "\n".join(segment.text.strip() for segment in segments if segment.text.strip())
        return TranscriptResult(transcript, source="asr_faster_whisper", status="done") if transcript else TranscriptResult("", status="failed", error="empty_asr_transcript")


def youtube_asr_enabled() -> bool:
    mode = os.getenv("PROMPTLESS_YOUTUBE_ASR", "").strip().lower()
    enabled = os.getenv("PROMPTLESS_YOUTUBE_ASR_ENABLED", "").strip().lower()
    if mode in {"faster-whisper", "faster_whisper"}:
        return True
    if enabled in {"1", "true", "yes", "on"}:
        return True
    return False


def ytdlp_base_command() -> list[str]:
    executable = shutil.which("yt-dlp")
    if executable:
        return [executable]
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        return []
    return [sys.executable, "-m", "yt_dlp"]


def parse_vtt(content: str) -> str:
    lines = []
    seen = set()
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line == "WEBVTT" or "-->" in line or line.isdigit() or line.startswith(("Kind:", "Language:", "NOTE")):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line and line not in seen:
            seen.add(line)
            lines.append(line)
    return "\n".join(lines)


def classify_youtube_content(transcript: str, metadata: dict[str, str]) -> Classification:
    text = combined_video_text(transcript, metadata)
    if len(text.split()) < 20:
        return "UNKNOWN"

    actionable_score = sum(1 for term in ACTIONABLE_TERMS if term in text)
    leisure_score = sum(1 for term in LEISURE_TERMS if term in text)

    if actionable_score >= 2 or any(term in text for term in ["step one", "first install", "copy this code", "preheat"]):
        return "ACTIONABLE"
    if leisure_score >= 1 and actionable_score == 0:
        return "LEISURE"
    return "UNKNOWN"


def detect_actionable_subtype(transcript: str, metadata: dict[str, str]) -> str:
    text = combined_video_text(transcript, metadata)
    if any(term in text for term in ["recipe", "ingredients", "tablespoon", "teaspoon", "preheat", "bake", "cook"]):
        return "recipe"
    if any(term in text for term in ["code", "github", "terminal", "npm", "python", "install", "api", "programming"]):
        return "coding"
    return "tutorial"


def get_youtube_intervention(
    classification: Classification,
    transcript: str,
    metadata: dict[str, str],
) -> dict[str, object] | None:
    if classification != "ACTIONABLE":
        return None

    subtype = detect_actionable_subtype(transcript, metadata)
    channel = metadata.get("channel") or "this channel"
    title = metadata.get("title") or "this video"

    if subtype == "recipe":
        actions = [
            SuggestedAction(
                id="extract_ingredients",
                label="Extract ingredients",
                description="Create an ingredients list, steps, and cooking notes from the transcript.",
                score=0.92,
            ),
            SuggestedAction(
                id="save_tutorial_checklist",
                label="Save checklist",
                description="Turn the recipe walkthrough into a step-by-step checklist.",
                score=0.84,
            ),
        ]
        body = f"Recipe video from {channel}."
        intent = "watching a recipe walkthrough"
    elif subtype == "coding":
        actions = [
            SuggestedAction(
                id="extract_code_snippets",
                label="Extract code",
                description="Pull commands, snippets, and setup details from the tutorial transcript.",
                score=0.94,
            ),
            SuggestedAction(
                id="save_tutorial_checklist",
                label="Save checklist",
                description="Turn the coding tutorial into ordered implementation steps.",
                score=0.90,
            ),
        ]
        body = f"Tech tutorial from {channel}: {title}."
        intent = "watching a coding guide"
    else:
        actions = [
            SuggestedAction(
                id="save_tutorial_checklist",
                label="Save checklist",
                description="Turn the tutorial into prerequisites, steps, mistakes, and verification.",
                score=0.91,
            ),
        ]
        body = f"{title} by {channel} looks actionable."
        intent = "watching a tutorial"

    return {
        "workflow": "youtube",
        "subtype": subtype,
        "intent": intent,
        "title": "Actionable video detected",
        "body": body,
        "actions": [action.model_dump() for action in actions],
    }


def build_context_patch(transcript: str, metadata: dict[str, str], classification: Classification) -> dict[str, object]:
    return {
        "workflow": "youtube",
        "youtube": {
            "videoId": metadata.get("video_id", ""),
            "title": metadata.get("title", ""),
            "channel": metadata.get("channel", ""),
            "url": metadata.get("url", ""),
            "classification": classification,
        },
        "youtubeTranscript": transcript[:24000],
    }


def combined_video_text(transcript: str, metadata: dict[str, str]) -> str:
    return f"{metadata.get('title', '')} {metadata.get('channel', '')} {transcript}".lower()


def transcript_from_context_dump(context: dict[str, object]) -> str:
    transcript = context.get("youtubeTranscript") or ""
    return str(transcript)


def youtube_metadata_from_context_dump(context: dict[str, object]) -> dict[str, str]:
    metadata = context.get("youtube")
    if isinstance(metadata, dict):
        return {str(key): str(value) for key, value in metadata.items()}
    return {
        "title": str(context.get("title") or ""),
        "url": str(context.get("url") or ""),
        "channel": "",
        "videoId": extract_video_id(str(context.get("url") or "")),
    }
