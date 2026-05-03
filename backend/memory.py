"""Per-user Promptless memory — feeds Hermes context when the user actually prompts."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import uuid4


class EntryType(str, Enum):
    YOUTUBE_ACTIONABLE = "youtube_actionable"
    YOUTUBE_LEISURE = "youtube_leisure"
    WEB_PAGE = "web_page"
    GITHUB_ISSUE = "github_issue"
    OAUTH_SETUP = "oauth_setup"
    PRICING_PAGE = "pricing_page"
    GENERIC_EXTRACTION = "generic_extraction"


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
MEMORY_PATH = DATA_DIR / "promptless_memory.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store(entry: dict) -> None:
    """Append a memory entry to the JSONL file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with MEMORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def _update(existing_id: str, updates: dict) -> None:
    """Update an entry by ID, rewriting the entire file."""
    if not MEMORY_PATH.exists():
        return
    lines = []
    with MEMORY_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("id") == existing_id:
                obj.update(updates)
                obj["last_accessed"] = _now_iso()
            lines.append(json.dumps(obj, ensure_ascii=False, default=str))
    with MEMORY_PATH.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def store(
    entry_type: str,
    title: str,
    summary: str,
    url: Optional[str] = None,
    workflow: Optional[str] = None,
    action_taken: Optional[str] = None,
    extracted_content: Optional[str] = None,
    tags: Optional[list[str]] = None,
    user_id: str = "default",
    metadata: Optional[dict] = None,
) -> dict:
    """
    Store a memory entry. Deduplicates by URL + user_id — updates visit_count
    and last_accessed instead of creating a duplicate.
    """
    entry_id = str(uuid4())
    created = _now_iso()

    # Deduplicate by url if provided
    if url:
        existing = _find_by_url(url, user_id)
        if existing:
            existing["visit_count"] = existing.get("visit_count", 1) + 1
            existing["last_accessed"] = created
            if summary and len(summary) > len(existing.get("summary", "")):
                existing["summary"] = summary
            existing["title"] = title  # Always update title on revisit
            if action_taken:
                existing["action_taken"] = action_taken
            if extracted_content:
                existing["extracted_content"] = extracted_content
            if tags:
                existing["tags"] = list(set(existing.get("tags", []) + tags))
            _update(existing["id"], existing)
            return existing

    entry = {
        "id": entry_id,
        "user_id": user_id,
        "type": entry_type,
        "created_at": created,
        "last_accessed": created,
        "title": title,
        "summary": summary,
        "url": url or "",
        "workflow": workflow or "",
        "action_taken": action_taken or "",
        "extracted_content": extracted_content or "",
        "tags": tags or [],
        "visit_count": 1,
        "metadata": metadata or {},
    }
    _store(entry)
    return entry


def _find_by_url(url: str, user_id: str) -> Optional[dict]:
    if not MEMORY_PATH.exists():
        return None
    with MEMORY_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("url") == url and obj.get("user_id") == user_id:
                return obj
    return None


def retrieve(query: str, limit: int = 5, entry_types: Optional[list[str]] = None, user_id: str = "default") -> list[dict]:
    """
    Search memories by keyword match across title, summary, tags, and extracted_content.
    Returns entries sorted by relevance score (keyword matches) then recency.
    """
    if not MEMORY_PATH.exists():
        return []

    query_terms = query.lower().split()

    scored: list[tuple[float, dict]] = []
    with MEMORY_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if entry.get("user_id") != user_id:
                continue
            if entry_types and entry.get("type") not in entry_types:
                continue

            score = _relevance_score(entry, query_terms)
            if score > 0:
                scored.append((score, entry))

    scored.sort(key=lambda x: (x[0], x[1].get("last_accessed", "")), reverse=True)
    return [entry for _, entry in scored[:limit]]


def _relevance_score(entry: dict, query_terms: list[str]) -> float:
    score = 0.0
    title_lower = entry.get("title", "").lower()
    summary_lower = entry.get("summary", "").lower()
    tags = entry.get("tags", [])
    extracted = entry.get("extracted_content", "").lower()
    url = entry.get("url", "").lower()

    for term in query_terms:
        if term in title_lower:
            score += 5
        if term in summary_lower:
            score += 2
        if term in url:
            score += 3
        if any(term in tag.lower() for tag in tags):
            score += 3
        if term in extracted:
            score += 1

    # Boost recently accessed
    if entry.get("last_accessed"):
        score += 0.5

    return score


def for_hermes(user_query: str, limit: int = 5, user_id: str = "default") -> str:
    """
    Build a memory context block to inject into a Hermes prompt.
    Called when the user prompts Hermes after browsing/watching.
    """
    memories = retrieve(user_query, limit=limit)
    if not memories:
        return ""

    lines = ["[PROMPTLESS MEMORY — things you know from the user's recent browsing and watching]\n"]

    for i, mem in enumerate(memories, 1):
        lines.append(f"{i}. [{mem['type']}] {mem['title']}")
        lines.append(f"   {mem['summary']}")
        if mem.get("url"):
            lines.append(f"   URL: {mem['url']}")
        if mem.get("extracted_content"):
            preview = mem["extracted_content"][:600]
            if len(mem["extracted_content"]) > 600:
                preview += "\n   ..."
            lines.append(f"   Extracted: {preview}")
        if mem.get("tags"):
            lines.append(f"   Tags: {', '.join(mem['tags'])}")
        lines.append("")

    lines.append("Use the above memories to answer the user's question. "
                  "If they reference something vague like 'that video' or 'that page', "
                  "identify the matching memory and use it.")
    return "\n".join(lines)


def store_youtube(
    url: str,
    title: str,
    channel: str,
    classification: str,  # "ACTIONABLE" or "LEISURE"
    summary: str,
    transcript_preview: Optional[str] = None,
    extracted_content: Optional[str] = None,
    action_taken: Optional[str] = None,
    tags: Optional[list[str]] = None,
    user_id: str = "default",
) -> dict:
    """Convenience wrapper for storing a YouTube watch memory."""
    entry_type = EntryType.YOUTUBE_ACTIONABLE.value if classification == "ACTIONABLE" else EntryType.YOUTUBE_LEISURE.value
    full_title = f"{title} | {channel}"
    all_tags = [classification.lower(), "youtube"] + (tags or [])

    return store(
        entry_type=entry_type,
        title=full_title,
        summary=summary,
        url=url,
        workflow="youtube",
        action_taken=action_taken,
        extracted_content=extracted_content,
        tags=all_tags,
        user_id=user_id,
        metadata={
            "channel": channel,
            "classification": classification,
            "transcript_preview": (transcript_preview or "")[:2000],
        },
    )


def store_web_extraction(
    url: str,
    title: str,
    summary: str,
    workflow: str,
    extracted_content: Optional[str] = None,
    action_taken: Optional[str] = None,
    tags: Optional[list[str]] = None,
    user_id: str = "default",
) -> dict:
    """Convenience wrapper for storing a web page extraction memory."""
    return store(
        entry_type=EntryType.GENERIC_EXTRACTION.value,
        title=title,
        summary=summary,
        url=url,
        workflow=workflow,
        action_taken=action_taken,
        extracted_content=extracted_content,
        tags=[workflow] + (tags or []),
        user_id=user_id,
    )
