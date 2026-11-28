// The Quick Access panel: pairing, Rook's state, push-to-talk, a typed request, stop, the waiting card, history,
// the Deck agent token, the hotkey and unpairing. Every control is a @decky/ui one, so the gamepad reaches it.
import {
  ButtonItem, ConfirmModal, DialogButton, DropdownItem, Field, Focusable, GamepadButton, GamepadEvent,
  PanelSection, PanelSectionRow, TextField, showModal,
} from "@decky/ui";
import { useQuickAccessVisible } from "@decky/api";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import {
  Activity, Card, Exchange, OVERLAY_ANCHORS, answerCard, failure, getDeckToken, setAddonsDir, setOverlayPosition, optionLabel, pair, sendText, setHotkey,
  stop, talkStart, talkStop, unpair,
} from "./api";
import { Dust, moodFor } from "./dust";
import { Icon, stepIcon } from "./icons";
import { store } from "./store";

const CSS = `
.rook-panel { --rook-gold: #f2b347; --rook-pale: #fde9b2; --rook-dim: #9a98a6; --rook-ink: #0b0c0f; }
.rook-presence { display: flex; align-items: center; gap: 10px; }
.rook-presence canvas { width: 88px; height: 44px; flex: none; }
.rook-state { font-variant: small-caps; letter-spacing: .08em; color: var(--rook-pale); font-weight: 700; }
.rook-sub { color: var(--rook-dim); font-size: 12px; line-height: 1.35; }
.rook-error { color: #f0907a; font-size: 12px; line-height: 1.35; white-space: pre-wrap; }
.rook-item { padding: 8px 2px 10px; border-bottom: 1px solid rgba(242,179,71,.16); }
.rook-item.gpfocus, .rook-item:focus-within { background: rgba(242,179,71,.08); border-radius: 6px; }
.rook-request { color: var(--rook-pale); font-size: 13px; line-height: 1.35; font-style: italic; }
.rook-answer { color: #e8e4d8; font-size: 13px; line-height: 1.4; white-space: pre-wrap; margin-top: 4px;
  overflow-wrap: anywhere; }
.rook-answer.clip { display: -webkit-box; -webkit-line-clamp: 5; -webkit-box-orient: vertical; overflow: hidden; }
.rook-draft { color: #cfc8b4; }
.rook-draft::after { content: ""; display: inline-block; width: 5px; height: 5px; margin-left: 4px; border-radius: 50%;
  background: var(--rook-gold); box-shadow: 0 0 6px var(--rook-gold); animation: rook-glim 1.2s ease-in-out infinite; }
@keyframes rook-glim { 50% { opacity: .25; } }
.rook-step { display: flex; gap: 6px; align-items: flex-start; font-size: 12px; color: var(--rook-dim); line-height: 1.35;
  margin-top: 3px; }
.rook-step b { color: #d9d3c1; font-weight: 500; }
.rook-meta { font-size: 11px; color: var(--rook-dim); margin-top: 3px; }
.rook-token { font-family: monospace; font-size: 15px; letter-spacing: .06em; color: var(--rook-pale);
  word-break: break-all; line-height: 1.5; user-select: all; }
.rook-talk { width: 100%; min-height: 44px; display: flex !important; align-items: center; justify-content: center;
  gap: 8px; }
.rook-talk.on { background: rgba(242,179,71,.85) !important; color: var(--rook-ink) !important; }
.rook-path { font-family: monospace; font-size: 12px; color: #e8e4d8; word-break: break-all; }
.rook-card-q { font-size: 13px; line-height: 1.4; color: #f2ecdc; white-space: pre-wrap; }
`;

