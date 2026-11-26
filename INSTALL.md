# Installing Rook (for a coding agent)

This file is for a coding agent, such as Claude Code, Codex, Pi, or Antigravity, that a person asked to install Rook. Follow it in order.

A step marked **(by hand)** cannot be automated by the installer because it needs root access or an interactive account sign-in.

## One command

A person can also install Rook with one command, without an agent:

```sh
curl -fsSL https://raw.githubusercontent.com/topmass/rook/main/install/get.sh | sh
```

To install from somewhere else, such as a fork, a local checkout, or a `.tar.gz` URL, pass the source after `sh -s --`:

```sh
sh install/get.sh /path/to/rook
curl -fsSL <get.sh URL> | sh -s -- <git URL or .tar.gz URL>
```

`install/get.sh` needs `git`. It installs uv when it is missing and gets the code. Then it runs `install/install.sh` with the agent named by `--agent`, or else the first agent on `PATH` that runs, and says which one Rook will run on. It installs Rook with the medium voice when this computer can run it (else the small voice), both speech models, and the login service. When neither T3 Code nor Herdr is on `PATH`, it recommends T3 Code, and offers to install Herdr with Herdr's official installer (`https://herdr.dev/install.sh`). It asks on the terminal, and installs nothing without a yes. Then it starts Rook. Any `install/install.sh` option after the source replaces a default, for example `--agent codex` or `--dry-run`. The system packages, the `input` group, and the agent sign-in in steps 1 and 3 are still by hand. When a package or the agent is missing, the installer stops and prints the fix. Run the same command again after the fix. The installer does not stop for the `input` group or the agent sign-in: it prints a note, and the talk key works only after the next login. When the agent is not signed in, the last line says `Sign in first:` with the command to run. Until the talk key works, the person can type to Rook with the `relay.py ask` line it prints.

On an Apple Silicon Mac, use this one command. Steps 3 to 5 below are for Linux. The Mac needs the Command Line Tools first (`xcode-select --install`). The installer builds Rook.app, starts it with launchd, and prints the two permission commands to run.

### What is tested

- Linux on Omarchy: Rook is built and used there every day. `install/test_install_failures.sh` and `install/test_uninstall.sh` test the installer in a scratch folder.
- Mac: `install/get.sh` and `install/install.sh` are tested in a scratch home folder only. No one has run them on a fresh Mac yet.
- The Mac medium voice install is not tested on a Mac yet.

## Rules for you, the agent

- Do these steps in order, and finish each one before the next.
- Ask the person every question below, and wait for the answers before installing anything.
- Do not start other work until Rook is running, even when the person asks for it. Say it comes right after the install.
- Rook runs on Arch Linux with Hyprland (Omarchy), and on an Apple Silicon Mac. On another system, stop and say so.
- Never run `install/install.sh` or `install/uninstall.sh` as root, and never pass `-y` without asking the person first.
- Never print a token or a password.

## 1. Ask which agent Rook runs on

Ask: "Which agent should Rook run on: Claude Code, Codex, Pi, or Antigravity?"

All four work: **Claude Code** (`claude`), **Codex** (`codex`), **Pi** (`pi`), and **Antigravity** (`agy`).

Recommend one of these models for Rook:

- Claude Code with Claude Opus 5.5 (`claude-opus-5-5`) at medium effort.
- Antigravity with Gemini 4 Neon (`gemini-4-neon`) at medium effort.
- For Codex, Sol 6.2 (`gpt-6.2-sol`) at high effort.

Onboarding offers the same choice and saves it as `agent_model` and `agent_effort`.

The chosen agent must be installed and signed in **(by hand)**:

- Claude Code: `claude` on `PATH`, signed in with the command below. Claude Code's own installer (`curl -fsSL https://claude.ai/install.sh | bash`) puts it in `~/.local/bin`, which a new shell on Arch may not search. Then run `~/.local/bin/claude auth login`.
  ```sh
  claude auth login
  ```
- Codex: `codex` on `PATH`, signed in to Codex, plus a one-time T3 MCP sign-in:
  ```sh
  codex mcp login t3
  ```
