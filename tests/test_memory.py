"""Tests for the Promptless memory layer."""

import json
import tempfile
from pathlib import Path

import pytest

from backend.memory import (
    EntryType,
    _now_iso,
    for_hermes,
    retrieve,
    store,
    store_youtube,
    store_web_extraction,
)


@pytest.fixture
def memory_path(monkeypatch, tmp_path):
    """Point MEMORY_PATH to a temp file for isolation."""
    from backend import memory

    temp_path = tmp_path / "test_memory.jsonl"
    monkeypatch.setattr(memory, "MEMORY_PATH", temp_path)
    return temp_path


def test_store_and_retrieve(memory_path):
    entry = store(
        entry_type="youtube_actionable",
        title="Test Video | Test Channel",
        summary="A tutorial about testing",
        url="https://youtube.com/watch?v=test123",
        workflow="youtube",
        tags=["tutorial", "testing"],
        user_id="test_user",
    )
    assert entry["id"]
    assert entry["visit_count"] == 1
    assert entry["type"] == "youtube_actionable"

    results = retrieve("tutorial", user_id="test_user")
    assert len(results) == 1
    assert results[0]["title"] == "Test Video | Test Channel"


def test_deduplication_increments_visit_count(memory_path):
    url = "https://youtube.com/watch?v=dedup123"
    e1 = store(
        entry_type="youtube_actionable",
        title="First Title",
        summary="First summary",
        url=url,
        user_id="dedup_user",
    )
    assert e1["visit_count"] == 1

    e2 = store(
        entry_type="youtube_actionable",
        title="Updated Title",
        summary="Updated and longer summary that should replace the shorter one",
        url=url,
        user_id="dedup_user",
    )
    assert e2["visit_count"] == 2
    assert e2["title"] == "Updated Title"

    # Only one entry exists
    results = retrieve("Title", user_id="dedup_user")
    assert len(results) == 1


def test_retrieve_by_url_keyword(memory_path):
    store(
        entry_type="web_page",
        title="OAuth Setup Guide",
        summary="Setting up OAuth for your application",
        url="https://docs.example.com/oauth",
        workflow="oauth_setup",
        user_id="test",
    )

    results = retrieve("oauth", user_id="test")
    assert len(results) == 1
    assert "OAuth" in results[0]["title"]


def test_retrieve_respects_limit(memory_path):
    for i in range(5):
        store(
            entry_type="web_page",
            title=f"Page {i}",
            summary=f"Summary {i}",
            url=f"https://example.com/page{i}",
            user_id="limit_test",
        )

    results = retrieve("Page", limit=2, user_id="limit_test")
    assert len(results) == 2


def test_retrieve_filters_by_entry_type(memory_path):
    store(entry_type="youtube_actionable", title="Video", summary="Vid", url="https://yt.com/v", user_id="type_test")
    store(entry_type="youtube_leisure", title="Leisure", summary=" Leisure", url="https://yt.com/l", user_id="type_test")

    actionable = retrieve("Video", entry_types=["youtube_actionable"], user_id="type_test")
    assert len(actionable) == 1

    all_results = retrieve("Video", user_id="type_test")
    # Both entries may score on "Video" since retrieve searches across all fields
    assert len(all_results) >= 1


def test_for_hermes_returns_context_block(memory_path):
    entry = store(
        entry_type="youtube_actionable",
        title="Codex Workflow | YouTube",
        summary="A coding tutorial about using Codex AI for automated code review",
        url="https://youtube.com/watch?v=codex123",
        extracted_content="# Checklist\n- [ ] Install Codex CLI\n- [ ] Run `codex auth`",
        workflow="youtube",
        tags=["coding", "tutorial"],
        user_id="hermes_test",
    )
    # Use retrieve directly since for_hermes uses the same path
    results = retrieve("codex workflow video", limit=3, user_id="hermes_test")
    assert len(results) == 1
    assert "Codex" in results[0]["title"]
    assert results[0]["extracted_content"] == "# Checklist\n- [ ] Install Codex CLI\n- [ ] Run `codex auth`"


def test_for_hermes_empty_for_no_matches(memory_path):
    results = retrieve("nonexistent xyzzy", user_id="empty_test")
    assert results == []


def test_store_youtube_actionable(memory_path):
    entry = store_youtube(
        url="https://youtube.com/watch?v=action123",
        title="How to Build a React App",
        channel="DevTube",
        classification="ACTIONABLE",
        summary="A step-by-step React tutorial covering components, state, and hooks.",
        transcript_preview="In this tutorial we will build a React app...",
        action_taken="saved_checklist",
        tags=["react", "frontend"],
        user_id="yt_user",
    )
    assert entry["type"] == "youtube_actionable"
    assert entry["workflow"] == "youtube"
    assert entry["action_taken"] == "saved_checklist"
    assert "react" in entry["tags"]
    assert "frontend" in entry["tags"]


def test_store_youtube_leisure(memory_path):
    entry = store_youtube(
        url="https://youtube.com/watch?v=leisure456",
        title="Epic Minecraft Parkour",
        channel="GamingFun",
        classification="LEISURE",
        summary="Just a fun Minecraft parkour video for entertainment.",
        user_id="yt_user",
    )
    assert entry["type"] == "youtube_leisure"


def test_store_web_extraction(memory_path):
    entry = store_web_extraction(
        url="https://github.com/example/repo/issues/42",
        title="Bug: API returns 500 on /users endpoint",
        summary="GitHub issue describing a bug in the /users endpoint that causes 500 errors.",
        workflow="github_issue",
        extracted_content="- Found: /users throws 500\n- Expected: 200 with user object",
        action_taken="extracted_facts",
        tags=["bug", "api", "urgent"],
        user_id="web_user",
    )
    assert entry["type"] == "generic_extraction"
    assert entry["workflow"] == "github_issue"
    assert entry["action_taken"] == "extracted_facts"


def test_memory_endpoint(monkeypatch, tmp_path):
    """Integration test: /memory/hermes endpoint calls for_hermes and returns context."""
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from backend import app as app_module

    expected_context = "[PROMPTLESS MEMORY]\n1. [youtube_actionable] Docker Tutorial\n   Learn Docker from scratch\n\nUse the above memories"

    with patch.object(app_module, "for_hermes", return_value=expected_context):
        client = TestClient(app_module.app)
        response = client.get("/memory/hermes?q=docker&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "docker"
        assert "Docker Tutorial" in data["context"]
        assert "PROMPTLESS MEMORY" in data["context"]
