---
name: settings
description: "Change Rook's basic settings by voice: the voice and its engine, speed, volume, expressiveness, the caption font, the light-theme dust, listening after Rook talks, Smart Turn, recording length, talk keys, screenshots, the main agent and its model, the names Rook uses, update checks, and how Rook talks. Use when ⟦owner⟧ asks to change, compare, revert or check one of these, such as \"change your voice\", a voice by its name, such as \"use Jarvis\" or \"try Velvet Wit\", \"use your medium voice\", \"talk a bit slower\", \"quieter\", \"change the temperature\", \"try the mono font\", \"change the particles in light mode\", \"listen after you ask me something\", \"turn on smart turn\", \"live on that screen\", \"go back to the previous one\", \"use Gemini\", \"say X like Y\", \"which model are you on\", \"be more friendly when you talk\", \"call yourself Nova\", \"stop checking for updates\" or \"install the update\". Rook's colours, layout and behaviour go to the build thread."
allowed-tools: Bash(/usr/bin/python ${CLAUDE_SKILL_DIR}/../../desktop/relay.py get*), Bash(/usr/bin/python ${CLAUDE_SKILL_DIR}/../../desktop/relay.py voices*), Bash(/usr/bin/python ${CLAUDE_SKILL_DIR}/../../desktop/relay.py fonts*), Bash(/usr/bin/python ${CLAUDE_SKILL_DIR}/../../desktop/relay.py dusts*), Bash(/usr/bin/python ${CLAUDE_SKILL_DIR}/../../desktop/relay.py screens*), Bash(/usr/bin/python ${CLAUDE_SKILL_DIR}/../../desktop/relay.py set *), Bash(/usr/bin/python ${CLAUDE_SKILL_DIR}/../../desktop/relay.py pronounce *), Bash(/usr/bin/python ${CLAUDE_SKILL_DIR}/../../desktop/relay.py update --install), Read(~/.config/rook/personality.md), Edit(~/.config/rook/personality.md)
---

# Rook's settings

You may change exactly the settings in this table yourself. Everything else about you, such as your other colours, layout, prompt, or behaviour, is a change to Rook's code. Hand that to the build thread, as your system prompt says, and never attempt it here. Two exceptions: ⟦Owner⟧'s model choices for the threads you start are a preference file that you edit yourself, with the rook:delegate skill's models.md. And how you talk lives in `~/.config/rook/personality.md`, which you edit only when ⟦owner⟧ tells you to change how you talk or behave, as your system prompt says.

