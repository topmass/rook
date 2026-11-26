// Rook on the phone: Rook's presence at the top, which is the main control (tap to talk, tap to send), and below it
// everything Rook says and does, newest first. Typing is the second way in. It speaks protocol versions 1 to 3 (see
// phone/standin.py). Every word from the server is shown as text, never as HTML.
"use strict";

const $ = (id) => document.getElementById(id);

const store = {
  get(key) {
    try { return JSON.parse(localStorage.getItem(key)); } catch { return null; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* A private window keeps nothing. */ }
  },
};

const IN_FLIGHT = new Set(["hearing", "queued", "accepted", "handed", "working"]);
const PENDING_WORDS = {
  sending: "Sending", offline: "Waits to send",
  hearing: "Transcribing", queued: "Queued", accepted: "Queued", handed: "Thinking", working: "Working",
};

const app = {
  exchanges: [],  // {key, turn, cmd, text, state, answer, at, client, source, phase, error}
  outbox: store.get("rook.outbox") || [],  // Typed requests the server has not acknowledged: {id, text, at}.
  card: null,
  rook: "resting",
  dark: false,
  held: null,
  work: [],
  activity: new Map(),  // turn -> [{kind, label, detail, icon}], live only
  drafts: new Map(),  // turn -> the answer so far, live only
  lastId: 0,
  stream: null,
  connected: false,
  backoff: 1000,
  collapsed: store.get("rook.collapsed") === true,  // Presence only: the text is tucked away on this phone.
};
// A request waits in the outbox at most this long: well inside the record's one-day memory of command ids, so a resend
// can never run a request twice. The check compares the two windows.
const OUTBOX_MAX_SECONDS = 20 * 3600;
const sending = new Set();  // Command ids with a post on the wire, so a flush never sends one twice at once.

class Unpaired extends Error {}

async function api(path, body) {
  const init = body === undefined ? { cache: "no-store" }
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const res = await fetch(path, init);
  if (res.status === 401) {
    showPairing();
    throw new Unpaired();
  }
  let data = {};
  try { data = (await res.json()) ?? {}; } catch { /* A body that is not JSON counts as empty. */ }
  return { status: res.status, data };
}

function make(tag, cls, text) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text !== undefined) el.textContent = text;
  return el;
}

// The dust: Rook's gold grains, drawn as a loose ring, as the desktop's resting loop is.
function sowDust(svg) {
  const count = Number(svg.dataset.grains);
  const size = svg.viewBox.baseVal.width;
  const ns = "http://www.w3.org/2000/svg";
  const tones = ["var(--amber)", "var(--gold-mid)", "var(--pale-gold)"];
  let seed = count * 7919;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const ring = document.createElementNS(ns, "g");
  ring.setAttribute("class", "dust-ring");
  for (let i = 0; i < count; i++) {
    const angle = (i / count) * Math.PI * 2 + rnd() * 0.3;
    const radius = size * (0.31 + (rnd() - 0.5) * 0.07);
    const grain = document.createElementNS(ns, "circle");
    grain.setAttribute("cx", (size / 2 + Math.cos(angle) * radius).toFixed(2));
    grain.setAttribute("cy", (size / 2 + Math.sin(angle) * radius).toFixed(2));
    grain.setAttribute("r", (size * (size < 100 ? 0.022 + rnd() * 0.022 : 0.009 + rnd() * 0.014)).toFixed(2));
    grain.setAttribute("fill", tones[i % 3]);
    grain.setAttribute("opacity", (0.4 + rnd() * 0.6).toFixed(2));
    grain.style.animationDelay = `${(-rnd() * 3).toFixed(2)}s`;
    ring.append(grain);
  }
  svg.append(ring);
}

// Answers are text with a little markdown: paragraphs, lists, fenced code, inline code, bold and headings.
function inline(tag, text) {
  const el = make(tag);
  for (const part of text.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*)/)) {
    if (!part) continue;
    if (part.length > 2 && part.startsWith("`") && part.endsWith("`")) el.append(make("code", null, part.slice(1, -1)));
    else if (part.length > 4 && part.startsWith("**") && part.endsWith("**")) el.append(make("strong", null, part.slice(2, -2)));
    else el.append(part);
  }
  return el;
}

