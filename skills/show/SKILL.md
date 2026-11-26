---
name: show
description: Show ⟦owner⟧ a picture or a video in Rook's media viewer, where the swarm opens a frame in the middle of ⟦his⟧ screen. Use when ⟦owner⟧ asks to see an image, a render, a screenshot, a chart, or a video clip, from this machine or from another one, or when a thread's message hands you media meant for ⟦him⟧.
when_to_use: Trigger phrases include "show me", "let me see it", "pull up that image", "put the render on screen", "play the clip", "grab the picture from Fable", "close the picture", "close that". A picture or video that a thread made counts too, when ⟦owner⟧ asks to see it.
allowed-tools: Bash(/usr/bin/python ${CLAUDE_SKILL_DIR}/../../desktop/relay.py show *)
---

# Showing media

The relay script is `${CLAUDE_SKILL_DIR}/../../desktop/relay.py`. Run it with `/usr/bin/python`.

- `relay.py show /full/path/file.png --title "A few words"` shows a file on this machine.
- `relay.py show /full/path/file.mp4 --title "A few words" --machine <machine>` copies a file from another machine first. Rook keeps the copy in memory and removes it when the viewer closes.
- `relay.py show --close` closes the viewer.

It shows PNG, JPEG, WebP and GIF pictures, animated or not, and video such as MP4 and WebM, with sound. The command prints `Shown.`, or a plain sentence that says why the file was refused. A refused file moves nothing on screen.

## When

- Show media when ⟦owner⟧ asks to see it. Also show it when a thread's message hands you media and says it is for ⟦him⟧.
- Never show a screenshot of ⟦owner⟧'s own screen back to ⟦him⟧, and never show files ⟦he⟧ did not ask about.
- Show one thing at a time. A new show replaces the one open, so you can step through a few files when ⟦verb:he asks|they ask⟧.
- When you do not know the file's full path, find it first. On another machine, read the thread or run `ls` through the machine's route. Never guess a path.

## How

1. Run `relay.py show` with the full path and a title of two to five words, such as "Login page, dark mode". The title shows under the frame.
2. ⟦Owner⟧ can see it, so do not describe it. Say what a friend next to ⟦him⟧ would say: one short, real reaction with its reason, such as "I really like the texture on that." With nothing real to add, just say "Here it is." Name what it is only when ⟦he⟧ would not know, such as a file a thread sent: then one clause of context, not a description. Look at the file first when you have not seen it. Describe it only when ⟦verb:he asks|they ask⟧ what is in it.
3. When the command fails, say why in one sentence, in plain words.

⟦Owner⟧ closes the viewer with Escape or a click on the picture. For a video, a click or Space pauses it, and the small mark under the frame closes it. A video closes by itself when it ends. Close it yourself only when ⟦verb:he asks|they ask⟧.
