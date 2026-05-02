const API_BASE = "http://127.0.0.1:8000";
const MAX_EVENTS = 50;
const SIGNIFICANT_SCROLL_PX = 350;
const IDLE_SEND_MS = 3000;
const MIN_PILL_VISIBLE_MS = 12000;
const DEBUG = false;

let recentEvents = [];
let lastScrollY = window.scrollY;
let lastSentAt = 0;
let dismissed = false;
let latestTraceId = null;
let lastContextSignature = "";
let lastSentSignature = "";
let activeExecution = false;
let resultVisible = false;
let visibleSuggestionKey = "";
let visibleSuggestionShownAt = 0;
let lastSuggestionIntent = "";
let lastSuggestionActions = [];
let lastSuggestionContext = null;
let lastSuggestionTraceId = null;

function debug(...args) {
  if (DEBUG) console.debug("[PromptlessAI]", ...args);
}

const staticActions = [
  {
    id: "summarize_what_matters",
    label: "Summarize",
    description: "Summarize only what matters on this page.",
    risk: "low"
  },
  {
    id: "extract_key_facts",
    label: "Extract facts",
    description: "Extract concrete facts, numbers, requirements, and conditions.",
    risk: "low"
  },
  {
    id: "what_should_i_do_next",
    label: "What next?",
    description: "Suggest the next useful actions or checks.",
    risk: "low"
  }
];

const {
  appendRecentEvent,
  formatFindingKinds,
  privacyRouteStatus,
  resultMetaText,
  resultParts,
  routeDescription,
  suggestionBasis,
  summarizePreviewContext,
  textForElement
} = globalThis.PromptlessContext;

function pushEvent(event) {
  recentEvents = appendRecentEvent(recentEvents, event, MAX_EVENTS);
}

function collectContext() {
  const selectedText = window.getSelection()?.toString() || "";
  const focusedElement = describeFocusedElement();
  const viewportSummary = buildViewportSummary();
  const elements = Array.from(document.querySelectorAll("button,a,input,textarea,select"))
    .slice(0, 200)
    .map((el, id) => {
      const rect = el.getBoundingClientRect();
      return {
        id,
        tag: el.tagName,
        text: textForElement(el),
        href: el.href || null,
        rect: typeof rect.toJSON === "function" ? rect.toJSON() : rect
      };
    });

  return {
    url: location.href,
    title: document.title,
    selectedText,
    focusedElement,
    visibleText: (document.body?.innerText || "").slice(0, 12000),
    viewportSummary,
    screenshotPath: null,
    elements,
    recentEvents
  };
}

function describeFocusedElement() {
  const el = document.activeElement;
  if (!el || el === document.body || el === document.documentElement) return "";
  const tag = el.tagName || "";
  const text = textForElement(el).slice(0, 160);
  const name = el.getAttribute?.("name") || "";
  const aria = el.getAttribute?.("aria-label") || "";
  return [tag, name, aria, text].filter(Boolean).join(" ");
}

function buildViewportSummary() {
  const headings = Array.from(document.querySelectorAll("h1,h2,h3"))
    .slice(0, 8)
    .map((el) => (el.textContent || "").trim())
    .filter(Boolean);
  return [document.title, ...headings].join(" | ").slice(0, 1200);
}

function contextSignature(context) {
  return [
    context.url,
    context.title,
    context.selectedText.slice(0, 240),
    context.visibleText.slice(0, 1200)
  ].join("|");
}

