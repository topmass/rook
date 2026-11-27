# Installing Rook (runbook for a coding agent)

A person pasted something like "install Rook from https://github.com/topmass/rook" into you, their coding agent (Claude Code, Codex, Antigravity or Pi). Set Rook up with them, step by step, until `relay.py verify` says every piece works. After that, Rook's own voice onboarding only asks their preferences.

Below, `relay.py` means `"${XDG_DATA_HOME:-$HOME/.local/share}/rook/venv/bin/python" "${XDG_DATA_HOME:-$HOME/.local/share}/rook/live/desktop/relay.py"`.

## Rules

- Do the steps in order. Run every command yourself, except the ones marked **the person**.
- After each step, run its check. Each row says one of three things:
  - `ok`: go on.
  - `FIX`: it prints the fix. Do it, then check again. Go on only when it says `ok`. The one exception: the row's own fix says the piece cannot work on this computer, and the person agrees. Then tell them, and go on with the other steps. A device they can plug in or pick is never that case.
  - `--`: not checked on this system. It prints what to do by hand, if anything: do that, as the step says, then go on.
- Never read, print or paste a password, a token or a key.
- Never click, approve or script a permission for the person. Tell them what to click, and wait.
- Offer each optional extra once. Install it only after a clear yes.

## Steps

1. **System.** Run `uname -sm`, and on Linux `cat /etc/os-release`. Rook runs on Arch Linux with Hyprland, and on an Apple Silicon Mac. On anything else, stop and say so.

2. **System packages (the person).** Linux: ask them to run this in their own terminal, because it needs their password:
   ```sh
   sudo pacman -S --needed base-devel linux-api-headers python gtk4 gtk4-layer-shell python-gobject python-cairo grim \
     pipewire-audio libpulse wl-clipboard ffmpeg libnotify git portaudio libsndfile uv python-dbus noto-fonts
   sudo usermod -aG input "$USER"
   ```
   Tell them first that the `input` group lets any program they run read every key press. Rook uses it only for the talk key. Mac: ask them to run `xcode-select --install` if `xcode-select -p` fails.

3. **Install.** Tell the person what it downloads: Rook and its speech models, about 1 GB. When this computer can run the medium voice, it gets that too: 3.3 GB more, or 2.5 GB on a Mac. To skip it, add `--voice small` after the agent. The install can outlast your shell's time limit, so run it in the background with a log. Use the agent the person uses with Rook (`claude`, `codex`, `antigravity` or `pi`):
   ```sh
   nohup sh -c 'curl -fsSL https://raw.githubusercontent.com/topmass/rook/main/install/get.sh -o ~/rook-get.sh && sh ~/rook-get.sh --agent claude; echo "install exit=$?"' > ~/rook-install.log 2>&1 < /dev/null & echo $! > ~/rook-install.pid
   ```
   Then run `tail -n 5 ~/rook-install.log` every 30 seconds until it shows `install exit=`. If that is not `install exit=0`, the log says why: fix that, then run the same command again. The log can stay quiet for many minutes while the medium voice downloads, because that download shows no progress. So while `kill -0 "$(cat ~/rook-install.pid)" 2>/dev/null` succeeds, the install is still running: keep waiting, and never start a second one. If it still runs after 60 minutes, tell the person how long it has run and the log's last line, and ask whether to keep waiting; ask again every 60 minutes after that. Only when that check fails and the log has no `install exit=`, the install stopped before it finished. Then ask the person to run, in their own terminal, `sh ~/rook-get.sh` with the same options you started it with, such as `--agent claude` and `--voice small`. After `install exit=0`, run `rm ~/rook-get.sh ~/rook-install.log ~/rook-install.pid`. Check: `relay.py verify --only python,models,speech`.

