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

  function urlOrigin(url) {
    if (!url) return "";
    try {
      return new URL(url).hostname;
    } catch {
      return "";
    }
  }

  const api = {
    privacyRouteStatus,
    resultMetaText,
    resultParts,
    suggestionBasis,
    textForElement,
    textForFormControl
  };
  root.PromptlessContext = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : window);