const DEFAULT_HOTKEYS = ["L4+R4", "L5+R5", "L4", "R4", "L5", "R5", "L1+R1+A", "off"];
const HOTKEY_WORDS: Record<string, string> = {
  "L4+R4": "Both upper back buttons (L4 + R4)", "L5+R5": "Both lower back buttons (L5 + R5)",
  L4: "Upper left back button (L4)", R4: "Upper right back button (R4)", L5: "Lower left back button (L5)",
  R5: "Lower right back button (R5)", "L1+R1+A": "L1 + R1 + A (no back buttons)", off: "No hotkey",
};
const ANCHOR_WORDS: Record<string, string> = {
  "middle-right": "Right, below the minimap", "middle-left": "Left, middle", "top-right": "Top right (covers the minimap)",
  "top-left": "Top left", "bottom-center": "Bottom, above the action bars",
};
const STATE_WORDS: Record<string, string> = {
  resting: "Resting", ready: "Resting", listening: "Listening", transcribing: "Transcribing", thinking: "Thinking",
  speaking: "Speaking", waiting: "Waiting on you", error: "Something went wrong", dark: "Resting", away: "Away",
};

function useModel() {
  return useSyncExternalStore(store.subscribe, store.get);
}

async function run(what: Promise<unknown>) {
  try {
    const err = failure((await what) as never);
    if (err) store.setError(err);
    return !err;
  } catch (e) {
    store.setError(String(e));
    return false;
  }
}

function Presence({ state }: { state?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const dust = useRef<Dust | null>(null);
  useEffect(() => {
    if (!ref.current) return;
    const d = new Dust(ref.current);
    dust.current = d;
    d.start();
    return () => d.stop();
  }, []);
  useEffect(() => { dust.current?.set(moodFor(state)); }, [state]);
  return <canvas ref={ref} width={88} height={44} aria-hidden="true" />;
}

function StatusRow() {
  const { status, error } = useModel();
  const state = status.state ?? "resting";
  const word = !status.paired ? "Not paired" : status.connected === false ? "Offline" : STATE_WORDS[state] ?? state;
  const where = status.paired
    ? status.connected === false ? `Reconnecting to ${status.server_url ?? "Rook"}…` : `Paired with ${status.server_url ?? "Rook"}`
    : "Pair this Deck with Rook on your PC.";
  return (
    <PanelSectionRow>
      <Focusable
        className="rook-presence"
        onActivate={() => store.clearError()}
        onOKActionDescription={error ? "Clear the error" : undefined}
      >
        <Presence state={status.paired && status.connected !== false ? state : "resting"} />
        <div>
          <div className="rook-state">{word}</div>
          <div className="rook-sub">{where}</div>
          {status.overlay?.error && <div className="rook-error">Overlay: {status.overlay.error}</div>}
          {status.overlay?.others?.length ? (
            <div className="rook-sub">Another in-game overlay is showing (the performance overlay?). gamescope shows one
              at a time: turn it off to see Rook over the game.</div>
          ) : null}
          {(error ?? status.error) && <div className="rook-error">{error ?? status.error}</div>}
        </div>
      </Focusable>
    </PanelSectionRow>
  );
}

function Pairing() {
  const { status } = useModel();
  const [url, setUrl] = useState(status.server_url ?? "http://");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const clean = code.replace(/[^0-9a-z]/gi, "").toUpperCase();
  const go = async () => {
    setBusy(true);
    store.clearError();
    if (await run(pair(url.trim(), clean))) setCode("");
    await store.refresh();
    setBusy(false);
  };
  return (
    <PanelSection title="Pair with Rook">
      <PanelSectionRow>
        <TextField
          label="Rook's address"
          description="The phone server, e.g. http://my-pc:8447"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          mustBeURL
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <TextField
          label="Pairing code"
          description="Ask Rook at your desk for a code. It works once, for ten minutes."
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase().slice(0, 8))}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy || clean.length !== 6 || !/^https?:\/\/.+/.test(url.trim())} onClick={go}>
          {busy ? "Pairing…" : "Pair this Deck"}
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

// Hold to talk: A held on the button (or a finger on it). A short tap latches instead: tap to start, tap to send.
type TalkMode = "off" | "hold" | "latched";