- Antigravity: `agy` on `PATH`, signed in to a Google account in `agy` (run `agy` once and complete the Google sign-in prompt).
- Pi: `pi` on `PATH`, with a model set up in Pi, such as a signed-in provider or a local model. Pi has no permission modes, so Rook acts without asking under Pi. For T3's tools, sign in once while T3 Code runs, then restart Rook:
  ```sh
  ~/.local/share/rook/venv/bin/python ~/.local/share/rook/live/desktop/relay.py pi t3-login
  ```

## 2. Ask about the voice, model downloads, and login service before installing

Ask these three questions before running `install/install.sh`:

### Voice tier and small voice download

Say this, then ask:

> Rook's medium voice sounds much more natural, and I recommend it. It is a 600-million-parameter model (Qwen3-TTS 0.6B). On Linux it needs an NVIDIA card from the RTX 20 series on, with 6 GB of graphics memory and driver 570 or newer. It uses about 4.3 GB of graphics memory while loaded and takes about 3.3 GB on disk. On a Mac it needs Apple Silicon and 16 GB of memory, and takes about 2.5 GB on disk. On other computers Rook uses its small voice. The small voice is a 31-million-parameter English model with 37 voices, downloads about 65 MB (62 MiB on disk), and needs no graphics card. Do you want the medium voice, and may I download the 65 MB small voice model (used directly or as fallback)?

- Record `--voice small` or `--voice medium`, and `--voice-model yes` or `--voice-model no`.
- If `--voice medium`: the installer checks the card first. If the card can run it, the installer adds the `rook-medium-voice.service` user unit (on a Mac, a launchd agent) and points Rook at it. With `--service no`, it adds no unit and prints the command that starts the voice by hand. If not, the installer says why in one sentence and keeps the small voice.

### Speech recogniser download

Ask:

> Rook uses AirType to hear you offline. Do you speak mostly English, or other languages too? English uses Parakeet English. Other languages use Parakeet multilingual, which knows 25 European languages, English among them. English is about a 480 MB download (660 MB on disk), and multilingual about 490 MB (670 MB on disk). May I download it?

- Record `--recogniser-model en` (the default) or `--recogniser-model multi`, and `--recogniser yes` or `--recogniser no`.
- The installer saves the choice as `recogniser_model` in `settings.json`, and Rook loads that model at start. When `recogniser_model` is not set, Rook uses the model in AirType's own config.
- AirType is Rook's own speech-to-text. The installer puts it in Rook's environment from its public repository at a pinned commit. The person installs nothing else.

### Login service

Ask:

> Should the installer write and enable Rook's systemd user service (starts Rook at login and restarts it daily at 04:30)?

- Record `--service yes` or `--service no`.

## 3. System packages and keyboard access (by hand, needs sudo)

The installer never runs `sudo`. Have the person run this command themselves first (it includes `base-devel` and `linux-api-headers` so `evdev` can build from source):

```sh
sudo pacman -S --needed base-devel linux-api-headers python gtk4 gtk4-layer-shell \
  python-gobject python-cairo grim pipewire-audio libpulse wl-clipboard ffmpeg \
  libnotify git portaudio libsndfile uv python-dbus noto-fonts
```

Omarchy already has most of these. For hardware video playback in Rook's media viewer, they can also install:

```sh
sudo pacman -S --needed gstreamer gst-plugin-va gst-plugin-gtk4
```

Rook reads the global talk key from `/dev/input`, so the person must belong to the `input` group **(by hand)**:

```sh
sudo usermod -aG input "$USER"
```

Tell the person plainly before they run it: joining the `input` group lets any program running as their user read every key press, including passwords. Rook uses it only to detect the push-to-talk key on Wayland. This group change takes effect at the next login.

## 4. Run the installer

Clone Rook first, unless you already have a checkout. Run `install/install.sh` from it, passing every answer from step 1 and step 2 explicitly:

```sh
git clone https://github.com/topmass/rook.git && cd rook
bash install/install.sh \
  --agent claude \
  --voice small \
  --voice-model yes \
  --recogniser yes \
  --recogniser-model en \
  --service yes
```