4. **Service.** Check: `relay.py verify --only service,desktop,keys,mic`. On Linux, the first time, the person logs out and in once, so the `input` group and the desktop session reach Rook. The logout ends this session too, so tell them first how to bring you back. They open a terminal in this same folder and run `claude --continue` (Codex: `codex resume --last`, Antigravity: `agy --continue`, Pi: `pi --continue`). Then they say "carry on with step 4". Then check again.

5. **Sign-in (the person).** Check: `relay.py verify --only agent`. If it marks FIX, ask the person to run the command it prints in their own terminal on this computer. On a Mac, they sign in from Terminal on this Mac, not over ssh: over ssh the Mac keeps the sign-in where Rook's own session cannot read it, and this check, run inside Rook, then marks FIX. Antigravity and Pi have no sign-in status to check: step 10 proves them. With T3 Code, Codex needs `codex mcp login t3` once, and Pi needs `relay.py pi t3-login` while T3 Code runs, then a Rook restart.

6. **Microphone permission (Mac, the person).** Run `open -W -n <Rook.app> --args --request-access microphone`, using the Rook.app path the installer printed. Tell them: "A dialog asks about the microphone. Click Allow." Check: `relay.py verify --only mic`. It asks inside Rook, so it reports this Rook.app's own permission. If no dialog appeared, they turn on Rook in System Settings, Privacy & Security, Microphone.

7. **Microphone.** Check: `relay.py verify --only input,output`. A FIX here means a virtual device, such as a loopback driver, is in use. Ask them to plug in or pick a real microphone and speakers.

8. **Talk key permission (Mac, the person).** Run `relay.py mac-access open input`, then `open -R <Rook.app>`. Tell them: "Turn on Rook in Input Monitoring. If Rook is not in the list, drag it in from the Finder window I opened, or click + and pick it." macOS often shows no dialog here, so do not wait for one. Then run `launchctl kickstart -k gui/$(id -u)/com.rook.companion`, and check: `relay.py verify --only keys`. It asks inside Rook, so a switch that shows on for an older Rook.app still marks FIX. Only if it marks FIX while they see Rook switched on, tell them: "Remove the Rook entry with the minus button, then add this one." Kick Rook again and check again. It says ok only when the permission is in force and Rook listens for Right Option.

9. **Extras, offered once.** Ask about each one in a single sentence. Run it only on a yes.
   - Background work: Rook hands long work to T3 Code or Herdr. T3 Code: they download it from https://t3.codes and open it. Herdr: `relay.py herdr install`.
   - The same memory for all their Claude Code projects: `relay.py memory install-shared`.
   - One shared instruction file and skills folder for all their coding agents (only with two or more agents): `relay.py shared-agents`.
   - Everystate, a free checker for a Rook build thread in T3 Code (only with T3 Code): `relay.py everystate install`.

10. **First real turn (the person).** You see a command's output only when it ends, so tell them first. Run `relay.py get talk_keys` to learn the key (on a Mac it is Right Option, the Option key on the right of the space bar). Then say: "Hold <that key>, say hello to Rook, and let go. Rook answers out loud and starts getting to know you." Then run `relay.py verify --only talk`, with a time limit of at least 3 minutes (the steps before proved the rest). It waits for that one spoken turn and its answer. It must say every piece works. Then ask the person whether they heard Rook answer. If they did not, run `relay.py verify --only output` and fix what it says.

11. **Done.** That hello started Rook's own voice setup, which only saves their preferences: their name, the voice, how they like to work. Tell them: "Rook takes it from here. Answer its questions by voice." Your part is done.

## Updating and removing

- Update: `relay.py update`. It moves Rook to the newest code and restarts it at a quiet moment.
- Remove: `bash "${XDG_DATA_HOME:-$HOME/.local/share}/rook/live/install/uninstall.sh" --dry-run`, then without `--dry-run`. Add `--purge` to remove settings and logs too. It prints each cache it leaves, with its size and how to remove it.
- `install/install.sh --help` lists every install option, such as `--voice small`, `--service no` or `--dry-run`.

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