function TalkButton({ disabled }: { disabled: boolean }) {
  const { status } = useModel();
  const [mode, setMode] = useState<TalkMode>("off");
  const modeRef = useRef<TalkMode>("off");
  const pressedAt = useRef(0);
  const lastAction = useRef(0);
  const put = (m: TalkMode) => { modeRef.current = m; setMode(m); };
  const start = (m: TalkMode) => { put(m); run(talkStart()); };
  const finish = () => { put("off"); lastAction.current = Date.now(); run(talkStop()); };
  const press = () => {
    lastAction.current = Date.now();
    if (disabled) return;
    if (modeRef.current === "latched") finish();
    else if (modeRef.current === "off") { pressedAt.current = Date.now(); start("hold"); }
  };
  const release = () => {
    if (modeRef.current !== "hold") return;
    lastAction.current = Date.now();
    if (Date.now() - pressedAt.current < 280) put("latched");
    else finish();
  };
  // The panel closing mid-recording sends what was said.
  useEffect(() => () => { if (modeRef.current !== "off") run(talkStop()); }, []);
  const isOK = (e: GamepadEvent) => e.detail?.button === GamepadButton.OK;
  const live = mode !== "off" || Boolean(status.talking);
  const words = mode === "latched" ? "Listening — press again to send"
    : mode === "hold" ? "Listening — release to send" : live ? "Listening…" : "Hold to talk";

  return (
    <DialogButton
      className={`rook-talk${live ? " on" : ""}`}
      disabled={disabled}
      onButtonDown={(e) => { if (isOK(e) && !e.detail?.is_repeat) press(); }}
      onButtonUp={(e) => { if (isOK(e)) release(); }}
      onPointerDown={() => press()}
      onPointerUp={() => release()}
      onPointerCancel={() => release()}
      onClick={() => {
        // A click with no press before it (a keyboard, or a Steam build without button events): toggle.
        if (Date.now() - lastAction.current < 600) return;
        if (modeRef.current === "off") start("latched");
        else finish();
      }}
      onOKActionDescription="Hold to talk"
    >
      <Icon name="voice" style={{ color: live ? "#0b0c0f" : undefined }} />
      {words}
    </DialogButton>
  );
}

function Talk() {
  const { status } = useModel();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const ready = Boolean(status.paired);
  const send = async () => {
    const t = text.trim();
    if (!t) return;
    setBusy(true);
    if (await run(sendText(t))) setText("");
    setBusy(false);
  };
  const working = !["resting", "ready", "dark", "away", undefined].includes(status.state as string);
  return (
    <PanelSection title="Talk to Rook">
      <PanelSectionRow>
        <TalkButton disabled={!ready} />
      </PanelSectionRow>
      <PanelSectionRow>
        <TextField
          label="Type a request"
          value={text}
          disabled={!ready || busy}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") send(); }}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={!ready || busy || !text.trim()} onClick={send}>
          {busy ? "Sending…" : "Send"}
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={!ready} onClick={() => run(stop())}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <Icon name="stop" /> {working ? "Stop Rook" : "Stop"}
          </span>
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

function CardView({ card }: { card: Card }) {
  const [busy, setBusy] = useState(false);
  const answer = async (value: string) => {
    setBusy(true);
    if (await run(answerCard(card.id, value))) store.dropCard(card.id);
    setBusy(false);
  };
  return (
    <PanelSection title={card.tool ? `Rook wants to use ${card.tool}` : card.title ?? "Rook needs your answer"}>
      {(card.question || card.options?.length) && (
        <PanelSectionRow>
          <Focusable>
            {card.question && <div className="rook-card-q">{card.question}</div>}
            {card.options?.map((o, i) => <div className="rook-step" key={i}>• {optionLabel(o)}</div>)}
          </Focusable>
        </PanelSectionRow>
      )}
      {card.desk ? (
        <PanelSectionRow><Field label="Answer this one at your desk" description="A question with options is answered at the PC." /></PanelSectionRow>
      ) : (
        <>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy} onClick={() => answer("allow")}>Allow</ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy} onClick={() => answer("decline")}>Decline</ButtonItem>
          </PanelSectionRow>
        </>
      )}
    </PanelSection>
  );
}

