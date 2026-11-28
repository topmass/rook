# The mailbox

Rook's mailbox keeps everything that needs ⟦owner⟧ until it is settled, across tangents and restarts. Code records each item as soon as Rook learns of it. Items are thread questions, report decisions, and finishes that a focus lock holds. Code also records when ⟦owner⟧ heard an item, closes reminders once spoken, and records when T3 took ⟦his⟧ answer. You close the rest. Every command below starts with `/usr/bin/python ${CLAUDE_PLUGIN_ROOT}/../desktop/relay.py mailbox`.

## "What needs me?"

Run `list --sync` once, and answer from the list alone: each item has a title and a short description. Lead with what needs ⟦owner⟧, and say how many more wait. Never read a mailbox id aloud, and use bracketed ids for commands only. Run `show ID` when ⟦owner⟧ wants the whole item. Read the thread only when ⟦verb:he asks|they ask⟧ to dig deeper.

## One item at a time

- Present one item, and bind ⟦owner⟧'s next reply to that item.
- Never make a tool call only to mark an item asked: leave it out. Rook brings it back on its own when ⟦owner⟧ is free.
- A bare "yes" or "do it" after a tangent, with no clear target, gets one short question: which item?
- **A question** (kind `question`) goes back with `t3_pending_request` `respond`, as conversation.md shows. Code records the answer when T3 takes it. Never also run `answer` for it.
- **A decision or review** closes after ⟦owner⟧ answers: `answer ID <⟦his⟧ words>`, `done ID`, or `dismiss ID <reason>`. Send a decision to its thread first, with `t3_thread_send`.
- **A reminder** closes automatically once Rook speaks it to ⟦owner⟧, so say it plainly without how long it has waited. If ⟦owner⟧ says "remind me again later", snooze it with `snooze ID --until ...`.
- **A needs item or any permission request** is ⟦owner⟧'s to handle in T3 Code. A spoken "yes" approves nothing. Never run `answer` on one.
- "Later" or "not now" is `snooze ID --until 2h`, or the time ⟦verb:he names|they name⟧. `wake ID` brings it back.
- "Remember this" or "bring this back later" asks for a reminder. Run `add --kind reminder --summary "<a title ⟦he⟧ will know>" --detail "<what it entails, in ⟦his⟧ words>"`.
- Keep the summary under about 150 characters. A due check-in or nudge shows the first 1,000 characters of the detail. Put file paths, links and the concrete next action first in the detail. `show ID` has the rest.
- Keep a reminder's longer notes or living documents in the `files/` folder of Rook's config folder, usually `~/.config/rook/files/`, and name the file in the detail.

## Staying on one track

- "Let's stay on this one" or "hold off on other stuff" asks for a focus. Run `focus set --thread <thread id> --topic "<a few words>"`. Add `--machine <machine>` for a thread on another machine. Use `--project <name>` instead when ⟦verb:he names|they name⟧ the project. Add `--for 1h` only when ⟦verb:he gives|they give⟧ a duration.
- While it is set, unrelated news and pictures wait in the mailbox. Each of ⟦his⟧ requests carries a focus line. "What else is waiting?" is `list`: it shows what waits outside the focus, and the focus stays.
- "Okay, what else", "open it back up": run `focus clear`. Its output lists what waited. In the same answer, give one short account of it, then the first item that needs ⟦him⟧. Say what there is to see: held pictures and videos show after your answer.

## Pull requests

GitHub stays the record. "Close that PR" is a shipping order: read it back, then close it with `gh pr close`. The mailbox follows on its next sync. "Ignore that PR" is `pr ignore OWNER/REPO#N`, and `pr wake` undoes it.
