from backend.intent import rank_actions
from backend.schemas import IntentRequest, PageElement, RecentEvent


def action_ids(ctx: IntentRequest) -> list[str]:
    _intent, _confidence, actions = rank_actions(ctx)
    return [action.id for action in actions]


def test_selected_text_prioritizes_explanation():
    ctx = IntentRequest(
        url="https://docs.example.com/api/auth",
        title="Authentication reference",
        selectedText="OAuth refresh tokens expire after 30 days.",
        visibleText="This API uses OAuth access tokens and refresh tokens for authentication.",
    )

    intent, confidence, actions = rank_actions(ctx)

    assert confidence >= 0.65
    assert "understand" in intent
    assert actions[0].id == "explain_this"


def test_pricing_page_with_plan_controls_prioritizes_comparison():
    ctx = IntentRequest(
        url="https://example.com/pricing",
        title="Pricing plans",
        visibleText="Free plan $0 per month. Pro plan $20 per month. Enterprise custom pricing.",
        elements=[
            PageElement(tag="BUTTON", text="Choose Free plan"),
            PageElement(tag="BUTTON", text="Choose Pro plan"),
            PageElement(tag="BUTTON", text="Contact Enterprise"),
        ],
        recentEvents=[RecentEvent(type="hover", text="Pro plan", tag="BUTTON")],
    )

    assert action_ids(ctx)[0] == "compare_visible_options"


def test_github_issue_with_error_signals_prioritizes_debug_actions():
    ctx = IntentRequest(
        url="https://github.com/example/project/issues/42",
        title="TokenExchangeError on login",
        visibleText=(
            "Bug report\n"
            "Reproduction steps: click login, complete OAuth, return to callback.\n"
            "Actual result: TokenExchangeError and status code 500.\n"
            "Expected result: user session starts."
        ),
        recentEvents=[RecentEvent(type="click", text="Login", tag="BUTTON")],
    )

    intent, confidence, actions = rank_actions(ctx)

    assert confidence >= 0.9
    assert "debug" in intent
    assert [action.id for action in actions[:3]] == [
        "summarize_what_matters",
        "extract_key_facts",
        "what_should_i_do_next",
    ]
