"""YouTube workflow detection and transcript helpers."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Literal

from .schemas import SuggestedAction

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CACHE_DIR = DATA_DIR / "youtube_cache"
Classification = Literal["ACTIONABLE", "LEISURE", "UNKNOWN"]

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
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "", video_id)
    if not safe_id:
        return ""

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{safe_id}.txt"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    transcript = fetch_transcript_uncached(safe_id)
    if transcript:
        cache_path.write_text(transcript, encoding="utf-8")
    return transcript


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