function ensureTraceId(traceId) {
  if (traceId) return traceId;
  if (latestTraceId) return latestTraceId;
  latestTraceId = `local-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  return latestTraceId;
}

async function sendContext(reason) {
  lastSentAt = Date.now();
  const context = collectContext();
  const signature = contextSignature(context);
  if (signature !== lastContextSignature) {
    dismissed = false;
    resultVisible = false;
    visibleSuggestionKey = "";
    lastContextSignature = signature;
  }

  if (reason === "idle" && signature === lastSentSignature) {
    debug("skip idle intent; context unchanged");
    return;
  }

  void chrome.runtime.sendMessage({
    type: "PROMPTLESS_CONTEXT",
    reason,
    context
  });

  lastSentSignature = signature;

  try {
    const response = await fetch(`${API_BASE}/intent`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(context)
    });

    if (!response.ok) {
      debug("intent non-ok", response.status, await response.text());
      renderStaticSuggestions(context);
      return;
    }

    const result = await response.json();
    debug("intent response", result);
    latestTraceId = result?.traceId || null;
    if (activeExecution || resultVisible) return;
    if (result?.confidence > 0.65 && Array.isArray(result.actions) && result.actions.length > 0) {
      renderSuggestions(result.intent || "working with this page", result.actions.slice(0, 3), context, latestTraceId);
    } else {
      hideSuggestions();
    }
  } catch (error) {
    debug("intent request failed", error);
    renderStaticSuggestions(context);
  }
}

function inferStaticIntent(context) {
  const text = `${context.title} ${context.url} ${context.selectedText} ${context.visibleText.slice(0, 2000)}`.toLowerCase();
  if (context.selectedText.trim()) return "trying to understand this";
  if (text.includes("pricing") || text.includes("plans") || text.includes("compare")) return "trying to compare options";
  if (text.includes("error") || text.includes("issue") || text.includes("traceback")) return "trying to debug a problem";
  return "trying to decide what matters here";
}

function renderStaticSuggestions(context) {
  if (dismissed) return;
  renderSuggestions(inferStaticIntent(context), staticActions, context, ensureTraceId(null));
}

function renderSuggestions(intent, actions, context, traceId) {
  if (dismissed || actions.length === 0) return;

  lastSuggestionIntent = intent;
  lastSuggestionActions = actions.slice(0, 3);
  lastSuggestionContext = context;
  lastSuggestionTraceId = traceId;

  const suggestionKey = actions
    .slice(0, 3)
    .map((action) => `${action.id}:${action.label}`)
    .join("|");
  if (visibleSuggestionKey === suggestionKey && document.getElementById("promptless-ai-root")) {
    debug("skip render; same suggestions already visible", suggestionKey);
    return;
  }

  let root = document.getElementById("promptless-ai-root");
  if (!root) {
    root = document.createElement("div");
    root.id = "promptless-ai-root";
    document.documentElement.appendChild(root);
  }

  root.innerHTML = "";
  resultVisible = false;
  visibleSuggestionKey = suggestionKey;
  visibleSuggestionShownAt = Date.now();

  const pill = document.createElement("div");
  pill.className = "promptless-pill";

  const intentWrap = document.createElement("div");
  intentWrap.className = "promptless-intent-wrap";

  const label = document.createElement("div");
  label.className = "promptless-intent";
  label.textContent = `Looks like you're ${intent}.`;

  const basis = document.createElement("div");
  basis.className = "promptless-basis";
  basis.textContent = suggestionBasis(context);

  intentWrap.append(label, basis);

  const actionsWrap = document.createElement("div");
  actionsWrap.className = "promptless-actions";

  actions.slice(0, 3).forEach((action) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "promptless-action";
    button.textContent = action.label;
    button.title = action.description;
    button.addEventListener("click", () => {
      const executionTraceId = ensureTraceId(traceId);
      pushEvent({ type: "click", text: action.label, tag: "PROMPTLESS_ACTION", ts: Date.now() });
      debug("selected action", { actionId: action.id, traceId: executionTraceId });
      void chrome.runtime.sendMessage({
        type: "PROMPTLESS_ACTION_CLICKED",
        actionId: action.id,
        traceId: executionTraceId,
        context
      });
      void postFeedback("accepted", executionTraceId, action.id, context);
      button.textContent = "Working...";
      button.disabled = true;
      void executeAction(action, context, executionTraceId, button);
    });
    actionsWrap.appendChild(button);
  });

  const privacy = document.createElement("button");
  privacy.type = "button";
  privacy.className = "promptless-privacy-button";
  privacy.textContent = "Privacy";
  privacy.title = "Preview the redacted context and model route before execution.";
  privacy.addEventListener("click", () => {
    void showPrivacyPreview(context, privacy);
  });

  const close = document.createElement("button");
  close.type = "button";
  close.className = "promptless-dismiss";
  close.textContent = "x";
  close.title = "Dismiss";
  close.addEventListener("click", () => {
    dismissed = true;
    hideSuggestions({ force: true });
    void chrome.runtime.sendMessage({ type: "PROMPTLESS_DISMISSED", traceId, context });
    void postFeedback("dismissed", ensureTraceId(traceId), null, context);
  });

  pill.append(intentWrap, actionsWrap, privacy, close);
  root.appendChild(pill);
}

