// The plugin backend's callables and event shapes (docs/steamdeck-plan.md, "Contracts": Inside the plugin).
// The shapes beyond the contract's names are read leniently: every field is optional, and a few have two spellings,
// so the panel keeps working while the backend's payloads settle. README.md lists what the panel reads.
import { callable } from "@decky/api";

export type RookState =
  | "resting" | "ready" | "listening" | "transcribing" | "thinking" | "speaking" | "waiting" | "error" | "dark" | "away";

export interface Activity {
  kind?: string;
  label?: string;
  detail?: string;
  icon?: string;
  turn?: string | number;
}

export type CardOption = string | { label?: string; value?: string; id?: string };

export interface Card {
  id: string;
  desk?: boolean;  // A question with options: answered at the desk in this release, as on the phone.
  live?: boolean;
  tool?: string;
  title?: string;
  question?: string;
  options?: CardOption[];
  state?: string;
}

export interface Exchange {
  id?: string | number;
  turn?: string | number;
  request?: string;
  text?: string;
  answer?: string | null;
  state?: string;
  at?: number;
  source?: string;
  error?: string | null;
  activity?: Activity[];
}

export const OVERLAY_ANCHORS = ["middle-right", "middle-left", "top-right", "top-left", "bottom-center"] as const;

export interface OverlayStatus {
  anchor?: string | null;
  others?: string[];
  running?: boolean;
  mode?: string | null;
  error?: string | null;
}

// The WoW AddOns folder on the Deck (Rook's notes go there, and the WoW mode reads the add-on's files there).
export interface AddonsStatus {
  path?: string | null;
  found?: boolean;
  exists?: boolean;
  ok?: boolean;
  writable?: boolean;
  addon?: boolean;  // The WoWFriend add-on is in the folder.
  error?: string | null;
  note?: string | null;
}

export interface Status {
  paired?: boolean;
  connected?: boolean;
  server_url?: string | null;
  device?: string | null;
  state?: RookState | string;
  talking?: boolean;
  hotkey?: string | null;
  hotkeys?: string[];
  card?: Card | null;
  draft?: string | null;
  error?: string | null;
  overlay?: OverlayStatus | null;
  addons_dir?: string | null;
  addons?: AddonsStatus | null;
  wow?: { addons_dir?: string | null; wowfriend?: boolean; slots?: boolean } | null;
  hotkey_active?: string | null;
  overlay_position?: string | null;
  version?: string;
}

// A result from a callable that does something: {ok, error}. A bare true/false or nothing also counts.
export type Result = { ok?: boolean; error?: string | null; [key: string]: unknown } | boolean | null | undefined;

// Backend -> frontend, as decky.emit("rook_event", {...}).
export interface RookEvent {
  type: "state" | "activity" | "draft" | "answer" | "card" | "error" | "chat" | string;
  state?: string;
  connected?: boolean;
  paired?: boolean;
  talking?: boolean;
  turn?: string | number;
  kind?: string;
  label?: string;
  detail?: string;
  icon?: string;
  text?: string | null;
  answer?: string;
  request?: string;
  message?: string;
  error?: string;
  card?: Card | null;
  id?: string;
  question?: string;
  options?: CardOption[];
  tool?: string;
  sender?: string;
  channel?: string;
}

export const getStatus = callable<[], Status>("get_status");
export const pair = callable<[server_url: string, code: string], Result>("pair");
export const unpair = callable<[], Result>("unpair");
export const talkStart = callable<[], Result>("talk_start");
export const talkStop = callable<[], Result>("talk_stop");
export const sendText = callable<[text: string], Result>("send_text");
export const stop = callable<[], Result>("stop");
export const getHistory = callable<[], Exchange[] | { items?: Exchange[]; history?: Exchange[] }>("get_history");
export const getDeckToken = callable<[], string | { token?: string; url?: string }>("get_deck_token");
export const setHotkey = callable<[chord: string], Result>("set_hotkey");
export const setOverlayPosition = callable<[anchor: string], Result>("set_overlay_position");
export const setAddonsDir = callable<[path: string], Result>("set_addons_dir");
export const answerCard = callable<[card_id: string, option: string], Result>("answer_card");

// What went wrong in a result, or null when it went through.
export function failure(r: Result): string | null {
  if (r === false) return "Rook did not take that.";
  if (r && typeof r === "object") {
    if (r.error) return String(r.error);
    if (r.ok === false) return "Rook did not take that.";
  }
  return null;
}

export function optionValue(o: CardOption): string {
  return typeof o === "string" ? o : String(o.value ?? o.id ?? o.label ?? "");
}

export function optionLabel(o: CardOption): string {
  return typeof o === "string" ? o : String(o.label ?? o.value ?? o.id ?? "");
}
