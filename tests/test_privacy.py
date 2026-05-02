from backend.privacy import (
    PrivacyMode,
    classify_sensitivity,
    redact_text,
    route_context,
    sanitize_context,
    scan_secrets,
)
from backend.schemas import IntentRequest


def test_scan_secrets_detects_and_redacts_known_patterns():
    openai_key = "sk-" + "a" * 24
    jwt = "eyJ" + "a" * 20 + "." + "b" * 12 + "." + "c" * 12
    text = f"OpenAI key {openai_key} and token {jwt}"

    redacted = redact_text(text)

    assert redacted.findings
    assert "sk-abc" not in redacted.text
    assert "eyJhbGci" not in redacted.text
    assert "[SECRET:OPENAI_KEY_1]" in redacted.text
    assert "[SECRET:JWT_1]" in redacted.text


def test_cloud_route_blocked_for_secrets():
    sanitized = sanitize_context(
        IntentRequest(
            url="https://dashboard.example.com",
            title="Private dashboard",
            visibleText="DATABASE_URL=postgres://user:pass@example.com/db",
        )
    )

    route = route_context(sanitized, PrivacyMode.REDACTED_CLOUD)

    assert sanitized.sensitivity == "secret"
    assert route.route == "local"
    assert not route.cloud_allowed
    assert "secret" in route.reason.lower()


def test_placeholders_are_stable_within_trace_and_rehydrate_locally():
    text = "Email support@example.com, then cc support@example.com about invoice INV-99281."

    redacted = redact_text(text)

    assert redacted.text.count("[EMAIL_1]") == 2
    assert "[INVOICE_ID_1]" in redacted.text
    assert redacted.rehydrate(redacted.text) == text


def test_public_context_can_use_redacted_cloud():
    sanitized = sanitize_context(
        IntentRequest(
            url="https://docs.example.com/api/auth",
            title="API Authentication Docs",
            visibleText="Use OAuth tokens. Rate limit is 100 requests per minute.",
        )
    )

    route = route_context(sanitized, PrivacyMode.REDACTED_CLOUD)

    assert sanitized.sensitivity in {"public", "low_sensitive"}
    assert route.route == "cloud_redacted"
    assert route.cloud_allowed


def test_sanitize_context_removes_pii_from_trace_context():
    ctx = IntentRequest(
        url="https://crm.example.com/customer",
        title="Customer ACME Corp",
        selectedText="Contact jane.doe@example.com at +1 415-555-1212 about invoice INV-10001",
        visibleText="Password: hunter2 should not be sent anywhere.",
    )

    sanitized = sanitize_context(ctx)
    dumped = str(sanitized.context)

    assert "jane.doe@example.com" not in dumped
    assert "415-555-1212" not in dumped
    assert "hunter2" not in dumped
    assert sanitized.redaction_count >= 3
    assert sanitized.sensitivity in {"personal", "business_confidential", "secret"}
