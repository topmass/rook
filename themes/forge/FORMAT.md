# Theme packs

> **Checkpoint 10: one new state.** `write`: Rook edits or writes a file (the overlay's `Edit`, `Write` and
> `NotebookEdit` activities, which Devs already shows as its `quill` form). Nova shows `quill`, a plasma fountain pen
> writing a looping line. For the desktop player: `map_overlay_state` returns `"write"` for those three activities,
> and the fallback in `FlipbookPresence.set_state` covers every state a pack lacks, not only `find` (a pack with no
> `write` shows thinking). No field changed.
>
> **Checkpoint 9: one new state.** `find`: Rook searches for a file or text on the computer, or sets a waypoint in
> the game. Nova shows `find`, a crystal pylon that pings the ground. Devs shows its `prism` (its manifest gains
> `"find": "prism"` on the desktop branch, where the state is wired). No field changed.
>
> **Checkpoint 7: one new state, one new manifest field, and anchors.**
> - New state `search`: web search and web fetch (the overlay's `WebSearch` and `WebFetch` activities). Nova shows its
>   globe there, now with a turning dashed ring, a scan line and an orbiting spark; Devs shows `globe`. A state a pack
>   lacks falls back to `thinking`.
> - Nova's `speak` is new (checkpoint 8 replaced the checkpoint 7 mouth): a speech bubble of plasma, with layers
>   `main` (the bubble; `scale` 0.96 to 1.05), `glow` (its inner light; `opacity` 0 to 1 and the same `scale`) and
>   `wave` (a standing sound wave baked at full height; `stretch` 0.1 to 1, `opacity` 0.55 to 1, the same `scale`).
>   Every layer follows the `out` level, so a loud syllable is a tall, bright wave and a pause is a flat line. The
>   ranges suit the desktop's level, `min(1, level) ** 0.55`. The old speaking globe is now `search`.
> - `base` (new, user packs only): a pack in Rook's own themes folder may name a built-in theme it builds on. See
>   "User packs" below.
> - Anchors: the rest icon, and anything braided from it (an icon whose `intro.from` is rest, and that intro), sits at
>   the host's rest anchor; every other icon sits at the centre; each fades where it is. Nothing slides between them.
> - Transitional one-shots now play at 60 fps: `flash` is 20 frames and `dispatch_in` 18 frames, both at 60 fps.
>   Loops stay on twos (12 fps): that is their character. Read `frames` and `fps` from each icon's JSON.
>
> **Checkpoint 6 (the dispatch): `send` now means the dispatch, and four fields are new.**
> - `states.send` is `"dispatch"` in Nova. The cascade stays in the pack for other uses; no state names it.
> - `icons.<icon>.intro`: `{"icon": <one-shot>, "from": <icon>}`. Changing from `from` to this icon plays the
>   one-shot first (Nova: `dispatch_in`, the rest tube braiding itself), then hands over to this icon's first frame
>   with no crossfade; changing back to `from` plays the one-shot backwards. See "Intros" below.
> - `icons.<icon>.tips`: `{<layer>: {"at": [x, y], "side": 1 or -1}}`. A tip layer is shown only while its side is
>   sending, at the sending level (0 to 1); `at` is the point in the cell where that side's strands start.
> - `icons.<icon>.sprite: true`: a small icon a player draws along a path, turned to the path's tangent (its art
>   points along +x). Nova's `strand_head` is the head of a send's strand.
> - One-shots (`loop: false`) are now baked with t from 0 to 1 inclusive, so their last frame is exactly their end.
>
> **Checkpoint 5: two optional fields added to `transition`.** `flash_at` (seconds after the change when the flash
> starts; default 0) and `flash_scale` (the flash's size against the icon's; default 1). The crossfade now eases in
> and out (cubic), not out only. Nova: `seconds` 0.45, `flash_at` 0.08, `flash_scale` 0.8. Nova's star and synapse
> are now 36 frames and the board 48; read `frames` from each icon's JSON.
>
> **Checkpoint 4: no field changed.** Nova's rook is now 60 frames (one full turn per 5 s loop) and the flash 8
> frames at 24 fps; read `frames` and `fps` from each icon's JSON, never assume them. Every cell's outer band
> (beyond 86% of its half-width from the centre, on either axis) is now empty by rule: `bake.py` fails if anything
> shows there, so a player may crop or pack cells without a visible edge.
>
> **Changed at checkpoint 3 (format stays 1, the fields below are current):**
> - Atlases may be WebP (`"image": "baked/<icon>.webp"`); Nova's are WebP now, at 256 px cells. GdkPixbuf
>   reads WebP and AVIF, and so does every browser.
> - Voice reactions moved from `states` into each icon's own `voice` entry, and gained `stretch` (height only).
> - A state names the level that drives it: `"level": "in"` (the owner's voice) or `"out"` (Rook's own speech).
> - A state may take a `cycle` of icons, the next one each time the state begins (listening: orb, then helix).
> - An icon may have a `label` place, where the player draws text (the thread a send goes to).
> - Thinking's `turn` is 3 seconds in Nova.

