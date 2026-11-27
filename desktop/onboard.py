"""Rook's onboarding commands: the voice audition, the scan, the apply, one shared setup for the coding agents, and
Everystate for a build thread. relay.py imports this module only when one of those commands runs, so the commands the
assistant runs all day do not compile it."""
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time

import desk
import memory
import relay  # When relay.py runs as the main script, it registers itself as relay first: this is the same module.
import settings
from relay import ask_rook, projects_folder_in_force
from settings import (
    CONFIG, MEDIUM_VOICES, atomic_write_text, fold, match_voice, medium_voice, read_settings, valid, voices,
    write_settings,
)

watch = relay.watch  # relay already loaded the thread watcher's module; onboarding reads its machine table.

OWNER = settings.OWNER_TOKEN  # The owner's name, filled in when the text leaves Rook.
SCRIPT = Path(__file__).resolve().with_name("relay.py")


# The onboarding voice audition. The voice in use speaks first, then the medium voices chosen to offer
# (2026-11-24: Late-Night Architect and Velvet Wit). Each sample has range: warmth, a little humour, and a question,
# about eight seconds each. The samples go through the running speech worker, so they keep the live speed, volume
# and expressiveness: only the voice differs.
OFFERED = ("late-night-architect", "velvet-wit")
SMALL_OFFERED = ("Miles", "Bryony")
SAMPLES = ("Good morning! The build passed overnight, and it seemed rather proud of itself. "
           "Shall I read you the two reviews waiting?",
           "Morning, you. Rain until noon, so the walk can wait. Better news: the research came back, and it is "
           "good. Want the highlights?",
           "Hey there. Your first call moved to ten thirty, which buys you a whole extra coffee. "
           "Should I hold your messages until then?")
# Seconds an audition line waits for the medium voice's first sound, instead of the usual 2.5 s. A busy graphics
# card was measured at about 8 s to first sound, and a cold model loads in 8 to 11 s.
AUDITION_WAIT = 15
TALK_KEYS = ("RightAlt", "RightCtrl", "CapsLock", "RightMeta", "F13", "F14", "F15")  # The first is the onboarding default.
PERMISSION_MODES = ("inherit", "careful", "automatic", "full")  # inherit keeps the agent's own settings.
ONBOARDING = CONFIG.with_name("onboarding.json")  # A record of the last onboarding's choices.
ROOK_ROOT = SCRIPT.parent.parent  # Rook's repository, where its build thread works.
CODE_FOLDERS = ("Code", "code", "Projects", "projects", "src", "dev", "Developer", "repos", "git", "Work")
# Rehearsal stand-ins for onboard --scan --as, so each orchestrator's path can be walked with none installed. Each
# follows the shape of that tool's real answer: T3 Code's project list (title and folder), relay.py herdr agents
# (name, kind, state, folder), and relay.py pi sessions (folder). The projects are invented.
AGENT_NAMES = {"claude": "Claude Code", "antigravity": "Antigravity", "codex": "Codex", "pi": "Pi"}
# The model and effort onboarding recommends for Rook's own agent, and its spoken name (the owner, 2026-11-26).
RECOMMENDED = {"claude": ("claude-opus-5-5", "medium", "Claude Opus 5.5"),
               "antigravity": ("gemini-4-neon", "medium", "Gemini 4 Neon"),
               "codex": ("gpt-6.2-sol", "high", "Sol 6.2")}
TIDY_AGENTS = ("claude", "antigravity", "codex", "pi")  # memory.py's nightly tidy runs with these (relay.py dream).
STAND_INS = {
    "t3": ["T3 Code: installed and running. Its projects, with their folders:",
           "  notes-app: ~/Code/notes-app", "  website: ~/Code/website", "  scripts: ~/Code/scripts",
           "Herdr: not installed.", "Pi: not installed."],
    "herdr": ["T3 Code: not installed.",
              "Herdr: installed and running, with 2 agents:",
              "  claude-website: claude, idle, ~/projects/website", "  pi-notes: pi, done, ~/projects/notes",
              "Pi: installed. Its newest sessions are in ~/projects/notes."],
    "pi": ["T3 Code: not installed.", "Herdr: not installed.",
           "Pi: installed. Its newest sessions are in ~/dev/api and ~/dev/site."],
    "none": ["T3 Code: not installed.", "Herdr: not installed.", "Pi: not installed.",
             "Code folders: none found. Git projects directly in your home folder: 4."],
}
# With neither T3 Code nor Herdr, Rook cannot hand work to background threads, which keeps it free to talk. So
# onboarding strongly recommends one, T3 Code first, and can install Herdr (the owner, 2026-11-26).
NO_ORCHESTRATOR = (
    "Background work: neither T3 Code nor Herdr is here, so Rook cannot hand work to background threads. These turns "
    "replace the coding tool step's first line.\n"
    "  First. Say: \"One thing matters a lot here. I stay free to talk with you because I hand real work to background "
    "threads and keep track of them, and for that I need a tool that runs those threads. We highly recommend T3 Code "
    "right now, an app you download and open. I also run on Herdr, a lighter option in your terminal, and I can "
    "install it for you.\" Ask: \"Which would you like?\"\n"
    "  T3 Code. Say: \"Download T3 Code from t3 dot codes, install it, and open it.\" Ask: \"Can you tell me when "
    "it's open?\" Then run onboard --scan again; in a rehearsal, take their word. Once T3 Code is running, say: "
    "\"Got it. I'll connect to T3 Code when I next start, and tell you if it needs you to sign me in.\" Then ask where "
    "their projects live, and give --orchestrator t3. While it is not running, ask them to check that it's open.\n"
    "  Herdr. Run relay.py herdr install, with --dry-run in a rehearsal. When it worked, say: \"Herdr's in. Open a "
    "terminal and type herdr once to start it, and I'll hand work to it from then on.\" Then ask the Herdr question, "
    "and give --orchestrator herdr. When it failed, say why in one sentence, and ask whether they'd rather set up T3 "
    "Code.\n"
    "  Skip. Say: \"Okay. Background work won't be available until you add T3 Code or Herdr, so ask me any time.\" "
    "Then go on as with no tool.")
BUILD_BRIEF = ("You are Rook's build thread, set up during onboarding. Rook is {owner}'s voice assistant. Its code is "
               "the repository at {root}. Rook hands you requests by voice, such as \"add this ability\", and you "
               "build, test and ship them. Rook never changes or restarts itself. Follow these rules on this computer. "
               "On Linux, run every test, check, benchmark or render under {root}/scripts/capped, which holds a job to "
               "half the processor cores and a quarter of the memory, and run one heavy job at a time. Ask {owner} "
               "before a job that may run over a minute or load the graphics card. Keep tests headless: open no "
               "window, play no sound, and never use the microphone. Point every test at scratch folders, never at "
               "{owner}'s own settings or data, and delete the scratch files when done. After a change is live, "
               "restart Rook safely with {python} {root}/desktop/relay.py restart, which waits for a quiet moment."
               "{subagents} Reply with one line that you are ready.")
