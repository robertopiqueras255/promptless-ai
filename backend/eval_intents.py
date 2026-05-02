"""Run fixture contexts through deterministic intent ranking."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.intent import rank_actions  # noqa: E402
from backend.schemas import IntentRequest  # noqa: E402

EVAL_DIR = ROOT / "eval"


def main() -> None:
    files = sorted(EVAL_DIR.glob("*.json"))
    if not files:
        print(f"No fixtures found in {EVAL_DIR}")
        return

    failures = 0
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        expected = payload.pop("expected", {})
        ctx = IntentRequest(**payload)
        intent, confidence, actions = rank_actions(ctx)
        ranked = ", ".join(f"{action.id} ({action.score:.2f})" for action in actions) or "none"
        print(f"{path.name}")
        print(f"  intent: {intent} ({confidence:.2f})")
        print(f"  actions: {ranked}")
        failures += check_expectations(expected, intent, actions)

    if failures:
        raise SystemExit(f"{failures} eval expectation(s) failed")


def check_expectations(expected: dict, intent: str, actions) -> int:
    failures = 0
    if not expected:
        return failures

    first_action = actions[0].id if actions else None
    expected_first = expected.get("firstActionId")
    if expected_first and first_action != expected_first:
        print(f"  FAIL firstActionId: expected {expected_first}, got {first_action}")
        failures += 1

    intent_includes = expected.get("intentIncludes")
    if intent_includes and intent_includes not in intent:
        print(f"  FAIL intentIncludes: expected {intent_includes!r} in {intent!r}")
        failures += 1

    label = actions[0].label if actions else None
    expected_label = expected.get("firstActionLabel")
    if expected_label and label != expected_label:
        print(f"  FAIL firstActionLabel: expected {expected_label!r}, got {label!r}")
        failures += 1

    if failures == 0:
        print("  expectations: ok")
    return failures


if __name__ == "__main__":
    main()