function Steps({ steps }: { steps: Activity[] }) {
  return (
    <>
      {steps.map((s, i) => (
        <div className="rook-step" key={i}>
          <Icon name={stepIcon(s)} size={14} />
          <span><b>{s.label ?? s.kind ?? "Working"}</b>{s.detail ? ` — ${s.detail}` : ""}</span>
        </div>
      ))}
    </>
  );
}

function clock(at?: number) {
  if (!at) return "";
  const ms = at > 1e12 ? at : at * 1000;
  return new Date(ms).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function HistoryItem({ x }: { x: Exchange }) {
  const [open, setOpen] = useState(false);
  const request = x.request ?? x.text ?? "";
  const answer = x.answer ?? "";
  const note = x.error ? x.error
    : !answer && x.state && !["done", "answered"].includes(x.state) ? x.state : "";
  return (
    <Focusable
      className="rook-item"
      onActivate={() => setOpen(!open)}
      onOKActionDescription={open ? "Show less" : "Show all"}
    >
      {request && <div className="rook-request">“{request}”</div>}
      {x.activity?.length ? <Steps steps={open ? x.activity : x.activity.slice(-3)} /> : null}
      {answer && <div className={`rook-answer${open ? "" : " clip"}`}>{answer}</div>}
      {note && <div className="rook-meta">{note}</div>}
      <div className="rook-meta">{clock(x.at)}</div>
    </Focusable>
  );
}

function History() {
  const { history, live, status } = useModel();
  const busy = !["resting", "ready", "dark", "away", "error", undefined].includes(status.state as string);
  const showLive = busy || Boolean(live.draft) || live.activity.length > 0;
  return (
    <PanelSection title="History">
      {showLive && (
        <PanelSectionRow>
          <Focusable className="rook-item">
            {live.request && <div className="rook-request">“{live.request}”</div>}
            <Steps steps={live.activity.slice(-4)} />
            {live.draft
              ? <div className="rook-answer rook-draft">{live.draft}</div>
              : <div className="rook-meta">{STATE_WORDS[status.state ?? ""] ?? "Working"}…</div>}
          </Focusable>
        </PanelSectionRow>
      )}
      {history.length === 0 && !showLive && (
        <PanelSectionRow><Field label="Nothing yet" description="Requests and answers show here, newest first." /></PanelSectionRow>
      )}
      {history.map((x, i) => (
        <PanelSectionRow key={String(x.turn ?? x.id ?? i)}><HistoryItem x={x} /></PanelSectionRow>
      ))}
    </PanelSection>
  );
}

// The WoW AddOns folder: where it is, whether it is usable, and a way to set it (empty: let the backend look).
function Addons() {
  const { status } = useModel();
  const wow = status.wow ?? {};
  const a = status.addons ?? {};
  const path = wow.addons_dir ?? a.path ?? status.addons_dir ?? "";
  const [edit, setEdit] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const friend = wow.wowfriend ?? a.addon;
  const state = a.error ? a.error
    : !path ? "Not found yet. Rook looks for it when WoW mode needs it, or set it here."
    : friend === false ? "Found; the WoWFriend add-on is not in it yet."
    : wow.slots === false ? "WoWFriend is there, but its note slots are missing: install the add-on zip, restart WoW."
    : "Found, with WoWFriend and its note slots.";
  const save = async () => {
    setBusy(true);
    if (await run(setAddonsDir((edit ?? "").trim()))) setEdit(null);
    await store.refresh();
    setBusy(false);
  };
  return (
    <>
      <PanelSectionRow>
        <Field label="WoW AddOns folder" description={state || undefined} childrenLayout="below" focusable
          onActivate={() => setEdit(edit === null ? path : null)}
          onOKActionDescription={edit === null ? "Change" : "Cancel"}>
          <div className="rook-path">{path || "—"}</div>
          {a.note && <div className="rook-sub">{a.note}</div>}
        </Field>
      </PanelSectionRow>
      {edit !== null && (
        <>
          <PanelSectionRow>
            <TextField
              label="AddOns folder path"
              description="The Interface/AddOns folder of the WoW install on this Deck. Leave empty to search again."
              value={edit}
              onChange={(e) => setEdit(e.target.value)}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy} onClick={save}>{busy ? "Saving…" : "Save folder"}</ButtonItem>
          </PanelSectionRow>
        </>
      )}
    </>
  );
}

