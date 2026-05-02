"""Allowed action definitions and validation helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionDefinition:
    id: str
    default_label: str
    description: str
    risk: str = "low"


ACTION_DEFINITIONS: dict[str, ActionDefinition] = {
    "explain_this": ActionDefinition(
        id="explain_this",
        default_label="Explain this",
        description="Explain the most relevant concept, selection, or focused section in plain English.",
    ),
    "extract_key_facts": ActionDefinition(
        id="extract_key_facts",
        default_label="Extract facts",
        description="Extract concrete facts, numbers, dates, names, requirements, and conditions.",
    ),
    "summarize_what_matters": ActionDefinition(
        id="summarize_what_matters",
        default_label="Summarize",
        description="Summarize only the most useful or decision-relevant information.",
    ),
    "compare_visible_options": ActionDefinition(
        id="compare_visible_options",
        default_label="Compare options",
        description="Compare the main visible options, plans, products, or choices.",
    ),
    "what_should_i_do_next": ActionDefinition(
        id="what_should_i_do_next",
        default_label="What next?",
        description="Suggest the next useful actions or checks based on the current page.",
    ),
    "answer_from_page_context": ActionDefinition(
        id="answer_from_page_context",
        default_label="Answer from page",
        description="Answer the most likely question using only the current page context.",
    ),
}

ALLOWED_ACTION_IDS = frozenset(ACTION_DEFINITIONS)
LOW_RISK_ONLY = {action_id for action_id, action in ACTION_DEFINITIONS.items() if action.risk == "low"}


def is_allowed_action(action_id: str) -> bool:
    return action_id in ALLOWED_ACTION_IDS


def default_action(action_id: str) -> ActionDefinition:
    return ACTION_DEFINITIONS[action_id]
