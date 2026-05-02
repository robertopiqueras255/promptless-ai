"""Local privacy gateway for Promptless AI context routing.

Raw browser/desktop context is scanned and redacted before it is stored in
training traces or sent to any cloud model. The placeholder map stays in memory
for local-only rehydration during a request; traces receive only redacted text.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Iterable, Literal

from .schemas import IntentRequest

SensitivityLabel = Literal["public", "low_sensitive", "personal", "business_confidential", "secret", "regulated", "unknown"]
RouteName = Literal["local", "cloud_redacted", "cloud_full"]


class PrivacyMode(StrEnum):
    LOCAL_ONLY = "local_only"
    REDACTED_CLOUD = "redacted_cloud"
    CLOUD_ALLOWED = "cloud_allowed"
    ASK_EVERY_TIME = "ask_every_time"


@dataclass(frozen=True)
class Finding:
    kind: str
    value: str
    placeholder: str
    start: int
    end: int
    sensitivity: SensitivityLabel


@dataclass
class RedactionResult:
    text: str
    findings: list[Finding] = field(default_factory=list)
    placeholder_map: dict[str, str] = field(default_factory=dict)

    def rehydrate(self, text: str) -> str:
        """Replace local placeholders with originals. Use only for local display."""
        restored = text
        for placeholder, original in sorted(self.placeholder_map.items(), key=lambda item: len(item[0]), reverse=True):
            restored = restored.replace(placeholder, original)
        return restored


@dataclass(frozen=True)
class SanitizedContext:
    context: dict[str, Any]
    sensitivity: SensitivityLabel
    findings: list[Finding]
    redaction_count: int
    placeholder_map: dict[str, str]


@dataclass(frozen=True)
class ModelRoute:
    route: RouteName
    cloud_allowed: bool
    reason: str
    sensitivity: SensitivityLabel


SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("PRIVATE_KEY", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----")),
    ("DATABASE_URL", re.compile(r"\b(?:postgres|postgresql|mysql|mongodb|redis)://[^\s'\"<>]+", re.IGNORECASE)),
    ("OPENAI_KEY", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("ANTHROPIC_KEY", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("STRIPE_KEY", re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("AWS_ACCESS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("BEARER_TOKEN", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}\b", re.IGNORECASE)),
    ("COOKIE", re.compile(r"\b(?:session|sid|auth|token|cookie)[_-]?(?:id|token)?\s*=\s*[^;\s]{12,}", re.IGNORECASE)),
    ("ENV_SECRET", re.compile(r"\b[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASS|DATABASE_URL)\s*=\s*[^\s'\"]+", re.IGNORECASE)),
    ("PASSWORD", re.compile(r"\b(?:password|passwd|pwd)\s*[:=]\s*[^\s'\"]{4,}", re.IGNORECASE)),
    ("WALLET_PRIVATE_KEY", re.compile(r"\b0x[a-fA-F0-9]{64}\b")),
]

PII_PATTERNS: list[tuple[str, re.Pattern[str], SensitivityLabel]] = [
    ("EMAIL", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE), "personal"),
    ("PHONE", re.compile(r"(?<!\w)(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\w)"), "personal"),
    ("INVOICE_ID", re.compile(r"\b(?:INV|INVOICE|ORDER|PO)[-# ]?\d{4,}\b", re.IGNORECASE), "business_confidential"),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "regulated"),
    ("CREDIT_CARD", re.compile(r"\b(?:\d[ -]*?){13,19}\b"), "regulated"),
]

BUSINESS_TERMS = {
    "customer", "crm", "internal", "private dashboard", "admin", "confidential", "contract", "invoice", "deal", "pipeline"
}
REGULATED_TERMS = {"medical", "patient", "diagnosis", "hipaa", "legal matter", "tax return", "ssn", "credit card"}


def scan_secrets(text: str) -> list[Finding]:
    """Detect obvious secrets and high-entropy token-looking strings."""
    findings = _scan_patterns(text, SECRET_PATTERNS, default_sensitivity="secret")
    occupied = [(f.start, f.end) for f in findings]
    for match in re.finditer(r"\b[A-Za-z0-9_-]{32,}\b", text):
        token = match.group(0)
        if _overlaps(match.start(), match.end(), occupied):
            continue
        if entropy(token) >= 4.2 and has_mixed_token_chars(token):
            findings.append(
                Finding("HIGH_ENTROPY_TOKEN", token, "", match.start(), match.end(), "secret")
            )
    return sorted(findings, key=lambda finding: (finding.start, -(finding.end - finding.start)))


def scan_sensitive_entities(text: str) -> list[Finding]:
    return _scan_patterns(text, [(k, p) for k, p, _ in PII_PATTERNS], sensitivity_by_kind={k: s for k, _, s in PII_PATTERNS})


def redact_text(text: str) -> RedactionResult:
    """Redact secrets and local sensitive entities using stable placeholders."""
    if not text:
        return RedactionResult(text="")

    candidates = scan_secrets(text) + scan_sensitive_entities(text)
    candidates = _dedupe_overlaps(candidates)
    counters: dict[str, int] = {}
    value_to_placeholder: dict[tuple[str, str], str] = {}
    placeholder_map: dict[str, str] = {}
    replacements: list[Finding] = []

    for finding in candidates:
        key = (finding.kind, finding.value)
        placeholder = value_to_placeholder.get(key)
        if placeholder is None:
            counters[finding.kind] = counters.get(finding.kind, 0) + 1
            prefix = "SECRET:" if finding.sensitivity == "secret" else ""
            placeholder = f"[{prefix}{finding.kind}_{counters[finding.kind]}]"
            value_to_placeholder[key] = placeholder
            placeholder_map[placeholder] = finding.value
        replacements.append(
            Finding(
                kind=finding.kind,
                value=finding.value,
                placeholder=placeholder,
                start=finding.start,
                end=finding.end,
                sensitivity=finding.sensitivity,
            )
        )

    redacted_parts: list[str] = []
    cursor = 0
    for finding in sorted(replacements, key=lambda item: item.start):
        redacted_parts.append(text[cursor:finding.start])
        redacted_parts.append(finding.placeholder)
        cursor = finding.end
    redacted_parts.append(text[cursor:])
    return RedactionResult("".join(redacted_parts), replacements, placeholder_map)


def classify_sensitivity(text: str, findings: Iterable[Finding] | None = None) -> SensitivityLabel:
    lowered = text.lower()
    finding_list = list(findings or [])
    sensitivities = {finding.sensitivity for finding in finding_list}
    if "secret" in sensitivities:
        return "secret"
    if "regulated" in sensitivities or any(term in lowered for term in REGULATED_TERMS):
        return "regulated"
    if any(term in lowered for term in BUSINESS_TERMS) or "business_confidential" in sensitivities:
        return "business_confidential"
    if "personal" in sensitivities:
        return "personal"
    if any(term in lowered for term in ["api key", "oauth", "token", "pricing", "docs", "documentation"]):
        return "low_sensitive"
    if text.strip():
        return "public"
    return "unknown"


def sanitize_context(ctx: IntentRequest) -> SanitizedContext:
    """Return a redacted context dict safe for default trace storage/cloud routing."""
    raw = ctx.model_dump()
    placeholder_map: dict[str, str] = {}
    findings: list[Finding] = []
    sanitized = _sanitize_value(raw, findings, placeholder_map)
    text_for_label = " ".join(_strings_from_value(raw))
    sensitivity = classify_sensitivity(text_for_label, findings)
    return SanitizedContext(
        context=sanitized if isinstance(sanitized, dict) else {},
        sensitivity=sensitivity,
        findings=findings,
        redaction_count=len(findings),
        placeholder_map=placeholder_map,
    )


def route_context(sanitized: SanitizedContext, user_mode: PrivacyMode | str = PrivacyMode.REDACTED_CLOUD) -> ModelRoute:
    mode = PrivacyMode(user_mode)
    sensitivity = sanitized.sensitivity
    if mode == PrivacyMode.LOCAL_ONLY:
        return ModelRoute("local", False, "user selected local-only mode", sensitivity)
    if sensitivity in {"secret", "regulated", "unknown"}:
        return ModelRoute("local", False, f"{sensitivity} context is local-only by default", sensitivity)
    if mode == PrivacyMode.ASK_EVERY_TIME:
        return ModelRoute("local", False, "approval required before cloud routing", sensitivity)
    if mode == PrivacyMode.CLOUD_ALLOWED:
        if sensitivity == "business_confidential":
            return ModelRoute("cloud_redacted", True, "business-confidential context uses redacted cloud route", sensitivity)
        return ModelRoute("cloud_full", True, "user explicitly allowed cloud for this context", sensitivity)
    if sensitivity == "business_confidential":
        return ModelRoute("local", False, "business-confidential context needs approval for redacted cloud", sensitivity)
    return ModelRoute("cloud_redacted", True, "redacted context allowed for cloud routing", sensitivity)


def _scan_patterns(
    text: str,
    patterns: list[tuple[str, re.Pattern[str]]],
    default_sensitivity: SensitivityLabel = "personal",
    sensitivity_by_kind: dict[str, SensitivityLabel] | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    for kind, pattern in patterns:
        for match in pattern.finditer(text):
            value = match.group(0)
            findings.append(
                Finding(
                    kind=kind,
                    value=value,
                    placeholder="",
                    start=match.start(),
                    end=match.end(),
                    sensitivity=(sensitivity_by_kind or {}).get(kind, default_sensitivity),
                )
            )
    return findings


def _dedupe_overlaps(findings: list[Finding]) -> list[Finding]:
    priority = {
        "PRIVATE_KEY": 0,
        "DATABASE_URL": 1,
        "OPENAI_KEY": 2,
        "ANTHROPIC_KEY": 2,
        "STRIPE_KEY": 2,
        "AWS_ACCESS_KEY": 2,
        "JWT": 3,
        "BEARER_TOKEN": 4,
        "ENV_SECRET": 5,
        "PASSWORD": 5,
    }
    # Choose the most specific secret type first, then fill non-overlapping
    # spans. This keeps `Bearer <jwt>` from hiding the JWT classification.
    candidates = sorted(findings, key=lambda f: (priority.get(f.kind, 50), f.start, -(f.end - f.start)))
    kept: list[Finding] = []
    for finding in candidates:
        if any(not (finding.end <= prev.start or finding.start >= prev.end) for prev in kept):
            continue
        kept.append(finding)
    return sorted(kept, key=lambda finding: finding.start)


def _overlaps(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    return any(not (end <= left or start >= right) for left, right in ranges)


def _sanitize_value(value: Any, findings: list[Finding], placeholder_map: dict[str, str]) -> Any:
    if isinstance(value, str):
        redacted = redact_text(value)
        offset = len(findings)
        findings.extend(redacted.findings)
        placeholder_map.update(redacted.placeholder_map)
        return redacted.text
    if isinstance(value, list):
        return [_sanitize_value(item, findings, placeholder_map) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_value(item, findings, placeholder_map) for key, item in value.items()}
    return value


def _strings_from_value(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings_from_value(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings_from_value(item)


def entropy(token: str) -> float:
    if not token:
        return 0.0
    counts = {char: token.count(char) for char in set(token)}
    length = len(token)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def has_mixed_token_chars(token: str) -> bool:
    return any(c.islower() for c in token) and any(c.isupper() for c in token) and any(c.isdigit() for c in token)
