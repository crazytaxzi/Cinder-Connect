const HOST = "cinder_connect";
let nativePort = null;
let rpcCounter = 0;
const rpcPending = new Map();
const chatPorts = new Map();

function postNative(message) {
  if (!nativePort) {
    throw new Error("Cinder native host is not connected");
  }
  nativePort.postMessage(message);
}

function rpcNative(method) {
  const requestId = `rpc-${Date.now()}-${++rpcCounter}`;
  return new Promise((resolve, reject) => {
    rpcPending.set(requestId, { resolve, reject });
    try {
      postNative({ type: "rpc.request", request_id: requestId, method });
    } catch (error) {
      rpcPending.delete(requestId);
      reject(error);
    }
  });
}
function chooseChat(conversationId) {
  if (conversationId && chatPorts.has(conversationId)) {
    return { id: conversationId, port: chatPorts.get(conversationId) };
  }
  if (!conversationId && chatPorts.size === 1) {
    const [id, port] = chatPorts.entries().next().value;
    return { id, port };
  }
  return null;
}

function routeToChat(message) {
  const target = chooseChat(message.conversation_id);
  if (!target) {
    const available = [...chatPorts.keys()];
    postNative({
      type: "chat.error",
      conversation_id: message.conversation_id || null,
      detail: available.length
        ? `No unique target chat. Available: ${available.join(", ")}`
        : "No Cinder-enabled ChatGPT conversation is connected."
    });
    return;
  }
  target.port.postMessage({ ...message, conversation_id: target.id });
}
function handleNativeMessage(message) {
  if (message?.type === "rpc.result") {
    const pending = rpcPending.get(message.request_id);
    if (!pending) return;
    rpcPending.delete(message.request_id);
    if (message.error) pending.reject(new Error(message.error));
    else pending.resolve(message.result);
    return;
  }
  if (message?.type === "terminal.chat" || message?.type === "command.batch_result") {
    routeToChat(message);
    return;
  }
  if (message?.type === "extension.hello.ack") {
    browser.storage.local.set({ lastStatus: message.binding });
  }
}

function connectNative() {
  if (nativePort) return;
  try {
    nativePort = browser.runtime.connectNative(HOST);
    nativePort.onMessage.addListener(handleNativeMessage);
    nativePort.onDisconnect.addListener(() => {
      nativePort = null;
      for (const pending of rpcPending.values()) {
        pending.reject(new Error("Native host disconnected"));
      }
      rpcPending.clear();
      setTimeout(connectNative, 1000);
    });
    nativePort.postMessage({ type: "extension.hello", version: 2 });
  } catch (error) {
    nativePort = null;
    setTimeout(connectNative, 1000);
  }
}

browser.runtime.onConnect.addListener((port) => {
  if (port.name !== "cinder-chat") return;
  let currentId = null;
  port.onMessage.addListener((message) => {
    if (message?.type === "chat.ready") {
      if (currentId && chatPorts.get(currentId) === port) chatPorts.delete(currentId);
      currentId = message.conversation_id;
      if (currentId) chatPorts.set(currentId, port);
      if (nativePort) postNative(message);
      return;
    }
    if (["assistant.reply", "chat.sent", "chat.error"].includes(message?.type)) {
      if (nativePort) postNative(message);
    }
  });
  port.onDisconnect.addListener(() => {
    if (currentId && chatPorts.get(currentId) === port) chatPorts.delete(currentId);
  });
});

browser.runtime.onMessage.addListener((message) => {
  if (message?.type === "get-status") {
    connectNative();
    return rpcNative("extension_status").then(async (status) => {
      status.chat_conversations = [...chatPorts.keys()];
      await browser.storage.local.set({ lastStatus: status });
      await updateBadge(status);
      return status;
    });
  }
  return undefined;
});

async function updateBadge(status) {
  const attached = status && status.ok && status.state === "attached";
  await browser.action.setBadgeText({ text: attached ? "ON" : "" });
  await browser.action.setTitle({
    title: attached ? `Cinder Connect - PID ${status.pid}` : "Cinder Connect - not attached"
  });
}

connectNative();