function Settings() {
  const { status } = useModel();
  const [token, setToken] = useState<{ token: string; url?: string } | null>(null);
  const [shown, setShown] = useState(false);
  const hotkeys = status.hotkeys?.length ? status.hotkeys : DEFAULT_HOTKEYS;
  const loadToken = async () => {
    try {
      const t = await getDeckToken();
      setToken(typeof t === "string" ? { token: t } : { token: t?.token ?? "", url: t?.url });
    } catch (e) {
      store.setError(`No token: ${String(e)}`);
    }
  };
  useEffect(() => { if (shown && !token) loadToken(); }, [shown]);
  const confirmUnpair = () => showModal(
    <ConfirmModal
      strTitle="Unpair this Deck?"
      strDescription="Rook forgets this Deck. To talk to Rook again, pair with a new code."
      strOKButtonText="Unpair"
      onOK={async () => { await run(unpair()); await store.refresh(); }}
    />,
  );
  return (
    <PanelSection title="Settings">
      <PanelSectionRow>
        <DropdownItem
          label="Talk hotkey"
          description={status.hotkey_active && status.hotkey && status.hotkey_active !== status.hotkey
            ? `This Deck cannot read ${status.hotkey}; the talk chord is ${status.hotkey_active} for now.`
            : "Hold it in a game to talk to Rook."}
          rgOptions={hotkeys.map((h) => ({ data: h, label: HOTKEY_WORDS[h] ?? h }))}
          selectedOption={status.hotkey ?? null}
          strDefaultLabel="Choose a hotkey"
          onChange={async (o) => { if (await run(setHotkey(String(o.data)))) store.patchStatus({ hotkey: String(o.data) }); }}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <DropdownItem
          label="Overlay position"
          description="Where Rook shows over the game. It never covers the screen's centre or its top edge."
          rgOptions={OVERLAY_ANCHORS.map((a) => ({ data: a, label: ANCHOR_WORDS[a] ?? a }))}
          selectedOption={status.overlay?.anchor ?? status.overlay_position ?? "middle-right"}
          onChange={async (o) => {
            const anchor = String(o.data);
            if (await run(setOverlayPosition(anchor))) {
              store.patchStatus({ overlay_position: anchor, overlay: { ...(status.overlay ?? {}), anchor } });
            }
          }}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => setShown(!shown)}>
          {shown ? "Hide the Deck agent token" : "Show the Deck agent token"}
        </ButtonItem>
      </PanelSectionRow>
      {shown && (
        <PanelSectionRow>
          <Field
            label="Deck agent token"
            description={`On the PC, set ROOK_DECK_TOKEN to this${token?.url ? ` and ROOK_DECK_URL to ${token.url}` : ""}.`}
            childrenLayout="below"
            focusable
          >
            <div className="rook-token">{token ? token.token.replace(/(.{8})(?=.)/g, "$1 ") || "—" : "…"}</div>
          </Field>
        </PanelSectionRow>
      )}
      <Addons />
      {status.paired && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={confirmUnpair}>Unpair this Deck</ButtonItem>
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}

export function Content() {
  const model = useModel();
  const visible = useQuickAccessVisible();
  useEffect(() => {
    store.setPanelOpen(visible);
    if (!visible) return;
    store.refresh();
    const timer = setInterval(() => store.refresh(), 5000);
    return () => clearInterval(timer);
  }, [visible]);
  useEffect(() => () => store.setPanelOpen(false), []);
  const { status, card } = model;
  return (
    <div className="rook-panel">
      <style>{CSS}</style>
      <PanelSection>
        <StatusRow />
      </PanelSection>
      {!status.paired && model.loaded && <Pairing />}
      {status.paired && card && <CardView card={card} />}
      {status.paired && <Talk />}
      {status.paired && <History />}
      <Settings />
    </div>
  );
}
