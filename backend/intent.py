"""Universal intent-mode ranking and context compression."""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Iterable, Literal
from urllib.parse import urlparse

from .actions import default_action, is_allowed_action
from .schemas import IntentRequest, SuggestedAction

CONFIDENCE_THRESHOLD = 0.65
IntentMode = Literal["understand", "decide", "compare", "extract", "debug", "act"]

MODE_ACTIONS: dict[IntentMode, list[tuple[str, float]]] = {
    "understand": [
        ("explain_this", 0.90),
        ("summarize_what_matters", 0.84),
        ("extract_key_facts", 0.76),
    ],
    "decide": [
        ("compare_visible_options", 0.90),
        ("summarize_what_matters", 0.82),
        ("what_should_i_do_next", 0.78),
    ],
    "compare": [
        ("compare_visible_options", 0.92),
        ("extract_key_facts", 0.82),
        ("summarize_what_matters", 0.76),
    ],
    "extract": [
        ("extract_key_facts", 0.90),
        ("answer_from_page_context", 0.80),
        ("summarize_what_matters", 0.74),
    ],
    "debug": [
        ("summarize_what_matters", 0.88),
        ("extract_key_facts", 0.82),
        ("what_should_i_do_next", 0.78),
    ],
    "act": [
        ("what_should_i_do_next", 0.88),
        ("answer_from_page_context", 0.80),
        ("summarize_what_matters", 0.74),
    ],
}

INTENT_LABELS: dict[IntentMode, str] = {
    "understand": "trying to understand this",
    "decide": "trying to decide what matters here",
    "compare": "trying to compare options",
    "extract": "trying to extract useful facts",
    "debug": "trying to debug a problem",
    "act": "trying to take the next action",
}


def fallback_rank(ctx: IntentRequest) -> tuple[str, float, list[SuggestedAction]]:
    """Compatibility wrapper for the deterministic universal ranker."""
    return rank_actions(ctx)


def rank_actions(ctx: IntentRequest) -> tuple[str, float, list[SuggestedAction]]:
    mode, confidence = infer_intent_mode(ctx)
    scores = score_universal_actions(ctx, mode)
    actions = make_actions(scores, ctx)[:3]
    if confidence < CONFIDENCE_THRESHOLD:
        return INTENT_LABELS[mode], confidence, []
    return INTENT_LABELS[mode], confidence, actions


def infer_intent_mode(ctx: IntentRequest) -> tuple[IntentMode, float]:
    text = combined_text(ctx).lower()
    url_title = f"{ctx.url} {ctx.title}".lower()
    controls = visible_controls(ctx)
    mode_scores: dict[IntentMode, float] = {
        "understand": 0.58,
        "decide": 0.52,
        "compare": 0.50,
        "extract": 0.54,
        "debug": 0.48,
        "act": 0.50,
    }

    if ctx.selectedText.strip() or ctx.focusedElement.strip():
        mode_scores["understand"] += 0.24
        mode_scores["extract"] += 0.10

    if is_docs_like(url_title, text):
        mode_scores["understand"] += 0.20
        mode_scores["extract"] += 0.10

    if is_article_like(url_title):
        mode_scores["understand"] += 0.22
        mode_scores["extract"] += 0.08

    if is_legal_or_policy(url_title, text):
        mode_scores["extract"] += 0.34
        mode_scores["understand"] += 0.10
        mode_scores["decide"] = min(mode_scores["decide"], 0.58)
        mode_scores["compare"] = min(mode_scores["compare"], 0.54)

    if has_long_explanatory_content(ctx.visibleText):
        mode_scores["understand"] += 0.12
        mode_scores["extract"] += 0.04

    debug_evidence = has_debug_evidence(text, url_title)

    if has_decision_signals(url_title, text) and not is_article_like(url_title) and not is_legal_or_policy(url_title, text):
        mode_scores["decide"] += 0.24
        mode_scores["compare"] += 0.16
        mode_scores["extract"] += 0.08

    option_count = count_option_signals(ctx, text)
    if option_count >= 3:
        mode_scores["compare"] += 0.26
        mode_scores["decide"] += 0.12
    elif option_count >= 2:
        mode_scores["compare"] += 0.16

    if has_extract_signals(text):
        mode_scores["extract"] += 0.22

    if debug_evidence:
        mode_scores["debug"] = max(mode_scores["debug"] + 0.38, 0.90)
        mode_scores["understand"] -= 0.08
        mode_scores["extract"] = min(mode_scores["extract"], 0.82)
        mode_scores["compare"] = min(mode_scores["compare"], 0.56)

    if has_action_signals(text, controls):
        mode_scores["act"] += 0.22
        mode_scores["decide"] += 0.08

    # Auth/API/reference docs often mention errors and responses. Keep them in
    # understand/extract unless there is strong issue evidence.
    if is_docs_like(url_title, text) and not debug_evidence:
        mode_scores["debug"] = min(mode_scores["debug"], 0.58)

    mode = max(mode_scores, key=mode_scores.get)
    confidence = min(max(mode_scores[mode], 0.0), 0.95)
    return mode, confidence


