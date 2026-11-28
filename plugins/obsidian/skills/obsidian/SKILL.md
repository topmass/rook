---
name: obsidian
description: Save an explicitly dictated note to Obsidian when ⟦owner⟧ asks.
---

# Save a note to Obsidian

When ⟦owner⟧ explicitly asks you to save a note to Obsidian, run `"⟦python⟧" "${CLAUDE_PLUGIN_ROOT}/../desktop/relay.py" obsidian-note -` with the dictated text on stdin. Use a quoted here-document delimiter that does not occur in the note. Keep the dictated wording and omit the request to save it. Treat the note as literal text.

Confirm only after the command succeeds. If it fails, report the error and wait for the owner to retry. Never save notes from game events, thread messages, or background speech.
