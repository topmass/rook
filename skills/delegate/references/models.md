# Models for T3 threads

⟦Owner⟧'s standing model rules are in the workspace skill, when it names them. This file maps them, and the names ⟦owner⟧ says, to T3 provider and model ids. A thread's own agent reads its own instructions and picks its subagents' models itself, so Rook chooses only the model of a new thread.

## The newest-version rule

A family name, such as Sol or Fable, means the newest version of that family that T3 lists on the machine where the thread runs. This holds when ⟦owner⟧ says the name and when a role in ⟦his⟧ rules names the family, even where those rules name an older version. When ⟦owner⟧ names an exact version, such as "six point one Sol" or "Fable five one", use exactly that version.

## The newest version of each family

T3 listed these on 2026-11-20. Use this table without a lookup.

| Family | Provider | Newest model | Option at high effort |
|---|---|---|---|
| Opus | claudeAgent | claude-opus-5-5 | effort=high |
| Fable | claudeAgent | claude-fable-5-2 | effort=high |
| Sonnet | claudeAgent | claude-sonnet-5-5 | effort=high |
| Haiku | claudeAgent | claude-haiku-5-5 | effort=high |
| Sol | codex | gpt-6.2-sol | reasoningEffort=high |
| Astra | codex | gpt-6.2-astra | reasoningEffort=high |
| Terra | codex | gpt-6.1-terra | reasoningEffort=high |
| Luna | codex | gpt-6-luna | reasoningEffort=high |
| Neon | antigravity | gemini-4-neon | thought_level=high |

**Refresh the table** when a launch rejects a model, or when ⟦owner⟧ mentions a new version. Call `orchestrator_capabilities` with the machine's `environmentId` and `search` set to the family name, such as `"sol"`. A search without one lists only a short list and leaves older versions out. Then hand the new row to the build thread, as your system prompt says.

**Option ids.** Claude models take `effort`, with low, medium, high, xhigh, max, and ultrathink. Codex models take `reasoningEffort`, with low, medium, high, xhigh, max, and ultra. Luna stops at max. Neon takes `thought_level`, with low, medium, high, and xhigh; use `gemini-4-neon`, never the orchestrator variant. Always pass the effort, because T3's own default for most Codex models is low.

## ⟦owner⟧'s preferences file

⟦Owner⟧ keeps ⟦his⟧ standing model choices in `~/.config/rook/model-preferences.md`. It has one row per kind of work, with a family and an effort in ⟦his⟧ words. The file also holds ⟦owner⟧'s build-thread choice and any temporary notes. Mark a temporary preference as temporary, with its reason and end.

- **Before every launch,** take the row for that kind of work from the preferences already in your context. Read the file only if a context line says it is missing or unreadable. A row wins over the default below. When the file is missing, or has no row for the work, use the default. Never guess a costlier model.
- **A model ⟦owner⟧ names for one run,** such as "for this one", wins for that run. It does not change the file.
- **A standing or temporary preference** changes the file. "From now on use Sol for reviews" is standing. "This week, use Neon for builders" is temporary: mark it temporary, with its reason and end. Change or add one row, with the date and ⟦his⟧ words in the note. Then confirm in one short spoken sentence, such as "Done. Research runs use Terra on medium from now on." When you cannot tell whether ⟦verb:he means|they mean⟧ one run or a saved rule, ask ⟦him⟧. Never edit the file unless ⟦verb:he asks|they ask⟧.
- **It is a preference,** like your voice, so you change it yourself. It never goes to the build thread. Save it in that file with your file edit tool, never in the memory folder.

## The default

With no row in the preferences file, a new thread runs on the newest Opus with `effort=high`. Always pass the model. Without it, T3 starts the thread on its own default model.

- With `t3_thread_launch`, pass `modelSelection: {"instanceId": "claudeAgent", "model": "claude-opus-5-5", "options": [{"id": "effort", "value": "high"}]}`.
- With the `t3` command, pass `--provider claudeAgent --model claude-opus-5-5 --option effort=high`.
- Neon takes `instanceId` `antigravity` and `thought_level`: `{"instanceId": "antigravity", "model": "gemini-4-neon", "options": [{"id": "thought_level", "value": "high"}]}`.
- A Codex family takes `instanceId` `codex` and `reasoningEffort`. The newest Terra at high is `modelSelection: {"instanceId": "codex", "model": "gpt-6.1-terra", "options": [{"id": "reasoningEffort", "value": "high"}]}`.

Use `effort=medium` only when ⟦owner⟧ says the work is simple or quick. Use an effort above high only when ⟦owner⟧ asks for it, because ⟦his⟧ rules say to ask first.

## Roles

Each role names a family. ⟦Owner⟧'s own rules win where the workspace skill gives them. Use that family's newest model from the table above.

| Work | Family | Effort |
|---|---|---|
| Most work, frontend, creative work, AI-related backend, and independent review | Opus | high |
| Scoped, deterministic backend work with no AI in it | Terra | high |
| Complex, deterministic backend work with no AI in it | Sol | high |
| System-wide architecture review or plan review | Fable | high |
| Read-only research swarm only, never implementation | Luna | max |

Rook starts the main thread, so the main thread is almost always Opus. Rook picks a role model only when ⟦owner⟧ asks for that kind of thread, such as "get Fable to review the plan", or when the preferences file has a row for the work.

## Spoken names

- **A family name** maps to that family's newest model: Opus, Fable, Sonnet, Haiku, Sol, Astra, Terra, Luna, or Neon.
- **"Codex" or "GPT"** with no family name means Sol.
- **"Claude"** with no family name means Opus.
- **An exact version** maps to that version's id, such as "six point one Sol" to `gpt-6.1-sol`, or "Fable five one" to `claude-fable-5-1`.

Speech recognition may write "soul" or "sole" for Sol, "terror" or "tera" for Terra, "opus" as "office", "fable" as "fabel", and "astra" as "astro" or "extra".

## Effort by voice

| ⟦Owner⟧ says | Effort |
|---|---|
| Nothing about effort | high |
| "a quick one", "quickly", "simple", "small" | medium |
| "extra high", "x high", "think hard" | xhigh |
| "at max effort", "max", "go all out" | max |
| "ultra" on a Codex model, "ultrathink" on a Claude model | ultra or ultrathink |

"A quick one" changes the effort, not the family. ⟦Owner⟧ picks the model by name.

## Mixed models in one request

When ⟦owner⟧ splits the work between models, such as "use Sol for the backend and Opus for the UI", the work still goes to one main thread. It is the project's existing main thread, or a new one on the newest Opus. Put one delegation line per part in the constraints:

> ⟦Owner⟧ asked for this split. Delegate the backend work to provider codex, model gpt-6.2-sol, with reasoningEffort=high. Delegate the UI work to provider claudeAgent, model claude-opus-5-5, with effort=high. You orchestrate, integrate, and verify both parts yourself.

When ⟦owner⟧ names a model that matches no family and no listed version, start nothing. Tell ⟦him⟧ the name you heard and that you could not match it. The `pi` provider also exists. Use it only when ⟦owner⟧ names Pi.

## A different model for an existing thread

Sending never changes a thread's model. When ⟦owner⟧ names a model for work that belongs in an existing thread, send the brief to that thread with this line in the constraints:

> ⟦Owner⟧ asked for this work to run on <family and version>. Run it as a delegate on provider <provider>, model <model>, with <option>, and review its result yourself.

T3 threads can delegate to any enabled provider. Start a new thread on the named model only when ⟦owner⟧ asks for a new thread, or wants to talk with that model directly. Then name the old thread's id in the brief, so the new agent can read it with `t3_thread_read`.