BUILDER_TITLE = "Rook builder"
# The T3 Code providers a build thread can start on, and each one's effort option (delegate skill, models.md).
EFFORT_OPTIONS = {"claudeAgent": "effort", "codex": "reasoningEffort", "antigravity": "thought_level"}
# The build thread onboarding recommends for each installed agent (its command, the --builder value, the spoken model,
# and the preferences file's family word), always at high effort, with subagents on the same model (the owner, 2026-11-26).
BUILDERS = {"claude": ("claude", "claudeAgent:claude-opus-5-5:high", "Claude Opus 5.5", "newest Opus"),
            "antigravity": ("agy", "antigravity:gemini-4-neon:high", "Gemini 4 Neon", "newest Neon"),
            "codex": ("codex", "codex:gpt-6.2-sol:high", "Sol 6.2", "newest Sol")}
PREFERENCES = CONFIG.with_name("model-preferences.md")  # The person's model choices; rook:delegate reads it.
PREFERENCES_SECTION = "## Build thread from setup"
PREFERENCES_TEMPLATE = ("# Rook's model preferences\n\nYour choices for the threads Rook starts in T3 Code. Rook reads this "
                        "before every launch, and changes it when you state a standing or temporary preference by "
                        "voice.\n\n")
BUILDER_STARTING = CONFIG.with_name("builder-starting")  # Written before a build thread start, removed once it is known.
STARTING_STALE = 600  # Seconds after which a start that left no thread in T3 Code counts as failed.
T3_WAIT = 75  # Seconds a build thread start may take, so the apply stays under the 120 s shell limit.


class StepFailed(Exception):
    """One apply step that did not happen. Its text is the reason, as a plain clause."""


def plain_reason(error):
    """Why a step failed, as a clause a person can hear."""
    if isinstance(error, StepFailed):
        return str(error)
    if isinstance(error, subprocess.TimeoutExpired):
        return "it did not answer in time"
    if isinstance(error, FileNotFoundError) and error.filename in ("t3", "claude"):
        return f"the {error.filename} command is not installed"
    if isinstance(error, OSError):
        return f"{(error.strerror or str(error)).rstrip('.').lower()}" + (f" at {error.filename}" if error.filename else "")
    if isinstance(error, ValueError):
        return "an answer or a file was not readable"
    return f"something went wrong ({type(error).__name__})"


def voice_words(name):
    """A medium voice's name as Rook says it."""
    return name.replace("-", " ").title()


def audition_command(argv):
    """Play the audition through the running Rook's speech worker: the voice in use, then the offered voices, each
    in its own voice with the live speed, volume and expressiveness. Saves nothing."""
    if argv:
        sys.exit("Usage: relay.py audition")
    running = ask_rook("get")
    if running is None:
        sys.exit("Rook is not running, so it cannot play the voices.")
    if not running.get("ok"):
        sys.exit(running.get("error") or "Could not read the running Rook's voice settings.")
    values = {key: (entry or {}).get("value") for key, entry in running["settings"].items()}
    engine = values.get("voice_engine")
    health = medium_voice("/health") if engine == "medium" else None
    names = (health or {}).get("voices") or ()
    current = values.get("voice_medium") if engine == "medium" else values.get("voice")
    medium = bool(health and health.get("loaded") and current in names)
    if medium:
        picks = [v for v in dict.fromkeys((current, *OFFERED)) if v in names]
        lines = [{"voice_medium": v, "first_audio": AUDITION_WAIT,
                  "text": f"{'You are hearing my voice now,' if i == 0 else 'And this is'} {voice_words(v)}. "
                          f"{SAMPLES[i % len(SAMPLES)]}"} for i, v in enumerate(picks)]
        spoken = [voice_words(v) for v in picks]
    else:
        picks = list(dict.fromkeys((values.get("voice") or SMALL_OFFERED[0], *SMALL_OFFERED)))
        lines = [{"voice": v, "text": f"{'This is my small voice,' if i == 0 else 'And this is'} {v}. "
                                      f"{SAMPLES[i % len(SAMPLES)]}"} for i, v in enumerate(picks)]
        spoken = picks
    for line, name in zip(lines, spoken):  # Each voice's name shows under the overlay while its sample plays.
        line["guide"] = {"text": name, "until": "listening"}
    answer = ask_rook("audition", json.dumps(lines), wait=110)  # Rook answers within 100 s, under the 120 s shell limit.
    relay.guide(None)
    if answer and answer.get("refused"):
        print(f"Nothing played: {answer['error']} Nothing was saved. The voice choice is not made: give onboard --voice none."
              + (" Say that the voice audition needs the desk for now." if answer["refused"] == "phone" else ""))
        return
    if not answer or not answer.get("ok"):
        sys.exit(f"Rook could not play the voices: {(answer or {}).get('error', 'Rook stopped answering.')}")
    why = ("" if medium else "Rook speaks with its small voice now" if engine != "medium" else
           "the medium voice server did not answer" if health is None else
           "the medium voice is not loaded yet" if not health.get("loaded") else
           "the medium voice server lacks the voice in use")
    lead = f"The medium voice cannot play: {why}. So Rook used its small voices. " if why else ""
    said = answer.get("lines") or [{}] * len(picks)
    report = [f"{name} spoke in its own voice." if line.get("spoke") else
              f"{name} was stopped before it ended." if line.get("stopped") else
              f"{name} did not play: {line.get('problem') or 'Rook gave no report for it'}."
              for name, line in zip(spoken, said)]
    failed = any(not line.get("spoke") and not line.get("stopped") for line in said)
    print(lead + " ".join(report) + " The samples used the live speed, volume and expressiveness. Nothing was saved."
          + (' The voice choice is not made. Say: "I could not reach my better voice just now. We can choose the'
             ' voice later." Then go on, and give onboard --voice none.' if failed else
             " The person stopped the audition, so they heard it as far as it went. Ask which voice they want, or"
             " offer to play them again." if any(line.get("stopped") for line in said) else
             f" End your turn with the question: which one, {', '.join(spoken[:-1])} or {spoken[-1]}?"))


# One shared instruction file and one shared skills folder for every coding agent: the canonical pair in ~/.agents,
# and each agent's own place as a link to it. Each agent is (name, home folder that shows it is installed,
# instruction file, skills folder). Antigravity reads its personal customizations from ~/.gemini/config.
SHARED_AGENTS = (("Claude Code", ".claude", ".claude/CLAUDE.md", ".claude/skills"),
                 ("Codex", ".codex", ".codex/AGENTS.md", ".codex/skills"),
                 ("Antigravity", ".gemini", ".gemini/config/AGENTS.md", ".gemini/config/skills"))
SHARED_FILE, SHARED_SKILLS = ".agents/AGENTS.md", ".agents/skills"


def has_content(path):
    """Whether a real file or folder (not a link) at path holds anything."""
    if path.is_symlink() or not path.exists():
        return False
    return path.stat().st_size > 0 if path.is_file() else any(path.iterdir())


