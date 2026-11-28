// The panel's state, kept outside React so the event listener runs (and toasts) while the Quick Access panel is shut.
// The backend owns the truth: status and history are read again from it whenever an event says something changed.
import { toaster } from "@decky/api";
import {
  Activity, Card, Exchange, RookEvent, Status, getHistory, getStatus,
} from "./api";

export interface Live {
  turn?: string | number;
  request?: string;
  draft?: string | null;
  activity: Activity[];
}

export interface Model {
  status: Status;
  loaded: boolean;
  history: Exchange[];
  live: Live;
  card: Card | null;
  error: string | null;
  chat: { sender?: string; text?: string; channel?: string } | null;
}

const ACTIVITY_MAX = 40;
const HISTORY_MAX = 50;

let model: Model = {
  status: {},
  loaded: false,
  history: [],
  live: { activity: [] },
  card: null,
  error: null,
  chat: null,
};
const listeners = new Set<() => void>();
let panelOpen = false;

function set(patch: Partial<Model>) {
  model = { ...model, ...patch };
  for (const l of listeners) l();
}

export const store = {
  get: () => model,
  subscribe(l: () => void) {
    listeners.add(l);
    return () => { listeners.delete(l); };
  },
  setPanelOpen(open: boolean) { panelOpen = open; },
  clearError() { set({ error: null }); },
  setError(error: string | null) { set({ error }); },
  dropCard(id: string) { if (model.card?.id === id) set({ card: null }); },
  patchStatus(patch: Partial<Status>) { set({ status: { ...model.status, ...patch } }); },
  refresh,
  refreshSoon,
  handle,
};

export async function refresh() {
  try {
    const [status, raw] = await Promise.all([getStatus(), getHistory().catch(() => [])]);
    const history = normaliseHistory(raw);
    const s = status ?? {};
    const card = s.card !== undefined ? s.card ?? null : model.card;
    set({ status: s, history, card, loaded: true, live: liveAfter(history, s) });
  } catch (e) {
    set({ loaded: true, error: model.error ?? `The Rook backend did not answer: ${String(e)}` });
  }
}

let soon: ReturnType<typeof setTimeout> | null = null;
export function refreshSoon(ms = 250) {
  if (soon) clearTimeout(soon);
  soon = setTimeout(() => { soon = null; refresh(); }, ms);
}

// The live turn ends once the history holds its answer; while Rook works the draft and the activity lines stay.
function liveAfter(history: Exchange[], s: Status): Live {
  const live = model.live;
  if (s.draft !== undefined && s.draft !== live.draft) return { ...live, draft: s.draft };
  if (live.turn !== undefined && history.some((x) => (x.turn ?? x.id) === live.turn && x.answer)) {
    return { activity: [] };
  }
  return live;
}

// History arrives oldest first (or with timestamps); the panel shows it newest first.
export function normaliseHistory(raw: unknown): Exchange[] {
  let list: Exchange[] = [];
  if (Array.isArray(raw)) list = raw as Exchange[];
  else if (raw && typeof raw === "object") {
    const r = raw as { items?: Exchange[]; history?: Exchange[] };
    list = r.items ?? r.history ?? [];
  }
  list = list.filter((x) => x && typeof x === "object");
  const timed = list.length > 1 && list.every((x) => typeof x.at === "number");
  const ordered = timed ? [...list].sort((a, b) => (b.at ?? 0) - (a.at ?? 0)) : [...list].reverse();
  return ordered.slice(0, HISTORY_MAX);
}

function short(text: string, n = 160) {
  const t = text.replace(/\s+/g, " ").trim();
  return t.length > n ? `${t.slice(0, n - 1)}…` : t;
}

function toast(title: string, body: string, critical = false) {
  if (panelOpen) return;
  try {
    toaster.toast({ title, body, critical, duration: critical ? 8000 : 6000 });
  } catch { /* A toast is a courtesy. */ }
}

function cardFrom(e: RookEvent): Card | null {
  if (e.card !== undefined) return e.card && e.card.id ? e.card : null;
  if (!e.id) return null;
  return { id: e.id, tool: e.tool, question: e.question ?? e.text ?? undefined, options: e.options, state: e.state };
}

export function handle(e: RookEvent) {
  if (!e || typeof e !== "object") return;
  switch (e.type) {
    case "state": {
      const patch: Partial<Status> = {};
      if (e.state !== undefined) patch.state = e.state;
      if (e.connected !== undefined) patch.connected = e.connected;
      if (e.paired !== undefined) patch.paired = e.paired;
      if (e.talking !== undefined) patch.talking = e.talking;
      const resting = e.state === "resting" || e.state === "ready";
      set({ status: { ...model.status, ...patch } });
      if (resting || e.paired !== undefined || e.connected !== undefined) refreshSoon(400);
      break;
    }
    case "activity": {
      const live = model.live;
      const sameTurn = e.turn === undefined || live.turn === undefined || e.turn === live.turn;
      const step: Activity = { kind: e.kind, label: e.label ?? e.text ?? undefined, detail: e.detail, icon: e.icon };
      const activity = [...(sameTurn ? live.activity : []), step].slice(-ACTIVITY_MAX);
      set({ live: { ...live, turn: e.turn ?? live.turn, activity, draft: sameTurn ? live.draft : null } });
      break;
    }
    case "draft": {
      const live = model.live;
      set({ live: { ...live, turn: e.turn ?? live.turn, request: e.request ?? live.request, draft: e.text ?? null } });
      break;
    }
    case "answer": {
      const text = e.text ?? e.answer ?? "";
      set({ live: { activity: [] } });
      if (text) toast("Rook", short(text));
      refreshSoon(150);
      break;
    }
    case "card": {
      const card = cardFrom(e);
      if (!card || card.state === "resolved") {
        const id = e.id ?? e.card?.id;
        if (!id || model.card?.id === id) set({ card: null });
      } else {
        const fresh = model.card?.id !== card.id;
        set({ card });
        if (fresh) toast("Rook needs your answer", short(card.question ?? card.tool ?? "Open Rook in Quick Access."), true);
      }
      break;
    }
    case "error": {
      const text = e.message ?? e.error ?? e.text ?? "Something went wrong.";
      set({ error: text });
      toast("Rook", short(text), true);
      refreshSoon(500);
      break;
    }
    case "chat": {
      set({ chat: { sender: e.sender, text: e.text ?? undefined, channel: e.channel } });
      const who = e.sender ? `${e.sender}${e.channel ? ` (${e.channel})` : ""}` : "Chat";
      if (e.text) toast(who, short(e.text));
      break;
    }
    default:
      refreshSoon(500);
  }
}
