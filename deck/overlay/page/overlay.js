// Rook over the game: drives phone/presence.js (copied as presence.js) and the answer text from the backend's
// /overlay/events stream, {"state": "resting"|"listening"|"thinking"|"speaking"|"waiting", "text": str,
// "draft": str|null}, one JSON object per SSE message. Each message is the whole picture, never a delta.
// It shows while Rook works, keeps the answer up long enough to read once Rook rests, then fades out.
// window.rookOverlay.visible() tells a host (overlay/rook_overlay.py's Qt window) whether anything shows, so it can
// unmap its window while nothing does.
"use strict";

// Qt 5's WebEngine is Chromium 87, older than Array.prototype.at, which presence.js uses.
for (const T of [Array, Float32Array, Int16Array, Uint8Array]) {
  if (!T.prototype.at) {
    Object.defineProperty(T.prototype, "at", {
      value(i) { i = Math.trunc(i) || 0; return this[i < 0 ? this.length + i : i]; },
      configurable: true, writable: true,
    });
  }
}

(() => {
  const $ = (id) => document.getElementById(id);
  const params = new URLSearchParams(location.search);
  const EVENTS = params.get("events") || "/overlay/events";
  const STATES = new Set(["resting", "listening", "transcribing", "thinking", "speaking", "waiting", "error"]);
  const LABELS = {
    listening: "Listening", transcribing: "Transcribing", thinking: "Thinking", speaking: "", waiting: "Waiting",
    error: "Trouble",
  };
  const OFFLINE_FADE_MS = 15000;  // A stream down this long counts as Rook at rest.
  // Where the page sits: ?anchor= (or an "anchor" field on the stream), as overlay/anchors.py. ?frame=window when
  // the page fills a window already placed for that anchor (the overlay process), else it is the whole screen.
  const ANCHORS = new Set(["middle-right", "middle-left", "top-right", "top-left", "bottom-center"]);
  const FRAME = params.get("frame") === "window" ? "window" : "screen";
  function setAnchor(a) {
    if (ANCHORS.has(a)) document.body.dataset.anchor = a;
  }

  const now = { state: "resting", text: "", draft: null };
  let presence = null;
  let restedAt = Date.now() - 60000;
  let lastText = "";
  let hideTimer = null;
  let downSince = null;
  let shown = false;

  // How long an answer stays up once Rook rests: long enough to read it once, at about 15 characters a second.
  function readingMs(text) {
    return Math.max(6000, Math.min(20000, 3000 + text.length * 65));
  }

  function setShown(on) {
    if (on === shown) return;
    shown = on;
    document.body.dataset.shown = String(on);
    if (presence) (on ? presence.wake : presence.halt)();
  }

  function paragraphs(text, live) {
    const box = $("text");
    const parts = String(text).replace(/\r\n?/g, "\n").split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
    box.replaceChildren(...parts.map((p) => {
      const el = document.createElement("p");
      el.textContent = p.replace(/\s*\n\s*/g, " ").replace(/\*\*([^*]+)\*\*/g, "$1").replace(/`([^`]+)`/g, "$1");
      return el;
    }));
    if (live && box.lastElementChild) {  // Words still arriving end in a glimmering grain.
      const grain = document.createElement("span");
      grain.className = "grain";
      box.lastElementChild.append(grain);
    }
    box.classList.toggle("long", box.scrollHeight > box.clientHeight + 2);
  }

  function render() {
    const state = now.state;
    const working = state !== "resting";
    const draft = typeof now.draft === "string" && now.draft.trim() ? now.draft.trim() : null;
    const text = now.text || "";
    document.body.dataset.mood = state;
    $("label").textContent = LABELS[state] ?? "";
    paragraphs(text, working && state !== "waiting" && Boolean(text));
    $("draft").hidden = !draft;
    $("draft-text").textContent = draft ?? "";
    $("say").hidden = !text && !draft;
    if (presence) presence.set(state);

    clearTimeout(hideTimer);
    if (working || draft) {
      setShown(true);
    } else {
      const left = (text ? readingMs(text) : 1500) - (Date.now() - restedAt);
      if (left > 0) {
        setShown(true);
        hideTimer = setTimeout(() => setShown(false), left);
      } else {
        setShown(false);
      }
    }
    if (!shown && presence) presence.halt();  // set() above may have woken it; nothing shows, so nothing draws.
  }

  function apply(data) {
    if (!data || typeof data !== "object") return;
    if (typeof data.anchor === "string" && FRAME === "screen") setAnchor(data.anchor);
    const state = STATES.has(data.state) ? data.state : data.state === "ready" ? "resting" : now.state;
    if (state === "resting" && now.state !== "resting") restedAt = Date.now();
    const text = typeof data.text === "string" ? data.text : now.text;
    if (state === "resting" && text !== lastText) restedAt = Date.now();  // A new answer at rest restarts the clock.
    lastText = text;
    now.state = state;
    now.text = text;
    now.draft = data.draft === undefined ? now.draft : data.draft;
    render();
  }

  function connect() {
    if (typeof EventSource === "undefined") return;
    const es = new EventSource(EVENTS);
    const onMessage = (e) => {
      let data;
      try { data = JSON.parse(e.data); } catch { return; }
      apply(data);
    };
    es.onmessage = onMessage;
    for (const name of ["overlay", "state"]) es.addEventListener(name, onMessage);
    es.onopen = () => { downSince = null; };
    es.onerror = () => {
      downSince ??= Date.now();
      if (es.readyState === EventSource.CLOSED) setTimeout(connect, 2000);
    };
  }

  // A dropped stream never leaves Rook "thinking" over the game.
  setInterval(() => {
    if (downSince !== null && Date.now() - downSince > OFFLINE_FADE_MS && (now.state !== "resting" || shown)) {
      apply({ state: "resting", text: "", draft: null });
    }
  }, 2000);

  async function boot() {
    document.body.dataset.frame = FRAME;
    setAnchor(params.get("anchor") || "middle-right");
    const canvas = $("dust");
    if (typeof RookPresence !== "undefined") {
      try {
        await RookPresence.load(canvas);
        presence = RookPresence;
        presence.set(now.state);
        if (!shown) presence.halt();
      } catch (e) {
        console.warn("presence did not load", e);
      }
    }
    render();
    connect();
  }

  window.rookOverlay = {
    apply,
    visible: () => shown,
    info: () => ({ shown, state: now.state, gl: Boolean(presence?.stats?.gl), frames: presence?.stats?.frames ?? 0 }),
  };

  window.addEventListener("DOMContentLoaded", () => { boot().catch((e) => console.warn(e)); });
})();
