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


def privacy_for_record(record: dict) -> dict:
    if record.get("type") == "execution":
        return (record.get("metadata") or {}).get("privacy") or {}
    return record.get("privacy") or {}


def privacy_counters(records: list[dict]) -> tuple[Counter, Counter, Counter, int]:
    labels = Counter((privacy_for_record(r) or {}).get("sensitivity", "(unknown)") for r in records)
    routes = Counter((privacy_for_record(r) or {}).get("route", "(unknown)") for r in records)
    finding_kinds: Counter[str] = Counter()
    redaction_total = 0
    for record in records:
        privacy = privacy_for_record(record)
        redaction_total += int(privacy.get("redactionCount") or 0)
        for kind in privacy.get("findingKinds") or []:
            finding_kinds[kind] += 1
    return labels, routes, finding_kinds, redaction_total


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
    dismissed_by_action = Counter(r.get("actionId") for r in feedback if r.get("event") == "dismissed" and r.get("actionId"))
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
    intent_privacy_labels, intent_privacy_routes, intent_finding_kinds, intent_redaction_total = privacy_counters(intents)
    execution_privacy_labels, execution_privacy_routes, execution_finding_kinds, execution_redaction_total = privacy_counters(executions)

    print(f"Trace file: {TRACE_PATH}")
    print(f"Total records: {len(records)}")
    print(f"Total intents: {len(intents)}")
    print(f"Total shown: {feedback_by_event['shown']} ({duplicate_shown} duplicate shown)")
    print(f"Total accepted: {feedback_by_event['accepted']}")
    print(f"Total executed: {len(executions)}")
    print(f"Total thumbs_up: {feedback_by_event['thumbs_up']}")
    print(f"Total thumbs_down: {feedback_by_event['thumbs_down']}")
    print(f"Total intent redactions: {intent_redaction_total}")
    print(f"Total execution redactions: {execution_redaction_total}")

    print_quality_report(
        intents=intents,
        feedback_by_event=feedback_by_event,
        shown_by_action=shown_by_action,
        accepted_by_action=accepted_by_action,
        dismissed_by_action=dismissed_by_action,
        executed_by_action=executed_by_action,
        thumbs_up_by_action=thumbs_up_by_action,
        thumbs_down_by_action=thumbs_down_by_action,
        page_dismissals=page_dismissals_from_feedback(feedback, intent_by_trace),
    )

    print("\nPrompt Avoidance Rate")
    print(f"  accepted/shown: {feedback_by_event['accepted']}/{feedback_by_event['shown']} ({percent(feedback_by_event['accepted'], feedback_by_event['shown'])})")

    print_counter("Intent privacy sensitivity labels", intent_privacy_labels)
    print_counter("Intent privacy routes", intent_privacy_routes)
    print_counter("Intent redaction finding kinds", intent_finding_kinds)
    print_counter("Execution privacy sensitivity labels", execution_privacy_labels)
    print_counter("Execution privacy routes", execution_privacy_routes)
    print_counter("Execution redaction finding kinds", execution_finding_kinds)

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


def print_quality_report(
    *,
    intents: list[dict],
    feedback_by_event: Counter,
    shown_by_action: Counter,
    accepted_by_action: Counter,
    dismissed_by_action: Counter,
    executed_by_action: Counter,
    thumbs_up_by_action: Counter,
    thumbs_down_by_action: Counter,
    page_dismissals: Counter,
) -> None:
    pages = {((record.get("request") or {}).get("url") or "(unknown)") for record in intents}
    total_shown_actions = sum(shown_by_action.values())
    print("\nPromptless AI Quality Report")
    print(f"  Pages observed: {len(pages)}")
    print(f"  Suggestions shown: {total_shown_actions}")
    print(f"  Accepted actions: {feedback_by_event['accepted']}")
    print(f"  Dismissed: {feedback_by_event['dismissed']}")
    print(f"  Executed actions: {sum(executed_by_action.values())}")
    print(f"  Prompt avoidance rate: {feedback_by_event['accepted']}/{total_shown_actions} ({percent(feedback_by_event['accepted'], total_shown_actions)})")

    print("\nBest actions")
    best_actions = sorted(
        shown_by_action,
        key=lambda action_id: (accepted_by_action[action_id], thumbs_up_by_action[action_id], -thumbs_down_by_action[action_id], shown_by_action[action_id]),
        reverse=True,
    )
    if not best_actions:
        print("  none")
    for action_id in best_actions[:5]:
        accepted = accepted_by_action[action_id]
        shown = shown_by_action[action_id]
        if accepted == 0:
            continue
        print(
            f"  {action_id}: accepted {accepted}/{shown} ({percent(accepted, shown)}), "
            f"executed {executed_by_action[action_id]}, thumbs +{thumbs_up_by_action[action_id]}/-{thumbs_down_by_action[action_id]}"
        )

    print("\nNoisy actions")
    noisy_actions = sorted(
        shown_by_action,
        key=lambda action_id: (dismissed_by_action[action_id], -accepted_by_action[action_id], shown_by_action[action_id]),
        reverse=True,
    )
    printed_noisy = False
    for action_id in noisy_actions[:5]:
        dismissed = dismissed_by_action[action_id]
        shown = shown_by_action[action_id]
        if dismissed == 0:
            continue
        printed_noisy = True
        print(
            f"  {action_id}: dismissed {dismissed}/{shown} ({percent(dismissed, shown)}), "
            f"accepted {accepted_by_action[action_id]}/{shown} ({percent(accepted_by_action[action_id], shown)})"
        )
    if not printed_noisy:
        print("  none")

    print("\nPages with most dismissals")
    if not page_dismissals:
        print("  none")
    for page, count in page_dismissals.most_common(8):
        print(f"  {page}: {count}")


def page_dismissals_from_feedback(feedback: list[dict], intent_by_trace: dict[str | None, dict]) -> Counter[str]:
    page_dismissals: Counter[str] = Counter()
    for record in feedback:
        if record.get("event") != "dismissed":
            continue
        intent = intent_by_trace.get(record.get("traceId")) or {}
        request = intent.get("request") or {}
        page = request.get("url") or "(unknown)"
        page_dismissals[page] += 1
    return page_dismissals


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
