const assert = require("node:assert/strict");
const test = require("node:test");

const { textForElement } = require("./context-utils.js");

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
