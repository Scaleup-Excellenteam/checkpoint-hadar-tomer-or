"use strict";

/**
 * A FIFO async queue: the same role client.py's `queue.Queue` plays for
 * control responses (login/signup/join_room/heartbeat/...) - the socket's
 * onmessage handler pushes into it, and requests await a pop with a timeout.
 */
class AsyncQueue {
  constructor() {
    this._items = [];
    this._waiters = [];
  }

  push(item) {
    if (this._waiters.length) {
      this._waiters.shift()(item);
    } else {
      this._items.push(item);
    }
  }

  pop(timeoutMs = 5000) {
    if (this._items.length) {
      return Promise.resolve(this._items.shift());
    }
    return new Promise((resolve, reject) => {
      const resolver = (item) => {
        clearTimeout(timer);
        resolve(item);
      };
      const timer = setTimeout(() => {
        const idx = this._waiters.indexOf(resolver);
        if (idx >= 0) this._waiters.splice(idx, 1);
        reject(new Error("timeout"));
      }, timeoutMs);
      this._waiters.push(resolver);
    });
  }
}

/**
 * Talks the exact same JSON-over-WebSocket protocol as client.py, straight
 * to the existing server - no extra backend involved.
 */
class ChatClient {
  constructor(url) {
    this.url = url;
    this.username = null;
    this.token = null;
    this.currentTarget = null;
    this.messageHandler = null;
    this.onDisconnect = null;
    this._controlQueue = new AsyncQueue();
    this._ws = null;
  }

  connect() {
    return new Promise((resolve, reject) => {
      let settled = false;
      const ws = new WebSocket(this.url);

      ws.onopen = () => {
        settled = true;
        resolve();
      };
      ws.onerror = () => {
        if (!settled) {
          settled = true;
          reject(new Error("Could not connect to server"));
        }
      };
      ws.onclose = () => {
        if (this.onDisconnect) this.onDisconnect();
      };
      ws.onmessage = (event) => this._onMessage(event);

      this._ws = ws;
    });
  }

  _onMessage(event) {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch (e) {
      return;
    }

    if (data.action === "receive") {
      const payload = data.payload || {};
      const sender = payload.sender;
      const address = payload.address;
      const message = payload.message;
      const chatId = address === this.username ? sender : address;

      this._saveHistory(chatId, sender, "received", message);
      if (this.messageHandler) {
        this.messageHandler(chatId, sender, message);
      }
    } else {
      this._controlQueue.push(data);
    }
  }

  _send(obj) {
    this._ws.send(JSON.stringify(obj));
  }

  async signup(username, password) {
    this._send({ action: "signup", payload: { username, password } });
    try {
      const response = await this._controlQueue.pop(5000);
      return response.action === "signup_response";
    } catch (e) {
      return false;
    }
  }

  async login(username, password) {
    this._send({ action: "login", payload: { username, password } });
    try {
      const response = await this._controlQueue.pop(5000);
      if (!response.token) return false;
      this.username = username;
      this.token = response.token;
      return true;
    } catch (e) {
      return false;
    }
  }

  async logout() {
    if (!this.token) return false;
    this._send({ action: "logout", token: this.token });
    try {
      const response = await this._controlQueue.pop(5000);
      const ok = response.action === "logout_response";
      this.token = null;
      this.username = null;
      this.currentTarget = null;
      return ok;
    } catch (e) {
      return false;
    }
  }

  startChat(target) {
    this.currentTarget = target;
  }

  async joinRoom(room) {
    this._send({ action: "join_room", room_id: room, uid: this.username });
    try {
      const response = await this._controlQueue.pop(5000);
      const ok =
        response.action === "room_response" &&
        response.payload &&
        response.payload.status === "success";
      if (ok) this.currentTarget = room;
      return ok;
    } catch (e) {
      return false;
    }
  }

  async sendMessage(chatId, message) {
    const target = chatId || this.currentTarget;
    if (!target) return { ok: false, error: "No chat selected." };

    try {
      this._send({
        action: "send",
        token: this.token,
        payload: { sender: this.username, address: target, message },
      });
    } catch (e) {
      return { ok: false, error: "Not connected to the server." };
    }

    this._saveHistory(target, this.username, "sent", message);

    // The server always answers a "send" with an ack or an error - consume
    // it here so it doesn't sit in the control queue and get picked up by
    // the next unrelated request (e.g. a later heartbeat or join_room).
    try {
      const response = await this._controlQueue.pop(5000);
      if (response.error) {
        return { ok: false, error: response.error };
      }
      if (response.action === "dlp_blocked") {
        const payload = response.payload || {};
        return {
          ok: false,
          error: `Blocked by DLP: ${payload.reason} (score ${payload.score}, reputation ${payload.reputation})`,
        };
      }
    } catch (e) {
      return { ok: false, error: "No response from server (timed out)." };
    }

    return { ok: true };
  }

  async heartbeat() {
    this._send({ action: "heartbeat" });
    try {
      return await this._controlQueue.pop(5000);
    } catch (e) {
      return null;
    }
  }