function hideSuggestions({ force = false } = {}) {
  if (!force && visibleSuggestionKey && Date.now() - visibleSuggestionShownAt < MIN_PILL_VISIBLE_MS) {
    debug("keep pill visible; minimum read time not reached");
    return;
  }
  resultVisible = false;
  visibleSuggestionKey = "";
  visibleSuggestionShownAt = 0;
  document.getElementById("promptless-ai-root")?.remove();
}

async function postFeedback(event, traceId, actionId, context = null) {
  if (!traceId) return;
  try {
    const response = await fetch(`${API_BASE}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ traceId, event, actionId, context })
    });
    if (!response.ok) debug("feedback post failed", response.status, await response.text());
  } catch (error) {
    debug("feedback post failed", error);
    // Feedback is best-effort for MVP.
  }
}

async function showPrivacyPreview(context, triggerButton = null, onClose = null) {
  if (triggerButton) {
    triggerButton.disabled = true;
    triggerButton.textContent = "Checking...";
  }

  try {
    const response = await fetch(`${API_BASE}/privacy/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(context)
    });
    const text = await response.text();
    let preview = null;
    try {
      preview = text ? JSON.parse(text) : null;
    } catch {
      preview = { error: text || "Privacy preview failed." };
    }

    if (!response.ok) {
      showPrivacyPanel({ error: preview?.detail || preview?.error || `Privacy preview failed with HTTP ${response.status}.` }, onClose);
      return;
    }

    showPrivacyPanel(preview || {}, onClose);
  } catch (error) {
    debug("privacy preview failed", error);
    showPrivacyPanel({ error: "Privacy preview unavailable. Is the local backend running?" }, onClose);
  } finally {
    if (triggerButton) {
      triggerButton.disabled = false;
      triggerButton.textContent = "Privacy";
    }
  }
}

