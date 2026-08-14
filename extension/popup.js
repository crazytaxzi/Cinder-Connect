console.log("Cinder Connect popup loaded");
const stateEl = document.getElementById("state");
const processEl = document.getElementById("pid");
const exeEl = document.getElementById("exe");
const bindingEl = document.getElementById("binding");
const terminalEl = document.getElementById("terminal");
const chatEl = document.getElementById("chat");
const detailEl = document.getElementById("detail");
const refreshEl = document.getElementById("refresh");
function render(status) {
  const attached = status && status.ok && status.state === "attached";
  stateEl.textContent = attached ? "Attached" : (status?.state || "Not attached");
  stateEl.classList.toggle("attached", attached);
}
function renderDetails(status) {
  processEl.textContent = status?.pid ?? "-";
  exeEl.textContent = status?.exe_path ?? "-";
  bindingEl.textContent = status?.binding_id ?? "-";
  terminalEl.textContent = status?.terminal_connected ? `PID ${status.terminal_pid}` : "Not connected";
  const chats = status?.chat_conversations || [];
  chatEl.textContent = chats.length ? chats.join(", ") : "Not connected";
  detailEl.textContent = status?.error || status?.detail || "";
}
async function refresh() {
  refreshEl.disabled = true;
  stateEl.textContent = "Checking...";
  try {
    const status = await browser.runtime.sendMessage({ type: "get-status" });
    render(status);
    renderDetails(status);
  } catch (error) {
    const status = {
      state: "extension_error",
      error: String(error?.message || error)
    };
    render(status);
    renderDetails(status);
  } finally {
    refreshEl.disabled = false;
  }
}
refreshEl.addEventListener("click", refresh);
refresh();
