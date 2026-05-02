# Promptless AI — Plan To Maximize 1B Outcome

## Goal

Move Promptless AI from a clever browser-extension MVP into a product path with real 1B-company potential: high-frequency use, defensible data, strong distribution, and expansion beyond webpage summarization.

## Core Recommendation

Do **not** abandon the browser extension immediately. Use it as the fastest learning wedge.

But the long-term company should not be “a Chrome extension.” It should become a **local-first intent OS / desktop agent** with browser, app, file, calendar, email, and voice context.

The winning shape:

> A proactive desktop companion that understands what the user is doing across apps and offers the next useful action before they prompt.

The browser extension is the first sensor. The desktop app becomes the product.

Critical addition: **privacy firewall before intelligence**. Raw context should never be sent to non-local models by default. Promptless needs a local privacy gateway that scans, redacts, classifies, and routes context before any cloud model sees it.

## Why Move Toward An Application

Chrome extension strengths:
- Fast to ship
- Easy structured context from webpages
- Good for docs/pricing/GitHub/ecommerce workflows
- Lower initial scope
- Great data collection wedge

Chrome extension weaknesses:
- Weak distribution
- Limited permissions/trust
- Web-only context
- Harder to charge serious money
- Chrome Web Store dependency
- Feels like a utility, not a daily operating layer

Desktop app strengths:
- Cross-app context: browser, files, screenshots, clipboard, calendar, terminal, email
- Always-on presence
- Better permission model under user control
- Better premium positioning
- Fits Alan’s Jarvis/Hermes thesis
- Lets Promptless become the interface to the computer, not just the web

Desktop app weaknesses:
- Harder onboarding
- More trust burden
- More platform complexity
- Must be excellent to justify install

Conclusion: **browser extension for wedge/data, desktop app for unicorn trajectory.**

## Strategic Positioning

Avoid positioning as:
- AI browser extension
- Page summarizer
- Chatbot overlay
- Copilot clone

Position as:

> Promptless AI is an intent engine for your computer. It notices what you are trying to do and offers the next useful action before you ask.

Alternative one-liners:
- “AI that knows what you need before you prompt.”
- “The missing intent layer between humans and software.”
- “Jarvis for work, starting in the browser.”

## Product Architecture Direction

### Phase 1 — Browser Intent Wedge

Keep current Chrome extension and FastAPI backend. Improve it until it reliably works on high-value web tasks.

Focus pages:
- API docs
- pricing pages
- GitHub issues/PRs
- SaaS dashboards
- admin panels
- legal/policy pages
- ecommerce comparison pages

Current architecture remains:

```text
Chrome Extension
  -> captures URL/title/selection/focus/events/visible elements
  -> sends context to local FastAPI backend

FastAPI Backend
  -> intent ranking
  -> action allowlist
  -> trace logging
  -> Hermes execution

Hermes
  -> concise text execution
```

Immediate upgrades:
1. Add LLM-backed ranker behind deterministic heuristic scorer.
2. Keep strict action allowlist.
3. Make traces useful for model training.
4. Build real demo pages and benchmark acceptance rate.

### Phase 2 — Desktop Shell

Build a local desktop application that runs the same backend but gains OS-level context.

Recommended stack:
- Tauri or Electron shell
- Local FastAPI backend already exists
- Browser extension connects to local app
- Optional browser native messaging host later

Desktop app modules:
- global command palette
- tray resident service
- screenshot/context capture with user permission
- clipboard observer
- active window/app title detection
- file-drop context
- local memory/profile
- settings/model routing
- feedback review

The browser extension becomes one plugin/sensor feeding the local desktop intent engine.

Target architecture:

```text
Promptless Desktop App
  ├── Intent Engine Backend
  ├── Privacy Gateway
  │   ├── Deterministic Secret Scanner
  │   ├── Local PII / Sensitive Entity Detector
  │   ├── Screenshot/OCR Redactor
  │   ├── Policy Router
  │   └── Local Placeholder Vault
  ├── Model Router
  │   ├── Local Small Model for intent/classification/redaction
  │   ├── Local Larger Model for private tasks
  │   └── Cloud Model only for safe/redacted tasks
  ├── Hermes Execution Adapter
  ├── Local Memory + Redacted Traces
  ├── Browser Extension Sensor
  ├── Screenshot/OCR Sensor
  ├── Clipboard Sensor
  ├── File Sensor
  └── Voice Sensor later
```

Raw local context stays on-device. The privacy gateway produces sanitized context for routing and execution. Cloud models receive only redacted task context unless the user explicitly overrides.

