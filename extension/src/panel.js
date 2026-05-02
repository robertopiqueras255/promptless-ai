function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function refreshState() {
  chrome.runtime.sendMessage({ type: "PROMPTLESS_GET_STATE" }, (state) => {
    if (chrome.runtime.lastError) return;

    const context = state?.latestContext;
    if (context) {
      setText("panel-status", context.title || context.url || "Page context captured.");
    }

    setText("panel-reason", state?.latestReason || "-");
    setText("panel-action", state?.latestActionId || "-");
  });
}

refreshState();
setInterval(refreshState, 1000);