Adjust `--agent`, `--voice`, `--voice-model`, `--recogniser`, `--recogniser-model`, and `--service` to match the person's answers. When run without a terminal, the installer refuses to guess any omitted yes/no flag.

Other options:

- `--dry-run`: print every step, write nothing, and change nothing.
- `--prefix DIR`: choose where Rook's live checkout goes (default: `~/.local/share/rook/live`). Uninstall only removes a prefix inside `~/.local/share/rook`; a prefix elsewhere is left for you to remove by hand.
- `--source PATH|URL`: clone Rook from a specific path or repository address (defaults to the checkout `install/install.sh` is run from).
- `--recogniser-source PATH|URL`: install AirType from a local wheel, checkout, or git URL instead (pinned to commit `fe4815a480e40a68b220dadc8b23d61dbd4c3340` when no `@ref` is given). Without it, AirType comes from `github.com/topmass/airtype-for-omarchy` at that commit.
- `--from-cache DIR`: install from a local offline cache folder.
- `--use-existing-env`: use an existing unrecorded Python environment as it is without installing packages into it (without this flag, the installer refuses to touch an unrecorded or previously kept environment, including on reruns).
- `--replace-units`: replace existing modified or unrecorded Rook systemd unit files instead of leaving them untouched. Before replacing a unit it did not write (or whose hash changed), the installer copies the original beside it as `<unit>.replaced-<date>` and records that copy as yours so uninstall never deletes it.

What `install/install.sh` does and verifies at every step:

1. Checks the system: Arch-based Linux, active Hyprland session, PipeWire audio, OpenGL 4.4 Core GPU support, and `input` group membership.
2. Verifies all required Arch packages (including `base-devel` and `linux-api-headers`) and system Python GTK 4 / `gtk4-layer-shell` bindings.
3. Cleans any stale installer-marked stage folders from a prior kill, initializes the manifest, stages the Rook clone in a fresh sibling temp folder, records its commit and branch in the manifest before renaming into `~/.local/share/rook/live`, and leaves any pre-existing install untouched.
4. Stages pinned Python 3.12.14 environments in fresh sibling temp folders with `uv` (`requirements-rook.txt` and `requirements-voice.txt` use `--require-hashes`; AirType is installed with `--no-deps` from its pinned source), records each stage folder's file list in the manifest before moving it into place, refuses to write into a pre-existing unrecorded environment unless `--use-existing-env` is passed (which uses it as-is; a rerun without `--use-existing-env` also refuses a kept environment), and never widens an existing environment's file list on rerun (rebuilding in a stage folder and keeping any old environment with extra files under a dated name):
   - `~/.local/share/rook/venv` for Rook and the AirType recogniser.
   - `~/.local/share/rook/voice-phonon` for the small voice (`ptts 0.7.1`, `numpy 2.5.5`).
   - Pre-warms `uv` script cache for `desktop/render_tool.py` (`mcp 2.3.0`).
5. Fetches the pinned speech models using a temporary folder on disk inside `~/.local/share/rook/` (never `/tmp` for model downloads), verifies SHA256 checksums and exact file sizes for the pinned Phonon and recogniser model files, and exits 2 (incomplete) if a required model was skipped:
   - Small voice (`gradium/phonon-31m-en@92741c5b...` q8 + `Miles` voice): about **65 MB** (62 MiB on disk).
   - Recogniser, only the chosen one: `parakeet-unified-en-0.6b-int8` (`--recogniser-model en`, about **480 MB** download, **660 MB** on disk) or `parakeet-tdt-0.6b-v3-int8` (`--recogniser-model multi`, about **490 MB** download, **670 MB** on disk).
