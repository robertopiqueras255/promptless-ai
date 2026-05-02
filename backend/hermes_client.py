"""Hermes execution adapter for MVP text actions."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .actions import default_action
from .schemas import IntentRequest
from .intent import compress_context

HERMES_PYTHON = os.getenv("PROMPTLESS_HERMES_PYTHON", "/home/alan/.hermes/hermes-agent/.venv/bin/python")
HERMES_TIMEOUT_SECONDS = int(os.getenv("PROMPTLESS_HERMES_TIMEOUT_SECONDS", "45"))
HERMES_ENABLED = os.getenv("PROMPTLESS_HERMES_ENABLED", "1") != "0"
MAX_RESULT_CHARS = int(os.getenv("PROMPTLESS_MAX_RESULT_CHARS", "5000"))
logger = logging.getLogger(__name__)

ACTION_PROMPTS = {
    "explain_this": "Explain the most relevant concept, selection, or focused section in plain English. Return 1 short paragraph or 3 bullets max.",
    "summarize_what_matters": "Summarize only the most decision-relevant or useful points. Return 3-6 bullets.",
    "extract_key_facts": "Return only concrete facts, numbers, limits, requirements, and links.",
    "compare_visible_options": "Compare the main visible options, plans, products, or choices. Focus on tradeoffs.",
    "what_should_i_do_next": "Suggest the next 1-3 useful actions or checks based on the visible page state.",
    "answer_from_page_context": "Answer the most likely user question from this page using only visible context.",
}


@dataclass(frozen=True)
class ExecutionOutcome:
    status: Literal["done", "error"]
    result: str
    hermes_used: bool
    fallback_used: bool
    duration_ms: int
    error: str | None = None


class HermesTimeoutError(RuntimeError):
    pass


def execute_text_action(action_id: str, ctx: IntentRequest | None, trace_id: str | None = None) -> ExecutionOutcome:
    started = time.monotonic()
    if ctx is None:
        return finish_execution(
            trace_id=trace_id,
            action_id=action_id,
            started=started,
            status="error",
            result="No page context was provided.",
            hermes_used=False,
            fallback_used=False,
            error="missing_context",
        )

    if HERMES_ENABLED:
        try:
            result = format_result_for_action(action_id, execute_with_hermes(action_id, ctx))
            return finish_execution(
                trace_id=trace_id,
                action_id=action_id,
                started=started,
                status="done",
                result=result,
                hermes_used=True,
                fallback_used=False,
            )
        except HermesTimeoutError as exc:
            return finish_execution(
                trace_id=trace_id,
                action_id=action_id,
                started=started,
                status="error",
                result="Hermes execution timed out.",
                hermes_used=True,
                fallback_used=False,
                error=str(exc),
            )
        except Exception as exc:
            fallback = format_result_for_action(action_id, execute_fallback_action(action_id, ctx))
            return finish_execution(
                trace_id=trace_id,
                action_id=action_id,
                started=started,
                status="done",
                result=fallback,
                hermes_used=True,
                fallback_used=True,
                error=str(exc),
            )

    return finish_execution(
        trace_id=trace_id,
        action_id=action_id,
        started=started,
        status="done",
        result=format_result_for_action(action_id, execute_fallback_action(action_id, ctx)),
        hermes_used=False,
        fallback_used=True,
    )


def execute_with_hermes(action_id: str, ctx: IntentRequest) -> str:
    hermes_python = Path(HERMES_PYTHON)
    if not hermes_python.exists():
        raise RuntimeError(f"Hermes Python not found at {hermes_python}")

    task = build_hermes_task(action_id, ctx)
    env = os.environ.copy()
    env.setdefault("HERMES_ACCEPT_HOOKS", "1")

    command = [
        str(hermes_python),
        "-m",
        "hermes_cli.main",
        "chat",
        "--quiet",
        "--source",
        "promptless-ai",
        "-q",
        task,
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=str(Path(__file__).resolve().parents[1]),
            env=env,
            text=True,
            capture_output=True,
            timeout=HERMES_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HermesTimeoutError(f"Hermes exceeded {HERMES_TIMEOUT_SECONDS}s") from exc

    output = clean_hermes_output(completed.stdout)
    if completed.returncode != 0:
        error = clean_hermes_output(completed.stderr) or f"Hermes exited with status {completed.returncode}"
        raise RuntimeError(error[:1000])
    if not output:
        raise RuntimeError("Hermes returned no output")
    return output


def build_hermes_task(action_id: str, ctx: IntentRequest) -> str:
    compressed = compress_context(ctx)
    action_prompt = ACTION_PROMPTS.get(action_id, default_action(action_id).description)
    likely_goal = infer_execution_goal(action_id, compressed)
    context_json = json.dumps(compressed, ensure_ascii=False, indent=2, default=str)
    return (
        "You are executing a low-risk text-only action for a promptless browser assistant.\n\n"
        f"User intent: {likely_goal}\n\n"
        f"Action ID: {action_id}\n"
        f"Action: {action_prompt}\n\n"
        f"Page context:\n{context_json}\n\n"
        "Return concise useful output for a small browser panel. "
        "Do not automate the browser, files, APIs, or OS."
    )


def infer_execution_goal(action_id: str, compressed: dict[str, object]) -> str:
    title = compressed.get("title") or compressed.get("url") or "this page"
    goals = {
        "explain_this": f"trying to understand {title}",
        "summarize_what_matters": f"trying to identify what matters on {title}",
        "extract_key_facts": f"trying to extract useful facts from {title}",
        "compare_visible_options": f"trying to compare options on {title}",
        "what_should_i_do_next": f"trying to decide what to do next on {title}",
        "answer_from_page_context": f"trying to answer a question from {title}",
    }
    return goals.get(action_id, f"reviewing {title}")


def clean_hermes_output(output: str) -> str:
    lines = [line.rstrip() for line in output.splitlines()]
    filtered = [
        line
        for line in lines
        if line.strip()
        and not line.lower().startswith("session_id:")
        and not line.lower().startswith("session id:")
        and not line.lower().startswith("session:")
    ]
    return "\n".join(filtered).strip()


def limit_output(text: str) -> str:
    cleaned = text.strip()
    if len(cleaned) <= MAX_RESULT_CHARS:
        return cleaned

    cutoff = max(0, MAX_RESULT_CHARS - len("\n\n[truncated]"))
    snippet = cleaned[:cutoff].rstrip()
    # Prefer ending at a line boundary if it does not discard too much.
    line_cut = snippet.rfind("\n")
    if line_cut >= int(cutoff * 0.75):
        snippet = snippet[:line_cut].rstrip()
    return f"{snippet}\n\n[truncated]"


def format_result_for_action(action_id: str, text: str) -> str:
    cleaned = normalize_text_lines(text)
    if action_id == "explain_this":
        return limit_output(compact_bullets("Explanation", cleaned, max_items=3))
    if action_id == "summarize_what_matters":
        return limit_output(compact_bullets("Summary", cleaned, max_items=6))
    if action_id == "extract_key_facts":
        return limit_output(compact_bullets("Key facts", cleaned, max_items=7, prefer_numbers=True))
    if action_id == "compare_visible_options":
        return limit_output(compact_bullets("Comparison", cleaned, max_items=7, prefer_numbers=True))
    if action_id == "what_should_i_do_next":
        return limit_output(compact_bullets("Next steps", cleaned, max_items=3))
    if action_id == "answer_from_page_context":
        return limit_output(compact_bullets("Answer", cleaned, max_items=5, prefer_numbers=True))
    return limit_output(cleaned)


def normalize_text_lines(text: str) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    compacted: list[str] = []
    blank = False
    for line in lines:
        if not line.strip():
            if not blank:
                compacted.append("")
            blank = True
            continue
        compacted.append(line.strip())
        blank = False
    return "\n".join(compacted).strip()


def compact_bullets(title: str, text: str, max_items: int, prefer_numbers: bool = False) -> str:
    items = extract_bulletish_lines(text)
    if prefer_numbers:
        numbered = [item for item in items if any(char.isdigit() for char in item)]
        rest = [item for item in items if item not in numbered]
        items = numbered + rest
    if not items:
        items = sentence_chunks(text)

    deduped = []
    seen = set()
    for item in items:
        normalized = " ".join(item.split())
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
        if len(deduped) >= max_items:
            break

    if not deduped:
        return title
    return title + "\n" + "\n".join(f"- {item}" for item in deduped)


def extract_bulletish_lines(text: str) -> list[str]:
    items = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        stripped = stripped.removeprefix("-").strip()
        stripped = re_numbered_prefix(stripped)
        if stripped.endswith(":"):
            continue
        if len(stripped.split()) <= 2 and not any(char.isdigit() for char in stripped):
            continue
        items.append(stripped[:420])
    return items


def re_numbered_prefix(text: str) -> str:
    parts = text.split(maxsplit=1)
    if len(parts) == 2 and parts[0].rstrip(".").isdigit():
        return parts[1].strip()
    return text


def sentence_chunks(text: str) -> list[str]:
    chunks = []
    for part in text.replace("\n", " ").split("."):
        part = part.strip()
        if part:
            chunks.append(part[:420])
    return chunks


def finish_execution(
    *,
    trace_id: str | None,
    action_id: str,
    started: float,
    status: Literal["done", "error"],
    result: str,
    hermes_used: bool,
    fallback_used: bool,
    error: str | None = None,
) -> ExecutionOutcome:
    duration_ms = int((time.monotonic() - started) * 1000)
    if error:
        logger.warning(
            "execute traceId=%s actionId=%s hermes_used=%s fallback_used=%s duration_ms=%s status=%s error=%s",
            trace_id,
            action_id,
            hermes_used,
            fallback_used,
            duration_ms,
            status,
            error,
        )
    else:
        logger.info(
            "execute traceId=%s actionId=%s hermes_used=%s fallback_used=%s duration_ms=%s status=%s",
            trace_id,
            action_id,
            hermes_used,
            fallback_used,
            duration_ms,
            status,
        )
    return ExecutionOutcome(
        status=status,
        result=result,
        hermes_used=hermes_used,
        fallback_used=fallback_used,
        duration_ms=duration_ms,
        error=error,
    )


def execute_fallback_action(action_id: str, ctx: IntentRequest) -> str:
    compressed = compress_context(ctx)
    title = compressed.get("title") or compressed.get("url") or "this page"
    selected = str(compressed.get("selectedText") or "").strip()
    snippets = [str(s) for s in compressed.get("snippets", [])]

    if action_id == "explain_this":
        focus = selected or str(compressed.get("focusedElement") or "") or first_snippet(snippets)
        return f"Explanation\n- {clean_line(focus) if focus else f'This page appears to be about {title}.'}"

    if action_id == "summarize_what_matters":
        return f"Summary\n" + bullet_snippets(snippets, max_items=5)

    if action_id == "extract_key_facts":
        return f"Key facts\n" + bullet_snippets(snippets, prefer_numbers=True, max_items=7)

    if action_id == "compare_visible_options":
        controls = compressed.get("controls", [])[:20]
        lines = [f"- {c.get('text') or c.get('href')}" for c in controls if isinstance(c, dict) and (c.get("text") or c.get("href"))]
        return "Comparison\n" + ("\n".join(lines[:7]) if lines else bullet_snippets(snippets, max_items=5))

    if action_id == "what_should_i_do_next":
        return (
            "Next steps\n"
            "- Review the most relevant visible details.\n"
            "- Compare any available options or requirements.\n"
            "- Use the page controls to continue only after confirming the key facts."
        )

    if action_id == "answer_from_page_context":
        return f"Answer\n" + bullet_snippets(snippets, max_items=4)

    return f"{default_action(action_id).default_label}:\n" + bullet_snippets(snippets)


def bullet_snippets(
    snippets: list[str],
    keywords: list[str] | None = None,
    max_items: int = 5,
    prefer_numbers: bool = False,
) -> str:
    filtered = snippets
    if keywords:
        lowered_keywords = [k.lower() for k in keywords]
        filtered = [s for s in snippets if any(k in s.lower() for k in lowered_keywords)] or snippets
    if prefer_numbers:
        numbered = [s for s in filtered if any(ch.isdigit() for ch in s)]
        filtered = numbered + [s for s in filtered if s not in numbered]
    if not filtered:
        return "- No relevant snippets found in captured context."
    return "\n".join(f"- {clean_line(snippet)}" for snippet in filtered[:max_items])


def first_snippet(snippets: list[str]) -> str:
    return snippets[0] if snippets else ""


def clean_line(text: str) -> str:
    return " ".join(text.split())[:500]
