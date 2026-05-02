let latestContext = null;
let latestReason = "";
let latestActionId = "";
let latestTraceId = "";

chrome.runtime.onMessage.addListener((message) => {
  if (message.type === "PROMPTLESS_CONTEXT") {
    latestContext = message.context || null;
    latestReason = message.reason || "";
  }

  if (message.type === "PROMPTLESS_ACTION_CLICKED") {
    latestContext = message.context || null;
    latestActionId = message.actionId || "";
    latestTraceId = message.traceId || latestTraceId;
  }

  if (message.type === "PROMPTLESS_DISMISSED") {
    latestContext = message.context || null;
    latestTraceId = message.traceId || latestTraceId;
  }
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type !== "PROMPTLESS_GET_STATE") return;

  sendResponse({
    latestContext,
    latestReason,
    latestActionId,
    latestTraceId
  });
});