A theme is a folder, `themes/<name>/`, with a `manifest.json`. One presence plays any pack through the same
states, so Rook can switch themes without engine changes. `presence.js` is the reference player.

## The manifest

- `name`, `title`, `format` (1), and `kind`: `flipbook` or `points`. The kind is the pack's default; an icon may set
  its own.
- `palette`: named colours, for the stage and the panel to match the theme. Players use `ink` and `core` for labels.
- `cell` (pixels) and `defaults` (any icon field, such as `frames`, `fps`, `format`, `quality`) apply to every icon.
- `icons`: one entry per icon.
  - A **flipbook** icon has `src` (a GLSL file, see `prelude.glsl`), and optionally `frames` (24), `fps` (12),
    `layers` (`["main"]`), `pivot` ([0.5, 0.5]), `loop` (true), `cell`, `format` (`png` or `webp`) and `quality`.
    The bake adds `image`, `grid`, `bbox` and `alpha`.
  - A **points** icon has `form` (a point set: a form name the dust engine knows, or a JSON file of `[x, y, z, w]`
    rows), or `cycle` (a list of forms taken in turn), and optionally `spin` (radians per second about the
    vertical axis).
  - `think: true` puts an icon in the thinking rotation.
  - `voice`: how the icon reacts to a level, used only while its state has a `level`. For flipbooks, one entry per
    layer name: `{"opacity": [lo, hi], "scale": [lo, hi], "stretch": [lo, hi]}`, each mapped linearly from level 0
    to 1. `scale` is uniform about the pivot; `stretch` scales height only. A layer without an entry plays as is.
    For points, `{"grains": <name>}` names the dust's own reaction.
  - `label`: `{"at": [x, y], "size": s}`, a place for one line of text. `at` is the text's centre in the cell, 0 to
    1 from the top left; `size` is the font height as a share of the drawn icon's size. Draw it in `palette.core`
    with an `palette.ink` edge about a quarter of the font height wide, so it reads on dark and on light; cut long
    text to about 22 characters. Fade it with the icon.
- `states`: what each of Rook's states shows. A value is an icon name, or an object:
  - `{"icon": <icon>}`, or `{"cycle": [<icon>, ...]}`: the next icon each time the state begins.
  - `"level": "in"` or `"out"`: the state's icons react to a level (see `voice`). `in` is the owner's voice, `out` is
    Rook's own speech. The host feeds one level, 0 to 1, about 20 times a second.
  - `thinking` is `{"rook": <icon>, "turn": <seconds>}`. Thinking always alternates the rook with each `think`
    icon in turn: rook, A, rook, B, rook, C.
- `transition`: how one icon gives way to the next. Flipbooks: `seconds`, `from_scale`, `to_scale`, and an optional
  one-shot `flash` icon, drawn over both, starting `flash_at` seconds into the change at `flash_scale` of the icon's
  size. The crossfade eases in and out: `f < 0.5 ? 4f^3 : 1 - (2 - 2f)^3 / 2`. Points: `{"kind": "flight"}`, the grains fly to the next form.

The state names map to the overlay like this: `rest` is the home loop; `listening`, `transcribing`, `thinking`,
`speaking` and `error` are the overlay's own states; `waiting` is `permission`; `send` is the t3 send and hand-off
tools; `open` is media and the reading frame; `timer` is the timer tool; `find` is file search, search commands and WoW
waypoints, and a pack with no `find` state shows thinking. On the phone, `presence.js` maps moods and
kinds the same way (`thinking` with kind `sending` or `launching` is `send`, `showing` is `open`, `timing` is
`timer`; `dark` and `away` show `rest` dimmed).

## Text

An optional `text` block sets the overlay's lettering for the state labels (`label`), the thread names at the send
strands (`name`) and the spoken captions (`caption`). A pack without it keeps Rook's own lettering. Every key in it
has a default. Devs is the example:

- `font`: a `.ttf` or `.otf` file in the pack folder. Only a built-in pack may bring one, because the overlay's font
  engine parses it. It must be a regular file inside the pack, with no symlink on its path, of at most 2 MiB. Rook
  ignores `font` in a user pack.
- `family`: the font family to use (default `Noto Serif`, which Devs uses). A user pack may name a family Rook ships
  or one already on the system.