def link(path, target):
    """Make path a link to target, through a temporary link and a rename, so nothing is ever half made."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.rook-link")
    temp.unlink(missing_ok=True)
    temp.symlink_to(target)
    temp.replace(path)


def exchange(a, b):
    """Swap two paths in one step where Linux allows it (renameat2), so neither name is ever missing. Return whether
    it did."""
    try:
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        return libc.renameat2(-100, os.fsencode(a), -100, os.fsencode(b), 2) == 0  # AT_FDCWD, RENAME_EXCHANGE
    except (OSError, AttributeError):
        return False


def unsafe_links(folder):
    """Links inside folder that would break, or that a copy could not follow: broken ones, and relative ones that
    point outside the folder."""
    found = []
    for root, dirs, files in os.walk(folder):
        for name in dirs + files:
            path = Path(root) / name
            if not path.is_symlink():
                continue
            target = os.readlink(path)
            inside = os.path.realpath(path).startswith(os.path.realpath(folder) + os.sep)
            if not path.exists():
                found.append(f"{path} is a broken link")
            elif not os.path.isabs(target) and not inside:
                found.append(f"{path} points outside it by a relative path")
    return found


def blocked(shared, kind):
    """Why the shared place cannot be made, or None: a broken link or a file on its way, or the wrong kind there."""
    home = Path.home()
    for parent in reversed(shared.relative_to(home).parents[:-1]):
        place = home / parent
        if place.is_symlink() and not place.exists():
            return f"{place} is a broken link"
        if place.exists() and not place.is_dir():
            return f"{place} is a file where a folder belongs"
    if shared.is_symlink() and not shared.exists():
        return f"{shared} is a broken link"
    if shared.exists() and (shared.is_dir() if kind == "instructions" else not shared.is_dir()):
        return f"{shared} is the wrong kind of thing for shared {kind}"
    return None


def shared_agents(dry):
    """Link each installed agent's instruction file and skills folder to the shared pair, losing nothing. Return
    (lines, whether anything was or would be done). An agent's own file or folder with content stays, and so does a
    link that points elsewhere. Only when exactly one place holds content, and the shared one does not exist, does
    that content move to the shared place, with a dated backup copy left beside it. Every check runs before any
    change, so the dry run says what the real run does, and a refusal leaves nothing behind."""
    home, lines, acted = Path.home(), [], False
    installed = [agent for agent in SHARED_AGENTS if (home / agent[1]).is_dir()]
    for kind, index, shared in (("instructions", 2, home / SHARED_FILE), ("skills", 3, home / SHARED_SKILLS)):
        wrong = (lambda path: path.is_dir()) if kind == "instructions" else (lambda path: path.is_file())
        places, odd = [], []
        for agent in installed:
            path = home / agent[index]
            linked = next((home / p for p in reversed(path.relative_to(home).parents[:-1]) if (home / p).is_symlink()),
                          None)
            if linked:  # Moving out of a linked folder, such as a dotfiles repo, would empty that repo.
                lines.append(f"{agent[0]} {kind}: {linked} is a link to {os.readlink(linked)}, so its {kind} stay "
                             "where they are. Move them by hand to share them.")
                continue
            (odd if not path.is_symlink() and path.exists() and wrong(path) else places).append((agent[0], path))
        lines += [f"{name} {kind}: {path} is the wrong kind of thing there, left as it is." for name, path in odd]
        own = [(name, path) for name, path in places if has_content(path)]
        if shared.is_symlink() and shared.exists():
            lines.append(f"Shared {kind}: {shared} is a link to somewhere else, so nothing changes.")
            continue
        why = blocked(shared, kind)
        if why:
            lines.append(f"Shared {kind}: {why}, so nothing changes.")
            continue
        if not shared.exists() and len(own) > 1:
            lines.append(f"Shared {kind}: {' and '.join(n for n, _ in own)} each have their own, so nothing changes.")
            continue
        mover = own[0][1] if not shared.exists() and own else None
        broken = unsafe_links(mover) if mover is not None and mover.is_dir() else []
        if broken:
            lines.append(f"Shared {kind}: {own[0][0]}'s {mover} holds links that would break if it moved ("
                         + "; ".join(broken[:3]) + "), so nothing changes. Move it by hand, or keep it as it is.")
            continue
        backup = None
        try:
            if mover is not None:  # Exactly one agent has content: it becomes the shared one.
                backup = mover.with_name(f"{mover.name}.backup-{datetime.now():%Y%m%d}")
                n = 2
                while backup.exists() or backup.is_symlink():
                    backup, n = mover.with_name(f"{mover.name}.backup-{datetime.now():%Y%m%d}-{n}"), n + 1
                if not dry:  # Copy, then swap the original for a link in one step: no moment without either.
                    shared.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        (shutil.copytree(mover, shared, symlinks=True) if mover.is_dir() else shutil.copy2(mover, shared))
                    except (OSError, shutil.Error):
                        shutil.rmtree(shared, ignore_errors=True) if shared.is_dir() else shared.unlink(missing_ok=True)
                        raise
                    temp = mover.with_name(f".{mover.name}.rook-link")
                    temp.unlink(missing_ok=True)
                    temp.symlink_to(shared)
                    if exchange(temp, mover):
                        temp.rename(backup)  # temp now holds the original: it is the backup.
                    else:
                        mover.rename(backup)
                        temp.rename(mover)
                lines.append(f"{own[0][0]} {kind}: {'would move' if dry else 'moved'} to {shared}, with a backup at "
                             f"{backup}, and linked.")
                acted = True
            elif not shared.exists() and places:  # Nothing to keep anywhere: start the shared one empty.
                if not dry:
                    shared.parent.mkdir(parents=True, exist_ok=True)
                    shared.mkdir() if kind == "skills" else shared.touch()
                lines.append(f"Shared {kind}: {'would make' if dry else 'made'} {shared}.")
            for name, path in places:
                if path == mover:
                    continue
                if path.is_symlink():
                    right = os.path.realpath(path) == os.path.realpath(shared)
                    lines.append(f"{name} {kind}: " + ("already linked." if right else
                                                       f"a link to {os.readlink(path)}, left as it is."))
                elif has_content(path) or path.is_file():
                    lines.append(f"{name} {kind}: has its own, left as it is.")
                else:  # Absent, or an empty folder: linking it loses nothing.
                    if not dry:
                        if path.is_dir():
                            path.rmdir()
                        link(path, shared)
                    lines.append(f"{name} {kind}: {'would link' if dry else 'linked'} to {shared}.")
                    acted = True
        except (OSError, shutil.Error) as error:
            lines.append(f"Shared {kind}: stopped, nothing more changed: {plain_reason(error)}.")
    if not installed:
        lines.append("No coding agent is installed, so there is nothing to share.")
    return lines, acted


# Everystate, a formal verification tool for build threads (MIT, mattzcarey/everystate). Pinned to release v0.4.1,
# commit 28fd7c5. The project publishes no checksums, so these SHA-256 sums were taken from its release files on
# 2026-11-25. The release has a prebuilt binary, so no Rust toolchain is needed.
EVERYSTATE_VERSION, EVERYSTATE_COMMIT = "v0.4.1", "28fd7c5f9069a021b7a9702007e2f2b054a789fb"
EVERYSTATE_URL = "https://github.com/mattzcarey/everystate"
EVERYSTATE_SHA256 = {
    ("Linux", "x86_64"): ("linux-x64", "347c5381c3eb1cb62b788ffa90c562ccd9a6b1df3f3f40e725db6c7b80bd5d68"),
    ("Linux", "aarch64"): ("linux-arm64", "18b1802546d2816156f6100c4582e4154bd34e6cf5499045a665f29c6de1f86b"),
    ("Darwin", "arm64"): ("darwin-arm64", "05936480d491bc3f9d0a5f058d0625950c70b8bb24021721b3ac6c8beb130221"),
    ("Darwin", "x86_64"): ("darwin-x64", "13b46ae67d4ecf613bfec4b42436afa4af340447a686a5f6d8599c2623f42774"),
}
EVERYSTATE_SKILL = {  # Each skill file at that commit, with its SHA-256, taken 2026-11-25.
    "SKILL.md": "4635cc26ecce02cd6abe96edf4a386a0e154297e6baebbb3be7c26e652593f60",
    "example/Charge.cfg": "e1c6c8811ab148999a92187d7d89e8005fe4d451527698a21cc4eae8b923b938",
    "example/Charge.tla": "f3ad94832691bfaff8e8aa3d83e2721388d5916f6cbb892d6a7dc1c737eb8c67",
    "example/ChargeBroken.cfg": "f1d7bf697af0c07beb447fa62b30a2c1c5120cbd4151343b71ce7a4794148d08",
    "example/charge-double.jsonl": "f22e38f7ae76c9d63c493f8d7ae64f6fbf372e538772ab4c9cbe67e0cafaeac3",
    "example/charge-ok.jsonl": "da1affe8df755f9b336aed0c03439c8b6c3196dc5c99c6c2b6dd1785e7c2adba",
    "example/observe.ts": "948b4a878ee19930f55a5b104e73dd3487825042f09bb7391a2b8c6e1f72f828",
}
INSTALLED = CONFIG.with_name("installed.json")  # What Rook installed outside itself, so it can be removed.


def build_skills_folder():
    """Where the person's build agents read skills: the shared folder, else Claude Code's, else Codex's."""
    home = Path.home()
    for place in (SHARED_SKILLS, ".claude/skills", ".codex/skills"):
        if (home / place).is_dir():
            return home / place
    return home / ".claude/skills"


