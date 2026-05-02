const assert = require("node:assert/strict");
const test = require("node:test");

const {
  compactPreviewText,
  formatFindingKinds,
  privacyRouteStatus,
  resultMetaText,
  resultParts,
  routeDescription,
  suggestionBasis,
  summarizePreviewContext,
  textForElement
} = require("./context-utils.js");

function element({ tagName, textContent = "", value = "", attrs = {} }) {
  return {
    tagName,
    textContent,
    value,
    getAttribute(name) {
      return attrs[name] || null;
    }
  };
}

test("text inputs use field metadata instead of typed values", () => {
  const el = element({
    tagName: "INPUT",
    value: "sk-typed-secret",
    attrs: {
      type: "text",
      name: "api_key",
      placeholder: "API key"
    }
  });

  const label = textForElement(el);

  assert.equal(label, "api_key API key text field input");
  assert.equal(label.includes("sk-typed-secret"), false);
});

test("textarea values are not used as captured element text", () => {
  const el = element({
    tagName: "TEXTAREA",
    value: "Private customer note",
    attrs: {
      "aria-label": "Support note",
      name: "note"
    }
  });

  const label = textForElement(el);

  assert.equal(label, "Support note note textarea");
  assert.equal(label.includes("Private customer note"), false);
});

test("submit inputs keep visible button text", () => {
  const el = element({
    tagName: "INPUT",
    value: "Continue",
    attrs: { type: "submit" }
  });

  assert.equal(textForElement(el), "Continue");
});

test("non-form elements use visible text", () => {
  const el = element({
    tagName: "A",
    textContent: "Pricing details",
    attrs: { href: "/pricing" }
  });

  assert.equal(textForElement(el), "Pricing details");
});

test("privacy route status names blocked local routes explicitly", () => {
  assert.deepEqual(privacyRouteStatus({ cloudAllowed: false, route: "local" }), {
    className: "promptless-route promptless-route-local",
    label: "Cloud blocked"
  });
});

test("privacy route status names redacted cloud routes explicitly", () => {
  assert.deepEqual(privacyRouteStatus({ cloudAllowed: true, route: "cloud_redacted" }), {
    className: "promptless-route promptless-route-cloud",
    label: "Redacted cloud allowed"
  });
});

test("suggestion basis prefers selected text", () => {
  assert.equal(
    suggestionBasis({ selectedText: "OAuth token", recentEvents: [{ type: "click", text: "Continue" }] }),
    "Based on selected text"
  );
});

test("suggestion basis uses recent click without exposing clicked text", () => {
  assert.equal(
    suggestionBasis({ recentEvents: [{ type: "scroll" }, { type: "click", text: "Private customer" }] }),
    "Based on your recent click"
  );
});

test("suggestion basis falls back to page structure", () => {
  assert.equal(suggestionBasis({ viewportSummary: "Pricing | Plans" }), "Based on visible page structure");
});

test("result parts parse headings and bullets", () => {
  assert.deepEqual(resultParts("Summary\n- First point\n- Second point"), [
    { type: "heading", text: "Summary" },
    { type: "bullet", text: "First point" },
    { type: "bullet", text: "Second point" }
  ]);
});

test("result parts parse numbered lines as bullets", () => {
  assert.deepEqual(resultParts("Next steps\n1. Confirm plan\n2. Continue checkout"), [
    { type: "heading", text: "Next steps" },
    { type: "bullet", text: "Confirm plan" },
    { type: "bullet", text: "Continue checkout" }
  ]);
});

test("result parts preserve plain paragraphs", () => {
  assert.deepEqual(resultParts("This page explains OAuth token expiry."), [
    { type: "paragraph", text: "This page explains OAuth token expiry." }
  ]);
});

test("result metadata includes route policy from execute response", () => {
  assert.equal(
    resultMetaText(
      { title: "Customer dashboard", url: "https://crm.example.com/customer" },
      { cloudAllowed: false, route: "local" }
    ),
    "Using redacted local page context from Customer dashboard (crm.example.com). Route policy: Cloud blocked."
  );
});

test("result metadata omits route policy for execution errors", () => {
  assert.equal(
    resultMetaText(
      { title: "Customer dashboard", url: "https://crm.example.com/customer" },
      { cloudAllowed: false, route: "local" },
      "error"
    ),
    "Using redacted local page context from Customer dashboard (crm.example.com)."
  );
});

test("route description includes route reason when present", () => {
  assert.equal(
    routeDescription({ route: "local", routeReason: "secret context requires local execution" }),
    "local: secret context requires local execution"
  );
});

test("finding kinds format empty and populated lists", () => {
  assert.equal(formatFindingKinds([]), "none");
  assert.equal(formatFindingKinds(["email", "password"]), "email, password");
});

test("preview text is compacted and bounded", () => {
  const compact = compactPreviewText(`First\n\n${"x".repeat(620)}`, 40);

  assert.equal(compact.length <= 40, true);
  assert.equal(compact.includes("\n"), false);
  assert.equal(compact.endsWith("[truncated]"), true);
});

test("preview context summary includes recent event signals", () => {
  assert.equal(
    summarizePreviewContext({
      title: "Checkout",
      url: "https://shop.example.com/checkout",
      focusedElement: "email field input",
      visibleText: "Complete your order",
      recentEvents: [
        { type: "scroll" },
        { type: "focus", placeholder: "Email address", tag: "INPUT" },
        { type: "click", text: "Continue", tag: "BUTTON" }
      ]
    }),
    [
      "Title: Checkout",
      "URL: https://shop.example.com/checkout",
      "Focused element: email field input",
      "Visible text: Complete your order",
      "Recent events: scroll; focus: Email address; click: Continue"
    ].join("\n\n")
  );
});

test("preview context summary handles empty context", () => {
  assert.equal(summarizePreviewContext({}), "No page context was captured.");
});