  _historyKey() {
    return `chat_history_${this.username}`;
  }

  _saveHistory(chatId, sender, direction, message) {
    if (!this.username) return;
    const all = this._loadAllHistory();
    if (!all[chatId]) all[chatId] = [];
    all[chatId].push({
      sender,
      direction,
      message,
      timestamp: new Date().toISOString(),
    });
    localStorage.setItem(this._historyKey(), JSON.stringify(all));
  }

  _loadAllHistory() {
    try {
      return JSON.parse(localStorage.getItem(this._historyKey()) || "{}");
    } catch (e) {
      return {};
    }
  }

  getHistory(chatId) {
    return this._loadAllHistory()[chatId] || [];
  }

  getKnownChats() {
    return Object.keys(this._loadAllHistory());
  }

  /** Makes sure a chat shows up in getKnownChats() even before any message exists. */
  touchChat(chatId) {
    const all = this._loadAllHistory();
    if (!all[chatId]) {
      all[chatId] = [];
      localStorage.setItem(this._historyKey(), JSON.stringify(all));
    }
  }
}

/* ---------------------------------------------------------------------- */
/* UI wiring                                                              */
/* ---------------------------------------------------------------------- */

let client = null;

const loginScreen = document.getElementById("login-screen");
const chatScreen = document.getElementById("chat-screen");
const loginStatus = document.getElementById("login-status");

const serverUrlInput = document.getElementById("server-url");

/**
 * Whoever runs the server can hand out a ready-to-use link:
 * index.html?server=wss://192.168.1.23:9000 (or just the host/IP - "wss://"
 * and ":9000" are added automatically). That value is remembered in
 * localStorage, so after the first open it's pre-filled even without the
 * query param.
 */
(function initServerUrl() {
  const SERVER_URL_KEY = "chat_server_url";
  const fromQuery = new URLSearchParams(location.search).get("server");

  if (fromQuery) {
    const normalized = /^wss?:\/\//.test(fromQuery)
      ? fromQuery
      : `wss://${fromQuery}:9000`;
    serverUrlInput.value = normalized;
    localStorage.setItem(SERVER_URL_KEY, normalized);
    return;
  }

  const saved = localStorage.getItem(SERVER_URL_KEY);
  if (saved) {
    serverUrlInput.value = saved;
  }

  serverUrlInput.addEventListener("change", () => {
    localStorage.setItem(SERVER_URL_KEY, serverUrlInput.value.trim());
  });
})();

const usernameInput = document.getElementById("username");
const passwordInput = document.getElementById("password");
const signupBtn = document.getElementById("signup-btn");
const loginBtn = document.getElementById("login-btn");

const meLabel = document.getElementById("me-label");
const logoutBtn = document.getElementById("logout-btn");
const newChatTarget = document.getElementById("new-chat-target");
const openChatBtn = document.getElementById("open-chat-btn");
const joinRoomBtn = document.getElementById("join-room-btn");
const chatListEl = document.getElementById("chat-list");
const chatTitleEl = document.getElementById("chat-title");
const messagesEl = document.getElementById("messages");
const messageForm = document.getElementById("message-form");
const messageInput = document.getElementById("message-input");
const sendBtn = messageForm.querySelector("button[type=submit]");

function setStatus(text, ok) {
  loginStatus.textContent = text;
  loginStatus.classList.toggle("ok", !!ok);
}

async function ensureConnected() {
  if (client) return client;

  const url = serverUrlInput.value.trim();
  if (!url) {
    setStatus("Enter a server address.", false);
    return null;
  }

  const c = new ChatClient(url);
  try {
    await c.connect();
  } catch (e) {
    setStatus(
      "Could not reach the server. If it uses a self-signed certificate, " +
        "open " + url.replace("wss://", "https://").replace("ws://", "http://") +
        " once and accept the warning, then try again.",
      false
    );
    return null;
  }

  c.onDisconnect = () => {
    setStatus("Disconnected from server.", false);
    chatScreen.classList.add("hidden");
    loginScreen.classList.remove("hidden");
    client = null;
  };

  client = c;
  return client;
}

signupBtn.addEventListener("click", async () => {
  const username = usernameInput.value.trim();
  const password = passwordInput.value;
  if (!username || !password) {
    setStatus("Enter a username and password.", false);
    return;
  }

  setStatus("Signing up...", false);
  const c = await ensureConnected();
  if (!c) return;

  const ok = await c.signup(username, password);
  setStatus(
    ok ? "Signup successful. You can log in now." : "Signup failed (username may be taken).",
    ok
  );
});

loginBtn.addEventListener("click", async () => {
  const username = usernameInput.value.trim();
  const password = passwordInput.value;
  if (!username || !password) {
    setStatus("Enter a username and password.", false);
    return;
  }

  setStatus("Logging in...", false);
  const c = await ensureConnected();
  if (!c) return;

  const ok = await c.login(username, password);
  if (!ok) {
    setStatus("Login failed.", false);
    return;
  }

  enterChatScreen();
});

