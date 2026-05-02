type PanelState = {
  latestContext?: {
    title?: string;
    url?: string;
  } | null;
  latestReason?: string;
  latestActionId?: string;
};

function setText(id: string, value: string): void {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function refreshState(): void {
  chrome.runtime.sendMessage({ type: "PROMPTLESS_GET_STATE" }, (state: PanelState) => {
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
