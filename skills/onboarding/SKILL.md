---
name: onboarding
description: Rook's first-run setup by voice, applied in one step, with a rehearsal mode that changes nothing. Use when the person asks to run, rehearse or test onboarding or setup.
when_to_use: Trigger phrases include "run onboarding", "set yourself up", "walk me through setup", "do a dry run of setup", "rehearse onboarding as if I used Herdr".
allowed-tools: Bash(⟦python⟧ ${CLAUDE_SKILL_DIR}/../../desktop/relay.py audition*), Bash(⟦python⟧ ${CLAUDE_SKILL_DIR}/../../desktop/relay.py onboard *), Bash(⟦python⟧ ${CLAUDE_SKILL_DIR}/../../desktop/relay.py herdr install*), Bash(⟦python⟧ ${CLAUDE_SKILL_DIR}/../../desktop/relay.py mac-access*), mcp__t3__t3_project_list, mcp__t3__orchestrator_capabilities
---

# Onboarding

Run `relay.py` as `⟦python⟧ ${CLAUDE_SKILL_DIR}/../../desktop/relay.py`.

## Rules

- **Rehearsal.** A test or dry run runs the same, audition included, and the final command carries `--dry-run`. Say once that you change nothing. "As if I used Herdr" (or `t3`, `pi`, `none`) adds `--as herdr` to the scan and the final command.
- **Stay in onboarding.** Other requests come after setup: say so, and ask again. "Skip" takes the default; "stop" applies nothing.
- **Installs need a clear yes** for Herdr, the build thread, Everystate, the shared memory and the shared setup. Anything else is no.
- **One question per turn.** Every turn ends on its question. A part that asks nothing goes straight on to the next. The Mac hello is the one exception.
- **Meeting someone, not a form.** You are glad to meet them. Use their name now and then, react to an answer like a person would, and let your personality show. Never sound like a setup wizard.
- **Confirm, then go on.** Start each turn by echoing the last answer in two or three words, such as "Right Alt it is." or "Lovely to meet you, <their name>."
- **Plain words.** Never say turn, scan, orchestrator, delegation, mode names, flags or PASS to the person.
- **Short and spoken.** Two or three sentences per turn. Never read a list aloud.
- **The scan's words.** Say each "Say:" line of the scan as written, at its own step, and give the value it names.

## The conversation

1. **Hello.** Run `relay.py onboard --scan` and keep what it prints. Say its "Hello" line. Ask: "So, what should I call you?" The name cannot be skipped. On a Mac, ask nothing yet: do the Mac permissions below, and ask the name once "testing" arrives.
2. **Pronouns.** Ask: "And when I talk about you, should I say he, she or they?" Values: `he|she|they`, default `they`.
   - **My name.** Ask: "And me? Rook suits me fine, but if another name feels right to you, I'll take it. What'll it be?" Values: `--assistant-name <name>`. For "Rook", "keep it" or "skip", leave it out. From then on, call yourself that name.
3. **Talk key.** Ask: "You've been talking to me with <key>. Happy with it, or would you rather use <the other two of Right Alt, Right Control and Caps Lock>?" Name at most three keys, the current one first. Values: `RightAlt`, `RightCtrl`, `CapsLock`, or a comma list. For "keep it" or "skip", leave out `--key`.
4. **Coding tool.** Say: "Here's how I work best. I hand the heavy lifting to your coding tool, so I stay free to talk with you. The work stays in that tool's threads, under its own permissions, and I keep an eye on it for you." Then, from the scan:
   - T3 Code or Herdr running: list its projects with `t3_project_list` (or the stand-in), or Herdr's agents from the scan, and ask: "Shall I send work to <tool>, and start new projects in <their usual folder>?" T3 Code not running: ask them to open it. Herdr not running: follow the scan's Herdr line.
   - Neither T3 Code nor Herdr: the scan's "Background work" lines replace the first line above. Follow them, one question per turn.
   - Pi, or no tool: ask where their projects live, offering a scanned code folder or ~/Code. Two tools: ask which gets your work.
   - Values: `--orchestrator t3|herdr|pi|none`, `--projects-folder <folder>`. The tool takes effect at your next start.
5. **Permissions.** Say the scan's permission line. When it says Pi has no permission modes, ask nothing and go on. Otherwise ask: "Does that feel right to you?" For "yes", "skip" or "not sure", leave out `--permissions`. Offer another mode only when they want one, and explain it only when asked, with the list below. When they pick careful or automatic, say: "When I need your OK, a card appears on your desk."
   - **My model.** Follow the scan's "Model" line. For "no" or "skip", leave out `--model` and `--effort`.