### Phase 2.5 — Privacy Gateway / Local Censor Layer

This is not optional. Privacy is a product moat and a trust prerequisite for desktop context.

Principle:

> Local models decide what cloud models are allowed to see.

Pipeline:

```text
Raw Context
  ↓
Deterministic Scanner
  ↓
Local PII / Sensitive Entity Detector
  ↓
Sensitivity Classifier
  ↓
Reversible Placeholder Redaction
  ↓
Policy Router
  ↓
Local Model or Redacted Cloud Model
```

#### Layer 1 — Deterministic Secret Scanner

Hard-block obvious secrets before any model call:

- API keys
- JWTs
- OAuth tokens
- SSH/private keys
- `.env` values
- AWS/GCP/Azure credentials
- Stripe keys
- OpenAI/Anthropic/OpenRouter keys
- session cookies
- bearer tokens
- database URLs
- wallet/private keys
- passwords

Examples:

```text
sk-live-abc123... -> [SECRET:STRIPE_KEY_1]
Bearer eyJhbGciOi... -> [SECRET:JWT_1]
postgres://user:pass@host/db -> [SECRET:DATABASE_URL_1]
```

#### Layer 2 — Local PII / Sensitive Entity Detector

Use local-only detection for fuzzy sensitive information:

- names
- emails
- phone numbers
- addresses
- company/customer names
- invoice IDs
- legal/medical/financial details
- proprietary project names
- private code snippets

Recommended MVP stack:

```text
regex/entropy scanner + Microsoft Presidio + GLiNER
```

Then add a small local GGUF model for judgment calls:

```text
Qwen2.5 1.5B/3B Instruct, Phi-3-mini, or similar via llama.cpp
```

#### Layer 3 — Sensitivity Labels And Policy Routing

Each context chunk gets a sensitivity label:

```json
{
  "chunkId": "ctx_17",
  "sensitivity": "business_confidential",
  "allowedRoute": "local_or_redacted_cloud"
}
```

Routing policy:

| Sensitivity | Route |
|---|---|
| `public` | cloud allowed |
| `low_sensitive` | cloud allowed after redaction |
| `personal` | redacted cloud or local |
| `business_confidential` | local preferred; redacted cloud only with approval |
| `secret` | local only; never cloud |
| `regulated` | local only |
| `unknown` | local or ask user |

Default rule: **if unsure, keep it local.**

#### Reversible Local Placeholder Vault

Replace sensitive values with stable placeholders before cloud calls, while preserving enough structure for reasoning.

Example:

```text
Email support@company.com about invoice INV-99281
```

becomes:

```text
Email [EMAIL_1] about invoice [INVOICE_ID_1]
```

The placeholder map stays local and encrypted. The app can rehydrate generated drafts locally before displaying them to the user.

#### Screenshot Privacy

Screenshots are high-risk by default.

Pipeline:

```text
Screenshot
  ↓
Local OCR
  ↓
Sensitive region detection
  ↓
Local blur/redaction boxes
  ↓
Send redacted image or OCR summary only
```

Most cloud calls should receive OCR-derived structured summaries, not raw screenshots.

#### Privacy Modes

User-facing modes:

- **Local Only** — nothing leaves machine
- **Redacted Cloud** — cloud receives sanitized context only
- **Cloud Allowed** — explicit permission for full context on this action/domain/session
- **Ask Every Time** — default for high-risk workflows

Add a privacy preview before cloud execution:

```text
Sending to cloud model:
- URL: docs.stripe.com/billing
- Redacted entities: 2
- Secrets removed: 0
- Risk: Low

[Use cloud] [Use local only]
```

For dangerous context:

```text
Blocked cloud route.
Reason:
- detected API key
- detected customer email
- detected private dashboard data

Use local model instead?
```

### Phase 3 — Vertical Killer Workflows

Do not try to be universally useful on day one. Pick 2-3 workflows where proactive assistance feels magical and monetizable.

Best initial verticals:

#### 1. Developer Research / Integration

Examples:
- user opens API docs -> “Build integration checklist”
- user highlights error -> “Diagnose this”
- user opens GitHub issue -> “Summarize failure and next fix”
- user compares pricing/API limits -> “Extract limits and recommend plan”

Why good:
- high willingness to pay
- users tolerate technical products
- context is text-rich
- Hermes can execute follow-up tasks
- distribution through dev communities is realistic

#### 2. Founder / Operator Web Work

