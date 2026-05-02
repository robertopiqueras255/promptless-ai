# Promptless AI MVP

Promptless AI is a general-web assistant that predicts what kind of help the user needs on the current page and offers universal actions before the user prompts.

## Current Status

Current MVP:

- Chrome MV3 extension.
- Page context capture from the content script, with form fields represented by labels/placeholders instead of typed values.
- Recent click, hover, scroll, selection, and focus event tracking.
- Backend context POSTs to `http://127.0.0.1:8000/intent`.
- Deterministic intent-mode ranking across `understand`, `decide`, `compare`, `extract`, `debug`, and `act`.
- `traceId` returned with every intent response.
- Strict backend action allowlist and low-risk-only filtering.
- Compact pill renders backend suggestions.
- Suggestion pill includes a privacy preview that shows redacted context, sensitivity, redaction count, finding kinds, and local/cloud route status.
- Clicking a suggestion calls `/execute` and shows a compact result panel tied to the selected action and redacted page context.
- Feedback events post to `/feedback` and append to `data/traces.jsonl`.
- `/execute` routes to the local Hermes CLI when available, with deterministic fallback text if Hermes fails.
- Local privacy gateway scans browser context for secrets/PII, redacts trace context, labels sensitivity, and blocks cloud routes for secret/regulated/unknown context by default.
- `POST /privacy/preview` returns redacted context plus sensitivity/route metadata for a privacy preview UI.
- Context schema is multimodal-ready with optional focused element, viewport summary, and screenshot path fields. Screenshot capture is not implemented yet.

Universal visible actions:

- `explain_this`
- `summarize_what_matters`
- `extract_key_facts`
- `compare_visible_options`
- `what_should_i_do_next`
- `answer_from_page_context`

## Load The Extension

1. Open Chrome or Chromium.
2. Go to `chrome://extensions`.
3. Enable Developer mode.
4. Click "Load unpacked".
5. Select `promptless-ai/extension`.

If the backend is unavailable, the extension still shows static universal suggestions.

Click `Privacy` in the suggestion pill to preview the redacted page context and route decision before executing an action.

## Backend

From repo root:

```bash
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
```

Hermes execution defaults to:

```bash
/home/alan/.hermes/hermes-agent/.venv/bin/python -m hermes_cli.main chat --quiet
```

Set `PROMPTLESS_HERMES_ENABLED=0` to force deterministic fallback execution during local debugging.
Set `PROMPTLESS_HERMES_TIMEOUT_SECONDS` to tune the execution timeout, default `45`.
Set `PROMPTLESS_MAX_RESULT_CHARS` to tune panel result length, default `5000`.

On Windows PowerShell:

```powershell
$env:PROMPTLESS_HERMES_ENABLED = "0"
```

On macOS/Linux:

```bash
export PROMPTLESS_HERMES_ENABLED=0
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Privacy preview:

```bash
curl -X POST http://127.0.0.1:8000/privacy/preview \
  -H 'content-type: application/json' \
  -d '{"url":"https://docs.example.com","title":"Docs","visibleText":"Email support@example.com about invoice INV-99281"}'
```

Trace review:

```bash
python -m backend.review_traces
```

The trace review includes Prompt Avoidance Rate, acceptance/execution metrics, privacy sensitivity labels, route counts, and redaction finding kinds.

## Development

Run backend tests:

```bash
python -m pytest
```

Run deterministic intent fixtures:

```bash
python -m backend.eval_intents
```

Run extension context helper tests:

```bash
node --test extension/src/context-utils.test.js
```

If Git reports dubious ownership for this checkout, add the repository as a safe directory:

```bash
git config --global --add safe.directory "$(pwd)"
```

See `CONTRIBUTING.md` for the issue, branch, pull request, eval, and privacy workflow.
