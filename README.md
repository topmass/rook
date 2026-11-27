<p align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/banner/banner-dark.webp"><img src="docs/banner/banner.webp" alt="Rook listens, thinks, then sends work to coding agents: T3 Code, Herdr, Claude Code, Codex, Antigravity and Pi" width="100%"></picture></p>

# Rook

**Coding agent:** to install Rook, follow https://raw.githubusercontent.com/topmass/rook/main/INSTALL.md step by step.

Rook is a voice assistant for your desktop. You hold a key, speak, and Rook answers out loud. A small swarm of particles on your screen shows what Rook is doing: listening, thinking, speaking, or drawing a diagram.

Rook runs on a coding agent that you already use: Claude Code, Codex, Antigravity, or Pi. It hands long work to your own agent threads in T3 Code or Herdr, follows them for you, and tells you when they need you.

## What Rook needs

- Linux with Hyprland. Rook is built and tested on Omarchy, an Arch setup with Hyprland. Other Linux desktops are not supported yet.
- Or an Apple Silicon Mac. The one-command install supports it. It is tested in a scratch home folder only, not on a fresh Mac yet.
- One agent CLI, installed and signed in: Claude Code (`claude`), Codex (`codex`), Antigravity (`agy`), or Pi (`pi`).
- A microphone and speakers.
- About 750 MB of disk for the speech models. The medium voice adds about 3.3 GB, or 2.5 GB on a Mac.
- For the medium voice: an NVIDIA card from the RTX 20 series on with 6 GB of graphics memory, or an Apple Silicon Mac with 16 GB of memory. Without one, Rook uses its small voice, which runs on the processor.

## Install

Paste this into your coding agent: "install Rook from https://github.com/topmass/rook". It follows [INSTALL.md](INSTALL.md) with you: the install, each permission and sign-in, and a check that every piece works, ending with your first spoken turn. Without an agent, run `curl -fsSL https://raw.githubusercontent.com/topmass/rook/main/install/get.sh | sh`, then `relay.py verify` as the install prints it, and fix each row it marks.

The installer picks the medium voice when this computer can run it. To keep the small voice, add `--voice small`. [INSTALL.md](INSTALL.md#models-and-licences) lists every model Rook downloads and its licence.

## First run

Once your coding agent has proved every piece, hold the talk key and say hello. The talk key is Right Control on Linux and Right Option on a Mac. On a new install, Rook then gets to know you by voice, in a few minutes, and saves only your preferences:

1. What to call you, which pronouns to use, and a name for Rook if you want one.
2. The key that wakes Rook.
3. Which coding tool gets Rook's background work (T3 Code, Herdr or Pi), and where your projects live.
4. How careful Rook's own agent is: careful, automatic, or full. Full is the default.
5. With T3 Code, a build thread that changes Rook's own code.
6. Whether Rook may take screenshots.
7. Rook's voice: it plays a few, and you pick one.

Rook changes nothing until it applies your choices. Say "skip" to take the default for a step, or "stop" to end setup with nothing changed. To try it without changes, say "do a dry run of setup". Say "run onboarding" any time to go through it again.

## Things to say

Hold the talk key, speak, and let go. Some examples:

- "Fix the failing test in this project." Rook hands the work to a T3 Code thread and follows it.
- "How is that going?" or "What needs me?" Rook reports on your threads.
- "Tell it yes." Rook answers a thread that waits for you.
- "Show me the render." Rook opens a picture or a video in its viewer.
- "Pause the video." or "Play the music." Rook controls your media players.
- "Change your voice." or "Talk a bit faster." Rook changes its own settings.
- "Go dark for an hour." Rook goes quiet, takes no screenshots, and holds its messages until it comes back.
- "Stop." Rook stops what it is saying.

Rook answers in short spoken sentences. It shows longer answers as text on the screen.

## What is yours and what ships

Rook ships the same base to everyone:

- the core prompts that steer Rook;
- the skills in `skills/` and the plugins in `plugins/`;
- a starter personality, `prompts/personality.md`. The installer copies it to `~/.config/rook/personality.md` once, when you have none.

Everything else is yours. It stays on your computer, and an update never changes it:

- `~/.config/rook/`: your personality, your model preferences, your own skills in `skills/`, and your machines in `machines.json`.
- `~/.local/share/rook/memory/`: Rook's memory of you.
- `~/.local/state/rook/`: your session state, such as the journal and the logs.

Edit your personality file to change how Rook talks. You can also tell Rook, such as "be more playful".

## Privacy

- **Speech to text runs on your computer.** Rook uses AirType, an offline recogniser, with Parakeet English or Parakeet multilingual (25 European languages). Your voice recording never leaves the machine.
- **Both voices run on your computer.** You can point the medium voice at a server of your own instead. Rook then sends the text it speaks to that server.
- **Your agent sees your request.** Rook sends the words you said to the agent you chose. With a spoken request, it also sends a screenshot of the focused window. That agent sends them to its own provider, such as Anthropic, OpenAI, or Google. Their terms apply.
- **Delegated work goes to your threads.** Rook sends briefs to your own T3 Code or Herdr threads, on machines you set up.
- **Rook's memory stays local.** Rook keeps its notes in `~/.local/share/rook/memory`. A nightly tidy reads them with your agent, so it uses your own model quota.
- Rook adds no permission layer of its own. Your agent's own permission mode decides what runs without asking.

## Contributing

Run `scripts/release-checks` before you send a change.

## Licence

Rook is released under the MIT licence. See [LICENSE](LICENSE). The speech models it downloads have their own licences, listed in [INSTALL.md](INSTALL.md#models-and-licences).