function showPrivacyPanel(preview, onClose = null) {
  let root = document.getElementById("promptless-ai-root");
  if (!root) {
    root = document.createElement("div");
    root.id = "promptless-ai-root";
    document.documentElement.appendChild(root);
  }

  root.innerHTML = "";
  resultVisible = true;
  visibleSuggestionKey = "";
  visibleSuggestionShownAt = 0;

  const panel = document.createElement("div");
  panel.className = preview?.error ? "promptless-privacy promptless-result-error" : "promptless-privacy";

  const header = document.createElement("div");
  header.className = "promptless-privacy-header";

  const title = document.createElement("div");
  title.className = "promptless-privacy-title";
  title.textContent = "Privacy preview";

  const status = document.createElement("div");
  const routeStatus = privacyRouteStatus(preview);
  status.className = routeStatus.className;
  status.textContent = routeStatus.label;

  header.append(title, status);

  const body = document.createElement("div");
  body.className = "promptless-privacy-body";

  if (preview?.error) {
    const error = document.createElement("p");
    error.className = "promptless-privacy-error";
    error.textContent = preview.error;
    body.appendChild(error);
  } else {
    body.append(
      makePrivacyMetric("Sensitivity", preview?.sensitivity || "unknown"),
      makePrivacyMetric("Redactions", String(preview?.redactionCount || 0)),
      makePrivacyMetric("Route", routeDescription(preview)),
      makePrivacyMetric("Finding kinds", formatFindingKinds(preview?.findingKinds))
    );

    const contextBlock = document.createElement("div");
    contextBlock.className = "promptless-context-preview";

    const contextTitle = document.createElement("div");
    contextTitle.className = "promptless-context-title";
    contextTitle.textContent = "Context used";

    const contextText = document.createElement("pre");
    contextText.className = "promptless-context-text";
    contextText.textContent = summarizePreviewContext(preview?.context || {});

    contextBlock.append(contextTitle, contextText);
    body.appendChild(contextBlock);
  }

  const controls = document.createElement("div");
  controls.className = "promptless-result-controls";

  const close = document.createElement("button");
  close.type = "button";
  close.textContent = "Close";
  close.addEventListener("click", () => {
    resultVisible = false;
    if (typeof onClose === "function") {
      onClose();
    } else if (lastSuggestionActions.length && lastSuggestionContext) {
      renderSuggestions(lastSuggestionIntent, lastSuggestionActions, lastSuggestionContext, lastSuggestionTraceId);
    } else {
      hideSuggestions({ force: true });
    }
  });

  controls.append(close);
  panel.append(header, body, controls);
  root.appendChild(panel);
}

function makePrivacyMetric(label, value) {
  const item = document.createElement("div");
  item.className = "promptless-privacy-metric";

  const name = document.createElement("span");
  name.textContent = label;

  const detail = document.createElement("strong");
  detail.textContent = value || "-";

  item.append(name, detail);
  return item;
}

