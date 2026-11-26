---
name: forge
description: Design and bake Rook's own animated icons and themes, as shaders, into ⟦owner⟧'s own theme packs. Use when ⟦owner⟧ asks for a new icon, a new thinking icon, a variation on one, or a whole new theme for Rook's presence.
when_to_use: Trigger phrases include "make me a new thinking icon", "design an icon for", "make a theme", "I want a new look for when you", "try another version of that icon", "use my theme".
allowed-tools: Bash(/usr/bin/python ${CLAUDE_SKILL_DIR}/../../desktop/relay.py forge *)
---

# The forge

The relay script is `${CLAUDE_SKILL_DIR}/../../desktop/relay.py`. Run it with `/usr/bin/python`.

⟦Owner⟧'s packs live in `~/.config/rook/themes/<theme>/`. Never edit Rook's own code or its built-in themes. A new pack builds on a built-in theme, Nova by default, and uses its palette and plasma helpers.

## Make an icon: two commands

1. Write the shader and create the icon in one call. Pipe the GLSL in:

   ```
   /usr/bin/python relay.py forge new nova-mine orbit --think <<'GLSL'
   vec4 icon(vec2 p, float t, int layer) { ... }
   GLSL
   ```

   - `p` runs from -1 to 1, y up. `t` is the loop's phase, 0 to 1. Return premultiplied colour.
   - Nova's helpers are ready to use: `plasma`, `orb`, `streak`, `glow`, `paint`, `over`, `fill`, `stroke`, `INK`, `INKW`, and the colours `VIOLET`, `PINK`, `CYAN` and `CORE`.
   - `--think` joins the thinking rotation. `--layers main,voice` adds a layer for the voice level.
2. Bake, check and preview:

   ```
   /usr/bin/python relay.py forge bake nova-mine orbit --show
   ```

   It prints the seam and edge checks and the preview paths. With `--show`, and only when both checks pass, it shows the loop to ⟦owner⟧ in the viewer.

## Rules

- **Seam:** a loop must close. Anything that moves uses whole turns of `t`, such as `TAU * t` or `fract(t * 2.0)`.
- **Edge:** keep shapes and glows inside about 85% of the cell, or the bake fails.
- **Failure:** when a check fails, fix the shader and run `new` again with the same names, then `bake` again. Say what you changed in one short sentence.
- **Before use:** let ⟦owner⟧ see it before it is used. When ⟦verb:he likes|they like⟧ it, run `relay.py set theme nova-mine`. To go back, run `relay.py set theme nova`.
- **Sketches:** to compare ideas, create two or three icons with plain names, such as `find_a` and `find_b`, then bake them with one `bake` call. Judge them by the taste skill, keep the winner, and say why it won.
- **Time:** a bake takes about half a minute. When other renders hold the shared lock, it waits for them and says so, which can take several minutes. Tell ⟦owner⟧ it will take a minute or more.
- **Scope:** bakes run headless, muted and offline. Write nowhere except the pack's own folder.
- `relay.py forge list` lists ⟦owner⟧'s packs and their icons.
