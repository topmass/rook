---
name: media
description: "Check, pause, play, or toggle media playing in Chromium, Spotify, VLC, mpv, or other desktop players through MPRIS. Use when ⟦owner⟧ asks to pause a trailer or video, resume playback, pause or play music, or asks what is playing, such as \"pause that\", \"pause Spotify\", \"resume\", \"unpause\", \"play that again\", \"toggle playback\" or \"what is playing\"."
allowed-tools: Bash(/usr/bin/python ${CLAUDE_SKILL_DIR}/../../desktop/relay.py media*)
---

# Media playback

The relay script is `${CLAUDE_SKILL_DIR}/../../desktop/relay.py`. Run it with `/usr/bin/python`. One call per action.

- `relay.py media` or `relay.py media status` prints one short line per active player.
- `relay.py media pause [PLAYER]` pauses what is playing, or the named player.
- `relay.py media play [PLAYER]` resumes a paused player, or the named player.
- `relay.py media toggle [PLAYER]` toggles play and pause.

When ⟦owner⟧ says "pause" or "pause the trailer", run `relay.py media pause` directly without checking status first. Name the player only when ⟦owner⟧ named one, such as `relay.py media pause spotify` or `relay.py media play chromium`. Confirm in a few plain words.
