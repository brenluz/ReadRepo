// Runs on github.com pages. Detects the repo being viewed, injects a chat
// panel, and streams answers from the local ReadRepo server (via the
// background worker). No external libraries - plain DOM, CSP-friendly.

// GitHub top-level paths that are NOT user/repo owners.
const RESERVED_OWNERS = new Set([
  "settings", "marketplace", "notifications", "explore", "topics", "trending",
  "collections", "events", "sponsors", "about", "pricing", "features", "apps",
  "orgs", "users", "login", "logout", "join", "new", "search", "codespaces",
  "pulls", "issues", "dashboard", "account",
]);

function detectRepo() {
  const parts = location.pathname.split("/").filter(Boolean);
  if (parts.length < 2) return null;
  const [owner, repo] = parts;
  if (RESERVED_OWNERS.has(owner.toLowerCase())) return null;
  return { owner, repo };
}

let state = {
  repo: null,
  conversationId: null,
  port: null,
  open: false,
};

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function buildPanel() {
  const launcher = el("button", "rr-launcher", "Ask ReadRepo");
  launcher.addEventListener("click", togglePanel);

  const panel = el("div", "rr-panel rr-hidden");
  const header = el("div", "rr-header");
  header.append(
    el("span", "rr-title", `ReadRepo · ${state.repo.owner}/${state.repo.repo}`),
  );
  const close = el("button", "rr-close", "×");
  close.addEventListener("click", togglePanel);
  header.append(close);

  const messages = el("div", "rr-messages");
  const form = el("form", "rr-form");
  const input = el("input", "rr-input");
  input.type = "text";
  input.placeholder = "Ask about this repo…";
  const send = el("button", "rr-send", "Send");
  send.type = "submit";
  form.append(input, send);

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (!q) return;
    input.value = "";
    ask(q, messages, input, send);
  });

  panel.append(header, messages, form);
  document.body.append(launcher, panel);
  state.elements = { launcher, panel, messages, input };
}

function togglePanel() {
  state.open = !state.open;
  state.elements.panel.classList.toggle("rr-hidden", !state.open);
  if (state.open) state.elements.input.focus();
}

function addMessage(messages, role, text) {
  const bubble = el("div", `rr-msg rr-${role}`);
  bubble.textContent = text;
  messages.append(bubble);
  messages.scrollTop = messages.scrollHeight;
  return bubble;
}

function ask(question, messages, input, send) {
  addMessage(messages, "user", question);
  const answer = addMessage(messages, "assistant", "");
  const status = el("div", "rr-status", "…");
  messages.append(status);
  messages.scrollTop = messages.scrollHeight;

  input.disabled = true;
  send.disabled = true;

  // Fresh port per question keeps the streaming simple.
  const port = chrome.runtime.connect({ name: "chat" });
  let answerText = "";

  const finish = () => {
    input.disabled = false;
    send.disabled = false;
    input.focus();
    try { port.disconnect(); } catch {}
  };

  port.onMessage.addListener((ev) => {
    if (ev.type === "conversation") {
      state.conversationId = ev.conversation_id;
    } else if (ev.type === "status") {
      status.textContent = ev.text;
    } else if (ev.type === "token") {
      status.remove();
      answerText += ev.text;
      answer.textContent = answerText;
      messages.scrollTop = messages.scrollHeight;
    } else if (ev.type === "sources") {
      status.remove();
      if (ev.sources && ev.sources.length) {
        const src = el("div", "rr-sources");
        src.append(el("div", "rr-sources-label", "Sources"));
        ev.sources.forEach((s) => src.append(el("div", "rr-source", s)));
        messages.append(src);
      }
    } else if (ev.type === "error") {
      status.remove();
      answer.classList.add("rr-error");
      answer.textContent = ev.detail || "Something went wrong.";
    } else if (ev.type === "done") {
      finish();
    }
  });

  port.onDisconnect.addListener(finish);

  port.postMessage({
    owner: state.repo.owner,
    repo: state.repo.repo,
    question,
    conversation_id: state.conversationId,
  });
}

function init() {
  const repo = detectRepo();
  if (!repo) return;
  if (state.elements) return; // already injected
  state.repo = repo;
  state.conversationId = null;
  buildPanel();
}

init();
// GitHub navigates as an SPA; re-check on history changes.
window.addEventListener("popstate", init);
