---
name: extend
description: Add a new skill to Rook's own skills folder for ⟦owner⟧. Use when ⟦owner⟧ asks Rook to learn a routine, keep the steps for a task, or make a skill.
when_to_use: Trigger phrases include "make a skill", "add a skill", "learn how to do this", "remember these steps".
---

# Adding a skill

1. Make the folder `$XDG_CONFIG_HOME/rook/skills/<name>/`. By default that is `~/.config/rook/skills/<name>/`. Use a short lowercase name with dashes.
2. Write `SKILL.md` in it. Start with front matter that holds `name` and a one-line `description` that says when to use the skill.
3. Keep the skill short and flat: a few plain steps, and no chain of reference files. Prefer a `relay.py` command to a new tool.
4. Never write into Rook's own code folders. Ask before you change a skill that is already there.
5. A new skill loads at the next restart, and you never restart yourself. Tell ⟦owner⟧ that it is saved and needs a restart.
