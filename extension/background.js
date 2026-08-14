const HOST = "cinder_connect";

async function queryNativeStatus() {
  try {
    const reply = await browser.runtime.sendNativeMessage(
      HOST,
      { command: "extension_status" }
    );
    await browser.storage.local.set({ lastStatus: reply });
    await updateBadge(reply);
    return reply;
  } catch (error) {
    const reply = {
      ok: false,
      state: "native_host_error",
      error: String(error?.message || error)
    };
    await browser.storage.local.set({ lastStatus: reply });
    await updateBadge(reply);
    return reply;
  }
}

async function updateBadge(status) {
  const attached = status && status.ok && status.state === "attached";
  await browser.action.setBadgeText({ text: attached ? "ON" : "" });
  await browser.action.setTitle({
    title: attached
      ? `Cinder Connect - PID ${status.pid}`
      : "Cinder Connect - not attached"
  });
}

browser.runtime.onMessage.addListener((message) => {
  if (message?.type === "get-status") {
    return queryNativeStatus();
  }
  return undefined;
});

browser.runtime.onInstalled.addListener(() => {
  queryNativeStatus();
});

browser.runtime.onStartup.addListener(() => {
  queryNativeStatus();
});
