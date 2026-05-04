# Promptless AI MVP Plan

## Scope

Build a Chrome extension that observes the active webpage, infers the user's likely intent, shows 1-3 useful actions, and executes the chosen action through the local backend/Hermes path.

Initial target pages:
- Docs and references
- Pricing and product pages
- Ecommerce listings
- Articles and forums
- Legal/policy pages
- Issue trackers and debugging pages

## Success Criteria

- User visits a page.
- Extension captures page context and recent behavior.
- Extension offers useful action suggestions before the user types a prompt.
- User clicks an action.
- Backend/Hermes returns a useful result.
- Feedback is logged to `data/traces.jsonl`.

## Architecture

- `extension/`: Chrome MV3 extension.
- `backend/`: FastAPI intent and execution service.
- `data/traces.jsonl`: JSONL trace store for intent requests and feedback.

## Action Allowlist

- `explain_this`
- `summarize_what_matters`
- `extract_key_facts`
- `compare_visible_options`
- `what_should_i_do_next`
- `answer_from_page_context`

## Day 1 - Extension Context Capture

Status: Complete

Tasks:
- [x] Create project scaffold.
- [x] Create Chrome extension manifest.
- [x] Capture URL, title, selected text, visible body text, interactive elements, and recent events.
- [x] Track click, hover, scroll, selection, and focus events.
- [x] Send context to backend on page load, selection, click, idle interval, and significant scroll.
- [x] Display static fake suggestions in a small non-chat pill.
- [x] Manual test as unpacked Chrome extension.

Notes:
- Day 1 uses static fallback suggestions in the extension so the browser UI can be tested before the backend intent engine exists.
- Runtime files are plain JavaScript for Chrome loading. TypeScript source files are included as the edit source for the planned build step.

## Day 2 - Intent Backend

Status: Complete

Tasks:
- [x] Build FastAPI app.
- [x] Add `POST /intent`.
- [x] Add intent schemas.
- [ ] Add LLM-backed JSON ranking.
- [x] Enforce action allowlist after model output.
- [x] Add deterministic fallback suggestions.
- [x] Return `traceId` with intent response.
- [x] Render backend suggestions in extension.
- [x] Add backend-side trace logging.
- [x] Redact trace context through local privacy gateway before storage.
- [x] Add privacy route metadata to intent traces.
- [x] Add low-risk-only filtering.
- [x] Validate backend `/execute` request/response shape with direct curl.
- [x] Manual Chrome extension action-click validation.
- [x] Suppress duplicate idle `/intent` calls when context is unchanged.

## Day 3 - Execution

Status: Hardened real Hermes adapter, extension validation pending

Tasks:
- [x] Add `POST /execute`.
- [x] Add placeholder Hermes client adapter.
- [x] Add real Hermes action prompt mapping.
- [x] Compress page context before execution.
- [x] Sanitize/redact execution context before Hermes or fallback receives it.
- [x] Log execution privacy route metadata.
- [x] Show result in compact extension UI.
- [x] Replace placeholder adapter with real Hermes CLI execution.
- [x] Smoke test backend adapter against real Hermes CLI.
- [x] Add configurable Hermes timeout protection.
- [x] Trim long Hermes output for panel display.
- [x] Fall back cleanly on missing CLI, non-zero exit, and empty output.
- [x] Return clean timeout error JSON.
- [x] Add structured backend execution logs.
- [x] Verify compressed context avoids raw page dumps.
- [x] Tighten action prompts for MVP text-only execution.
- [ ] Manual Chrome extension validation against real Hermes output.

## Day 4 - Feedback, Evaluation, And UX Tuning

Status: Complete for MVP tuning pass

Tasks:
- [x] Add `POST /feedback`.
- [x] Append intent traces to JSONL.
- [x] Append feedback events to JSONL.
- [x] Send accepted/dismissed feedback from extension.
- [x] Add request/trace correlation.
- [x] Add trace review script for intent, feedback, execution, action acceptance, thumbs, domains, pages, Prompt Avoidance Rate, and privacy labels/routes.
- [x] Add trace filtering for duplicate shown events, accepted actions, successful executions, and fallback usage.
- [x] Add eval fixtures for docs auth, pricing, GitHub issue, and error pages.
- [x] Add fixture runner for deterministic intent ranking.
- [x] Tune docs, pricing, and debugging page heuristics.
- [x] Tighten action-specific Hermes prompts.
- [x] Add action-specific result compaction for panel display.
- [x] Add minimal error styling to result panel.
- [x] Validate syntax, trace review, and fixture rankings.

## Day 5 - Demo Testing

Status: Automated fixture pass added, manual Chrome validation pending

Tasks:
- [x] Add deterministic eval coverage for Stripe-style docs.
- [x] Add deterministic eval coverage for OpenAI docs.
- [x] Add deterministic eval coverage for Shopify/OAuth setup.
- [x] Add deterministic eval coverage for pricing pages.
- [x] Add deterministic eval coverage for GitHub issues.
- [ ] Manual Chrome test on Stripe docs.
- [ ] Manual Chrome test on OpenAI docs.
- [ ] Manual Chrome test on Shopify admin/docs.
- [ ] Manual Chrome test on pricing pages.
- [ ] Manual Chrome test on GitHub issues.
- [ ] Tune static fallbacks and LLM prompt.

## Privacy Gateway / Unicorn Plan Implementation

Status: Core local gateway implemented

Tasks:
- [x] Add `backend/privacy.py` with deterministic secret scanner, entity redaction, sensitivity labels, sanitized context, and model route policy.
- [x] Detect API keys, JWTs, bearer tokens, private keys, database URLs, cookies, passwords, `.env` style secrets, wallet keys, and high-entropy tokens.
- [x] Detect local PII/entity patterns for emails, phone numbers, invoices/orders, SSNs, and credit-card-shaped values.
- [x] Use stable reversible placeholders within a redaction result.
- [x] Store redacted context in traces by default.
- [x] Route `secret`, `regulated`, and `unknown` context to local-only by default.
- [x] Add `/privacy/preview` for UI privacy previews.
- [x] Add privacy regression tests for secret redaction, route blocking, stable placeholders, rehydration, and redacted traces.
- [ ] Add optional Presidio/GLiNER local detectors.
- [ ] Add screenshot OCR/redaction pipeline.
- [ ] Add encrypted persistent placeholder vault.
- [ ] Add user-facing privacy mode controls in desktop shell.

## Universal Action Pivot

Status: Implemented

Tasks:
- [x] Replace visible action ontology with six universal actions.
- [x] Rank by user-help intent modes instead of page categories.
- [x] Add multimodal-ready schema fields without screenshot capture.
- [x] Update extension context plumbing for focused element and viewport summary.
- [x] Update Hermes prompts and fallback execution for universal actions.
- [x] Replace/broaden eval fixtures across general web page types.
- [x] Keep trace review compatible with generalized action IDs.
- [x] Preserve text-only execution and avoid browser automation.
