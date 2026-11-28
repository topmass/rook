# Rook on the Steam Deck

A Decky Loader plugin that makes a Steam Deck a thin client for [Rook](../rook), the voice assistant that runs on the
PC. Rook's brain, memory and models stay on the PC; the Deck gives push-to-talk, spoken answers, Rook's presence and
text over the game, and (later) the WoW companion. Plan and contracts: `~/src/rook/docs/steamdeck-plan.md`.

## Parts

- **Backend** (`main.py`, `py_modules/rook_deck/`): pairs with Rook's phone server, records and sends speech, plays
  answers, reads the talk chord from the controller, serves the Deck agent API (`:47330`) and the overlay feed
  (`:47331`), and starts the overlay process.
- **Frontend** (`src/`): the Quick Access panel and the toasts.
- **Overlay** (`overlay/`): a transparent, click-through window over the game (gamescope's external overlay) that
  draws Rook's gold dust and the answer. See `overlay/README.md`.

## The Quick Access panel

Every control is a `@decky/ui` one, so the D-pad and A reach it; text fields open the Deck keyboard.

- **Status**: a small gold-dust presence (a 2D canvas after Rook's desktop dust: loop at rest, halo listening, lattice
  thinking, globe speaking, open ring waiting), Rook's state, the server and connection, overlay problems, errors.
- **Pairing** (when not paired): Rook's address (the phone server URL) and the 6-character code → `pair(url, code)`.
- **Talk**: *Hold to talk* (hold A on it, or a finger: `talk_start()` on press, `talk_stop()` on release; a short tap
  latches, press again to send), *Type a request* + *Send* (`send_text`), *Stop* (`stop`).
- **Waiting card**: what Rook asks, with Allow / Decline (`answer_card(id, "allow"|"decline")`); a desk-only card
  says to answer at the PC.
- **History**, newest first: the request, its activity lines with Rook's gold line icons (from the phone app's
  sprite), the answer (A expands it), plus the live turn's activity and draft.
- **Settings**: talk hotkey (`set_hotkey`, choices from `get_status().hotkeys`), overlay position (five anchors,
  default right below the minimap: `set_overlay_position`), the WoW AddOns folder with its
  WoWFriend status and a path field (`set_addons_dir`, empty = search again), the Deck agent token for the PC's
  `ROOK_DECK_TOKEN` (and `ROOK_DECK_URL`) (`get_deck_token`), Unpair (with a confirmation).
- **Toasts** while the panel is shut: answers, errors, a new waiting card, chat messages.

The frontend listens to `rook_event` (`{"type": "state"|"activity"|"draft"|"answer"|"card"|"error"|"chat", ...}`)
from plugin load, so toasts work with the panel closed, and re-reads `get_status()` / `get_history()` after changes
and every 5 s while the panel shows. Fields read leniently (see `src/api.ts`): status `paired, connected, server_url,
state, talking, hotkey, hotkey_active, hotkeys, card, draft, error, overlay{running,mode,error,others},
wow{addons_dir,wowfriend,slots}`; history items `turn|id, request|text, answer, state, at, error, activity[]`
(sorted newest first by `at`).

## Build

```sh
npx --yes pnpm@9 install
npx --yes pnpm@9 build        # rollup → dist/index.js
npx --yes pnpm@9 typecheck    # tsc --noEmit
```

`pnpm` runs through `npx` (no global install); the lockfile is pnpm 9's (`lockfileVersion: '9.0'`).

## Overlay screenshots (`overlay/screenshots/`, 1280×800, over a bright stand-in game frame)

- `page-middle-right-*.png` (the default anchor) and `page-bottom-center-*.png` – the overlay page in headless
  Chromium with WebGL (what the webengine renderer shows): listening, thinking, speaking (streaming), answer,
  waiting (with a draft), resting (nothing drawn).
- `native-middle-right-*.png`, `native-bottom-center-*.png` – the native cairo renderer's window (answer, waiting),
  read back from a nested headless gamescope and composited at its window position.
- `game-frame.png` – the stand-in frame, with a mock WoW data strip in the top-centre 1024×6 px.

All are checked to leave the strip and the middle third of the screen fully transparent.

## Verify on a real Deck

- The overlay shows over a game in Game Mode (the external-overlay compositing itself could not be seen in a nested
  headless gamescope here), and which renderer runs (`overlay.log`: webengine needs qmlscene + QtWebEngine on that
  SteamOS release; otherwise native). Its clash with the performance overlay.
- Hold-to-talk with A: whether Steam delivers `onButtonDown`/`onButtonUp` to the panel button (the tap-to-latch and
  click fallbacks cover it if not); the keyboard opening on the text fields; the hotkey from the back paddles.
- Toast look and timing; the panel's layout in the real Quick Access width.

## Licence

Rook is MIT (Copyright (c) 2026 topmass). The copied Rook files (`overlay/page/presence.js`, `forms.json`, the icons in
`src/icons.tsx`) keep that notice; see `overlay/page/LICENSE-rook.txt`. `LICENSE` is still the plugin template's
BSD-3-Clause text: put the plugin's own licence above it before publishing.
