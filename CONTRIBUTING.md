# Contributing

Promptless AI is early-stage and product direction matters as much as code. Use issues for intent, small branches for implementation, and pull requests for review.

## Collaboration Workflow

1. Open or link an issue before meaningful code changes.
2. Keep each branch focused on one behavior, bug, or documentation improvement.
3. Prefer small pull requests that can be reviewed in one pass.
4. Include test or eval evidence when behavior changes.
5. Keep privacy-sensitive traces, secrets, and local runtime data out of commits.

Good branch names:

```text
docs/local-setup
feature/privacy-preview-ui
fix/redaction-password-case
eval/developer-docs-intent-ranking
refactor/extension-build-source-of-truth
```

## Change Proposals

Use a proposal issue for product or architecture changes, including:

- New actions or action semantics.
- Intent ranking changes.
- Privacy routing changes.
- Cloud model routing.
- Desktop shell or cross-app context work.
- Extension build/tooling decisions.

The proposal should state the user problem, the intended behavior, acceptance criteria, and any privacy or UX risks.

## Pull Requests

Every PR should include:

- What changed.
- Why it changed.
- How it was tested.
- Risks or follow-up work.

For backend or privacy changes, run:

```bash
python -m pytest
```

For intent-ranking changes, also run:

```bash
python -m backend.eval_intents
```

For extension UI changes, manually load `extension/` as an unpacked Chrome or Chromium extension and validate against `test-page.html` plus at least one real page.

## Local Setup

Install backend dependencies from the repository root:

```bash
python -m pip install -r backend/requirements.txt
```

Run the backend:

```bash
python -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
```

During local debugging, force deterministic execution fallback instead of Hermes:

```bash
set PROMPTLESS_HERMES_ENABLED=0
```

On macOS/Linux:

```bash
export PROMPTLESS_HERMES_ENABLED=0
```

## Extension Source

The extension currently includes both TypeScript sources and runtime JavaScript files under `extension/src/`. Until a build step is added, keep runtime JavaScript in sync with any TypeScript changes or clearly mark a PR as TypeScript-only.

## Privacy Rules

- Do not commit `data/*.jsonl`.
- Do not add real API keys, tokens, customer data, screenshots with private content, or raw trace exports.
- Privacy changes need regression tests showing sensitive values are redacted and cloud routes are blocked where expected.
