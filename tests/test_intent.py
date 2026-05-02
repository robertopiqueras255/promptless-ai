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
    assert actions[0].label == "Explain selection"


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

    _intent, _confidence, actions = rank_actions(ctx)

    assert actions[0].id == "compare_visible_options"
    assert actions[0].label == "Compare plans"
    assert any(action.id == "summarize_what_matters" and action.label == "Summarize tradeoffs" for action in actions)


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
    assert actions[0].label == "Summarize issue"
    assert actions[2].label == "Find next fix"


def test_focused_checkout_form_prioritizes_next_action():
    ctx = IntentRequest(
        url="https://shop.example.com/checkout",
        title="Checkout",
        focusedElement="INPUT email Email address email field input",
        visibleText="Shipping details. Enter your email address and continue to delivery options.",
        elements=[
            PageElement(tag="INPUT", text="email Email address email field input"),
            PageElement(tag="BUTTON", text="Continue"),
        ],
        recentEvents=[RecentEvent(type="focus", placeholder="Email address", tag="INPUT")],
    )

    intent, confidence, actions = rank_actions(ctx)

    assert confidence >= 0.85
    assert "next action" in intent
    assert actions[0].id == "what_should_i_do_next"
    assert actions[0].label == "Next step"


def test_passive_search_input_does_not_trigger_next_action():
    ctx = IntentRequest(
        url="https://example.com",
        title="Home",
        visibleText="",
        elements=[PageElement(tag="INPUT", text="Search search field input")],
    )

    intent, confidence, actions = rank_actions(ctx)

    assert confidence < 0.65
    assert actions == []


def test_recent_configure_click_boosts_action_help():
    ctx = IntentRequest(
        url="https://admin.example.com/integrations/slack",
        title="Slack integration settings",
        visibleText="Configure Slack notifications. Save changes after selecting the workspace and channel.",
        elements=[
            PageElement(tag="SELECT", text="workspace select"),
            PageElement(tag="SELECT", text="channel select"),
            PageElement(tag="BUTTON", text="Save changes"),
        ],
        recentEvents=[RecentEvent(type="click", text="Configure", tag="BUTTON")],
    )

    assert action_ids(ctx)[0] == "what_should_i_do_next"
