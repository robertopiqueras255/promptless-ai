from backend.actions import ALLOWED_ACTION_IDS
from backend.hermes_client import build_hermes_task, execute_fallback_action
from backend.schemas import IntentRequest, PageElement, RecentEvent


def test_all_allowed_actions_have_panel_output_contract():
    ctx = IntentRequest(
        url="https://docs.example.com/api/auth",
        title="API Auth Docs",
        visibleText="OAuth tokens expire after 30 days. Rate limit is 1000 requests per hour.",
    )

    for action_id in ALLOWED_ACTION_IDS:
        task = build_hermes_task(action_id, ctx)

        assert "Panel output contract" in task
        assert "Use only the redacted/compressed page context" in task
        assert "Do not invent facts" in task
        assert "No chatty preamble" in task


def test_compare_task_has_table_contract_and_uses_compressed_context_only():
    ctx = IntentRequest(
        url="https://example.com/pricing",
        title="Pricing",
        visibleText=(
            "Free plan is $0 per month for 1 user. "
            "Pro plan is $20 per month for 5 users. "
            "Enterprise has custom pricing and SSO."
        ),
    )

    task = build_hermes_task("compare_visible_options", ctx)

    assert "Option | Best for | Key facts | Tradeoffs" in task
    assert "Recommendation" in task
    assert '"snippets"' in task
    assert '"visibleText"' not in task


def test_fallback_compare_visible_options_extracts_options_and_recommendation():
    ctx = IntentRequest(
        url="https://example.com/pricing",
        title="Pricing plans",
        visibleText=(
            "Free plan $0 per month for hobby projects.\n\n"
            "Pro plan $20 per month includes 5 seats and priority support.\n\n"
            "Enterprise custom pricing includes SSO and audit logs."
        ),
        elements=[
            PageElement(tag="BUTTON", text="Choose Free"),
            PageElement(tag="BUTTON", text="Choose Pro"),
            PageElement(tag="A", text="Contact Enterprise", href="/enterprise"),
        ],
    )

    result = execute_fallback_action("compare_visible_options", ctx)

    assert result.startswith("Comparison")
    assert "Free" in result and "$0" in result
    assert "Pro" in result and "$20" in result
    assert "Enterprise" in result
    assert "Recommendation" in result


def test_fallback_next_steps_uses_page_state_not_generic_advice():
    ctx = IntentRequest(
        url="https://shop.example.com/checkout",
        title="Checkout",
        visibleText="Enter your email address and continue to delivery options.",
        focusedElement="INPUT email Email address email field input",
        elements=[
            PageElement(tag="INPUT", text="email Email address email field input"),
            PageElement(tag="BUTTON", text="Continue"),
        ],
        recentEvents=[RecentEvent(type="focus", placeholder="Email address", tag="INPUT")],
    )

    result = execute_fallback_action("what_should_i_do_next", ctx)

    assert result.startswith("Next steps")
    assert "Email address" in result or "email" in result
    assert "Continue" in result
    assert "Review the most relevant visible details" not in result


def test_fallback_answer_uses_page_context_only_when_context_is_sparse():
    ctx = IntentRequest(
        url="https://docs.example.com/limits",
        title="Rate limits",
        visibleText="API requests are limited to 1000 per hour. Burst limit is 60 per minute.",
    )

    result = execute_fallback_action("answer_from_page_context", ctx)

    assert result.startswith("Answer")
    assert "1000 per hour" in result
    assert "Only from captured page context" in result