def score_universal_actions(ctx: IntentRequest, intent_mode: IntentMode) -> OrderedDict[str, float]:
    text = combined_text(ctx).lower()
    scores: OrderedDict[str, float] = OrderedDict()
    for action_id, score in MODE_ACTIONS[intent_mode]:
        _add(scores, action_id, score)

    if ctx.selectedText.strip():
        _add(scores, "explain_this", 0.90)
        _add(scores, "extract_key_facts", 0.80)

    url_title = f"{ctx.url} {ctx.title}".lower()
    if intent_mode not in {"understand", "debug", "extract"} and has_decision_signals(url_title, text):
        _add(scores, "compare_visible_options", 0.86)
        _add(scores, "what_should_i_do_next", 0.78)

    if has_extract_signals(text):
        _add(scores, "extract_key_facts", 0.86)

    if intent_mode not in {"debug", "extract"} and has_action_signals(text, visible_controls(ctx)):
        _add(scores, "what_should_i_do_next", 0.84)

    return scores


def make_actions(scores: OrderedDict[str, float], ctx: IntentRequest) -> list[SuggestedAction]:
    sorted_items = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [action_from_id(action_id, score, ctx) for action_id, score in sorted_items if score >= CONFIDENCE_THRESHOLD]


def action_from_id(action_id: str, score: float, ctx: IntentRequest) -> SuggestedAction:
    definition = default_action(action_id)
    return SuggestedAction(
        id=action_id,
        label=contextual_label(action_id, ctx),
        description=definition.description,
        risk=definition.risk,
        score=round(score, 3),
    )


def contextual_label(action_id: str, ctx: IntentRequest) -> str:
    labels = {
        "explain_this": "Explain this",
        "summarize_what_matters": "Summarize",
        "extract_key_facts": "Extract facts",
        "compare_visible_options": "Compare options",
        "what_should_i_do_next": "What next?",
        "answer_from_page_context": "Answer from page",
    }
    return labels.get(action_id, default_action(action_id).default_label)


def combined_text(ctx: IntentRequest, limit: int = 16000) -> str:
    element_text = " ".join(el.text for el in ctx.elements[:80] if el.text)
    event_text = " ".join((ev.text or ev.placeholder or "") for ev in ctx.recentEvents[-20:])
    return (
        f"{ctx.url} {ctx.title} {ctx.selectedText} {ctx.focusedElement} "
        f"{ctx.viewportSummary} {element_text} {event_text} {ctx.visibleText[:12000]}"
    )[:limit]


def _add(scores: OrderedDict[str, float], action_id: str, score: float) -> None:
    if not is_allowed_action(action_id):
        return
    scores[action_id] = max(scores.get(action_id, 0.0), min(max(score, 0.0), 1.0))


def is_docs_like(url_title: str, text: str) -> bool:
    docs_terms = [
        "docs.",
        "/docs",
        "/api",
        "/reference",
        "/guide",
        "documentation",
        "api reference",
        "getting started",
        "tutorial",
        "authentication",
        "authenticating",
    ]
    return any(term in url_title for term in docs_terms) or any(
        term in text for term in ["api key", "endpoint", "webhook", "sdk", "access token", "oauth"]
    )


def is_article_like(url_title: str) -> bool:
    return any(term in url_title for term in ["/blog", "/article", "/news", "blog ", "article "])


def is_legal_or_policy(url_title: str, text: str) -> bool:
    terms = ["privacy policy", "terms of service", "legal", "/privacy", "/terms", "data retention", "user rights"]
    return any(term in url_title or term in text for term in terms)


def has_long_explanatory_content(text: str) -> bool:
    paragraphs = [p for p in re.split(r"\n{2,}", text) if len(p.split()) >= 35]
    return len(paragraphs) >= 2 or len(text.split()) >= 250


def has_decision_signals(url_title: str, text: str) -> bool:
    terms = [
        "pricing",
        "plans",
        "billing",
        "choose",
        "which",
        "best",
        "compare",
        "alternative",
        "tradeoff",
        "product",
        "buy",
        "reviews",
    ]
    return any(term in url_title or term in text for term in terms)


