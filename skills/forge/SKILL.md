---
name: forge
description: "Design Rook's own icons and themes into ⟦owner⟧'s own theme packs, as gold dust forms by default or as Nova shaders. Use when ⟦owner⟧ asks for a new icon, a new thinking icon, a variation on one, or a whole new theme for Rook's presence, such as \"make me a new thinking icon\", \"design an icon for\", \"make a theme\", \"I want a new look for when you\", \"try another version of that icon\" or \"use my theme\"."
allowed-tools: Bash(/usr/bin/python ${CLAUDE_SKILL_DIR}/../../desktop/relay.py forge *)
---

# The forge

The relay script is `${CLAUDE_SKILL_DIR}/../../desktop/relay.py`. Run it with `/usr/bin/python`.

⟦Owner⟧'s packs live in `~/.config/rook/themes/<theme>/`. Never edit Rook's own code or its built-in themes. A new pack builds on Devs, the gold dust, by default. Nova, the shader look, is the second choice.

## Make a dust icon: two commands

1. Pipe in a `show_scene` scene, in a 100 by 100 view, with no labels:

   ```
   /usr/bin/python relay.py forge new devs-mine lantern <<'JSON'
   {"name": "lantern", "parts": [{"id": "glass", "path": "M 33 39 C 24 52 24 66 33 79 M 67 39 C 76 52 76 66 67 79"},
    {"id": "flame", "ellipse": [50, 60, 5, 9], "fill": true, "lead": true}]}
   JSON
   ```

   - It becomes a flat form of 640 grains of Rook's own gold, drawn as a bold silhouette. It sways gently and never turns edge-on. `--spin` sets the sway's pace, 0.45 by default.
   - A dust form joins the thinking rotation only, first after the rook, at most four per pack. Rest, listening, speaking and sending stay Rook's own.
   - Hand-written rows also work: a JSON list of exactly 640 `[x, y, z]` rows in pixels, y down, z towards the eye, each within 62 of the centre.
2. `/usr/bin/python relay.py forge bake devs-mine lantern --show` renders, in about 5 seconds, the rest loop, the form assembling and swaying, and the return to rest, at real size. `--show` shows it to ⟦owner⟧.

## Dust rules

- A form assembles from the resting loop and returns to it: assemble, settle, act, rest.
- It reads at about 120 px, with a bold silhouette. Function shows in the form.
- One bright focal point: about a tenth of the grains at full brightness, the rest quieter. Mark that part `"lead": true`.
- No colours beyond the Devs gold.

## Make a Nova icon

For a new pack, add `--base nova --think` to `new` and pipe in GLSL: `vec4 icon(vec2 p, float t, int layer)`, `p` from -1 to 1, y up, `t` the loop's phase from 0 to 1, premultiplied colour out. Helpers: `plasma`, `orb`, `streak`, `glow`, `paint`, `over`, `fill`, `stroke`, `INK`, `INKW`, `VIOLET`, `PINK`, `CYAN`, `CORE`. Move by whole turns of `t` and stay inside about 85% of the cell, or the seam and edge checks fail.

## Rules

- **Failure:** fix it, run `new` again with the same names, then `bake`. Say what you changed in one short sentence.
- **Before use:** let ⟦owner⟧ see it first. When ⟦verb:he likes|they like⟧ it, run `relay.py set theme devs-mine`. To go back, run `relay.py set theme devs`.
- **Sketches:** create two or three icons with plain names, such as `find_a` and `find_b`, and bake them in one call. Judge them with the taste skill, keep one, and say why each other one lost.
- **Time:** a dust preview takes about 5 seconds. A Nova bake takes 1.5 to 9 minutes while it waits for other renders; tell ⟦owner⟧ first.
- **Scope:** bakes run headless, muted and offline. Write nowhere except the pack's own folder.
- `relay.py forge list` lists ⟦owner⟧'s packs and their icons.
