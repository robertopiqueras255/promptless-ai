"""Review Promptless AI JSONL traces from the terminal."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

TRACE_PATH = Path(__file__).resolve().parents[1] / "data" / "traces.jsonl"


def load_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"Skipping malformed line {line_no}: {exc}")
    return records


def domain_for(record: dict) -> str:
    request = record.get("request") or {}
    url = request.get("url") or ""
    if not url:
        return "(unknown)"
    return urlparse(url).netloc or url


def percent(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.0%"
    return f"{(numerator / denominator) * 100:.1f}%"


def print_counter(title: str, counter: Counter, limit: int = 10) -> None:
    print(f"\n{title}")
    if not counter:
        print("  none")
        return
    for key, count in counter.most_common(limit):
        print(f"  {key}: {count}")


def main() -> None:
    records = load_records(TRACE_PATH)
    intents = [r for r in records if r.get("type") == "intent"]
    feedback = [r for r in records if r.get("type") == "feedback"]
    executions = [r for r in records if r.get("type") == "execution"]

    feedback_by_event = Counter(r.get("event") for r in feedback)
    intent_by_trace = {r.get("traceId"): r for r in intents}
    shown_records = [r for r in feedback if r.get("event") == "shown"]
    duplicate_shown = count_duplicate_shown(shown_records, intent_by_trace)

    shown_by_action: Counter[str] = Counter()
    for record in shown_records:
        for action_id in (record.get("metadata") or {}).get("actionIds", []):
            shown_by_action[action_id] += 1

    accepted_by_action = Counter(r.get("actionId") for r in feedback if r.get("event") == "accepted" and r.get("actionId"))
    thumbs_up_by_action = Counter(r.get("actionId") for r in feedback if r.get("event") == "thumbs_up" and r.get("actionId"))
    thumbs_down_by_action = Counter(r.get("actionId") for r in feedback if r.get("event") == "thumbs_down" and r.get("actionId"))
    executed_by_action = Counter(r.get("actionId") for r in executions if r.get("actionId"))
    fallback_by_action = Counter(
        r.get("actionId")
        for r in executions
        if r.get("actionId") and (r.get("metadata") or {}).get("fallbackUsed")
    )
    success_by_action = Counter(
        r.get("actionId")
        for r in executions
        if r.get("actionId") and (r.get("metadata") or {}).get("status", "done") == "done"
    )

    intent_names = Counter((r.get("response") or {}).get("intent", "(unknown)") for r in intents)
    pages = Counter((r.get("request") or {}).get("url", "(unknown)") for r in intents)
    domains = Counter(domain_for(r) for r in intents)
    privacy_labels = Counter((r.get("privacy") or {}).get("sensitivity", "(unknown)") for r in intents)
    privacy_routes = Counter((r.get("privacy") or {}).get("route", "(unknown)") for r in intents)
    finding_kinds: Counter[str] = Counter()
    redaction_total = 0
    for record in intents:
        privacy = record.get("privacy") or {}
        redaction_total += int(privacy.get("redactionCount") or 0)
        for kind in privacy.get("findingKinds") or []:
            finding_kinds[kind] += 1

    print(f"Trace file: {TRACE_PATH}")
    print(f"Total records: {len(records)}")
    print(f"Total intents: {len(intents)}")
    print(f"Total shown: {feedback_by_event['shown']} ({duplicate_shown} duplicate shown)")
    print(f"Total accepted: {feedback_by_event['accepted']}")
    print(f"Total executed: {len(executions)}")
    print(f"Total thumbs_up: {feedback_by_event['thumbs_up']}")
    print(f"Total thumbs_down: {feedback_by_event['thumbs_down']}")
    print(f"Total redactions: {redaction_total}")

    print("\nPrompt Avoidance Rate")
    print(f"  accepted/shown: {feedback_by_event['accepted']}/{feedback_by_event['shown']} ({percent(feedback_by_event['accepted'], feedback_by_event['shown'])})")

    print_counter("Privacy sensitivity labels", privacy_labels)
    print_counter("Privacy routes", privacy_routes)
    print_counter("Redaction finding kinds", finding_kinds)

    print("\nAcceptance rate per action")
    all_actions = sorted(set(shown_by_action) | set(accepted_by_action) | set(executed_by_action))
    if not all_actions:
        print("  none")
    for action_id in all_actions:
        shown = shown_by_action[action_id]
        accepted = accepted_by_action[action_id]
        executed = executed_by_action[action_id]
        successful = success_by_action[action_id]
        fallback = fallback_by_action[action_id]
        print(
            f"  {action_id}: accepted {accepted}/{shown} ({percent(accepted, shown)}), "
            f"executed {executed}, success {successful}, fallback {fallback}"
        )

    print("\nThumbs per action")
    all_thumb_actions = sorted(set(thumbs_up_by_action) | set(thumbs_down_by_action))
    if not all_thumb_actions:
        print("  none")
    for action_id in all_thumb_actions:
        print(f"  {action_id}: up {thumbs_up_by_action[action_id]}, down {thumbs_down_by_action[action_id]}")

    print_counter("Most common intents", intent_names)
    print_counter("Most common domains", domains)
    print_counter("Most common pages", pages, limit=8)


def count_duplicate_shown(shown_records: list[dict], intent_by_trace: dict[str | None, dict]) -> int:
    seen: set[tuple[str, tuple[str, ...]]] = set()
    duplicates = 0
    for record in shown_records:
        action_ids = tuple((record.get("metadata") or {}).get("actionIds", []))
        intent_record = intent_by_trace.get(record.get("traceId"), {})
        request = intent_record.get("request") or {}
        page_key = request.get("url") or record.get("traceId") or "(unknown)"
        key = (page_key, action_ids)
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)
    return duplicates


if __name__ == "__main__":
    main()