- `label`, `name`, `caption`: each takes `size` (px), `weight` (100 to 900), `case` (`upper`, `lower`, or as written;
  captions stay as written), `tracking` (letter spacing in em), `color` (a palette key or `#RRGGBB`) and `rim` (true
  for the rim below).
- `outline`: the thin edge outside each letter that keeps it legible over games: `color`, `width` (px), `alpha`.
- `rim`: a thin line just inside the outline: `color`, `width`, `alpha`.
- `reveal`: `spread` (grains spread sideways along a new label or name and settle into it as its letters fade in,
  then dissolve, in about 0.6 s) or `none`.

The lettering never has a plate, a pill or a blur. A bad font, a missing family or a bad block keeps Rook's own
lettering. It shows in the dark theme with the default font option; the light theme and a font chosen by voice keep
theirs. Thread names keep the words before a colon, or else whole words up to 22 characters and an ellipsis.

## Bytes

A baked atlas is a PNG or WebP with straight alpha, cells in rows, layer by layer, frame by frame: cell `k` is
`layer * frames + frame`, at column `k % grid[0]`, row `k // grid[0]`. A GL player uploads it premultiplied
(`UNPACK_PREMULTIPLY_ALPHA` or one multiply at load) and blends with `ONE, ONE_MINUS_SRC_ALPHA`. Every loop's last
frame leads into its first; `bake.py --seam` proves it. Nothing shows in a cell's outer band (see the top); every
bake checks it.

## Transitions at the display's rate

Everything transitional is smooth at the display's rate. A player computes the crossfade's opacity and scale from the
clock on every display frame (cubic ease in and out over `transition.seconds`), and plays the one-shots (`flash`,
intros) from their 60 fps atlases. Nothing transitional moves position. `presence.js` is the reference.

## What the desktop player on main must change (for the dust builder)

1. **Anchors, which end the infinity sliding from the top down to the middle.** Today `_draw_flipbook_gl` (and the
   Cairo path in `Scene.draw`) moves every quad to the rest height while `scene.home`, so when `home` flips, the
   fading rest loop drops 164 px. Instead, `FlipbookPresence.draw_list(now, level, rest_dy)` tags each quad with `dy`:
   `rest_dy` for the rest icon, any icon whose `intro.from` is the rest icon, and that intro; 0 for every other
   icon. The overlay passes `rest_dy = scene.rest_pad - scene.lift - ORB / 2` when `scene.lift > 0`, else 0, and
   draws each quad at `centre_y + q["dy"]`, instead of choosing one `cy_draw` for all quads.
2. **The flash's blend.** Draw it premultiplied over (`BlendFunc(1, 0x0303)`; Cairo `OPERATOR_OVER`), not additive:
   Nova's flash has ink edges that must darken, and additive blending washes it out on a light desktop.
3. **The frame rate during a change.** In `_pace`, before the rest checks, return `1000 / TICK_MS` while
   `scene.flipbook.changing(now)` is true: the previous icon is set and `now - cur_at` is under the longer of
   `transition.seconds` and `flash_at` plus the flash's duration, or an intro is playing. Otherwise a leftover
   `rest_idx` can hold a Nova change to 30 fps.
4. **The `search` state.** In `map_overlay_state`, return `"search"` when the activity is `WebSearch` or `WebFetch`.
   In `FlipbookPresence.pick`, a state missing from the pack's `states` falls back to `"thinking"`.
