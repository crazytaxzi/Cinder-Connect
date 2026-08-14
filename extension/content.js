if (globalThis.__cinderConnectLoaded) {
  console.debug("Cinder Connect content bridge already loaded");
} else {
  globalThis.__cinderConnectLoaded = true;

const port = browser.runtime.connect({ name: "cinder-chat" });
const KEEP_TURNS = 8;
const COMMAND_RE = /\[\[CINDER_CMD:v1\]\]\s*([\s\S]*?)\s*\[\[\/CINDER_CMD\]\]/g;
let conversationId = null;
let awaitingReply = false;
let baselineAssistant = "";
let settleTimer = null;
let bridgeHeaderInjected = false;

const BRIDGE_HEADER = `[CINDER_BRIDGE:v1 ACTIVE]\n` +
  `You may append machine commands using [[CINDER_CMD:v1]] JSON [[/CINDER_CMD]]. ` +
  `Supported actions: shell.run, process.start, process.stop, file.read, file.write, file.list. ` +
  `Each command needs a unique id. Never invent execution results; wait for CINDER_RESULT.\n` +
  `[/CINDER_BRIDGE]\n\n`;

function currentConversationId() {
  const match = location.pathname.match(/\/c\/([0-9a-f-]{20,})/i);
  return match ? match[1] : null;
}

function reportConversation() {
  const next = currentConversationId();
  if (next === conversationId) return;
  conversationId = next;
  if (conversationId) port.postMessage({ type: "chat.ready", conversation_id: conversationId });
}
function messageNodes(role) {
  return [...document.querySelectorAll(`[data-message-author-role="${role}"]`)];
}

function turnContainer(node) {
  return node.closest("article") || node.closest('[data-testid^="conversation-turn"]') || node.parentElement;
}

function compactTurns() {
  const nodes = [...document.querySelectorAll("[data-message-author-role]")];
  const turns = [];
  for (const node of nodes) {
    const container = turnContainer(node);
    if (container && !turns.includes(container)) turns.push(container);
  }
  const cutoff = Math.max(0, turns.length - KEEP_TURNS);
  turns.forEach((turn, index) => {
    if (index < cutoff) {
      turn.dataset.cinderCompacted = "1";
      turn.style.display = "none";
    } else if (turn.dataset.cinderCompacted === "1") {
      turn.style.display = "";
      delete turn.dataset.cinderCompacted;
    }
  });
}

function latestAssistantText() {
  const nodes = messageNodes("assistant");
  return nodes.length ? (nodes[nodes.length - 1].innerText || "").trim() : "";
}
function isGenerating() {
  return Boolean(
    document.querySelector('[data-testid="stop-button"]') ||
    document.querySelector('button[aria-label*="Stop" i]')
  );
}

function parseCommands(rawText) {
  const commands = [];
  let match;
  COMMAND_RE.lastIndex = 0;
  while ((match = COMMAND_RE.exec(rawText)) !== null) {
    try {
      const parsed = JSON.parse(match[1]);
      const items = Array.isArray(parsed) ? parsed : (Array.isArray(parsed.commands) ? parsed.commands : [parsed]);
      for (const item of items) {
        if (item && typeof item === "object" && item.id && item.action) commands.push(item);
      }
    } catch (error) {
      port.postMessage({ type: "chat.error", conversation_id: conversationId,
        detail: `Invalid CINDER_CMD JSON: ${error.message}` });
    }
  }
  const visible = rawText.replace(COMMAND_RE, "").trim();
  return { visible, commands };
}

function findComposer() {
  return document.querySelector("#prompt-textarea") ||
    document.querySelector('textarea[placeholder*="Message" i]') ||
    document.querySelector('[contenteditable="true"][role="textbox"]');
}
function setComposerText(composer, text) {
  composer.focus();
  if (composer instanceof HTMLTextAreaElement || composer instanceof HTMLInputElement) {
    const proto = composer instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    if (setter) setter.call(composer, text); else composer.value = text;
    composer.dispatchEvent(new Event("input", { bubbles: true }));
    return;
  }
  composer.innerHTML = "";
  const p = document.createElement("p");
  p.textContent = text;
  composer.appendChild(p);
  composer.dispatchEvent(new InputEvent("input", {
    bubbles: true, inputType: "insertText", data: text
  }));
}

function findSendButton(composer) {
  return document.querySelector('[data-testid="send-button"]') ||
    document.querySelector('button[aria-label*="Send" i]') ||
    composer.closest("form")?.querySelector('button[type="submit"]');
}

async function submitText(text) {
  const composer = findComposer();
  if (!composer) throw new Error("ChatGPT composer was not found");
  baselineAssistant = latestAssistantText();
  awaitingReply = true;
  setComposerText(composer, text);
  await new Promise((resolve) => requestAnimationFrame(resolve));
  const send = findSendButton(composer);
  if (!send || send.disabled) {
    awaitingReply = false;
    throw new Error("ChatGPT send button is unavailable");
  }
  send.click();
  port.postMessage({ type: "chat.sent", conversation_id: conversationId });
}

function scheduleAssistantCheck() {
  if (!awaitingReply) return;
  clearTimeout(settleTimer);
  settleTimer = setTimeout(() => {
    if (!awaitingReply || isGenerating()) return;
    const raw = latestAssistantText();
    if (!raw || raw === baselineAssistant) return;
    const { visible, commands } = parseCommands(raw);
    awaitingReply = false;
    port.postMessage({
      type: "assistant.reply",
      conversation_id: conversationId,
      batch_id: crypto.randomUUID(),
      text: visible,
      commands
    });
  }, 500);
}

function resultEnvelope(message) {
  return `[CINDER_RESULT:v1]\n${JSON.stringify({
    batch_id: message.batch_id,
    results: message.results
  })}\n[/CINDER_RESULT]`;
}
port.onMessage.addListener(async (message) => {
  try {
    if (message?.type === "terminal.chat") {
      let text = String(message.text || "");
      if (!bridgeHeaderInjected) {
        text = BRIDGE_HEADER + text;
        bridgeHeaderInjected = true;
      }
      await submitText(text);
      return;
    }
    if (message?.type === "command.batch_result") {
      await submitText(resultEnvelope(message));
    }
  } catch (error) {
    port.postMessage({
      type: "chat.error",
      conversation_id: conversationId,
      detail: String(error?.message || error)
    });
  }
});

const observer = new MutationObserver(() => {
  reportConversation();
  compactTurns();
  scheduleAssistantCheck();
});
observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
window.addEventListener("popstate", reportConversation);
reportConversation();
compactTurns();

}
