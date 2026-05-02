# Promptless AI

A proactive context engine that watches what you're doing and surfaces the right help before you have to ask. Built for the gap between passive browsing and active prompting.

**The core idea:** your browser copilot should know when you're stuck — on a tutorial, a recipe, an OAuth setup, a pricing page — and offer the exact next step without being asked. And when you do ask Hermes, he already knows what you were just watching or reading.

## How it works

```
You open a YouTube tutorial / GitHub issue / pricing page / form
    ↓
Extension detects the workflow type
    ↓
Backend fetches relevant context (transcript, page state, form fields)
    ↓
System decides: intervention or passive watch?
    ↓
If actionable → surface specific suggestion card
If passive → store in memory for later Hermes context
```

## Current workflows

### YouTube → Actionable video detection

When you open a YouTube video, Promptless fetches the public captions and classifies it:

- **ACTIONABLE** — tutorial, recipe, coding guide, how-to
  - Surfaces: "Save checklist", "Extract code", "Extract ingredients"
  - Stores: title, channel, transcript preview, extracted content
- **LEISURE** — vlog, reaction, entertainment
  - No suggestion shown
  - Stored in memory for later reference

### Web workflows

- **GitHub issues** — detect issue state, labels, assignees; suggest debug actions
- **OAuth/setup forms** — detect missing fields (redirect URI, client ID, scope)
- **Pricing pages** — compare plans, estimate usage

### Hermes memory integration

Everything Promptless sees gets written to `data/promptless_memory.jsonl`. When you prompt Hermes with something like:

> "I was watching a video about Codex workflow last week"

Hermes reads that memory and already knows what you watched, what was extracted, and can answer without you re-explaining.

## What's included

- **Chrome MV3 extension** — content script captures page context (title, URL, visible text, form fields, events)
- **Backend API** — intent ranking, action execution, YouTube workflow, privacy gateway
- **Local privacy gateway** — scans for secrets/PII, redacts traces, blocks cloud routing by default
- **Hermes execution** — routes to local Hermes CLI with deterministic fallback
- **Trace logging** — `data/traces.jsonl` for quality metrics

## Actions

**Web (universal):**

- `explain_this` — explain selected/focused concept
- `summarize_what_matters` — summarize key details for decision/action
- `extract_key_facts` — extract numbers, limits, dates, requirements
- `compare_visible_options` — compare plans/products/choices
- `what_should_i_do_next` — suggest next steps from page state
- `answer_from_page_context` — answer from captured context only

**YouTube:**

- `save_tutorial_checklist` — convert transcript to step checklist
- `extract_code_snippets` — pull commands from coding tutorials
- `extract_ingredients` — parse recipe transcripts

## Load the extension

1. Open Chrome or Chromium
2. Go to `chrome://extensions`
3. Enable Developer mode
4. Click "Load unpacked"
5. Select `promptless-ai/extension`

Click `Privacy` in the suggestion pill to preview the redacted context and route decision before executing.

## Backend

```bash
pip install -r backend/requirements.txt
python -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
```

Environment variables:

| Variable | Default | Description |
|---|---|---|
| `PROMPTLESS_HERMES_ENABLED` | `1` | Set `0` to force deterministic fallback |
| `PROMPTLESS_HERMES_TIMEOUT_SECONDS` | `45` | Hermes execution timeout |
| `PROMPTLESS_MAX_RESULT_CHARS` | `5000` | Panel result length limit |

```bash
# Health check
curl http://127.0.0.1:8000/health

# YouTube workflow
curl -X POST http://127.0.0.1:8000/youtube/intervene \
  -H 'content-type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=VIDEO_ID","title":"Tutorial","channel":"Channel"}'

# Trace review
python -m backend.review_traces
```

## Development

```bash
# All tests
python -m pytest

# Intent ranking fixtures
python -m backend.eval_intents

# Extension context helpers
node --test extension/src/context-utils.test.js
```

## Architecture

```
extension/src/
├── content.js       # Captures page context, renders suggestion pill
└── content.ts       # TypeScript source

backend/
├── app.py           # FastAPI routes (/intent, /execute, /youtube/intervene)
├── intent.py        # Intent ranking logic
├── hermes_client.py # Hermes execution + deterministic fallbacks
├── youtube.py       # YouTube transcript fetch + classification
├── privacy.py       # Privacy gateway (redaction, routing)
├── storage.py       # JSONL trace logging
└── review_traces.py # Quality report generator
```

## Where it's headed

The product is shifting from generic actions toward **workflow-specific interventions** — the system should recognize what you're trying to do and offer exactly what's missing. The YouTube workflow is the template: detect → extract → store in memory → surface specific action.

Coming next:

- GitHub issue workflow (debug actions, PR checklists)
- OAuth/setup workflow (missing field detection, config templates)
- Hermes memory skill (so you can ask "what was that video about" and get a real answer)
