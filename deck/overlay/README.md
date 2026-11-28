# Rook's in-game overlay

Rook's presence (gold dust) in the top-right corner of the game, the answer as it streams, and a pending chat draft.
It shows while Rook works, keeps an answer up long enough to read once, then fades out and unmaps its window.

## How it gets over the game

gamescope (SteamOS Game Mode) composites one extra X11 window on top of the game: a window on its Xwayland
(`DISPLAY=:0`) that carries the property `GAMESCOPE_EXTERNAL_OVERLAY` (CARDINAL 1). This is how mangoapp, Steam's
performance overlay, draws (gamescope `src/steamcompmgr.cpp`, `EXTERNAL_OVERLAY_PROP`; MangoHud `src/app/main.cpp`).
An empty XShape input region makes the window click- and touch-through. decky-overlay
(github.com/powange/decky-overlay, `renderer/renderer.py`) proves this works on stock SteamOS from a Decky plugin,
with the system `python3` and ctypes on `libX11`/`libXext`/`libcairo`.

Two renderers draw the same picture; `rook_overlay.py --mode auto` tries them in order:

1. **webengine** – loads `page/` (this folder's web page, with Rook's real WebGL dust from `phone/presence.js`) in a
   transparent frameless Qt Quick window, using a QML runtime already on the system: `qmlscene --transparent` with
   `qt5-webengine` (both in SteamOS 3.5's package list), or Qt 6's `qml` with `qt6-webengine`. Our process finds
   the host's window, checks it is 32-bit ARGB (really transparent), then tags it and empties its input shape. A
   window that is not ARGB is never tagged, so gamescope never shows it (no black box over the game), and we fall back.
2. **native** – `native.py`: an ARGB override-redirect window painted with cairo through ctypes. Needs only libX11,
   libXext and libcairo, which every SteamOS has. Simpler dust, same text and draft card.

WebKitGTK is not on SteamOS (and GTK alone has no web view), so a GTK web view was ruled out. Steam's own CEF can draw
over games too (Deckamine's route: a Decky global component plus a minimum composition-state request), but it relies
on Steam's internal React tree and keeps Steam's UI composited; the X11 atom is a stable gamescope interface.

Position: one of five anchors (`anchors.py`), the same in the page (`?anchor=`) and the native renderer. On a
1280×800 Deck:

| anchor | window x, y, w×h | |
| --- | --- | --- |
| `middle-right` (default) | 850, 264, 430×436 | below WoW's minimap, zone name and coordinates; over the quest tracker |
| `middle-left` | 0, 264, 430×436 | free outside a group; WoW's party frames sit here in a group |
| `top-right` | 850, 10, 430×560 | covers the minimap and the coordinates Rook's wow skill reads |
| `top-left` | 0, 10, 430×560 | covers the player and target frames |
| `bottom-center` | 380, 537, 520×190 | above the main action bars, presence beside the card |

Middle-right is the default: the minimap area must stay clear (Rook reads the coordinates under it), the quest
tracker matters less, and middle-left would cover the party frames exactly when party chat (Phase 5) is in use. Every
anchor keeps off the top 10 px (a WoW add-on draws a 1024×6 px data strip at the top centre) and off the middle third
of the screen each way.

**One external overlay at a time.** gamescope picks one external overlay window. While Steam's performance overlay
(mangoapp) is showing (level ≥ 1), it and Rook compete and only one shows; mangoapp unmaps itself at level 0. Other
Decky overlay plugins (decky-overlay / Decky Timer) compete the same way. `launcher.status()["others"]` lists other
mapped external overlays so the panel can say so.

## Interface for the backend (`launcher.py`)

```python
import importlib.util, os
spec = importlib.util.spec_from_file_location("rook_overlay_launcher",
                                              os.path.join(decky.DECKY_PLUGIN_DIR, "overlay", "launcher.py"))
launcher = importlib.util.module_from_spec(spec); spec.loader.exec_module(launcher)

launcher.start(url="http://127.0.0.1:47331/overlay", display=":0", xauthority=None, user="deck",
               mode="auto", log_path=".../overlay.log", geometry=None, parent_pid=None,
               anchor="middle-right")                                                  # -> status dict
launcher.stop(timeout=3.0)                                                                # -> status dict
launcher.status()  # {"running", "pid", "mode": "webengine"|"native"|None, "anchor", "error", "log", "others"}
launcher.ANCHORS   # ("middle-right", "middle-left", "top-right", "top-left", "bottom-center")
```

- `set_overlay_position(anchor)` in the backend: store the anchor, then `start(..., anchor=anchor)`; a changed anchor
  restarts the overlay there (the webengine page gets `?anchor=…&frame=window`). Report `status()["anchor"]` as
  `get_status().overlay.anchor`; the panel's dropdown reads it.
- Pure stdlib, Python 3.11, no `decky` import. Call `start()` once the overlay server listens; it is idempotent
  (same arguments: left alone) and kills a stale overlay from an earlier backend (`/tmp/rook-overlay/overlay.pid`).
- Runs `/usr/bin/python3 -u overlay/rook_overlay.py …` as `user` (root drops to it), with `DISPLAY`/`XAUTHORITY`
  (from the arguments, else from the user's running gamescope/Steam, else `:0`) and without Decky's
  `LD_LIBRARY_PATH`/`PYTHONHOME`/`PYTHONPATH`. The child exits by itself when `parent_pid` (default: the caller) is
  gone, or on SIGTERM.
- The child reads `url` (webengine) or `url + "/events"` (native) from the backend; the backend must serve
  `page/index.html` at `/overlay` and every file of `page/` at `/overlay/<name>` (the page loads
  `/overlay/overlay.css`, `/overlay/presence.js`, `/overlay/overlay.js`, `/overlay/forms.json`).
- SSE at `/overlay/events`: unnamed `data:` messages, each the whole picture:
  `{"state": "resting"|"listening"|"thinking"|"speaking"|"waiting", "text": str, "draft": str|null}`.
  `transcribing` and `error` are understood too. A stream down for 15 s counts as resting. An optional `"anchor"`
  field moves a full-screen page (`frame=screen`); a window-hosted page moves only by restarting the process.

By hand: `overlay/run.sh start|stop|status|restart` (env `ROOK_OVERLAY_MODE`, `ROOK_OVERLAY_URL`,
`ROOK_OVERLAY_DISPLAY`; log `/tmp/rook-overlay/overlay.log`).

## Files

- `launcher.py` – start/stop/status for the backend; `python3 launcher.py start|stop|status`.
- `run.sh` – the same from a shell.
- `rook_overlay.py` – the overlay process: picks a renderer, tags windows, follows the parent.
- `overlay.qml` – the Qt Quick window for the webengine renderer (filled in by `rook_overlay.py`).
- `native.py` – the cairo renderer and its SSE reader.
- `anchors.py` – the five anchors and their window rectangles.
- `xlib.py` – the ctypes Xlib calls (ARGB window, atoms, XShape input, window lookup).
- `page/` – the overlay web page: `index.html`, `overlay.css`, `overlay.js`; `presence.js` and `forms.json` copied
  from Rook's `phone/` (MIT, `page/LICENSE-rook.txt`; changes marked "Rook Deck:").
- `dev/fake_server.py` – a stand-in backend: serves `page/` and a cycling or fixed-scene SSE stream.
- `dev/screenshot.py` – renders `page/` headlessly at 1280×800 over a stand-in game frame and checks the strip and
  the centre stay untouched.
- `dev/x11_check.py` – runs the overlay process on an X display (a nested headless gamescope) and checks the window:
  32-bit, tagged, empty input shape, position, maps while Rook works and unmaps at rest, nothing left after stop.
- `dev/pyside_host.py` – a qmlscene stand-in (PySide6, via `ROOK_OVERLAY_QML_HOST`) to test `overlay.qml` off SteamOS.
- `screenshots/` – results (see the top-level README).

## Testing off the Deck

```sh
uv run --no-project overlay/dev/fake_server.py --port 47391 &
uv run --no-project --with playwright --with pillow overlay/dev/screenshot.py --port 47391 --anchor middle-right
gamescope --backend headless -W 1280 -H 800 -- \
  python3 overlay/dev/x11_check.py --game --mode native --events http://127.0.0.1:47391/overlay/events
ROOK_OVERLAY_QML_HOST="uv run --no-project --with PySide6 python overlay/dev/pyside_host.py" \
  gamescope --backend headless -W 1280 -H 800 -- \
  python3 overlay/dev/x11_check.py --game --mode webengine --url http://127.0.0.1:47391/overlay --events x
```

## Packaging

Decky's CLI packs `dist/`, `main.py`, `plugin.json`, `package.json`, `py_modules/`, `bin/` and `defaults/` (copied to
the plugin root). This folder must reach the plugin as `overlay/`: copy it in the package script (or keep a copy under
`defaults/overlay/`). Leave out `dev/` and `screenshots/` if size matters.
