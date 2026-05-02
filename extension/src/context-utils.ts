(function initPromptlessContext(root) {
  function textForElement(el) {
    const tag = (el.tagName || "").toUpperCase();
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
      return textForFormControl(el, tag);
    }
    return (el.textContent || el.getAttribute?.("aria-label") || "").trim().slice(0, 120);
  }

  function textForFormControl(el, tag) {
    const type = (el.getAttribute?.("type") || "").toLowerCase();
    if (tag === "INPUT" && ["button", "submit", "reset"].includes(type)) {
      return (el.value || el.getAttribute?.("aria-label") || type).trim().slice(0, 120);
    }

    const label = [
      el.getAttribute?.("aria-label"),
      el.getAttribute?.("name"),
      el.getAttribute?.("placeholder"),
      type ? `${type} field` : "",
      tag.toLowerCase()
    ]
      .filter(Boolean)
      .join(" ");
    return label.trim().slice(0, 120);
  }

  function appendRecentEvent(events, event, limit = 50) {
    const current = Array.isArray(events) ? events : [];
    const next = { ...event };
    const last = current[current.length - 1];
    if (last && eventSignature(last) === eventSignature(next)) {
      return [...current.slice(0, -1), { ...last, ...next }].slice(-limit);
    }
    return [...current, next].slice(-limit);
  }

  function eventSignature(event) {
    return [
      event?.type || "",
      event?.tag || "",
      event?.text || "",
      event?.placeholder || ""
    ].join("\u0000");
  }

  function contextSignature(context) {
    const recent = Array.isArray(context?.recentEvents) ? context.recentEvents : [];
    const lastMeaningfulEvent = [...recent].reverse().find((event) => event?.type && event.type !== "scroll");
    return [
      context?.url || "",
      context?.title || "",
      String(context?.selectedText || "").slice(0, 240),
      String(context?.focusedElement || "").slice(0, 240),
      String(context?.viewportSummary || "").slice(0, 500),
      lastMeaningfulEvent ? eventSignature(lastMeaningfulEvent) : "",
      String(context?.visibleText || "").slice(0, 1200)
    ].join("|");
  }

  function privacyRouteStatus(preview) {
    if (preview?.error) {
      return { className: "promptless-route promptless-route-local", label: "Unavailable" };
    }
    if (preview?.cloudAllowed) {
      return { className: "promptless-route promptless-route-cloud", label: "Redacted cloud allowed" };
    }
    return { className: "promptless-route promptless-route-local", label: "Cloud blocked" };
  }

  function suggestionBasis(context) {
    if (context?.selectedText?.trim()) {
      return "Based on selected text";
    }
    if (context?.focusedElement?.trim()) {
      return "Based on the focused field";
    }
    const recent = Array.isArray(context?.recentEvents) ? context.recentEvents : [];
    const lastEvent = [...recent].reverse().find((event) => event?.type && event.type !== "scroll");
    if (lastEvent) {
      if (lastEvent.type === "click") return "Based on your recent click";
      if (lastEvent.type === "hover") return "Based on what you hovered";
      if (lastEvent.type === "focus") return "Based on the focused field";
      if (lastEvent.type === "selection") return "Based on selected text";
    }
    if (context?.viewportSummary?.trim()) {
      return "Based on visible page structure";
    }
    return "Based on visible page text";
  }

  function resultParts(text) {
    const lines = String(text || "")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    const parts = [];
    for (const line of lines) {
      const bullet = line.match(/^[-*]\s+(.+)$/);
      if (bullet) {
        parts.push({ type: "bullet", text: bullet[1].trim() });
        continue;
      }
      const numbered = line.match(/^\d+[.)]\s+(.+)$/);
      if (numbered) {
        parts.push({ type: "bullet", text: numbered[1].trim() });
        continue;
      }
      if (parts.length === 0 && line.length <= 80 && !/[.!?]$/.test(line)) {
        parts.push({ type: "heading", text: line });
        continue;
      }
      parts.push({ type: "paragraph", text: line });
    }
    return parts.length ? parts : [{ type: "paragraph", text: "No result returned." }];
  }

  function resultMetaText(context, privacyMetadata = null, status = "done") {
    const page = context?.title || context?.url || "current page";
    const origin = urlOrigin(context?.url);
    const source = origin ? `${page} (${origin})` : page;
    const routeStatus = privacyMetadata && Object.prototype.hasOwnProperty.call(privacyMetadata, "cloudAllowed")
      ? privacyRouteStatus(privacyMetadata)
      : null;
    const routeText = status !== "error" && routeStatus?.label ? ` Route policy: ${routeStatus.label}.` : "";
    return `Using redacted local page context from ${source}.${routeText}`;
  }

  function routeDescription(preview) {
    if (!preview) return "unknown";
    const route = preview.route || "unknown";
    const reason = preview.routeReason || "";
    if (!reason) return route;
    return `${route}: ${reason}`;
  }

  function formatFindingKinds(kinds) {
    if (!Array.isArray(kinds) || kinds.length === 0) return "none";
    return kinds.join(", ");
  }

  function summarizePreviewContext(context) {
    const parts = [];
    const fields = [
      ["Title", context?.title],
      ["URL", context?.url],
      ["Selection", context?.selectedText],
      ["Focused element", context?.focusedElement],
      ["Viewport", context?.viewportSummary],
      ["Visible text", context?.visibleText]
    ];

    fields.forEach(([label, value]) => {
      const text = String(value || "").trim();
      if (!text) return;
      parts.push(`${label}: ${compactPreviewText(text)}`);
    });

    if (Array.isArray(context?.recentEvents) && context.recentEvents.length) {
      const events = context.recentEvents
        .slice(-5)
        .map((event) => [event.type, event.text || event.placeholder || event.tag].filter(Boolean).join(": "))
        .filter(Boolean)
        .join("; ");
      if (events) parts.push(`Recent events: ${compactPreviewText(events)}`);
    }

    return parts.join("\n\n") || "No page context was captured.";
  }

  function compactPreviewText(text, limit = 520) {
    const compact = text.replace(/\s+/g, " ").trim();
    if (compact.length <= limit) return compact;
    return `${compact.slice(0, limit - 12).trim()} [truncated]`;
  }

  function urlOrigin(url) {
    if (!url) return "";
    try {
      return new URL(url).hostname;
    } catch {
      return "";
    }
  }

  const api = {
    appendRecentEvent,
    compactPreviewText,
    contextSignature,
    eventSignature,
    formatFindingKinds,
    privacyRouteStatus,
    resultMetaText,
    resultParts,
    routeDescription,
    suggestionBasis,
    summarizePreviewContext,
    textForElement,
    textForFormControl
  };
  root.PromptlessContext = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : window);