def count_option_signals(ctx: IntentRequest, text: str) -> int:
    labels = [el.text.lower() for el in ctx.elements if el.text]
    option_words = ["free", "pro", "plus", "team", "business", "enterprise", "basic", "premium", "plan", "option"]
    count = sum(1 for label in labels[:80] if any(word in label for word in option_words))
    repeated_prices = len(re.findall(r"[$€£]\s?\d+|\d+\s?(?:usd|eur|gbp|/mo|per month)", text))
    return count + repeated_prices


def has_extract_signals(text: str) -> bool:
    number_count = len(re.findall(r"\b\d+(?:[.,]\d+)?(?:%|k|m|gb|mb|ms|s| days?| months?| users?| requests?)?\b", text))
    legal_terms = ["terms", "policy", "privacy", "requirements", "conditions", "limit", "date", "deadline"]
    return number_count >= 4 or any(term in text for term in legal_terms)


def has_debug_evidence(text: str, url_title: str) -> bool:
    strong_terms = [
        "traceback",
        "stack trace",
        "exception:",
        "uncaught exception",
        "internal server error",
        "status code 500",
        "status code 504",
        "500 error",
        "504 error",
        "segmentation fault",
        "tokenexchangeerror",
    ]
    if any(term in text for term in strong_terms):
        return True
    if any(term in url_title for term in ["/issues/", "/pull/"]):
        return True
    bug_terms = ["bug report", "reproduction steps", "expected result", "actual result"]
    return sum(1 for term in bug_terms if term in text) >= 2


def has_action_signals(text: str, controls: list[dict[str, str | None]]) -> bool:
    cta_terms = ["submit", "buy", "start", "continue", "book", "contact", "sign up", "checkout", "configure", "save"]
    control_text = " ".join(str(control.get("text") or "") for control in controls).lower()
    return any(term in text or term in control_text for term in cta_terms)


def visible_controls(ctx: IntentRequest) -> list[dict[str, str | None]]:
    return [
        {"tag": el.tag, "text": el.text[:160], "href": el.href}
        for el in ctx.elements[:80]
        if el.text or el.href
    ]


def compress_context(ctx: IntentRequest) -> dict[str, object]:
    headings = extract_headings(ctx.visibleText)
    snippets = top_relevant_snippets(ctx)
    return {
        "url": ctx.url,
        "domain": urlparse(ctx.url).netloc,
        "title": ctx.title,
        "selectedText": ctx.selectedText[:2000],
        "focusedElement": ctx.focusedElement[:500],
        "viewportSummary": ctx.viewportSummary[:1200],
        "headings": headings[:20],
        "recentEvents": [ev.model_dump(exclude_none=True) for ev in ctx.recentEvents[-20:]],
        "controls": visible_controls(ctx)[:80],
        "snippets": snippets[:8],
        "screenshotPath": ctx.screenshotPath,
    }


def extract_headings(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines()]
    candidates = []
    for line in lines:
        if not line or len(line) > 120:
            continue
        if len(line.split()) <= 12 and not line.endswith("."):
            candidates.append(line)
    return list(dict.fromkeys(candidates))[:30]


def top_relevant_snippets(ctx: IntentRequest) -> list[str]:
    text = ctx.visibleText or ""
    terms = keyword_terms(ctx)
    chunks = split_chunks(text, max_len=650)
    scored = []
    for chunk in chunks:
        lowered = chunk.lower()
        score = sum(1 for term in terms if term in lowered)
        if ctx.selectedText and ctx.selectedText[:80].lower() in lowered:
            score += 5
        if score:
            scored.append((score, chunk.strip()))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored[:8]] or [text[:1200].strip()] if text else []


def keyword_terms(ctx: IntentRequest) -> set[str]:
    base = {
        "price",
        "pricing",
        "plan",
        "limit",
        "api",
        "auth",
        "oauth",
        "token",
        "error",
        "date",
        "requirement",
        "compare",
        "policy",
    }
    for part in [ctx.title, ctx.url, ctx.selectedText, ctx.focusedElement, ctx.viewportSummary]:
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", part.lower()):
            base.add(token)
    return base


def split_chunks(text: str, max_len: int = 650) -> Iterable[str]:
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    for paragraph in paragraphs:
        if len(paragraph) <= max_len:
            yield paragraph
            continue
        for i in range(0, len(paragraph), max_len):
            yield paragraph[i : i + max_len]
