const assert = require("node:assert/strict");
const test = require("node:test");

const { privacyRouteStatus, suggestionBasis, textForElement } = require("./context-utils.js");

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