Examples:
- terms page -> “Find dangerous clauses”
- pricing page -> “Compare with current stack”
- CRM/admin page -> “Draft follow-up”
- competitor page -> “Extract positioning and pricing”

Why good:
- clear business ROI
- bridges into Alan’s Webmaker/outbound/commerce projects
- can become an executive assistant layer

#### 3. Personal Knowledge / Document Work

Examples:
- PDF or web article -> “Extract decision facts”
- contract -> “Find obligations and deadlines”
- email thread -> “What do I need to reply?”

Why good:
- broad market
- high retention if memory works
- desktop app makes more sense here than extension-only

Recommendation: start with **developer research/integration** as the first killer wedge.

## Product Roadmap

### Week 1 — Make The Existing Extension Demo-Grade

1. Run Day 5 testing from `PLAN.md`:
   - Stripe docs
   - OpenAI docs
   - Shopify docs/admin
   - pricing pages
   - GitHub issues

2. Add acceptance metrics:
   - suggestions shown
   - accepted actions
   - dismissed actions
   - execution success
   - thumbs up/down
   - domain/page type
   - latency

3. Add a simple trace review dashboard or richer CLI output.

4. Add LLM ranker:
   - deterministic scorer proposes candidates
   - local privacy gateway sanitizes context first
   - LLM reranks/contextualizes labels only on redacted context
   - backend validates IDs/risk/confidence
   - fallback if LLM fails

5. Define the core north-star metric:
   - **Prompt Avoidance Rate**: % of times user clicks a suggested action instead of typing a prompt.

### Week 1.5 — Build The Privacy Gateway Before Cloud Routing

1. Add `backend/privacy.py` with:
   - `scan_secrets(text) -> list[Finding]`
   - `redact_text(text) -> RedactionResult`
   - `classify_sensitivity(text) -> SensitivityLabel`
   - `sanitize_context(ctx) -> SanitizedContext`
   - `route_context(sanitized, user_mode) -> ModelRoute`

2. Add deterministic detection for:
   - API keys
   - JWTs
   - bearer tokens
   - private keys
   - database URLs
   - cookies
   - passwords
   - `.env` style assignments
   - high-entropy strings

3. Add local PII/entity detection:
   - start with regex + Presidio + GLiNER
   - add optional local small-model classifier via llama.cpp later

4. Add redacted trace logging:
   - raw context stored only locally when needed
   - default trace store uses redacted context
   - telemetry/export path is opt-in and anonymized

5. Add route enforcement:
   - `secret`, `regulated`, `unknown` -> local only by default
   - `business_confidential` -> local or redacted cloud with approval
   - `public`, `low_sensitive` -> cloud after redaction

6. Add privacy tests:
   - no known secret patterns survive redaction
   - cloud route is blocked for secrets
   - placeholders are stable within a trace
   - rehydration only happens locally

### Week 2 — Build The Desktop App Shell

1. Create `desktop/` app around existing backend.
2. Add tray menu:
   - start/stop backend
   - open settings
   - open traces
   - open command palette
3. Add global hotkey:
   - “What am I doing?” / “Help with current context”
4. Add screenshot capture with explicit user action.
5. Add active-window metadata.
6. Keep all actions text-only and approval-gated.

### Week 3 — Browser Extension As Sensor For Desktop App

1. Extension sends context to desktop-local backend.
2. Desktop app owns settings, memory, model routing, traces.
3. Extension becomes lightweight UI surface.
4. Add local user memory:
   - role
   - tools used
   - frequent workflows
   - accepted action patterns
5. Add per-domain learning:
   - on docs sites, prefer integration checklists
   - on pricing pages, prefer plan comparison
   - on GitHub, prefer debugging summary

### Week 4 — Killer Workflow: Developer Integration Copilot

Build a complete demo around one workflow:

> User opens unfamiliar API docs. Promptless detects integration intent, extracts auth/rate limits/pricing/webhooks, creates an implementation checklist, and can hand off to Hermes to scaffold code.

Actions:
- Summarize auth flow
- Extract endpoints and limits
- Build integration checklist
- Generate test curl commands
- Create implementation plan
- Ask Hermes to inspect repo for integration points

This is much more valuable than generic summarization.

## Business Model

### Free

- browser-only suggestions
- limited daily executions
- local traces
- basic actions

### Pro — $20/month

- desktop app
- cross-app context
- model routing
- memory
- unlimited local actions
- screenshot/file context
- advanced dev/operator actions
- redacted cloud mode
- local privacy gateway

### Team — $30-50/seat/month

