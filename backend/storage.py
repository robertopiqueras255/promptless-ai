"""JSONL trace storage for intent predictions, executions, and feedback."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
TRACE_PATH = DATA_DIR / "traces.jsonl"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_trace_id() -> str:
    return str(uuid4())


def append_trace(record: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"ts": now_iso(), **record}
    with TRACE_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def log_intent(
    trace_id: str,
    request: dict[str, Any],
    response: dict[str, Any],
    privacy: dict[str, Any] | None = None,
) -> None:
    append_trace(
        {
            "type": "intent",
            "traceId": trace_id,
            "request": request,
            "response": response,
            "privacy": privacy or {},
        }
    )


def log_feedback(trace_id: str | None, event: str, action_id: str | None = None, metadata: dict[str, Any] | None = None) -> None:
    append_trace(
        {
            "type": "feedback",
            "traceId": trace_id,
            "event": event,
            "actionId": action_id,
            "metadata": metadata or {},
        }
    )


def log_execution(trace_id: str | None, action_id: str, result: str, metadata: dict[str, Any] | None = None) -> None:
    append_trace(
        {
            "type": "execution",
            "traceId": trace_id,
            "actionId": action_id,
            "result": result,
            "metadata": metadata or {},
        }
    )