def install_everystate(dry, fetch=None):
    """Install Everystate's binary to ~/.local/bin and its skill into the build agents' skills folder, for this user
    only. Return one line, or raise StepFailed. Every file is checked against its pinned sum before it is placed, and
    recorded in installed.json as soon as it is placed. A file Rook did not place, or one changed since, stays."""
    import hashlib
    import http.client
    import io
    import platform
    import tarfile
    import urllib.request
    fetch = fetch or (lambda url: urllib.request.urlopen(url, timeout=30).read())
    asset = EVERYSTATE_SHA256.get((platform.system(), platform.machine()))
    if not asset:
        raise StepFailed(f"Everystate has no release for {platform.system()} on {platform.machine()}")
    binary = Path.home() / ".local/bin/everystate"
    skill = build_skills_folder() / "formal-verification"
    try:
        record = json.loads(INSTALLED.read_text()) if INSTALLED.exists() else {}
        placed = dict((record.get("everystate") or {}).get("files") or {})
    except (OSError, ValueError, AttributeError):
        raise StepFailed(f"Rook's record of what it installed, {INSTALLED}, is not readable") from None
    if not isinstance(record, dict):
        raise StepFailed(f"Rook's record of what it installed, {INSTALLED}, is not readable")

    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    wanted = {str(skill / name): sum_ for name, sum_ in EVERYSTATE_SKILL.items()}
    for path in [binary, *map(Path, wanted)]:
        if path.is_symlink() or path.exists() and str(path) not in placed:
            raise StepFailed(f"{path} is already there, and not Rook's, so I left it")
        if path.exists() and digest(path) != placed[str(path)]:
            raise StepFailed(f"{path} changed since Rook installed it, so I left it")
    if binary.exists() and all(Path(path).exists() and placed.get(path) == sum_ for path, sum_ in wanted.items()) \
            and (record.get("everystate") or {}).get("version") == EVERYSTATE_VERSION:
        return f"Everystate {EVERYSTATE_VERSION} is already installed."
    if dry:
        return (f"download Everystate {EVERYSTATE_VERSION} for {asset[0]}, check every file's SHA-256, and install "
                f"{binary} and the skill at {skill}")
    try:
        data = fetch(f"{EVERYSTATE_URL}/releases/download/{EVERYSTATE_VERSION}/everystate-{asset[0]}.tar.gz")
        if hashlib.sha256(data).hexdigest() != asset[1]:
            raise StepFailed("the download did not match its pinned checksum")
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            files = {str(binary): archive.extractfile("everystate").read()}
        for name in EVERYSTATE_SKILL:
            body = fetch(f"https://raw.githubusercontent.com/mattzcarey/everystate/{EVERYSTATE_COMMIT}/skills/"
                         f"formal-verification/{name}")
            if hashlib.sha256(body).hexdigest() != EVERYSTATE_SKILL[name]:
                raise StepFailed(f"the skill file {name} did not match its pinned checksum")
            files[str(skill / name)] = body
    except (OSError, KeyError, AttributeError, tarfile.TarError, ValueError, http.client.HTTPException) as error:
        raise StepFailed(f"the download failed: {plain_reason(error)}") from None
    entry = {"version": EVERYSTATE_VERSION, "commit": EVERYSTATE_COMMIT, "binary": str(binary), "skill": str(skill),
             "installed": datetime.now().isoformat(timespec="seconds"), "files": placed}
    INSTALLED.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    for path, body in files.items():  # Each file goes in whole, then into the record, before the next.
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(f".{target.name}.rook-new")
        temp.write_bytes(body)
        temp.chmod(0o755 if target == binary else 0o644)
        temp.replace(target)
        placed[path] = hashlib.sha256(body).hexdigest()
        atomic_write_text(INSTALLED, json.dumps({**record, "everystate": entry}, indent=2) + "\n")
    return f"Installed Everystate {EVERYSTATE_VERSION} at {binary}, with its skill at {skill}."


def shared_agents_command(argv):
    """relay.py shared-agents [--dry-run]: link every coding agent's instructions and skills to one shared pair."""
    if argv not in ([], ["--dry-run"]):
        sys.exit("Usage: relay.py shared-agents [--dry-run]")
    lines, _ = shared_agents(bool(argv))
    print("\n".join(lines))


def build_thread_line(t3=True):
    """The scan's build thread line: the model to recommend from the agents installed here. A build thread runs in
    T3 Code, so without it there is nothing to offer."""
    have = [agent for agent, (command, *_) in BUILDERS.items() if shutil.which(command)]
    helpers = ("You can change which models its helpers use any time by telling me, for good or just for one job, "
               "and I'll remember it.")
    if not have:
        return "Build thread: no Claude Code, Antigravity or Codex is here to run one. Give --builder skip."
    if not t3:
        return "Build thread: it needs T3 Code, which is not here. Ask nothing, and give --builder skip."
    picks = [agent for agent in ("claude", "antigravity") if agent in have] or have
    if len(picks) > 1:
        return ("Build thread: Claude Code and Antigravity are both here. Say: \"You have Claude Code and Antigravity, "
                f"so it's your call: Claude Opus 5.5 or Gemini 4 Neon, both at high effort. {helpers}\" Ask: \"Which "
                "would you like?\" Opus: give --builder claudeAgent:claude-opus-5-5:high --subagents claude-opus-5-5. "
                "Neon: give --builder antigravity:gemini-4-neon:high --subagents gemini-4-neon.")
    _, builder, spoken, _ = BUILDERS[picks[0]]
    return (f"Build thread: Say: \"I'd run it on {spoken} at high effort, with {spoken} helpers at high too. {helpers}\" "
            f"Ask: \"Sound good?\" On yes, give --builder {builder} --subagents {builder.split(':')[1]}.")