async function executeAction(action, context, traceId, button) {
  activeExecution = true;
  const payload = { traceId, actionId: action.id, context };
  debug("execute payload", payload);
  try {
    const response = await fetch(`${API_BASE}/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const text = await response.text();
    let result = null;
    try {
      result = text ? JSON.parse(text) : null;
    } catch {
      result = { status: "error", result: text };
    }
    debug("execute response", { status: response.status, body: result });

    if (!response.ok) {
      showResult(action, result?.detail || result?.result || `Execution failed with HTTP ${response.status}.`, traceId, action.id, "error", context, result?.privacy || null);
      return;
    }

    showResult(action, result?.result || "No result returned.", traceId, action.id, result?.status || "done", context, result?.privacy || null);
  } catch (error) {
    debug("execute request failed", error);
    showResult(action, "Backend execution failed. Is the local server running?", traceId, action.id, "error", context);
  } finally {
    activeExecution = false;
    if (button) {
      button.disabled = false;
      button.textContent = action.label;
    }
  }
}

function showResult(action, result, traceId, actionId, status = "done", context = null, privacyMetadata = null) {
  let root = document.getElementById("promptless-ai-root");
  if (!root) {
    root = document.createElement("div");
    root.id = "promptless-ai-root";
    document.documentElement.appendChild(root);
  }

  root.innerHTML = "";
  resultVisible = true;
  visibleSuggestionKey = "";
  visibleSuggestionShownAt = 0;
  const panel = document.createElement("div");
  panel.className = status === "error" ? "promptless-result promptless-result-error" : "promptless-result";

  const header = document.createElement("div");
  header.className = "promptless-result-header";

  const heading = document.createElement("div");
  heading.className = "promptless-result-heading";

  const title = document.createElement("div");
  title.className = "promptless-result-title";
  title.textContent = status === "error" ? `${action.label} failed` : action.label;

  const badge = document.createElement("div");
  badge.className = status === "error" ? "promptless-result-badge promptless-result-badge-error" : "promptless-result-badge";
  badge.textContent = status === "error" ? "Error" : "Done";

  heading.append(title, badge);

  const meta = document.createElement("div");
  meta.className = "promptless-result-meta";
  meta.textContent = resultMetaText(context, privacyMetadata, status);

  const description = document.createElement("div");
  description.className = "promptless-result-description";
  description.textContent = action.description || "Result generated from the current page context.";

  header.append(heading, meta, description);

  const body = document.createElement("div");
  body.className = "promptless-result-body";
  renderResultBody(body, result);

  const controls = document.createElement("div");
  controls.className = "promptless-result-controls";

  const privacy = document.createElement("button");
  privacy.type = "button";
  privacy.textContent = "Privacy";
  privacy.addEventListener("click", () => {
    if (context) {
      void showPrivacyPreview(context, null, () => {
        showResult(action, result, traceId, actionId, status, context, privacyMetadata);
      });
    }
  });
  privacy.disabled = !context;

  const copy = document.createElement("button");
  copy.type = "button";
  copy.textContent = "Copy";
  copy.addEventListener("click", () => void navigator.clipboard?.writeText(result));

  const good = document.createElement("button");
  good.type = "button";
  good.textContent = "Good";
  good.addEventListener("click", () => void postFeedback("thumbs_up", traceId, actionId));

  const bad = document.createElement("button");
  bad.type = "button";
  bad.textContent = "Bad";
  bad.addEventListener("click", () => void postFeedback("thumbs_down", traceId, actionId));

  const close = document.createElement("button");
  close.type = "button";
  close.textContent = "Close";
  close.addEventListener("click", () => {
    void postFeedback("result_closed", traceId, actionId);
    hideSuggestions({ force: true });
  });

  controls.append(privacy, copy, good, bad, close);
  panel.append(header, body, controls);
  root.appendChild(panel);
}

function renderResultBody(body, result) {
  resultParts(result).forEach((part) => {
    const el = document.createElement(part.type === "bullet" ? "div" : "p");
    el.className = `promptless-result-${part.type}`;
    el.textContent = part.type === "bullet" ? `• ${part.text}` : part.text;
    body.appendChild(el);
  });
}

document.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target : null;
  if (!target || target.closest("#promptless-ai-root")) return;
  pushEvent({ type: "click", text: textForElement(target), tag: target.tagName, ts: Date.now() });
  void sendContext("click");
});

document.addEventListener(
  "mouseover",
  (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target || target.closest("#promptless-ai-root")) return;
    const text = textForElement(target);
    if (!text) return;
    pushEvent({ type: "hover", text, tag: target.tagName, ts: Date.now() });
  },
  { passive: true }
);

document.addEventListener("selectionchange", () => {
  const text = window.getSelection()?.toString().trim() || "";
  if (!text) return;
  pushEvent({ type: "selection", text: text.slice(0, 500), ts: Date.now() });
  void sendContext("selection");
});

document.addEventListener(
  "focusin",
  (event) => {
    const target = event.target instanceof HTMLElement ? event.target : null;
    if (!target || target.closest("#promptless-ai-root")) return;
    pushEvent({
      type: "focus",
      placeholder: (target.placeholder || "").slice(0, 120),
      tag: target.tagName,
      ts: Date.now()
    });
    void sendContext("focus");
  },
  { passive: true }
);

window.addEventListener(
  "scroll",
  () => {
    const delta = Math.abs(window.scrollY - lastScrollY);
    if (delta < SIGNIFICANT_SCROLL_PX) return;
    lastScrollY = window.scrollY;
    pushEvent({ type: "scroll", y: window.scrollY, ts: Date.now() });
    void sendContext("scroll");
  },
  { passive: true }
);

window.addEventListener("load", () => {
  void sendContext("load");
});

setInterval(() => {
  if (Date.now() - lastSentAt >= IDLE_SEND_MS) {
    void sendContext("idle");
  }
}, IDLE_SEND_MS);

void sendContext("document_idle");
