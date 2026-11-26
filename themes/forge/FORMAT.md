# Theme packs

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
  - A **points** icon has `form` (a form name the dust engine knows, or in a user pack a dust form file, see
    "User packs"), or `cycle` (a list of forms taken in turn), and optionally `spin` (radians per second about the
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
frame leads into its first; `bake.py --seam` proves it. Nothing shows in a cell's outer band, beyond 86% of its
half-width from the centre on either axis; every bake checks it.

## Transitions at the display's rate

Everything transitional is smooth at the display's rate. A player computes the crossfade's opacity and scale from the
clock on every display frame (cubic ease in and out over `transition.seconds`), and plays the one-shots (`flash`,
intros) from their 60 fps atlases. Nothing transitional moves position. `presence.js` is the reference.

## User packs

Rook makes its own icons and themes with `themes/forge/forge.py` (the `forge` skill, `skills/forge`, through
`relay.py forge`), and never edits the repo. Its packs live in `$XDG_CONFIG_HOME/rook/themes/<name>/`, and `relay.py
set theme <name>` accepts them. A user pack names a built-in theme as its `base`. The loader lays the user's `icons`
and `states` over the base's (the user's entries win) and keeps the base's `palette` unless the user gives one.

**Devs (the default): dust forms.** The manifest has `"kind": "points"` and `"base": "devs"`. Each icon is `{"form":
"forms/<icon>.json", "spin": 0.45, "think": true}`, and the form file is a JSON list of exactly 640 `[x, y, z]`
rows: one grain each, in logical pixels from the presence's centre, x right, y down, z towards the eye, each within
62 (the 124 px form box). The rows are the form's rest pose. The engine sways it about the vertical axis, at most
0.3 radians either way (`DATA_SWAY` in `desktop/overlay.py`), so a flat form never turns edge-on; `spin`, from -2 to
2, sets the sway's pace in radians per second. The built-in tilt and depth shading apply, and the springs fly the
grains in from the resting loop and back. The colour, the grain look and the grain count are Rook's own. A pack's
dust forms, at most 4, come first in the thinking rotation, right after the rook, and Devs' own thinking forms
follow; they take no other state. A form file that is missing, over 64 KB, outside the pack folder, not JSON, or not
640 rows of three plain numbers inside the box is refused in one sentence on the overlay's log, and thinking keeps
the built-in forms. `forge.py new` makes flat rows (z 0) from a render-tool scene, or takes rows written by hand; a
new pack's `--base` (devs by default) decides the kind, and an icon whose kind does not match its pack is refused.
`forge.py bake` renders a still and a 10.5 s loop with `dust_preview.py`, offscreen, in about 5 seconds.

**Nova (second choice): shader icons.** The manifest has `"kind": "flipbook"` and `"base": "nova"`,
`icons/<icon>.glsl`, and the bake's `baked/`, `pack.js` and `previews/`. `bake.py` finds a theme in the repo first,
then in that folder, and compiles a user pack's shaders with its base's `common.glsl`.

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