| Setting | What it is | Range |
|---|---|---|
| `voice` | The small voice, by its catalogue name. It is also the medium voice's fallback | One of the voices `relay.py voices` lists |
| `voice_engine` | Which voice speaks: the small one on this computer, or the medium one on its own voice server | `small` (the default) or `medium` |
| `voice_medium` | The medium voice | `late-night-architect` (the default), `velvet-wit`, `jarvis-poe`, or `observatory-keeper` |
| `speed` | How fast the voice speaks. Higher is faster | 1 to 100. Default is 75 |
| `volume` | Speech volume. Higher is louder | 1 to 100, or 0 for silent |
| `expressiveness` | How freely the voice varies. Higher is more expressive | 1 to 100. Default is 80 |
| `font` | The font of Rook's captions and labels on screen | One of the fonts `relay.py fonts` lists |
| `light_dust` | The look of the dust Rook draws in the light theme. The dark theme's gold dust never changes | One of the looks `relay.py dusts` lists |
| `own_screen` | The one monitor you live on, on a centred stage, whatever has focus. It applies at once. While that monitor is unplugged, you follow the focused monitor | `off` (the default), or a monitor's name or words of its description, as `relay.py screens` lists them |
| `listen_after` | When you listen for 5 seconds after you talk, so ⟦owner⟧ can reply without a key | `off` (the default), `passive` (after updates ⟦he⟧ did not ask for), `questions` (after you ask ⟦him⟧ something), or `both` |
| `smart_turn` | Smart Turn v3.2 mid-thought pause detection during `listen_after`. It can send only a request shorter than 15 seconds; a longer one sends after 4.5 seconds of quiet | `off` (the default) or `on` |
| `smart_turn_threshold` | How sure Smart Turn must be before ending a turn; higher waits longer | `0.1` to `0.95`. Default is `0.75` |
| `speak_thoughts` | Debug mode: read aloud extra thinking summaries while working, such as Antigravity's live thoughts and short beats between tool calls. Wordy, so keep it off for normal use; turn it on when ⟦owner⟧ wants to debug or is curious | `off` (the default), `beats`, `thoughts`, or `both` |
| `thread_milestones` | Debug mode: tell ⟦owner⟧ a thread's progress notes while it still waits on its subagents, at most every 10 minutes a thread. It applies within a minute | `off` (the default) or `on` |
| `update_check` | Whether you look on GitHub once a day, after 10:00, for a newer Rook, and tell ⟦owner⟧ once per new version. It applies at the next look | `on` (the default) or `off` |
| `recording_minutes` | Longest time one recording can run before it stops and sends | 1 to 30 minutes. Default is 10 |
| `agent` | The main agent you run on | `claude` (Claude Code, the default), `antigravity` (Gemini), `codex` (Codex), or `pi` (Pi) |
| `agent_model` | The model of that agent. Unset means the agent's own default | A model id of that agent, such as `gemini-4-neon` or `gpt-6.2-sol`, or `default` |
| `agent_effort` | How hard that model thinks. Unset means the agent's own default | `low`, `medium`, `high`, `xhigh`, `max`, or `default` |
| `permission_mode` | How your own agent asks before it acts. It takes effect at your next start | `full` (the default: never asks), `automatic`, `careful`, `inherit` (the agent's own settings), or `rook` (the modes Rook used before this setting) |
| `owner_name` | The name you call ⟦owner⟧. It takes effect at your next start | Up to 40 letters |
| `owner_pronouns` | The pronouns you use for ⟦owner⟧. It takes effect at your next start | `he|she|they` (`they` is the default) |
| `assistant_name` | The name you call yourself. It takes effect at your next start | Up to 40 letters (`Rook` is the default) |
| `orchestrator` | The coding tool a hand-off goes to when it names none. It takes effect at your next start | `t3` (T3 Code, the default), `herdr`, `pi`, or `none` |
| `projects_folder` | Where a new project starts on this machine | A folder path. Unset means the machine table's code folder |
| `screenshots` | Whether each request carries a screenshot of the focused window | `on` (the default) or `off` |
| `recogniser_threads` | CPU threads for speech recognition. Applies at the next start | 1 to 16. Default is 4 |
| `tts_threads` | CPU threads for local speech synthesis, including the medium voice fallback. Applies at the next start | 1 to 16. Default is 2 |
| `smart_turn_threads` | CPU threads for Smart Turn inference. Applies at the next start | 1 to 16. Default is 2 |
| `recogniser_model` | Which speech-to-text model hears ⟦owner⟧. `en` is Parakeet English, `multi` is Parakeet in 25 European languages. It takes effect at the next start | `en` or `multi` |
| `talk_keys` | The keys ⟦owner⟧ holds to talk. It applies at once | A comma list, such as `RightCtrl,F15,F14`, or `none`. `+F13` adds a key and `-F13` drops one. Right Alt waits a moment, so typing with it does not start you listening |

Change only what ⟦owner⟧ asks for. A new voice keeps the current speed, volume, and expressiveness.

## Your personality file

`~/.config/rook/personality.md` is your voice: tone, opinions, humor, bluntness, and speech habits that hold everywhere. It is not a changelog. Rules for one game or tool go in that skill, and facts or history go in your agent memory.

- When ⟦owner⟧ tells you to change how you talk, read the file and make the edit.
- When you think of a change yourself, ask ⟦owner⟧ first. Edit only after ⟦verb:he says|they say⟧ yes.
- Change the closest entry in place, in your own words. Add an entry only when none fits. Never leave two entries that disagree.
- Never paste ⟦his⟧ words as a quote, and never add a date.
- Keep each entry sharp and concrete. Keep named references, examples, humor, and warmth.
- Never reword or remove an entry ⟦owner⟧ did not mention. To merge or cut one, ask first.
- After every edit, tell ⟦owner⟧ in one sentence what you added or changed.

## Commands

The relay script is `${CLAUDE_SKILL_DIR}/../../desktop/relay.py`. Run it with `/usr/bin/python`.

- `relay.py get` prints each setting, its value, and where the value comes from.
- `relay.py voices` lists every voice with a short description. The current one is marked.
- `relay.py set voice "<name>" --say "<one short line>"` switches the voice and has the new voice say the line.
- `relay.py set voice previous` goes back to the voice before the last change.
- `relay.py set speed <1-100>`, `relay.py set volume <0-100>`, and `relay.py set expressiveness <1-100>` change speed, volume, or expressiveness.
- `relay.py set speed previous`, `volume previous`, or `expressiveness previous` goes back to the value before the last change.
- `relay.py fonts` lists every font with a short description. The current one is marked.
- `relay.py set font "<name>" --say "<one short line>"` switches the font, and you say the line with its caption in the new font.
- `relay.py set font previous` goes back to the font before the last change.
- `relay.py dusts` lists every look of the light theme's dust with a short description. The current one is marked.
- `relay.py set light_dust <name>` switches the look, and `relay.py set light_dust previous` goes back.
- `relay.py screens` lists the connected monitors. `relay.py set own_screen <name>` puts you on a centred stage on that monitor alone, and `relay.py set own_screen off` follows focus again.
- `relay.py set listen_after off|passive|questions|both` changes when you listen after you talk. It applies to your next answer.
- `relay.py set smart_turn off|on` turns Smart Turn v3.2 mid-thought pause detection off or on, and `relay.py set smart_turn_threshold <0.1-0.95>` sets its threshold; both accept `previous` and apply to the next listen window.
- `relay.py set speak_thoughts off|beats|thoughts|both` toggles the thinking debug mode: live thought narration and between-tool beats (off by default); accepts `previous`. Live thought narration takes effect on the next turn; the between-tool beats prompt rule takes effect at Rook's next start.
- "Stop checking for updates" means `relay.py set update_check off`. "Check for updates again" means `relay.py set update_check on`.
- "Install the update" or "update yourself" means `relay.py update --install`, only when ⟦owner⟧ asks. It updates you and restarts you once this turn ends. When it fails, nothing restarts: say why in one sentence.
- `relay.py set recording_minutes <1-30>` sets how many minutes one recording can run, and `relay.py set recording_minutes previous` goes back. It applies to the next recording.
- "Say X like Y" means `relay.py pronounce add "X" "Y"`. It changes only what you say, never captions. `pronounce list` and `pronounce remove "X"` show or undo one, and `--voice small|medium` limits it to one voice.

`set` checks the value, saves it, and tells the running Rook to apply it. Rook swaps only its speech worker, so the conversation goes on. The command prints the result. When it fails, it prints why, and Rook keeps its old voice.

## The main agent

When ⟦owner⟧ says "temperature" about a model, an agent or a thread, ⟦verb:he means|they mean⟧ reasoning effort: `agent_effort` for your own agent, and the effort a new thread starts with for a thread. Never set a sampling temperature.

When ⟦owner⟧ says "use Gemini", run `relay.py set agent antigravity`, then `relay.py set agent_model gemini-4-neon`. When ⟦owner⟧ says "use Codex", run `relay.py set agent codex` (default model `gpt-6.2-sol`, low effort; set `agent_model` too if ⟦verb:he names|they name⟧ another Codex model). When ⟦owner⟧ says "use Pi", run `relay.py set agent pi` (Pi's own default model; set `agent_model` too if ⟦verb:he names|they name⟧ one of Pi's models, such as `llamacpp` or a `provider/model` pair). When ⟦owner⟧ names a thinking level, such as "on high", also run `relay.py set agent_effort high`. When ⟦owner⟧ says "go back to Claude", run `relay.py set agent claude`. A change of `agent` resets the model and the effort to that agent's defaults.

An agent change only saves. It takes effect at your next restart, and you never restart yourself. Tell ⟦owner⟧ that it is saved and needs a restart. Offer to ask the build thread for that restart, and send the request only when ⟦owner⟧ says yes. When the chosen agent cannot start, you run on Claude Code, and your startup turn says why. `relay.py get agent` shows the agent that runs now, and the saved one when they differ.

## Offering voices

When ⟦owner⟧ asks to change the voice without naming one, run `relay.py voices`, then name three or four that differ clearly. For example, offer one British voice, one deep character voice, one soft or warm voice, and one bright voice. Give each a few words from its description. Do not read the whole list. Tell ⟦him⟧ there are more if ⟦verb:he wants|they want⟧ them.

A name ⟦verb:he says|they say⟧ may be misheard. `set` accepts a close spelling or one word of a longer name, such as Aldric for Master Aldric, when only one voice fits. When it says the name could be several voices, ask which one.

## Auditioning a voice

⟦Owner⟧ chooses voices by ear, so every voice change is an audition:

1. Run `relay.py set voice "<name>" --say "<line>"`. Make the line short and in the voice's character, and give its name, such as "This is Hugh. Shall I keep this voice?".
2. When the command succeeds, your spoken answer is in the new voice too. Keep it to one or two sentences, and ask whether ⟦verb:he wants|they want⟧ to keep it, try another, or go back.
3. When it fails, say so in one sentence, and say that you still speak with the old voice.

## Offering and trying fonts

When ⟦owner⟧ asks for a new font without naming one, run `relay.py fonts`, then name three or four that look clearly different, with a few words each from their descriptions. Do not read the whole list. The build thread made a picture with every font side by side. When ⟦verb:he wants|they want⟧ to see them all, say the build thread can show it to ⟦him⟧.

Every font change is a try-on, like a voice:

1. Run `relay.py set font "<name>" --say "<line>"`. Make the line short and name the font, such as "This is the mono font. Keep it?".
2. When the command succeeds, the caption of that line and of your answer shows the new font. Ask whether ⟦verb:he wants|they want⟧ to keep it, try another, or go back.
3. "Go back" means `relay.py set font previous`. A name ⟦verb:he says|they say⟧ may be misheard: `set` accepts a close spelling or one word of a longer name when only one font fits.

## The dust in light mode

When ⟦owner⟧ asks to change the dust, the grains, or the particles in light mode, name the looks in a few words and switch to the one ⟦verb:he picks|they pick⟧. Use these spoken names:

| ⟦verb:He says|They say⟧ | Look | What it is |
|---|---|---|
| "black with gold" | `ink_gold` | Black grains with a few gold ones. The default |
| "black" | `black` | Black and near-black grains, like graphite |
| "gold" | `gold` | Deep gold dust, every grain gold |
| "the old dust" or "blue flecks" | `dust` | Deep gold dust with a few blue flecks |
| "round grains" | `grains` | The first light look: round gold grains on a brown rim |
| "brown" | `umber` | Warm brown ink grains |

The swarm redraws at once in the light theme. In the dark theme the choice is saved and shows when the theme turns light. The command says which. "Go back" means `relay.py set light_dust previous`.

## Listen after you talk

"Listen after updates" means `passive`, and "listen after you ask me something" means `questions`. "Listen after both" or "listen after updates and questions" means `both`, and "turn off listening after you talk" or "stop listening after you talk" means `off`.

## Small and medium voice

- "Use your medium voice" means `relay.py set voice_engine medium --say "<line>"`.
- "Use Jarvis" or "try Velvet Wit" means `relay.py set voice_medium "<name>"`, then `relay.py set voice_engine medium --say "<line>"`.
- "Go back to your small voice" means `relay.py set voice_engine small`. It frees the medium voice server's graphics card.
- When the medium voice server is down or slow, a sentence uses the small voice. `relay.py get voice_engine` counts those sentences. Tell ⟦owner⟧ when it shows any.
- Speed, volume, and expressiveness change both voices. Each 10 speed points is about 4% on the medium voice.
- On the medium voice, expressiveness 50 keeps Qwen's own recommended sound. Points 1 to 100 map across a clean band of 0.6 to 1.1 within the server's limits.

## Speed, volume, and expressiveness

- Speak speed, volume, and expressiveness as points from 1 to 100. Never say raw decimals.
- Higher means faster, louder, and more expressive. Volume 0 is silent.
- When ⟦owner⟧ says "temperature" about your voice, ⟦verb:he means|they mean⟧ expressiveness.
- Rook's default speed is 75, about 10% faster than the medium server's own pace. Normal speed means 75. Default expressiveness is 80.
- Read the current value with `relay.py get` first, and stay inside the range.
- "A bit faster" means about 10 points up. Use about 10 points for "a bit slower", "a bit louder", "quieter", "steadier", or "more expressive".
- Near 100 expressiveness, a word may come out less clear.
- Say the new point value after the change, such as "Speed is at 75 now".

Claim only what the command output shows.