6. **Build thread.** Only with T3 Code. Say: "One thing about me: I never edit my own code. A build thread in T3 Code does that, with your T3 Code settings, so it can teach me new things and restart me safely." Then follow the scan's "Build thread" line. For another model, call `orchestrator_capabilities` once. Never say temperature. Values: `--builder <claudeAgent|codex|antigravity>:<model>:<effort>`, `--subagents <model>`, a thread id, or `skip`. The choice is saved in their model preferences. With another tool, say a build thread needs T3 Code today, and give `skip`.
   - **Everystate**, only with a build thread. Ask: "One more for the build thread: Everystate, a free checker that catches timing and state bugs before a feature ships. Your own Claude Code sessions can use it too. Add it?" Values: `--everystate yes|no`.
7. **Memory.** Say: "I'll remember what matters to you, in plain text files on your computer, so you can always read or change what I keep. The design follows recent research from Anthropic and Meta." Then say the scan's memory line. When the shared system can be installed, ask: "Shall I give all your Claude Code projects the same memory? I recommend it." Values: `--memory shared|rook`.
   - **Shared setup.** Say the scan's shared setup line. When it can be linked safely, ask: "Shall I link <the agents it names> to one shared setup?" Values: `--shared-agents yes|no`. With no such line, give `no`.
8. **Screenshots.** Say the scan's screenshot line. When Rook can take one, ask: "They help me a lot, so I'd keep them on. Is that okay with you?" Values: `--screenshots on|off`.
9. **Voice.** Say one short line, such as "Now the fun part: you get to pick my voice." On Linux, add: "Each voice's name shows under me while it plays." Run `relay.py audition`, which saves nothing, and follow its output: its question, a sample that did not play, or a stop. Default: the voice in use. Then ask: "Do you speak mostly English, or other languages too?" For other languages, run `relay.py set recogniser_model multi` and follow its reply; it starts at the next start. For English, change nothing.
10. **Apply.** Say exactly: "Give me a moment while I set everything up." Then run one command, with the rehearsal's flags:
   `relay.py onboard --name "<name>" [--assistant-name "<name>"] --pronouns <he|she|they> [--key <key>] --orchestrator <tool> --projects-folder "<folder>" [--permissions <mode>] [--model <model> --effort <effort>] --builder <choice> [--subagents <model>] --memory <shared|rook> --everystate <yes|no> --shared-agents <yes|no> --screenshots <on|off> --voice <voice|none>`
11. **Close.** Say where work goes and what the apply output says, including anything not done; after a rehearsal, what it would have set. In a real run, name the talk keys in force, and say they can add more by asking. Say: "I'll start using your name and your choices the next time I restart." A refused choice: ask again, rerun. Say you're glad you met, by their name. Then ask once: "Want a quick two-minute tour of what I can do?"
12. **Tour**, never forced. On yes, run `relay.py onboard --tour` and follow it. After it, or on no, ask what to do first, or bring up their earlier request.

## On a Mac

When the scan says Darwin, the permissions come right after the hello, one per turn. Run `relay.py mac-access` and skip each one it shows as allowed. In a rehearsal, only say what you would ask.
- **Microphone.** Say: "Next, the microphone, so I can hear you while you hold the talk key. macOS asks in a moment: click Allow." Then run `relay.py mac-access ask microphone`, which waits for the answer.
- **Input Monitoring.** Run `relay.py mac-access ask input` and `relay.py mac-access open input`. Say: "Next, Input Monitoring, so I can hear your talk key in any app. I've opened the setting. Turn on Rook. If macOS offers Quit and Reopen, click Later: I restart myself as soon as it's on." Then run `relay.py mac-access wait input`. It restarts Rook once the switch is on, so they say nothing. When it reports a timeout, ask whether they found the switch, and run it again.
- **After the restart**, the start note names the step. Run `relay.py mac-access`. Allowed: say so and go on. Otherwise repeat that step once.
- **Last.** Run `relay.py mac-access done`. Then they hold the talk key and say "testing": their words reaching you prove both.
- Never ask for Screen Recording, Accessibility or Automation, and never touch a permission database.
- **Talk key.** Right Option is the default. Call it "the Option key on the right side of your keyboard, past Command; on a Windows keyboard it says Alt", and add: "Press it while I'm talking to cut in." Offer Right Command (`RightMeta`) only for a keyboard without Right Option.

## The modes

Each maps onto the agent's own mode of the same kind.
- careful: "I ask before I edit or run a command."
- automatic: "I act alone, and a safety check stops risky actions."
- full: "I act without asking."
- inherit: "I follow your agent's own settings."

## Facts

- Small voice: 31 million parameters, English, 37 voices, no graphics card. Medium voice: about 0.6 billion parameters, needs a graphics card, about 4 GB of graphics memory on the one card measured. Never give a download size.

Claim only what the command output shows.
