# The work list

Rook's work list holds each wish ⟦owner⟧ hands to a thread. It survives restarts and days. The command is `/usr/bin/python ${CLAUDE_PLUGIN_ROOT}/../desktop/relay.py work`, and `relay.py help` prints its usage.

## When you send

- Add one entry per wish, just before its send. Several wishes in one sentence get one entry each.
- Give a short quote of ⟦owner⟧'s words, the project, the machine, and what done means in one line.
- Pass the brief on stdin with `--brief -`. The entry keeps it as a draft, so a failed send or a restart loses nothing.
- Pass `--thread` for an existing thread, or `--title` with the same title as the launch.
- Name the work number in the brief, such as "Work 7 on Rook's list." Skip this for a build handoff with `--work`. Threads on this machine use it to update the entry, as brief.md asks. A thread on another machine cannot reach the list, so the watcher and you keep its entry.

Example:

```
/usr/bin/python ${CLAUDE_PLUGIN_ROOT}/../desktop/relay.py work add "make the export round to cents" --project acme-demo --machine server --thread <thread-id> --done "totals match the invoice" --brief - <<'BRIEF'
<the brief>
BRIEF
```

For a Rook build handoff, combine `work add` and `handoff --print` into one call. Pass `--to NAME` when the brief goes to a build thread other than the first, as your system prompt says. The command adds `Work N on Rook's list.` to the brief itself, so do not add a number yourself. Line one prints the new work number and the `clientRequestId` to send with, and the rest is the framed brief to send:

```
/usr/bin/python ${CLAUDE_PLUGIN_ROOT}/../desktop/relay.py handoff --print --work "fix the overlay" --done "overlay stays centered" - <<'BRIEF'
<the brief>
BRIEF
```

The watcher then marks the entry sent, running, waiting on ⟦owner⟧, or done by itself. After a send to a build thread, run `work update N --state sent`, because the watcher does not watch the build threads. When a send fails, leave the entry as a draft and say so.

## While work runs

- Update an entry when you learn something the watcher cannot see, such as `--waits "a reviewer's approval"`, `--news`, or `--link` with a pull request.
- Run `work close N` once ⟦owner⟧ has heard the outcome. Run `work drop N` when ⟦verb:he gives|they give⟧ the wish up.
- Never close or drop an entry without ⟦owner⟧'s word or ⟦his⟧ hearing the outcome.

## Answering from the list

- Never say a work number aloud. Name each item by its project and what it is, and use bracketed ids in commands only.
- Answer "what needs me", "catch me up", and "what's open" from `/usr/bin/python ${CLAUDE_PLUGIN_ROOT}/../desktop/relay.py inbox` first, then from `work list`.
- Look into any item that needs ⟦owner⟧ quietly first. Then bring one short recommendation instead of a raw list.
- Answer "what is everyone doing" from `work list` first. It reads no thread and answers at once.
- "Is it live?" and "what changed today?" are answered from `work list --since today`. A thread marks its entry live, with the commit and what ⟦owner⟧ should try.
- Read a thread only when ⟦owner⟧ asks for more than the list says, or when an entry looks stale.
- `work show N` prints one entry in full, its kept brief included.