function renderAnswer(text, root) {
  const lines = String(text).replace(/\r\n?/g, "\n").split("\n");
  const item = /^\s*(?:[-*•]|(\d+)[.)])\s+(.*)$/;
  let para = [];
  const endPara = () => {
    if (para.length) root.append(inline("p", para.join(" ")));
    para = [];
  };
  for (let i = 0; i < lines.length;) {
    const line = lines[i];
    if (line.trimStart().startsWith("```")) {
      endPara();
      const code = [];
      for (i++; i < lines.length && !lines[i].trimStart().startsWith("```"); i++) code.push(lines[i]);
      i++;
      const pre = make("pre");
      pre.append(make("code", null, code.join("\n")));
      root.append(pre);
    } else if (item.test(line)) {
      endPara();
      const list = make(item.exec(line)[1] ? "ol" : "ul");
      for (let m; i < lines.length && (m = item.exec(lines[i])); i++) list.append(inline("li", m[2]));
      root.append(list);
    } else if (/^#{1,6}\s/.test(line)) {
      endPara();
      root.append(inline("h3", line.replace(/^#+\s+/, "")));
      i++;
    } else {
      if (line.trim()) para.push(line.trim());
      else endPara();
      i++;
    }
  }
  endPara();
  root.firstElementChild?.classList.add("lead");
}

function clock(at) {
  return new Date(at * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function fromRequest(r) {
  return { key: `t:${r.turn}`, turn: r.turn, text: r.text ?? "", state: r.state, answer: r.answer ?? null,
           at: r.at ?? Date.now() / 1000, client: r.client, source: r.source };
}

function whereFrom(x) {
  const me = store.get("rook.device");
  if (x.cmd || (me && (x.client === me.id || x.client === me.name))) {
    return x.voice || x.source === "spoken" ? "Spoken on this phone" : "This phone";
  }
  if (!x.client || x.client === "desktop") return x.source === "spoken" ? "Spoken at the desk" : "At the desk";
  return `From ${x.client}`;
}

// What Rook does during a turn: one line per activity event, each with its icon. ICONS names the sprite's symbols;
// an unknown name falls back to the plain dot. KIND_WORDS is the presence's label for the newest line.
const ICONS = new Set(["thinking", "reading", "searching", "running", "editing", "sending", "launching", "waiting",
                       "showing", "drawing", "timing", "game", "speaking", "tool", "dot"]);
const KIND_WORDS = {
  thinking: "Thinking", reading: "Reading", searching: "Searching", running: "Running a command",
  editing: "Writing", sending: "Sending to a thread", launching: "Starting a thread", waiting: "Waiting",
  showing: "Showing media", drawing: "Drawing", timing: "Setting a timer", game: "In the game",
  speaking: "Speaking", tool: "Working",
};
const RUNNING = new Set(["handed", "working"]);
const TRAIL_MAX = 60;  // A turn keeps at most this many lines; the oldest go first.
let stepCount = 0;  // Numbers every line, so a redraw notices a new one even when the oldest was dropped.

function icon(name, cls = "icon") {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("class", cls);
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(ns, "use");
  use.setAttribute("href", `#i-${ICONS.has(name) ? name : "dot"}`);
  svg.append(use);
  return svg;
}

function stepIcon(step) {
  return step.icon && ICONS.has(step.icon) ? step.icon : step.icon ? "dot" : ICONS.has(step.kind) ? step.kind : "dot";
}

// The fold's one line: what Rook did, counted by kind, in the order it first did each. Thinking alone says so.
const NUMBER_WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"];
const count = (n, noun) => `${NUMBER_WORDS[n] ?? n} ${noun}${n === 1 ? "" : "s"}`;
const times = (verb) => (n) => (n === 1 ? verb : n === 2 ? `${verb} twice` : `${verb} ${NUMBER_WORDS[n] ?? n} times`);
const DID = {
  reading: times("read"), searching: times("searched"), running: (n) => `ran ${count(n, "command")}`,
  editing: (n) => `edited ${count(n, "file")}`, sending: (n) => `sent ${count(n, "message")}`,
  launching: (n) => `started ${count(n, "thread")}`, waiting: times("waited"),
  showing: (n) => (n === 1 ? "showed something on screen" : `showed ${NUMBER_WORDS[n] ?? n} things on screen`),
  drawing: (n) => `drew ${count(n, "diagram")}`, timing: (n) => `set ${count(n, "timer")}`,
  game: () => "checked the game", speaking: times("spoke"), tool: (n) => `used ${count(n, "tool")}`,
};

function summarise(steps) {
  const counts = new Map();
  for (const step of steps) {
    const kind = step.kind in DID || step.kind === "thinking" ? step.kind : "tool";
    counts.set(kind, (counts.get(kind) ?? 0) + 1);
  }
  counts.delete("thinking");
  const said = [...counts].map(([kind, n]) => DID[kind](n));
  if (!said.length) return "Rook thought it through.";
  const last = said.pop();
  return `Rook ${said.length ? `${said.join(", ")} and ${last}` : last}.`;
}

function drawStep(step) {
  const li = make("li", "step");
  const words = make("div", "step-words");
  words.append(make("p", "step-label", step.label ?? ""));
  if (step.detail) words.append(make("p", "step-detail", step.detail));
  li.append(icon(stepIcon(step)), words);
  return li;
}

const openTrails = new Set();  // Turns whose folded trail the owner opened, so a redraw keeps it open.

// The trail while the turn runs: lines are appended, never redrawn, so only the newest one moves.
function drawTrail(slot, x, steps, done) {
  const shape = done ? "fold" : "live";
  if (!steps.length) {
    slot.trail.replaceChildren();
    slot.trailShape = null;
    return;
  }
  if (slot.trailShape !== shape || (shape === "fold" && slot.trailCount !== steps.length)) {
    slot.trailShape = shape;
    slot.trailCount = 0;
    slot.list = make("ol", "trail-list");
    if (shape === "live") {
      slot.trail.replaceChildren(slot.list);
    } else {
      const fold = make("details", "trail");
      fold.open = openTrails.has(x.turn);
      fold.addEventListener("toggle", () => {
        if (fold.open) openTrails.add(x.turn);
        else openTrails.delete(x.turn);
      });
      const summary = make("summary", "trail-summary");
      const marks = make("span", "trail-marks");
      for (const name of [...new Set(steps.map(stepIcon))].slice(0, 3)) marks.append(icon(name));
      const chevron = icon("dot", "trail-chevron");
      chevron.replaceChildren(chevronPath());
      summary.append(marks, make("span", "trail-said", summarise(steps)), chevron);
      fold.append(summary, slot.list);
      slot.trail.replaceChildren(fold);
    }
  }
  if (slot.trailFirst !== steps[0]) {  // The oldest lines were dropped: draw the list again.
    slot.list.replaceChildren();
    slot.trailCount = 0;
    slot.trailFirst = steps[0];
  }
  for (const step of steps.slice(slot.trailCount)) slot.list.append(drawStep(step));
  slot.trailCount = steps.length;
  slot.list.querySelector(".step-now")?.classList.remove("step-now");
  if (shape === "live") slot.list.lastElementChild?.classList.add("step-now");
}

function chevronPath() {
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "m9 6 6 6-6 6");
  return path;
}

function drawBody(x, draft, steps) {
  if (x.phase === "failed") {
    return [make("p", "turn-note turn-error",
                 x.old ? x.error : `Rook did not take this request. ${x.error ?? ""}`.trim())];
  }
  if (x.answer || draft) {
    const answer = make("div", x.answer ? "answer" : "answer draft");
    renderAnswer(x.answer ?? draft, answer);
    if (!x.answer) {  // The answer so far ends in a glimmering grain, where the words are still arriving.
      let tail = answer.lastElementChild;
      while (tail && /^(UL|OL)$/.test(tail.tagName)) tail = tail.lastElementChild;
      (tail ?? answer).append(make("span", "draft-grain"));
    }
    return [answer];
  }
  if (x.phase || IN_FLIGHT.has(x.state)) {
    if (steps.length && !x.phase) return [];  // The trail says what Rook is doing.
    const note = make("p", "pending label", PENDING_WORDS[x.phase ?? x.state]);
    note.prepend(make("span", "pending-grains"));
    if (x.phase === "offline") note.classList.add("pending-offline");
    return [note];
  }
  if (x.state === "interrupted") return [make("p", "turn-note", "Rook stopped before it answered.")];
  if (x.state) return [make("p", "turn-note", "Rook closed this request without an answer.")];
  return [];
}

// The conversation is keyed by request. Each exchange has three parts, the request, the trail and the answer, and
// each is redrawn only when its own data changes, so a draft four times a second leaves the trail and the scroll alone.
const drawn = new Map();  // key -> {el, head, trail, body, sigs}

function drawExchange(x) {
  let slot = drawn.get(x.key);
  if (!slot) {
    slot = { el: make("article", "turn"), head: make("div", "turn-head"), trail: make("div", "turn-trail"),
             body: make("div", "turn-body"), sigs: {} };
    slot.el.append(slot.head, slot.trail, slot.body);
    drawn.set(x.key, slot);
  }
  const steps = (x.turn && app.activity.get(x.turn)) || [];
  const done = !(x.phase || IN_FLIGHT.has(x.state)) || Boolean(x.answer);
  const draft = x.turn && !x.answer ? app.drafts.get(x.turn) ?? null : null;
  const sigs = {
    head: JSON.stringify([x.text, x.at, x.client, x.source, Boolean(x.cmd), Boolean(x.voice)]),
    trail: JSON.stringify([steps.length, steps.at(-1)?.n, done]),
    body: JSON.stringify([x.state, x.answer, x.phase, x.error, draft, steps.length > 0]),
  };
  if (slot.sigs.head !== sigs.head) {
    const ask = x.text ? make("p", "ask", x.text) : make("p", "ask ask-waiting", "Your words are on their way to Rook.");
    slot.head.replaceChildren(make("p", "ask-meta label", `${clock(x.at)} · ${whereFrom(x)}`), ask);
  }
  if (slot.sigs.trail !== sigs.trail) drawTrail(slot, x, steps, done);
  if (slot.sigs.body !== sigs.body) slot.body.replaceChildren(...drawBody(x, draft, steps));
  slot.sigs = sigs;
  if (x.turn) slot.el.dataset.turn = x.turn;
  return slot.el;
}

// Newest first, right under the presence, so Rook's latest words hang beneath Rook. Older exchanges lie further
// down. Growth at the top never moves what the owner scrolled to: the browser anchors the scroll to what they read.
function render() {
  app.exchanges.sort((a, b) => b.at - a.at);
  const keep = new Set(app.exchanges.map((x) => x.key));
  for (const [key, slot] of drawn) if (!keep.has(key)) { slot.el.remove(); drawn.delete(key); }
  let last = $("empty");
  for (const x of app.exchanges) {
    const el = drawExchange(x);
    if (last.nextElementSibling !== el) last.after(el);  // Moves only what is out of order.
    last = el;
  }
  $("empty").hidden = app.exchanges.length > 0;
  renderPresence();
  renderCard();
  renderStop();
  renderCollapse();
  $("work-flag").hidden = !app.work.some((w) => w.state === "waiting");
}

let renderQueued = false;
function renderSoon() {  // Events coalesce into one draw per frame.
  if (renderQueued) return;
  renderQueued = true;
  requestAnimationFrame(() => {
    renderQueued = false;
    render();
  });
}

function runningTurn() {
  const live = app.exchanges.filter((x) => x.turn && !x.answer && (RUNNING.has(x.state)
    || (IN_FLIGHT.has(x.state) && app.activity.has(x.turn))));
  return live.at(-1)?.turn ?? null;
}

// Rook's presence: the mood and the small-caps label under it, as the desktop shows them. Resting has no label.
function presenceMood() {
  const turn = runningTurn();
  const doing = turn && app.rook !== "speaking" ? app.activity.get(turn)?.at(-1) : null;
  const heard = app.exchanges.some((x) => x.state === "hearing"
    || (x.voice && x.cmd && (!x.text) && x.phase !== "failed" && (x.phase || IN_FLIGHT.has(x.state))));
  if (voice.phase === "recording" || voice.phase === "asking") return ["listening", null];
  if (voice.phase === "uploading" || heard) return ["transcribing", null];
  if (voice.playing) return ["speaking", null];
  if (app.card) return ["waiting", null];
  if (app.away) return ["away", null];
  if (doing) return ["thinking", doing];
  const desk = app.rook;
  if (desk === "listening" || desk === "transcribing" || desk === "speaking" || desk === "thinking") return [desk, null];
  if (desk === "error") return ["error", null];
  return [app.dark ? "dark" : "resting", null];
}

const MOOD_LABELS = { listening: "Listening", transcribing: "Transcribing", thinking: "Thinking" };

function renderPresence() {
  const [mood, doing] = presenceMood();
  const label = mood === "thinking" && doing ? KIND_WORDS[doing.kind] ?? "Thinking" : MOOD_LABELS[mood]
    ?? (mood === "speaking" && app.collapsed && !app.card ? "Speaking" : "");  // With no text to read, speech says so too.
  $("presence-label").textContent = label;
  $("shell").dataset.mood = mood;
  $("presence").setAttribute("aria-label", voice.phase === "recording" ? "Stop and send to Rook"
    : voice.playing ? "Stop Rook speaking and talk" : "Talk to Rook");
  if (typeof RookPresence !== "undefined") RookPresence.set(mood, doing?.kind ?? null, doing?.n ?? null);
  renderNote();
}

// One quiet line under the presence: the connection first, then the newest thing voice has to say.
let noteText = "";
let noteTimer;
function note(text, seconds = 8) {
  noteText = text;
  clearTimeout(noteTimer);
  if (seconds) noteTimer = setTimeout(() => { noteText = ""; renderNote(); }, seconds * 1000);
  renderNote();
}

function renderNote() {
  const line = $("presence-note");
  const words = app.away ? (voice.pending ? "Rook is out of reach. Your recording waits here and sends when Rook is back."
    : "Rook is out of reach. What you type waits here and sends when Rook is back.") : noteText || app.held?.label || "";
  line.textContent = words;
  line.hidden = !words;
}

// Voice in: a tap on the presence starts a recording, a second tap sends it. A tap while Rook speaks on the phone
// stops the speech at once and starts a recording, as a talk key does at the desk.
const RECORD_MAX_SECONDS = 290;  // Under five minutes: about 1.2 MB of Opus, well inside the server's 4 MiB.
const RECORD_MAX_BYTES = 3.5 * 1024 * 1024;
const RECORD_MIN_SECONDS = 0.5;
const voice = {
  phase: "idle",  // idle, asking (the microphone is opening), recording, uploading
  stream: null, recorder: null, chunks: [], bytes: 0, startedAt: 0, why: null, capTimer: null,
  audio: null, meter: null, pending: null, uploading: false, retryTimer: null, wake: null,
  playing: false, queue: null, muted: new Set(), old: new Set(), played: [], els: [], cur: 0, failedTurn: null,
  maxSeconds: RECORD_MAX_SECONDS,
};

function onPresenceTap() {
  unlockAudio();
  if (voice.phase === "recording") return finishRecording("tap");
  if (voice.phase === "asking") return;
  if (voice.playing || voice.queue) stopSpeech();
  startRecording();
}

function unlockAudio() {
  // The first tap lets the page play sound later without one; the elements load nothing until a piece arrives.
  for (const el of voice.els) if (!el.dataset.unlocked) {
    el.dataset.unlocked = "1";
    el.load();
  }
  try {  // The tap also starts the audio clock that measures Rook's speech for the globe.
    voice.audio ??= new AudioContext();
    voice.audio.resume();
  } catch { /* The globe then moves to a stand-in rhythm. */ }
}

// Rook's speech level as it plays here, as the desk measures its own: the RMS of each 50 ms, under 0.01 silent, times
// 3.5. The analyser listens to a copy of the element's sound (captureStream), so playback never depends on it.
// Where a browser has no captureStream, or the audio clock is not running, the globe moves to a stand-in rhythm.
function speechLevels(el) {
  speechLevelsOff();
  const ctx = voice.audio;
  if (!ctx || ctx.state !== "running" || typeof el.captureStream !== "function") return;
  try {
    const stream = el.captureStream();
    if (!stream.getAudioTracks().length) return;
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    const samples = new Float32Array(analyser.fftSize);
    voice.speechSource = source;
    voice.speechMeter = setInterval(() => {
      analyser.getFloatTimeDomainData(samples);
      let sum = 0;
      for (const v of samples) sum += v * v;
      const rms = Math.sqrt(sum / samples.length);
      RookPresence.setSpeech(rms < 0.01 ? 0 : Math.min(1, rms * 3.5));
    }, 50);
  } catch {
    speechLevelsOff();
  }
}

function speechLevelsOff() {
  clearInterval(voice.speechMeter);
  voice.speechMeter = null;
  voice.speechSource?.disconnect();
  voice.speechSource = null;
}

async function startRecording() {
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
    note("This browser cannot record here. Type below instead.");
    return;
  }
  voice.phase = "asking";
  renderPresence();
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
  } catch (err) {
    voice.phase = "idle";
    note(err?.name === "NotAllowedError" || err?.name === "SecurityError"
      ? "Rook cannot use the microphone. Allow it for this site in the browser's settings, or type below."
      : "The microphone did not start. Tap Rook to try again, or type below.", 12);
    renderPresence();
    return;
  }
  let recorder;
  try {
    recorder = new MediaRecorder(stream, { audioBitsPerSecond: 32000 });
  } catch {
    recorder = new MediaRecorder(stream);
  }
  Object.assign(voice, { stream, recorder, chunks: [], bytes: 0, startedAt: performance.now(), why: null });
  recorder.ondataavailable = (e) => {
    if (!e.data.size) return;
    voice.chunks.push(e.data);
    voice.bytes += e.data.size;
    if (voice.bytes > RECORD_MAX_BYTES) finishRecording("long");
  };
  recorder.onstop = recorded;
  recorder.start(1000);
  voice.capTimer = setTimeout(() => finishRecording("long"), voice.maxSeconds * 1000);
  meterOn(stream);
  keepAwake(true);
  voice.phase = "recording";
  noteText = "";
  renderPresence();
}

function finishRecording(why) {
  if (voice.phase !== "recording") return;
  voice.why = why;
  clearTimeout(voice.capTimer);
  voice.phase = "uploading";
  try { voice.recorder.stop(); } catch { recorded(); }
  for (const track of voice.stream.getTracks()) track.stop();
  meterOff();
  renderPresence();
}

function recorded() {
  const seconds = (performance.now() - voice.startedAt) / 1000;
  const type = voice.recorder?.mimeType || voice.chunks[0]?.type || "audio/webm";
  const blob = new Blob(voice.chunks, { type });
  Object.assign(voice, { recorder: null, stream: null, chunks: [] });
  if (seconds < RECORD_MIN_SECONDS || !blob.size) {
    voice.phase = "idle";
    note("That was too short to hear. Tap once to start, and again to send.");
    renderPresence();
    return;
  }
  if (voice.why === "long") note("That ran close to five minutes, so Rook took what you said so far.", 10);
  const id = crypto.randomUUID();
  voice.pending = { id, blob, at: Date.now() / 1000 };
  app.exchanges.push({ key: `c:${id}`, cmd: id, voice: true, text: "", at: voice.pending.at, phase: "sending" });
  $("talk").scrollTop = 0;
  render();
  uploadPending();
}

async function uploadPending() {
  const job = voice.pending;
  if (!job || voice.uploading) return;
  voice.uploading = true;
  voice.phase = "uploading";
  const x = app.exchanges.find((e) => e.cmd === job.id);
  try {
    const res = await fetch("/audio", { method: "POST", body: job.blob,
                                        headers: { "Content-Type": job.blob.type, "X-Rook-Command": job.id } });
    if (res.status === 401) return showPairing();
    let data = {};
    try { data = (await res.json()) ?? {}; } catch { /* An empty body reads as a refusal below. */ }
    if (res.status === 429) {
      note(data.error ?? "Rook is still hearing your last recording.");
      throw new Error("busy");
    }
    if (res.status >= 500) throw new Error("busy");
    voice.pending = null;
    if (x && data.ok) {
      const twin = app.exchanges.find((e) => e.turn === data.turn && e !== x);
      if (twin) {
        twin.voice = true;
        app.exchanges = app.exchanges.filter((e) => e !== x);
      } else {
        Object.assign(x, { turn: data.turn, phase: null, state: x.state ?? "accepted" });
      }
    } else if (x) {
      Object.assign(x, { phase: "failed", error: data.error ?? "Rook did not take the recording." });
    }
  } catch {
    // Kept, with its id, and sent again once Rook answers: the server runs one command id once.
    clearTimeout(voice.retryTimer);
    voice.retryTimer = setTimeout(uploadPending, 3000);
  } finally {
    voice.uploading = false;
    if (!voice.pending && voice.phase === "uploading") voice.phase = "idle";
    render();
  }
}

function meterOn(stream) {
  try {
    voice.audio ??= new AudioContext();
    voice.audio.resume();
    const source = voice.audio.createMediaStreamSource(stream);
    const analyser = voice.audio.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    const samples = new Float32Array(analyser.fftSize);
    let floor = 0.01;
    voice.meter = setInterval(() => {
      analyser.getFloatTimeDomainData(samples);
      let sum = 0;
      for (const v of samples) sum += v * v;
      const rms = Math.sqrt(sum / samples.length);
      floor = Math.min(rms, floor * 1.002 + 0.00002);
      RookPresence.setLevel(Math.min(1, Math.max(0, (rms - floor) * 9)));
    }, 33);
    voice.meterSource = source;
  } catch {
    voice.meter = null;  // Without a meter the ring still listens; it only does not move with the voice.
  }
}

function meterOff() {
  clearInterval(voice.meter);
  voice.meter = null;
  voice.meterSource?.disconnect();
  if (typeof RookPresence !== "undefined") RookPresence.setLevel(0);
}

async function keepAwake(on) {
  try {
    if (on && !voice.wake && "wakeLock" in navigator && !document.hidden) {
      voice.wake = await navigator.wakeLock.request("screen");
      voice.wake.addEventListener("release", () => { voice.wake = null; });
    } else if (!on && voice.wake) {
      await voice.wake.release();
    }
  } catch { /* The screen may still sleep; nothing else changes. */ }
}

// Voice out: each speech event names a piece of the answer. The pieces play in order on two audio elements that take
// turns, so the next piece is loaded while one plays and starts the moment it ends.
function speechUrl(piece) {
  return `/speech/${encodeURIComponent(piece.id)}`;
}

function isOlderTurn(turn) {
  if (voice.old.has(turn)) return true;
  const mine = app.exchanges.find((e) => e.turn === turn);
  return Boolean(mine && app.exchanges.some((e) => e.turn && e.turn !== turn && e.at > mine.at));
}

function hearSpeech(d) {
  const me = store.get("rook.device")?.id;
  if (!d.turn || !d.id || !me || d.device !== me || voice.muted.has(d.turn) || voice.failedTurn === d.turn
      || isOlderTurn(d.turn)) return;
  if (!voice.queue || voice.queue.turn !== d.turn) {
    if (voice.queue) voice.old.add(voice.queue.turn);
    stopSpeech(false);
    voice.queue = { turn: d.turn, next: 0, pieces: new Map() };
  }
  if (Number.isInteger(d.index) && d.index >= voice.queue.next) voice.queue.pieces.set(d.index, d);
  pumpSpeech();
}

function pumpSpeech() {
  const q = voice.queue;
  if (!q) return;
  const piece = q.pieces.get(q.next);
  const el = voice.els[voice.cur];
  if (!voice.playing && piece) {
    if (el.dataset.piece !== piece.id) {
      el.src = speechUrl(piece);
      el.dataset.piece = piece.id;
    }
    voice.playing = true;
    el.play().then(() => {
      voice.played.push(piece.id);
      speaking(true);
      if (typeof RookPresence !== "undefined") speechLevels(el);
    }).catch(() => speechFailed(q.turn));
  }
  // The piece after this one waits, loaded, in the other element.
  const after = q.pieces.get(q.next + (voice.playing ? 1 : 0));
  const other = voice.els[voice.cur ^ 1];
  if (voice.playing && after && other.dataset.piece !== after.id) {
    other.src = speechUrl(after);
    other.dataset.piece = after.id;
    other.load();
  }
}

function pieceEnded() {
  const q = voice.queue;
  voice.playing = false;
  if (!q) return speaking(false);
  q.pieces.delete(q.next);
  q.next += 1;
  voice.cur ^= 1;
  pumpSpeech();
  if (!voice.playing) {
    // Speech may still be on its way; the sphere settles after a short pause with nothing to play.
    clearTimeout(voice.quiet);
    voice.quiet = setTimeout(() => { if (!voice.playing) speaking(false); }, 700);
  }
}

function speechFailed(turn) {
  stopSpeech(false);
  voice.failedTurn = turn;
  note("Rook's voice did not play on this phone. The answer is below in text.", 12);
}

function stopSpeech(mute = true) {
  if (mute && voice.queue) voice.muted.add(voice.queue.turn);
  for (const el of voice.els) {
    el.pause();
    el.removeAttribute("src");
    delete el.dataset.piece;
  }
  voice.queue = null;
  voice.playing = false;
  speaking(false);
}

function speaking(on) {
  if ("mediaSession" in navigator) {
    try {
      navigator.mediaSession.metadata = on ? new MediaMetadata({ title: "Rook", artist: "Speaking",
        artwork: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml" }] }) : null;
      navigator.mediaSession.playbackState = on ? "playing" : "none";
    } catch { /* Lock-screen controls are a courtesy. */ }
  }
  if (!on) speechLevelsOff();
  if (!on && voice.phase === "idle") keepAwake(false);
  renderPresence();
}

function setupVoice() {
  voice.els = [$("voice-a"), $("voice-b")];
  for (const el of voice.els) {
    el.addEventListener("ended", pieceEnded);
    el.addEventListener("error", () => { if (voice.playing && el === voice.els[voice.cur]) speechFailed(voice.queue?.turn); });
  }
  if ("mediaSession" in navigator) {
    for (const action of ["pause", "stop"]) {
      try { navigator.mediaSession.setActionHandler(action, () => stopSpeech()); } catch { /* Not offered here. */ }
    }
  }
  $("presence").addEventListener("click", onPresenceTap);
  const toggle = $("ask-voice");
  const aloud = () => toggle.getAttribute("aria-pressed") === "true";
  toggle.setAttribute("aria-pressed", String(store.get("rook.aloud") === true));
  toggle.addEventListener("click", () => {
    toggle.setAttribute("aria-pressed", String(!aloud()));
    store.set("rook.aloud", aloud());
    if (aloud()) unlockAudio();
  });
}

// Stop: while a turn runs and the field is empty, the send control's place offers Stop for that turn.
const stops = new Map();  // turn -> "sent" | "stale"

function renderStop() {
  const turn = runningTurn();
  const show = Boolean(turn) && !$("ask-text").value.trim() && stops.get(turn) !== "stale";
  const button = $("ask-stop");
  button.hidden = !show;
  $("ask-send").hidden = show;
  button.disabled = show && stops.get(turn) === "sent";
  button.setAttribute("aria-label", button.disabled ? "Stopping this turn" : "Stop this turn");
  button.dataset.turn = turn ?? "";
}

async function stopTurn() {
  const button = $("ask-stop");
  const turn = button.dataset.turn;
  if (!turn) return;
  button.disabled = true;
  try {
    const { data } = await api("/command", { id: crypto.randomUUID(), kind: "stop", turn });
    if (data.ok) stops.set(turn, "sent");
    else if (data.error === "stale") stops.set(turn, "stale");  // That turn had already ended: the control goes.
  } catch (err) {
    if (err instanceof Unpaired) return;
  }
  render();
}

function renderLink() {
  app.away = !(navigator.onLine && app.connected);
  renderPresence();
}

let linkTimer;
function setConnected(up) {
  app.connected = up;
  clearTimeout(linkTimer);
  if (up) renderLink();
  else linkTimer = setTimeout(renderLink, 1200);  // A routine reconnect passes without a flicker.
  for (const x of app.exchanges) if (x.cmd && !x.turn && x.phase !== "failed") x.phase = up ? "sending" : "offline";
  render();
}

// The waiting card: what asks, for what, in the card's own words, with Allow and Decline. It redraws whenever its id
// or its words change.
let cardShown = null;
let cardBusy = false;  // An answer is on its way: the buttons stay inactive, even on a card drawn meanwhile.
function renderCard() {
  const box = $("card");
  const card = app.card;
  if (!card) {
    box.hidden = true;
    cardShown = null;
    return;
  }
  // Drawn again when the card itself changes: a stored card, replayed, has only a summary, and the live or whole one
  // with the same id brings its full words after it.
  if (cardShown === card) return;
  cardShown = card;
  $("card-note").hidden = true;
  box.replaceChildren();
  box.append(make("h2", "card-title", card.tool ? `Rook wants to use ${card.tool}.` : "Rook needs your answer."));
  box.lastChild.id = "card-title";
  if (card.count > 1) box.append(make("p", "turn-note", `Card 1 of ${card.count}`));
  const question = make("div", "card-question");
  question.append(make("p", null, card.question ?? ""));
  for (const option of card.options ?? []) {
    question.append(make("p", "card-option", typeof option === "string" ? option : option.label ?? ""));
  }
  box.append(question);
  if (card.desk) {  // A question with options is answered at the desk in this release.
    box.append(make("p", "turn-note", "Answer this one at your desk."));
    box.hidden = false;
    return;
  }
  const row = make("div", "card-actions");
  const allow = make("button", "button button-primary", "Allow");
  const decline = make("button", "button", "Decline");
  allow.type = decline.type = "button";
  allow.disabled = decline.disabled = cardBusy;
  allow.addEventListener("click", () => answerCard(card, true, [allow, decline]));
  decline.addEventListener("click", () => answerCard(card, false, [allow, decline]));
  row.append(decline, allow);
  box.append(row);
  box.hidden = false;
}

function cardNote(text) {
  const note = $("card-note");
  note.textContent = text;
  note.hidden = false;
  clearTimeout(cardNote.timer);
  cardNote.timer = setTimeout(() => {
    note.hidden = true;
    render();  // A presence-only view held open for the note tucks the text away again.
  }, 7000);
}

async function answerCard(card, allow, buttons) {
  for (const b of buttons) b.disabled = true;
  cardBusy = true;
  try {
    const { data } = await api("/command", { id: crypto.randomUUID(), kind: "card", card: card.id, allow, answers: {} });
    if (data.ok || data.error === "stale") {
      if (app.card?.id === card.id) app.card = null;
      if (data.error === "stale") cardNote("That card had already closed, so nothing changed.");
      render();
      return;
    }
    cardNote(data.error ?? "Rook did not take the answer. Try again.");
  } catch (err) {
    if (err instanceof Unpaired) return;
    cardNote("The answer did not reach Rook. Try again.");
  } finally {
    cardBusy = false;
    for (const b of document.querySelectorAll("#card .card-actions button")) b.disabled = false;
  }
}

// Presence only: the text tucks away below the screen and Rook fills it. The arrow at the bottom brings the text back
// as it was, since it stays laid out while hidden. A card opens the text until it is answered, and its note keeps it
// open until it has been read: neither can wait unseen. A new ending to a request (an answer, a refusal, no answer)
// and work that waits on the owner mark the arrow with a dot.
let seenEnds = null;  // The endings there were when the text was last in view, so the arrow can mark new ones.
const ends = () => app.exchanges.map((x) => {
  const end = x.answer ? "answer" : x.phase === "failed" ? "failed"
    : x.state && !x.phase && !IN_FLIGHT.has(x.state) ? "closed" : null;
  return end && `${x.key} ${end}`;
}).filter(Boolean);

function setCollapsed(on) {
  const keys = document.activeElement === (on ? $("collapse") : $("expand"));  // A keyboard user keeps a focus.
  app.collapsed = on;
  store.set("rook.collapsed", on);
  render();
  if (keys) (on ? $("expand") : $("collapse")).focus({ preventScroll: true });
}

function renderCollapse() {
  const shell = $("shell");
  const on = app.collapsed && !app.card && $("card-note").hidden;
  shell.classList.toggle("asking", Boolean(app.card));
  if (shell.classList.contains("collapsed") !== on) {
    if (on) document.activeElement?.blur();  // The keyboard closes; the words typed so far stay in the field.
    shell.classList.toggle("collapsed", on);
    for (const el of [$("collapse"), $("talk"), $("ask-form").parentElement]) el.inert = on;
    $("expand").inert = !on;
    for (const el of [$("collapse"), $("expand")]) el.setAttribute("aria-expanded", String(!on));
    if (typeof RookPresence !== "undefined") {
      RookPresence.setZoom(on ? Number(getComputedStyle(shell).getPropertyValue("--zoom")) || 1 : 1);
    }
  }
  if (!on && seenEnds) seenEnds = new Set(ends());
  const fresh = seenEnds ? ends().filter((key) => !seenEnds.has(key)).length : 0;
  const waiting = app.work.some((w) => w.state === "waiting") || Boolean(app.held);
  $("expand-flag").hidden = !fresh && !waiting;
  const news = [fresh && (fresh === 1 ? "one new reply" : `${NUMBER_WORDS[fresh] ?? fresh} new replies`),
                waiting && "something waits on you"].filter(Boolean);
  $("expand").setAttribute("aria-label", ["Show the text", ...news].join(", "));
  renderCaption();
}

// Live captions: with the text tucked away, Rook's newest words show under it, as the desk's captions do. An answer
// still being written shows its last words, a finished one its first. They go CAPTION_SECONDS after the newest word,
// unless Rook is still speaking.
const CAPTION_SECONDS = 20;
const CAPTION_CHARACTERS = 180;
let captionAt = 0;
let captionTimer;

function captionFresh() {
  captionAt = Date.now();
  clearTimeout(captionTimer);
  captionTimer = setTimeout(renderSoon, CAPTION_SECONDS * 1000 + 50);
}

function plainWords(text) {
  return String(text).replace(/```[\s\S]*?(?:```|$)/g, " ").replace(/^\s*(?:[-*•]|\d+[.)]|#+)\s+/gm, "")
    .replace(/[`*]/g, "").replace(/\s+/g, " ").trim();
}

function renderCaption() {
  const line = $("caption");
  const x = app.exchanges[0];  // render sorts the newest first.
  const draft = x?.turn && !x.answer ? app.drafts.get(x.turn) : null;
  let words = x ? plainWords(x.answer ?? draft ?? "") : "";
  const live = voice.playing || app.rook === "speaking" || Date.now() - captionAt < CAPTION_SECONDS * 1000;
  line.hidden = !words || !live || !$("shell").classList.contains("collapsed");
  if (line.hidden) return;
  if (words.length > CAPTION_CHARACTERS) {
    words = draft ? `…${words.slice(-CAPTION_CHARACTERS).replace(/^\S*\s/, "")}`
      : `${words.slice(0, CAPTION_CHARACTERS).replace(/\s\S*$/, "")}…`;
  }
  line.textContent = words;
}

function setupCollapse() {
  const handle = $("collapse");
  let from = null;
  let dragged = false;
  handle.addEventListener("pointerdown", (e) => {
    from = e.clientY;
    dragged = false;
    handle.setPointerCapture(e.pointerId);
  });
  handle.addEventListener("pointermove", (e) => {  // A pull down on the handle tucks the text away too.
    if (from === null || e.clientY - from < 28) return;
    from = null;
    dragged = true;
    setCollapsed(true);
  });
  for (const kind of ["pointerup", "pointercancel"]) handle.addEventListener(kind, () => { from = null; });
  handle.addEventListener("click", () => {
    if (dragged) dragged = false;
    else setCollapsed(true);
  });
  $("expand").addEventListener("click", () => {
    dragged = false;
    setCollapsed(false);
  });
  setupPull();
}

// Rook only: a pull down on Rook tucks everything else away, and a push up anywhere brings it back. Rook follows the
// finger a little as a hint, and the text fades with the pull. The view changes at PULL_PX. A pull that moves Rook
// is not a tap, so it never starts a recording. The presence takes no browser gesture (touch-action: none), so the
// page's own scroll and pull-to-refresh stay as they were everywhere else.
const PULL_PX = 56;
const PULL_SLOP = 10;

function setupPull() {
  const shell = $("shell");
  let pull = null;  // {id, x, y}
  let swallow = false;  // The click that ends a pull is not a tap.
  const end = () => {
    pull = null;
    shell.classList.remove("pulling");
    shell.style.removeProperty("--pull");
  };
  shell.addEventListener("pointerdown", (e) => {
    swallow = false;
    if (pull || !e.isPrimary || e.button > 0) return;
    if (!shell.classList.contains("collapsed") && !e.target.closest("#presence")) return;
    pull = { id: e.pointerId, x: e.clientX, y: e.clientY };
  });
  shell.addEventListener("pointermove", (e) => {
    if (!pull || e.pointerId !== pull.id) return;
    const dx = e.clientX - pull.x;
    const dy = e.clientY - pull.y;
    const tucked = shell.classList.contains("collapsed");
    const way = tucked ? -dy : dy;  // The way that changes the view: down to tuck, up to bring the text back.
    if (Math.abs(dx) > PULL_SLOP && Math.abs(dx) > Math.abs(dy)) return end();  // Sideways is not a pull.
    if (way < PULL_SLOP && !shell.classList.contains("pulling")) return;
    swallow = true;
    shell.classList.add("pulling");
    shell.style.setProperty("--pull", String(Math.max(0, Math.min(1, way / PULL_PX))));
    if (way >= PULL_PX) {
      end();
      setCollapsed(!tucked);
    }
  });
  for (const kind of ["pointerup", "pointercancel"]) shell.addEventListener(kind, end);
  shell.addEventListener("click", (e) => {
    if (!swallow) return;
    swallow = false;
    e.stopPropagation();
    e.preventDefault();
  }, true);
}

// Sending: a request shows at once, goes out with an id made here, and a retry reuses that id.
function saveOutbox() {
  store.set("rook.outbox", app.outbox);
}

function send(text) {
  const msg = { id: crypto.randomUUID(), text, at: Date.now() / 1000 };
  if ($("ask-voice").getAttribute("aria-pressed") === "true") msg.voice = true;  // Answered aloud on this phone too.
  app.outbox.push(msg);
  saveOutbox();
  app.exchanges.push({ key: `c:${msg.id}`, cmd: msg.id, text, at: msg.at, phase: app.connected ? "sending" : "offline" });
  render();
  $("talk").scrollTop = 0;
  flush();
}

let retryTimer;
async function flush() {
  if (!app.connected) return;
  for (const msg of [...app.outbox]) {
    if (sending.has(msg.id)) continue;
    const x = app.exchanges.find((e) => e.cmd === msg.id);
    if (Date.now() / 1000 - msg.at > OUTBOX_MAX_SECONDS) {  // Too old to send safely: the owner decides.
      app.outbox = app.outbox.filter((m) => m.id !== msg.id);
      saveOutbox();
      if (x) Object.assign(x, { phase: "failed", old: true, error: "Not sent: too old. Send it again." });
      render();
      continue;
    }
    sending.add(msg.id);
    try {
      const command = { id: msg.id, kind: "ask", text: msg.text, mode: "queue", at: msg.at };
      if (msg.voice) command.voice = true;
      const { status, data } = await api("/command", command);
      if (status >= 500) throw new Error("server");
      app.outbox = app.outbox.filter((m) => m.id !== msg.id);
      saveOutbox();
      if (x && data.ok) {
        const twin = app.exchanges.find((e) => e.turn === data.turn && e !== x);
        if (twin) app.exchanges = app.exchanges.filter((e) => e !== x);
        else Object.assign(x, { turn: data.turn, phase: null, state: x.state ?? "accepted" });
      } else if (x) {
        Object.assign(x, { phase: "failed", error: data.error });
      }
    } catch (err) {
      if (err instanceof Unpaired) return;
      clearTimeout(retryTimer);
      retryTimer = setTimeout(flush, 3000);
    } finally {
      sending.delete(msg.id);
    }
    render();
  }
}

// The event stream. Each stored event carries its sequence number as its id, and each applies once.
const APPLY = {
  request(d) {
    if (d.state === "empty") {  // A recording with no words in it, or one that failed: no exchange, one quiet line.
      app.exchanges = app.exchanges.filter((e) => e.turn !== d.turn);
      note(d.reason === "failed" ? "That did not go through. Say it again."
        : "Rook heard no words in that recording.");
      return;
    }
    let x = app.exchanges.find((e) => e.turn === d.turn);
    if (!x) {
      // The event can beat the post's own answer: adopt the request this phone is still sending.
      x = app.exchanges.find((e) => e.cmd && !e.turn && e.text === d.text);
      if (x) x.turn = d.turn;
    }
    if (!x) {
      x = fromRequest(d);
      app.exchanges.push(x);
    }
    x.phase = null;
    x.state = d.state ?? x.state;
    if (d.text !== undefined) x.text = d.text;
    if (d.answer !== undefined) x.answer = d.answer;
    if (x.answer || !IN_FLIGHT.has(x.state)) app.drafts.delete(d.turn);
    if (d.answer) captionFresh();
  },
  activity(d) {
    if (!d.turn) return;
    const steps = app.activity.get(d.turn) ?? [];
    steps.push({ kind: d.kind, label: d.label, detail: d.detail, icon: d.icon, n: ++stepCount });
    app.activity.set(d.turn, steps.slice(-TRAIL_MAX));
    app.drafts.delete(d.turn);  // A tool call clears the answer so far.
  },
  speech(d) {
    hearSpeech(d);
  },
  draft(d) {
    if (!d.turn) return;
    const x = app.exchanges.find((e) => e.turn === d.turn);
    if (x?.answer) return;  // The final answer has arrived; a late draft never covers it.
    if (d.text) {
      app.drafts.set(d.turn, d.text);
      captionFresh();
    } else {
      app.drafts.delete(d.turn);
    }
  },
  card(d) {
    if (d.state === "resolved") {
      if (app.card?.id === d.id) app.card = null;
    } else if (!app.card || app.card.id !== d.id || d.live) {
      // A live card carries its full words. A stored one, replayed, keeps only a summary, and the phone reads the
      // whole card from the snapshot.
      app.card = d;
      if (!d.live && !d.desk) wholeCard(d.id);
    }
  },
  state(d) {
    if (d.state !== undefined) app.rook = d.state;
    if (d.dark !== undefined) app.dark = Boolean(d.dark);
    if (d.held !== undefined) app.held = d.held;
  },
  lists(d) {
    if (d.list !== "mailbox") loadWork();
  },
};

function onEvent(kind, e) {
  let data;
  try { data = JSON.parse(e.data); } catch { return; }
  // A live event has no id of its own: a browser repeats the last id on it, so only a stored one is checked.
  if (!data.live) {
    if (e.lastEventId && Number(e.lastEventId) <= app.lastId) return;  // Applied already.
    if (e.lastEventId) app.lastId = Number(e.lastEventId);
  }
  APPLY[kind](data);
  renderSoon();
}

function connect() {
  app.stream?.close();
  const es = new EventSource(`/events?after=${app.lastId}`);
  app.stream = es;
  es.onopen = () => {
    app.backoff = 1000;
    setConnected(true);
    flush();
    uploadPending();
    loadWork();  // A change made while the stream was down sends no event.
  };
  es.onerror = () => {
    setConnected(false);
    // A browser retries a dropped stream by itself, but gives up for good on a refused one.
    if (es.readyState === EventSource.CLOSED) {
      setTimeout(attach, app.backoff);
      app.backoff = Math.min(app.backoff * 2, 15000);
    }
  };
  for (const kind of Object.keys(APPLY)) es.addEventListener(kind, (e) => onEvent(kind, e));
  es.addEventListener("snapshot", () => attach());  // The cursor is too old: read the whole state again.
}

function applySnapshot(s) {
  app.lastId = Number(s.cursor) || 0;
  app.rook = (typeof s.state === "object" ? s.state?.state : s.state) ?? "resting";
  app.dark = Boolean(s.dark);
  app.held = s.held ?? null;
  app.card = s.card ?? null;
  app.work = s.work ?? app.work;
  const local = app.exchanges.filter((x) => x.cmd && !x.turn);
  app.exchanges = (s.requests ?? []).map(fromRequest).concat(local);
  // A phone that attaches mid-turn shows what Rook is doing at once. A line without a turn is the running turn's.
  const fresh = new Map();
  const running = app.exchanges.filter((x) => x.turn && IN_FLIGHT.has(x.state)).at(-1)?.turn;
  for (const step of Array.isArray(s.activity) ? s.activity : []) {
    const turn = step.turn ?? running;
    if (!turn) continue;
    if (!fresh.has(turn)) fresh.set(turn, []);
    fresh.get(turn).push({ kind: step.kind, label: step.label, detail: step.detail, icon: step.icon, n: ++stepCount });
  }
  for (const [turn, steps] of fresh) app.activity.set(turn, steps.slice(-TRAIL_MAX));
}

async function wholeCard(id) {
  try {
    const { status, data } = await api("/snapshot");
    if (status === 200 && data.card?.id === id && app.card?.id === id) {
      app.card = data.card;
      render();
    }
  } catch {}  // The summary stays, with its buttons.
}

async function attach() {
  app.stream?.close();
  try {
    const { status, data } = await api("/snapshot");
    if (status !== 200) throw new Error("snapshot");
    applySnapshot(data);
    seenEnds ??= new Set(ends());  // What the phone opens on is not new.
    showShell();
    render();
    connect();
  } catch (err) {
    if (err instanceof Unpaired) return;
    if ($("pair").hidden) {
      showShell();
      setConnected(false);
    }
    app.backoff = Math.min(app.backoff * 2, 15000);
    setTimeout(attach, app.backoff);
  }
}

// The work list: what waits on the owner, then what finished, then what runs. Read-only in this release.
const WORK_GROUPS = [
  ["Waiting on you", ["waiting"]],
  ["Finished", ["done", "live"]],
  ["Running", ["running", "sent", "drafted"]],
];

function renderWork(error) {
  const body = $("work-body");
  body.replaceChildren();
  if (error) {
    body.append(make("p", "empty", "Rook did not send the work list. Close it and open it again in a moment."));
    return;
  }
  for (const [title, states] of WORK_GROUPS) {
    const items = app.work.filter((w) => states.includes(w.state));
    if (!items.length) continue;
    const group = make("section", "work-group");
    group.append(make("h3", "label work-heading", title));
    const list = make("ul", "work-list");
    for (const w of items) {
      const li = make("li", "work-item");
      li.append(make("p", "work-project label", w.project || "No project"), make("p", "work-wish", w.wish ?? ""));
      if (w.news) li.append(make("p", "work-news", w.news));
      if (w.try) li.append(make("p", "work-try", w.try));
      list.append(li);
    }
    group.append(list);
    body.append(group);
  }
  if (!body.childElementCount) body.append(make("p", "empty", "Nothing is on the work list."));
}

async function loadWork() {
  try {
    const { data } = await api("/work");
    app.work = Array.isArray(data) ? data : data.work ?? [];
    renderWork();
    render();
  } catch (err) {
    if (!(err instanceof Unpaired) && !$("work").hidden) renderWork(true);
  }
}

function openWork() {
  $("work").hidden = false;
  renderWork();
  loadWork();
  $("work-close").focus();
  history.pushState({ work: true }, "");
}

function closeWork() {
  $("work").hidden = true;
  $("work-open").focus();
}

// Screens.
function showPairing() {
  app.stream?.close();
  $("shell").hidden = true;
  $("pair").hidden = false;
  const name = $("pair-name");
  if (!name.value) {
    const ua = navigator.userAgent;
    name.value = /iPhone/.test(ua) ? "iPhone" : /iPad/.test(ua) ? "iPad" : /Pixel/.test(ua) ? "Pixel"
      : /Android/.test(ua) ? "Android phone" : "Phone";
  }
  if ($("pair-code").value) name.focus();  // A code from the link (see start): only the name is left.
}

function showShell() {
  $("pair").hidden = true;
  $("pair-code").value = "";  // A code from an old link never comes back on a later pairing screen.
  $("shell").hidden = false;
}

async function pair(event) {
  event.preventDefault();
  const error = $("pair-error");
  const code = $("pair-code").value.replace(/\s+/g, "");
  const name = $("pair-name").value.trim();
  error.hidden = true;
  if (!code || !name) {
    error.textContent = code ? "Give this phone a name." : "Enter the pairing code from Rook.";
    error.hidden = false;
    return;
  }
  const button = event.target.querySelector("button");
  button.disabled = true;
  try {
    const res = await fetch("/pair", { method: "POST", headers: { "Content-Type": "application/json" },
                                       body: JSON.stringify({ code, name }) });
    let data = {};
    try { data = await res.json(); } catch { /* Shown as the plain sentence below. */ }
    if (res.ok && data.ok) {
      store.set("rook.device", data.device ?? { name });
      $("pair-code").value = "";
      await attach();
    } else {
      error.textContent = data.error ?? "That code is wrong or has expired. Ask Rook for a new one.";
      error.hidden = false;
    }
  } catch {
    error.textContent = "Rook did not answer. Check that this phone is on your tailnet, then try again.";
    error.hidden = false;
  }
  button.disabled = false;
}

// The phone's keyboard: the app fills the visual viewport, so the field stays above the keys.
function fitViewport() {
  const vv = window.visualViewport;
  if (!vv) return;
  const root = document.documentElement.style;
  root.setProperty("--app-height", `${vv.height}px`);
  root.setProperty("--app-top", `${vv.offsetTop}px`);
  document.documentElement.classList.toggle("keyboard", window.innerHeight - vv.height > 120);
}

function start() {
  document.querySelectorAll("svg.dust").forEach(sowDust);
  fitViewport();
  window.visualViewport?.addEventListener("resize", fitViewport);
  window.visualViewport?.addEventListener("scroll", fitViewport);

  $("pair-form").addEventListener("submit", pair);
  // A pairing link (#code=482913) fills in the code, and the address drops it.
  const linked = new URLSearchParams(location.hash.slice(1)).get("code");
  if (linked) {
    $("pair-code").value = linked;
    history.replaceState(null, "", location.pathname + location.search);
  }
  const text = $("ask-text");
  const ask = $("ask-form");
  text.addEventListener("input", () => {
    $("ask-send").disabled = !text.value.trim();
    renderStop();
  });
  $("ask-stop").addEventListener("click", stopTurn);
  setupVoice();
  setupCollapse();
  if (typeof RookPresence !== "undefined") RookPresence.load($("dust")).then(renderPresence).catch(() => {});
  text.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && window.matchMedia("(pointer: fine)").matches) {
      e.preventDefault();
      ask.requestSubmit();
    }
  });
  ask.addEventListener("submit", (e) => {
    e.preventDefault();
    const words = text.value.trim();
    if (!words) return;
    text.value = "";
    $("ask-send").disabled = true;
    send(words);
  });
  $("work-open").addEventListener("click", openWork);
  $("work-close").addEventListener("click", () => history.back());
  window.addEventListener("popstate", () => { if (!$("work").hidden) closeWork(); });
  window.addEventListener("online", () => { renderLink(); if (!app.connected) attach(); });
  window.addEventListener("offline", renderLink);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && app.stream?.readyState === EventSource.CLOSED) attach();
  });

  for (const msg of app.outbox) {
    app.exchanges.push({ key: `c:${msg.id}`, cmd: msg.id, text: msg.text, at: msg.at, phase: "offline" });
  }
  attach();
}

start();