6. Creates `~/.config/rook/` (mode `0700`), `~/.config/rook/skills/`, and `~/.config/rook/settings.json` (mode `0600`). Preserves symlinks (writing through to the target) and refuses to overwrite an existing `settings.json` that does not parse as JSON.
7. When `--service yes` is passed, the installer records each unit's SHA256 hash and writes Rook's user units (`rook.service`, `rook-failed.service`, `rook-daily.service`, `rook-daily.timer`) with systemd-quoted paths and without `--wow` (when the agent's folder, such as `~/.local/bin`, is missing from the systemd user manager's `PATH`, `rook.service` gets a `PATH` line that adds it; `rook.service` starts with `graphical-session.target` when that target is active or uwsm is installed, and otherwise with `default.target`, and then Rook finds the Hyprland and Wayland sockets itself and leaves when that session ends, so the next start finds the next one), never writing or touching `rook.service.d/` drop-ins and calling `daemon-reload` only when a unit file changed or was removed. The daily restart timer may be enabled only while the installer owns all three of `rook.service`, `rook-daily.service`, and `rook-daily.timer` (checked on every run, including `--service no`); if any of the three is unowned or edited, the installer leaves your units alone, disables and removes its own timer (and removes its own daily service only when no user timer remains), and reports what was left and how to use `--replace-units`. Passing `--replace-units` (refused when `~/.config/systemd/user` is a symlink) copies any unowned or edited regular unit beside it as `<unit>.replaced-<date>`, records that copy in the manifest as yours so uninstall never deletes it, and writes Rook's unit.

If your checkout includes the optional `wow/` folder, enable `--wow` by hand (the installer never writes a drop-in itself) with a drop-in at `~/.config/systemd/user/rook.service.d/wow.conf` containing `[Service]`, `ExecStart=`, and `ExecStart=%h/.local/share/rook/venv/bin/python %h/.local/share/rook/live/desktop/rook.py --workspace %h --wow`, then run `systemctl --user daemon-reload && systemctl --user restart rook.service`.

## 5. Start Rook

```sh
systemctl --user start rook.service
journalctl --user -u rook.service -o cat --since -60s
```

The log says "Rook is ready" when it runs. Rook's presence then appears on the screen.

Now Rook's own onboarding takes over, by voice. Tell the person:

> Rook is running. Hold Right Control and say "run onboarding". Rook asks the rest itself.

The talk key works only after the `input` group takes effect at the next login. Until then the person can type each answer instead:

```sh
~/.local/share/rook/venv/bin/python ~/.local/share/rook/live/desktop/relay.py ask "run onboarding"
```

Until onboarding sets one, the talk keys are Right Control, F15, and F14. Onboarding sets the person's name, pronouns and talk key, finds their coding tool and where new projects start, sets how Rook's own agent asks before it acts, offers a build thread in T3 Code, offers the shared memory for Claude Code projects, explains screenshots, and auditions the voices. The key, the voice and screenshots apply at once, and the name, the pronouns and the permission mode at Rook's next start. The coding tool takes effect at Rook's next start too. By default Rook's own agent runs in full mode, and the person can change that by asking Rook.

Your part is done. Now you may help with other work.

## Updating Rook

Run this in a terminal to bring Rook up to date:

```sh
~/.local/share/rook/venv/bin/python ~/.local/share/rook/live/desktop/relay.py update
```

The command fetches the newest code and moves Rook's checkout to it. It runs the installer again only when Rook's requirements changed, or on a Mac when Rook.app must be rebuilt. Then it restarts Rook at a quiet moment. Add a tag or commit to the command to move to that version instead. The command updates only a checkout the installer made, and it stops when the checkout has local changes. Running the one-command install again does not update Rook, and Rook never updates itself.

## Uninstalling Rook

To preview or remove only what `install/install.sh` created (keeping `~/.config/rook`, `~/.local/state/rook`, any pre-existing checkout or environment, any venv with user-added files, any unit you wrote or edited, any user symlink, and any checkout with linked worktrees, custom `.git/hooks`, commits not reachable from a remote-tracking ref, extra branches, stashes, or user/ignored files):

```sh
bash ~/.local/share/rook/live/install/uninstall.sh --dry-run
bash ~/.local/share/rook/live/install/uninstall.sh
```

Uninstall removes its own copy too, so keep the checkout of Rook you cloned (or download `install/uninstall.sh` again) for a later `--purge`. It names each model cache and Python it leaves, with its size and the command that removes it, and the nightly tidy of the shared memory when onboarding installed it.