def write_build_preferences(parts, subagents):
    """Write the build thread and its subagents into the person's model preferences, in one section of their own.
    A missing file starts from a short template. Return one line."""
    family = {builder.split(":")[1]: word for _, builder, _, word in BUILDERS.values()}
    section = (f"{PREFERENCES_SECTION}\n\n| Work | Model | Effort | Note |\n|---|---|---|---|\n"
               f"| Rook's build thread | {family.get(parts[1], parts[1])} | {parts[2]} | Chosen in setup on "
               f"{datetime.now():%Y-%m-%d}. |\n"
               + (f"| Build thread subagents | {family.get(subagents, subagents)} | high | Chosen in setup. Change it by "
                  "voice any time, for good or for one job. |\n" if subagents else ""))
    text = PREFERENCES.read_text() if PREFERENCES.exists() else PREFERENCES_TEMPLATE
    start = text.find(PREFERENCES_SECTION)
    if start < 0:
        text = text.rstrip("\n") + "\n\n" + section
    else:
        end = text.find("\n## ", start + 1)
        text = text[:start] + section + ("\n" + text[end + 1:] if end >= 0 else "")
    atomic_write_text(PREFERENCES, text)
    return f"Saved the build thread choice in {PREFERENCES}."


def onboard_scan(as_tool=None):
    """Print what onboarding needs to know before it asks: the system, Rook's agent and memory, the coding tools that
    are installed or running, the machines, and where code lives. as_tool prints a rehearsal stand-in instead of the
    real tools. Reads only."""
    import platform
    saved = read_settings()[0]
    agent = saved.get("agent", "claude")
    print(f"System: {platform.system()}. Rook's agent: {AGENT_NAMES.get(agent, agent)}.")
    keys = settings.talk_keys_in_force(saved, settings.HOLD_KEYS)[0]
    print(f"Talk keys now: {', '.join(keys) or 'none'}.")
    name, shown = None, False
    if keys:  # The overlay shows the key until Rook listens. No overlay: nothing.
        name = re.sub(r"(?<=[a-z])(?=[A-Z0-9])", " ", keys[0]).replace("Ctrl", "Control")
        if platform.system() == "Darwin":
            name = name.replace("Alt", "Option").replace("Meta", "Command")
        shown = relay.guide({"text": f"Hold {name} to answer", "until": "listening"})
    print("Hello. Say: \"Hi, I'm Rook. Well, that's my name, but you can call me whatever you want. I'm going to "
          "live on your computer and work alongside you, so let's take a few minutes to get to know each other. "
          "Anything we set up now, you can change later just by asking."
          + (f" When you want to talk to me, hold {name} while you speak, or tap it once to start and again to stop."
             if name else "") + (" It's written under me on screen." if shown and platform.system() != "Darwin" else "")
          + "\"")
    # Each part's words for the person, so the skill says them as written.
    mode = saved.get("permission_mode")
    if agent == "pi":  # Pi has no permission modes, so Rook offers none. The person's own Pi extensions can ask.
        print("Permissions now: Pi has no permission modes, so give no --permissions. Say: \"On Pi I act without "
              "asking first. Pi's own extensions can add checks, if you want them.\"")
    else:
        print(f"Permissions now: {mode or 'none saved, so full'}. Say: \"" + {
            "careful": "Right now I check with you before I change files or run commands.",
            "automatic": "Right now I act alone, and a safety check stops risky actions.",
            "rook": "Right now I act alone, and a safety check stops risky actions.",
            "inherit": "Right now I follow your coding agent's own settings."}.get(
            mode, "Right now I act without asking first. If you'd rather I check with you before I change files or "
                  "run commands, say so, now or any time.") + "\"")
    pick = RECOMMENDED.get(agent)
    if not pick:
        print(f"Model: {AGENT_NAMES.get(agent, agent)} picks its own, so give no --model or --effort.")
    elif (saved.get("agent_model"), saved.get("agent_effort")) == pick[:2]:
        print(f"Model: already {pick[2]} at {pick[1]} effort, the one we recommend. Give no --model or --effort.")
    else:
        print(f"Model: now {saved.get('agent_model') or 'the agent default'}. Say: \"I think best on {pick[2]} at "
              f"{pick[1]} effort, so that's what I'd recommend.\" Ask: \"Shall I use it?\" On yes, give --model "
              f"{pick[0]} --effort {pick[1]}.")
    # Window capture needs the platform's support and Hyprland's window list. Rook's agent may have started before the
    # session's variables reached Rook, so the scan looks for the session itself.
    desk.find_session()
    capture = desk.PLATFORM.supports_capture and bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"))
    goes = ("It goes only to Claude, with your words, and I keep no copy on your computer." if agent == "claude" else
            "It goes only to the model Pi runs on, with your words, and I keep no copy on your computer."
            if agent == "pi" else
            f"It goes only to {'OpenAI' if agent == 'codex' else 'Google'}, with your words. My agent keeps it in a "
            "private folder until the session ends, and then I wipe that folder.")
    print("Screenshots: " + (
        "Rook can take one of the focused window here. Say: \"Here's how my screenshots work. When you talk to me, I "
        f"take one screenshot of the window you're in, never the whole screen. {goes} I send nothing to the people who "
        "made me. Say go dark any time, and I stop taking screenshots and hold my news until you call me back. To turn "
        "them off for good, just say: turn off screenshots.\"" if capture else
        "Rook cannot take screenshots on this system yet. Say: \"On this computer I can't see your screen yet, so I "
        "work from your words. I send nothing to the people who made me.\" Give --screenshots on."))
    if memory.is_shared():
        print("Memory: the shared memory system is installed here. Say so briefly, and give --memory rook.")
    else:
        tidy, claude, timers = agent in TIDY_AGENTS, bool(shutil.which("claude")), bool(shutil.which("systemctl"))
        print("Memory: Rook's own memory. " + ("Its nightly tidy runs with this agent. " if tidy else
                                               f"Its nightly tidy does not run with {AGENT_NAMES.get(agent, agent)} "
                                               "yet: notes are saved and loaded, not tidied. ")
              + ("The shared system for all Claude Code projects can be installed." if claude and timers
                 else "The shared system needs systemd for its nightly tidy, and this computer has none." if claude
                 else "The shared system needs Claude Code, which is not installed.") + " Say: \""
              + ("Each night, a dreaming run tidies and repairs what I learned that day. It uses your own model quota. "
                 if tidy else "")
              + ("The shared version also switches off Claude Code's own automatic memory, so only one memory keeps notes.\"" if claude and timers
                 else "The shared version isn't available on this computer yet, so for now my memory is just mine.\" "
                      "Give --memory rook." if claude
                 else "The shared version needs Claude Code, so for now my memory is just mine.\" Give --memory rook."))
    print(build_thread_line(as_tool == "t3" if as_tool else bool(shutil.which("t3"))))
    if as_tool:
        print(f"Rehearsal stand-in for {as_tool}, not this machine:")
        print("\n".join(STAND_INS[as_tool]))
        if as_tool in ("pi", "none"):
            print(NO_ORCHESTRATOR)
        return
    t3 = "not installed"
    if shutil.which("t3"):
        try:
            pid = json.loads((Path.home() / ".t3/userdata/server-runtime.json").read_text()).get("pid")
            os.kill(int(pid), 0)
            t3 = "installed and running. Read its projects with t3_project_list"
        except (OSError, ValueError, TypeError):
            t3 = "installed, not running"
    print(f"T3 Code: {t3}.")
    line = "not installed"
    if shutil.which("herdr"):
        import herdr
        try:
            agents = herdr.call(None, "agent", "list", timeout=5).get("agents") or []
            line = f"installed and running, with {len(agents)} agents" + "".join(
                f"\n  {a.get('name')}: {a.get('kind')}, {a.get('state')}, {a.get('cwd') or a.get('folder') or '?'}"
                for a in agents[:8])
        except Exception:
            line = "installed, not running"
    print(f"Herdr: {line}." + (" Say: \"Herdr's here, it just isn't running. Open a terminal and type herdr once to "
                               "start it.\" Ask: \"Can you tell me when it's going?\" Then run onboard --scan again."
                               if line == "installed, not running" and not t3.startswith("installed and running") else ""))
    sessions = sorted((Path.home() / ".pi/agent/sessions").glob("*/*.jsonl"))
    print("Pi: " + ("not installed." if not shutil.which("pi") else f"installed, with {len(sessions)} saved sessions."))
    if t3 == line == "not installed":
        print(NO_ORCHESTRATOR)
    print(f"Machines Rook can reach: {', '.join(watch.machines())} (this one: {watch.local_machine()}).")
    found = []
    for name in CODE_FOLDERS:
        folder = Path.home() / name
        if folder.is_dir():
            repos = sum(1 for child in folder.iterdir() if (child / ".git").exists())
            found.append(f"~/{name} ({repos} git projects)")
    loose = sum(1 for child in Path.home().iterdir() if child.is_dir() and (child / ".git").exists())
    print(f"Code folders: {', '.join(found) or 'none found'}. Git projects directly in your home folder: {loose}.")
    folder, source = projects_folder_in_force(saved)
    print(f"New projects start in: {folder} ({source}).")
    lines, can = shared_agents(dry=True)
    links = [line for line in lines if " linked" in line or "left" in line]
    linked = bool(links) and all(line.endswith("already linked.") for line in links)  # No agent shares nothing.
    agents_here = sum((Path.home() / agent[1]).is_dir() for agent in SHARED_AGENTS)
    print("Shared agent setup: " + (
        "no coding agent is installed yet. Say: \"You have no coding agents installed yet, so there's nothing to share.\" "
        "Give --shared-agents no."
        if not agents_here else
        "only one coding agent is here, so there is nothing to share yet. Ask nothing, and give --shared-agents no."
        if agents_here == 1 else
        "you already share one setup. Say: \"You already share one setup across your coding agents, just as I'd "
        "recommend.\" Give --shared-agents no." if not can and linked and lines else
        "can be linked safely. Say: \"One more good habit: one shared instruction file and one shared skills folder "
        "for all your coding agents, so they all follow the same rules.\"" if can else
        "nothing can be linked safely. Say: \"Your coding agents each keep their own setup, so I'll leave them as they "
        "are.\" Give --shared-agents no.")
          + ("".join(f"\n  {line}" for line in lines) if agents_here > 1 else ""))