function enterChatScreen() {
  loginScreen.classList.add("hidden");
  chatScreen.classList.remove("hidden");
  meLabel.textContent = client.username;

  client.messageHandler = (chatId, sender, message) => {
    addKnownChat(chatId);
    if (chatId === client.currentTarget) {
      renderMessage(sender, message, sender === client.username);
    } else {
      markUnread(chatId);
    }
  };

  renderChatList();
}

logoutBtn.addEventListener("click", async () => {
  if (client) {
    await client.logout();
    client = null;
  }
  chatScreen.classList.add("hidden");
  loginScreen.classList.remove("hidden");
  usernameInput.value = "";
  passwordInput.value = "";
  setStatus("", false);
});

function addKnownChat(chatId) {
  client.touchChat(chatId);
  renderChatList();
}

function markUnread(chatId) {
  const item = chatListEl.querySelector(`[data-chat-id="${CSS.escape(chatId)}"]`);
  if (item) item.classList.add("has-unread");
}

function renderChatList() {
  const known = client.getKnownChats();
  chatListEl.innerHTML = "";

  if (known.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No chats yet";
    chatListEl.appendChild(empty);
    return;
  }

  for (const chatId of known) {
    const item = document.createElement("div");
    item.className = "chat-list-item";
    item.dataset.chatId = chatId;
    if (chatId === client.currentTarget) item.classList.add("active");

    const avatar = document.createElement("div");
    avatar.className = "chat-avatar";
    avatar.textContent = chatId.slice(0, 2);

    const label = document.createElement("span");
    label.textContent = chatId;

    item.appendChild(avatar);
    item.appendChild(label);
    item.addEventListener("click", () => openChat(chatId));

    chatListEl.appendChild(item);
  }
}

function openChat(chatId) {
  client.startChat(chatId);
  chatTitleEl.textContent = chatId;
  messageInput.disabled = false;
  sendBtn.disabled = false;

  renderChatList();
  messagesEl.innerHTML = "";

  const history = client.getHistory(chatId);
  if (history.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No messages yet - say hello!";
    messagesEl.appendChild(empty);
    return;
  }

  for (const entry of history) {
    renderMessage(entry.sender, entry.message, entry.direction === "sent");
  }
}

// Deterministic per-username colors, so the same person always gets the
// same bubble color across messages, chats, and page reloads - without
// needing to store anything.
const USER_COLORS = [
  { bg: "#ffe0e0", text: "#c23b3b" },
  { bg: "#e0f0ff", text: "#2f6fb3" },
  { bg: "#e0ffe4", text: "#2f8f52" },
  { bg: "#fff3d6", text: "#b8860b" },
  { bg: "#f1e0ff", text: "#8a4fc7" },
  { bg: "#e0fbff", text: "#1f8fa3" },
  { bg: "#ffe8f4", text: "#c23b83" },
  { bg: "#eaf5cf", text: "#6b8f1f" },
];

function colorForUser(name) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  }
  return USER_COLORS[hash % USER_COLORS.length];
}

function renderMessage(sender, message, mine) {
  const empty = messagesEl.querySelector(".empty-state");
  if (empty) empty.remove();

  const row = document.createElement("div");
  row.className = "msg-row " + (mine ? "mine" : "theirs");

  const bubbleWrap = document.createElement("div");
  bubbleWrap.className = "bubble-wrap";

  const color = colorForUser(sender);

  if (!mine) {
    const senderLabel = document.createElement("div");
    senderLabel.className = "msg-sender";
    senderLabel.textContent = sender;
    senderLabel.style.color = color.text;
    bubbleWrap.appendChild(senderLabel);
  }

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = message;
  if (!mine) {
    bubble.style.backgroundColor = color.bg;
  }
  bubbleWrap.appendChild(bubble);

  row.appendChild(bubbleWrap);
  messagesEl.appendChild(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

openChatBtn.addEventListener("click", () => {
  const target = newChatTarget.value.trim();
  if (!target) return;
  addKnownChat(target);
  openChat(target);
  newChatTarget.value = "";
});

joinRoomBtn.addEventListener("click", async () => {
  const room = newChatTarget.value.trim();
  if (!room) return;

  joinRoomBtn.disabled = true;
  const ok = await client.joinRoom(room);
  joinRoomBtn.disabled = false;

  if (!ok) {
    alert(`Could not join room "${room}".`);
    return;
  }

  addKnownChat(room);
  openChat(room);
  newChatTarget.value = "";
});

function showToast(text) {
  let toast = document.getElementById("toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "toast";
    toast.className = "toast";
    document.body.appendChild(toast);
  }
  toast.textContent = text;
  toast.classList.add("visible");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => toast.classList.remove("visible"), 4000);
}

messageForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = messageInput.value;
  const target = client.currentTarget;
  if (!text.trim() || !target) return;

  messageInput.value = "";
  renderMessage(client.username, text, true);

  const result = await client.sendMessage(target, text);
  if (!result.ok) {
    showToast(`Message to "${target}" failed: ${result.error}`);
  }
});