5. **Intros, tips and the dispatch** as in checkpoint 6 (`dispatch_in` braids the rest loop; see "Intros").
6. **User packs.** `list_packs` also lists the packs in Rook's own themes folder (`$XDG_CONFIG_HOME/rook/themes`,
   by default under `.config` in the home folder), so `relay.py set theme <name>` accepts them. `load_pack` loads a
   pack with `base` by loading the base (a repo theme) first, then laying the user's `icons` and `states` over it
   (the user's entries win), and keeping the base's `palette` unless the user gives one. It resolves each icon's
   `_image_path` against the folder that icon came from. A user icon with `think: true` joins the thinking rotation.

## User packs

Rook makes its own icons and themes with `themes/forge/forge.py` (the `forge` skill, `skills/forge`), and
never edits the repo. Its packs live in `$XDG_CONFIG_HOME/rook/themes/<name>/`: a `manifest.json` with
`"base": "nova"` (or another built-in theme), `icons/<icon>.glsl`, and the bake's `baked/`, `pack.js` and
`previews/`. `bake.py` finds a theme in the repo first, then in that folder, and compiles a user pack's shaders with
its base's `common.glsl`.

To register the forge skill:
- **Claude Code:** add `relay.py forge`, which runs `themes/forge/forge.py` with the same arguments and standard
  input. The skill's `allowed-tools` line already names it. Add one line to Rook's prompt in `rook.py`: "To design a
  new icon or theme, use the rook:forge skill."
- **Antigravity:** add `"forge "` to `RELAY_SKILLS` in `desktop/agy_harness.py`. Its `check()` asserts that the list
  equals the skills' `allowed-tools` lines, so the check fails until it is added. `antigravity_home.skills()` renders
  `skills/forge` with no text changes.

## Intros

A change into an icon with an `intro`, from the intro's `from` icon, runs in three steps:

1. The one-shot starts at once, at full strength, under the old icon, which fades out over 0.12 s (no scale, no
   flash). Its first frame is the old icon's shape, so nothing dips or pops.
2. When the one-shot ends, the target icon starts at its first frame, with no crossfade: the one-shot's last frame is
   the same image (to within 3 of 255 in a handful of pixels, from float rounding).
3. Going back to `from`, the one-shot plays backwards under the target as it fades over 0.15 s, then `from` takes
   over the same way.

`Presence.change` and `Presence.draw` in `presence.js` are the reference.

## The dispatch (sending to threads)

`stage/dispatch.md` on branch `t3/stage` holds the timing, rows, curves, type and marks. A flipbook player adds:

- **The braid.** `dispatch` loops (36 frames at 12 fps) and is reached from `rest` through `dispatch_in` (8 frames
  at 24 fps). Its layers are `main`, `tip_r` and `tip_l`; the tips follow the sending sides.
- **Strands.** Each starts at its side's tip point (`tips.<layer>.at`, in the cell), not at the spec's `0.9 r`,
  because Nova's loop is narrower than the dust's. The strand body is drawn by the player as a Nova plasma line,
  scaled by `k` (drawn size / 140): a pink glow 7k wide at 16%, an ink underlay 3.4k wide at 55% (it carries the
  line on a light desktop), a violet-to-pink line 1.8k wide, and white beads (1.1k wide, 2.2k on, 9k off) marching
  toward the name, one pass every 2.4 s. While a strand travels, `strand_head` sits at its head, 30k across.
- **Outcome marks**, drawn as vectors (a bitmap would blur at 2 to 3 px), each with a thin ink rim for light
  desktops: no answer yet, a violet 2.1k dot breathing between alphas 0.45 and 0.8; landed, a filled pink 2.6k dot
  with a 14k four-point glint that fades over 0.5 s; did not land, an empty 3.4k ring with a 1.3k line in the quiet
  colour `#a08ce0`; cannot tell, three 1.6k grains 5k apart in the quiet colour.
- **Names**: IBM Plex Sans 600 at 21k, in `#ffafed` (core mixed 45% with pink), with a 1.7k ink edge and a light
  4k shade; "and N more" in regular weight and the quiet colour; project · machine under a single send, 11k, upper
  case, spaced 1.4k, in the quiet colour. The font must be available to the player (the phone app's
  `default-src 'none'` needs `font-src 'self'` and a served copy).
- **The phone layout** (one column under the presence) is in the spec but not built in `presence.js` yet.

`Presence.send`, `Presence.sendOutcome` and `Presence.drawDispatch` in `presence.js` are the reference.

## What the dust engine must provide for a points pack

1. A lookup from a form name, or a points file, to N points with weights: `_form_points` already does this.
2. One call to play an icon, `play(icon, params)`, taking the same `spin`, `voice` and `cycle` fields.
3. The state names above, resolved through the pack's `states` instead of `FORM_FOR_STATE`.
4. The thinking rule from the pack (`rook`, `turn`, the `think` icons) instead of the fixed lattice and rook pair.

## A desktop GL player for flipbooks

1. Load the pack's manifest and each atlas on first use (GdkPixbuf reads PNG and WebP); upload premultiplied,
   linear filtering, clamp to edge.
2. Keep only the current, the previous and the flash atlas on the GPU; free the rest.
3. Each frame, draw one quad per live layer (more during a change, plus the flash).
4. The vertex shader scales the quad about the pivot (`scale`, and `stretch` on height); the fragment shader picks
   the cell from a frame uniform.
5. Frame index: `floor(seconds * fps) % frames`, from the time the icon started; a one-shot holds its last frame.
6. Voice: per layer, opacity, scale and stretch from the level, when the state has a `level`.
7. Changes: ease in and out over `seconds`; the old icon fades and shrinks, the new one grows; play the flash on
   top once, from `flash_at`, at `flash_scale`.
8. Thinking and cycles: the same rules as `Presence.pick` in `presence.js`. Keep the old icon until the new
   atlas has loaded.
9. Labels: draw the text at the icon's `label` place, as above (Cairo on the desktop is fine).
10. The cost is one texture fetch per pixel of a 140 px quad, far below the dust's compute pass.
