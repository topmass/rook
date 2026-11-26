// Standalone transparent presence host page for desktop web views (macOS RookHelper.app).
// Loads phone/presence.js (WebGL gold dust) by default, or themes/forge/presence.js when ?pack=<name> is set,
// and drives it from the same /snapshot and /events SSE stream that the phone app uses.
"use strict";

(() => {
  const params = new URLSearchParams(location.search);
  const pack = (params.get("pack") || "").replace(/[^a-z0-9_-]/gi, "");
  const state = {
    rook: "ready",
    dark: false,
    card: null,
    activity: null,
    step: 0,
    lastId: 0,
    connected: false,
    ready: false,
  };
  let presence = null;

  function moodAndKind() {
    if (state.card) return ["waiting", null, null];
    if (state.activity && state.rook !== "speaking") return ["thinking", state.activity.kind || null, state.activity.n];
    if (["listening", "transcribing", "speaking", "thinking", "error"].includes(state.rook)) return [state.rook, null, null];
    return [state.dark ? "dark" : "resting", null, null];
  }

  function render() {
    if (!presence) return;
    const [mood, kind, n] = moodAndKind();
    presence.set(mood, kind, n);
  }

  function apply(kind, data) {
    if (!data || typeof data !== "object") return;
    if (kind === "state") {
      if (data.state !== undefined) state.rook = data.state;
      if (data.dark !== undefined) state.dark = Boolean(data.dark);
      if (data.state === "ready") state.activity = null;
      if (typeof data.level === "number" && presence) presence.setLevel(data.level);
    } else if (kind === "activity") {
      state.activity = { kind: data.kind || null, n: ++state.step };
    } else if (kind === "card") {
      state.card = data.state === "resolved" ? null : data;
    } else if (kind === "request") {
      if (data.answer || ["done", "failed", "empty", "cancelled"].includes(data.state)) state.activity = null;
    } else if (kind === "level" && typeof data.level === "number" && presence) {
      presence.setLevel(data.level);
      return;
    } else if (kind === "mood" && data.mood) {
      state.rook = data.mood === "resting" ? "ready" : data.mood;
      state.activity = data.kind ? { kind: data.kind, n: ++state.step } : null;
      if (typeof data.level === "number" && presence) presence.setLevel(data.level);
    }
    render();
  }

  async function syncAndStream() {
    try {
      const res = await fetch("/snapshot", { credentials: "same-origin" });
      if (res.ok) {
        const snap = await res.json();
        state.lastId = snap.cursor || 0;
        state.rook = snap.state || "ready";
        state.dark = Boolean(snap.dark);
        state.card = snap.card || null;
        const lastAct = Array.isArray(snap.activity) ? snap.activity.at(-1) : null;
        state.activity = lastAct ? { kind: lastAct.kind || null, n: ++state.step } : null;
        render();
      }
    } catch {}
    const es = new EventSource(`/events?after=${state.lastId}`, { withCredentials: true });
    es.onopen = () => { state.connected = true; };
    es.onerror = () => { state.connected = false; };
    for (const kind of ["state", "activity", "card", "request"]) {
      es.addEventListener(kind, (e) => {
        let data;
        try { data = JSON.parse(e.data); } catch { return; }
        if (!data.live && e.lastEventId) {
          const seq = Number(e.lastEventId);
          if (seq <= state.lastId) return;
          state.lastId = seq;
        }
        apply(kind, data);
      });
    }
  }

  async function boot() {
    const canvas = document.getElementById("dust");
    if (pack && typeof ThemePresence !== "undefined") {
      presence = ThemePresence.phone({ base: `/themes/${pack}/` });
    } else if (typeof RookPresence !== "undefined") {
      presence = RookPresence;
    }
    if (presence) {
      await presence.load(canvas);
      state.ready = true;
      render();
    }
    syncAndStream();
  }

  window.rookPresenceHost = {
    apply,
    info() {
      return {
        ready: state.ready,
        connected: state.connected,
        pack: pack || "devs",
        gl: Boolean(presence?.stats?.gl),
        form: presence?.form ? presence.form() : null,
        forms: presence?.forms ? presence.forms().length : 0,
      };
    },
  };

  window.addEventListener("DOMContentLoaded", () => { boot().catch(() => {}); });
})();
