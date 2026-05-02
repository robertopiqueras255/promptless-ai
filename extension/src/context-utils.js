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

  const api = { textForElement, textForFormControl, privacyRouteStatus };
  root.PromptlessContext = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : window);