TOUR = (  # The optional tour after setup: one sentence and one thing to try per feature, or None.
    ("I hand coding work to your coding tool's threads, and tell you when one finishes or needs you.",
     "start a thread in one of your projects to fix a small typo"),
    ("Questions from your threads wait in my mailbox until you answer them.", "what needs me?"),
    ("Say go dark, and I stay quiet until you call me back.", None),
    ("I set timers, draw diagrams, show pictures and videos, and pause what's playing.", "set a timer for five minutes"),
    ("I keep my own small set of skills and don't load the rest of your computer's, so I stay quick, and you can "
     "ask me for a new ability.", None),
    ("You can change my voice, or the agent I run on, whenever you like.", "try a different voice"))


def onboard_command(argv):
    """Check every onboarding choice, then apply them. One settings write holds every setting, so a refused apply
    leaves them as they were. The voice, the talk key and screenshots apply at once; the name, the pronouns and
    the permission mode at Rook's next start. A talk key or permission mode left out keeps a saved one. Then, as asked: the projects folder is made when missing, the shared
    memory is installed, and a build thread is started in T3 Code. --dry-run prints what it would do and changes
    nothing. --scan prints what onboarding detects, and --as KIND makes it a rehearsal stand-in."""
    if argv[:1] == ["--scan"]:
        rest = argv[1:]
        if rest and (len(rest) != 2 or rest[0] != "--as" or rest[1] not in STAND_INS):
            sys.exit("Usage: relay.py onboard --scan [--as t3|herdr|pi|none]")
        return onboard_scan(rest[1] if rest else None)
    if argv == ["--tour"]:
        print("Give one feature per turn in one sentence, with its \"Try it now\" when it has one, and ask \"More?\" "
              "between features. \"Stop\" ends the tour at once.")
        for number, (line, attempt) in enumerate(TOUR, 1):
            print(f"{number}. {line}" + (f" Try it now: \"{attempt}\"" if attempt else ""))
        return
    choices = {"name": None, "assistant-name": None, "pronouns": None, "key": None, "permissions": None, "voice": OFFERED[0],
               "model": None, "effort": None, "orchestrator": None, "projects-folder": None, "memory": None, "screenshots": None,
               "builder": "skip", "subagents": None, "as": None, "everystate": "no", "shared-agents": "no"}
    dry = "--dry-run" in argv
    args = [a for a in argv if a != "--dry-run"]
    while args:
        flag = args.pop(0)
        if flag[2:] not in choices or not flag.startswith("--") or not args:
            sys.exit("Usage: relay.py onboard [--name NAME] [--assistant-name NAME] [--pronouns he|she|they] [--key KEY[,KEY]] [--permissions MODE] "
                     "[--model MODEL] [--effort EFFORT] [--voice VOICE] [--orchestrator t3|herdr|pi|none] [--projects-folder PATH] [--memory shared|rook] "
                     "[--screenshots on|off] [--builder skip|THREAD|PROVIDER:MODEL:EFFORT] [--subagents MODEL] "
                     "[--everystate yes|no] [--shared-agents yes|no] [--as t3|herdr|pi|none] [--dry-run]")
        choices[flag[2:]] = args.pop(0).strip()
    saved = read_settings()[0]
    name = choices["name"]
    if name is not None and not valid({"owner_name": name}):
        sys.exit(f"{name!r} is not a name Rook can use. Give a name of up to 40 letters.")
    me = choices["assistant-name"]
    if me is not None and not valid({"assistant_name": me}):
        sys.exit(f"{me!r} is not a name Rook can take. Give a name of up to 40 letters.")
    pronouns = choices["pronouns"] and choices["pronouns"].lower()
    if pronouns is not None and pronouns not in settings.OWNER_PRONOUNS:
        sys.exit(f"{pronouns} are not pronouns Rook knows. Choose {', '.join(settings.OWNER_PRONOUNS)}.")
    # Left out, the talk keys and the permission mode keep what is saved (rook included), else the defaults.
    keys = settings.talk_keys_in_force(saved, settings.HOLD_KEYS)[0] if choices["key"] is None else None  # "Keep it".
    available = settings.MAC_TALK_KEY_NAMES if desk.IS_MAC else TALK_KEYS
    wanted = [available[0]] if choices["key"] is None else [k.strip() for k in choices["key"].split(",") if k.strip()]
    key = [next((k for k in available if fold(k) == fold(name)), None) for name in wanted]  # Several keys: a comma list.
    if not key or None in key:
        sys.exit(f"{choices['key']} is not a talk key Rook offers. Choose {', '.join(available)}.")
    key = list(dict.fromkeys(key))
    mode = (saved.get("permission_mode", settings.PERMISSION_MODE) if choices["permissions"] is None
            else choices["permissions"].lower())
    if mode not in PERMISSION_MODES and not (choices["permissions"] is None and mode in settings.PERMISSION_MODES):
        sys.exit(f"{mode} is not a permission mode. Choose {', '.join(PERMISSION_MODES)}.")
    model, effort = choices["model"], choices["effort"]  # Rook's own agent, from the next start.
    if model is not None and "agent_model" not in valid({"agent": saved.get("agent", "claude"), "agent_model": model}):
        sys.exit(f"{model} is not a model of Rook's agent, {saved.get('agent', 'claude')}.")
    if effort is not None and effort not in settings.EFFORTS:
        sys.exit(f"--effort takes {', '.join(settings.EFFORTS)}.")
    if choices["as"] and (not dry or choices["as"] not in STAND_INS):
        sys.exit("--as takes t3, herdr, pi or none, and only with --dry-run: a rehearsal changes nothing.")
    orchestrator = (choices["orchestrator"] or choices["as"] or saved.get("orchestrator") or settings.ORCHESTRATOR).lower()
    if orchestrator not in settings.ORCHESTRATORS:
        sys.exit(f"{orchestrator} is not a coding tool Rook knows. Choose {', '.join(settings.ORCHESTRATORS)}.")
    folder = choices["projects-folder"]
    if folder is not None:
        folder = os.path.abspath(os.path.expanduser(folder))
        if os.path.exists(folder) and not os.path.isdir(folder):
            sys.exit(f"{folder} is a file, not a folder. Choose another place for projects.")
    shared = choices["memory"]
    if shared not in (None, "shared", "rook"):
        sys.exit("--memory takes shared or rook.")
    if shared == "shared" and not shutil.which("claude"):
        sys.exit("The shared memory needs Claude Code for your projects, and it is not installed. Keep Rook's own "
                 "memory: give --memory rook.")
    # Left out, screenshots keep the saved value, else on.
    shots = (saved.get("screenshots") if saved.get("screenshots") in settings.SCREENSHOTS else settings.SCREENSHOTS[0]) \
        if choices["screenshots"] is None else choices["screenshots"].lower()
    if shots not in settings.SCREENSHOTS:
        sys.exit("--screenshots takes on or off.")
    builder = choices["builder"]
    parts = builder.split(":")
    word = r"[A-Za-z0-9][\w.-]*"  # Never a flag: no leading dash, no spaces.
    t3_build = (len(parts) == 3 and parts[0] in EFFORT_OPTIONS and re.fullmatch(word, parts[1])
                and parts[2] in settings.EFFORTS)
    if builder != "skip" and not t3_build and not re.fullmatch(rf"{word}(:{word})?", builder):
        sys.exit("--builder takes skip, a thread id, or provider:model:effort, such as claudeAgent:claude-opus-5-5:high, "
                 f"with a provider of {' or '.join(EFFORT_OPTIONS)} and an effort of {', '.join(settings.EFFORTS)}.")
    if choices["everystate"] not in ("yes", "no") or choices["shared-agents"] not in ("yes", "no"):
        sys.exit("--everystate and --shared-agents take yes or no.")
    unchosen = fold(choices["voice"]) == "none"  # The audition could not play: the voice stays as it is.
    voice = None if unchosen else match_voice(choices["voice"], [{"name": m} for m in MEDIUM_VOICES])[0]
    setting = "voice_medium" if voice else "voice"
    if not voice and not unchosen:
        catalogue, error = voices()
        voice, problem = match_voice(choices["voice"], catalogue) if catalogue else (None, error)
        if not voice:
            sys.exit(f"There is no voice named {choices['voice']!r}. The medium voices are {', '.join(MEDIUM_VOICES)}. "
                     f"{problem}")
    engine = "medium" if setting == "voice_medium" else "small"
    now = {"talk_keys": keys if keys is not None else key, "screenshots": shots, **({} if unchosen else {setting: voice, "voice_engine": engine}),
           **({"projects_folder": folder} if folder else {})}
    later = {"permission_mode": mode, "orchestrator": orchestrator, **({"owner_name": name.strip()} if name else {}),
             **({"owner_pronouns": pronouns} if pronouns else {}),
             **({"assistant_name": me.strip()} if me else {}),
             **({"agent_model": model} if model else {}), **({"agent_effort": effort} if effort else {})}
    words = ", ".join(f"{k} {', '.join(v) if isinstance(v, list) else v}" for k, v in {**later, **now}.items())
    timing = ("The voice, the talk key and screenshots apply at once" if not unchosen else "The talk key and "
              "screenshots apply at once, and the voice stays as it is") + "; the name, the pronouns, the permission mode " \
        "and the coding tool at Rook's next start."
    py = f"{sys.executable} {SCRIPT}"
    steps = []  # What a real apply does after the settings, in order.
    if t3_build and orchestrator == "t3" and settings.build_thread_details(saved).get("builder"):
        steps.append("start no build thread, because Rook already has one")
    elif t3_build and orchestrator == "t3":
        steps.append(f"add Rook's folder to T3 Code with t3 project add {ROOK_ROOT} --title Rook, if it is missing, then "
                     f"start its build thread with t3 thread start {ROOK_ROOT} - --json --title \"Rook builder\" "
                     f"--provider {parts[0]} --model {parts[1]} --option {EFFORT_OPTIONS[parts[0]]}={parts[2]}")
    elif t3_build:
        steps.append("record the build thread choice for later: " + ("there is no coding tool yet" if orchestrator == "none"
                     else f"{orchestrator} cannot start one with a chosen model yet"))
    elif builder != "skip":
        steps.append(f"record thread {builder} as Rook's build thread")
    if t3_build:
        steps.append(f"write the build thread choice to {PREFERENCES}")
    if folder and not os.path.isdir(folder):
        steps.append(f"make the folder {folder}")
    if shared == "shared" and not memory.is_shared():
        steps.append(f"install the shared memory with {py} memory install-shared")
    if choices["shared-agents"] == "yes":
        steps.append("link the coding agents to one shared setup: " + " ".join(shared_agents(dry=True)[0]))
    if choices["everystate"] == "yes":
        try:
            if not (t3_build or builder != "skip" or settings.build_thread_details(saved).get("builder")):
                raise StepFailed("there is no build thread for it")
            steps.append(install_everystate(dry=True))
        except StepFailed as error:
            steps.append(f"not install Everystate, because {error}")
    if dry:
        print(f"Dry run: nothing changed. A real apply sets {words}. {timing}"
              + (" Then it would " + "; then ".join(steps) + "." if steps else "")
              + (" The shared memory is already installed here." if shared == "shared" and memory.is_shared() else "")
              + (" Rook keeps its own memory." if shared == "rook" else ""))
        return
    old = CONFIG.read_text() if CONFIG.exists() else None
    saved, previous = read_settings()
    old_mode = stat.S_IMODE(CONFIG.stat().st_mode) if old is not None else 0o600
    changed = {**later, **now}
    try:
        write_settings({**saved, **changed},
                       {**previous, **{k: saved[k] for k in changed if k in saved and saved[k] != changed[k]}})
    except (OSError, ValueError) as exc:
        sys.exit(f"Could not save the choices, so nothing changed: {str(exc).rstrip('.')}.")
    answer = ask_rook("apply") if ask_rook("get") else {"ok": True, "stopped": True}
    if not answer or not answer.get("ok"):
        if old is None:
            CONFIG.unlink(missing_ok=True)
        else:
            atomic_write_text(CONFIG, old, mode=old_mode)
        sys.exit(f"Rook could not apply the choices, so nothing changed: "
                 f"{(answer or {}).get('error', 'Rook stopped answering.')}")
    done = [f"Set {words}. " + ("Rook is not running, so all of it takes effect at its next start."
                                if answer.get("stopped") else timing)]
    missed = []

    def step(what, action):
        """Run one step alone. A failure becomes one plain line, and the steps after it still run."""
        try:
            line = action()
            if line:
                done.append(line)
        except Exception as error:  # noqa: BLE001 - no step may stop the others, or reach the person as a traceback.
            missed.append(f"I could not {what}, because {plain_reason(error)}.")

    def make_folder():
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
            return f"Made the projects folder {folder}."
        return None

    def install_memory():
        if memory.is_shared():
            return "The shared memory is already installed here."
        ok, message = memory.install_shared()
        if not ok:
            raise StepFailed(message.rstrip(".").removeprefix("Refused: "))
        return message

    def record_builder(entry):
        saved_now, previous_now = read_settings()
        write_settings({**saved_now, "build_threads": {**saved_now.get("build_threads", {}), "builder": entry}},
                       previous_now, updated={"build_threads"}, updated_build_threads={"builder"})

    def builder_threads():
        """Rook's build threads in T3 Code, newest first, by their title. Raise StepFailed when T3 Code cannot say."""
        listed = subprocess.run(["t3", "thread", "list", "--project", str(ROOK_ROOT), "--json"], capture_output=True,
                                text=True, timeout=20)
        if listed.returncode != 0:  # Without the list, a start could make a second thread.
            raise StepFailed("T3 Code could not list its threads, so I could not check for one started earlier")
        return [t["threadId"] for t in json.loads(listed.stdout) if t.get("title") == BUILDER_TITLE]

    def start_builder():
        existing = settings.build_thread_details(read_settings()[0]).get("builder")
        if existing:
            thread = existing if isinstance(existing, str) else existing["thread"]
            return f"Rook's build thread {thread} already exists, so I started no other."
        entry = {"machine": watch.local_machine(), "provider": parts[0], "model": parts[1], "effort": parts[2],
                 **({"subagents": choices["subagents"]} if choices["subagents"] else {})}
        if BUILDER_STARTING.exists():  # An earlier apply began a start: find its thread before starting another.
            found = builder_threads()
            if found:
                record_builder({**entry, "thread": found[0]})
                BUILDER_STARTING.unlink(missing_ok=True)
                return f"Found the build thread {found[0]} that an earlier setup started, and recorded it."
            if time.time() - BUILDER_STARTING.stat().st_mtime < STARTING_STALE:
                raise StepFailed("an earlier start may still be under way in T3 Code. Ask me again in a few minutes")
        subprocess.run(["t3", "project", "add", str(ROOK_ROOT), "--title", "Rook"], capture_output=True, text=True,
                       timeout=20)  # Already there is fine.
        brief = BUILD_BRIEF.format(owner=name or OWNER, root=ROOK_ROOT, python=sys.executable,
                                   subagents=f" Use {choices['subagents']} at high effort for your sub-agents, unless told otherwise."
                                   if choices["subagents"] else "")
        atomic_write_text(BUILDER_STARTING, datetime.now().isoformat(timespec="seconds") + "\n")
        try:  # T3 Code's own default access for new threads: Rook names no mode.
            started = subprocess.run(["t3", "thread", "start", str(ROOK_ROOT), "-", "--json", "--title", BUILDER_TITLE,
                                      "--provider", parts[0], "--model", parts[1], "--option", f"{EFFORT_OPTIONS[parts[0]]}={parts[2]}"],
                                     input=settings.render(brief), capture_output=True, text=True, timeout=T3_WAIT)
        except subprocess.TimeoutExpired:
            raise StepFailed("T3 Code did not answer in time. The thread may still start: ask me to run setup again "
                             "in a few minutes, and I will find it") from None
        except BaseException:
            BUILDER_STARTING.unlink(missing_ok=True)
            raise
        thread = json.loads(started.stdout).get("threadId") if started.returncode == 0 else None
        if not thread:
            BUILDER_STARTING.unlink(missing_ok=True)
            raise StepFailed("T3 Code refused it: " + ((started.stderr or started.stdout).strip()[:160] or "no reason given"))
        record_builder({**entry, "thread": thread})  # At once, before any other step.
        BUILDER_STARTING.unlink(missing_ok=True)
        return f"Started Rook's build thread {thread} in T3 Code."

    if t3_build and orchestrator == "t3":
        step("start the build thread", start_builder)
    elif t3_build:
        done.append("Recorded the build thread choice. " + ("There is no coding tool yet" if orchestrator == "none" else
                    f"{orchestrator} cannot start one with a chosen model yet") + ", so it is set up later.")
    elif builder != "skip":
        def record_named():
            record_builder({"thread": builder, "machine": watch.local_machine()})
            return f"Recorded thread {builder} as Rook's build thread."
        step("record the build thread", record_named)
    if t3_build:
        step("save the build thread choice", lambda: write_build_preferences(parts, choices["subagents"]))
    step("make the projects folder", make_folder)
    if shared == "shared":
        step("install the shared memory", install_memory)
    if choices["shared-agents"] == "yes":  # Before Everystate, so its skill lands in the shared folder.
        def link_agents():
            lines = shared_agents(dry=False)[0]
            missed.extend(f"I could not finish the shared setup: {line}" for line in lines if "stopped" in line)
            return " ".join(line for line in lines if "stopped" not in line)
        step("link the shared setup", link_agents)
    if choices["everystate"] == "yes":
        def everystate():
            if not settings.build_thread_details(read_settings()[0]).get("builder"):
                raise StepFailed("there is no build thread for it")
            return install_everystate(dry=False)
        step("install Everystate", everystate)
    step("save the onboarding record", lambda: atomic_write_text(ONBOARDING, json.dumps({
        "recorded": datetime.now().isoformat(timespec="seconds"), "applied_now": now, "at_next_start": later,
        "memory": shared, "builder": builder, "subagents": choices["subagents"], "result": done[1:],
        "not_done": missed}, indent=2) + "\n"))
    print(" ".join(done) + ("" if not missed else " Not done: " + " ".join(missed)
                            + " Everything else is done. To finish the rest later, ask me to run setup again: "
                              "it keeps what is already done."))
    relay.guide(None)  # Setup is over: the overlay drops its guide.