Inside folders it owns, uninstall removes only compiled Python files (`*.pyc`, `*.pyo`, and `__pycache__` folders when empty of other files) and any edit made in place to a file the installer created inside an environment. A checkout with local work is kept, except tracked edits hidden with `git update-index --skip-worktree` or `--assume-unchanged` which git status cannot see. Any `<unit>.replaced-<date>` copy saved by `--replace-units` is kept and not restored automatically; uninstall tells you where it is and how to put it back by hand.

Pass `--purge` to also remove `~/.config/rook` and `~/.local/state/rook` when the manifest recorded that the installer created them (pre-existing folders and user symlinks are left untouched). When any item is kept or skipped, the manifest is kept and updated rather than deleted. Run `bash install/test_uninstall.sh` and `bash install/test_install_failures.sh` to run the automated install and uninstall safety tests in a scratch folder.

## Models and licences

Rook ships no model weights. It downloads these at install, or when you turn an optional feature on. Each keeps its own licence.

| Model or tool | Used for | Licence | Source |
|---|---|---|---|
| Phonon 31M (`gradium/phonon-31m-en`) and its voices (`gradium/phonon-voices`) | The small voice | Apache-2.0 | [model card](https://huggingface.co/gradium/phonon-31m-en), [voices](https://huggingface.co/gradium/phonon-voices) |
| `ptts` 0.7.1 | Runs the small voice | MIT or Apache-2.0 | [repo](https://github.com/gradium-ai/xn-ptts) |
| Qwen3-TTS 12Hz 0.6B Base | The medium voice | Apache-2.0 | [model card](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base) |
| Its GGUF build (`Serveurperso/Qwen3-TTS-GGUF`), on Linux | The medium voice | Apache-2.0 | [model card](https://huggingface.co/Serveurperso/Qwen3-TTS-GGUF) |
| Its MLX builds (`mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit` and `-4bit`), on a Mac | The medium voice | Apache-2.0 | [8-bit](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit), [4-bit](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-0.6B-Base-4bit) |
| `qwentts-cpp-python` 0.5.0 (Linux) and `mlx-audio` 0.6.8 (Mac) | Run the medium voice | MIT | [qwentts-cpp-python](https://github.com/andimarafioti/qwentts-cpp-python), [mlx-audio](https://github.com/Blaizzy/mlx-audio) |
| Parakeet Unified EN 0.6B (`nvidia/parakeet-unified-en-0.6b`) | Speech to text in English (the default) | NVIDIA Open Model License | [model card](https://huggingface.co/nvidia/parakeet-unified-en-0.6b), [licence](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/) |
| Parakeet TDT 0.6B v3 (`nvidia/parakeet-tdt-0.6b-v3`) | Speech to text in 25 European languages (`--recogniser-model multi`) | CC-BY-4.0 | [model card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) |
| AirType | Runs speech to text | MIT | [repo](https://github.com/topmass/airtype-for-omarchy) |
| Smart Turn v3.2 (`pipecat-ai/smart-turn-v3`) | Optional end-of-turn detection | BSD-2-Clause | [model card](https://huggingface.co/pipecat-ai/smart-turn-v3) |
| Everystate v0.4.1 | Optional checker for the build thread | MIT | [repo](https://github.com/mattzcarey/everystate) |

The NVIDIA Open Model License is not an open-source licence. Read it before you use the recogniser commercially. AirType fetches an int8 ONNX build of Parakeet from [`csukuangfj2/sherpa-onnx-nemo-parakeet-unified-en-0.6b-int8-non-streaming`](https://huggingface.co/csukuangfj2/sherpa-onnx-nemo-parakeet-unified-en-0.6b-int8-non-streaming). That build states no licence of its own, so NVIDIA's licence applies to it. The multilingual model comes from [`csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8`](https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8), an int8 ONNX build under CC-BY-4.0 like NVIDIA's original.

The repo holds four medium voice reference clips in `assets/voices/medium/`. They were made with Qwen3-TTS VoiceDesign ([model card](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign), Apache-2.0).