- shared workflow templates
- team promptless actions
- admin controls
- security policy
- audit logs
- private model gateway
- redacted trace exports
- organization-level sensitivity policies

### Enterprise

- local/VPC deployment
- SSO
- DLP / permission controls
- custom actions
- internal app integrations
- cloud-disable mode
- audit-ready privacy logs
- custom redaction dictionaries

## Data Moat Plan

Trace data must become a training asset, not a log dump.

Each trace should capture:
- context signature
- page type
- inferred intent
- candidate actions
- shown actions
- accepted/dismissed
- execution result
- thumbs up/down
- time to click
- whether user typed after dismissing
- final outcome if available

Training targets:
- intent classification
- action ranking
- label generation
- confidence calibration
- context compression quality

Important: keep privacy posture strong. For local-first users, offer opt-in anonymized telemetry only. Enterprise defaults to private/no telemetry.

Privacy rule for the data moat:

- train on redacted context and behavioral metadata by default
- never upload raw secrets, raw screenshots, private dashboard text, or regulated data
- keep placeholder maps local and encrypted
- allow users/teams to export only sanitized traces
- make sensitivity labels part of the training target so the intent engine learns what should stay local

This makes privacy part of the moat: Promptless learns intent patterns without needing to exfiltrate raw work context.

## Key Product Bet

The important leap is from “suggesting summaries” to “detecting workflows.”

Bad version:
- Summarize this page
- Explain this
- Extract facts

Good version:
- “Looks like you’re checking if Stripe Billing supports metered usage.”
- “Build an integration checklist?”
- “Find rate limits and webhook requirements?”
- “Generate test curl commands?”

The model should infer not just page category, but user work-in-progress.

## Risks And Mitigations

### Risk: Extension distribution is weak

Mitigation:
- use extension as wedge, not final form
- publish demos to dev Twitter/YouTube
- create desktop app with browser plugin companion
- focus on workflows with clear ROI

### Risk: Generic suggestions are ignored

Mitigation:
- verticalize around developer/founder workflows
- use contextual labels
- only show when confidence is high
- learn from dismissals aggressively

### Risk: OS-level context feels creepy

Mitigation:
- local-first
- explicit permissions
- visible tray status
- pause button
- action approval gate
- no autonomous destructive actions
- privacy preview before cloud calls
- local-only mode

### Risk: Sensitive information leaks to non-local models

Mitigation:
- raw context never leaves the machine by default
- deterministic secret scanner before model routing
- local PII/entity detector before cloud routing
- reversible local placeholders
- encrypted local placeholder vault
- cloud receives only redacted context
- `secret`, `regulated`, and `unknown` sensitivity routes are local-only by default
- screenshots are OCR-redacted locally before any cloud use
- enterprise can disable cloud entirely

### Risk: Latency kills proactive UX

Mitigation:
- deterministic scorer first
- cache context signatures
- async LLM rerank
- fast local/small model for classification
- execute only after click

### Risk: The product becomes Clippy

Mitigation:
- minimal UI
- high confidence threshold
- no nagging
- no anthropomorphic popups
- user-tunable sensitivity
- action suggestions only, not personality theater

## Success Metrics

Early demo metrics:
- >30% suggestion acceptance on target pages
- >70% thumbs-up on executed results
- <1.5s suggestion latency
- <10s execution latency for text actions
- <5% “annoying/irrelevant” feedback
- 0 known secret leakage in privacy test corpus
- 100% cloud-route blocking for detected secrets
- <300ms deterministic redaction overhead for typical page context

Product-market metrics:
- daily active usage >4 days/week
- >10 accepted actions/week/user
- >40% week-4 retention
- >5% free-to-paid conversion
- users describe it as “it knew what I needed”

## Recommended Next Move

1. Keep the current extension.
2. Finish Day 5 real-page validation.
3. Build the privacy gateway before any cloud LLM routing.
4. Add deterministic secret scanning, local PII detection, sensitivity labels, and redacted trace storage.
5. Add LLM-backed action reranking only on sanitized/redacted context.
6. Build a desktop shell that owns the backend/settings/memory/privacy controls.
7. Reframe as **Promptless Desktop / Intent OS**, not a Chrome extension.
8. Build the first killer workflow: developer API integration copilot.

## Final Thesis

The 1B path is not “better browser extension.”

The 1B path is:

> Local-first proactive AI layer for the computer, starting with browser context, expanding into desktop context, and compounding through intent/action feedback data.

Browser extension = wedge.  
Desktop app = product.  
Privacy gateway = trust moat.  
Intent/action dataset = moat.  
Hermes execution = leverage.
