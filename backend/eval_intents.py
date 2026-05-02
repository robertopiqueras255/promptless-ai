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

    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        ctx = IntentRequest(**payload)
        intent, confidence, actions = rank_actions(ctx)
        ranked = ", ".join(f"{action.id} ({action.score:.2f})" for action in actions) or "none"
        print(f"{path.name}")
        print(f"  intent: {intent} ({confidence:.2f})")
        print(f"  actions: {ranked}")


if __name__ == "__main__":
    main()
