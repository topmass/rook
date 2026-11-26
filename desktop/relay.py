"""Hand ⟦owner⟧'s requests from Rook to a build thread, give Rook messages from any T3 thread, and change
the few settings Rook may change itself.

relay.py handoff [--to NAME] [--print [--work WISH [--project NAME] [--machine NAME] [--thread ID] [--title TITLE] [--done LINE]]] [TEXT|-]
                            Send a request to a build thread through the t3 command: the first in settings, or
                            another with --to NAME. The command can only queue it. With --print, print the framed request
                            and send nothing, so Rook can send it with the T3 tool. With --print and --work,
                            also add a work entry, put its number in the brief, and print its work line first.
                            Line one gives the clientRequestId to send it with.
relay.py handoff --again KEY
                            Print a handoff that did not reach its thread, to send again with the same key.
relay.py device pair        Print a one-use code that pairs a phone with Rook. It lasts ten minutes.
relay.py device list        List the paired devices.
relay.py device revoke NAME Unpair a device by its name or id. Its open stream closes at once.
relay.py tell [--urgent] [TEXT|-]
                            Give the running Rook a message through its inbox socket. Any thread may use it.
                            With --urgent, Rook pauses playing video instead of waiting for playback to stop.
relay.py media [status|pause|play|toggle] [PLAYER]
                            Show active desktop media players in one line each, or pause, play, or toggle one.
relay.py note [TEXT|-]      Leave the reason for a restart, which the next Rook start reports.
relay.py get [KEY]          Print Rook's settings and where each value comes from.
relay.py voices             List the voices Rook can speak with.
relay.py fonts              List the fonts Rook can show its text in.
relay.py dusts              List the looks of the dust that Rook's light theme draws.
relay.py themes             List the presence theme packs installed under themes/ and ~/.config/rook/themes/.
relay.py forge <new|bake|list> ...
                            Create, bake, or list Rook's own shader icons and theme packs in ~/.config/rook/themes/.
relay.py set KEY VALUE [--say TEXT]
                            Change one setting and apply it in the running Rook. VALUE may be "previous".
                            With --say, Rook speaks TEXT as part of the change: a new voice says it, and a
                            new font shows it as a caption. agent, agent_model, and agent_effort only save:
                            they take effect at Rook's next start.
relay.py audition           Play two medium voices, Late-Night Architect then Velvet Wit, through the running
                            Rook. Without the medium voice it plays two small voices. It saves nothing.
relay.py onboard --scan [--as t3|herdr|pi|none]
                            Print what onboarding detects: system, agent, memory, coding tools, machines, code
                            folders and the shared agent setup. --as prints a rehearsal stand-in for that tool.
relay.py onboard --tour     Print the optional tour after setup: one line and one thing to try per feature.
relay.py onboard [CHOICES] [--dry-run]
                            Apply the onboarding choices: one settings write, then the projects folder, the shared
                            agent setup, the shared memory, Everystate and a T3 build thread, as chosen. A record goes
                            to ~/.config/rook/onboarding.json. --dry-run prints what it would do and changes nothing.
                            Run relay.py onboard --help for the choices.
relay.py shared-agents [--dry-run]
                            Link each coding agent's instruction file and skills folder to ~/.agents, losing nothing.
relay.py watch THREAD [--machine NAME] [--title TITLE]
                            Have Rook watch a T3 thread and say when it finishes, stops, or needs ⟦owner⟧.
relay.py watching           List the threads Rook watches.
relay.py threads [--json]   List Rook's thread roster: every open, unsettled or recently active T3 thread and Herdr
                            agent, with machine, project, title, status and id. It reads no thread, so it answers
                            at once. It needs a running Rook.
relay.py herdr agents       List every Herdr agent here and on the saved Herdr machines: name, kind, state
                            (working, blocked, done, idle or unknown), folder and machine.
relay.py herdr read AGENT [--machine NAME] [--lines N]
                            Print a Herdr agent's state and the last N lines of its screen, 40 by default.
relay.py herdr send AGENT [--machine NAME] TEXT|-
                            Prompt a Herdr agent once, only when it is idle or done, and watch it. A send whose
                            outcome is unknown is recorded and never sent again.
relay.py herdr start FOLDER --kind KIND [--model MODEL] [--name NAME] [--machine NAME] TEXT|-
                            Open a new Herdr workspace for FOLDER without focus, start a KIND agent there (claude,
                            codex, pi and others), send it TEXT through the same guard, and watch it. --model passes
                            the agent its own --model flag. With --machine, FOLDER must be absolute or start with ~/,
                            and it is not expanded here.
relay.py herdr install [--dry-run]
                            Install Herdr for this user with its official installer, then check that it runs.
relay.py pi sessions [--limit N]
                            List Pi's newest saved sessions, 10 by default. Read only.
relay.py pi read SESSION [--messages N]
                            Print the last N messages, 6 by default, of a Pi session named by its id or a prefix.
relay.py pi t3-login        Sign Pi in to T3's tools, in a terminal. Restart Rook after.
relay.py inbox [--all] [--json]
                            Show T3 threads that need ⟦owner⟧, waiting work entries, and open PRs.
                            Order: T3 threads, waiting work, ready PRs, failing CI, then draft PRs.
                            Ignored or snoozed PRs leave the default listing. --all shows them.
                            With --json, print every shown item as JSON.
relay.py mailbox list [--all] [--sync] [--json]
                            List open mailbox items grouped by priority, with any active focus lock.
                            Each item has a title line and a short description. show ID has the rest.
                            --all includes snoozed and closed items. --sync refreshes live sources first.
relay.py mailbox show ID    Show every field of one mailbox item.
relay.py mailbox add --kind reminder|decision|review|needs --summary TEXT [--detail TEXT] [--thread ID]
                     [--machine NAME] [--project NAME] [--run ID]
                            Add a mailbox item and print its id. A T3 thread on this machine may add for itself.
relay.py mailbox answer ID TEXT
                            Record ⟦owner⟧'s short answer and close the item. Needs entries stay in T3 Code.
relay.py mailbox dismiss ID [REASON]
                            Dismiss a mailbox item with an optional reason.
relay.py mailbox done ID [REASON]
                            Mark a mailbox item done.
relay.py mailbox snooze ID [--until TIME|DURATION]
                            Snooze a mailbox item until a clock time, duration, or until ⟦owner⟧ wakes it.
relay.py mailbox wake ID    Wake a snoozed or dismissed mailbox item back to open.
relay.py mailbox asked ID   Mark an item as told to ⟦owner⟧. Only Rook's agent may run this.
relay.py mailbox pr ignore|snooze|wake OWNER/REPO#N [--until TIME|DURATION]
                            Ignore, snooze, or wake a pull request overlay.
relay.py mailbox focus set [--thread ID ...] [--project NAME ...] [--topic TEXT] [--for DURATION]
                            Lock the mailbox focus to the named threads or projects.
relay.py mailbox focus status|clear
                            Show or clear the active focus lock.
relay.py mailbox sync       Refresh mailbox items from live T3 and GitHub sources on demand.
relay.py work add WISH --project NAME [--machine NAME] [--thread ID] [--title TITLE] [--done LINE] [--brief TEXT|-]
                            Add one of ⟦owner⟧'s wishes to Rook's work list, just before its send. WISH is a short
                            quote of ⟦his⟧ words. The entry is a draft, and keeps the brief, until the send works:
                            the watcher marks it sent when the send names the thread, or a new thread with the
                            same title. Prints the entry's number. A thread's own add needs no --thread.
relay.py work update [ID] [--state STATE] [--waits TEXT] [--news TEXT] [--link URL] [--commit HASH] [--try TEXT]
                         [--thread ID] [--title TITLE] [--thread-link TEXT] [--done LINE]
                            Change an entry. States: drafted, sent, running, waiting (on ⟦owner⟧, or on --waits),
                            done, live (in use now), and dropped. --try says what ⟦owner⟧ should try or look at.
                            A thread may leave out ID when it has one entry in progress.
relay.py work list [--all | --since today|12h|3d]
                            The open entries, in short lines to read aloud: what waits on ⟦owner⟧ first, then what
                            finished, then what runs. It reads no thread. --all lists every entry. --since lists
                            what finished or went live since then.
relay.py work show ID       Every field of one entry, the kept brief included.
relay.py work close ID      ⟦owner⟧ has heard the outcome, so the entry leaves the list. The file keeps it.
relay.py work drop ID [REASON]
                            ⟦Owner⟧ gave the wish up. The entry leaves the list. The file keeps it.
relay.py project new NAME [--machine NAME] [--path PATH] [--git]
                            Make a project folder on a machine, optionally a git repository, and add it to
                            T3 Code there. Prints "created <machine> <project-id> <path>".
relay.py ask [--no-image] [--test] TEXT|-
                            Give Rook a typed request, exactly as if ⟦owner⟧ had said it, and print Rook's
                            spoken answer. It has the same power as speaking to Rook, so only ⟦owner⟧'s user
                            can reach Rook's socket, which is mode 0600. No T3 thread and not Rook itself
                            may use it. Only a build thread may, with --test: Rook is told it is a test,
                            not ⟦owner⟧, and the log and the replay say so. These refusals guard against
                            mistakes and injected instructions. They are not a security boundary, since
                            everything runs as ⟦owner⟧'s user.
relay.py timer set DURATION|--at TIME [LABEL] [--task TEXT]
                            Have the running Rook set a timer, such as 10m, 90s, 1h30m, --at 3:30 pm, or --at 15:30.
                            When it is due, Rook says so aloud by itself. With --task, Rook instead gets
                            TEXT as a turn when it is due, and carries it out as ⟦owner⟧'s request.
relay.py timer list         List the timers Rook keeps.
relay.py daily-restart      Restart the running Rook once Rook is idle and the nightly dream is done. It tries
                            again every five minutes and gives up after two hours. rook-daily.service runs it.
                            In own-memory mode, it runs relay.py dream first instead of waiting for agent-dream.
relay.py remember TEXT      Append one fact and why to Rook's own memory/incoming.jsonl and return at once.
relay.py dream              Tidy Rook's own memory from incoming.jsonl and new turns. Skips shared mode and
                            empty nights. Backs up the memory folder (keeping seven) before running the agent.
relay.py memory install-shared
                            Install Rook's vendored shared memory system into ~/.agents/, merge SessionStart
                            hooks, add the git ignore line, enable agent-dream.timer, and move Rook's notes.
relay.py memory remove-shared
                            Undo Rook's shared memory install from its manifest, leave all notes in place,
                            and copy Rook's notes back to Rook's own memory folder.
relay.py restart [--timeout DURATION] [--reason TEXT]
                            Ask Rook to reserve a quiet moment and restart it for a deploy. Leave the note
                            first. It waits for a quiet moment and may take minutes, so run it with a long
                            shell timeout. It prints blockers at most once a minute and exits non-zero without
                            restarting after the limit (9m by default). A stopped Rook starts.
relay.py update [TAG|COMMIT]
                            Update an installed Rook: fetch its source, move the checkout to the newest
                            commit or to TAG or COMMIT, run the installer again when the requirements
                            changed (on a Mac, also when the helper changed, to rebuild Rook.app), then
                            restart Rook at a quiet moment. Run it yourself in a terminal, since Rook never
                            updates itself: ~/.local/share/rook/venv/bin/python
                            ~/.local/share/rook/live/desktop/relay.py update
relay.py restart --status   Say whether a restart or overlay reload waits, who asked, why, since when, and what blocks it.
relay.py restart --cancel   Withdraw a waiting restart or overlay reload so its caller exits without restarting.
relay.py mac-access [ask|open|wait|restart GRANT] | done
                            On a Mac: say which permissions Rook.app has, show Apple's prompt for one, or open
                            its System Settings list. restart saves the onboarding step and restarts Rook through
                            launchd after this turn. done forgets the step. GRANT is microphone, input, screen,
                            accessibility, or automation.
relay.py reload overlay [--timeout DURATION] [--reason TEXT]
                            Start a new overlay from the code on disk after Rook grants a quiet moment. It
                            may take minutes while Rook is busy, so run it with a long shell timeout. The
                            conversation, voice, and tool servers keep running, and nothing is spoken. The
                            new overlay keeps the font, dust, dark mode, answer history, and any open file.
                            A reload loses some things: a video in the viewer starts over, and the answer
                            panel closes and forgets where it was dragged. A Rook dragged aside goes home.
                            It gives up without reloading after the limit (9m by default).
                            The smallest reload for each change:
                              desktop/overlay.py               reload overlay
                              desktop/render.py                reload overlay; restart when describe() or
                                                               SCENE_SECONDS changes, which the render tool tells Claude
                              desktop/render_tool.py           restart. Each tool server runs under Claude Code. Its
                                                               mcp_reconnect control request could restart one alone,
                                                               which nothing sends yet
                              skills/                          restart. A skill Rook used already stays as it read it
                              relay.py                         none for its own commands; restart when rook.py uses it
                              rook.py, speech.py, watch.py,    restart
                              prompts
relay.py timer cancel ID|LABEL|all
                            Cancel one timer, or every timer with all.
relay.py dark on [--for DURATION | --until TIME]
                            Turn Rook dark: no swarm at rest, no screenshots, and every message held until dark
                            ends. Without an end, dark lasts until relay.py dark off. On again while dark replaces
                            the end. ⟦Owner⟧'s questions and ⟦his⟧ timers still get answers.
relay.py dark off           End dark now: the swarm comes back, and the held messages follow in one turn.
relay.py dark status        Say whether Rook is dark, since when, and until when.
relay.py show FILE [--title TITLE] [--machine NAME] [--note TEXT]
                            Show ⟦owner⟧ a picture or a video in Rook's media viewer. With --machine, Rook first
                            copies the file from that machine into its runtime folder. Rook's own Claude, and a
                            command ⟦owner⟧ runs, show it at once. A T3 thread's show waits, like any message from a
                            thread, until ⟦owner⟧ is there and Rook is free; Rook then says a sentence about it.
                            A thread puts its explanation in --note, at most 500 characters, and sends no tell
                            about the same file: Rook gets the note with the show and passes on what matters.
relay.py show --close       Close the media viewer.
relay.py clip TEXT|-        Put TEXT on the Wayland clipboard so it stays after the caller exits.
relay.py plugin list        List the installed plugins, whether each is on and why, and any problem.
relay.py plugin enable|disable ID
                            Turn a plugin on or off in settings. The agent sees the change at Rook's next start.
relay.py plugin check       Check every plugin's plugin.json. It exits non-zero when one has a problem.
"""

import ast
from datetime import datetime, timedelta
import importlib.util
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
from urllib.parse import urlparse

import desk
import memory
import settings
from settings import (
    AGENTS, AGENT_SETTINGS, CONFIG, CONFIG_SETTINGS, DATA, DEFAULT_THEME_PACK, DIAGRAM_DANCE, DIAGRAM_DANCES,
    DIAGRAM_ENTRANCE, DIAGRAM_ENTRANCES, DISPLAY_SETTINGS, EFFORTS, FONTS, LISTEN_AFTER,
    LISTEN_AFTERS, MEDIUM_VOICES, MEDIUM_VOICE_URL, OVERLAY, POINT_ALIASES, POINT_SETTINGS,
    RANGES, RECORDING_MINUTES, RECORDING_MINUTES_RANGE, SETTINGS, SMART_TURN, SMART_TURNS,
    SMART_TURN_THRESHOLD, SPEAK_THOUGHTS, SPEAK_THOUGHTS_MODES, STAGES, THEMES_DIR, VOICE_ENGINES,
    _LIGHT_DUSTS_CACHE, atomic_write_text,
    build_threads, diagram_dance_in_force, diagram_entrance_in_force, engine_to_points, fold,
    font_in_force, fonts, light_dust_in_force, light_dusts, listen_after_in_force, match_voice,
    medium_voice, medium_voice_url, points_to_engine, read_settings, recording_minutes_in_force,
    smart_turn_in_force, smart_turn_threshold_in_force, speak_thoughts_in_force, stage_in_force,
    theme_pack_in_force, theme_packs,
    valid, valid_medium_voice_url, voice_python, voices, write_settings,
)
import watch
import work
OWNER = settings.OWNER_TOKEN  # The owner's name, filled in when the text leaves Rook.
OWNER_START = settings.OWNER_START_TOKEN  # The same, as the first word of a sentence.


def pn(phrase, they=None):
    """The owner token for a phrase written with he, such as \"his\" or \"he asks\". A phrase with a verb
    gives its they form too."""
    return settings.token(phrase, they)



# Configured build threads live in ~/.config/rook/settings.json ("build_threads").
# Defaults are empty so a fresh install never points at another person's threads.
BUILD_THREAD = ""
OPUS_THREAD = ""
NEON_THREAD = ""
BUILD_THREADS = {}


def active_build_threads():
    """Return build threads from settings.json (or test overrides in BUILD_THREADS), else {}."""
    return build_threads() or dict(BUILD_THREADS)
SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parent.parent
INBOX = desk.runtime_dir() / "rook.sock"
# Memory-backed, so the note never reaches the disk. Rook ignores a note older than ten minutes.
RESTART_NOTE = INBOX.with_name("rook-restart-note")
# The first line of a request on Rook's socket, such as a settings change, a watch, or a typed request.
# Rook answers it with one JSON line. The name predates the other requests and stays for older Rooks.
REQUEST = "rook-settings:"
# The most one request on Rook's socket may hold, its first line included. Rook refuses anything larger.
SOCKET_LIMIT = 256 * 1024


def projects_folder_in_force(saved, machine=None):
    """Return (folder, source) where a new project starts on machine, this one by default: the projects_folder
    setting on this machine, else the machine table's code folder."""
    machine = machine or watch.local_machine()
    if machine == watch.local_machine() and "projects_folder" in valid({"projects_folder": saved.get("projects_folder")}):
        return saved["projects_folder"], "settings file"
    return watch.machines().get(machine, {}).get("code") or str(Path.home() / "Code"), "machine table"


def theme_now():
    """"light" or "dark", the desktop theme the overlay follows, or None when it cannot be read."""
    return desk.desktop_theme()


def guide(value):
    """Show an onboarding guide on Rook's overlay, or clear it with None. Return whether the overlay showed it."""
    return bool((ask_rook("guide", json.dumps(value), wait=2) or {}).get("shown"))


def ask_rook(command, body="", wait=300):
    """Send a request to the running Rook and return its answer, or None when Rook is not running. A Rook
    that does not answer in time gives an error that says so: it may still be working on the request."""
    data = f"{REQUEST}{command}\n{body}".encode()
    if len(data) > SOCKET_LIMIT:
        return {"ok": False, "error": f"The request is too large: {len(data) // 1024} KB, and Rook takes at most "
                                      f"{SOCKET_LIMIT // 1024} KB."}
    sock = socket.socket(socket.AF_UNIX)
    try:
        sock.settimeout(10)
        sock.connect(str(INBOX))
    except OSError:
        sock.close()
        return None  # Only a connection that fails means Rook is not running.
    try:
        with sock:
            sock.sendall(data)
            sock.shutdown(socket.SHUT_WR)
            # A voice that is not downloaded yet takes a while to load the first time, and a typed request
            # waits for its whole answer.
            sock.settimeout(wait)
            answer = b""
            while chunk := sock.recv(65536):
                answer += chunk
    except TimeoutError:
        return {"ok": False, "timeout": True,
                "error": f"Rook did not answer within {wait} seconds. It may still be working on it."}
    except OSError as error:
        return {"ok": False, "error": f"Rook closed the connection before it answered: {error}"}
    try:
        answer = json.loads(answer)
    except ValueError:
        return {"ok": False, "error": "Rook gave no answer to the request."}
    for key in ("said", "error"):  # Rook's own words, with their owner tokens filled in.
        if isinstance(answer, dict) and isinstance(answer.get(key), str):
            answer[key] = settings.render(answer[key])
    return answer


def utter(*parts, **options):
    """print() for Rook's own words: owner tokens fill in."""
    print(*(settings.render(part) if isinstance(part, str) else part for part in parts), **options)


def leave(message=None):
    """sys.exit() with Rook's own words: owner tokens fill in."""
    sys.exit(settings.render(message) if isinstance(message, str) else message)


def settings_command(argv):
    command, args = argv[0], argv[1:]
    if command == "voices":
        catalogue, error = voices()
        if error:
            leave(error)
        running = ask_rook("get")
        current = running["settings"]["voice"]["value"] if running and running.get("ok") else read_settings()[0].get("voice")
        for voice in catalogue:
            mark = " (current)" if current and fold(voice["name"]) == fold(current) else ""
            utter(f"{voice['name']}{mark}: {voice.get('description') or 'no description'}")
        return
    if command == "fonts":
        listed = fonts()
        if not listed:
            leave("No fonts are installed yet, so Rook keeps its usual look.")
        running = ask_rook("get")
        current = (running["settings"]["font"]["value"] if running and running.get("ok") and "font" in running["settings"]
                   else font_in_force(read_settings()[0])[0])
        for entry in listed:
            mark = " (current)" if entry["name"] == current else ""
            utter(f"{entry['name']}{mark}: {entry.get('description') or 'no description'}")
        return
    if command == "dusts":
        looks, _ = light_dusts()
        if not looks:
            leave("Rook's overlay has no dust looks to choose from.")
        running = ask_rook("get")
        current = (running["settings"]["light_dust"]["value"] if running and running.get("ok")
                   and "light_dust" in running["settings"] else light_dust_in_force(read_settings()[0])[0])
        for look in looks:
            mark = " (current)" if look["name"] == current else ""
            utter(f"{look['name']}{mark}: {look.get('description') or 'no description'}")
        return
    if command == "themes":
        packs = theme_packs()
        if not packs:
            leave("No presence theme packs are installed under themes/.")
        running = ask_rook("get")
        current = (running["settings"]["theme"]["value"] if running and running.get("ok")
                   and "theme" in running["settings"] else theme_pack_in_force(read_settings()[0])[0])
        for pack in packs:
            mark = " (current)" if pack["name"] == current else ""
            utter(f"{pack['name']}{mark}: {pack.get('description') or 'no description'}")
        return
    if command == "get":
        keys = [POINT_ALIASES.get(arg, arg) for arg in args] if args else list(SETTINGS)
        valid_get = set(SETTINGS) | set(CONFIG_SETTINGS)
        if bad := next((arg for arg, key in zip(args, keys)
                        if key not in valid_get and not key.startswith("build_threads.")), None):
            leave(f"{bad} is not a setting Rook can change. Settings: {', '.join((*DISPLAY_SETTINGS, *CONFIG_SETTINGS))}.")
        running = ask_rook("get")
        saved_file = read_settings()[0]
        if running and running.get("ok"):
            values = dict(running["settings"])
        else:
            values = {key: {"value": saved_file[key], "source": "settings file"} if key in saved_file else
                      {"value": None, "source": "Rook's default; Rook is not running, so it cannot say which"}
                      for key in SETTINGS}
            font, source = font_in_force(saved_file)
            values["font"] = {"value": font, "source": source}
            dust, source = light_dust_in_force(saved_file)
            values["light_dust"] = {"value": dust, "source": source}
            theme_pack, source = theme_pack_in_force(saved_file)
            values["theme"] = {"value": theme_pack, "source": source}
            entrance, source = diagram_entrance_in_force(saved_file)
            values["diagram_entrance"] = {"value": entrance, "source": source}
            dance, source = diagram_dance_in_force(saved_file)
            values["diagram_dance"] = {"value": dance, "source": source}
            stage, source = stage_in_force(saved_file)
            values["stage"] = {"value": stage, "source": source}
            listen, source = listen_after_in_force(saved_file)
            values["listen_after"] = {"value": listen, "source": source}
            st_mode, source = smart_turn_in_force(saved_file)
            values["smart_turn"] = {"value": st_mode, "source": source}
            st_thresh, source = smart_turn_threshold_in_force(saved_file)
            values["smart_turn_threshold"] = {"value": st_thresh, "source": source}
            sp_mode, source = speak_thoughts_in_force(saved_file)
            values["speak_thoughts"] = {"value": sp_mode, "source": source}
            minutes, source = recording_minutes_in_force(saved_file)
            values["recording_minutes"] = {"value": minutes, "source": source}
            for key in ("owner_name", "owner_pronouns", "assistant_name"):
                values[key] = {"value": valid({key: saved_file.get(key)}).get(key, settings.OWNER_PRONOUN
                                                                             if key == "owner_pronouns" else
                                                                             settings.ASSISTANT if key == "assistant_name"
                                                                             else None),
                               "source": "settings file" if key in valid(saved_file) else "default"}
            held, source = settings.talk_keys_in_force(saved_file, settings.HOLD_KEYS)
            values["talk_keys"] = {"value": held, "source": source}
            mode, source = settings.permission_mode_in_force(saved_file)
            values["permission_mode"] = {"value": mode, "source": source}
            folder, source = projects_folder_in_force(saved_file)
            values["projects_folder"] = {"value": folder, "source": source}
            for key, default in (("orchestrator", settings.ORCHESTRATOR), ("screenshots", settings.SCREENSHOTS[0])):
                values[key] = {"value": saved_file.get(key, default),
                               "source": "settings file" if key in saved_file else "default"}
            values["recogniser_model"] = {"value": saved_file.get("recogniser_model"), "source": "settings file"
                                          if "recogniser_model" in saved_file else "not set; AirType's own model"}
            for key, default in (("voice_engine", VOICE_ENGINES[0]), ("voice_medium", MEDIUM_VOICES[0])):
                if key not in saved_file:
                    values[key] = {"value": default, "source": "default"}
        values["medium_voice_url"] = (
            {"value": medium_voice_url(saved_file) or None,
             "source": "environment" if os.environ.get("ROOK_MEDIUM_VOICE_URL") or MEDIUM_VOICE_URL
             else ("settings file" if saved_file.get("medium_voice_url") else "not set")}
        )
        values["github_user"] = (
            {"value": saved_file.get("github_user") or None,
             "source": "settings file" if saved_file.get("github_user") else "not set"}
        )
        values["build_threads"] = (
            {"value": saved_file.get("build_threads") or {},
             "source": "settings file" if saved_file.get("build_threads") else "not set"}
        )
        # The thread watcher reads this one from the file at each look, so the file is what is in force.
        values["thread_milestones"] = dict(zip(("value", "source"), settings.thread_milestones_in_force(saved_file)))
        values["plugins"] = {"value": saved_file.get("plugins") or {},
                             "source": "settings file" if saved_file.get("plugins") else "not set"}
        for key in keys:
            if key.startswith("build_threads."):
                name = key[len("build_threads."):].strip().lower()
                tid = (saved_file.get("build_threads") or {}).get(name)
                utter(f"{key}: {tid} ({'settings file' if tid else 'not set'})")
                continue
            value = values.get(key) or {"value": None, "source": "this Rook does not know it yet; it needs a restart"}
            if key in POINT_SETTINGS:
                label, _, hint = POINT_SETTINGS[key]
                if value["value"] is None:
                    utter(f"{label}: None ({value['source']})")
                else:
                    pts = engine_to_points(key, value["value"])
                    raw = f"{value['value'] + 0:g}"
                    utter(f"{label}: {pts} of 100 ({hint}, {value['source']}) [{raw}]")
            else:
                utter(f"{key}: {value['value']} ({value['source']})")
        return
    say = ""
    if "--say" in args:
        at = args.index("--say")
        say, args = " ".join(args[at + 1:]).strip(), args[:at]
    if len(args) < 2:
        leave("Usage: relay.py set KEY VALUE [--say TEXT]")
    raw_key, value = args[0], " ".join(args[1:]).strip()
    key = POINT_ALIASES.get(raw_key, raw_key)
    is_build_thread_key = key.startswith("build_threads.")
    if key not in SETTINGS and key not in ("medium_voice_url", "github_user") and not is_build_thread_key:
        leave(f"{raw_key} is not a setting Rook can change itself. Such changes go through the build thread "
                 f"with relay.py handoff. Settings: {', '.join((*DISPLAY_SETTINGS, 'medium_voice_url', 'github_user', 'build_threads.<name>'))}.")
    label = POINT_SETTINGS[key][0] if key in POINT_SETTINGS else key
    try:
        saved, previous = read_settings(strict=True)
    except (OSError, ValueError) as exc:
        leave(f"Could not read {CONFIG}: {str(exc).rstrip('.')}. Fix the file before changing settings.")

    def save_checked(new_saved, new_previous, *, updated, removed=(), updated_build_threads=None):
        try:
            return write_settings(new_saved, new_previous, updated=updated, removed=removed,
                                  updated_build_threads=updated_build_threads)
        except (OSError, ValueError) as exc:
            leave(f"Could not write {CONFIG}: {str(exc).rstrip('.')}.")

    if key in ("medium_voice_url", "github_user") or is_build_thread_key:
        if key == "medium_voice_url":
            clearing = not value or value.lower() == "clear"
            if clearing:
                left = save_checked({k: v for k, v in saved.items() if k != key}, previous, updated={key}, removed={key})
                url = ""
            else:
                url = valid_medium_voice_url(value)
                if not url:
                    leave("medium_voice_url must be an http:// or https:// address with no username or password.")
                left = save_checked({**saved, key: url}, previous, updated={key})
            note = f" (left alone: {', '.join(left)})" if left else ""
            running = ask_rook("get")
            if running and running.get("ok") and (running["settings"].get("voice_engine") or {}).get("value") == "medium":
                answer = ask_rook("apply", "")
                if answer and answer.get("ok"):
                    if clearing:
                        utter(f"Cleared medium_voice_url. Rook now uses its small voice.{note}")
                    else:
                        utter(f"Saved medium_voice_url = {url}. Rook now uses that voice server.{note}")
                    return
                if clearing:
                    utter(f"Cleared medium_voice_url. It takes effect at Rook's next start.{note}")
                else:
                    utter(f"Saved medium_voice_url = {url}. It takes effect at Rook's next start.{note}")
                return
            if clearing:
                utter(f"Cleared medium_voice_url.{note}")
            else:
                utter(f"Saved medium_voice_url = {url}.{note}")
            return
        if key == "github_user":
            if not value or value.lower() == "clear":
                left = save_checked({k: v for k, v in saved.items() if k != key}, previous, updated={key}, removed={key})
                note = f" (left alone: {', '.join(left)})" if left else ""
                utter(f"Cleared github_user.{note}")
                return
            if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", value):
                leave(f"github_user must be a valid GitHub login (or 'clear' to unset), not {value!r}.")
            left = save_checked({**saved, key: value}, previous, updated={key})
            note = f" (left alone: {', '.join(left)})" if left else ""
            utter(f"Saved github_user = {value}.{note}")
            return
        name = key[len("build_threads."):].strip().lower()
        if not name or not re.fullmatch(r"[a-z0-9_-]+", name):
            leave(f"build_threads name must use letters, digits, '-' or '_', not {name!r}.")
        threads = dict(saved.get("build_threads") or {})
        if not value or value.lower() == "clear":
            threads.pop(name, None)
            if threads:
                left = save_checked({**saved, "build_threads": threads}, previous,
                                    updated={"build_threads"}, updated_build_threads={name})
            else:
                left = save_checked({k: v for k, v in saved.items() if k != "build_threads"}, previous,
                                    updated={"build_threads"}, removed={"build_threads"}, updated_build_threads={name})
            note = f" (left alone: {', '.join(left)})" if left else ""
            utter(f"Cleared build_threads.{name}.{note}")
            return
        if any(ch.isspace() for ch in value):
            leave(f"build_threads.{name} thread id must not contain spaces, got {value!r}.")
        old = threads.get(name)
        kept = [field for field in settings.BUILD_THREAD_FIELDS if field != "thread" and isinstance(old, dict) and field in old]
        threads[name] = {**old, "thread": value} if isinstance(old, dict) else value
        left = save_checked({**saved, "build_threads": threads}, previous,
                            updated={"build_threads"}, updated_build_threads={name})
        note = f" (left alone: {', '.join(left)})" if left else ""
        kept_note = f" It keeps its {', '.join(kept)}." if kept else ""
        utter(f"Saved build_threads.{name} = {value}.{kept_note}{note}")
        return
    if key in AGENT_SETTINGS:
        value = value.lower()
        agent = value if key == "agent" else saved.get("agent", "claude")
        if key == "agent" and value not in AGENTS:
            names = list(AGENTS)
            listed = f"{', '.join(names[:-1])} or {names[-1]}" if len(names) > 2 else " or ".join(names)
            leave(f"agent must be {listed}. {value} is not one of them.")
        if key == "agent_effort" and value not in (*EFFORTS, "default"):
            leave(f"agent_effort must be {', '.join(EFFORTS)} or default. {value} is not one of them.")
        if key == "permission_mode" and value not in (*settings.PERMISSION_MODES, "default"):
            leave(f"permission_mode must be {', '.join(settings.PERMISSION_MODES)} or default. "
                     f"{value} is not one of them.")
        if key == "agent_model" and value != "default" and key not in valid({"agent": agent, key: value}):
            leave(f"{value} is not a model id for {agent}. Its model ids start with {AGENTS[agent]}. "
                     "For another agent's model, set agent first.")
        removed = set()
        if key == "agent":  # The model and effort belong to the agent before.
            saved = {k: v for k, v in saved.items() if k not in ("agent_model", "agent_effort")}
            removed.update(("agent_model", "agent_effort"))
        saved = {k: v for k, v in saved.items() if k != key}  # "default" leaves it out.
        if value == "default":
            removed.add(key)
        left = save_checked({**saved, **({key: value} if value != "default" else {})}, previous,
                            updated={key}, removed=removed)
        note = f" (left alone: {', '.join(left)})" if left else ""
        utter(f"Saved {key} = {value}" + (", with that agent's default model and effort" if key == "agent" else "")
              + f". It takes effect at Rook's next start, not now. Rook never restarts itself. {OWNER_START} or the build "
              f"thread restarts it with relay.py restart, or the daily restart at 04:30 does.{note}")
        return
    if key == "thread_milestones":  # The thread watcher reads the file at each look, so nothing is applied now.
        value = value.strip().lower()
        old = settings.thread_milestones_in_force(saved)[0]
        if value == "previous":
            if key not in previous:
                leave(f"There is no previous {key} to go back to.")
            value = previous[key]
        if value not in settings.THREAD_MILESTONES_MODES:
            leave(f"thread_milestones must be {' or '.join(settings.THREAD_MILESTONES_MODES)}. {value} is not one of them.")
        save_checked({**saved, key: value}, {**previous, key: old}, updated={key})
        utter(f"Saved thread_milestones = {value}. The thread watcher uses it from its next look, within a minute.")
        return
    if key in ("owner_name", "owner_pronouns", "assistant_name"):  # Rook's prompt names both, so these take effect at its next start.
        value = value.strip() if key != "owner_pronouns" else value.strip().lower()
        if not valid({key: value}):
            leave(f"{value!r} is not a name Rook can use. Give a name of up to 40 letters." if key != "owner_pronouns"
                     else f"owner_pronouns must be {', '.join(settings.OWNER_PRONOUNS)}, not {value!r}.")
        write_settings({**saved, key: value}, {**previous, **({key: saved[key]} if key in saved else {})})
        utter(f"Saved {key} = {value}. Rook uses it from its next start. Rook never restarts itself. "
              "The owner or the build thread restarts it with relay.py restart, or the daily restart at 04:30 does.")
        return
    if key == "recogniser_model":  # AirType loads its model once, so the choice takes effect at Rook's next start.
        value = value.strip().lower()
        if not valid({key: value}):
            leave(f"recogniser_model must be {' or '.join(settings.RECOGNISER_MODELS)}, not {value!r}.")
        write_settings({**saved, key: value}, {**previous, **({key: saved[key]} if key in saved else {})})
        try:
            from airtype.asr import model_exists
            from airtype.registry import get_model_spec
            missing = not model_exists(get_model_spec(settings.RECOGNISER_MODELS[value]))
        except ImportError:
            missing = False
        utter(f"Saved {key} = {value}. Rook loads it from its next start. Rook never restarts itself. "
              "The owner or the build thread restarts it with relay.py restart, or the daily restart at 04:30 does."
              + (f" The model is not on this computer yet. Run install/install.sh --recogniser-model {value} "
                 "--recogniser yes to download and check it first." if missing else ""))
        return
    running = ask_rook("get")
    in_force = ({k: v["value"] for k, v in running["settings"].items()} if running and running.get("ok")
                else {"voice_engine": VOICE_ENGINES[0], "voice_medium": MEDIUM_VOICES[0], **saved,
                      "listen_after": listen_after_in_force(saved)[0],
                      "smart_turn": smart_turn_in_force(saved)[0],
                      "smart_turn_threshold": smart_turn_threshold_in_force(saved)[0],
                      "speak_thoughts": speak_thoughts_in_force(saved)[0],
                      "stage": stage_in_force(saved)[0],
                      "recording_minutes": recording_minutes_in_force(saved)[0]})
    from_previous = value.lower() == "previous"
    if from_previous:
        if key not in previous:
            leave(f"There is no previous {label} to go back to.")
        value = previous[key]
    if key == "voice":
        catalogue, error = voices()
        if error:
            leave(error)
        value, error = match_voice(str(value), catalogue)
        if error:
            leave(error)
    elif key in ("orchestrator", "screenshots") and not from_previous:
        value, allowed = value.lower(), settings.ORCHESTRATORS if key == "orchestrator" else settings.SCREENSHOTS
        if value not in allowed:
            leave(f"{key} must be {', '.join(allowed)}. {value} is not one of them.")
    elif key == "projects_folder" and not from_previous:
        value = os.path.abspath(os.path.expanduser(value))
        if not os.path.isdir(value):
            leave(f"{value} is not a folder on this machine.")
    elif key == "talk_keys":
        if not from_previous:  # A comma list of key names, or none for no talk key. +Key adds keys, -Key drops them.
            change, value = (value[0], value[1:]) if value[:1] in ("+", "-") else ("", value)
            names = [] if value.lower() == "none" else [name.strip() for name in value.split(",") if name.strip()]
            fit = [next((k for k in settings.TALK_KEY_NAMES if fold(k) == fold(name)), None) for name in names]
            if None in fit:
                leave(f"{names[fit.index(None)]} is not a talk key Rook knows. Choose from "
                         f"{', '.join(settings.TALK_KEY_NAMES)}, or none.")
            if change:
                held = settings.talk_keys_in_force(saved, settings.HOLD_KEYS)[0]
                fit = held + fit if change == "+" else [k for k in held if k not in fit]
            value = list(dict.fromkeys(fit))
    elif key == "voice_engine":
        value = value.lower()
        if value not in VOICE_ENGINES:
            leave(f"voice_engine must be small or medium. {value} is not one of them.")
    elif key == "voice_medium":
        names = [n for n in (medium_voice("/health") or {}).get("voices", ()) if isinstance(n, str)] or MEDIUM_VOICES
        # The short names first, so "Jarvis" is jarvis-poe and not also the server's folder for it.
        short = [{"name": n} for n in MEDIUM_VOICES if n in names]
        fit = short and match_voice(str(value), short)[0] or match_voice(str(value), [{"name": n} for n in names])[0]
        if not fit:
            leave(f"There is no medium voice named {value!r}. The medium voices are {', '.join(names)}.")
        value = fit
    elif key == "font":
        listed = fonts()
        if not listed:
            leave("No fonts are installed yet, so Rook keeps its usual look.")
        value, error = match_voice(str(value), listed, kind="font")
        if error:
            leave(error)
    elif key == "light_dust":
        looks, _ = light_dusts()
        if not looks:
            leave("Rook's overlay has no dust looks to choose from.")
        value, error = match_voice(str(value), looks, kind="dust")
        if error:
            leave(error)
    elif key == "theme":
        packs = theme_packs()
        if not packs:
            leave("No presence theme packs are installed under themes/.")
        value, error = match_voice(str(value), packs, kind="theme")
        if error:
            leave(error)
    elif key == "diagram_entrance":
        value = value.lower()
        if value not in DIAGRAM_ENTRANCES:
            leave(f"diagram_entrance must be {' or '.join(DIAGRAM_ENTRANCES)}. {value} is not one of them.")
    elif key == "diagram_dance":
        value = value.lower()
        if value not in DIAGRAM_DANCES:
            leave(f"diagram_dance must be {', '.join(DIAGRAM_DANCES[:-1])} or {DIAGRAM_DANCES[-1]}. {value} is not one of them.")
    elif key == "stage":
        value = value.lower()
        if value not in STAGES:
            leave("The desktop stage is shelved, so stage stays off. Rook draws diagrams with its own particles.")
    elif key == "listen_after":
        value = value.lower()
        if value not in LISTEN_AFTERS:
            leave(f"listen_after must be {', '.join(LISTEN_AFTERS[:-1])} or {LISTEN_AFTERS[-1]}. {value} is not one of them.")
    elif key == "smart_turn":
        value = value.lower()
        if value not in SMART_TURNS:
            leave(f"smart_turn must be {' or '.join(SMART_TURNS)}. {value} is not one of them.")
    elif key == "speak_thoughts":
        value = value.lower()
        if value not in SPEAK_THOUGHTS_MODES:
            leave(f"speak_thoughts must be {', '.join(SPEAK_THOUGHTS_MODES[:-1])} or {SPEAK_THOUGHTS_MODES[-1]}. {value} is not one of them.")
    elif key == "smart_turn_threshold":
        if not from_previous:
            low, high = RANGES["smart_turn_threshold"]
            try:
                parsed = float(value)
            except ValueError:
                parsed = float("nan")
            if not low <= parsed <= high:
                leave(f"smart_turn_threshold takes a number from {low:g} to {high:g}, not {value}.")
            value = round(parsed, 4)
    elif key == "recording_minutes":
        if not from_previous:
            low, high = RECORDING_MINUTES_RANGE
            if not re.fullmatch(r"[0-9]+", value) or not low <= int(value) <= high:
                leave(f"recording_minutes takes a whole number from {low} to {high}, not {value}.")
            value = int(value)
    elif not from_previous:
        low = POINT_SETTINGS[key][1]
        if not re.fullmatch(r"[0-9]+", value) or not low <= int(value) <= 100:
            if low == 0:
                leave(f"{label.capitalize()} takes a whole number from 1 to 100, or 0 for silent, not {value}.")
            leave(f"{label.capitalize()} takes a whole number from 1 to 100, not {value}.")
        value = points_to_engine(key, int(value))
    shown = (f"{engine_to_points(key, value)} of 100" if key in POINT_SETTINGS else
             ", ".join(value) or "none" if isinstance(value, list) else value)
    old = None
    old_mode = 0o600
    if CONFIG.exists():
        old_mode = stat.S_IMODE(CONFIG.stat().st_mode)
        old = CONFIG.read_text()
    if key in in_force and in_force[key] is not None and in_force[key] != value:
        previous = {**previous, key: in_force[key]}
    left = save_checked({**saved, key: value}, previous, updated={key})
    left_note = f" (left alone: {', '.join(left)})" if left else ""
    if key == "orchestrator":  # Rook's prompt reads it at its next start, where the herdr plugin is on. Nothing to apply now.
        utter(f"Saved orchestrator = {shown}. Rook uses it from its next start.{left_note}")
        return
    if running is None:
        if key == "voice_engine" and value == "medium" and not medium_voice_url():
            utter(f"Saved voice_engine = medium. No medium voice server is set yet. The small voice speaks until you set one.{left_note}")
            return
        utter(f"Saved {label} = {shown}. Rook is not running, so it takes effect at Rook's next start.{left_note}")
        return
    if key not in running["settings"]:
        utter(f"Saved {label} = {shown}. The running Rook predates this setting, so it takes effect at its next start.{left_note}")
        return
    answer = ask_rook("apply", say)
    if answer and answer.get("timeout"):
        # Rook may still finish the change, so the saved setting stays.
        leave(f"Saved {label} = {shown}, but {answer['error']} Check with relay.py get.{left_note}")
    if not answer or not answer.get("ok"):
        # The running voice stays, so the file goes back to what is running.
        try:
            if old is None:
                CONFIG.unlink(missing_ok=True)
            else:
                atomic_write_text(CONFIG, old, mode=old_mode)
        except OSError as exc:
            leave(f"Rook could not apply {label} = {shown}, and could not restore {CONFIG}: {str(exc).rstrip('.')}.")
        leave(f"Rook could not apply {label} = {shown}: {(answer or {}).get('error', 'Rook stopped answering.')} "
                 "Rook still speaks as before.")
    applied = answer["settings"]
    if key == "light_dust":
        theme = theme_now()
        utter(f"Rook's light theme now draws its dust as {applied.get('light_dust')}."
              + (" The theme is dark now, so it shows when the theme turns light." if theme == "dark" else
                 "" if theme == "light" else " It applies to the light theme only.") + left_note)
        return
    if key == "theme":
        utter(f"Rook's presence theme is now {applied.get('theme')}.{left_note}")
        return
    if key == "font":
        utter(f"Rook's text now shows in the {applied.get('font')} font."
              + (" It spoke the line, and its caption shows the new font." if answer.get("said") else "") + left_note)
        return
    if key == "diagram_entrance":
        mode = applied.get("diagram_entrance")
        how = "draw on" if mode == "draw" else "fly in"
        utter(f"Diagrams now {how} ({mode}) starting from the next diagram.{left_note}")
        return
    if key == "diagram_dance":
        preset = applied.get("diagram_dance")
        utter(f"Diagram dust dance is now {preset} starting from the next diagram.{left_note}")
        return
    if key == "stage":
        where = "the stage, beside the presence" if applied.get("stage") == "on" else "the overlay"
        utter(f"Diagrams and the answer panel now show in {where}, starting from the next one.{left_note}")
        return
    if key == "listen_after":
        utter(f"Listen after speaking is now {applied.get('listen_after')}, starting from the next answer.{left_note}")
        return
    if key == "smart_turn":
        utter(f"Smart turn detection is now {applied.get('smart_turn')}, starting from the next listen window.{left_note}")
        return
    if key == "speak_thoughts":
        mode = applied.get("speak_thoughts")
        beats_note = (" The between-tool beats prompt rule takes effect at Rook's next start."
                      if applied.get("speak_thoughts_beats_pending") else "")
        utter(f"Speak thoughts is now {mode}, starting from the next turn.{beats_note}{left_note}")
        return
    if key == "smart_turn_threshold":
        thresh = applied.get("smart_turn_threshold")
        shown_thresh = f"{float(thresh):.2f}" if isinstance(thresh, (int, float)) else thresh
        utter(f"Smart turn threshold is now {shown_thresh}, starting from the next listen window.{left_note}")
        return
    if key == "talk_keys":
        keys = applied.get("talk_keys") or []
        utter(f"Rook now listens while {' or '.join(keys)} is held." if keys else "Rook now has no talk key.")
        return
    if key == "recording_minutes":
        minutes = applied.get("recording_minutes")
        unit = "minute" if minutes == 1 else "minutes"
        utter(f"Recording limit is now {minutes} {unit}, starting from the next recording.{left_note}")
        return
    if applied.get("voice_engine") == "medium":
        med_url = applied.get("medium_voice_url") if "medium_voice_url" in applied else medium_voice_url()
        if not med_url:
            utter(f"Saved voice_engine = medium. No medium voice server is set yet. "
                  f"Rook still speaks with its small voice, {applied['voice']}."
                  + (" It said the line." if answer.get("said") else "") + left_note)
            return
        host = urlparse(med_url).hostname or ""
        label = host.split(".")[0] if host and not re.fullmatch(r"[0-9.]+", host) else host
        origin = f", from {label}" if label else ""
        server_name = label or "the medium voice server"
        utter(f"Rook now speaks with its medium voice, {applied['voice_medium']}{origin}. "
              f"Speed is {engine_to_points('voice_pace', applied['voice_pace'])} "
              f"(about {max(0.8, min(1.2, 1.0 - 0.4 * applied['voice_pace'])):.2f}x), "
              f"volume is {engine_to_points('voice_volume', applied['voice_volume'])}, "
              f"and expressiveness is {engine_to_points('voice_temperature', applied['voice_temperature'])} of 100. "
              f"Expressiveness applies to both voices. On the medium voice, 50 keeps Qwen's own sound. "
              f"When {server_name} cannot answer in time, a sentence uses the small voice, {applied['voice']}."
              + (" It said the line." if answer.get("said") else "") + left_note)
        return
    utter(f"Rook now speaks as {applied['voice']}, at speed {engine_to_points('voice_pace', applied['voice_pace'])}, "
          f"volume {engine_to_points('voice_volume', applied['voice_volume'])}, "
          f"and expressiveness {engine_to_points('voice_temperature', applied['voice_temperature'])} of 100."
          + (" It said the line in the new voice." if answer.get("said") else "") + left_note)


def _onboard():
    """The onboarding module, loaded only for its commands. It imports relay, so this module goes in first."""
    sys.modules.setdefault("relay", sys.modules[__name__])
    import onboard
    return onboard


def check_settings():
    """Self-check point conversions, round trips, friendly names, previous, and refusals on scratch folders."""
    import tempfile
    import threading
    assert points_to_engine("voice_pace", 50) == 0.0
    # build_threads holds plain thread ids, as written by relay.py set, or objects from onboarding; readers get ids.
    mixed = {"build_threads": {"fable": "mcp:x", "builder": {"thread": "t-1", "model": "m", "extra": 3}}}
    assert settings.build_threads(mixed) == {"fable": "mcp:x", "builder": "t-1"}
    assert settings.build_thread_details(valid(mixed)) == {"fable": "mcp:x", "builder": {"thread": "t-1", "model": "m"}}
    assert settings.invalid_keys({"build_threads": {"a": {"model": "m"}}}) == ["build_threads"]
    # Owner tokens: filled in one pass, so a name is never read again; text without tokens stays as it is.
    said = ("Tell ⟦owner⟧ so. ⟦verb:He asks|They ask⟧. It is ⟦hers⟧. ⟦His⟧ to-do list, and ⟦him⟧. "
            "Two exceptions: ⟦owner⟧'s. ⟦Owner⟧ and he go.")
    assert settings.render(said, "Test Owner", "he") == ("Tell Test Owner so. He asks. It is his. His to-do list, and him. "
                                                          "Two exceptions: Test Owner's. Test Owner and he go.")
    assert settings.render(said, "Test Owner", "she") == ("Tell Test Owner so. She asks. It is hers. Her to-do list, and her. "
                                                   "Two exceptions: Test Owner's. Test Owner and he go.")
    assert settings.render(said, "the person", "they") == (
        "Tell the person so. They ask. It is theirs. Their to-do list, and them. Two exceptions: the person's. "
        "The person and he go.")
    assert settings.render("Tell ⟦owner⟧ so. ⟦verb:He asks|They ask⟧.", "He", "they") == "Tell He so. They ask."
    assert settings.render("[--to opus|neon] he|she") == "[--to opus|neon] he|she"  # No token, no change.
    assert settings.unknown_tokens("⟦owner⟧ ⟦verb:he asks|they ask⟧ ⟦nope⟧ ⟦verb:asks⟧") == ["⟦nope⟧", "⟦verb:asks⟧"]
    assert settings.token("his") == "⟦his⟧" and settings.token("he asks", "they ask") == "⟦verb:he asks|they ask⟧"
    # Shipped text names no owner and uses no owner pronoun outside a token, and holds no unknown token. Skills hold
    # no environment id and no home folder: the owner's own setup is in their private workspace skill. The house style
    # is another branch's work.
    # The owner's name comes from ROOK_CHECK_OWNER, which scripts/release-checks fills from the real owner settings.
    names = "".join(f"{re.escape(n)}|" for n in [os.environ.get("ROOK_CHECK_OWNER", "").strip()] if len(n) > 1)
    root, word = Path(__file__).resolve().parent.parent, re.compile(rf"(?<![\w⟦:|<])(?<!say )({names}he|He|his|His|him|himself)(?![\w⟧|])")  # "say he, she or they" offers.
    texts = {str(f): f.read_text() for f in [*(root / "skills").rglob("*.md"), *(root / "wow/skills").rglob("*.md"),
                                               *(root / "plugins").rglob("*.md"), *(root / "plugins").rglob("plugin.json"),
                                               *(root / "plugin").rglob("plugin.json")]}
    own = [f for f in texts if re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-|/home/", texts[f])]
    assert not own, own
    # Skills name no machine either. The names come from this machine at check time, so the check ships none: the host
    # name, the scratch machine table, and ROOK_CHECK_PRIVATE_NAMES, which scripts/release-checks fills from the real one.
    hosts = {socket.gethostname().split(".")[0], *watch.machines(),
             *os.environ.get("ROOK_CHECK_PRIVATE_NAMES", "").split(",")}
    hosts = [h for h in hosts if isinstance(h, str) and len(h) > 1 and h.lower() not in ("local", "localhost")]
    if hosts:
        named = re.compile(r"(?<![\w.-])(" + "|".join(map(re.escape, hosts)) + r")(?![\w-])", re.I)
        own = {f: sorted(set(named.findall(text))) for f, text in texts.items() if named.search(text)}
        assert not own, own
    for f in [*(root / "desktop").glob("*.py"), *(root / "wow").glob("*.py"), *(root / "skills").rglob("*.py")]:
        if f.name == "settings.py":
            continue
        tree = ast.parse(f.read_text())
        skip = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and re.fullmatch(r"_?check(_\w*)?|\w*_check|test\w*", node.name):
                skip.update(id(sub) for sub in ast.walk(node))
            elif isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) in ("pn", "token"):
                skip.update(id(arg) for arg in node.args)
            body = getattr(node, "body", None)
            if isinstance(body, list) and body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                if not (isinstance(node, ast.Module) and f.name == "relay.py"):  # relay.py's docstring is its help.
                    skip.add(id(body[0].value))
        texts.update({f"{f}:{node.lineno}": node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)
                      and isinstance(node.value, str) and id(node) not in skip})
    left = {where: sorted({m.group(1) for m in word.finditer(text)}) + settings.unknown_tokens(text)
            for where, text in texts.items() if word.search(text) or settings.unknown_tokens(text)}
    assert not left, left
    assert points_to_engine("voice_pace", 100) == -0.5
    assert points_to_engine("voice_pace", 1) == 0.49
    assert points_to_engine("voice_volume", 0) == 0.0
    assert points_to_engine("voice_volume", 100) == 1.5
    assert points_to_engine("voice_temperature", 1) == 0.01
    assert points_to_engine("voice_temperature", 100) == 1.0
    assert engine_to_points("voice_pace", -0.15) == 65
    assert engine_to_points("voice_volume", 0.7) == 47
    assert engine_to_points("voice_temperature", 0.65) == 65
    for key, (_, low, _) in POINT_SETTINGS.items():
        for pts in range(low, 101):
            eng = points_to_engine(key, pts)
            assert RANGES[key][0] <= eng <= RANGES[key][1], (key, pts, eng)
            stored = json.loads(json.dumps(eng))
            assert engine_to_points(key, stored) == pts, (key, pts, stored)
    with tempfile.TemporaryDirectory() as folder:
        base = Path(folder)
        cfg_home, rt_dir = base / "config", base / "runtime"
        rt_dir.mkdir(mode=0o700)
        settings_path = cfg_home / "rook/settings.json"
        settings_path.parent.mkdir(mode=0o700, parents=True)
        initial = {
            "voice": "Miles", "voice_pace": -0.15, "voice_volume": 0.7, "voice_temperature": 0.65,
            "previous": {"voice": "Spencer", "voice_pace": -0.25, "voice_volume": 0.9, "voice_temperature": 0.3},
        }
        settings_path.write_text(json.dumps(initial, indent=2) + "\n")

        def run_cli(*args, med_url="http://127.0.0.1:9", **extra):
            env = {k: v for k, v in os.environ.items() if k not in ("T3CODE_THREAD_ID", "ROOK_MEDIUM_VOICE_URL")}
            env.update(XDG_CONFIG_HOME=str(cfg_home), XDG_RUNTIME_DIR=str(rt_dir),
                       XDG_STATE_HOME=str(base / "state"), XDG_DATA_HOME=str(base / "data"),
                       XDG_CACHE_HOME=str(base / "cache"), **extra)
            if med_url is not None:
                env["ROOK_MEDIUM_VOICE_URL"] = med_url  # Never nimbus-pc.
            return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True, env=env)

        got = run_cli("get")
        assert got.returncode == 0, got.stderr
        assert "speed: 65 of 100 (higher is faster, settings file) [-0.15]" in got.stdout, got.stdout
        assert "volume: 47 of 100 (0 is silent, settings file) [0.7]" in got.stdout, got.stdout
        assert "expressiveness: 65 of 100 (higher is more varied, settings file) [0.65]" in got.stdout, got.stdout
        assert "recording_minutes: 10 (default)" in got.stdout, got.stdout
        assert "smart_turn: off (default)" in got.stdout, got.stdout
        assert "smart_turn_threshold: 0.75 (default)" in got.stdout, got.stdout
        assert "speak_thoughts: off (default)" in got.stdout, got.stdout
        assert run_cli("get", "speed").stdout == run_cli("get", "voice_pace").stdout
        assert run_cli("get", "volume").stdout == run_cli("get", "voice_volume").stdout
        assert run_cli("get", "expressiveness").stdout == run_cli("get", "voice_temperature").stdout

        res = run_cli("set", "speed", "70")
        assert res.returncode == 0 and "Saved speed = 70 of 100." in res.stdout, (res.stdout, res.stderr)
        saved = json.loads(settings_path.read_text())
        assert saved["voice_pace"] == -0.2 and saved["previous"]["voice_pace"] == -0.15, saved

        prev = run_cli("set", "speed", "previous")
        assert prev.returncode == 0 and "Saved speed = 65 of 100." in prev.stdout, (prev.stdout, prev.stderr)
        assert json.loads(settings_path.read_text())["voice_pace"] == -0.15

        old_key = run_cli("set", "voice_pace", "80")
        assert old_key.returncode == 0 and "Saved speed = 80 of 100." in old_key.stdout, (old_key.stdout, old_key.stderr)
        assert json.loads(settings_path.read_text())["voice_pace"] == -0.3

        mute = run_cli("set", "volume", "0")
        assert mute.returncode == 0 and "Saved volume = 0 of 100." in mute.stdout, (mute.stdout, mute.stderr)
        assert json.loads(settings_path.read_text())["voice_volume"] == 0.0
        assert "volume: 0 of 100" in run_cli("get", "volume").stdout

        expr = run_cli("set", "expressiveness", "75")
        assert expr.returncode == 0 and "Saved expressiveness = 75 of 100." in expr.stdout, (expr.stdout, expr.stderr)
        assert json.loads(settings_path.read_text())["voice_temperature"] == 0.75

        before_bad = settings_path.read_text()
        for bad_args in (
            ("set", "speed", "-0.25"), ("set", "voice_pace", "-0.25"),
            ("set", "speed", "101"), ("set", "speed", "0"),
            ("set", "volume", "101"), ("set", "volume", "-0.25"),
            ("set", "expressiveness", "0"), ("set", "expressiveness", "0.65"), ("set", "expressiveness", "101"),
        ):
            bad = run_cli(*bad_args)
            assert bad.returncode != 0 and "1 to 100" in bad.stderr, (bad_args, bad.stdout, bad.stderr)
        assert settings_path.read_text() == before_bad

        # recording_minutes: default 10, set 15, refuse 0 and 31, and previous.
        assert "recording_minutes: 10 (default)" in run_cli("get", "recording_minutes").stdout
        rec = run_cli("set", "recording_minutes", "15")
        assert rec.returncode == 0 and "Saved recording_minutes = 15." in rec.stdout, (rec.stdout, rec.stderr)
        saved = json.loads(settings_path.read_text())
        assert saved["recording_minutes"] == 15 and saved["previous"]["recording_minutes"] == 10, saved
        assert "recording_minutes: 15 (settings file)" in run_cli("get", "recording_minutes").stdout
        before_bad_rec = settings_path.read_text()
        for bad_val in ("0", "31", "-1", "1.5", "ten"):
            bad = run_cli("set", "recording_minutes", bad_val)
            assert bad.returncode != 0 and "1 to 30" in bad.stderr, (bad_val, bad.stdout, bad.stderr)
        assert settings_path.read_text() == before_bad_rec
        rec_prev = run_cli("set", "recording_minutes", "previous")
        assert rec_prev.returncode == 0 and "Saved recording_minutes = 10." in rec_prev.stdout, (rec_prev.stdout, rec_prev.stderr)
        saved = json.loads(settings_path.read_text())
        assert saved["recording_minutes"] == 10 and saved["previous"]["recording_minutes"] == 15, saved

        # smart_turn and smart_turn_threshold: defaults, set, refusals, and previous.
        assert "smart_turn: off (default)" in run_cli("get", "smart_turn").stdout
        assert "smart_turn_threshold: 0.75 (default)" in run_cli("get", "smart_turn_threshold").stdout
        st_on = run_cli("set", "smart_turn", "ON")
        assert st_on.returncode == 0 and "Saved smart_turn = on." in st_on.stdout, (st_on.stdout, st_on.stderr)
        saved = json.loads(settings_path.read_text())
        assert saved["smart_turn"] == "on" and saved["previous"]["smart_turn"] == "off", saved
        assert "smart_turn: on (settings file)" in run_cli("get", "smart_turn").stdout
        st_bad = run_cli("set", "smart_turn", "maybe")
        assert st_bad.returncode != 0 and "off or on" in st_bad.stderr, (st_bad.stdout, st_bad.stderr)
        st_prev = run_cli("set", "smart_turn", "previous")
        assert st_prev.returncode == 0 and "Saved smart_turn = off." in st_prev.stdout, (st_prev.stdout, st_prev.stderr)
        saved = json.loads(settings_path.read_text())
        assert saved["smart_turn"] == "off" and saved["previous"]["smart_turn"] == "on", saved

        # speak_thoughts: default off, set all valid modes, refusal, and previous.
        assert "speak_thoughts: off (default)" in run_cli("get", "speak_thoughts").stdout
        for mode in ("beats", "thoughts", "both"):
            sp_set = run_cli("set", "speak_thoughts", mode.upper())
            assert sp_set.returncode == 0 and f"Saved speak_thoughts = {mode}." in sp_set.stdout, (sp_set.stdout, sp_set.stderr)
            assert json.loads(settings_path.read_text())["speak_thoughts"] == mode
        assert "speak_thoughts: both (settings file)" in run_cli("get", "speak_thoughts").stdout
        sp_bad = run_cli("set", "speak_thoughts", "always")
        assert sp_bad.returncode != 0 and "off, beats, thoughts or both" in sp_bad.stderr, (sp_bad.stdout, sp_bad.stderr)
        sp_prev = run_cli("set", "speak_thoughts", "previous")
        assert sp_prev.returncode == 0 and "Saved speak_thoughts = thoughts." in sp_prev.stdout, (sp_prev.stdout, sp_prev.stderr)
        sp_off = run_cli("set", "speak_thoughts", "off")
        assert sp_off.returncode == 0 and json.loads(settings_path.read_text())["speak_thoughts"] == "off"

        # stage: default off, set, refusal, and previous, through the same tables and saved file.
        assert "stage: off (default)" in run_cli("get", "stage").stdout
        # The desktop stage is shelved: "on" is refused when set and ignored when already saved.
        sg_on = run_cli("set", "stage", "On")
        assert sg_on.returncode != 0 and "shelved" in sg_on.stderr, (sg_on.stdout, sg_on.stderr)
        assert "stage: off (default)" in run_cli("get", "stage").stdout
        kept = json.loads(settings_path.read_text())
        settings_path.write_text(json.dumps({**kept, "stage": "on"}))
        assert "stage: off (default)" in run_cli("get", "stage").stdout
        settings_path.write_text(json.dumps(kept))

        th_set = run_cli("set", "smart_turn_threshold", "0.65")
        assert th_set.returncode == 0 and "Saved smart_turn_threshold = 0.65." in th_set.stdout, (th_set.stdout, th_set.stderr)
        saved = json.loads(settings_path.read_text())
        assert saved["smart_turn_threshold"] == 0.65 and saved["previous"]["smart_turn_threshold"] == 0.75, saved
        assert "smart_turn_threshold: 0.65 (settings file)" in run_cli("get", "smart_turn_threshold").stdout
        before_bad_th = settings_path.read_text()
        for bad_val in ("0.05", "0.96", "-0.2", "nan", "inf", "high"):
            bad = run_cli("set", "smart_turn_threshold", bad_val)
            assert bad.returncode != 0 and "0.1 to 0.95" in bad.stderr, (bad_val, bad.stdout, bad.stderr)
        assert settings_path.read_text() == before_bad_th
        th_prev = run_cli("set", "smart_turn_threshold", "previous")
        assert th_prev.returncode == 0 and "Saved smart_turn_threshold = 0.75." in th_prev.stdout, (th_prev.stdout, th_prev.stderr)
        saved = json.loads(settings_path.read_text())
        assert saved["smart_turn_threshold"] == 0.75 and saved["previous"]["smart_turn_threshold"] == 0.65, saved

        # voice_engine and voice_medium: defaults, set, refusals, and the four known names while the server is down.
        assert "voice_engine: small (default)" in run_cli("get", "voice_engine").stdout
        assert "voice_medium: late-night-architect (default)" in run_cli("get", "voice_medium").stdout
        assert "Saved voice_engine = medium." in run_cli("set", "voice_engine", "Medium").stdout
        assert "Saved voice_medium = velvet-wit." in run_cli("set", "voice_medium", "Velvet Wit").stdout
        assert "Saved voice_medium = late-night-architect." in run_cli("set", "voice_medium", "previous").stdout
        assert "Saved voice_medium = observatory-keeper." in run_cli("set", "voice_medium", "Observatory Keeper").stdout
        assert json.loads(settings_path.read_text())["voice_medium"] == "observatory-keeper"
        assert "Saved voice_medium = observatory-keeper." in run_cli("set", "voice_medium", "the observatory keeper").stdout
        assert "Saved voice_medium = late-night-architect." in run_cli("set", "voice_medium", "Late Night Architect").stdout
        assert "Saved voice_medium = late-night-architect." in run_cli("set", "voice_medium", "late-night architect").stdout
        assert "Saved voice_medium = late-night-architect." in run_cli("set", "voice_medium", "Architect").stdout
        assert "Saved voice_medium = observatory-keeper." in run_cli("set", "voice_medium", "previous").stdout
        assert "Saved voice_engine = small." in run_cli("set", "voice_engine", "previous").stdout
        # agent setting: claude, antigravity, and codex with model prefix validation.
        cx_set = run_cli("set", "agent", "codex")
        assert cx_set.returncode == 0 and "Saved agent = codex" in cx_set.stdout, (cx_set.stdout, cx_set.stderr)
        assert json.loads(settings_path.read_text())["agent"] == "codex"
        cx_mod = run_cli("set", "agent_model", "gpt-6.2-sol")
        assert cx_mod.returncode == 0 and "Saved agent_model = gpt-6.2-sol" in cx_mod.stdout, (cx_mod.stdout, cx_mod.stderr)
        cx_bad = run_cli("set", "agent_model", "claude-opus-5-5")
        assert cx_bad.returncode != 0 and "gpt-" in cx_bad.stderr, (cx_bad.stdout, cx_bad.stderr)
        bad_agent = run_cli("set", "agent", "unknown")
        assert bad_agent.returncode != 0 and "codex" in bad_agent.stderr, (bad_agent.stdout, bad_agent.stderr)
        assert run_cli("set", "agent", "claude").returncode == 0
        before_bad_voice = settings_path.read_text()
        assert "small or medium" in run_cli("set", "voice_engine", "large").stderr
        assert "late-night-architect, velvet-wit, jarvis-poe, observatory-keeper" in run_cli("set", "voice_medium", "Bob").stderr
        assert settings_path.read_text() == before_bad_voice

        # Safe writes: preserve unknown keys and file mode, refuse corrupt file, survive concurrent writers.
        settings_path.write_text(json.dumps({**initial, "custom_note": "keep-me", "nested_extra": [1, 2]}, indent=2) + "\n")
        settings_path.chmod(0o640)
        keep_res = run_cli("set", "recording_minutes", "12")
        assert keep_res.returncode == 0, keep_res.stderr
        after_keep = json.loads(settings_path.read_text())
        assert after_keep["recording_minutes"] == 12 and after_keep["custom_note"] == "keep-me" and after_keep["nested_extra"] == [1, 2], after_keep
        assert stat.S_IMODE(settings_path.stat().st_mode) == 0o640
        settings_path.write_text("{broken json\n")
        settings_path.chmod(0o640)
        broken_res = run_cli("set", "recording_minutes", "14")
        assert broken_res.returncode != 0 and "Could not read" in broken_res.stderr and ".." not in broken_res.stderr, (broken_res.stdout, broken_res.stderr)
        assert settings_path.read_text() == "{broken json\n" and stat.S_IMODE(settings_path.stat().st_mode) == 0o640
        settings_path.write_text("[]\n")
        non_obj_res = run_cli("set", "recording_minutes", "14")
        assert non_obj_res.returncode != 0 and "JSON object." in non_obj_res.stderr and ".." not in non_obj_res.stderr, non_obj_res.stderr
        # Review 64 #1: one bad known key never blocks unrelated sets; it is left alone and named once, and setting it repairs it.
        bad_val_json = json.dumps({
            **initial,
            "medium_voice_url": "voice-host:8090",
            "voice_engine": "huge",
            "previous": {**initial["previous"], "voice_engine": "badprev"},
        }, indent=2) + "\n"
        settings_path.write_text(bad_val_json)
        settings_path.chmod(0o640)
        unrel_res = run_cli("set", "recording_minutes", "14")
        assert unrel_res.returncode == 0, (unrel_res.stdout, unrel_res.stderr)
        assert "left alone: medium_voice_url, previous.voice_engine, voice_engine" in unrel_res.stdout, unrel_res.stdout
        after_unrel = json.loads(settings_path.read_text())
        assert after_unrel["recording_minutes"] == 14
        assert after_unrel["medium_voice_url"] == "voice-host:8090" and after_unrel["voice_engine"] == "huge"
        assert after_unrel["previous"]["voice_engine"] == "badprev"
        assert stat.S_IMODE(settings_path.stat().st_mode) == 0o640
        # Repairing voice_engine directly works even when voice_engine itself was bad.
        fix_eng = run_cli("set", "voice_engine", "small")
        assert fix_eng.returncode == 0 and "left alone: medium_voice_url, previous.voice_engine" in fix_eng.stdout, (fix_eng.stdout, fix_eng.stderr)
        assert json.loads(settings_path.read_text())["voice_engine"] == "small"
        # Setting the three config keys via relay.py set works; invalid values for the key being set are refused.
        bad_url_res = run_cli("set", "medium_voice_url", "voice-host:8090")
        assert bad_url_res.returncode != 0 and "medium_voice_url" in bad_url_res.stderr and ".." not in bad_url_res.stderr
        fix_url = run_cli("set", "medium_voice_url", "https://voice.local:8090/")
        assert fix_url.returncode == 0 and "Saved medium_voice_url = https://voice.local:8090." in fix_url.stdout, (fix_url.stdout, fix_url.stderr)
        assert "medium_voice_url" not in fix_url.stdout.split("left alone:")[-1] if "left alone:" in fix_url.stdout else True
        assert json.loads(settings_path.read_text())["medium_voice_url"] == "https://voice.local:8090"
        assert "https://voice.local:8090" in run_cli("get", "medium_voice_url", med_url=None).stdout
        bad_gh = run_cli("set", "github_user", "bad user!")
        assert bad_gh.returncode != 0 and "github_user" in bad_gh.stderr
        ok_gh = run_cli("set", "github_user", "octocat")
        assert ok_gh.returncode == 0 and json.loads(settings_path.read_text())["github_user"] == "octocat"
        assert "octocat" in run_cli("get", "github_user").stdout
        bad_bt = run_cli("set", "build_threads.bad!name", "mcp:123")
        assert bad_bt.returncode != 0 and "build_threads" in bad_bt.stderr
        ok_bt = run_cli("set", "build_threads.fable", "mcp:thread-1")
        assert ok_bt.returncode == 0 and json.loads(settings_path.read_text())["build_threads"] == {"fable": "mcp:thread-1"}
        assert "mcp:thread-1" in run_cli("get", "build_threads.fable").stdout
        assert run_cli("set", "build_threads.fable", "clear").returncode == 0
        assert "build_threads" not in json.loads(settings_path.read_text())
        assert run_cli("set", "medium_voice_url", "clear").returncode == 0
        assert "medium_voice_url" not in json.loads(settings_path.read_text())
        # Review 64 #3 (offline): set voice_engine medium with no server tells the truth in short sentences.
        no_srv_off = run_cli("set", "voice_engine", "medium", med_url=None)
        assert no_srv_off.returncode == 0 and "No medium voice server is set yet." in no_srv_off.stdout and "relay.py" not in no_srv_off.stdout, no_srv_off.stdout
        # Review 67 #3: credentials in medium_voice_url refused without echoing secret; bad build_threads sibling preserved; bad smart_turn left alone.
        cred_res = run_cli("set", "medium_voice_url", "https://alice:topsecretpw@voice.local:8090", med_url=None)
        assert cred_res.returncode != 0 and "topsecretpw" not in (cred_res.stdout + cred_res.stderr), (cred_res.stdout, cred_res.stderr)
        settings_path.write_text(json.dumps({**initial, "smart_turn": "bogus", "build_threads": {"bad!": 123}}, indent=2) + "\n")
        bt_keep = run_cli("set", "build_threads.fable", "mcp:thread-ok")
        assert bt_keep.returncode == 0 and "left alone: build_threads.bad!, smart_turn" in bt_keep.stdout, (bt_keep.stdout, bt_keep.stderr)
        after_bt = json.loads(settings_path.read_text())
        assert after_bt["build_threads"] == {"fable": "mcp:thread-ok", "bad!": 123} and after_bt["smart_turn"] == "bogus", after_bt
        assert run_cli("set", "smart_turn", "on").returncode == 0 and json.loads(settings_path.read_text())["smart_turn"] == "on"
        # Review 67 #3c: file not writable by current user (mode 0644) says "not writable by this user", not "read-only".
        old_access = os.access
        os.access = lambda p, m: False
        try:
            ro_other = base / "other-owned.json"
            ro_other.write_text("{}\n")
            ro_other.chmod(0o644)
            try:
                atomic_write_text(ro_other, '{"a": 1}\n', mode=0o644)
                raise AssertionError("expected PermissionError")
            except PermissionError as exc:
                assert "not writable by this user" in str(exc) and "read-only" not in str(exc), str(exc)
        finally:
            os.access = old_access
        # Review 67 #3d: onboarding refuses read-only onboarding.json cleanly without traceback.
        onb_path = cfg_home / "rook/onboarding.json"
        onb_path.write_text("{}\n")
        onb_path.chmod(0o444)
        try:
            onb_ro = run_cli("onboard", "--voice", "none")
            assert onb_ro.returncode == 0 and "I could not save the onboarding record" in onb_ro.stdout \
                and "Traceback" not in onb_ro.stdout + onb_ro.stderr, (onb_ro.stdout, onb_ro.stderr)
        finally:
            onb_path.chmod(0o600)
            onb_path.unlink(missing_ok=True)
        # Review 64 #2: read-only target (mode 444), direct or through symlink, is refused without overwriting.
        settings_path.write_text(json.dumps(initial, indent=2) + "\n")
        settings_path.chmod(0o444)
        try:
            ro_res = run_cli("set", "recording_minutes", "16")
            assert ro_res.returncode != 0 and "read-only" in ro_res.stderr and ".." not in ro_res.stderr, (ro_res.stdout, ro_res.stderr)
            assert json.loads(settings_path.read_text()) == initial
        finally:
            settings_path.chmod(0o600)
        # Symlinked settings.json writes through to the target and keeps the symlink intact (and refuses read-only target).
        link_target = base / "dotfiles-settings.json"
        link_target.write_text(json.dumps(initial, indent=2) + "\n")
        link_target.chmod(0o444)
        settings_path.unlink()
        settings_path.symlink_to(link_target)
        try:
            ro_sym = run_cli("set", "recording_minutes", "16")
            assert ro_sym.returncode != 0 and "read-only" in ro_sym.stderr and ".." not in ro_sym.stderr, (ro_sym.stdout, ro_sym.stderr)
            assert settings_path.is_symlink() and json.loads(link_target.read_text()) == initial
        finally:
            link_target.chmod(0o640)
        sym_res = run_cli("set", "recording_minutes", "16")
        assert sym_res.returncode == 0, sym_res.stderr
        assert settings_path.is_symlink() and settings_path.resolve() == link_target.resolve()
        assert json.loads(link_target.read_text())["recording_minutes"] == 16
        assert stat.S_IMODE(link_target.stat().st_mode) == 0o640
        settings_path.unlink()
        # Two concurrent writers never collide on a shared temp filename.
        settings_path.write_text(json.dumps(initial, indent=2) + "\n")
        settings_path.chmod(0o600)
        old_cfg = settings.CONFIG
        settings.CONFIG = settings_path
        errors = []
        def writer(val):
            try:
                for _ in range(15):
                    write_settings({**initial, "recording_minutes": val}, {})
            except Exception as exc:
                errors.append(exc)
        try:
            t1, t2 = threading.Thread(target=writer, args=(11,)), threading.Thread(target=writer, args=(13,))
            t1.start(); t2.start(); t1.join(); t2.join()
            assert not errors, errors
            assert json.loads(settings_path.read_text())["recording_minutes"] in (11, 13)
        finally:
            settings.CONFIG = old_cfg

        # Live apply prints points, not raw engine decimals.
        settings_path.write_text(json.dumps(initial, indent=2) + "\n")
        sock_path = rt_dir / "rook.sock"
        stop_srv = threading.Event()
        srv = socket.socket(socket.AF_UNIX)
        srv.bind(str(sock_path))
        sock_path.chmod(0o600)
        srv.listen(4)
        srv.settimeout(0.05)

        def serve():
            while not stop_srv.is_set():
                try:
                    conn, _ = srv.accept()
                except TimeoutError:
                    continue
                except OSError:
                    break
                with conn:
                    raw = b""
                    while chunk := conn.recv(65536):
                        raw += chunk
                    text = raw.decode(errors="replace")
                    cmd = text[len(REQUEST):].partition("\n")[0].strip() if text.startswith(REQUEST) else ""
                    asked.append((cmd, text[len(REQUEST):].partition("\n")[2]))
                    cur = json.loads(settings_path.read_text())
                    if cmd == "get":
                        minutes, minutes_source = recording_minutes_in_force(cur)
                        st_mode, st_source = smart_turn_in_force(cur)
                        st_thresh, st_thresh_source = smart_turn_threshold_in_force(cur)
                        sp_mode, sp_source = speak_thoughts_in_force(cur)
                        resp = {"ok": True, "settings": {
                            **{k: {"value": cur[k], "source": "settings file"}
                               for k in ("voice", "voice_pace", "voice_volume", "voice_temperature")},
                            "recording_minutes": {"value": minutes, "source": minutes_source},
                            "smart_turn": {"value": st_mode, "source": st_source},
                            "smart_turn_threshold": {"value": st_thresh, "source": st_thresh_source},
                            "speak_thoughts": {"value": sp_mode, "source": sp_source},
                            # A Rook that knows the engine settings, so a voice set applies at once.
                            **({k: {"value": cur.get(k, d), "source": "settings file"}
                                for k, d in (("voice_engine", "small"), ("voice_medium", "jarvis-poe"))}
                               if "engine" in refuse or "engine_ok" in refuse else {}),
                        }}
                    elif cmd == "audition" and "phone" in refuse:
                        resp = {"ok": False, "refused": "phone", "error": "This turn came from a phone."}
                    elif cmd == "audition":  # refuse may make the second line fail or stop.
                        resp = {"ok": True, "lines": [{"spoke": True, "problem": None},
                                                      {"spoke": not refuse, "stopped": "stop" in refuse,
                                                       "problem": "stand-in refusal" if "fail" in refuse else None}]}
                    elif cmd == "apply" and "engine" in refuse and cur.get("voice_engine") == "medium":
                        resp = {"ok": False, "error": "stand-in refusal"}
                    elif cmd == "apply":
                        resp = {"ok": True, "settings": {
                            **{k: cur[k] for k in ("voice", "voice_pace", "voice_volume", "voice_temperature")},
                            "voice_engine": cur.get("voice_engine", "small"),
                            "voice_medium": cur.get("voice_medium", "jarvis-poe"),
                            "recording_minutes": recording_minutes_in_force(cur)[0],
                            "smart_turn": smart_turn_in_force(cur)[0],
                            "smart_turn_threshold": smart_turn_threshold_in_force(cur)[0],
                            "speak_thoughts": speak_thoughts_in_force(cur)[0],
                            "speak_thoughts_beats_pending": speak_thoughts_in_force(cur)[0] in ("beats", "both"),
                        }, "said": False}
                    else:
                        resp = {"ok": False, "error": "bad"}
                    conn.sendall((json.dumps(resp) + "\n").encode())

        asked, refuse = [], []
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            live = run_cli("set", "speed", "70")
            assert live.returncode == 0, (live.stdout, live.stderr)
            assert live.stdout.strip() == "Rook now speaks as Miles, at speed 70, volume 47, and expressiveness 65 of 100.", live.stdout
            live_rec = run_cli("set", "recording_minutes", "15")
            assert live_rec.returncode == 0, (live_rec.stdout, live_rec.stderr)
            assert live_rec.stdout.strip() == "Recording limit is now 15 minutes, starting from the next recording.", live_rec.stdout
            live_rec_prev = run_cli("set", "recording_minutes", "previous")
            assert live_rec_prev.returncode == 0, (live_rec_prev.stdout, live_rec_prev.stderr)
            assert live_rec_prev.stdout.strip() == "Recording limit is now 10 minutes, starting from the next recording.", live_rec_prev.stdout
            # Review 64 #3 & Review 67 #2 (live): set voice_engine medium with no server tells the truth;
            # setting medium_voice_url while running in medium mode sends apply so the worker restarts.
            refuse.append("engine_ok")
            live_med = run_cli("set", "voice_engine", "medium", med_url=None)
            assert live_med.returncode == 0, (live_med.stdout, live_med.stderr)
            assert "No medium voice server is set yet." in live_med.stdout and "speaks with its medium voice" not in live_med.stdout and "relay.py" not in live_med.stdout, live_med.stdout
            asked[:] = []
            live_url = run_cli("set", "medium_voice_url", "https://voice.local:8090", med_url=None)
            assert live_url.returncode == 0 and "Rook now uses that voice server." in live_url.stdout, (live_url.stdout, live_url.stderr)
            assert any(c == "apply" for c, _ in asked), asked
            assert run_cli("set", "medium_voice_url", "clear", med_url=None).returncode == 0
            refuse.clear()
            assert run_cli("set", "voice_engine", "small", med_url=None).returncode == 0
            live_st = run_cli("set", "smart_turn", "on")
            assert live_st.returncode == 0, (live_st.stdout, live_st.stderr)
            assert live_st.stdout.strip() == "Smart turn detection is now on, starting from the next listen window.", live_st.stdout
            live_st_prev = run_cli("set", "smart_turn", "previous")
            assert live_st_prev.returncode == 0, (live_st_prev.stdout, live_st_prev.stderr)
            assert live_st_prev.stdout.strip() == "Smart turn detection is now off, starting from the next listen window.", live_st_prev.stdout
            live_th = run_cli("set", "smart_turn_threshold", "0.6")
            assert live_th.returncode == 0, (live_th.stdout, live_th.stderr)
            assert live_th.stdout.strip() == "Smart turn threshold is now 0.60, starting from the next listen window.", live_th.stdout
            live_th_prev = run_cli("set", "smart_turn_threshold", "previous")
            assert live_th_prev.returncode == 0, (live_th_prev.stdout, live_th_prev.stderr)
            assert live_th_prev.stdout.strip() == "Smart turn threshold is now 0.75, starting from the next listen window.", live_th_prev.stdout
            live_sp = run_cli("set", "speak_thoughts", "thoughts")
            assert live_sp.returncode == 0, (live_sp.stdout, live_sp.stderr)
            assert live_sp.stdout.strip() == "Speak thoughts is now thoughts, starting from the next turn.", live_sp.stdout
            live_sp_both = run_cli("set", "speak_thoughts", "both")
            assert live_sp_both.returncode == 0, (live_sp_both.stdout, live_sp_both.stderr)
            assert "Speak thoughts is now both, starting from the next turn." in live_sp_both.stdout
            assert "next start" in live_sp_both.stdout, live_sp_both.stdout
            live_sp_prev = run_cli("set", "speak_thoughts", "previous")
            assert live_sp_prev.returncode == 0 and "now thoughts" in live_sp_prev.stdout, (live_sp_prev.stdout, live_sp_prev.stderr)
            assert run_cli("set", "speak_thoughts", "off").returncode == 0

            # Onboarding: the audition and a dry run save nothing, and each choice is checked before anything changes.
            def files():
                return {f: f.read_bytes() for f in cfg_home.rglob("*") if f.is_file()}
            before, asked[:] = files(), []
            heard = run_cli("audition")
            assert heard.returncode == 0 and "So Rook used its small voices. Miles spoke in its own voice. Bryony " \
                "spoke in its own voice. The samples used the live speed, volume and expressiveness. Nothing was " \
                "saved." in heard.stdout and heard.stdout.strip().endswith("which one, Miles or Bryony?"), \
                (heard.stdout, heard.stderr)
            lines = json.loads(asked[-2][1])
            assert asked[-2][0] == "audition" and [line["voice"] for line in lines] == ["Miles", "Bryony"], asked
            # Each voice's name shows under the overlay while it plays, and the guide clears at the end.
            assert [line["guide"] for line in lines] == [{"text": n, "until": "listening"} for n in ("Miles", "Bryony")] \
                and asked[-1] == ("guide", "null"), asked
            assert all("medium voice" not in line["text"] and len(line["text"].split()) < 40 and "first_audio" not in line
                       for line in lines), lines
            refuse.append("fail")  # A line that did not play: the plain words, and no voice choice.
            plain = run_cli("audition")
            refuse.clear()
            assert plain.returncode == 0 and "Bryony did not play: stand-in refusal." in plain.stdout \
                and "We can choose the voice later." in plain.stdout and "--voice none" in plain.stdout, plain.stdout
            refuse.append("stop")  # The person stopped a line: no talk of an unreachable voice.
            cut = run_cli("audition")
            refuse.clear()
            assert cut.returncode == 0 and "Bryony was stopped before it ended." in cut.stdout \
                and "offer to play them again" in cut.stdout and "could not reach" not in cut.stdout, cut.stdout
            refuse.append("phone")  # A phone turn: nothing plays at the desk.
            phone = run_cli("audition")
            refuse.clear()
            assert phone.returncode == 0 and "Nothing played" in phone.stdout and "needs the desk" in phone.stdout \
                and "--voice none" in phone.stdout, phone.stdout
            assert files() == before, "An audition must save nothing."
            asked[:] = []
            dry = run_cli("onboard", "--name", "Test Owner", "--key", "rightalt", "--permissions", "Full",
                          "--voice", "Velvet Wit", "--dry-run")
            assert dry.returncode == 0 and dry.stdout.startswith("Dry run: nothing changed.") and "velvet-wit" in dry.stdout \
                and "talk_keys RightAlt" in dry.stdout and "permission_mode full" in dry.stdout \
                and "owner_name Test Owner" in dry.stdout, (dry.stdout, dry.stderr)
            assert files() == before and not asked, asked
            for bad_args, why in ((("--key", "Fn"), "not a talk key"), (("--permissions", "yolo"), "not a permission mode"),
                                  (("--name", "Robert'); drop"), "not a name"), (("--pronouns", "it"), "not pronouns"),
                                  (("--voice", "Bob"), "no voice named 'Bob'"),
                                  (("--colour", "red"), "Usage")):
                bad = run_cli("onboard", *bad_args)
                assert bad.returncode != 0 and why in bad.stderr, (bad_args, bad.stdout, bad.stderr)
            assert files() == before and not asked, asked
            none = run_cli("onboard", "--voice", "none", "--dry-run")
            assert none.returncode == 0 and "the voice stays as it is" in none.stdout and files() == before, none.stdout
            refuse.append("engine")  # Rook refuses the apply: every choice stays as it was, in one write.
            failed = run_cli("onboard", "--name", "Test Owner", "--voice", "velvet wit")
            refuse.clear()
            assert failed.returncode != 0 and "nothing changed" in failed.stderr, (failed.stdout, failed.stderr)
            assert files() == before, "A refused apply leaves the settings as they were."
            real = run_cli("onboard", "--voice", "none")
            assert real.returncode == 0 and "the voice stays as it is" in real.stdout, (real.stdout, real.stderr)
            saved = json.loads(settings_path.read_text())
            in_use = settings.talk_keys_in_force({}, settings.HOLD_KEYS)[0]  # No --key keeps the keys in use.
            assert (saved["talk_keys"], saved["permission_mode"]) == (in_use, "full"), saved
            assert "voice_medium" not in json.loads(before[settings_path]) and "voice_medium" not in saved, saved
            assert "not a model of Rook's agent" in run_cli("onboard", "--model", "gpt-6.2-sol").stderr
            assert "--effort takes" in run_cli("onboard", "--effort", "huge").stderr
            assert "not a name Rook can take" in run_cli("onboard", "--assistant-name", "R2D2!").stderr
            real = run_cli("onboard", "--name", "Test Owner", "--pronouns", "She", "--voice", "late night architect",
                           "--permissions", "careful", "--assistant-name", "Nova", "--model", "claude-opus-5-5",
                           "--effort", "medium")
            assert real.returncode == 0 and real.stdout.startswith("Set ") and "next start" in real.stdout, \
                (real.stdout, real.stderr)
            record = json.loads((cfg_home / "rook/onboarding.json").read_text())
            assert record["applied_now"] == {"talk_keys": in_use, "screenshots": "on",
                                             "voice_medium": "late-night-architect", "voice_engine": "medium"} and \
                record["at_next_start"] == {"permission_mode": "careful", "orchestrator": "t3", "owner_name": "Test Owner",
                                             "owner_pronouns": "she", "assistant_name": "Nova",
                                             "agent_model": "claude-opus-5-5", "agent_effort": "medium"}, record
            assert json.loads(settings_path.read_text())["assistant_name"] == "Nova"

            # Getting situated: the scan's rehearsal stand-ins, the coding tool and projects folder, the build thread,
            # the shared memory (in a scratch home, where a foreign dream makes the install refuse), and screenshots.
            for tool, words in (("t3", "notes-app: ~/Code/notes-app"), ("herdr", "claude-website: claude, idle"),
                                ("pi", "~/dev/api"), ("none", "Git projects directly in your home folder: 4")):
                scan = run_cli("onboard", "--scan", "--as", tool)
                assert scan.returncode == 0 and f"Rehearsal stand-in for {tool}" in scan.stdout and words in scan.stdout, \
                    (tool, scan.stdout, scan.stderr)
                assert ("We highly recommend T3 Code" in scan.stdout) == (tool in ("pi", "none")), (tool, scan.stdout)
            (base / "no-tools").mkdir()  # Neither T3 Code nor Herdr: the scan asks for one, T3 Code first.
            bare = run_cli("onboard", "--scan", PATH=str(base / "no-tools"), HOME=str(base / "no-tools"))
            assert bare.returncode == 0 and "T3 Code: not installed.\nHerdr: not installed." in bare.stdout \
                and "Background work: neither" in bare.stdout and "relay.py herdr install" in bare.stdout, bare.stdout
            assert "Hello. Say: \"Hi, I'm Rook." in bare.stdout and "Model: already Claude Opus 5.5 at medium" in bare.stdout, \
                bare.stdout
            assert "Build thread: no Claude Code, Antigravity or Codex" in bare.stdout, bare.stdout
            prefs = cfg_home / "rook/model-preferences.md"
            for _ in range(2):  # A second setup replaces its own section, and keeps the rest of the file.
                neon = run_cli("onboard", "--orchestrator", "none", "--voice", "none",
                               "--builder", "antigravity:gemini-4-neon:high", "--subagents", "gemini-4-neon")
                assert neon.returncode == 0 and "Saved the build thread choice" in neon.stdout, (neon.stdout, neon.stderr)
            text = prefs.read_text()
            assert text.startswith("# Rook's model preferences") and text.count("## Build thread from setup") == 1 \
                and "| Rook's build thread | newest Neon | high |" in text \
                and "| Build thread subagents | newest Neon | high |" in text, text
            prefs.write_text("# Mine\n\n## Build thread from setup\n\nold\n\n## Kept\n\nkeep me\n")
            assert run_cli("onboard", "--orchestrator", "none", "--voice", "none",
                           "--builder", "codex:gpt-6.2-sol:high").returncode == 0
            text = prefs.read_text()
            assert "old" not in text and "## Kept\n\nkeep me" in text and "| newest Sol | high |" in text, text
            assert "Usage" in run_cli("onboard", "--scan", "--as", "vim").stderr
            assert "only with --dry-run" in run_cli("onboard", "--name", "Test Owner", "--as", "herdr").stderr
            before = files()
            t3_dry = run_cli("onboard", "--name", "Test Owner", "--orchestrator", "t3", "--builder", "claudeAgent:claude-opus-5-5:high",
                             "--subagents", "claude-sonnet-5-5", "--dry-run")
            assert t3_dry.returncode == 0 and "t3 thread start" in t3_dry.stdout and "--option effort=high" in t3_dry.stdout \
                and "orchestrator t3" in t3_dry.stdout, t3_dry.stdout
            codex_dry = run_cli("onboard", "--name", "Test Owner", "--orchestrator", "t3", "--builder", "codex:gpt-6.2-sol:high",
                                "--dry-run")
            assert "--option reasoningEffort=high" in codex_dry.stdout, codex_dry.stdout
            assert "a provider of claudeAgent or codex" in run_cli("onboard", "--builder", "agy:gemini:high").stderr
            herdr_dry = run_cli("onboard", "--name", "Test Owner", "--as", "herdr", "--builder", "claudeAgent:claude-opus-5-5:high",
                                "--dry-run")
            assert "orchestrator herdr" in herdr_dry.stdout and "herdr cannot start one with a chosen model yet" in \
                herdr_dry.stdout and "t3 thread start" not in herdr_dry.stdout, herdr_dry.stdout
            assert "--builder takes" in run_cli("onboard", "--name", "Test Owner", "--builder", "a b").stderr
            assert files() == before, "A dry run writes nothing."
            home = base / "home"
            (home / ".agents/bin").mkdir(parents=True)
            (home / ".agents/bin/dream").write_text("#!/bin/sh\n")  # Not Rook's: install-shared refuses here.
            shared_dry = run_cli("onboard", "--name", "Test Owner", "--memory", "shared", "--dry-run", HOME=str(home))
            assert "memory install-shared" in shared_dry.stdout, shared_dry.stdout
            folder = base / "projects-here"
            real = run_cli("onboard", "--name", "Test Owner", "--memory", "shared", "--screenshots", "off",
                           "--projects-folder", str(folder), "--orchestrator", "pi", "--builder", "skip", HOME=str(home))
            assert real.returncode == 0 and "I could not install the shared memory, because ~/.agents/bin/dream already exists" in real.stdout \
                and folder.is_dir() and f"Made the projects folder {folder}" in real.stdout, (real.stdout, real.stderr)
            saved = json.loads(settings_path.read_text())
            assert (saved["screenshots"], saved["orchestrator"], saved["projects_folder"]) == ("off", "pi", str(folder)), saved
            no_claude = {"PATH": "/usr/bin:/bin", "HOME": str(home)}  # Claude Code is not on this PATH.
            assert "needs Claude Code for your projects" in run_cli("onboard", "--name", "Test Owner", "--memory", "shared",
                                                                    **no_claude).stderr
            assert "needs Claude Code, which is not installed" in run_cli("onboard", "--scan", "--as", "t3",
                                                                         **no_claude).stdout
            settings_path.write_text(json.dumps({**saved, "agent": "codex"}))
            assert "Its nightly tidy runs with this agent" in run_cli("onboard", "--scan", "--as", "t3", HOME=str(home)).stdout
            settings_path.write_text(json.dumps(saved))
            for value in ("off", "on"):  # The setting saves, and reads back.
                done = run_cli("set", "screenshots", value)
                assert done.returncode == 0 and json.loads(settings_path.read_text())["screenshots"] == value, \
                    (done.stdout, done.stderr)
            assert "is not a folder" in run_cli("set", "projects_folder", str(base / "missing")).stderr
            tool = run_cli("set", "orchestrator", "herdr")  # Read at the next start: no apply, no voice line.
            assert tool.returncode == 0 and "from its next start" in tool.stdout \
                and "speaks as" not in tool.stdout, (tool.stdout, tool.stderr)

            # One shared setup, in fresh scratch homes: nothing is ever lost or replaced.
            def home_with(name, **parts):
                h = base / "homes" / name
                for agent in (".claude", ".codex"):
                    (h / agent).mkdir(parents=True)
                for rel, body in parts.items():
                    path = h / rel.replace("__", "/")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.mkdir() if body is None else path.write_text(body)
                return h
            h = home_with("nothing")
            done = run_cli("shared-agents", HOME=str(h))
            assert (h / ".agents/AGENTS.md").is_file() and (h / ".agents/skills").is_dir(), done.stdout
            assert os.readlink(h / ".claude/CLAUDE.md") == str(h / ".agents/AGENTS.md") and \
                os.readlink(h / ".codex/skills") == str(h / ".agents/skills"), done.stdout
            again = run_cli("shared-agents", HOME=str(h))
            assert again.stdout.count("already linked.") == 4, again.stdout
            h = home_with("one", **{".claude__CLAUDE.md": "my rules\n", ".claude__skills__a__SKILL.md": "a\n"})
            dry = run_cli("shared-agents", "--dry-run", HOME=str(h))
            assert "would move" in dry.stdout and not (h / ".agents").exists(), dry.stdout
            run_cli("shared-agents", HOME=str(h))
            assert (h / ".agents/AGENTS.md").read_text() == "my rules\n" and (h / ".claude/CLAUDE.md").is_symlink()
            assert (h / ".agents/skills/a/SKILL.md").read_text() == "a\n" and (h / ".codex/skills").is_symlink()
            assert [p.name for p in (h / ".claude").iterdir() if ".backup-" in p.name] and \
                (h / ".codex/AGENTS.md").is_symlink()
            h = home_with("two", **{".claude__CLAUDE.md": "one\n", ".codex__AGENTS.md": "two\n"})
            two = run_cli("shared-agents", HOME=str(h))
            assert "each have their own, so nothing changes" in two.stdout and not (h / ".agents/AGENTS.md").exists()
            assert (h / ".claude/CLAUDE.md").read_text() == "one\n" and (h / ".codex/AGENTS.md").read_text() == "two\n"
            h = home_with("elsewhere")
            (h / "mine").write_text("x\n")
            (h / ".claude/CLAUDE.md").symlink_to(h / "mine")
            run_cli("shared-agents", HOME=str(h))
            assert os.readlink(h / ".claude/CLAUDE.md") == str(h / "mine"), "A link that points elsewhere stays."
            h = home_with("locked")
            (h / ".codex").chmod(0o500)
            try:
                locked = run_cli("shared-agents", HOME=str(h))
                assert locked.returncode == 0 and "stopped, nothing more changed" in locked.stdout, locked.stdout
            finally:
                (h / ".codex").chmod(0o700)

            # Everystate: pinned checksum, user-only install, a record, and nothing replaced that is not Rook's.
            import io
            import tarfile
            payload = io.BytesIO()
            with tarfile.open(fileobj=payload, mode="w:gz") as archive:
                info = tarfile.TarInfo("everystate")
                info.size = 6
                archive.addfile(info, io.BytesIO(b"binary"))
            fake = payload.getvalue()
            fetched = []

            def fake_fetch(url):
                fetched.append(url)
                return fake if url.endswith(".tar.gz") else b"skill text\n"
            h = base / "homes" / "everystate"
            (h / ".claude/skills").mkdir(parents=True)
            ob = _onboard()  # Its record of installs goes to this scratch home, never the caller's.
            old_home, old_pins, old_skill = os.environ.get("HOME"), dict(ob.EVERYSTATE_SHA256), dict(ob.EVERYSTATE_SKILL)
            old_installed, ob.INSTALLED = ob.INSTALLED, h / "installed.json"
            os.environ["HOME"] = str(h)

            def everystate(dry=False):
                try:
                    return ob.install_everystate(dry, fake_fetch)
                except ob.StepFailed as error:
                    return f"failed: {error}"
            try:
                assert "did not match its pinned checksum" in everystate()
                assert not (h / ".local/bin/everystate").exists()
                for key in ob.EVERYSTATE_SHA256:
                    ob.EVERYSTATE_SHA256[key] = (ob.EVERYSTATE_SHA256[key][0], __import__("hashlib").sha256(fake).hexdigest())
                assert "skill file SKILL.md did not match" in everystate() and not (h / ".local/bin").exists()
                for key in ob.EVERYSTATE_SKILL:
                    ob.EVERYSTATE_SKILL[key] = __import__("hashlib").sha256(b"skill text\n").hexdigest()
                assert "download Everystate" in everystate(dry=True)
                assert everystate().startswith("Installed Everystate")
                binary = h / ".local/bin/everystate"
                assert binary.read_bytes() == b"binary" and binary.stat().st_mode & 0o777 == 0o755
                assert (h / ".claude/skills/formal-verification/SKILL.md").read_text() == "skill text\n"
                entry = json.loads(ob.INSTALLED.read_text())["everystate"]
                assert entry["binary"] == str(binary) and len(entry["files"]) == 1 + len(ob.EVERYSTATE_SKILL), entry
                assert all("28fd7c5" in url or "v0.4.1" in url for url in fetched), fetched
                assert "already installed" in everystate()
                binary.write_bytes(b"the person's own build")  # Replaced by the person: left as it is.
                assert "changed since Rook installed it" in everystate() and binary.read_bytes() == b"the person's own build"
                ob.INSTALLED.write_text("{not json")
                assert "is not readable" in everystate()
                ob.INSTALLED.unlink()
                assert "already there, and not Rook's" in everystate()
            finally:
                ob.EVERYSTATE_SHA256.update(old_pins)
                ob.EVERYSTATE_SKILL.update(old_skill)
                ob.INSTALLED = old_installed
                os.environ.pop("HOME") if old_home is None else os.environ.update(HOME=old_home)
            assert (cfg_home / "rook/onboarding.json").stat().st_mode & 0o777 == 0o600
            saved = json.loads(settings_path.read_text())
            assert (saved["voice_medium"], saved["owner_name"]) == ("late-night-architect", "Test Owner"), saved

            # A talk key or permission mode left out keeps a saved one, rook included.
            before_keep = settings_path.read_text()  # The stand-in Rook reads this file: it comes back after.
            settings_path.write_text(json.dumps({**json.loads(before_keep), "talk_keys": ["RightCtrl", "F15", "F14"],
                                                 "permission_mode": "rook", "screenshots": "off"}))
            kept = run_cli("onboard", "--name", "Test Owner", "--voice", "none", "--dry-run")
            assert kept.returncode == 0 and "permission_mode rook" in kept.stdout and "screenshots off" in kept.stdout \
                and "talk_keys RightCtrl, F15, F14" in kept.stdout, (kept.stdout, kept.stderr)
            settings_path.write_text(before_keep)

            # The personal settings, each checked.
            assert "Saved owner_name = Test Owner." in run_cli("set", "owner_name", "Test Owner").stdout
            assert "not a name" in run_cli("set", "owner_name", "R2D2!").stderr
            assert "Saved owner_pronouns = she." in run_cli("set", "owner_pronouns", "She").stdout
            assert "must be he, she, they" in run_cli("set", "owner_pronouns", "it").stderr
            assert "Saved permission_mode = full." in run_cli("set", "permission_mode", "Full").stdout
            assert "must be inherit" in run_cli("set", "permission_mode", "yolo").stderr
            keys = run_cli("set", "talk_keys", "rightctrl, F15")
            assert keys.returncode == 0 and json.loads(settings_path.read_text())["talk_keys"] == ["RightCtrl", "F15"], \
                (keys.stdout, keys.stderr)
            assert "Fn is not a talk key" in run_cli("set", "talk_keys", "Fn").stderr
            assert run_cli("set", "talk_keys", "+F13").returncode == 0
            assert json.loads(settings_path.read_text())["talk_keys"] == ["RightCtrl", "F15", "F13"]
            assert run_cli("set", "talk_keys", "-f15").returncode == 0
            assert json.loads(settings_path.read_text())["talk_keys"] == ["RightCtrl", "F13"]
            assert run_cli("set", "talk_keys", "none").returncode == 0
            assert json.loads(settings_path.read_text())["talk_keys"] == []
            settings_path.write_text(json.dumps({"voice": "Miles", "previous": {}}))  # Written by an older Rook.
            assert run_cli("set", "owner_name", "Test Owner").returncode == 0
            saved = json.loads(settings_path.read_text())  # No write raises a person's access.
            assert "permission_mode" not in saved and "version" not in saved and saved["voice"] == "Miles", saved
            settings_path.write_text(json.dumps({"build_threads": {"opus": {"thread": "t-1", "model": "m"}}}))
            kept = run_cli("set", "build_threads.opus", "t-9")
            assert "It keeps its model." in kept.stdout, (kept.stdout, kept.stderr)
            assert json.loads(settings_path.read_text())["build_threads"]["opus"] == {"thread": "t-9", "model": "m"}
        finally:
            stop_srv.set()
            srv.close()
            thread.join(2)
    # mac-access wait polls a fresh helper check until the grant is on. The stand-in helper turns it on at its second
    # call. Only the microphone and the timeout run here: input would restart the real service.
    import contextlib
    import io
    stub_dir = Path(tempfile.mkdtemp(dir=os.environ.get("XDG_RUNTIME_DIR")))
    stub = stub_dir / "helper"
    stub.write_text('#!/bin/sh\nn=$(cat "$0.n" 2>/dev/null || echo 0); echo $((n+1)) > "$0.n"\n'
                    '[ "$n" -ge 1 ] && m=true || m=false\necho "{\\"microphone\\": $m, \\"input\\": false}"\n')
    stub.chmod(0o700)
    was_mac, was_wait, os.environ["ROOK_MAC_HELPER"] = desk.IS_MAC, MAC_WAIT_SECONDS, str(stub)
    try:
        desk.IS_MAC = True
        with contextlib.redirect_stdout(io.StringIO()) as out:
            mac_access_command(["wait", "microphone"])
        assert out.getvalue() == "microphone: allowed.\n" and (stub_dir / "helper.n").read_text().strip() == "2", \
            out.getvalue()
        globals()["MAC_WAIT_SECONDS"] = 0
        with contextlib.redirect_stdout(io.StringIO()) as out:
            mac_access_command(["wait", "input"])
        assert "input: still not allowed" in out.getvalue(), out.getvalue()
    finally:
        desk.IS_MAC, globals()["MAC_WAIT_SECONDS"] = was_mac, was_wait
        os.environ.pop("ROOK_MAC_HELPER")
        shutil.rmtree(stub_dir)
    print("Relay voice points: all checks passed.")


def no_machine_error(name):
    table = watch.machines()
    err = watch.machines_error()
    note = f" ({err})" if err else ""
    if not table:
        return f"No machines are configured in {watch.machines_file()}.{note}"
    return f"No machine named {name}. Machines: {', '.join(table)}.{note}"


def ask_watch(thread, machine, title):
    """Ask the running Rook to watch a thread. Return its answer, or None when Rook is not running, or is too old to
    take it: the list file then holds the watch for Rook's next start."""
    answer = ask_rook("watch", json.dumps({"thread": thread, "machine": machine, "title": title}))
    if answer is None:
        entries = watch.load()
        watch.add(entries, thread, machine, title)
        watch.save(entries)
    return answer


def watch_command(argv):
    if argv[0] == "watching":
        answer = ask_rook("watching")
        listing = answer["watching"] if answer and answer.get("ok") else [
            {key: entry.get(key) for key in ("thread", "machine", "title", "quiet_since")}
            for entry in watch.load().values()]
        print("\n".join(f"{e['machine']} | {e.get('title') or '?'} | {e['thread']}"
                        + (f" | quiet since {time_of_day(e['quiet_since'])}" if e.get("quiet_since") else "")
                        for e in listing) or "Rook watches no threads.")
        return
    args, options = argv[1:], {"machine": watch.local_machine(), "title": None}
    for flag in ("machine", "title"):
        if f"--{flag}" in args:
            at = args.index(f"--{flag}")
            options[flag], args = (args[at + 1] if at + 1 < len(args) else None), args[:at] + args[at + 2:]
    if len(args) != 1 or not options["machine"]:
        sys.exit("Usage: relay.py watch THREAD [--machine NAME] [--title TITLE]")
    if options["machine"] not in watch.machines():
        sys.exit(no_machine_error(options["machine"]))
    answer = ask_watch(args[0], options["machine"], options["title"])
    if answer is None:
        print(f"Saved. Rook watches {args[0]} on {options['machine']} from its next start.")
    elif answer.get("ok"):
        print(f"Rook now watches {args[0]} on {options['machine']}.")
    else:
        sys.exit(answer.get("error"))


def threads_command(argv):
    answer = ask_rook("threads", wait=10)
    if not answer or not answer.get("ok"):  # The roster lives in the running Rook. ponytail: no offline read.
        sys.exit((answer or {}).get("error") or "Rook is not running, so it holds no thread roster now.")
    rows = answer["threads"]
    if argv == ["--json"]:
        print(json.dumps(rows, indent=1))
        return
    print("\n".join(" | ".join(part for part in (
        row["machine"], row["orchestrator"], row["project"], row["title"] or "?",
        row["status"] + (", settled" if row["settled"] else "") + (", snoozed" if row["snoozed"] else ""), row["id"])
        if part) for row in rows) or "The roster holds no threads.")


def take_option(args, flag, default=None):
    """Remove --flag VALUE from args and return VALUE, or default when the flag is absent."""
    if flag not in args:
        return default
    at = args.index(flag)
    if at + 1 >= len(args):
        sys.exit(f"Give a value after {flag}.")
    value = args[at + 1]
    del args[at:at + 2]
    return value


def take_count(args, flag, default):
    value = take_option(args, flag, str(default))
    if not value.isdigit() or not 0 < int(value) <= 500:
        sys.exit(f"{flag} takes a number from 1 to 500.")
    return int(value)


def herdr_watch(machine, agent):
    """Have Rook watch a Herdr agent it sent to, and say when it is blocked or done."""
    answer = ask_watch(watch.herdr_thread(machine, agent), watch.local_machine(), agent)
    if answer is None:  # ask_watch kept the watch for Rook's next start.
        return " Rook is not running, so its result waits in Herdr. Rook watches it from its next start."
    if not answer.get("ok"):
        return f" Rook could not watch it: {answer.get('error')}"
    return f" Rook will say when it is done or needs {OWNER}."


def herdr_command(argv):
    """Herdr's agents: list, read, a guarded send, a start in a new pane that never takes focus, and an install."""
    import herdr
    args = list(argv)
    machine = take_option(args, "--machine")
    verb = args.pop(0) if args else None
    if verb == "agents" and not args and not machine:
        lines = []
        for label in (None, *herdr.machines()):
            try:
                agents = herdr.call(label, "agent", "list", timeout=8 if label else herdr.SECONDS)["agents"]
            except herdr.Failed as error:
                if label is None and error.code in ("server_not_running", "not_installed"):
                    lines.append("Herdr is not installed." if error.code == "not_installed"
                                 else "Herdr is not running on this machine.")
                    if error.code == "not_installed":
                        break
                else:
                    lines.append(f"{label or 'This machine'}: Herdr did not answer ({error}).")
                continue
            lines += [herdr.agent_line(agent, label or "this machine") for agent in agents]
        utter("\n".join(lines) or "Herdr runs no agents.")
        return
    if verb == "read" and args:
        lines = take_count(args, "--lines", 40)
        if len(args) != 1:
            leave("Usage: relay.py herdr read AGENT [--machine NAME] [--lines N]")
        try:
            info = herdr.call(machine, "agent", "get", args[0])["agent"]
            screen = herdr.call(machine, "agent", "read", args[0], "--source", "recent-unwrapped", "--lines",
                                str(lines), raw=True)
        except herdr.Failed as error:
            leave(f"Rook could not read {args[0]}: {error}")
        print(f"{herdr.target(info)} ({info.get('agent') or '?'}) is {info.get('agent_status') or 'unknown'} in "
              f"{herdr.short_path(info.get('foreground_cwd') or info.get('cwd'))}.")
        print(herdr.screen_tail(screen, lines) or "Its screen is empty.")  # A pane's words are data: never rendered.
        return
    if verb in ("send", "start") and args:
        kind = take_option(args, "--kind") if verb == "start" else None
        name = take_option(args, "--name") if verb == "start" else None
        model = take_option(args, "--model") if verb == "start" else None
        if len(args) != 2 or verb == "start" and not kind:
            leave("Usage: relay.py herdr send AGENT [--machine NAME] TEXT|-\n"
                     "       relay.py herdr start FOLDER --kind KIND [--model MODEL] [--name NAME] [--machine NAME] TEXT|-")
        text = (sys.stdin.read() if args[1] == "-" else args[1]).strip()
        if not text:
            leave("Give the text as an argument or on stdin.")
        agent, said = args[0], ""
        if verb == "start":
            try:
                info = herdr.start(machine, args[0], kind, name, model)
            except herdr.Failed as error:
                if error.code == "agent_not_ready":
                    leave(f"Herdr started {error.name}, but it waits at a startup question or approval. {OWNER_START} "
                             "answers it in Herdr. The first prompt was not sent." + herdr_watch(machine, error.name))
                leave(f"Herdr could not start the agent: {error}")
            agent = herdr.target(info)
            said = f"Started {agent} ({kind}) in {herdr.short_path(info.get('cwd'))}. "
        outcome, words = herdr.send(machine, agent, text)
        if outcome in ("sent", "unknown") or verb == "start":  # A started agent is watched whatever its prompt did.
            words += herdr_watch(machine, agent)
        if outcome != "sent":
            sys.exit(said + words)  # herdr.send renders its own words; the agent's name is data.
        print(said + words)
        return
    if verb == "install" and args in ([], ["--dry-run"]) and not machine:
        try:
            print(herdr.install(dry=bool(args)))
        except herdr.Failed as error:
            leave(f"{error}.")
        return
    leave("Usage: relay.py herdr agents | read AGENT | send AGENT TEXT | start FOLDER --kind KIND TEXT | install [--dry-run]")


def pi_command(argv):
    """Pi's saved sessions, read only: the newest, and the last messages of one."""
    import herdr
    args = list(argv)
    verb = args.pop(0) if args else None
    if verb == "sessions":
        limit = take_count(args, "--limit", 10)
        if args:
            sys.exit("Usage: relay.py pi sessions [--limit N]")
        lines = []
        for path in herdr.pi_files()[:limit]:
            try:
                sid, name, cwd, messages = herdr.pi_session(path)
                at = path.stat().st_mtime
            except OSError:  # Pi removed it during the scan.
                continue
            first = next((text for role, text in messages if role == "user"), "")
            lines.append(f"{sid[:8]} | {name or ' '.join(first.split())[:60] or 'untitled'} | "
                         f"{herdr.short_path(cwd)} | {datetime.fromtimestamp(at):%-d %b} {time_of_day(at)}")
        print("\n".join(lines) or f"Pi has no saved sessions in {herdr.short_path(str(herdr.PI_SESSIONS))}.")
        return
    if verb == "read" and args:
        count = take_count(args, "--messages", 6)
        if len(args) != 1:
            sys.exit("Usage: relay.py pi read SESSION [--messages N]")
        found = [p for p in herdr.pi_files() if p.stem.rpartition("_")[2].startswith(args[0])]
        if len(found) != 1:
            sys.exit(f"No Pi session starts with {args[0]}." if not found else
                     f"{len(found)} Pi sessions start with {args[0]}. Give more of the id.")
        try:
            sid, name, cwd, messages = herdr.pi_session(found[0])
        except OSError as error:
            sys.exit(f"Rook could not read that Pi session: {error}")
        print(f"Pi session {sid[:8]}, {name or 'untitled'}, in {herdr.short_path(cwd)}.")
        for role, text in messages[-count:]:
            text = " ".join(text.split())
            print(f"{'User' if role == 'user' else 'Pi'}: {text if len(text) <= 600 else text[:600] + '...'}")
        return
    if verb == "t3-login" and not args:
        # Pi's sign-in belongs to the server's name and address, so a short-lived t3 entry in Pi's own file carries it.
        # The entry goes again after, because a file entry overrides Rook's. A t3 entry of the person's own stays.
        try:
            runtime = json.loads((Path.home() / ".t3/userdata/server-runtime.json").read_text())
            url = f"http://{runtime['host']}:{int(runtime['port'])}/mcp"
        except (OSError, ValueError, KeyError, TypeError):
            sys.exit("T3 Code has not written its address. Start T3 Code, then run this again.")
        if not shutil.which("pi"):
            sys.exit("pi is not installed.")
        try:
            own = "t3" in json.loads((Path(os.environ.get("PI_CODING_AGENT_DIR") or Path.home() / ".pi/agent")
                                      / "mcp.json").read_text())["mcpServers"]
        except (OSError, ValueError, KeyError, TypeError):
            own = False
        if not own and subprocess.run(["pi", "mcp", "add", "t3", "--url", url], stdout=subprocess.DEVNULL).returncode:
            sys.exit("pi mcp add failed, so Pi is not signed in.")
        try:
            code = subprocess.run(["pi", "mcp", "login", "t3"]).returncode
        finally:
            if not own:
                subprocess.run(["pi", "mcp", "remove", "t3"], stdout=subprocess.DEVNULL)
        if code:
            sys.exit(code)
        print("Pi is signed in to T3's tools. Restart Rook to use them.")
        return
    sys.exit("Usage: relay.py pi sessions [--limit N] | pi read SESSION [--messages N] | pi t3-login")


# relay.py work's options, and the entry field each sets.
WORK_OPTIONS = {"--project": "project", "--machine": "machine", "--thread": "thread", "--title": "title",
                "--thread-link": "thread_link", "--done": "done_means", "--state": "state", "--waits": "waits_on",
                "--news": "news", "--link": "link", "--brief": "brief", "--commit": "commit", "--try": "try"}
WORK_USAGE = "Run relay.py help for the usage of relay.py work."


def inbox_command(argv):
    flags = set(argv)
    if len(flags) != len(argv) or not flags <= {"--all", "--json"}:
        leave("Usage: relay.py inbox [--all] [--json]")
    show_all = "--all" in flags
    as_json = "--json" in flags
    import agent_inbox
    import mailbox

    data = agent_inbox.gather()
    try:
        overlays = mailbox.pr_overlays()
    except mailbox.Unavailable as error:
        data = {**data, "errors": [*data["errors"], str(error)]}
        overlays = {}
    filtered, hidden = agent_inbox.apply_overlays(data, overlays, show_all=show_all)
    if as_json:
        print(json.dumps(filtered, indent=2))  # Data, printed as it is: the formatter renders its own words.
    else:
        print(agent_inbox.format_inbox(filtered, hidden_prs=hidden, pr_overlays=overlays if show_all else None))


MAILBOX_ADD_OPTIONS = {
    "--kind": "kind",
    "--summary": "summary",
    "--detail": "detail",
    "--thread": "thread",
    "--machine": "machine",
    "--project": "project",
    "--run": "run",
    "--parent-thread": "parent_thread",
}
MAILBOX_ADD_KINDS = ("reminder", "decision", "review", "needs")
MAILBOX_DURATION = re.compile(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?")
MAILBOX_MAX_DURATION = 365 * 86400


def _parse_mailbox_duration(token):
    """Parse a duration such as 30m, 1h30m, or 2d into seconds, or return None."""
    match = MAILBOX_DURATION.fullmatch(token.lower())
    if not match or not any(match.groups()):
        return None
    seconds = sum(int(n or 0) * unit for n, unit in zip(match.groups(), (86400, 3600, 60, 1)))
    return seconds if 0 < seconds <= MAILBOX_MAX_DURATION else None


def _parse_mailbox_until(tokens, now):
    """Parse a duration or clock time for mailbox snooze or focus."""
    if not tokens:
        sys.exit("Give a time or duration after --until, such as 30m, 2h, or 3:30 pm.")
    if len(tokens) == 1:
        seconds = _parse_mailbox_duration(tokens[0])
        if seconds is not None:
            return now + seconds
        if " " in tokens[0]:
            tokens = tokens[0].split()
    due, _, rest = clock_time(tokens)
    if rest:
        sys.exit("Give only one time or duration after --until.")
    return due


def mailbox_command(argv):
    import mailbox

    command, args = (argv[0] if argv else ""), argv[1:]
    thread_env = os.environ.get("T3CODE_THREAD_ID", "").strip()
    role = "rook" if os.environ.get("ROOK_AGENT") else "thread" if thread_env else "terminal"
    now = time.time()

    try:
        if command == "list":
            flags = set(args)
            if len(flags) != len(args) or not flags <= {"--all", "--sync", "--json"}:
                leave("Usage: relay.py mailbox list [--all] [--sync] [--json]")
            show_all, do_sync, as_json = "--all" in flags, "--sync" in flags, "--json" in flags
            if do_sync and role == "thread":
                leave(f"Only Rook or {OWNER} can sync the mailbox.")
            errors, failed_sources = [], {}
            if do_sync:
                sync_res = mailbox.sync(now=now)
                errors = sync_res["errors"]
                failed_sources = sync_res["failed_sources"]
            focus = mailbox.focus_get(now=now)
            if show_all:
                listed = mailbox.items(states=None, now=now)
                held_count = 0
            else:
                all_open = mailbox.items(states=("open",), now=now)
                if focus:
                    listed = [item for item in all_open if mailbox.related(item, focus)]
                    held_count = len(all_open) - len(listed)
                else:
                    listed = all_open
                    held_count = 0
            if as_json:
                json_items = [
                    {**item, "last_known_waiting": True}
                    if mailbox.item_source_failed(item, failed_sources)
                    else item
                    for item in listed
                ]
                print(json.dumps({  # Mailbox data, printed as it is.
                    "focus": focus,
                    "items": json_items,
                    "held_outside_focus": held_count,
                    "errors": errors,
                }, indent=2))
            else:
                print(mailbox.format_list(
                    listed,
                    focus=focus,
                    now=now,
                    errors=errors,
                    failed_sources=failed_sources,
                    held_count=held_count,
                    show_all=show_all,
                    details=True,
                ))
                if held_count:  # What else waits, listed without ending the focus.
                    outside = [item for item in all_open if not mailbox.related(item, focus)]
                    print("\nWaiting outside this focus:\n" + "\n".join(
                        mailbox.format_line(item, now, failed_sources=failed_sources) + mailbox.format_description(item)
                        for item in outside))
            return

        if command == "show":
            if len(args) != 1 or args[0].startswith("--"):
                leave("Usage: relay.py mailbox show ID")
            item = mailbox.get(args[0], now=now)
            if item is None:
                leave(f"No mailbox item {args[0]}.")
            print(mailbox.format_item(item))
            return

        if command == "add":
            fields, at = {}, 0
            while at < len(args):
                opt = args[at]
                if opt in MAILBOX_ADD_OPTIONS:
                    if at + 1 >= len(args) or not args[at + 1].strip():
                        leave(f"Give a value after {opt}.")
                    fields[MAILBOX_ADD_OPTIONS[opt]] = args[at + 1]
                    at += 2
                else:
                    leave("Usage: relay.py mailbox add --kind reminder|decision|review|needs "
                             "--summary TEXT [--detail TEXT] [--thread ID] [--machine NAME] [--project NAME]")
            kind = fields.get("kind")
            if kind not in MAILBOX_ADD_KINDS:
                leave(f"Use --kind with {', '.join(MAILBOX_ADD_KINDS)}.")
            if not fields.get("summary"):
                leave("Give --summary TEXT for the mailbox item.")
            if fields.get("detail") == "-":
                fields["detail"] = sys.stdin.read().strip()
            if "machine" in fields and fields["machine"] not in watch.machines():
                leave(no_machine_error(fields["machine"]))
            if role == "thread":
                local = watch.local_machine()
                if fields.get("thread") and fields["thread"] != thread_env:
                    leave("A T3 thread can add items only for itself.")
                if fields.get("machine") and fields["machine"] != local:
                    leave(f"A T3 thread on {local} can add items only for {local}.")
                fields["thread"] = thread_env
                fields["machine"] = local
            item = mailbox.observe(
                kind,
                fields["summary"],
                detail=fields.get("detail", ""),
                machine=fields.get("machine"),
                thread=fields.get("thread"),
                parent_thread=fields.get("parent_thread"),
                project=fields.get("project"),
                run=fields.get("run"),
                observed_at=now,
            )
            utter(item["id"])
            return

        if command == "answer":
            if role == "thread":
                leave(f"Only Rook or {OWNER} can answer mailbox items.")
            if len(args) < 2:
                leave("Usage: relay.py mailbox answer ID TEXT")
            text = sys.stdin.read().strip() if args[1:] == ["-"] else " ".join(args[1:]).strip()
            item = mailbox.answer(args[0], text, now=now)
            utter(f"Answered {item['id']}.")
            return

        if command == "dismiss":
            if role == "thread":
                leave(f"Only Rook or {OWNER} can dismiss mailbox items.")
            if not args:
                leave("Usage: relay.py mailbox dismiss ID [REASON]")
            reason_text = " ".join(args[1:]).strip() or None
            item = mailbox.dismiss(args[0], reason_text, now=now)
            utter(f"Dismissed {item['id']}.")
            return

        if command == "done":
            if role == "thread":
                leave(f"Only Rook or {OWNER} can mark mailbox items done.")
            if not args:
                leave("Usage: relay.py mailbox done ID [REASON]")
            reason_text = " ".join(args[1:]).strip() or None
            item = mailbox.done(args[0], reason_text, now=now)
            utter(f"Marked {item['id']} done.")
            return

        if command == "snooze":
            if role == "thread":
                leave(f"Only Rook or {OWNER} can snooze mailbox items.")
            if not args or args[0].startswith("--"):
                leave("Usage: relay.py mailbox snooze ID [--until TIME|DURATION]")
            item_id, rest = args[0], args[1:]
            until = None
            if rest:
                if rest[0] != "--until" or len(rest) not in (2, 3):
                    leave("Usage: relay.py mailbox snooze ID [--until TIME|DURATION]")
                until = _parse_mailbox_until(rest[1:], now)
            item = mailbox.snooze(item_id, until, now=now)
            if until is None:
                utter(f"Snoozed {item['id']} until you wake it.")
            else:
                utter(f"Snoozed {item['id']} until {time_of_day(until)}.")
            return

        if command == "wake":
            if role == "thread":
                leave(f"Only Rook or {OWNER} can wake mailbox items.")
            if len(args) != 1 or args[0].startswith("--"):
                leave("Usage: relay.py mailbox wake ID")
            item = mailbox.wake(args[0], now=now)
            utter(f"Woke {item['id']}.")
            return

        if command == "asked":
            if role != "rook":
                leave("Only Rook's agent can mark an item as asked.")
            if len(args) != 1 or args[0].startswith("--"):
                leave("Usage: relay.py mailbox asked ID")
            item = mailbox.mark_asked(args[0], at=now)
            utter(f"Marked {item['id']} as asked.")
            return

        if command == "pr":
            if role == "thread":
                leave(f"Only Rook or {OWNER} can change pull request overlays.")
            if len(args) < 2 or args[0] not in ("ignore", "snooze", "wake"):
                leave("Usage: relay.py mailbox pr ignore|snooze|wake OWNER/REPO#N [--until TIME|DURATION]")
            action, raw_ref, rest = args[0], args[1], args[2:]
            pr_ref = mailbox.normalize_pr(raw_ref)
            if action == "ignore":
                reason_text = None
                if rest:
                    if rest[0] == "--reason" and len(rest) >= 2:
                        reason_text = " ".join(rest[1:]).strip()
                    else:
                        leave("Usage: relay.py mailbox pr ignore OWNER/REPO#N [--reason TEXT]")
                item = mailbox.observe("pr", pr_ref, pr=pr_ref, observed_at=now)
                item = mailbox.dismiss(item["id"], reason_text or f"ignored by {OWNER}", now=now)
                utter(f"Ignored {pr_ref} ({item['id']}).")
                return
            if action == "snooze":
                until = None
                if rest:
                    if rest[0] != "--until" or len(rest) not in (2, 3):
                        leave("Usage: relay.py mailbox pr snooze OWNER/REPO#N [--until TIME|DURATION]")
                    until = _parse_mailbox_until(rest[1:], now)
                item = mailbox.observe("pr", pr_ref, pr=pr_ref, observed_at=now)
                item = mailbox.snooze(item["id"], until, now=now)
                if until is None:
                    utter(f"Snoozed {pr_ref} ({item['id']}) until you wake it.")
                else:
                    utter(f"Snoozed {pr_ref} ({item['id']}) until {time_of_day(until)}.")
                return
            if rest:
                leave("Usage: relay.py mailbox pr wake OWNER/REPO#N")
            existing = mailbox.get_by_pr(pr_ref, now=now)
            if existing is None:
                leave(f"There is no overlay for {pr_ref}.")
            item = mailbox.wake(existing["id"], now=now)
            utter(f"Woke {pr_ref} ({item['id']}).")
            return

        if command == "focus":
            sub, rest = (args[0] if args else ""), args[1:]
            if sub == "status" and not rest:
                focus = mailbox.focus_get(now=now)
                print(mailbox.format_focus(focus) if focus else "No focus lock is set.")
                return
            if sub == "clear" and not rest:
                if role == "thread":
                    leave(f"Only Rook or {OWNER} can change the focus lock.")
                focus = mailbox.focus_get(now=now)
                had = mailbox.focus_clear()
                if not had:
                    utter("No focus lock was set.")
                    return
                waiting = [item for item in mailbox.items(states=("open",), now=now)
                           if not focus or not mailbox.related(item, focus)]
                utter("Cleared the focus lock." + ("" if not waiting else
                      f" Give {OWNER} one account of what waited, and the first item that needs {pn('him')}, in this answer.\n\n"
                      + mailbox.format_list(waiting, now=now, details=True)))
                return
            if sub == "set":
                if role == "thread":
                    leave(f"Only Rook or {OWNER} can change the focus lock.")
                threads, projects, topic, machine, until = [], [], "", None, None
                at = 0
                while at < len(rest):
                    opt = rest[at]
                    if opt == "--thread" and at + 1 < len(rest) and not rest[at + 1].startswith("--"):
                        at += 1
                        while at < len(rest) and not rest[at].startswith("--"):
                            threads.append(rest[at])
                            at += 1
                    elif opt == "--project" and at + 1 < len(rest) and not rest[at + 1].startswith("--"):
                        at += 1
                        while at < len(rest) and not rest[at].startswith("--"):
                            projects.append(rest[at])
                            at += 1
                    elif opt == "--topic" and at + 1 < len(rest):
                        topic = rest[at + 1]
                        at += 2
                    elif opt == "--machine" and at + 1 < len(rest):
                        machine = rest[at + 1]
                        if machine not in watch.machines():
                            leave(no_machine_error(machine))
                        at += 2
                    elif opt == "--for" and at + 1 < len(rest):
                        seconds = _parse_mailbox_duration(rest[at + 1])
                        if seconds is None:
                            leave(f"{rest[at + 1]!r} is not a valid duration. Use 30m, 1h, or 2d.")
                        until = now + seconds
                        at += 2
                    elif opt == "--until" and at + 1 < len(rest):
                        end = at + 3 if at + 2 < len(rest) and rest[at + 2].lower().replace(".", "") in ("am", "pm") else at + 2
                        until = _parse_mailbox_until(rest[at + 1:end], now)
                        at = end
                    else:
                        leave("Usage: relay.py mailbox focus set [--thread ID ...] [--project NAME ...] "
                                 "[--topic TEXT] [--for DURATION]")
                if not threads and not projects and not topic.strip():
                    leave("Give at least one --thread, --project, or --topic for the focus lock.")
                scoped_threads = [(machine, tid) if machine else tid for tid in threads]
                focus = mailbox.focus_set(scoped_threads, projects, topic, until=until, now=now)
                print(mailbox.format_focus(focus) + ".")
                return
            leave("Usage: relay.py mailbox focus set ... | status | clear")

        if command == "sync":
            if role == "thread":
                leave(f"Only Rook or {OWNER} can sync the mailbox.")
            if args:
                leave("Usage: relay.py mailbox sync")
            res = mailbox.sync(now=now)
            lines = [f"Synced mailbox: {len(res['upserted'])} updated, {len(res['closed'])} closed."]
            if res["errors"]:
                lines.extend(res["errors"])
            utter("\n".join(lines))
            return

        leave("Use relay.py mailbox list, show, add, answer, dismiss, done, snooze, wake, asked, pr, focus, or sync.")
    except (mailbox.MailboxError, ValueError) as error:
        leave(str(error))


def work_actor():
    """Name who edits the work list: rook, a T3 thread, or the owner in a terminal."""
    thread = os.environ.get("T3CODE_THREAD_ID", "").strip()
    return thread, ("rook" if os.environ.get("ROOK_AGENT") else f"thread {thread}" if thread else "terminal")


def validate_work_fields(fields):
    if len(fields.get("brief") or "") > work.BRIEF:
        sys.exit(f"The brief is {len(fields['brief'])} characters, and the list keeps at most {work.BRIEF}.")
    if "state" in fields and fields["state"] not in work.STATES:
        sys.exit(f"{fields['state']!r} is not a state. States: {', '.join(work.STATES)}.")
    if "machine" in fields and fields["machine"] not in watch.machines():
        sys.exit(no_machine_error(fields["machine"]))


def work_added_line(entry, name_in_brief=True):
    return (f"Added work {entry['id']}, {entry['state']}. Name work {entry['id']} in the brief."
            if name_in_brief and entry["state"] == "drafted" else f"Added work {entry['id']}, {entry['state']}.")


def work_command(argv):
    command, args = (argv[0] if argv else ""), argv[1:]
    # Who writes: Rook's own Claude, a T3 thread, which the entry records, or the owner in a terminal.
    thread, by = work_actor()
    now = time.time()
    if command == "list":
        since = None
        if args[:1] == ["--since"] and len(args) == 2:
            span_match = re.fullmatch(r"(\d+)([hd])", args[1])
            if args[1] == "today":
                since = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            elif span_match:
                since = now - int(span_match[1]) * (3600 if span_match[2] == "h" else 86400)
            else:
                leave(f"{args[1]!r} is not a time Rook can list from. Use today, 12h, or 3d.")
        elif args not in ([], ["--all"]):
            leave("Usage: relay.py work list [--all | --since today|12h|3d]")
        try:
            entries = work.listing(work.load(), now, everything=args == ["--all"], since=since)
        except work.Unreadable as error:
            leave(str(error))
        print("\n".join(work.line(entry, now) for entry in entries) or
              ("Nothing finished or went live then." if since else "The work list is empty." if args else
               "Nothing is open on the work list."))
        return
    words, fields, at = [], {}, 0
    while at < len(args):
        if args[at] in WORK_OPTIONS:
            if at + 1 >= len(args) or not args[at + 1].strip():
                leave(f"Give a value after {args[at]}.")
            fields[WORK_OPTIONS[args[at]]] = args[at + 1]
            at += 2
        elif args[at].startswith("--"):
            leave(f"{args[at]} is not an option of relay.py work {command}. {WORK_USAGE}")
        else:
            words.append(args[at])
            at += 1
    if fields.get("brief") == "-":
        fields["brief"] = sys.stdin.read().strip()
    validate_work_fields(fields)
    if command not in ("add", "update", "show", "close", "drop"):
        leave(f"Use relay.py work add, update, list, show, close, or drop. {WORK_USAGE}")
    if command == "add":
        fields["wish"] = " ".join(words).strip()
        if not fields["wish"] or not fields.get("project"):
            leave('Give the wish and its project, such as relay.py work add "fix the export" --project acme-demo.')
        if by.startswith("thread ") and "thread" not in fields:
            fields["thread"] = thread
    elif command != "update" and (len(words) < 1 or fields or (command != "drop" and len(words) > 1)):
        leave(f"Usage: relay.py work {command} ID" + (" [REASON]" if command == "drop" else ""))
    elif command == "update" and not fields:
        leave("Give at least one change, such as --state running or --news TEXT.")
    try:
        with work.changing() as data:
            if command == "add":
                entry = work.add(data, fields, by, now)
            else:
                if words[:1] and words[0].isdigit():
                    entry = work.find(data, int(words[0]))
                    if entry is None:
                        leave(f"The work list has no entry {words[0]}.")
                    if command == "update" and len(words) > 1:
                        leave(f"Put the text in an option, such as --news. {WORK_USAGE}")
                elif command == "update" and by.startswith("thread ") and not words:
                    mine = [e for e in data["entries"] if e["thread"] == thread and work.is_open(e) and e["state"] in work.OPEN]
                    if len(mine) != 1:
                        leave("This thread has no entry in progress. Add one with relay.py work add." if not mine else
                                 f"This thread has entries in progress {', '.join(str(e['id']) for e in mine)}. Give the number.")
                    entry = mine[0]
                else:
                    leave(f"Give the entry's number, such as relay.py work {command} 7.")
                if command == "close":
                    work.change(entry, {"state": "done"} if entry["state"] in work.OPEN else {}, by, now)
                    entry["closed"] = entry.get("closed") or now
                elif command == "drop":
                    work.change(entry, {"state": "dropped", **({"news": " ".join(words[1:])} if words[1:] else {})}, by, now)
                    entry["closed"] = entry.get("closed") or now
                elif command == "update":
                    work.change(entry, fields, by, now)
    except work.Unreadable as error:
        leave(str(error))
    if command == "show":
        print("\n".join(f"{key}: {datetime.fromtimestamp(value).strftime('%Y-%m-%d %H:%M') if key in ('made', 'changed', 'finished', 'live_at', 'closed') and value else value}"
                        for key, value in entry.items() if key != "brief") + f"\nbrief:\n{entry.get('brief') or '(none kept)'}")
    elif command == "add":
        print(work_added_line(entry))
    elif command in ("close", "drop"):
        verb = "Closed" if command == "close" else "Dropped"
        wish = work.sentence(entry["wish"]) if entry.get("wish") else ""
        head = f"{verb} {work.where(entry)}: {wish}" if wish else f"{verb} {work.where(entry)}."
        print(f"{head} It leaves the list. [id {entry['id']}]")
    else:
        print(work.line(entry, now))


def ask_command(argv):
    flags = [arg for arg in argv[1:] if arg in ("--no-image", "--test")]
    args = [arg for arg in argv[1:] if arg not in flags]
    # A typed request speaks with the owner's authority. Rook's own Claude Code runs with ROOK_AGENT set, and a
    # T3 thread with T3CODE_THREAD_ID: a thread reports with tell. Only the build threads' tests may ask.
    if os.environ.get("ROOK_AGENT"):
        leave("Rook does not ask itself. Answer the request in this turn.")
    thread = os.environ.get("T3CODE_THREAD_ID")
    if (thread or "--test" in flags) and not (thread in active_build_threads().values() and "--test" in flags):
        leave(f"A T3 thread cannot ask Rook as {OWNER}. Report with relay.py tell.")
    text = " ".join(args).strip() if args and args != ["-"] else sys.stdin.read().strip()
    if not text:
        leave("Give the request as an argument or on stdin.")
    # Rook waits up to five minutes to be free and five more for the answer.
    answer = ask_rook(" ".join(["ask", *flags]), text, wait=630)
    if answer is None:
        leave(f"Rook is not running: nothing answers at {INBOX}.")
    if not answer.get("ok"):
        leave(answer.get("error") or answer.get("answer") or "Rook could not answer.")  # The agent's own reason.
    print(answer.get("spoken") or answer.get("answer") or "")  # The agent's own answer: never rendered again.


# A project name is a plain folder name.
PROJECT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
# What a folder on a machine is: missing, a file, an empty folder, or a folder that holds something.
FOLDER_STATE = ('if [ ! -e "$1" ]; then echo missing; elif [ ! -d "$1" ]; then echo file; '
                'elif [ -z "$(ls -A "$1")" ]; then echo empty; else echo full; fi')


def run_on(machine, *args, timeout=60):
    """Run a command on a machine, as the machine table says, and return (exit code, output, error)."""
    try:
        done = subprocess.run(watch.on(machine, *args), capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as error:
        return 1, "", str(error)
    return done.returncode, done.stdout, done.stderr


def reason(error):
    """The line of a command's error output that says what went wrong, without a stack trace."""
    lines = [line.strip() for line in error.splitlines() if line.strip() and not line.strip().startswith("at ")]
    return next((line for line in lines if "Error" in line), lines[-1] if lines else "no error output")


def project_command(argv):
    if argv[:1] == ["list"]:
        sys.exit("The t3 command cannot list projects. The T3 tools can, with t3_project_list.")
    args, options = argv[1:], {"machine": watch.local_machine(), "path": None}
    git = "--git" in args
    args = [arg for arg in args if arg != "--git"]
    for flag in ("machine", "path"):
        if f"--{flag}" in args:
            at = args.index(f"--{flag}")
            options[flag], args = (args[at + 1] if at + 1 < len(args) else ""), args[:at] + args[at + 2:]
    if argv[:1] != ["new"] or len(args) != 1:
        sys.exit("Usage: relay.py project new NAME [--machine NAME] [--path PATH] [--git]")
    name, machine = args[0], options["machine"]
    if not PROJECT_NAME.fullmatch(name):
        sys.exit(f"{name!r} is not a plain folder name. Use letters, digits, dots, dashes, and underscores.")
    if machine not in watch.machines():
        sys.exit(no_machine_error(machine))
    path = options["path"] or posixpath.join(projects_folder_in_force(read_settings()[0], machine)[0], name)
    if not path.startswith("/") or posixpath.normpath(path) != path or "\n" in path:
        sys.exit(f"{path!r} is not a plain absolute path.")
    code, out, error = run_on(machine, "sh", "-c", FOLDER_STATE, "sh", path)
    state = out.strip()
    if code or state not in ("missing", "file", "empty", "full"):
        sys.exit(f"Could not reach {machine}: {reason(error)}")
    if state == "file":
        sys.exit(f"{path} on {machine} is a file, not a folder.")
    made = state == "missing"
    if made and run_on(machine, "mkdir", path)[0]:
        sys.exit(f"Could not make {path} on {machine}. Its parent folder may be missing.")
    t3 = watch.machines()[machine]["t3"]

    def undo(project=None):
        """Take back what this command did: the project it added, and the folder it made, while empty."""
        if project:
            run_on(machine, t3, "project", "remove", project)
        if made:
            run_on(machine, "rmdir", path)

    code, out, error = run_on(machine, t3, "project", "add", path, "--title", name)
    if code:
        if "already exists" in error + out:
            if made:
                # A project names this path, but its folder was missing. Take back the folder made here.
                undo()
                sys.exit(f"A T3 project for {path} on {machine} exists, but its folder was missing.")
            # Already that project. The CLI gives no id for it, and its thread list cannot prove which project
            # a row belongs to, since it resolves an enclosing project too. So no id is guessed.
            print(f"exists {machine} unknown-id {path}")
            return
        undo()
        sys.exit(f"T3 Code on {machine} could not add the project: {reason(error)}")
    found = re.search(r"Added project (\S+)", out)
    project = found.group(1) if found else None
    if state == "full":
        # The folder already held files and was not a project. The project just added goes again.
        undo(project or path)
        sys.exit(f"{path} on {machine} already holds files and is not a T3 project. Choose another name.")
    if git and run_on(machine, "git", "init", "-q", path)[0]:
        undo(project or path)
        sys.exit(f"git init failed in {path} on {machine}, so the project was taken back.")
    print(f"created {machine} {project or 'unknown-id'} {path}")


NUMBERS = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
           "sixteen seventeen eighteen nineteen").split()
TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()
# A timer runs for one day at most. A duration is hours, minutes, and seconds, such as 1h30m.
TIMER_SECONDS = 24 * 3600
DURATION = re.compile(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?")
TIMER_LABEL = 60


def words(n):
    """A whole number as a voice reads it well, such as forty five. From 100 up, digits."""
    if n < 20:
        return NUMBERS[n]
    if n < 100:
        return TENS[n // 10 - 2] + (f" {NUMBERS[n % 10]}" if n % 10 else "")
    return str(n)


def span(seconds):
    """A time span in words, such as two hours and five minutes, to the nearest minute."""
    minutes = round(seconds / 60)
    if minutes < 1:
        return "less than a minute"
    days, hours, minutes = minutes // 1440, minutes // 60 % 24, minutes % 60
    parts = [f"{words(n)} {unit}{'s' if n != 1 else ''}"
             for n, unit in ((days, "day"), (hours, "hour"), (minutes, "minute")) if n][:2]
    return " and ".join(parts)


def time_of_day(at=None, seconds=False):
    """A wall-clock time on the 12-hour clock, such as 2:21 pm, for text that reaches Rook's model. Now when at is
    None. Commands take this form too, and 24-hour times."""
    return time.strftime("%-I:%M:%S %p" if seconds else "%-I:%M %p", time.localtime(at)).lower()


def clock_time(args):
    """Read the clock time at the start of args: 15:30, or 3:30 pm, 3:30pm, 3:30 p.m. or 3 pm. An am or pm in the
    next word belongs to the time, never to a label. Return (the next such time as a timestamp, "HH:MM", the words
    after it). Exit with one sentence when it is no clock time."""
    words = list(args[:1])
    if len(args) > 1 and args[1].lower().replace(".", "") in ("am", "pm"):
        words.append(args[1])
    clock = re.fullmatch(r"(\d{1,2})(?::([0-5]\d))?\s*(?:([ap])\.?m\.?)?", " ".join(words).lower())
    if not clock or not clock[2] and not clock[3] or not (1 <= int(clock[1]) <= 12 if clock[3] else int(clock[1]) <= 23):
        sys.exit(f"{' '.join(words)!r} is not a clock time. Use 1 to 12 with am or pm, such as 3:30 pm, "
                 "or 24-hour time, such as 15:30.")
    hour, minute = int(clock[1]) % 12 + 12 * (clock[3] == "p") if clock[3] else int(clock[1]), int(clock[2] or 0)
    now = datetime.now()
    due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return (due + timedelta(days=1) if due <= now else due).timestamp(), f"{hour:02d}:{minute:02d}", args[len(words):]


def timer_command(argv):
    command, args = (argv[0] if argv else ""), argv[1:]
    if command == "list":
        answer = ask_rook("timer list")
    elif command == "cancel" and args:
        answer = ask_rook("timer cancel", " ".join(args))
    elif command == "set" and args:
        timer = {}
        if "--task" in args:
            at = args.index("--task")
            timer["task"], args = " ".join(args[at + 1:]).strip(), args[:at]
            if not timer["task"] or not args:
                sys.exit("Give the task after --task, and the duration or --at before it.")
        if args[0] == "--at":
            timer["due"], timer["clock"], args = clock_time(args[1:])
        else:
            parts = DURATION.fullmatch(args[0].lower())
            seconds = sum(int(n or 0) * unit for n, unit in zip(parts.groups(), (3600, 60, 1))) if parts else 0
            if not 0 < seconds <= TIMER_SECONDS:
                sys.exit(f"{args[0]!r} is not a duration Rook can time. Use 10m, 90s, or 1h30m, up to 24h, "
                         "or --at 3:30 pm.")
            timer["seconds"], args = seconds, args[1:]
        timer["label"] = " ".join(" ".join(args).split())[:TIMER_LABEL]
        answer = ask_rook("timer set", json.dumps(timer))
    else:
        sys.exit("Usage: relay.py timer set DURATION|--at TIME [LABEL] [--task TEXT], timer list, or timer cancel ID|LABEL|all")
    if answer is None:
        sys.exit(f"Rook is not running, so it cannot keep a timer: nothing answers at {INBOX}.")
    if not answer.get("ok"):
        sys.exit(answer.get("error") or "Rook could not do that.")

    def describe(timer):
        due = timer["due"]
        if timer.get("held"):
            reason = timer.get("held_reason") or "waiting"
            return (f"Timer {timer['id']}" + (f" ({timer['label']})" if timer.get("label") else "")
                    + f" was due at {time_of_day(due)} (held: {reason})"
                    + (f". Task: {timer['task']}" if timer.get("task") else ""))
        return (f"Timer {timer['id']}" + (f" ({timer['label']})" if timer.get("label") else "")
                + f" goes off at {time_of_day(due)}, in {span(max(0, due - time.time()))}"
                + (f". Task: {timer['task']}" if timer.get("task") else ""))

    if command == "list":
        print("\n".join(describe(timer) + "." for timer in answer["timers"]) or "No timers are set.")
    elif "cancelled" in answer:
        count = len(answer["cancelled"])
        print(f"Cancelled {words(count)} timer{'s' if count != 1 else ''}." if count else "No timers were set.")
    elif command == "set":
        print(f"Set. {describe(answer['timer'])}.")
    else:
        timer = answer["timer"]
        print(f"Cancelled timer {timer['id']}" + (f" ({timer['label']})." if timer.get("label") else "."))


def dark_command(argv):
    command, args = (argv[0] if argv else ""), argv[1:]
    if command == "on":
        until = None
        if args[:1] == ["--until"] and len(args) in (2, 3):
            until, _, rest = clock_time(args[1:])
            if rest:
                leave("Usage: relay.py dark on [--for DURATION | --until TIME]")
        elif args[:1] == ["--for"] and len(args) == 2:
            parts = DURATION.fullmatch(args[1].lower())
            seconds = sum(int(n or 0) * unit for n, unit in zip(parts.groups(), (3600, 60, 1))) if parts else 0
            if not 0 < seconds <= TIMER_SECONDS:
                leave(f"{args[1]!r} is not a duration Rook can go dark for. Use 30m, 1h, or 1h30m, up to 24h.")
            until = time.time() + seconds
        elif args:
            leave("Usage: relay.py dark on [--for DURATION | --until TIME]")
        answer = ask_rook("dark on", json.dumps({"until": until}))
    elif command in ("off", "status") and not args:
        answer = ask_rook(f"dark {command}")
    else:
        leave("Usage: relay.py dark on [--for DURATION | --until TIME], dark off, or dark status")
    if answer is None:
        leave(f"Rook is not running, so it cannot go dark: nothing answers at {INBOX}.")
    if not answer.get("ok"):
        leave(answer.get("error") or "Rook could not do that.")

    def end(dark):
        if not dark["until"]:
            return f"until {OWNER} ends it"
        return (f"until {time_of_day(dark['until'])}, "
                f"in {span(max(0, dark['until'] - time.time()))}")

    if command == "on":
        utter(("Rook stays dark, now " if answer["extended"] else "Rook is dark ") + end(answer["dark"]) + ".")
    elif command == "off":
        utter(f"Rook is back online after {span(time.time() - answer['was']['since'])} dark." if answer["was"]
              else "Rook was not dark.")
    else:
        dark = answer["dark"]
        utter(f"Rook is dark since {time_of_day(dark['since'])}, {end(dark)}." if dark
              else "Rook is not dark.")


def forge_command(argv):
    """Run themes/forge/forge.py (new, bake, list) headless and muted; bakes run under flock + scripts/capped."""
    if not argv or argv[0] not in ("new", "bake", "list", "-h", "--help"):
        sys.exit("Usage: relay.py forge <new|bake|list> ...")
    forge_script = ROOT / "themes" / "forge" / "forge.py"
    if not forge_script.is_file():
        sys.exit(f"Forge script missing: {forge_script}")
    env = {**os.environ, "SDL_AUDIODRIVER": "dummy", "PULSE_SERVER": "/dev/null", "AUDIODEV": "null"}
    done = subprocess.run([sys.executable, str(forge_script), *argv], env=env)
    if done.returncode:
        sys.exit(done.returncode)


def media_command(argv):
    import media
    usage = "Usage: relay.py media [status | pause [PLAYER] | play [PLAYER] | toggle [PLAYER]]"
    if not argv:
        action, target = "status", None
    else:
        action = argv[0].lower()
        rest = argv[1:]
        if action == "status":
            if rest:
                sys.exit(usage)
            target = None
        elif action in ("pause", "play", "toggle"):
            if any(arg.startswith("-") for arg in rest):
                sys.exit(usage)
            target = " ".join(rest).strip() or None
        else:
            sys.exit(usage)
    ok, output = media.control(action, target)
    if not ok:
        sys.exit(output)
    print(output)


def show_command(argv):
    if argv == ["--close"]:
        answer = ask_rook("show", json.dumps({"close": True}), wait=15)
    else:
        args, options = list(argv), {"title": None, "machine": None, "note": None}
        for flag in ("title", "machine", "note"):
            if f"--{flag}" in args:
                at = args.index(f"--{flag}")
                options[flag], args = (args[at + 1] if at + 1 < len(args) else ""), args[:at] + args[at + 2:]
        if len(args) != 1 or "" in options.values() or args[0].startswith("--"):
            sys.exit("Usage: relay.py show FILE [--title TITLE] [--machine NAME] [--note TEXT], or relay.py show --close")
        if options["note"] and len(options["note"]) > 500:
            sys.exit(f"The note has {len(options['note'])} characters. Keep it to 500 at most.")
        path, machine = args[0], options["machine"]
        if machine is not None and machine not in watch.machines():
            sys.exit(no_machine_error(machine))
        if machine is not None and not (watch.machines()[machine].get("run") or []):
            machine = None  # This machine: the file is shown where it is.
        if machine is None:
            path = os.path.abspath(os.path.expanduser(path))
        elif not posixpath.isabs(path) or "\n" in path:
            sys.exit(f"Give the full path of the file on {options['machine']}, such as /home/user/picture.png.")
        # Who asks: Rook's own Claude shows at once, inside the owner's turn; a T3 thread's show waits for the owner. This
        # guards against mistakes, not attacks: everything runs as the owner's user.
        thread = os.environ.get("T3CODE_THREAD_ID", "").strip()
        source = "rook" if os.environ.get("ROOK_AGENT") else "thread" if thread else "terminal"
        if options["note"] and source != "thread":
            sys.exit("Only a T3 thread's show carries a note. It goes in the turn where Rook presents the file.")
        answer = ask_rook("show", json.dumps({"path": path, "title": options["title"], "machine": machine,
                                              "source": source, "thread": thread or None,
                                              **({"note": options["note"]} if options["note"] else {})}), wait=120)
    if answer is None:
        sys.exit(f"Rook is not running: nothing answers at {INBOX}.")
    if not answer.get("ok"):
        sys.exit(answer.get("error") or "Rook could not show it.")
    print(answer.get("said") or "Done.")


def plugin_command(argv):
    """relay.py plugin list|enable ID|disable ID|check. Its output is read aloud: plain words, short sentences."""
    import plugin_loader
    if argv in (["list"], ["check"]):
        doc = plugin_loader.resolve()
        if not doc["plugins"] and not doc["diagnostics"]:
            return print("No plugins are installed.")
        for plugin in doc["plugins"]:
            state = "on" if plugin["active"] else "off"
            print(f"{plugin['id']}: {state}, {plugin['reason']}. {plugin['description'].rstrip('.')}.")
        for note in doc["diagnostics"]:
            print(note)
        if argv == ["check"]:
            if doc["diagnostics"]:
                sys.exit(f"{len(doc['diagnostics'])} plugin problem{'s' if len(doc['diagnostics']) > 1 else ''}.")
            print("Every plugin checks out.")
        return
    if len(argv) != 2 or argv[0] not in ("enable", "disable"):
        sys.exit("Usage: relay.py plugin list|enable ID|disable ID|check")
    pid, on = argv[1], argv[0] == "enable"
    if not any(plugin["id"] == pid for plugin in plugin_loader.resolve()["plugins"]):
        sys.exit(f"No usable plugin named {pid} is installed. relay.py plugin list shows them.")
    try:
        saved, previous = read_settings(strict=True)
    except (OSError, ValueError) as exc:
        sys.exit(f"Could not read {CONFIG}: {str(exc).rstrip('.')}. Fix the file before changing settings.")
    try:
        write_settings({**saved, "plugins": {**saved.get("plugins", {}), pid: on}}, previous, updated={"plugins"})
    except (OSError, ValueError) as exc:
        sys.exit(f"Could not write {CONFIG}: {str(exc).rstrip('.')}.")
    plugin = next(plugin for plugin in plugin_loader.resolve()["plugins"] if plugin["id"] == pid)
    if on and not plugin["active"]:
        return print(f"Saved, but the {pid} plugin stays off: {plugin['reason']}.")
    print(f"The {pid} plugin is {'on' if on else 'off'}. The agent sees the change at Rook's next start.")


_OPTIONAL_COMMAND_MODULES = ("wow/relay_commands.py",)


def _optional_help(modules=_OPTIONAL_COMMAND_MODULES):
    """Read optional command help literals without importing any optional module."""
    helps, edits = [], []
    for rel in modules:
        mod_path = (SCRIPT.parent.parent / rel).resolve()
        if not mod_path.is_file():
            continue
        try:
            tree = ast.parse(mod_path.read_text(), filename=str(mod_path))
        except (OSError, SyntaxError):
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            target = node.targets[0].id
            if target == "HELP":
                try:
                    val = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    continue
                if isinstance(val, str) and val.strip():
                    helps.append(val.strip("\n"))
            elif target == "HELP_EDITS":
                try:
                    val = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    continue
                if isinstance(val, (list, tuple)):
                    edits.extend(val)
    return helps, edits


def _load_command_module(name, module_name, mod_path):
    """Load a command module from its exact file, and check that the loaded file is that file. None when no loader."""
    if Path(mod_path).resolve() != Path(mod_path):  # A link swapped in after the path was checked.
        sys.exit(f"Could not load the {name} command from {mod_path}.")
    try:
        spec = importlib.util.spec_from_file_location(module_name, mod_path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as error:
        sys.exit(f"Could not load the {name} command: {error}")
    loaded = getattr(mod, "__file__", None)
    if not loaded or Path(loaded).resolve() != mod_path:
        sys.exit(f"Could not load the {name} command from {mod_path}.")
    return mod


def _optional_command(name):
    """Lazily load an optional relay command from its exact file under this checkout, or return None."""
    root = str(SCRIPT.parent.parent.resolve())
    for idx, rel in enumerate(_OPTIONAL_COMMAND_MODULES):
        mod_path = (SCRIPT.parent.parent / rel).resolve()
        if not mod_path.is_file():
            continue
        if root not in sys.path:
            sys.path.insert(0, root)
        mod = _load_command_module(name, f"_rook_optional_relay_{idx}", mod_path)
        if mod is None:
            continue
        commands = getattr(mod, "COMMANDS", {})
        if name in commands:
            return commands[name]
    return None


def _plugin_command(name):
    """Lazily load an installed plugin's relay command by the exact path its activation names, or return None.
    Only a name no native command takes reaches here, so native commands never read a plugin file."""
    import plugin_loader
    if (found := plugin_loader.command(name)) is None:
        return None
    plugin, mod_path = found
    mod = _load_command_module(name, f"_rook_plugin_relay_{plugin.replace('-', '_')}", Path(mod_path))
    handler = getattr(mod, "COMMANDS", {}).get(name) if mod else None
    if not callable(handler):
        sys.exit(f"The {plugin} plugin does not define the {name} command.")
    return handler


def _plugin_help():
    """Help lines for every installed plugin command: its module's HELP, read by AST, or one plain line."""
    import plugin_loader
    lines, modules = [], {}
    for name, entry in plugin_loader.activation()["installed_commands"].items():
        modules.setdefault(entry["module"], (entry["plugin"], []))[1].append(name)
    for module, (plugin, names) in modules.items():
        helps = _optional_help((module,))[0]
        lines += helps or [f"relay.py {name:<{max(len(name) + 1, 19)}}A command of the {plugin} plugin." for name in names]
    return lines


def _usage():
    text = __doc__.strip()
    helps, edits = _optional_help()
    for old, new in edits:
        text = text.replace(old, new, 1)
    if helps:
        block = "\n".join(helps) + "\n"
        marker = "relay.py clip TEXT|-"
        text = text.replace(marker, block + marker, 1) if marker in text else text + "\n" + block.rstrip("\n")
    if plugin_lines := _plugin_help():
        text += "\n" + "\n".join(plugin_lines)
    return settings.render(text)  # The help is Rook's own words.


SYSTEMD_RUN = "/usr/bin/systemd-run"
WL_COPY = "/usr/bin/wl-copy"
WL_PASTE = "/usr/bin/wl-paste"
CLIP_MAX = 2000
CLIP_WAIT = 1.0


def clip_command(argv):
    text = (sys.stdin.read() if argv == ["-"] else " ".join(argv)).strip()
    if not text:
        sys.exit("Give text to copy to the clipboard.")
    if len(text) > CLIP_MAX:
        sys.exit(f"Text is too long to copy ({len(text)} characters, max {CLIP_MAX}).")
    if "\x00" in text:
        sys.exit("Text cannot hold a null byte.")
    if desk.IS_MAC:
        if error := desk.copy_clipboard(text):
            sys.exit(error)
        one_line = " ".join(text.splitlines())
        shown = one_line if len(one_line) <= 120 else one_line[:117] + "..."
        print(f"Copied to the clipboard: {shown}")
        return
    unit = f"rook-clip-{os.getpid()}-{time.time_ns()}"
    cmd = [SYSTEMD_RUN, "--user", "--collect", "--quiet", "--expand-environment=no",
           "--description", "Rook clipboard", "--unit", unit, "--", WL_COPY, "--foreground", "--", text]
    try:
        started = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as error:
        sys.exit(f"Could not start the clipboard unit: {error}")
    if started.returncode:
        sys.exit((started.stderr or started.stdout).strip() or f"systemd-run failed with exit code {started.returncode}.")
    deadline, last_error = time.monotonic() + CLIP_WAIT, "clipboard stayed empty"
    while True:
        try:
            pasted = subprocess.run([WL_PASTE, "--no-newline", "--type", "text"], stdin=subprocess.DEVNULL,
                                    capture_output=True, timeout=1)
        except (OSError, subprocess.TimeoutExpired) as error:
            sys.exit(f"Could not read the clipboard: {error}")
        out = pasted.stdout.decode("utf-8", errors="replace")
        if pasted.returncode == 0 and out == text:
            one_line = " ".join(text.splitlines())
            shown = one_line if len(one_line) <= 120 else one_line[:117] + "..."
            print(f"Copied to the clipboard: {shown}")
            return
        if pasted.returncode != 0:
            err = (pasted.stderr or pasted.stdout).decode("utf-8", errors="replace").strip()
            if "no suitable type" in err.lower() or "not available as" in err.lower():
                last_error = "the clipboard still held an image"
            else:
                last_error = err or f"wl-paste exited with {pasted.returncode}"
        elif "\ufffd" in out or "\x00" in out:
            last_error = "the clipboard still held an image"
        else:
            got = out if len(out) <= 80 else out[:77] + "..."
            last_error = f"clipboard held {got!r} instead"
        if time.monotonic() >= deadline:
            sys.exit(f"Clipboard did not hold the copied text ({last_error}).")
        time.sleep(0.05)


def check_clip():
    """Self-check relay.py clip against fake scripts in a scratch folder without touching the real clipboard."""
    import contextlib
    import io
    import tempfile
    global SYSTEMD_RUN, WL_COPY, WL_PASTE, CLIP_WAIT
    real = (SYSTEMD_RUN, WL_COPY, WL_PASTE, CLIP_WAIT)
    with tempfile.TemporaryDirectory() as folder:
        base = Path(folder)
        argv_log, clip_file, delay_file, mismatch_file, image_file, png_file = (
            base / "argv.json", base / "clip.txt", base / "delay.txt",
            base / "mismatch.txt", base / "image.txt", base / "png.txt")
        fake_run, fake_copy, fake_paste = base / "systemd-run", base / "wl-copy", base / "wl-paste"
        fake_run.write_text(
            f"#!{sys.executable}\nimport json, pathlib, sys\n"
            f"pathlib.Path({str(argv_log)!r}).write_text(json.dumps(sys.argv[1:]))\n"
            f"val = 'wrong text' if pathlib.Path({str(mismatch_file)!r}).exists() else sys.argv[-1]\n"
            f"pathlib.Path({str(clip_file)!r}).write_text(val)\n"
        )
        fake_paste.write_text(
            f"#!{sys.executable}\nimport pathlib, sys\n"
            "assert sys.argv[1:] == ['--no-newline', '--type', 'text'], sys.argv[1:]\n"
            "def take(path):\n"
            "    if not path.exists():\n"
            "        return False\n"
            "    raw = path.read_text().strip()\n"
            "    if raw == 'always':\n"
            "        return True\n"
            "    n = int(raw)\n"
            "    if n <= 0:\n"
            "        return False\n"
            "    path.write_text(str(n - 1))\n"
            "    return True\n"
            f"if take(pathlib.Path({str(delay_file)!r})):\n"
            "    sys.stderr.write('Nothing is copied\\n'); sys.exit(1)\n"
            f"if take(pathlib.Path({str(image_file)!r})):\n"
            "    sys.stderr.write('Clipboard content is not available as requested type \"text\"\\n'); sys.exit(1)\n"
            f"if take(pathlib.Path({str(png_file)!r})):\n"
            "    sys.stdout.buffer.write(b'\\x89PNG\\r\\n\\x1a\\n\\x00\\x00\\x00\\rIHDR\\x00\\x00\\x00\\x01'); sys.exit(0)\n"
            f"sys.stdout.buffer.write(pathlib.Path({str(clip_file)!r}).read_bytes())\n"
        )
        fake_run.chmod(0o755)
        fake_paste.chmod(0o755)
        SYSTEMD_RUN, WL_COPY, WL_PASTE, CLIP_WAIT = str(fake_run), str(fake_copy), str(fake_paste), 0.25

        def call(args, stdin_text=""):
            buf, real_stdin = io.StringIO(), sys.stdin
            sys.stdin = io.StringIO(stdin_text)
            try:
                with contextlib.redirect_stdout(buf):
                    clip_command(args)
                return 0, buf.getvalue(), ""
            except SystemExit as exc:
                return (1 if exc.code else 0), buf.getvalue(), str(exc.code or "")
            finally:
                sys.stdin = real_stdin

        try:
            # Exact argv, single text argument, apostrophe and $ pass through untouched.
            way = "/wf way Un'Goro Crater 45.2 60.1 Marshal's $HOME `id`"
            code, out, err = call([way])
            assert code == 0 and out.strip() == f"Copied to the clipboard: {way}", (code, out, err)
            got_argv = json.loads(argv_log.read_text())
            assert got_argv[:7] == ["--user", "--collect", "--quiet", "--expand-environment=no",
                                    "--description", "Rook clipboard", "--unit"], got_argv
            assert got_argv[7].startswith("rook-clip-"), got_argv
            assert got_argv[8:] == ["--", str(fake_copy), "--foreground", "--", way], got_argv
            assert len(got_argv) == 13, got_argv

            # Multiple arguments join with spaces, and "-" reads stdin; delayed paste still succeeds.
            delay_file.write_text("2")
            code, out, err = call(["/wf", "way", "45.2", "60.1"])
            assert code == 0 and json.loads(argv_log.read_text())[-1] == "/wf way 45.2 60.1", (code, out, err)
            code, out, err = call(["-"], "Marshal's $100\n")
            assert code == 0 and json.loads(argv_log.read_text())[-1] == "Marshal's $100", (code, out, err)
            # Boundary: exactly CLIP_MAX characters succeeds.
            code, _, err = call(["x" * CLIP_MAX])
            assert code == 0, err

            # Empty text and text over CLIP_MAX are refused without running systemd-run.
            for bad_args, bad_in in (([], ""), ([""], ""), (["   "], ""), (["-"], "  \n"), (["x" * (CLIP_MAX + 1)], "")):
                argv_log.unlink(missing_ok=True)
                code, _, err = call(bad_args, bad_in)
                assert code != 0 and not argv_log.exists(), (bad_args, code, err)

            # Mismatched paste reports failure.
            mismatch_file.write_text("1")
            code, _, err = call(["wanted text"])
            assert code != 0 and "wrong text" in err, (code, err)
            mismatch_file.unlink()

            # Transient image then text succeeds; persistent image reports a clean message.
            way2 = "/wf way Undercity 74.0 32.8 Andrew Brownell"
            image_file.write_text("2")
            code, out, err = call([way2])
            assert code == 0 and out.strip() == f"Copied to the clipboard: {way2}", (code, out, err)
            image_file.write_text("always")
            code, _, err = call([way2])
            assert code != 0 and "the clipboard still held an image" in err, (code, err)
            image_file.unlink()

            # PNG bytes returned under a text type do not crash.
            png_file.write_text("2")
            code, out, err = call([way2])
            assert code == 0 and out.strip() == f"Copied to the clipboard: {way2}", (code, out, err)
            png_file.write_text("always")
            code, _, err = call([way2])
            assert code != 0 and "the clipboard still held an image" in err and "PNG" not in err, (code, err)
            png_file.unlink()
        finally:
            SYSTEMD_RUN, WL_COPY, WL_PASTE, CLIP_WAIT = real
    print("Relay clip: all checks passed.")


FAKE_HERDR = '''
import json, pathlib, sys
base = pathlib.Path(sys.argv[0]).parent
state = json.loads((base / "state.json").read_text())
args = sys.argv[1:]
with open(base / "calls.log", "a") as log:
    log.write(json.dumps(args) + "\\n")
def out(result):
    (base / "state.json").write_text(json.dumps(state))
    print(json.dumps({"id": "fake", "result": result}))
    sys.exit(0)
def err(code, message):
    print(json.dumps({"error": {"code": code, "message": message}, "id": "fake"}), file=sys.stderr)
    sys.exit(1)
label = None
if args[:1] == ["--machine"]:
    label, args = args[1], args[2:]
if args == ["machine", "list", "--json"]:
    print(json.dumps(state.get("saved", [])))
    sys.exit(0)
agents = state["machines"].get(label or "local")
if agents is None:
    err("server_not_running", "no herdr server is running")
verb = args[:2]
if verb == ["agent", "list"]:
    out({"agents": list(agents.values()), "type": "agent_list"})
if verb in (["agent", "get"], ["agent", "prompt"]) and args[2] not in agents:
    err("agent_not_found", "agent target " + args[2] + " not found")
if verb == ["agent", "get"]:
    out({"agent": agents[args[2]], "type": "agent_info"})
if verb == ["agent", "read"]:
    print(state.get("screen", ""))
    sys.exit(0)
if verb == ["agent", "prompt"]:
    if state.get("prompt", "ok") != "ok":
        err(state["prompt"], "the connection dropped")
    agents[args[2]].update(agent_status="working", state_change_seq=agents[args[2]]["state_change_seq"] + 1)
    out({"type": "agent_prompted"})
if verb == ["workspace", "list"]:
    out({"workspaces": state.get("workspaces", [])})
if verb == ["pane", "list"]:
    out({"panes": state.get("panes", [])})
if verb == ["workspace", "create"]:
    out({"root_pane": {"pane_id": "w9:p1", "cwd": args[args.index("--cwd") + 1]}})
if verb == ["pane", "split"]:
    out({"pane": {"pane_id": "w1:p9", "cwd": args[args.index("--cwd") + 1]}})
if verb == ["agent", "start"]:
    agents[args[2]] = {"name": args[2], "agent": args[args.index("--kind") + 1], "agent_status": "idle",
                       "state_change_seq": 1, "pane_id": args[args.index("--pane") + 1], "cwd": "/tmp/proj"}
    out({"agent": agents[args[2]], "type": "agent_started"})
err("unknown", "the fake herdr does not know " + " ".join(args))
'''


def check_herdr():
    """Self-check relay.py herdr and pi, and the watcher's Herdr kind, against a fake herdr and a Pi fixture."""
    import asyncio
    import tempfile
    import herdr
    with tempfile.TemporaryDirectory() as folder:
        base = Path(folder)
        here = watch.local_machine()  # The watcher names this machine by the host name, as on any computer.
        state_file, calls = base / "bin/state.json", base / "bin/calls.log"
        (base / "bin").mkdir()
        (base / "bin/herdr").write_text(f"#!{sys.executable}\n{FAKE_HERDR}")
        (base / "bin/herdr").chmod(0o755)
        sessions = base / "pi/--tmp-proj--"
        sessions.mkdir(parents=True)
        (sessions / "2026-11-25T10-00-00-000Z_0199aaaa-0000.jsonl").write_text("\n".join(json.dumps(line) for line in (
            {"type": "session", "version": 3, "id": "0199aaaa-0000", "timestamp": "2026-11-25T10:00:00Z",
             "cwd": "/tmp/proj"},
            {"type": "session_info", "id": "a1", "name": "Fixture work"},
            {"type": "message", "id": "m1", "message": {"role": "user", "content": "Fix the halo."}},
            {"type": "message", "id": "m2", "message": {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "secret thoughts"}, {"type": "toolCall", "name": "bash"},
                {"type": "text", "text": "The halo is fixed."}]}},
            {"type": "message", "id": "m3", "message": {"role": "toolResult", "content": [{"type": "text",
                                                                                          "text": "tool noise"}]}},
        )) + "\nnot json\n")
        env = {**{k: v for k, v in os.environ.items() if k not in ("T3CODE_THREAD_ID", "HERDR_SOCKET_PATH")},
               "PATH": f"{base / 'bin'}:{os.environ.get('PATH', '')}", "XDG_STATE_HOME": str(base / "state"),
               "XDG_RUNTIME_DIR": str(base / "run"), "PI_CODING_AGENT_SESSION_DIR": str(base / "pi")}
        (base / "run").mkdir(mode=0o700)  # No Rook answers here, so a watch goes to the list file.

        def fake(**changes):
            data = json.loads(state_file.read_text()) if state_file.exists() else {}
            data.update(changes)
            state_file.write_text(json.dumps(data))

        def agent(name, status, seq=1, kind="pi", cwd="/tmp/proj"):
            return {"name": name, "agent": kind, "agent_status": status, "state_change_seq": seq, "pane_id": "w1:p1",
                    "cwd": cwd}

        def run(*args):
            done = subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True, env=env)
            return done.returncode, done.stdout + done.stderr

        def prompts(name):
            lines = calls.read_text().splitlines() if calls.exists() else []
            return sum(1 for line in lines if json.loads(line)[:3] == ["agent", "prompt", name])

        sends = base / "state/rook/herdr-sends.json"
        # The listing: this machine and an enabled saved machine, never a disabled one.
        fake(machines={"local": {"fake1": agent("fake1", "idle"), "fake2": agent("fake2", "working")},
                       "nimbus": {"far": agent("far", "blocked", kind="claude")}},
             saved=[{"id": "m1", "label": "nimbus", "enabled": True}, {"id": "m2", "label": "off", "enabled": False}])
        code, out = run("herdr", "agents")
        assert code == 0 and "fake1 | pi | idle | /tmp/proj | this machine" in out, out
        assert "far | claude | blocked | /tmp/proj | nimbus" in out and "off" not in out, out
        fake(machines={"local": None}, saved=[])
        assert run("herdr", "agents") == (0, "Herdr is not running on this machine.\n")
        # The guard: a working or blocked agent gets nothing, and no intent is recorded.
        fake(machines={"local": {"fake1": agent("fake1", "blocked"), "fake2": agent("fake2", "working")}})
        for name, words in (("fake2", "is working"), ("fake1", "answers it in Herdr")):
            code, out = run("herdr", "send", name, "Carry on.")
            assert code == 1 and words in out and prompts(name) == 0, out
        assert not sends.exists()
        # A ready agent gets one prompt, recorded before and after, and is watched.
        fake(machines={"local": {"fake1": agent("fake1", "idle"), "fake3": agent("fake3", "done", 4)}})
        code, out = run("herdr", "send", "fake1", "Carry on.")
        assert code == 0 and "Sent to fake1." in out and prompts("fake1") == 1, out
        assert [(r["agent"], r["seq"], r["outcome"]) for r in herdr.records(sends)] == [("fake1", 1, "sent")]
        assert "Carry on." not in sends.read_text()  # Only a hash and a short description.
        assert (here, "herdr:fake1") in watch.load(base / "state/rook/watching.json")
        # An outcome Herdr cannot give is unknown: said, recorded, never retried and never replayed.
        fake(prompt="connection_lost")
        code, out = run("herdr", "send", "fake3", "Try this.")
        assert code == 1 and "outcome is unknown" in out and "will not resend" in out and prompts("fake3") == 1, out
        assert herdr.records(sends)[-1]["outcome"] == "unknown"
        run("herdr", "agents")
        assert prompts("fake3") == 1 and herdr.records(sends)[-1]["outcome"] == "unknown"
        # Herdr's own refusal proves nothing was sent.
        fake(prompt="agent_blocked")
        code, out = run("herdr", "send", "fake3", "Try this.")
        assert code == 1 and "Nothing was sent" in out and herdr.records(sends)[-1]["outcome"] == "failed", out
        fake(prompt="ok", screen="line one\n\n\n\nline two   \n\n")
        code, out = run("herdr", "read", "fake3", "--lines", "5")
        assert code == 0 and out == "fake3 (pi) is done in /tmp/proj.\nline one\n\nline two\n", repr(out)
        # A start opens a new workspace for a new folder, never takes focus, and sends through the guard.
        code, out = run("herdr", "start", "/tmp/new-proj", "--kind", "pi", "--model", "m-1", "Begin.")
        assert code == 0 and "Started pi-new-proj (pi)" in out and "Sent to pi-new-proj." in out, out
        assert "Rook is not running, so its result waits in Herdr." in out, out  # No Rook runs in this check.
        made = [json.loads(line) for line in calls.read_text().splitlines()]
        assert ["agent", "start", "pi-new-proj", "--kind", "pi", "--pane", "w9:p1", "--", "--model", "m-1"] in made, made
        assert ["workspace", "create", "--cwd", "/tmp/new-proj", "--label", "new-proj", "--no-focus"] in made, made
        assert not any("focus" in word and word != "--no-focus" for line in made for word in line), made
        assert prompts("pi-new-proj") == 1
        assert not any(line[:2] == ["pane", "split"] for line in made), made  # Never a pane the owner looks at.
        # A started agent is watched even when its first prompt does not go.
        fake(prompt="agent_blocked")
        code, out = run("herdr", "start", "/tmp/proj", "--kind", "codex", "Begin.")
        assert code == 1 and "Started codex-proj (codex)" in out and "Nothing was sent" in out, out
        assert (here, "herdr:codex-proj") in watch.load(base / "state/rook/watching.json")
        fake(prompt="ok")

        # The watcher: one cheap get per poll, news once for blocked and once for done.
        said, real_path = [], os.environ.get("PATH", "")
        os.environ["PATH"] = env["PATH"]
        try:
            watcher = watch.Watcher(base / "state/rook/watching.json",
                                    lambda text, delivered, source: said.append((text, delivered, source)),
                                    lambda *args, **kwargs: None)

            def poll(**agents):
                fake(machines={"local": agents})
                asyncio.run(watcher.poll())
                return said.pop() if said else None

            key = (here, "herdr:fake1")
            assert poll(fake1=agent("fake1", "working", 2)) is None
            assert watcher.entries[key]["since"] == 1  # From the intent record of the send.
            text, delivered, source = poll(fake1=agent("fake1", "done", 3))
            assert "fake1" in text and "finished its turn" in text and "line two" in text, text
            assert source["thread"] == "herdr:fake1" and poll(fake1=agent("fake1", "idle", 4)) is None  # Seen: same finish.
            delivered()
            assert key not in watcher.entries
            watcher.add("herdr:fake2", here, "fake2")
            assert poll(fake2=agent("fake2", "working", 7)) is None and watcher.entries[(here, "herdr:fake2")]["since"] == 7
            text, delivered, _ = poll(fake2=agent("fake2", "blocked", 8))
            assert text.startswith(settings.render(watch.ANSWER)) and " it in Herdr" in text and "Never send it keys" in text, text
            delivered()
            assert poll(fake2=agent("fake2", "blocked", 8)) is None and (here, "herdr:fake2") in watcher.entries
            text, delivered, _ = poll(fake2=agent("fake2", "done", 10))
            assert "finished its turn" in text
            delivered()
            watcher.add("herdr:gone", here, "gone")
            assert poll() is None and (here, "herdr:gone") not in watcher.entries  # The agent exited.
            # A watch ends when the Herdr server restarted, or when the send never took after KEEP_SECONDS.
            watcher.add("herdr:fake5", here, "fake5")
            assert poll(fake5=agent("fake5", "working", 9)) is None and poll(fake5=agent("fake5", "idle", 2)) is None
            assert (here, "herdr:fake5") not in watcher.entries
            watcher.add("herdr:fake4", here, "fake4")
            assert poll(fake4=agent("fake4", "idle", 5)) is None and (here, "herdr:fake4") in watcher.entries
            watcher.entries[(here, "herdr:fake4")]["watched_at"] -= watch.KEEP_SECONDS + 1
            assert poll(fake4=agent("fake4", "idle", 5)) is None and (here, "herdr:fake4") not in watcher.entries
            assert "herdr:" not in (base / "state/rook/work.json").read_text("utf-8") if (
                base / "state/rook/work.json").exists() else True  # The work list names T3 threads only.
            assert len([line for line in calls.read_text().splitlines() if "prompt" in line]) == 5  # The watcher sent none.
            # A prompt that went out but whose outcome could not be written stays "sending", and is never resent.
            fake(machines={"local": {"fake9": agent("fake9", "idle", 3)}})
            real_write, writes = herdr.write_records, []

            def failing_write(rows, path=None):
                writes.append(1)
                if len(writes) == 2:
                    raise OSError("disk full")
                real_write(rows, path)
            herdr.write_records = failing_write
            try:
                outcome, words = herdr.send(None, "fake9", "Go.", sends)
            finally:
                herdr.write_records = real_write
            assert outcome == "sent" and "could not record" in words and herdr.records(sends)[-1]["outcome"] == "sending"
            # The watcher's start marks it unknown before it tells it, tells it once, and watches the agent.
            rows = herdr.records(sends)
            rows[-1]["at"] -= 2 * herdr.SECONDS + 1
            herdr.write_records(rows, sends)
            watcher.stale_sends()
            text, _, source = said.pop()
            assert "fake9" in text and "may or may not have arrived" in text and source["thread"] == "herdr:fake9", text
            assert (herdr.records(sends)[-1]["outcome"], herdr.records(sends)[-1]["result"]) == (
                "unknown", "Rook stopped mid-send")
            assert (here, "herdr:fake9") in watcher.entries and prompts("fake9") == 1
            watcher.stale_sends()
            assert not said
        finally:
            os.environ["PATH"] = real_path

        # Pi, read only: the newest sessions, and the text of the last messages without thinking or tool output.
        assert herdr.pi_session(sessions / "2026-11-25T10-00-00-000Z_0199aaaa-0000.jsonl")[:3] == (
            "0199aaaa-0000", "Fixture work", "/tmp/proj")
        code, out = run("pi", "sessions")
        assert code == 0 and out.startswith("0199aaaa | Fixture work | /tmp/proj | "), out
        code, out = run("pi", "read", "0199", "--messages", "2")
        assert code == 0 and out == ("Pi session 0199aaaa, Fixture work, in /tmp/proj.\nUser: Fix the halo.\n"
                                     "Pi: The halo is fixed.\n"), repr(out)
        assert run("pi", "read", "zzz")[0] == 1
        # pi t3-login in one step: a short-lived t3 entry at T3's address carries the sign-in. The person's own stays.
        (base / "bin/pi").write_text(f"#!/bin/sh\necho \"$*\" >> {base}/pi-calls.log\n")
        (base / "bin/pi").chmod(0o755)
        (base / "home/.t3/userdata").mkdir(parents=True)
        env.update(HOME=str(base / "home"), PI_CODING_AGENT_DIR=str(base / "pi-agent"))
        assert run("pi", "t3-login")[0] == 1 and not (base / "pi-calls.log").exists()  # T3 wrote no address.
        (base / "home/.t3/userdata/server-runtime.json").write_text('{"host": "127.0.0.1", "port": 4321}')
        code, out = run("pi", "t3-login")
        assert code == 0 and "Restart Rook" in out, out
        assert (base / "pi-calls.log").read_text().splitlines() == [
            "mcp add t3 --url http://127.0.0.1:4321/mcp", "mcp login t3", "mcp remove t3"]
        (base / "pi-agent").mkdir()
        (base / "pi-agent/mcp.json").write_text('{"mcpServers": {"t3": {"url": "http://elsewhere/mcp"}}}')
        (base / "pi-calls.log").unlink()
        assert run("pi", "t3-login")[0] == 0 and (base / "pi-calls.log").read_text().splitlines() == ["mcp login t3"]
        # herdr install runs Herdr's installer through a stand-in, never the real one, into a scratch folder.
        real_path, real_dir = os.environ.get("PATH", ""), os.environ.get("HERDR_INSTALL_DIR")
        (base / "tools").mkdir()  # Only what the stand-in needs: this machine's own herdr must stay out of sight.
        for tool in ("sh", "mkdir", "chmod"):
            (base / "tools" / tool).symlink_to(shutil.which(tool))
        os.environ.update(PATH=f"{base / 'inst'}:{base / 'tools'}", HERDR_INSTALL_DIR=str(base / "inst"))
        try:
            fake_installer = ('mkdir -p "$HERDR_INSTALL_DIR" && printf "#!/bin/sh\\necho herdr 9.9.9\\n" > '
                              '"$HERDR_INSTALL_DIR/herdr" && chmod +x "$HERDR_INSTALL_DIR/herdr"').encode()
            assert "Dry run: nothing changed" in herdr.install(dry=True) and not (base / "inst").exists()
            assert herdr.install(fetch=lambda: fake_installer) == f"Installed herdr 9.9.9 at {base / 'inst/herdr'}."
            assert herdr.install(fetch=lambda: b"exit 9") == f"Herdr is already installed at {base / 'inst/herdr'}."
            (base / "inst/herdr").unlink()
            for script, words in ((b"printf '  \\033[31m\\342\\234\\227\\033[0m no route\\n' >&2; exit 1", "stopped: no route"),
                                  (b"exit 0", "does not run")):
                try:
                    herdr.install(fetch=lambda: script)
                    raise AssertionError(words)
                except herdr.Failed as error:
                    assert words in str(error) and "\x1b" not in str(error), error
        finally:
            os.environ["PATH"] = real_path
            os.environ.pop("HERDR_INSTALL_DIR") if real_dir is None else os.environ.update(HERDR_INSTALL_DIR=real_dir)
    print("Relay herdr and pi: all checks passed.")


def write_note(text):
    """Leave the restart note atomically, private to the owner. A fresh note that no start has read yet is kept, and this
    one is added after it."""
    try:
        if time.time() - RESTART_NOTE.stat().st_mtime <= 600 and (unread := RESTART_NOTE.read_text().strip()):
            text = f"{unread}\n\n{text}"
    except OSError:
        pass
    temp = RESTART_NOTE.with_suffix(".tmp")
    try:
        desk.ensure_dir(RESTART_NOTE.parent)
        with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w") as note:
            os.fchmod(note.fileno(), 0o600)
            note.write(text)
        temp.replace(RESTART_NOTE)
    except OSError as error:
        sys.exit(f"Could not write the restart note at {RESTART_NOTE}: {error}")


# rook-daily.service: the units it checks, how often it tries again, and when it gives up until tomorrow.
SYSTEMCTL = os.environ.get("SYSTEMCTL", "systemctl")  # Tests point this at a stand-in.
DAILY_RETRY_SECONDS = 300
DAILY_GIVE_UP_SECONDS = 2 * 3600
# Legacy fallback wait for an older Rook that does not support the restart grant verb.
QUIET_WAIT_SECONDS = 60
# Default limit, poll interval, and progress-report interval for grant-based restart and overlay reload.
RESTART_WAIT_SECONDS = 9 * 60
RESTART_POLL_SECONDS = 0.5
RESTART_REPORT_SECONDS = 60


class StopSignal(BaseException):
    """Raised on SIGTERM or SIGINT so restart callers always cancel their wait or grant."""

    def __init__(self, signum):
        self.signum = signum


def install_stop_signals():
    """Install SIGINT and SIGTERM handlers that raise StopSignal, returning the prior handlers."""
    def handle(signum, _frame):
        raise StopSignal(signum)

    return {sig: signal.signal(sig, handle) for sig in (signal.SIGINT, signal.SIGTERM)}


def restore_stop_signals(previous):
    for sig, handler in previous.items():
        signal.signal(sig, handler)
DAILY_NOTE = ("The daily restart after the nightly dream. Your code did not change. Your memory notes may be new, "
              "so read the ones that relate before you answer from memory.")


def unit_state(unit):
    """A user unit's ActiveState, such as active, activating, or inactive."""
    if desk.IS_MAC:
        return desk.service_state(unit)
    return subprocess.run([SYSTEMCTL, "--user", "show", "-p", "ActiveState", "--value", unit],
                          capture_output=True, text=True).stdout.strip()


def unknown_restart_verb(answer):
    """Whether an older Rook answered that it does not know the restart verb."""
    return bool(answer and not answer.get("ok") and "Unknown request" in str(answer.get("error") or ""))


BLOCKER_PHRASES = {
    "recording": "a recording", "turn": "a turn", "warm-up": "the agent warm-up",
    "scene": "a scene", "overlay reload": "an overlay reload", "restart": "another restart",
    "activity": "active work",
}


def still_line(items):
    """The sentence a restart or overlay reload that gave up ends with: what still blocked it."""
    return "Rook did not answer in time." if items == [SILENT] else f"Rook was still blocked by {blocker_text(items)}."


def blocker_text(items):
    """Join blocker names with articles so every status and wait line reads as plain English."""
    return " and ".join(BLOCKER_PHRASES.get(name, name) for name in items)


SILENT = "no answer"  # The blocker when Rook did not answer the restart ask in time.


def wait_line(items, label="restart"):
    """One plain sentence naming what blocks a waiting restart or overlay reload."""
    if items == [SILENT]:
        return f"Rook did not answer within 5 seconds, so the {label} asks again."
    joined = blocker_text(items)
    if any("permission card" in item for item in items):
        return f"Waiting because Rook has {joined}."
    return f"Waiting for {joined} to end."


def asked_phrase(who):
    """Describe who asked for a restart in plain English."""
    if who == "terminal":
        return "asked from a terminal"
    if who == "daily-restart":
        return "asked by the daily restart"
    if who and who.startswith("build thread "):
        return f"asked by build thread {who[len('build thread '):].capitalize()}"
    return f"asked by {who or 'an unknown caller'}"


def restart_caller():
    """Name who asks for a restart: the owner in a terminal, a build thread, or another T3 thread."""
    if os.environ.get("ROOK_AGENT"):
        return "rook"
    thread = os.environ.get("T3CODE_THREAD_ID", "").strip()
    if not thread:
        return "terminal"
    for name, tid in active_build_threads().items():
        if thread == tid:
            return f"build thread {name}"
    return f"thread {thread}"


def parse_wait_args(argv, usage, default_reason):
    """Parse --timeout DURATION and --reason TEXT for restart and reload overlay."""
    timeout, reason, at = RESTART_WAIT_SECONDS, default_reason, 0
    while at < len(argv):
        arg = argv[at]
        if arg == "--timeout":
            if at + 1 >= len(argv):
                sys.exit("Give a duration after --timeout, such as 10m or 30s.")
            parts = DURATION.fullmatch(argv[at + 1].lower())
            seconds = sum(int(n or 0) * unit for n, unit in zip(parts.groups(), (3600, 60, 1))) if parts else 0
            if not 0 < seconds <= TIMER_SECONDS:
                sys.exit(f"{argv[at + 1]!r} is not a timeout duration. Use 30s, 10m, or 1h, up to 24h.")
            timeout, at = seconds, at + 2
        elif arg == "--reason":
            if at + 1 >= len(argv) or not argv[at + 1].strip():
                sys.exit("Give a short reason after --reason.")
            reason, at = " ".join(argv[at + 1].split())[:120], at + 2
        else:
            sys.exit(usage)
    return timeout, reason


def daily_restart():
    """Restart the running Rook once, when the dream job is done and Rook is idle. A stopped Rook stays stopped."""
    give_up = time.time() + DAILY_GIVE_UP_SECONDS
    if not memory.is_shared():
        ok, message = memory.run_dream()
        if message:
            print(message, file=sys.stdout if ok else sys.stderr, flush=True)
    token = f"daily-{os.getpid()}-{time.time_ns()}"
    granted_token = None
    prior_signals = install_stop_signals()
    try:
        while True:
            if unit_state("rook.service") != "active":
                print("Rook is not running, so the daily restart leaves it alone.")
                return
            dreaming = unit_state("agent-dream.service") in ("active", "activating", "reloading")
            if dreaming:
                answer = None
            else:
                answer = ask_rook("restart ask", json.dumps({
                    "id": token, "who": "daily-restart", "reason": "the daily restart", "kind": "daily",
                }), wait=30)
                if unknown_restart_verb(answer):
                    legacy = ask_rook("idle", wait=30)
                    if legacy and legacy.get("idle"):
                        break
                elif answer and answer.get("granted"):
                    granted_token = token
                    break
            if time.time() + DAILY_RETRY_SECONDS > give_up:
                sys.exit("Rook stayed busy, or the dream kept running, for two hours. No restart until tomorrow.")
            print("The dream is still running." if dreaming else "Rook is busy.",
                  f"Trying again in {span(DAILY_RETRY_SECONDS)}.", flush=True)
            time.sleep(DAILY_RETRY_SECONDS)
        write_note(DAILY_NOTE)
        # try-restart restarts Rook only while it runs, so a Rook stopped meanwhile stays stopped.
        if desk.IS_MAC:
            rc, detail = desk.service_restart(try_only=True)
            mgr = "launchctl"
        else:
            done = subprocess.run([SYSTEMCTL, "--user", "try-restart", "rook.service"], capture_output=True, text=True)
            rc, detail, mgr = done.returncode, (done.stderr or done.stdout or "").strip(), "systemctl"
        if rc:
            if granted_token:
                ask_rook("restart cancel", json.dumps({"id": granted_token}), wait=5)
            sys.exit(f"{mgr} could not restart Rook: {detail}" if detail else f"{mgr} could not restart Rook.")
        print("Restarted Rook for the day.")
    except StopSignal as stop:
        restore_stop_signals(prior_signals)
        if granted_token:
            ask_rook("restart cancel", json.dumps({"id": granted_token}), wait=2)
        name = "SIGTERM" if stop.signum == signal.SIGTERM else "SIGINT"
        sys.exit(f"This command stopped on {name} and cancelled the daily restart.")
    finally:
        restore_stop_signals(prior_signals)


def wait_until_quiet():
    """Legacy fallback for an older Rook without the restart verb: wait up to QUIET_WAIT_SECONDS."""
    started, seen = time.monotonic(), []
    while True:
        answer = ask_rook("idle", wait=5)
        if answer is None:
            return "Rook is not running, so restart starts it right away."
        if not isinstance(answer.get("busy"), list):  # No answer in time, or a Rook from before restart.
            return ("Rook did not answer within 5 seconds, so restart goes ahead." if answer.get("timeout")
                    else "Rook did not report its state, so restart goes ahead.")
        waited = round(time.monotonic() - started)
        if not answer["busy"]:
            return f"Waited {waited} s for {blocker_text(seen)} to end." if seen else "Rook was idle."
        seen += [name for name in answer["busy"] if name not in seen]
        if waited >= QUIET_WAIT_SECONDS:
            return f"Rook stayed busy after {waited} s ({blocker_text(answer['busy'])}), so restart goes ahead."
        time.sleep(0.5)


def wait_for_grant(kind, reason, timeout, *, require_running=False, active=None):
    """Ask Rook for a quiet-moment reservation and wait until granted, cancelled, restarted, or timed out."""
    token = f"{kind}-{os.getpid()}-{time.time_ns()}"
    if active is not None:
        active[0] = token
    payload = json.dumps({"id": token, "who": restart_caller(), "reason": reason, "kind": kind})
    started, seen, last_report, saw_rook = time.monotonic(), [], None, False
    action = "reloading the overlay" if kind == "reload" else "restarting"
    label = "overlay reload" if kind == "reload" else "restart"
    while True:
        answer = ask_rook("restart ask", payload, wait=5)
        if answer is None:
            if active is not None:
                active[0] = None
            if saw_rook:
                if kind == "reload":
                    return "restarted", "Rook restarted while this caller waited, so the new Rook starts a fresh overlay."
                return "restarted", "Rook restarted while this caller waited, so it already runs the new code."
            if require_running:
                sys.exit(f"Rook is not running: nothing answers at {INBOX}.")
            return None, "Rook is not running, so restart starts it right away."
        saw_rook = True
        if unknown_restart_verb(answer):
            if active is not None:
                active[0] = None
            return None, wait_until_quiet()
        if answer.get("cancelled"):
            if active is not None:
                active[0] = None
            sys.exit(f"relay.py restart --cancel withdrew the waiting {label}.")
        if answer.get("ok") and answer.get("granted"):
            waited = round(time.monotonic() - started)
            return token, (f"Waited {waited} s for {blocker_text(seen)} to end." if seen else "Rook was idle.")
        if answer.get("ok"):
            busy = answer.get("busy") or ["active work"]
        elif answer.get("timeout"):
            busy = [SILENT]
        else:
            if active is not None:
                active[0] = None
            sys.exit(answer.get("error") or f"Rook refused the {label} request.")
        seen += [name for name in busy if name not in seen]
        now = time.monotonic()
        if now - started >= timeout:
            ask_rook("restart cancel", json.dumps({"id": token}), wait=5)
            if active is not None:
                active[0] = None
            elapsed = span(timeout) if timeout >= 60 else f"{round(timeout)} seconds"
            sys.exit(f"Gave up after {elapsed} without {action}. {still_line(busy)}")
        if last_report is None or now - last_report >= RESTART_REPORT_SECONDS:
            print(wait_line(busy, label), flush=True)
            last_report = now
        remaining = started + timeout - time.monotonic()
        if remaining > 0:
            time.sleep(min(RESTART_POLL_SECONDS, remaining))


# The Mac permission walkthrough, in order, with each grant's System Settings pane.
MAC_GRANTS = {"microphone": "Privacy_Microphone", "input": "Privacy_ListenEvent", "screen": "Privacy_ScreenCapture",
              "accessibility": "Privacy_Accessibility", "automation": "Privacy_Automation"}


MAC_WAIT_SECONDS = 100  # One wait fits inside a two-minute tool call.


def mac_access_command(argv):
    """Handle relay.py mac-access: check, ask for, or open each Mac permission. After a grant that needs a fresh
    process, restart saves the step in Rook's state folder and restarts Rook through launchd after this turn."""
    if not desk.IS_MAC:
        sys.exit("relay.py mac-access works only on a Mac.")
    saved = desk.state_dir() / "rook/mac-permissions.json"
    verb, grant = (list(argv) + [None, None])[:2]
    if verb not in (None, "ask", "open", "wait", "restart", "kick", "done") or (
            verb in ("ask", "open", "wait", "restart", "kick") and (len(argv) != 2 or grant not in MAC_GRANTS)):
        sys.exit(f"Usage: relay.py mac-access [ask|open|wait|restart {'|'.join(MAC_GRANTS)}] | done")
    if verb == "open":
        try:
            done = subprocess.run(["/usr/bin/open", f"x-apple.systempreferences:com.apple.preference.security?"
                                   f"{MAC_GRANTS[grant]}"], capture_output=True, text=True)
        except OSError as error:
            sys.exit(f"Could not open System Settings: {error}")
        if done.returncode:
            sys.exit(f"Could not open System Settings: {(done.stderr or done.stdout).strip()}")
        print(f"System Settings shows the {grant} list.")
        return
    if verb == "restart":
        desk.ensure_dir(saved.parent)
        saved.write_text(json.dumps({"step": grant, "at": round(time.time())}))
        write_note(f"Onboarding restarted Rook for the {grant} permission. Run relay.py mac-access to check it took, "
                   "then go on with onboarding from that step.")
        subprocess.Popen([sys.executable, str(SCRIPT), "mac-access", "kick", grant], start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("Rook restarts through launchd once this turn ends, and onboarding goes on from this step.")
        return
    if verb == "kick":  # Detached by restart: wait for a quiet moment, then let launchd restart Rook.
        wait_for_grant("restart", f"the Mac {grant} permission", 120)
        rc, detail = desk.service_restart()
        if rc:
            sys.exit(f"launchctl could not restart Rook: {detail}")
        return
    if verb == "done":
        saved.unlink(missing_ok=True)
        print("Onboarding has no saved Mac step now.")
        return
    if verb == "ask" and grant == "automation":
        print("macOS asks about each app the first time Rook controls it. Nothing to ask now.")
        return
    helper = os.environ.get("ROOK_MAC_HELPER") or str(Path.home() / "Applications/Rook.app/Contents/MacOS/RookHelper")

    def access(ask=None):
        try:
            done = subprocess.run([helper, "--request-access", ask] if ask else [helper, "--check-access"],
                                  capture_output=True, text=True, timeout=150)
            return json.loads(done.stdout.strip().splitlines()[-1])
        except (OSError, subprocess.TimeoutExpired, ValueError, IndexError) as error:
            sys.exit(f"Rook.app could not check the permissions: {error}")
    if verb == "wait":  # The person switches the grant on and says nothing: each check is a fresh helper process.
        end = time.monotonic() + MAC_WAIT_SECONDS
        while time.monotonic() < end:
            if access().get(grant) is True:
                print(f"{grant}: allowed.")
                return mac_access_command(["restart", grant]) if grant in ("input", "screen") else None
            time.sleep(2)
        print(f"{grant}: still not allowed after {MAC_WAIT_SECONDS} seconds. Ask whether they found the switch, "
              f"then run relay.py mac-access wait {grant} again.")
        return
    state = access(grant if verb == "ask" else None)
    for name in ("microphone", "input", "screen", "accessibility"):
        value = state.get(name)
        print(f"{name}: {value if isinstance(value, str) else 'allowed' if value else 'not allowed'}")
    try:
        print(f"Saved onboarding step: {json.loads(saved.read_text())['step']}")
    except (OSError, ValueError, KeyError):
        pass


def update_command(argv):
    """relay.py update [TAG|COMMIT]: fetch Rook's source, move this install's checkout to the new commit, run
    install/install.sh again when the requirements changed, and restart Rook through the idle restart grant.
    It updates only a checkout that install/install.sh made, with no local changes."""
    if len(argv) > 1 or argv[:1] and argv[0].startswith("-"):
        sys.exit("Usage: relay.py update [TAG|COMMIT]")
    if os.environ.get("ROOK_AGENT"):
        sys.exit("Rook never updates or restarts itself. Run relay.py update in a terminal.")
    try:
        entries = json.loads((desk.data_dir() / "rook/install-manifest.json").read_text()).get("entries") or []
    except (OSError, ValueError, AttributeError):
        entries = []
    if not any(isinstance(e, dict) and e.get("created") is True and isinstance(e.get("path"), str)
               and os.path.realpath(e["path"]) == str(ROOT) for e in entries):
        sys.exit(f"{ROOT} was not made by install/install.sh, so relay.py update leaves it alone. Update it with git.")

    def git(*args):
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                              env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})

    if git("status", "--porcelain", "--untracked-files=no").stdout.strip():
        sys.exit(f"{ROOT} has local changes, so Rook did not update it.")
    # get.sh installs a .tar.gz through a temporary folder that it deletes, so that origin points at nothing.
    source = git("remote", "get-url", "origin").stdout.strip().removeprefix("file://")
    if source.startswith("/") and not Path(source).exists():
        sys.exit(f"Rook was installed from a .tar.gz file or a folder that is gone ({source}), so it has no source to "
                 f"update from. Point it at Rook's git repository with: git -C {ROOT} remote set-url origin <git URL>. "
                 "Then run relay.py update again.")
    fetched = git("fetch", "-q", "origin", *argv)
    if fetched.returncode:
        sys.exit(f"Rook could not fetch its source. Check the network and try again. ({fetched.stderr.strip()})")
    old, new = git("rev-parse", "HEAD").stdout.strip(), git("rev-parse", "FETCH_HEAD^{commit}").stdout.strip()
    if not new:
        sys.exit("Rook could not find the commit it fetched.")
    if new == old:
        print(f"Rook is already at {new[:7]}.")
        return
    changed = git("diff", "--name-only", old, new, "--", "install/requirements-rook.txt",
                  "install/requirements-voice.txt", "install/requirements-rook-macos.txt",
                  "install/requirements-voice-macos.txt").stdout.split()
    # On a Mac, new helper sources need a new Rook.app. The installer's own build step rebuilds and signs it with the
    # same identity, so the permission grants survive. It leaves a Rook.app it did not make as it is. An install made
    # with --service no has neither Rook.app nor its launchd agent in the manifest, and the update keeps that choice.
    service = any(isinstance(e, dict) and e.get("role") in ("mac_app", "launchd_plist") for e in entries)
    helper = desk.IS_MAC and service and git("diff", "--name-only", old, new, "--", "macos/RookHelper").stdout.split()
    moved = git("checkout", "-q", "--detach", new)
    if moved.returncode:
        sys.exit(f"Rook could not move its checkout to {new[:7]}. ({moved.stderr.strip()})")
    print(f"Moved Rook from {old[:7]} to {new[:7]}.", flush=True)
    if changed or helper:
        what = "The requirements and the Mac helper" if changed and helper else \
            "The requirements" if changed else "The Mac helper"
        print(f"{what} changed, so the installer runs again." + (" It rebuilds Rook.app." if helper else ""),
              flush=True)
        # No model downloads, and no unit changes beyond Rook.app: an update only brings Rook's own parts up to date.
        done = subprocess.run(["bash", str(ROOT / "install/install.sh"), "--prefix", str(ROOT), "--voice-model", "no",
                               "--recogniser", "no", "--service", "yes" if helper else "no"], stdin=subprocess.DEVNULL)
        if done.returncode:
            git("checkout", "-q", "--detach", old)
            sys.exit(f"The installer failed, so Rook moved back to {old[:7]}. Fix the problem above and run this again.")
    restart_command(["--reason", f"an update to {new[:7]}"])


def restart_command(argv):
    """Handle relay.py restart, restart --status, and restart --cancel."""
    if argv == ["--status"]:
        answer = ask_rook("restart status", wait=5)
        if answer is None:
            utter("Rook is not running.")
            return
        if unknown_restart_verb(answer):
            utter("This running Rook does not report restart status yet.")
            return
        if not answer.get("ok"):
            leave(answer.get("error") or "Rook could not report restart status.")
        state = answer.get("state")
        if state == "none":
            utter("No restart is waiting.")
            return
        subject = "An overlay reload" if answer.get("kind") == "reload" else "A restart"
        since = time_of_day(answer["since"]) if answer.get("since") else "unknown time"
        who = answer.get("who") or "an unknown caller"
        reason = answer.get("reason") or ("an overlay reload" if answer.get("kind") == "reload" else "a deploy")
        if state == "granted":
            utter(f"{subject} is granted since {since}, {asked_phrase(who)} for {reason}.")
            return
        busy = answer.get("busy") or []
        blocker = f"Blocked by {blocker_text(busy)}." if busy else "Ready to go."
        utter(f"{subject} waits since {since}, {asked_phrase(who)} for {reason}. {blocker}")
        return
    if os.environ.get("ROOK_AGENT"):
        leave(f"Rook never restarts, reloads, or cancels restarts for itself. Only {OWNER} or the build thread runs this command.")
    if argv == ["--cancel"]:
        answer = ask_rook("restart cancel", wait=5)
        if answer is None:
            leave(f"Rook is not running: nothing answers at {INBOX}.")
        if unknown_restart_verb(answer):
            leave("This running Rook does not support cancelling restarts yet.")
        if not answer.get("ok"):
            leave(answer.get("error") or "Rook could not cancel the restart.")
        if answer.get("cancelled") and (was := answer.get("was")):
            label = "overlay reload" if was.get("kind") == "reload" else "restart"
            utter(f"Cancelled the waiting {label}, {asked_phrase(was.get('who'))}.")
        else:
            utter("No restart is waiting.")
        return
    timeout, reason = parse_wait_args(
        argv, "Usage: relay.py restart [--timeout DURATION] [--reason TEXT] | --status | --cancel", "a deploy")
    active = [None]
    prior_signals = install_stop_signals()
    try:
        token, note = wait_for_grant("restart", reason, timeout, active=active)
        utter(note, flush=True)
        if token == "restarted":
            return
        if desk.IS_MAC:
            rc, detail = desk.service_restart(try_only=False)
            mgr = "launchctl"
        else:
            done = subprocess.run([SYSTEMCTL, "--user", "restart", "rook.service"], capture_output=True, text=True)
            rc, detail, mgr = done.returncode, (done.stderr or done.stdout or "").strip(), "systemctl"
        if rc:
            if token:
                ask_rook("restart cancel", json.dumps({"id": token}), wait=5)
                active[0] = None
            leave(f"{mgr} could not restart Rook: {detail}" if detail else f"{mgr} could not restart Rook.")
        active[0] = None
        utter("Restarted Rook.")
    except StopSignal as stop:
        restore_stop_signals(prior_signals)
        if active[0]:
            ask_rook("restart cancel", json.dumps({"id": active[0]}), wait=2)
        name = "SIGTERM" if stop.signum == signal.SIGTERM else "SIGINT"
        leave(f"This command stopped on {name} and cancelled the restart.")
    finally:
        restore_stop_signals(prior_signals)


def reload_overlay_command(argv):
    """Handle relay.py reload overlay with the same quiet-moment grant as restart."""
    if os.environ.get("ROOK_AGENT"):
        leave(f"Rook never restarts or reloads itself. Only {OWNER} or the build thread runs this command.")
    timeout, reason = parse_wait_args(
        argv, "Usage: relay.py reload overlay [--timeout DURATION] [--reason TEXT]", "an overlay reload")
    active = [None]
    prior_signals = install_stop_signals()
    try:
        token, note = wait_for_grant("reload", reason, timeout, require_running=True, active=active)
        utter(note, flush=True)
        if token == "restarted":
            return
        answer = ask_rook("reload overlay", json.dumps({"id": token}) if token else "", wait=60)
        if answer is None or not answer.get("ok"):
            if token:
                ask_rook("restart cancel", json.dumps({"id": token}), wait=5)
                active[0] = None
            if answer is None:
                leave(f"Rook is not running: nothing answers at {INBOX}.")
            leave(answer.get("error") or "Rook could not reload the overlay.")
        active[0] = None
        utter(answer["said"])
    except StopSignal as stop:
        restore_stop_signals(prior_signals)
        if active[0]:
            ask_rook("restart cancel", json.dumps({"id": active[0]}), wait=2)
        name = "SIGTERM" if stop.signum == signal.SIGTERM else "SIGINT"
        leave(f"This command stopped on {name} and cancelled the overlay reload.")
    finally:
        restore_stop_signals(prior_signals)


def check():
    """Self-check light_dusts() mtime cache and handoff --work against the two-call form."""
    import shutil
    import tempfile
    import threading
    global OVERLAY, _LIGHT_DUSTS_CACHE, INBOX
    real_overlay, real_cache, real_parse = settings.OVERLAY, settings._LIGHT_DUSTS_CACHE, ast.parse
    # A check never reaches the caller's running Rook or its files. Every child gets scratch XDG folders, and
    # the caller's runtime folder is swapped for a trap socket that counts each connection.
    iso = Path(tempfile.mkdtemp(prefix="rook-check-"))
    (iso / "run").mkdir(mode=0o700)
    (iso / "trap").mkdir(mode=0o700)
    xdg_keys = ("XDG_RUNTIME_DIR", "XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME")
    real_xdg, real_inbox = {k: os.environ.get(k) for k in xdg_keys}, INBOX
    os.environ.update(XDG_RUNTIME_DIR=str(iso / "trap"), XDG_STATE_HOME=str(iso / "state"),
                      XDG_CONFIG_HOME=str(iso / "config"), XDG_DATA_HOME=str(iso / "data"),
                      XDG_CACHE_HOME=str(iso / "cache"))
    INBOX = iso / "trap/rook.sock"
    trap = socket.socket(socket.AF_UNIX)
    trap.bind(str(INBOX))
    trap.listen(8)
    trap.settimeout(0.05)
    trap_hits, trap_stop = [], threading.Event()

    def trap_serve():
        while not trap_stop.is_set():
            try:
                trap.accept()[0].close()
                trap_hits.append(1)
            except TimeoutError:
                pass

    trapper = threading.Thread(target=trap_serve, daemon=True)
    trapper.start()
    parses = []

    def counting_parse(source, *args, **kwargs):
        parses.append(1)
        return real_parse(source, *args, **kwargs)

    def run_cli(state_dir, args, stdin_text="", path_prefix=None, cfg_dir=None):
        env = {k: v for k, v in os.environ.items() if k != "T3CODE_THREAD_ID"}
        env.update(XDG_STATE_HOME=str(state_dir), ROOK_AGENT="1", XDG_RUNTIME_DIR=str(iso / "run"),
                   XDG_CONFIG_HOME=str(cfg_dir if cfg_dir is not None else iso / "config"),
                   XDG_DATA_HOME=str(iso / "data"), XDG_CACHE_HOME=str(iso / "cache"))
        if path_prefix is not None:
            env["PATH"] = f"{path_prefix}:{env.get('PATH', '')}"
        return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin_text, text=True,
                              capture_output=True, env=env)

    def strip_times(entry):
        return {k: v for k, v in entry.items() if k not in ("made", "changed")}

    try:
        # Confirm the real overlay still parses and caches identically.
        first = light_dusts()
        assert first[0] and first[1], first
        ast.parse = counting_parse
        assert light_dusts() == first and not parses
        with tempfile.TemporaryDirectory() as folder:
            sample = Path(folder) / "overlay.py"
            sample.write_text('LIGHT_LOOK = "ash"\nLIGHT_LOOKS = {"ash": {"description": "Soft ash"}}\n')
            OVERLAY = settings.OVERLAY = sample
            got = light_dusts()
            assert got == ([{"name": "ash", "description": "Soft ash"}], "ash") and len(parses) == 1
            got[0][0]["name"] = "mutated"  # Callers must not corrupt the cached list.
            assert light_dusts() == ([{"name": "ash", "description": "Soft ash"}], "ash") and len(parses) == 1
            sample.write_text('LIGHT_LOOK = "ink"\nLIGHT_LOOKS = {"ink": {"description": "Dark ink"}}\n')
            os.utime(sample, ns=(sample.stat().st_atime_ns, sample.stat().st_mtime_ns + 10_000_000))
            assert light_dusts() == ([{"name": "ink", "description": "Dark ink"}], "ink") and len(parses) == 2
            sample.unlink()
            assert light_dusts() == ([], None)
            # relay.py forge list finds themes/forge/forge.py from the repository root.
            forge = run_cli(Path(folder), ["forge", "list"], cfg_dir=Path(folder) / "forge-config")
            assert forge.returncode == 0 and forge.stdout == "No packs yet.\n", (forge.returncode, forge.stderr)
            # forge new on the default Devs path: a scene becomes 640 flat rows; a bad file or a mismatch gets one sentence.
            forge_cfg = Path(folder) / "forge-config"
            scene = '{"name": "ring", "parts": [{"id": "ring", "circle": [50, 50, 30]}]}'
            forge = run_cli(Path(folder), ["forge", "new", "dusty", "ring"], stdin_text=scene, cfg_dir=forge_cfg)
            made = json.loads((forge_cfg / "rook/themes/dusty/forms/ring.json").read_text())
            assert forge.returncode == 0 and len(made) == 640 and {r[2] for r in made} == {0.0}, forge.stderr
            for args, stdin_text, said in (
                    (["dusty", "orb", "--base", "nova"], "vec4 icon(vec2 p, float t, int l){return vec4(0);}",
                     "dusty is a points pack on devs. Start a new pack for this icon."),
                    (["dusty", "huge"], json.dumps([[0, 10 ** 400, 0]] + [[0, 0, 0]] * 639),
                     "Row 1 of the form lies outside the 124 px form box."),
                    (["dusty", "deep"], "[" * 30000 + "]" * 30000, None)):
                forge = run_cli(Path(folder), ["forge", "new", *args], stdin_text=stdin_text, cfg_dir=forge_cfg)
                assert forge.returncode == 1 and forge.stderr.strip() == (said or forge.stderr.strip().split("\n")[0]) \
                    and "Traceback" not in forge.stderr, (args, forge.stderr)
            # A hand-edited manifest that forge cannot add to gets one sentence.
            (forge_cfg / "rook/themes/handmade").mkdir(parents=True)
            for broken in ("[]", '{"icons": {}}', '{"base": "devs"}', "{"):
                (forge_cfg / "rook/themes/handmade/manifest.json").write_text(broken)
                forge = run_cli(Path(folder), ["forge", "new", "handmade", "ring"], stdin_text=scene, cfg_dir=forge_cfg)
                assert forge.returncode == 1 and forge.stderr.strip() == (
                    "The manifest of handmade needs a base theme and an icons object. Start a new pack instead."), forge.stderr
            # Combined handoff --work --print writes the same work entry and prints the same brief bytes as two calls.
            test_cfg = Path(folder) / "config"
            (test_cfg / "rook").mkdir(parents=True, exist_ok=True)
            (test_cfg / "rook/machines.json").write_text(json.dumps({
                "oak": {"environmentId": "env-oak", "run": [], "t3": "t3", "code": "/tmp/code"},
                "nimbus-pc": {"environmentId": "env-nb", "run": ["ssh", "host"], "t3": "t3", "code": "/tmp/code"},
            }) + "\n")
            test_fable, test_opus, test_neon = "mcp:test-fable-thread", "mcp:test-opus-thread", "mcp:test-neon-thread"
            (test_cfg / "rook/settings.json").write_text(json.dumps({
                "build_threads": {"fable": test_fable, "opus": test_opus, "neon": test_neon},
            }) + "\n")
            empty_cfg = Path(folder) / "empty-config"
            empty_cfg.mkdir(exist_ok=True)
            # With no machines.json, a stranger can still watch threads on their own machine, while unknown machines fail.
            local_watch = run_cli(Path(folder) / "empty-mach-ok", ["watch", "t-1"], cfg_dir=empty_cfg)
            assert local_watch.returncode == 0 and "Rook watches t-1" in local_watch.stdout, (local_watch.stdout, local_watch.stderr)
            bad_mach = run_cli(Path(folder) / "empty-mach", ["watch", "t-1", "--machine", "mars"], cfg_dir=empty_cfg)
            assert bad_mach.returncode != 0 and "No machine named mars" in bad_mach.stderr, bad_mach.stderr
            # Malformed machines.json warns clearly on stderr and falls back to this machine only.
            bad_m_cfg = Path(folder) / "bad-machines-cfg"
            (bad_m_cfg / "rook").mkdir(parents=True, exist_ok=True)
            (bad_m_cfg / "rook/machines.json").write_text("{broken machines json\n")
            bad_m_res = run_cli(Path(folder) / "bad-m-state", ["watch", "t-1", "--machine", "mars"], cfg_dir=bad_m_cfg)
            assert bad_m_res.returncode != 0 and "Ignoring invalid" in bad_m_res.stderr and "machines.json" in bad_m_res.stderr, bad_m_res.stderr
            no_bt = run_cli(Path(folder) / "empty-bt", ["handoff", "--print", "-"], "Hi.\n", cfg_dir=empty_cfg)
            assert no_bt.returncode != 0 and "No build threads are configured" in no_bt.stderr, no_bt.stderr
            brief_text = "Test Owner said: fix the halo.\nGoal: keep it steady.\n"
            numbered_brief = f"Work 1 on Rook's list.\n\n{brief_text}"
            for idx, (to_args, thread_id, cmd_args) in enumerate((
                ([], test_fable, ["handoff", "--print", "--work", "fix the halo", "--done", "halo stays steady", "-"]),
                (["--to", "opus"], test_opus, ["handoff", "--to", "opus", "--work", "fix the halo", "--done", "halo stays steady", "--print", "-"]),
                (["--to", "neon"], test_neon, ["handoff", "--to", "neon", "--work", "fix the halo", "--done", "halo stays steady", "--print", "-"]),
            )):
                two_state, one_state = Path(folder) / f"two-{idx}", Path(folder) / f"one-{idx}"
                add_res = run_cli(two_state, ["work", "add", "fix the halo", "--project", "rook", "--machine", "oak",
                                              "--thread", thread_id, "--done", "halo stays steady", "--brief", "-"], brief_text, cfg_dir=test_cfg)
                print_res = run_cli(two_state, ["handoff", *to_args, "--print", "-"], numbered_brief, cfg_dir=test_cfg)
                comb_res = run_cli(one_state, cmd_args, brief_text, cfg_dir=test_cfg)
                assert add_res.returncode == 0 and print_res.returncode == 0 and comb_res.returncode == 0, (
                    add_res.stderr, print_res.stderr, comb_res.stderr)
                first_line, rest = comb_res.stdout.split("\n", 1)
                key_line, printed_rest = print_res.stdout.split("\n", 1)
                # Each run prints a key of its own: the same brief sent twice on purpose is two messages.
                key = re.fullmatch(r"Send it with clientRequestId (rook-[0-9a-f]{24})\.", key_line)
                assert key and first_line.startswith("Added work 1, drafted. Send it with clientRequestId rook-")
                assert key.group(1) not in first_line, (first_line, key_line)
                assert rest == printed_rest, (rest, printed_rest)
                assert "Work 1 on Rook's list.\n\n" in rest, rest
                assert "never write a work number in notes or tells that Rook reads." in rest, rest
                assert "The restart waits for a quiet moment and may take minutes, so run it with a long shell timeout." in rest, rest
                listed = run_cli(one_state, ["work", "list"], cfg_dir=test_cfg)
                assert listed.returncode == 0 and listed.stdout.startswith("rook: fix the halo."), listed.stdout
                assert listed.stdout.strip().endswith(" [id 1]") and "Work 1" not in listed.stdout, listed.stdout
                two_entries = work.load(two_state / "rook/work.json")["entries"]
                one_entries = work.load(one_state / "rook/work.json")["entries"]
                assert len(two_entries) == len(one_entries) == 1
                assert strip_times(one_entries[0]) == strip_times(two_entries[0]), (one_entries[0], two_entries[0])
            # work close and work drop keep non-oak machines and confirm the entry leaves the list.
            cd_state = Path(folder) / "close-drop"
            assert run_cli(cd_state, ["work", "add", "fix the halo", "--project", "rook"], cfg_dir=test_cfg).returncode == 0
            assert run_cli(cd_state, ["work", "add", "export rounding", "--project", "acme-demo",
                                      "--machine", "nimbus-pc"], cfg_dir=test_cfg).returncode == 0
            closed = run_cli(cd_state, ["work", "close", "1"], cfg_dir=test_cfg)
            dropped = run_cli(cd_state, ["work", "drop", "2"], cfg_dir=test_cfg)
            assert closed.returncode == 0 and closed.stdout.strip() == "Closed rook: fix the halo. It leaves the list. [id 1]", closed.stdout
            assert dropped.returncode == 0 and dropped.stdout.strip() == "Dropped acme-demo on nimbus-pc: export rounding. It leaves the list. [id 2]", dropped.stdout
            # relay.py opens the record's file in one place only: journal.with_sends, with its one rule for a file
            # the new Rook has not opened yet. tell and timer reach the record through Rook's socket, and the
            # mailbox commands through the mailbox's own checked open.
            assert "sqlite3." + "connect" not in Path(__file__).read_text()
            # Old handoff --print without --work writes no work entry and prints only the framed brief.
            plain_state = Path(folder) / "plain"
            plain_res = run_cli(plain_state, ["handoff", "--print", "-"], numbered_brief, cfg_dir=test_cfg)
            assert plain_res.returncode == 0 and plain_res.stdout.split("\n", 1)[1] == printed_rest
            assert not (plain_state / "rook/work.json").exists()
            # Refusals and guards match work add and handoff, and write nothing or call t3.
            fake_bin = Path(folder) / "bin"
            fake_bin.mkdir()
            t3_called = fake_bin / "t3-called"
            fake_t3 = fake_bin / "t3"
            fake_t3.write_text(f"#!/bin/sh\necho \"$*\" >> {t3_called}\nexit 99\n")
            fake_t3.chmod(0o755)
            for bad_args, stdin_text in (
                (["handoff", "--work", "", "--print", "-"], brief_text),
                (["handoff", "--work", "-", "--print", "-"], brief_text),
                (["handoff", "--work", "-", "-"], brief_text),
                (["handoff", "--work", "fix the halo", "-"], brief_text),
                (["handoff", "--done", "x", "-"], brief_text),
                (["handoff", "--work", "--print", "-"], brief_text),
                (["handoff", "--print", "--work", "--print", "-"], brief_text),
                (["handoff", "--done", "x", "--print", "-"], brief_text),
                (["handoff", "--to", "nobody", "--print", "-"], brief_text),
                (["handoff", "--work", "x", "--machine", "mars", "--print", "-"], brief_text),
                (["handoff", "--work", "x", "--state", "bogus", "--print", "-"], brief_text),
                (["handoff", "--work", "x", "--print", "-"], "x" * (work.BRIEF + 1)),
                (["handoff", "--work", "x", "--print", "-"], "   "),
            ):
                bad = run_cli(plain_state, bad_args, stdin_text, path_prefix=fake_bin, cfg_dir=test_cfg)
                assert bad.returncode != 0, (bad_args, bad.stdout)
            assert not t3_called.exists(), t3_called.read_text()
            assert not (plain_state / "rook/work.json").exists()
            bad_file = plain_state / "rook/work.json"
            bad_file.parent.mkdir(parents=True, exist_ok=True)
            bad_file.write_text("{not json")
            damaged = run_cli(plain_state, ["handoff", "--work", "x", "--print", "-"], brief_text, cfg_dir=test_cfg)
            assert damaged.returncode != 0 and bad_file.read_text() == "{not json"
            # The t3 fallback that went out says so, even when the work list cannot be written after it.
            queued_bin = Path(folder) / "queued-bin"
            queued_bin.mkdir()
            (queued_bin / "t3").write_text("#!/bin/sh\ncat > /dev/null\necho Queued.\n")
            (queued_bin / "t3").chmod(0o755)
            locked_state = Path(folder) / "locked"
            (locked_state / "rook/work.lock").mkdir(parents=True)  # work.changing() cannot open its lock.
            assert shutil.which("t3", path=f"{queued_bin}:{os.environ.get('PATH', '')}") == str(queued_bin / "t3")
            went = run_cli(locked_state, ["handoff", "-"], brief_text, path_prefix=queued_bin, cfg_dir=test_cfg)
            assert went.returncode == 0 and went.stdout.startswith("Queued."), (went.stdout, went.stderr)

            # Restart, reload overlay, and daily-restart: guards, older-companion fallback, timeout, and failure cleanup.
            import threading
            fake_sys_bin = Path(folder) / "sys-bin"
            fake_sys_bin.mkdir()
            sys_calls = Path(folder) / "sys-calls"
            sys_fail = Path(folder) / "sys-fail"
            (fake_sys_bin / "systemctl").write_text(
                "#!/bin/sh\n"
                f"echo \"$*\" >> {sys_calls}\n"
                'if [ "$2" = "show" ] && [ "$6" = "rook.service" ]; then echo active; exit 0; fi\n'
                'if [ "$2" = "show" ] && [ "$6" = "agent-dream.service" ]; then echo inactive; exit 0; fi\n'
                f'if [ -f "{sys_fail}" ]; then echo "boom" >&2; exit 1; fi\n'
                "exit 0\n"
            )
            (fake_sys_bin / "systemctl").chmod(0o755)
            rt_dir = Path(folder) / "rt"
            rt_dir.mkdir(mode=0o700)
            sock_path = rt_dir / "rook.sock"
            mode = {"legacy": True, "busy": ["recording"], "polls": 0, "cancels": [], "reloads": 0}
            stop_srv = threading.Event()
            srv = socket.socket(socket.AF_UNIX)
            srv.bind(str(sock_path))
            sock_path.chmod(0o600)
            srv.listen(8)
            srv.settimeout(0.05)

            def serve():
                while not stop_srv.is_set():
                    try:
                        conn, _ = srv.accept()
                    except TimeoutError:
                        continue
                    except OSError:
                        break
                    with conn:
                        raw = b""
                        while chunk := conn.recv(65536):
                            raw += chunk
                        text = raw.decode(errors="replace")
                        cmd, _, body = text[len(REQUEST):].partition("\n") if text.startswith(REQUEST) else ("", "", "")
                        verb, _, arg = cmd.strip().partition(" ")
                        if verb == "restart":
                            if mode["legacy"]:
                                resp = {"ok": False, "error": "Unknown request 'restart'."}
                            elif arg == "status":
                                resp = {"ok": True, "state": "none", "busy": mode["busy"]}
                            elif arg == "cancel":
                                mode["cancels"].append(body)
                                resp = {"ok": True, "cancelled": True, "was": {"kind": "restart", "who": "terminal"}}
                            elif arg == "ask":
                                mode["polls"] += 1
                                if mode["busy"]:
                                    resp = {"ok": True, "granted": False, "busy": list(mode["busy"])}
                                else:
                                    resp = {"ok": True, "granted": True, "id": "tok"}
                            else:
                                resp = {"ok": False, "error": "bad"}
                        elif verb == "idle":
                            mode["polls"] += 1
                            busy = list(mode["busy"]) if mode["polls"] == 1 else []
                            resp = {"ok": True, "idle": not busy, "busy": busy}
                        elif verb == "reload" and arg == "overlay":
                            mode["reloads"] += 1
                            resp = {"ok": True, "said": "Started a new overlay."}
                        else:
                            resp = {"ok": False, "error": f"Unknown request {verb!r}."}
                        conn.sendall((json.dumps(resp) + "\n").encode())

            thread = threading.Thread(target=serve, daemon=True)
            thread.start()

            def run_ctl(args, *, rook_agent=False):
                env = {k: v for k, v in os.environ.items() if k not in ("T3CODE_THREAD_ID", "ROOK_AGENT", "SYSTEMCTL")}
                env.update(XDG_RUNTIME_DIR=str(rt_dir), XDG_STATE_HOME=str(plain_state),
                           XDG_DATA_HOME=str(Path(folder) / "data"),
                           PATH=f"{fake_sys_bin}:{env.get('PATH', '')}")
                if rook_agent:
                    env["ROOK_AGENT"] = "1"
                return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True, env=env)

            try:
                # Older companion without the restart verb: restart, reload overlay, and daily-restart fall back to idle.
                old_r = run_ctl(["restart"])
                assert old_r.returncode == 0 and "Restarted Rook." in old_r.stdout, (old_r.stdout, old_r.stderr)
                assert sys_calls.read_text().splitlines() == ["--user restart rook.service"]
                sys_calls.unlink()
                mode["polls"] = 0
                old_ov = run_ctl(["reload", "overlay"])
                assert old_ov.returncode == 0 and mode["reloads"] == 1, (old_ov.stdout, old_ov.stderr)
                mode["polls"], mode["busy"] = 1, []
                old_day = run_ctl(["daily-restart"])
                assert old_day.returncode == 0 and "Restarted Rook for the day." in old_day.stdout, (old_day.stdout, old_day.stderr)
                assert any(line == "--user try-restart rook.service" for line in sys_calls.read_text().splitlines())
                sys_calls.unlink()
                old_st = run_ctl(["restart", "--status"], rook_agent=True)
                assert old_st.returncode == 0 and "does not report restart status" in old_st.stdout, old_st.stdout
                old_can = run_ctl(["restart", "--cancel"])
                assert old_can.returncode != 0 and "does not support cancelling" in old_can.stderr, old_can.stderr

                # New companion: guards for ROOK_AGENT, reload timeout without reload, and daily-restart failure cleanup.
                mode.update(legacy=False, busy=["turn"], polls=0, cancels=[], reloads=0)
                for forbidden in (["restart"], ["restart", "--cancel"], ["reload", "overlay"], ["daily-restart"]):
                    denied = run_ctl(forbidden, rook_agent=True)
                    assert denied.returncode != 0 and "Rook never restarts" in denied.stderr, (forbidden, denied.stderr)
                allowed_st = run_ctl(["restart", "--status"], rook_agent=True)
                assert allowed_st.returncode == 0 and "No restart is waiting." in allowed_st.stdout, allowed_st.stdout
                ov_to = run_ctl(["reload", "overlay", "--timeout", "1s"])
                assert ov_to.returncode != 0 and "without reloading the overlay" in ov_to.stderr and "turn" in ov_to.stderr
                assert mode["reloads"] == 0 and len(mode["cancels"]) == 1
                mode.update(busy=[], cancels=[])
                sys_fail.write_text("1")
                day_fail = run_ctl(["daily-restart"])
                assert day_fail.returncode != 0 and "boom" in day_fail.stderr and len(mode["cancels"]) == 1, (day_fail.stderr, mode["cancels"])
                sys_fail.unlink()

                # Progress lines print at most once a minute, checked with a fake clock.
                import contextlib
                import io
                fake_now = [0.0]
                real_mono, real_sleep, real_ask = time.monotonic, time.sleep, ask_rook
                globals()["ask_rook"] = lambda cmd, body="", wait=300: (
                    {"ok": True, "granted": True, "id": "t"} if fake_now[0] >= 130
                    else {"ok": True, "granted": False, "busy": ["recording"]})
                time.monotonic = lambda: fake_now[0]
                time.sleep = lambda s: fake_now.__setitem__(0, fake_now[0] + 10.0)
                try:
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        tok, summary = wait_for_grant("restart", "clock test", 300)
                    lines = buf.getvalue().splitlines()
                    assert tok and len(lines) == 3 and all(l == "Waiting for a recording to end." for l in lines), lines
                    assert "Waited 130 s for a recording to end." == summary, summary
                finally:
                    time.monotonic, time.sleep = real_mono, real_sleep
                    globals()["ask_rook"] = real_ask

                # House-style phrasing checks: articles, terminal phrasing, and active voice when stopped.
                assert blocker_text(["recording", "turn", "scene", "overlay reload"]) == (
                    "a recording and a turn and a scene and an overlay reload")
                assert wait_line(["turn"]) == "Waiting for a turn to end."
                # Rook that does not answer in time is said plainly, with a subject, while waiting and when giving up.
                assert wait_line([SILENT], "overlay reload") == (
                    "Rook did not answer within 5 seconds, so the overlay reload asks again.")
                assert still_line([SILENT]) == "Rook did not answer in time."
                assert still_line(["turn"]) == "Rook was still blocked by a turn."
                assert wait_line(["a permission card that waits for Test Owner"]) == (
                    "Waiting because Rook has a permission card that waits for Test Owner.")
                assert asked_phrase("terminal") == "asked from a terminal"
                assert asked_phrase("build thread fable") == "asked by build thread Fable"
                assert asked_phrase("build thread neon") == "asked by build thread Neon"

                # If Rook restarts while a second caller waits, restart and reload overlay exit 0 without re-running.
                for subcmd, want_text in (
                    (["restart", "--timeout", "5s"], "already runs the new code"),
                    (["reload", "overlay", "--timeout", "5s"], "fresh overlay"),
                ):
                    if sys_calls.exists():
                        sys_calls.unlink()
                    mode.update(legacy=False, busy=["another restart"], polls=0, reloads=0)
                    stop_srv.clear()
                    if not sock_path.exists():
                        srv = socket.socket(socket.AF_UNIX)
                        srv.bind(str(sock_path))
                        sock_path.chmod(0o600)
                        srv.listen(8)
                        srv.settimeout(0.05)
                        thread = threading.Thread(target=serve, daemon=True)
                        thread.start()
                    env = {k: v for k, v in os.environ.items() if k not in ("T3CODE_THREAD_ID", "ROOK_AGENT", "SYSTEMCTL")}
                    env.update(XDG_RUNTIME_DIR=str(rt_dir), XDG_STATE_HOME=str(plain_state),
                               PATH=f"{fake_sys_bin}:{env.get('PATH', '')}")
                    proc = subprocess.Popen([sys.executable, str(SCRIPT), *subcmd],
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
                    deadline = time.monotonic() + 5
                    while mode["polls"] < 1 and time.monotonic() < deadline:
                        time.sleep(0.02)
                    assert mode["polls"] >= 1
                    stop_srv.set()
                    srv.close()
                    thread.join(2)
                    sock_path.unlink(missing_ok=True)
                    out, err = proc.communicate(timeout=5)
                    assert proc.returncode == 0 and want_text in out, (subcmd, proc.returncode, out, err)
                    assert not sys_calls.exists() and mode["reloads"] == 0

                # Default limit is 9 minutes; SIGTERM cancels both while waiting and after the grant.
                assert RESTART_WAIT_SECONDS == 9 * 60
                sys_slow = Path(folder) / "sys-slow"
                (fake_sys_bin / "systemctl").write_text(
                    "#!/bin/sh\n"
                    f"echo \"$*\" >> {sys_calls}\n"
                    f'if [ -f "{sys_slow}" ]; then sleep 5; fi\n'
                    "exit 0\n"
                )
                (fake_sys_bin / "systemctl").chmod(0o755)
                stop_srv.clear()
                srv = socket.socket(socket.AF_UNIX)
                srv.bind(str(sock_path))
                sock_path.chmod(0o600)
                srv.listen(8)
                srv.settimeout(0.05)
                thread = threading.Thread(target=serve, daemon=True)
                thread.start()
                sig_env = {k: v for k, v in os.environ.items() if k not in ("T3CODE_THREAD_ID", "ROOK_AGENT", "SYSTEMCTL")}
                sig_env.update(XDG_RUNTIME_DIR=str(rt_dir), XDG_STATE_HOME=str(plain_state),
                               PATH=f"{fake_sys_bin}:{sig_env.get('PATH', '')}")
                # SIGTERM while waiting.
                mode.update(legacy=False, busy=["recording"], polls=0, cancels=[])
                p_wait = subprocess.Popen([sys.executable, str(SCRIPT), "restart"],
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=sig_env)
                deadline = time.monotonic() + 5
                while mode["polls"] < 1 and time.monotonic() < deadline:
                    time.sleep(0.02)
                p_wait.terminate()
                out, err = p_wait.communicate(timeout=5)
                assert p_wait.returncode != 0 and "SIGTERM" in err and len(mode["cancels"]) == 1, (p_wait.returncode, out, err, mode["cancels"])
                # SIGTERM after grant (while systemctl runs).
                sys_slow.write_text("1")
                if sys_calls.exists():
                    sys_calls.unlink()
                mode.update(legacy=False, busy=[], polls=0, cancels=[])
                p_after = subprocess.Popen([sys.executable, str(SCRIPT), "restart"],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=sig_env)
                deadline = time.monotonic() + 5
                while not sys_calls.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                assert sys_calls.exists()
                p_after.terminate()
                out, err = p_after.communicate(timeout=5)
                assert p_after.returncode != 0 and "SIGTERM" in err and len(mode["cancels"]) == 1, (p_after.returncode, out, err, mode["cancels"])
                sys_slow.unlink()
            finally:
                stop_srv.set()
                srv.close()
                thread.join(2)
        # The trap stayed silent: no child and no in-process call reached a socket from the caller's runtime folder.
        time.sleep(0.1)
        assert not trap_hits, f"{len(trap_hits)} connection(s) reached the caller's rook.sock during the check."
    finally:
        trap_stop.set()
        trapper.join(1)
        trap.close()
        INBOX = real_inbox
        for k, v in real_xdg.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(iso, ignore_errors=True)
        ast.parse = real_parse
        OVERLAY = settings.OVERLAY = real_overlay
        _LIGHT_DUSTS_CACHE = settings._LIGHT_DUSTS_CACHE = real_cache
    check_settings()
    print("Relay cache and handoff: all checks passed.")


def record_send(write, *args, **kwargs):
    """One write to Rook's record of sends. A record that cannot be written never stops a handoff."""
    import sqlite3
    import journal
    try:
        return journal.with_sends(None, write, *args, **kwargs)
    except (sqlite3.Error, OSError) as error:
        print(f"Rook's record of sends is unavailable ({type(error).__name__}).", file=sys.stderr)
        return None


def device_command(argv):
    """Pair, list, and unpair the devices that reach Rook, such as the owner's phone. A paired device acts as the owner does,
    so only the owner and Rook's own agent pair one, never a T3 thread."""
    if os.environ.get("T3CODE_THREAD_ID") and not os.environ.get("ROOK_AGENT"):
        leave(f"A T3 thread cannot pair or unpair {OWNER}'s devices.")
    import server
    import session
    try:
        store = server.DeviceStore(session.devices_path()).open()
        if argv == ["pair"]:
            code = store.create_code()
            utter(f"Pairing code {code[:3]} {code[3:]}. It works once, within ten minutes.")
            name = session.tailnet_name()
            host = f"{name}:{session.SERVE_PORT}" if name else None
            line = (f"On your phone, open {host}" if len(f"On your phone, open {host}") <= 75 else host) if host \
                else "Open Rook on your phone and enter this code"
            guide({"code": f"{code[:3]} {code[3:]}", "text": line, "seconds": 600})  # The overlay shows both.
            if host:
                utter(f"Phone address: https://{host}/#code={code}")
            utter("Open Rook on the phone, and enter the code with a name for the phone.")
            return
        if argv == ["list"]:
            devices = store.list_devices()
            for device in devices:
                utter(f"{device.name}: paired {time_of_day(device.created_at)} {datetime.fromtimestamp(device.created_at):%-d %B}, "
                      f"last seen {time_of_day(device.last_seen)} {datetime.fromtimestamp(device.last_seen):%-d %B}. "
                      f"[{device.id}]")
            if not devices:
                utter("No device is paired.")
            return
        if len(argv) == 2 and argv[0] == "revoke":
            found = [d for d in store.list_devices() if argv[1] in (d.id, d.name) or d.name.casefold() == argv[1].casefold()]
            if len(found) != 1:
                leave("No paired device has that name." if not found else "Two devices share that name. Use its id.")
            answer = ask_rook(f"device revoke {found[0].id}", wait=5)
            if not (answer and answer.get("ok")):  # Rook is not running, or its server is off: the store alone.
                store.revoke(found[0].id)
            utter(f"Unpaired {found[0].name}. It must pair again to reach Rook.")
            return
    except server.StoreUnavailable as error:
        leave(str(error))
    leave("Usage: relay.py device pair | list | revoke NAME")


def handoff_description(text):
    """A handoff's one line in Rook's record of sends, which a notice may say: never its work number."""
    return " ".join(re.sub(r"\bWork \d+ on Rook's list\.", "", text).split())[:120]


def handoff_again(key):
    """Print a handoff that did not reach its thread, with its key, to send again unchanged."""
    import journal
    if key.startswith("cli-"):
        sys.exit("T3 never saw a key for a command-line send, so a second send would be a second message.")
    rows = record_send(lambda conn: conn.execute("SELECT brief, told FROM sends WHERE client = ? AND key = ? AND "
                                                 "brief IS NOT NULL", (journal.CLIENT, key)).fetchall())
    if not rows:
        sys.exit("Rook keeps no brief under that key: it was settled or never saved.")
    if rows[0][1] == "unknown":
        sys.exit("That handoff may have arrived, so Rook does not send it again.")
    print(f"Send it with clientRequestId {key}.")
    print(rows[0][0])


def handoff_command(argv):
    threads = active_build_threads()
    target_name = None
    build_thread, printed, wish, fields, words, at = threads.get("fable") or next(iter(threads.values()), ""), False, None, {}, [], 0
    while at < len(argv):
        arg = argv[at]
        if arg == "--to":
            target_name = argv[at + 1] if at + 1 < len(argv) else ""
            if not threads:
                sys.exit("No build threads are configured in settings.json.")
            if (build_thread := threads.get(target_name)) is None:
                keys = list(threads)
                names = keys[0] if len(keys) == 1 else " or ".join(keys) if len(keys) == 2 else ", ".join(keys[:-1]) + ", or " + keys[-1]
                sys.exit(f"handoff --to takes {names}.")
            at += 2
        elif arg == "--print":
            printed = True
            at += 1
        elif arg == "--again":
            if at + 1 >= len(argv) or len(argv) != 2:
                sys.exit("Use handoff --again KEY alone.")
            return handoff_again(argv[at + 1])
        elif arg == "--work":
            if (at + 1 >= len(argv) or not (val := argv[at + 1].strip())
                    or val == "-" or val.startswith("--")):
                sys.exit("Give a wish after --work.")
            wish = val
            at += 2
        elif arg in WORK_OPTIONS:
            if at + 1 >= len(argv) or not argv[at + 1].strip():
                sys.exit(f"Give a value after {arg}.")
            fields[WORK_OPTIONS[arg]] = argv[at + 1]
            at += 2
        elif arg.startswith("--"):
            sys.exit(f"{arg} is not an option of relay.py handoff.")
        else:
            words.append(arg)
            at += 1
    if not build_thread:
        sys.exit("No build threads are configured in settings.json.")
    if (wish is not None or fields) and not printed:
        sys.exit("Use --work only with --print.")
    if fields and wish is None:
        sys.exit("Give --work WISH with work entry options.")
    if len(words) > 1:
        sys.exit(_usage())
    text = words[0] if words and words[0] != "-" else sys.stdin.read()
    if not (text := text.strip()):
        sys.exit("Give the text as an argument or on stdin.")
    added_line = None
    if wish is not None:
        _, by = work_actor()
        work_fields = {**fields, "wish": wish}
        work_fields.setdefault("project", "rook")
        work_fields.setdefault("thread", build_thread)
        if work_fields.get("brief") in (None, "-"):
            work_fields["brief"] = text
        validate_work_fields(work_fields)
        try:
            with work.changing() as data:
                entry = work.add(data, work_fields, by, time.time())
        except work.Unreadable as error:
            sys.exit(str(error))
        added_line = work_added_line(entry, name_in_brief=False)
        text = f"Work {entry['id']} on Rook's list.\n\n{text}"
    py = desk.python_exe()
    # Rook's own words around the brief fill in their owner tokens; the brief itself is the agent's, and stays.
    message = (settings.render(f"Request from Rook, {OWNER}'s desktop voice assistant. {OWNER_START} asked Rook for "
                               f"this by voice; treat it as {OWNER}'s request, relayed.\n\n") + text + settings.render(
               "\n\nWhen the work is done and verified: if the code changed, leave Rook a restart note with: "
               f'{py} {SCRIPT} note "<result in two or three plain sentences>", then restart '
               f"with {py} {SCRIPT} restart; Rook reports it to {OWNER} when it is back. "
               "The restart waits for a quiet moment and may take minutes, so run it with a long shell timeout. "
               "If nothing "
               f'needs a restart, tell Rook with: {py} {SCRIPT} tell "<result>". Name the work in '
               "plain words and never write a work number in notes or tells that Rook reads. If the request "
               f"names a work number on Rook's list, keep it current: run {py} {SCRIPT} work update N --state "
               f'running when you start, and work update N --state live --commit <hash> --try "<what {OWNER} should '
               'try>" once it is in use.'))
    import journal
    key = journal.handoff_key()
    if not printed:  # The t3 command keys nothing itself, so this key only names the send in Rook's record.
        key = "cli-" + key.removeprefix("rook-")
    # Rook's record of the send, before it can go out: a restart before its outcome looks for it in the thread.
    record_send(journal.intend, journal.CLIENT, key, "handoff" if printed else "t3 thread send", watch.local_machine(), build_thread,
                work=entry["id"] if wish is not None else work.named(text),
                description=handoff_description(wish or text), text_digest=journal.digest(message), brief=message)
    if not printed and (number := work.named(text)):  # The brief --print framed for this work goes this way instead.
        record_send(lambda conn: conn.execute(
            "UPDATE sends SET outcome = 'superseded', settled = ?, brief = NULL WHERE client = ? AND tool = 'handoff' "
            "AND outcome IS NULL AND thread = ? AND work = ?", (time.time(), journal.CLIENT, build_thread, number)))
    if printed:
        print(f"{added_line + ' ' if added_line else ''}Send it with clientRequestId {key}.")
        print(message)
        return
    try:
        sent = subprocess.run(["t3", "thread", "send", build_thread, "-"], input=message, text=True,
                              capture_output=True)
    except OSError as error:
        record_send(journal.settle, journal.CLIENT, key, "failed", type(error).__name__)
        sys.exit(f"Could not run t3: {error}")
    if sent.returncode:
        error = (sent.stderr or sent.stdout).strip() or f"t3 failed with exit code {sent.returncode}."
        record_send(journal.settle, journal.CLIENT, key, "failed", error.splitlines()[0][:200])
        sys.exit(error)
    # The t3 command cannot steer: a busy build thread gets the request as its next turn.
    delivery = next((watch.COMMAND_DELIVERY[line.strip()] for line in sent.stdout.splitlines()
                     if line.strip() in watch.COMMAND_DELIVERY), None)
    record_send(journal.settle, journal.CLIENT, key, "landed", delivery or "sent")
    try:  # Rook sees no T3 send in this command, so its draft for the build thread is marked sent here.
        with work.changing() as data:
            work.thread_sent(data, watch.local_machine(), build_thread, None, delivery, time.time(), work.named(text))
    except (work.Unreadable, OSError):  # The send went out: a work list that cannot be written must not hide that.
        pass
    print({"started": "Sent. The build thread was idle and started on it.",
           "queued": "Queued. The build thread is busy and takes it after its current turn. "
                     "The t3 command cannot steer."}.get(delivery, "Sent to the build thread."))


def remember_command(argv):
    """Append one fact and why to Rook's own memory/incoming.jsonl with no model call."""
    if memory.is_shared():
        sys.exit('Shared memory is active; use ~/.agents/bin/remember "<fact and why>" instead.')
    if not argv:
        sys.exit("Usage: relay.py remember TEXT")
    try:
        memory.remember(" ".join(argv))
    except ValueError as error:
        sys.exit(str(error))
    print("Remembered.")


def dream_command(argv):
    """Run Rook's nightly memory tidy in own-memory mode."""
    if argv:
        sys.exit("Usage: relay.py dream")
    ok, message = memory.run_dream()
    if not ok:
        sys.exit(message)
    print(message)


def memory_command(argv):
    """Install or remove Rook's vendored shared memory system."""
    if argv == ["install-shared"]:
        ok, message = memory.install_shared()
        if not ok:
            sys.exit(message)
        print(message)
        return
    if argv == ["remove-shared"]:
        ok, message = memory.remove_shared()
        if not ok:
            sys.exit(message)
        print(message)
        return
    sys.exit("Usage: relay.py memory install-shared | remove-shared")


def check_memory():
    """Self-check Rook's own memory: append, load-path detection, empty-night skip, backups, and lock."""
    import fcntl
    import shlex
    import tempfile
    from datetime import timezone as _tz
    import antigravity_home

    with tempfile.TemporaryDirectory() as folder:
        base = Path(folder)
        fake_home = base / "home"
        xdg_data = base / "data"
        xdg_state = base / "state"
        xdg_config = base / "config"
        xdg_rt = base / "runtime"
        for d in (fake_home, xdg_data, xdg_state, xdg_config, xdg_rt):
            d.mkdir(mode=0o700, parents=True)

        def run_cli(*args, env_extra=None):
            env = {k: v for k, v in os.environ.items()
                   if k not in ("T3CODE_THREAD_ID", "ROOK_AGENT", "ROOK_DREAM_COMMAND", "SYSTEMCTL", "CODEX_HOME")}
            env.update(HOME=str(fake_home), XDG_DATA_HOME=str(xdg_data), XDG_STATE_HOME=str(xdg_state),
                       XDG_CONFIG_HOME=str(xdg_config), XDG_RUNTIME_DIR=str(xdg_rt))
            env.update(env_extra or {})
            return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True, env=env)

        # 1. Append via relay.py remember (argument and empty refusal).
        r1 = run_cli("remember", "User prefers Ghostty for terminal work because it is fast.")
        assert r1.returncode == 0 and "Remembered." in r1.stdout, (r1.returncode, r1.stdout, r1.stderr)
        r2 = run_cli("remember", "Morning standup is at 9:30 AM.")
        assert r2.returncode == 0, (r2.returncode, r2.stdout, r2.stderr)
        assert run_cli("remember", "   ").returncode != 0
        inc_file = xdg_data / "rook/memory/incoming.jsonl"
        assert inc_file.is_file() and (inc_file.stat().st_mode & 0o777) == 0o600
        rows = [json.loads(line) for line in inc_file.read_text().splitlines()]
        assert len(rows) == 2 and rows[0]["text"].startswith("User prefers Ghostty") and rows[1]["text"] == "Morning standup is at 9:30 AM."

        # 2. Load-path detection both ways, newest-first incoming cap, and Antigravity prompt compatibility.
        saved_env = {k: os.environ.get(k) for k in ("HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_RUNTIME_DIR")}
        try:
            os.environ.update(HOME=str(fake_home), XDG_DATA_HOME=str(xdg_data), XDG_STATE_HOME=str(xdg_state),
                              XDG_CONFIG_HOME=str(xdg_config), XDG_RUNTIME_DIR=str(xdg_rt))
            assert not memory.is_shared()
            (xdg_data / "rook/memory/MEMORY.md").write_text("- [Terminal](terminal.md): Terminal choice.\n")
            own_prompt = memory.startup_prompt("/usr/bin/python", SCRIPT)
            assert str(xdg_data / "rook/memory") in own_prompt and "relay.py remember" in own_prompt
            assert "- [Terminal](terminal.md): Terminal choice." in own_prompt
            assert "User prefers Ghostty" in own_prompt and "Morning standup is at 9:30 AM." in own_prompt
            sample_rook_prompt = (
                "You run as a full Claude Code session.\n" + own_prompt
                + "Before your first tool call, you may write one short sentence. "
                + "Your answer then confirms it in a few words. Never write filler."
            )
            agy_prompt = antigravity_home.prompt(sample_rook_prompt, str(base))
            assert "full Antigravity session" in agy_prompt and "relay.py remember" in agy_prompt

            # Newest incoming notes win when incoming.jsonl exceeds INCOMING_LIMIT.
            old_limit = memory.INCOMING_LIMIT
            memory.INCOMING_LIMIT = 90
            try:
                trimmed_prompt = memory.startup_prompt("/usr/bin/python", SCRIPT)
                assert "Morning standup is at 9:30 AM." in trimmed_prompt
                assert "older untidied notes" in trimmed_prompt
            finally:
                memory.INCOMING_LIMIT = old_limit

            # Shared mode when ~/.agents/hooks/memory-context.sh exists.
            shared_hook = fake_home / ".agents/hooks/memory-context.sh"
            shared_hook.parent.mkdir(parents=True)
            shared_hook.write_text("#!/bin/sh\necho shared\n")
            assert memory.is_shared() and memory.startup_prompt("/usr/bin/python", SCRIPT) == ""

            marker = base / "agent-ran"
            fake_agent = base / "fake-agent.py"
            fake_agent.write_text(
                f"#!{sys.executable}\n"
                "import os, pathlib, subprocess, sys\n"
                "prompt = sys.stdin.read()\n"
                f"pathlib.Path({str(marker)!r}).write_text(os.getcwd() + '\\n' + prompt)\n"
                "if os.environ.get('FAKE_FAIL') == '1':\n"
                "    print('simulated failure', file=sys.stderr)\n"
                "    sys.exit(2)\n"
                "if os.environ.get('FAKE_CONCURRENT'):\n"
                f"    subprocess.run([sys.executable, {str(SCRIPT)!r}, 'remember', os.environ['FAKE_CONCURRENT']], check=True)\n"
                "pathlib.Path('prefs.md').write_text('---\\nname: Prefs\\ndescription: User prefs\\n---\\nGhostty\\n')\n"
                "pathlib.Path('MEMORY.md').write_text('- [Prefs](prefs.md): User prefs\\n')\n"
                "print('Updated prefs.md and MEMORY.md.')\n"
            )
            fake_agent.chmod(0o755)
            fake_cmd = f"{shlex.quote(sys.executable)} {shlex.quote(str(fake_agent))}"

            shared_res = run_cli("dream", env_extra={"ROOK_DREAM_COMMAND": fake_cmd})
            assert shared_res.returncode == 0 and "Shared memory is active" in shared_res.stdout
            assert not marker.exists() and not (xdg_data / "rook/memory-backups").exists()

            # Back to own mode.
            shared_hook.unlink()
            inc_file.unlink()

            # 3. Empty-night skip, including a log holding only a startup turn and its reply.
            turns_file = xdg_state / "rook/turns.jsonl"
            turns_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            t_start = datetime.now(_tz.utc).isoformat()
            turns_file.write_text(
                json.dumps({"at": t_start, "session": "s0", "event": "request", "turn": "u0",
                            "source": "startup", "text": "Daily restart startup turn."}) + "\n"
                + json.dumps({"at": t_start, "session": "s0", "event": "response", "turns": ["u0"],
                              "status": "completed", "spoken": "Good morning."}) + "\n"
            )
            skip_res = run_cli("dream", env_extra={"ROOK_DREAM_COMMAND": fake_cmd})
            assert skip_res.returncode == 0 and "Skipped dream" in skip_res.stdout, (skip_res.stdout, skip_res.stderr)
            assert not marker.exists() and not (xdg_data / "rook/memory-backups").exists()

            # 4. Real dream run with incoming + spoken turn, failure preservation, and concurrent append.
            assert run_cli("remember", "Project Atlas uses Rust.").returncode == 0
            assert run_cli("remember", "Prefer concise replies.").returncode == 0
            t_now = datetime.now(_tz.utc).isoformat()
            with open(turns_file, "a") as handle:
                handle.write(
                    json.dumps({"at": t_now, "session": "s1", "event": "request", "turn": "u1",
                                "source": "spoken", "text": "Remember I switched my editor to Helix."}) + "\n"
                    + json.dumps({"at": t_now, "session": "s1", "event": "response", "turns": ["u1"],
                                  "status": "completed", "spoken": "Got it, Helix."}) + "\n"
                )

            fail_res = run_cli("dream", env_extra={"ROOK_DREAM_COMMAND": fake_cmd, "FAKE_FAIL": "1"})
            assert fail_res.returncode != 0 and "simulated failure" in fail_res.stderr
            assert inc_file.is_file() and len(inc_file.read_text().splitlines()) == 2
            assert not (xdg_state / "rook/memory-dream.stamp").exists()
            marker.unlink()

            ok_res = run_cli("dream", env_extra={
                "ROOK_DREAM_COMMAND": fake_cmd,
                "FAKE_CONCURRENT": "Concurrent fact saved mid-dream.",
            })
            assert ok_res.returncode == 0 and "Tidied memory (2 incoming, 2 turns)." in ok_res.stdout, (ok_res.stdout, ok_res.stderr)
            first_line, prompt_body = marker.read_text().split("\n", 1)
            assert first_line == str(xdg_data / "rook/memory")
            assert "Project Atlas uses Rust." in prompt_body and "switched my editor to Helix" in prompt_body
            assert "Daily restart startup turn." not in prompt_body
            assert (xdg_data / "rook/memory/prefs.md").is_file()
            remaining = [json.loads(line) for line in inc_file.read_text().splitlines()]
            assert len(remaining) == 1 and remaining[0]["text"] == "Concurrent fact saved mid-dream.", remaining
            marker.unlink()

            # Drain the concurrent line, then verify empty-night skip resumes and a newer typed turn triggers dream.
            assert run_cli("dream", env_extra={"ROOK_DREAM_COMMAND": fake_cmd}).returncode == 0 and not inc_file.exists()
            marker.unlink()
            skip2 = run_cli("dream", env_extra={"ROOK_DREAM_COMMAND": fake_cmd})
            assert skip2.returncode == 0 and "Skipped dream" in skip2.stdout and not marker.exists()
            future_iso = datetime.fromtimestamp(time.time() + 5, _tz.utc).isoformat()
            with open(turns_file, "a") as handle:
                handle.write(json.dumps({"at": future_iso, "session": "s1", "event": "request", "turn": "u2",
                                         "source": "typed", "text": "My coffee order is oat cortado."}) + "\n")
            turn_only = run_cli("dream", env_extra={"ROOK_DREAM_COMMAND": fake_cmd})
            assert turn_only.returncode == 0 and "Tidied memory (0 incoming, 1 turns)." in turn_only.stdout
            assert "oat cortado" in marker.read_text()
            marker.unlink()

            # 5. Antigravity nightly dream: missing agy skip, dream-guard confinement, and fake agy ACP tests.
            (xdg_config / "rook").mkdir(mode=0o700, parents=True, exist_ok=True)
            (xdg_config / "rook/settings.json").write_text(json.dumps({
                "agent": "antigravity",
                "agent_model": "gemini-4-neon",
                "agent_effort": "max",
            }) + "\n")
            assert run_cli("remember", "Antigravity dream test note.").returncode == 0
            empty_bin = base / "empty-bin"
            empty_bin.mkdir(mode=0o700, exist_ok=True)
            agy_skip = run_cli("dream", env_extra={"PATH": str(empty_bin)})
            assert agy_skip.returncode == 0 and "Skipped dream: agy is not installed." in agy_skip.stdout, (
                agy_skip.returncode, agy_skip.stdout, agy_skip.stderr
            )
            assert inc_file.is_file()

            # 5a. Exact generated `python3 -I desktop/memory.py dream-guard <mem_dir>` invoked from /tmp.
            mem_dir = (xdg_data / "rook/memory").resolve()
            guard_cmd = shlex.split(memory._dream_guard_command(mem_dir))
            assert guard_cmd[1] == "-I" and guard_cmd[3] == "dream-guard", guard_cmd
            outside_target = base / "escape-target.txt"
            outside_target.write_text("secret\n")
            escape_link = mem_dir / "escape-link.md"
            escape_link.symlink_to(outside_target)
            incoming_link = mem_dir / "incoming-link.md"
            incoming_link.symlink_to(mem_dir / "incoming.jsonl")
            guard_env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
            guard_env["HOME"] = str(fake_home)
            guard_env["REL"] = "a/b/c"

            def run_guard(tool, args):
                payload = json.dumps({"toolCall": {"name": tool, "args": args}, "workspacePaths": [str(mem_dir)]})
                done = subprocess.run(guard_cmd, input=payload, cwd="/tmp", text=True, capture_output=True, env=guard_env)
                assert done.returncode == 0, (tool, args, done.returncode, done.stderr)
                return json.loads(done.stdout)

            # Allowed inside mem_dir, including markdown content mentioning outside paths.
            for tool, args in (
                ("read_file", {"Path": str(mem_dir / "MEMORY.md")}),
                ("view_file", {"AbsolutePath": "prefs.md"}),
                ("read_file", {"Path": "incoming.jsonl"}),
                ("list_dir", {"DirectoryPath": str(mem_dir)}),
                ("find_by_name", {"SearchDirectory": "."}),
                ("grep_search", {"SearchPath": str(mem_dir), "Query": "/etc/passwd"}),
                ("write_file", {
                    "Path": str(mem_dir / "notes.md"),
                    "Content": "Discussed /etc/passwd and ~/Code/rook in conversation.\n",
                }),
                ("edit_file", {
                    "Path": "notes.md",
                    "Target": "/etc/passwd",
                    "Replacement": "~/Code/rook",
                }),
                ("replace_file_content", {
                    "TargetFile": str(mem_dir / "notes.md"),
                    "TargetContent": "old",
                    "ReplacementContent": "See /home/alice/Code/rook",
                }),
                ("finish", {}),
            ):
                verdict = run_guard(tool, args)
                assert verdict["decision"] == "allow", (tool, args, verdict)

            # Denied: incoming.jsonl (any case), dotfiles/subdirs/non-.md, mem_dir itself, outside paths, $, URIs, symlinks, forbidden tools, missing paths.
            for tool, args in (
                ("write_file", {"Path": str(mem_dir / "incoming.jsonl"), "Content": ""}),
                ("write_file", {"Path": str(mem_dir / "INCOMING.jsonl"), "Content": ""}),
                ("edit_file", {"Path": "incoming.jsonl", "Target": "a", "Replacement": "b"}),
                ("write_file", {"Path": str(incoming_link), "Content": "x"}),
                ("write_file", {"Path": str(mem_dir / ".agents/hooks.json"), "Content": "{}"}),
                ("write_file", {"Path": str(mem_dir / ".gemini/settings.json"), "Content": "{}"}),
                ("write_file", {"Path": str(mem_dir / ".hidden.md"), "Content": "x"}),
                ("write_file", {"Path": str(mem_dir / "sub/note.md"), "Content": "x"}),
                ("write_file", {"Path": str(mem_dir / "script.sh"), "Content": "echo hi"}),
                ("write_file", {"Path": str(mem_dir), "Content": "x"}),
                ("edit_file", {"Path": ".", "Target": "a", "Replacement": "b"}),
                ("write_file", {"Path": "/tmp/escape.txt", "Content": "x"}),
                ("write_file", {"Path": "../escape.txt", "Content": "x"}),
                ("write_file", {"Path": "~/escape.txt", "Content": "x"}),
                ("write_file", {"Path": "$HOME/escape.txt", "Content": "x"}),
                ("write_file", {"Path": "${HOME}/escape.txt", "Content": "x"}),
                ("write_file", {"Path": "$REL/../../../escape.md", "Content": "x"}),
                ("write_file", {"Path": "$NOPE/note.md", "Content": "x"}),
                ("write_file", {"Path": "file:///tmp/escape.txt", "Content": "x"}),
                ("write_file", {"Path": "vscode://x/../../etc/passwd", "Content": "x"}),
                ("read_file", {"Path": "vscode://x/../../etc/passwd"}),
                ("write_file", {"Path": str(escape_link), "Content": "x"}),
                ("read_file", {"Path": str(escape_link)}),
                ("read_file", {"Path": "/etc/passwd"}),
                ("list_dir", {"DirectoryPath": "/tmp"}),
                ("grep_search", {"SearchPath": str(mem_dir), "Cwd": "/tmp", "Query": "x"}),
                ("write_file", {"Path": "ok.md\n/tmp/bad.txt", "Content": "x"}),
                ("write_file", {"Content": "no path"}),
                ("edit_file", {"Target": "a", "Replacement": "b"}),
                ("read_file", {}),
                ("run_command", {"CommandLine": "ls"}),
                ("call_mcp_tool", {"ServerName": "t3", "ToolName": "t3_thread_list"}),
                ("mcp_t3_t3_thread_send", {"threadId": "t1", "message": "hi"}),
                ("invoke_subagent", {"Prompt": "do x"}),
                ("search_web", {"query": "test"}),
                ("ask_question", {"questions": []}),
                ("browser_open", {"url": "https://example.com"}),
                ("unknown_future_tool", {"Path": str(mem_dir / "ok.md")}),
            ):
                verdict = run_guard(tool, args)
                assert verdict["decision"] == "deny", (tool, args, verdict)
            escape_link.unlink()
            incoming_link.unlink()

            # 5b. Full run_dream() Antigravity ACP test with a fake agy script on PATH.
            fake_agy_bin = base / "agy-bin"
            fake_agy_bin.mkdir(mode=0o700, exist_ok=True)
            agy_trace = base / "agy-trace.json"
            agy_pid_file = base / "agy-hang.pid"
            fake_agy = fake_agy_bin / "agy"
            fake_agy.write_text(
                f"#!{sys.executable}\n"
                "import json, os, pathlib, sys, time\n"
                "from sqlite3 import connect as db_connect\n"
                "argv = sys.argv[1:]\n"
                "mode = os.environ.get('FAKE_AGY_MODE', 'ok')\n"
                f"trace_path = pathlib.Path({str(agy_trace)!r})\n"
                f"pid_path = pathlib.Path({str(agy_pid_file)!r})\n"
                "gdir = None\n"
                "for idx, a in enumerate(argv):\n"
                "    if a == '--gemini-dir' and idx + 1 < len(argv):\n"
                "        gdir = pathlib.Path(argv[idx + 1])\n"
                "record = {\n"
                "    'argv': argv,\n"
                "    'cwd': os.getcwd(),\n"
                "    'gemini_dir': str(gdir) if gdir else None,\n"
                "    'env_no_update': os.environ.get('AGY_CLI_DISABLE_AUTO_UPDATE'),\n"
                "    'env_browser': os.environ.get('BROWSER'),\n"
                "    'config_files': {},\n"
                "    'config_options': [],\n"
                "    'prompt': None,\n"
                "    'permissions': {},\n"
                "    'unexpected_resp': None,\n"
                "}\n"
                "if gdir:\n"
                "    for rel in ('config/hooks.json', 'config/mcp_config.json', 'config/skills.json', 'config/projects/default-cli-project.json'):\n"
                "        p = gdir / rel\n"
                "        if p.is_file():\n"
                "            record['config_files'][rel] = json.loads(p.read_text())\n"
                "def emit(obj):\n"
                "    sys.stdout.write(json.dumps({'jsonrpc': '2.0', **obj}) + '\\n')\n"
                "    sys.stdout.flush()\n"
                "def save():\n"
                "    tmp = trace_path.with_suffix('.tmp')\n"
                "    tmp.write_text(json.dumps(record))\n"
                "    tmp.replace(trace_path)\n"
                "save()\n"
                "for line in sys.stdin:\n"
                "    msg = json.loads(line)\n"
                "    m = msg.get('method')\n"
                "    rid = msg.get('id')\n"
                "    if m == 'initialize':\n"
                "        if mode == 'signed_out':\n"
                "            save()\n"
                "            emit({'id': rid, 'error': {'code': -32000, 'message': 'Authentication required'}})\n"
                "            break\n"
                "        emit({'id': rid, 'result': {'protocolVersion': 1}})\n"
                "    elif m == 'session/new':\n"
                "        emit({'id': rid, 'result': {'sessionId': 'fake-sess-1'}})\n"
                "    elif m == 'session/set_config_option':\n"
                "        p = msg.get('params') or {}\n"
                "        record['config_options'].append([p.get('configId'), p.get('value')])\n"
                "        emit({'id': rid, 'result': {}})\n"
                "    elif m == 'session/prompt':\n"
                "        record['prompt'] = msg.get('params')\n"
                "        save()\n"
                "        if mode == 'timeout':\n"
                "            pid_path.write_text(str(os.getpid()))\n"
                "            time.sleep(30)\n"
                "            break\n"
                "        if mode == 'refusal':\n"
                "            save()\n"
                "            emit({'id': rid, 'result': {'stopReason': 'refusal'}})\n"
                "            break\n"
                "        if mode == 'silent_error':\n"
                "            db = gdir / 'antigravity-acp/conversations/fake-sess-1.db'\n"
                "            db.parent.mkdir(parents=True, exist_ok=True)\n"
                "            c = db_connect(str(db))\n"
                "            c.execute('CREATE TABLE steps (idx INTEGER, step_type INTEGER, step_payload BLOB)')\n"
                "            c.execute('INSERT INTO steps VALUES (1, 17, ?)', (b'RESOURCE_EXHAUSTED (code 429): quota hit',))\n"
                "            c.commit(); c.close()\n"
                "            save()\n"
                "            emit({'id': rid, 'result': {'stopReason': 'end_turn'}})\n"
                "            break\n"
                "        # Unexpected server->client request must get -32601 without blocking.\n"
                "        emit({'id': 'srv-1', 'method': 'client/unknown_method', 'params': {}})\n"
                "        record['unexpected_resp'] = json.loads(sys.stdin.readline())\n"
                "        opts = [{'optionId': 'allow_id', 'kind': 'allow_once'}, {'optionId': 'deny_id', 'kind': 'reject_once'}]\n"
                "        for label, tc, tc_opts in (\n"
                "            ('inside_write', {'toolCallId': 't1', 'name': 'write_file', 'rawInput': {'Path': os.path.join(os.getcwd(), 'agy-note.md'), 'Content': 'See ~/Code/rook'}}, opts),\n"
                "            ('args_key_write', {'toolCallId': 't1b', 'name': 'write_file', 'args': {'Path': 'agy-note.md', 'Content': 'ok'}}, opts),\n"
                "            ('outside_write', {'toolCallId': 't2', 'name': 'write_file', 'rawInput': {'Path': '/tmp/escape.txt', 'Content': 'bad'}}, opts),\n"
                "            ('dot_config_write', {'toolCallId': 't2b', 'name': 'write_file', 'rawInput': {'Path': os.path.join(os.getcwd(), '.agents/hooks.json'), 'Content': '{}'}}, opts),\n"
                "            ('run_command', {'toolCallId': 't3', 'name': 'run_command', 'rawInput': {'CommandLine': 'id'}}, opts),\n"
                "            ('title_fallback', {'toolCallId': 't4', 'title': 'run_command'}, opts),\n"
                "            ('interaction', {'toolCallId': 'interaction_1', 'name': 'write_file', 'rawInput': {'Path': 'agy-note.md', 'Content': 'ok'}}, opts),\n"
                "            ('no_matching_opt', {'toolCallId': 't5', 'name': 'write_file', 'rawInput': {'Path': 'agy-note.md', 'Content': 'ok'}}, []),\n"
                "        ):\n"
                "            emit({'id': f'perm-{label}', 'method': 'session/request_permission', 'params': {'toolCall': tc, 'options': tc_opts}})\n"
                "            record['permissions'][label] = json.loads(sys.stdin.readline())\n"
                "        emit({'method': 'session/update', 'params': 'malformed-params'})\n"
                "        emit({'method': 'session/update', 'params': {'update': 'malformed-update'}})\n"
                "        emit({'method': 'session/update', 'params': {'update': {'sessionUpdate': 'agent_message_chunk', 'content': 'malformed-content'}}})\n"
                "        emit({'method': 'session/update', 'params': {'update': {'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': 'Working...'}}}})\n"
                "        emit({'method': 'session/update', 'params': {'update': {'sessionUpdate': 'tool_call', 'toolCallId': 't1', 'name': 'write_file'}}})\n"
                "        pathlib.Path('agy-note.md').write_text('---\\nname: Agy Note\\ndescription: Tidied via ACP\\n---\\nSaved.\\n')\n"
                "        pathlib.Path('MEMORY.md').write_text('- [Agy Note](agy-note.md): Tidied via ACP\\n')\n"
                "        emit({'method': 'session/update', 'params': {'update': {'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': 'Updated agy-note.md and MEMORY.md.'}}}})\n"
                "        save()\n"
                "        emit({'id': rid, 'result': {'stopReason': 'end_turn'}})\n"
                "        break\n"
            )
            fake_agy.chmod(0o755)
            agy_path = f"{fake_agy_bin}:{os.environ.get('PATH', '')}"

            # 5b-i. Signed-out (-32000), quota refusal, silent DB error, and timeout preserve incoming.jsonl and stamp.
            turns_file.unlink(missing_ok=True)
            stamp_file = xdg_state / "rook/memory-dream.stamp"
            stamp_file.unlink(missing_ok=True)
            for fail_mode, expected_err in (
                ("signed_out", "not signed in"),
                ("refusal", "refused"),
                ("silent_error", "quota hit"),
            ):
                agy_fail = run_cli("dream", env_extra={"PATH": agy_path, "FAKE_AGY_MODE": fail_mode})
                assert agy_fail.returncode != 0 and expected_err in agy_fail.stderr.lower(), (
                    fail_mode, agy_fail.returncode, agy_fail.stdout, agy_fail.stderr
                )
                assert inc_file.is_file() and not stamp_file.exists()
                tr = json.loads(agy_trace.read_text())
                assert tr["gemini_dir"] and not Path(tr["gemini_dir"]).exists(), tr["gemini_dir"]

            # Timeout kills hung fake agy, preserves incoming.jsonl + stamp, and cleans up temp --gemini-dir.
            timeout_env = {k: v for k, v in os.environ.items()
                           if k not in ("T3CODE_THREAD_ID", "ROOK_AGENT", "ROOK_DREAM_COMMAND", "SYSTEMCTL")}
            timeout_env.update(
                HOME=str(fake_home), XDG_DATA_HOME=str(xdg_data), XDG_STATE_HOME=str(xdg_state),
                XDG_CONFIG_HOME=str(xdg_config), XDG_RUNTIME_DIR=str(xdg_rt),
                PATH=agy_path, FAKE_AGY_MODE="timeout",
            )
            timeout_res = subprocess.run(
                [sys.executable, "-c",
                 f"import sys; sys.path.insert(0, {str(SCRIPT.parent)!r}); import memory; "
                 "ok, msg = memory.run_dream(timeout=1.0); print(msg, file=sys.stderr if not ok else sys.stdout); "
                 "sys.exit(0 if ok else 1)"],
                text=True, capture_output=True, env=timeout_env,
            )
            assert timeout_res.returncode != 0 and "timed out" in timeout_res.stderr.lower(), (
                timeout_res.returncode, timeout_res.stdout, timeout_res.stderr
            )
            assert inc_file.is_file() and not stamp_file.exists()
            tr_to = json.loads(agy_trace.read_text())
            assert tr_to["gemini_dir"] and not Path(tr_to["gemini_dir"]).exists(), tr_to["gemini_dir"]
            if agy_pid_file.is_file():
                hung_pid = int(agy_pid_file.read_text().strip())
                try:
                    os.kill(hung_pid, 0)
                    raise AssertionError(f"Hung fake agy process {hung_pid} was not killed")
                except ProcessLookupError:
                    pass

            # 5b-ii. Success path: verifies config files, options, permissions, note write, drain, stamp, cleanup.
            agy_ok = run_cli("dream", env_extra={"PATH": agy_path, "FAKE_AGY_MODE": "ok"})
            assert agy_ok.returncode == 0, (agy_ok.returncode, agy_ok.stdout, agy_ok.stderr)
            assert "Tidied memory (1 incoming, 0 turns)." in agy_ok.stdout, agy_ok.stdout
            assert "Updated agy-note.md and MEMORY.md." in agy_ok.stdout, agy_ok.stdout
            assert "Working..." not in agy_ok.stdout, agy_ok.stdout
            assert not inc_file.exists()
            assert (mem_dir / "agy-note.md").is_file()
            assert stamp_file.is_file()
            tr_ok = json.loads(agy_trace.read_text())
            assert tr_ok["gemini_dir"] and not Path(tr_ok["gemini_dir"]).exists(), tr_ok["gemini_dir"]
            assert "--include-default-customizations=false" in tr_ok["argv"]
            assert tr_ok["env_no_update"] == "1" and tr_ok["env_browser"] == desk.false_exe()
            assert tr_ok["config_files"]["config/mcp_config.json"] == {"mcpServers": {}}
            assert tr_ok["config_files"]["config/skills.json"] == {"entries": []}
            hooks_list = tr_ok["config_files"]["config/hooks.json"]["rook-dream"]["PreToolUse"]
            assert hooks_list[0]["matcher"] == ".*" and "dream-guard" in hooks_list[0]["hooks"][0]["command"]
            assert ["mode", "default"] in tr_ok["config_options"]
            assert ["model", "gemini-4-neon"] in tr_ok["config_options"]
            assert ["thought_level", "xhigh"] in tr_ok["config_options"]
            assert "Antigravity dream test note." in tr_ok["prompt"]["prompt"][0]["text"]
            assert tr_ok["unexpected_resp"]["error"]["code"] == -32601
            assert tr_ok["permissions"]["inside_write"]["result"]["outcome"] == {"outcome": "selected", "optionId": "allow_id"}
            assert tr_ok["permissions"]["args_key_write"]["result"]["outcome"] == {"outcome": "selected", "optionId": "allow_id"}
            assert tr_ok["permissions"]["outside_write"]["result"]["outcome"] == {"outcome": "selected", "optionId": "deny_id"}
            assert tr_ok["permissions"]["dot_config_write"]["result"]["outcome"] == {"outcome": "selected", "optionId": "deny_id"}
            assert tr_ok["permissions"]["run_command"]["result"]["outcome"] == {"outcome": "selected", "optionId": "deny_id"}
            assert tr_ok["permissions"]["title_fallback"]["result"]["outcome"] == {"outcome": "selected", "optionId": "deny_id"}
            assert tr_ok["permissions"]["interaction"]["result"]["outcome"] == {"outcome": "selected", "optionId": "deny_id"}
            assert tr_ok["permissions"]["no_matching_opt"]["result"]["outcome"] == {"outcome": "cancelled"}

            # 5b-iii. Large prompt (>64 KiB) completes cleanly and default thought_level is sent when unset.
            (xdg_config / "rook/settings.json").write_text(json.dumps({"agent": "antigravity"}) + "\n")
            big_fact = "Large note payload: " + ("z" * 70_000)
            assert run_cli("remember", big_fact).returncode == 0
            big_ok = run_cli("dream", env_extra={"PATH": agy_path, "FAKE_AGY_MODE": "ok"})
            assert big_ok.returncode == 0, (big_ok.returncode, big_ok.stdout, big_ok.stderr)
            tr_big = json.loads(agy_trace.read_text())
            assert len(tr_big["prompt"]["prompt"][0]["text"]) > 70_000
            assert ["thought_level", "low"] in tr_big["config_options"], tr_big["config_options"]
            assert not inc_file.exists()

            # 5c. Codex nightly dream: missing codex skip, fake codex exec argv/CODEX_HOME/stdin/output/failures.
            (xdg_config / "rook/settings.json").write_text(json.dumps({
                "agent": "codex",
                "agent_model": "gpt-6.2-sol",
                "agent_effort": "high",
            }) + "\n")
            assert run_cli("remember", "Codex dream test note.").returncode == 0
            codex_skip = run_cli("dream", env_extra={"PATH": str(empty_bin)})
            assert codex_skip.returncode == 0 and "Skipped dream: codex is not installed." in codex_skip.stdout, (
                codex_skip.returncode, codex_skip.stdout, codex_skip.stderr
            )
            assert inc_file.is_file()

            fake_user_codex = fake_home / ".codex"
            fake_user_codex.mkdir(mode=0o700, parents=True, exist_ok=True)
            (fake_user_codex / "auth.json").write_text('{"tokens": {"access_token": "fake-test-token"}}\n')
            (fake_user_codex / ".credentials.json").write_text('{"fake": true}\n')
            (fake_user_codex / "config.toml").write_text('model = "gpt-should-be-ignored"\n')
            fake_host_skill = fake_home / ".agents/skills/demo-skill/SKILL.md"
            fake_host_skill.parent.mkdir(parents=True, exist_ok=True)
            fake_host_skill.write_text("---\nname: demo-skill\n---\n")

            fake_codex_bin = base / "codex-bin"
            fake_codex_bin.mkdir(mode=0o700, exist_ok=True)
            codex_trace = base / "codex-trace.json"
            codex_pid_file = base / "codex-hang.pids"
            fake_codex = fake_codex_bin / "codex"
            fake_codex.write_text(
                f"#!{sys.executable}\n"
                "import json, os, pathlib, subprocess, sys, time\n"
                "argv = sys.argv[1:]\n"
                "mode = os.environ.get('FAKE_CODEX_MODE', 'ok')\n"
                f"trace_path = pathlib.Path({str(codex_trace)!r})\n"
                f"pid_path = pathlib.Path({str(codex_pid_file)!r})\n"
                "ch = os.environ.get('CODEX_HOME')\n"
                "ch_path = pathlib.Path(ch) if ch else None\n"
                "out_path = None\n"
                "for idx, a in enumerate(argv):\n"
                "    if a == '-o' and idx + 1 < len(argv):\n"
                "        out_path = pathlib.Path(argv[idx + 1])\n"
                "cfg_text = (ch_path / 'config.toml').read_text() if (ch_path and (ch_path / 'config.toml').is_file()) else ''\n"
                "record = {\n"
                "    'argv': argv,\n"
                "    'cwd': os.getcwd(),\n"
                "    'codex_home': ch,\n"
                "    'codex_home_parent': str(ch_path.parent) if ch_path else None,\n"
                "    'browser': os.environ.get('BROWSER'),\n"
                "    'config_toml': cfg_text,\n"
                "    'auth_is_symlink': bool(ch_path and (ch_path / 'auth.json').is_symlink()),\n"
                "    'auth_target': os.readlink(ch_path / 'auth.json') if (ch_path and (ch_path / 'auth.json').is_symlink()) else None,\n"
                "    'creds_is_symlink': bool(ch_path and (ch_path / '.credentials.json').is_symlink()),\n"
                "    'creds_target': os.readlink(ch_path / '.credentials.json') if (ch_path and (ch_path / '.credentials.json').is_symlink()) else None,\n"
                "    'out_path': str(out_path) if out_path else None,\n"
                "    'stdin_len': 0,\n"
                "    'stdin_sample': '',\n"
                "}\n"
                "def save():\n"
                "    tmp = trace_path.with_suffix('.tmp')\n"
                "    tmp.write_text(json.dumps(record))\n"
                "    tmp.replace(trace_path)\n"
                "if mode == 'timeout':\n"
                "    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
                "    pid_path.write_text(f'{os.getpid()}\\n{child.pid}\\n')\n"
                "    save()\n"
                "    time.sleep(30)\n"
                "    sys.exit(0)\n"
                "prompt = sys.stdin.read()\n"
                "record['stdin_len'] = len(prompt)\n"
                "record['stdin_sample'] = prompt[:4000]\n"
                "save()\n"
                "if mode == 'fail':\n"
                "    print('simulated codex failure', file=sys.stderr)\n"
                "    sys.exit(2)\n"
                "if mode == 'prompt_echo_fail':\n"
                "    print('user prompt: earlier we discussed not signed in and codex login renewal', file=sys.stderr)\n"
                "    print('line 1', file=sys.stderr)\n"
                "    print('line 2', file=sys.stderr)\n"
                "    print('line 3', file=sys.stderr)\n"
                "    print('line 4', file=sys.stderr)\n"
                "    print('network connection reset while talking to backend', file=sys.stderr)\n"
                "    sys.exit(2)\n"
                "if mode == 'unauth':\n"
                "    print('ERROR: unexpected status 401 Unauthorized: Missing bearer or basic authentication in header', file=sys.stderr)\n"
                "    sys.exit(1)\n"
                "if mode == 'symlink_incoming':\n"
                "    p = pathlib.Path('incoming.jsonl')\n"
                "    p.unlink(missing_ok=True)\n"
                "    p.symlink_to('/etc/hosts')\n"
                "    sys.exit(0)\n"
                "pathlib.Path('codex-note.md').write_text('---\\nname: Codex Note\\ndescription: Tidied via Codex\\n---\\nSaved.\\n')\n"
                "pathlib.Path('MEMORY.md').write_text('- [Codex Note](codex-note.md): Tidied via Codex\\n')\n"
                "if mode == 'ok_stdout_fallback':\n"
                "    print('OpenAI Codex banner')\n"
                "    print('Fallback summary from stdout.')\n"
                "    sys.exit(0)\n"
                "if out_path is not None:\n"
                "    out_path.write_text('Updated codex-note.md and MEMORY.md.\\n')\n"
                "print('noisy stdout header that -o overrides')\n"
            )
            fake_codex.chmod(0o755)
            codex_path = f"{fake_codex_bin}:{os.environ.get('PATH', '')}"

            # 5c-i. Failure modes (non-zero exit, echoed-prompt non-auth fail, unauth, symlinked incoming, timeout) preserve incoming + stamp and clean up temp CODEX_HOME.
            stamp_file.unlink(missing_ok=True)
            for fail_mode, expected_err, forbidden_err in (
                ("fail", "simulated codex failure", "not signed in"),
                ("prompt_echo_fail", "network connection reset", "not signed in"),
                ("unauth", "not signed in", "network connection"),
            ):
                cx_fail = run_cli("dream", env_extra={"PATH": codex_path, "FAKE_CODEX_MODE": fail_mode})
                assert cx_fail.returncode != 0 and expected_err in cx_fail.stderr.lower(), (
                    fail_mode, cx_fail.returncode, cx_fail.stdout, cx_fail.stderr
                )
                assert forbidden_err not in cx_fail.stderr.lower(), (fail_mode, cx_fail.stderr)
                assert inc_file.is_file() and not stamp_file.exists()
                tr_cx = json.loads(codex_trace.read_text())
                assert tr_cx["codex_home"] and tr_cx["codex_home"] != str(fake_user_codex), tr_cx
                assert not Path(tr_cx["codex_home"]).exists() and not Path(tr_cx["codex_home_parent"]).exists(), tr_cx

            # Symlinked incoming.jsonl fails dream, removes symlink, and preserves stamp.
            saved_inc_bytes = inc_file.read_bytes()
            cx_sym = run_cli("dream", env_extra={"PATH": codex_path, "FAKE_CODEX_MODE": "symlink_incoming"})
            assert cx_sym.returncode != 0 and "symlink" in cx_sym.stderr.lower(), (cx_sym.returncode, cx_sym.stderr)
            assert not inc_file.is_symlink() and not stamp_file.exists()
            inc_file.write_bytes(saved_inc_bytes)

            codex_trace.unlink(missing_ok=True)
            codex_pid_file.unlink(missing_ok=True)
            cx_timeout_env = {k: v for k, v in os.environ.items()
                              if k not in ("T3CODE_THREAD_ID", "ROOK_AGENT", "ROOK_DREAM_COMMAND", "SYSTEMCTL", "CODEX_HOME")}
            cx_timeout_env.update(
                HOME=str(fake_home), XDG_DATA_HOME=str(xdg_data), XDG_STATE_HOME=str(xdg_state),
                XDG_CONFIG_HOME=str(xdg_config), XDG_RUNTIME_DIR=str(xdg_rt),
                PATH=codex_path, FAKE_CODEX_MODE="timeout",
            )
            cx_timeout_res = subprocess.run(
                [sys.executable, "-c",
                 f"import sys; sys.path.insert(0, {str(SCRIPT.parent)!r}); import memory; "
                 "ok, msg = memory.run_dream(timeout=2.0); print(msg, file=sys.stderr if not ok else sys.stdout); "
                 "sys.exit(0 if ok else 1)"],
                text=True, capture_output=True, env=cx_timeout_env,
            )
            assert cx_timeout_res.returncode != 0 and "timed out" in cx_timeout_res.stderr.lower(), (
                cx_timeout_res.returncode, cx_timeout_res.stdout, cx_timeout_res.stderr
            )
            assert inc_file.is_file() and not stamp_file.exists()
            tr_cx_to = json.loads(codex_trace.read_text())
            assert tr_cx_to["codex_home_parent"] and not Path(tr_cx_to["codex_home_parent"]).exists(), tr_cx_to
            assert codex_pid_file.is_file()
            for raw_pid in codex_pid_file.read_text().splitlines():
                if not raw_pid.strip():
                    continue
                hung_pid = int(raw_pid.strip())
                try:
                    os.kill(hung_pid, 0)
                    raise AssertionError(f"Hung fake codex process {hung_pid} was not killed")
                except ProcessLookupError:
                    pass

            # 5c-ii. Success path: argv flags, isolated CODEX_HOME + config.toml, auth symlinks, -o summary, drain, stamp, cleanup.
            cx_ok = run_cli("dream", env_extra={"PATH": codex_path, "FAKE_CODEX_MODE": "ok"})
            assert cx_ok.returncode == 0, (cx_ok.returncode, cx_ok.stdout, cx_ok.stderr)
            assert "Tidied memory (1 incoming, 0 turns)." in cx_ok.stdout, cx_ok.stdout
            assert "Updated codex-note.md and MEMORY.md." in cx_ok.stdout, cx_ok.stdout
            assert "noisy stdout header" not in cx_ok.stdout, cx_ok.stdout
            assert not inc_file.exists()
            assert (mem_dir / "codex-note.md").is_file()
            assert stamp_file.is_file()
            tr_cx_ok = json.loads(codex_trace.read_text())
            argv = tr_cx_ok["argv"]
            assert argv[0] == "exec" and argv[-1] == "-", argv
            assert argv[argv.index("--sandbox") + 1] == "workspace-write", argv
            assert argv[argv.index("-C") + 1] == str(mem_dir), argv
            for flag in ("--ephemeral", "--skip-git-repo-check", "--ignore-rules"):
                assert flag in argv, (flag, argv)
            assert argv[argv.index("--color") + 1] == "never", argv
            assert argv[argv.index("-m") + 1] == "gpt-6.2-sol", argv
            assert argv[argv.index("-o") + 1] == tr_cx_ok["out_path"], argv
            disabled = [argv[i + 1] for i, tok in enumerate(argv) if tok == "--disable" and i + 1 < len(argv)]
            for feat in ("apps", "browser_use", "computer_use", "image_generation", "plugins", "multi_agent"):
                assert feat in disabled, (feat, disabled)
            c_vals = [argv[i + 1] for i, tok in enumerate(argv) if tok == "-c" and i + 1 < len(argv)]
            for required_cfg in (
                'approval_policy="never"',
                'web_search="disabled"',
                "project_doc_max_bytes=0",
                'history.persistence="none"',
                "sandbox_workspace_write.network_access=false",
                "sandbox_workspace_write.exclude_slash_tmp=true",
                "sandbox_workspace_write.exclude_tmpdir_env_var=true",
                'model_reasoning_effort="high"',
            ):
                assert required_cfg in c_vals, (required_cfg, c_vals)
            cfg_toml = tr_cx_ok["config_toml"]
            assert 'web_search = "disabled"' in cfg_toml and "project_doc_max_bytes = 0" in cfg_toml, cfg_toml
            assert str(fake_host_skill) in cfg_toml and "enabled = false" in cfg_toml, cfg_toml
            assert tr_cx_ok["cwd"] == str(mem_dir), tr_cx_ok
            assert tr_cx_ok["browser"] == desk.false_exe(), tr_cx_ok
            assert tr_cx_ok["codex_home"] != str(fake_user_codex), tr_cx_ok
            assert tr_cx_ok["auth_is_symlink"] and Path(tr_cx_ok["auth_target"]) == fake_user_codex / "auth.json", tr_cx_ok
            assert tr_cx_ok["creds_is_symlink"] and Path(tr_cx_ok["creds_target"]) == fake_user_codex / ".credentials.json", tr_cx_ok
            assert not Path(tr_cx_ok["codex_home_parent"]).exists(), tr_cx_ok
            assert sorted(p.name for p in fake_user_codex.iterdir()) == [".credentials.json", "auth.json", "config.toml"]
            assert "Codex dream test note." in tr_cx_ok["stdin_sample"]

            # 5c-iii. Large prompt (>64 KiB) over stdin, unset model/effort omitted, broken auth symlink skipped, stdout fallback.
            (fake_user_codex / "auth.json").unlink()
            (fake_user_codex / "auth.json").symlink_to(base / "nonexistent-auth.json")
            (xdg_config / "rook/settings.json").write_text(json.dumps({"agent": "codex"}) + "\n")
            big_cx_fact = "Large Codex payload: " + ("q" * 70_000)
            assert run_cli("remember", big_cx_fact).returncode == 0
            cx_big = run_cli("dream", env_extra={"PATH": codex_path, "FAKE_CODEX_MODE": "ok_stdout_fallback"})
            assert cx_big.returncode == 0, (cx_big.returncode, cx_big.stdout, cx_big.stderr)
            assert "Fallback summary from stdout." in cx_big.stdout, cx_big.stdout
            tr_cx_big = json.loads(codex_trace.read_text())
            assert tr_cx_big["stdin_len"] > 70_000, tr_cx_big["stdin_len"]
            assert not tr_cx_big["auth_is_symlink"], tr_cx_big
            assert "-m" not in tr_cx_big["argv"], tr_cx_big["argv"]
            assert not any("model_reasoning_effort" in tok for tok in tr_cx_big["argv"]), tr_cx_big["argv"]
            assert not Path(tr_cx_big["codex_home_parent"]).exists(), tr_cx_big
            assert not inc_file.exists()

            # 5d. Pi nightly dream: missing pi skips; a fake pi gets the print-mode argv, the prompt on stdin, and a
            # guard that keeps writes in the memory folder.
            (xdg_config / "rook/settings.json").write_text(json.dumps({
                "agent": "pi", "agent_model": "llamacpp", "agent_effort": "low"}) + "\n")
            assert run_cli("remember", "Pi dream test note.").returncode == 0
            pi_skip = run_cli("dream", env_extra={"PATH": str(empty_bin)})
            assert pi_skip.returncode == 0 and "Skipped dream: pi is not installed." in pi_skip.stdout, pi_skip.stdout
            pi_bin, pi_trace = base / "pi-bin", base / "pi-trace.json"
            pi_bin.mkdir()
            (pi_bin / "pi").write_text(f"#!{sys.executable}\nimport json, os, sys\n"
                                       f"json.dump({{'argv': sys.argv[1:], 'guard': os.environ['ROOK_DREAM_GUARD'], "
                                       f"'stdin': sys.stdin.read(), 'cwd': os.getcwd()}}, open({str(pi_trace)!r}, 'w'))\n"
                                       "print('Pi tidied.')\n")
            (pi_bin / "pi").chmod(0o755)
            pi_run = run_cli("dream", env_extra={"PATH": f"{pi_bin}:{os.environ.get('PATH', '')}"})
            assert pi_run.returncode == 0 and "Pi tidied." in pi_run.stdout, (pi_run.stdout, pi_run.stderr)
            tr_pi = json.loads(pi_trace.read_text())
            argv = tr_pi["argv"]
            assert argv[:3] == ["-p", "--no-session", "--no-extensions"] and "--no-mcp" in argv, argv
            assert argv[argv.index("--tools") + 1] == "read,write,edit,find,ls", argv
            assert Path(argv[argv.index("-e") + 1]).is_file() and argv[-4:] == ["--model", "llamacpp", "--thinking", "low"]
            mem_real = os.path.realpath(xdg_data / "rook/memory")
            assert "Pi dream test note." in tr_pi["stdin"] and os.path.realpath(tr_pi["cwd"]) == mem_real, tr_pi["cwd"]
            guard = json.loads(tr_pi["guard"])
            for path, verdict in ((f"{mem_real}/note.md", "allow"), (str(base / "outside.md"), "deny")):
                said = subprocess.run(guard, input=json.dumps({"toolCall": {"name": "write_file", "args": {"path": path}}}),
                                      capture_output=True, text=True, cwd="/")
                assert json.loads(said.stdout)["decision"] == verdict, (path, said.stdout, said.stderr)
            assert not inc_file.exists()

            # 6. Backup rotation keeps only the last 7 backups.
            created = []
            for idx in range(9):
                (xdg_data / "rook/memory/seq.txt").write_text(f"v{idx}\n")
                time.sleep(0.002)
                created.append(memory.backup_memory(keep=7).name)
            kept = sorted(p.name for p in (xdg_data / "rook/memory-backups").iterdir() if p.is_dir())
            assert len(kept) == 7 and kept == sorted(created[-7:]), (kept, created)

            # 6. Lock prevents two dream runs from clashing.
            lock_fd = os.open(xdg_state / "rook/memory-dream.lock", os.O_WRONLY | os.O_CREAT, 0o600)
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked_res = run_cli("dream", env_extra={"ROOK_DREAM_COMMAND": fake_cmd})
                assert locked_res.returncode != 0 and "already running" in locked_res.stderr
                assert not marker.exists()
            finally:
                os.close(lock_fd)
        finally:
            for k, v in saved_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    print("Relay memory: all checks passed.")


def check_shared_memory():
    """Self-check shared memory install, partial-failure recovery, hook merge, note moves, cap, and removal."""
    import shlex
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        base = Path(folder)
        fake_home = base / "home"
        xdg_data = base / "data"
        xdg_state = base / "state"
        xdg_config = base / "config"
        xdg_cache = base / "cache"
        xdg_rt = base / "runtime"
        fake_bin = base / "bin"
        for d in (fake_home, xdg_data, xdg_state, xdg_config, xdg_cache, xdg_rt, fake_bin):
            d.mkdir(mode=0o700, parents=True)

        sys_log = base / "systemctl.log"
        sys_fail = base / "systemctl.fail"
        fake_systemctl = fake_bin / "systemctl"
        fake_systemctl.write_text(
            "#!/bin/sh\n"
            f'echo "$*" >> {shlex.quote(str(sys_log))}\n'
            f'if [ -f {shlex.quote(str(sys_fail))} ]; then echo "systemd unavailable" >&2; exit 1; fi\n'
            "exit 0\n"
        )
        fake_systemctl.chmod(0o755)

        claude_count = base / "claude-count"
        fake_claude = fake_bin / "claude"
        fake_claude.write_text(
            f"#!{sys.executable}\n"
            "import json, pathlib, sys\n"
            f"p = pathlib.Path({str(claude_count)!r})\n"
            "p.write_text(str(int(p.read_text()) + 1 if p.exists() else 1))\n"
            'print(json.dumps({"is_error": False, "result": "PROPOSALS\\n1. ADD\\n   Note: prefs.md", "modelUsage": {}}))\n'
        )
        fake_claude.chmod(0o755)

        def make_env(extra=None):
            env = {k: v for k, v in os.environ.items()
                   if k not in ("T3CODE_THREAD_ID", "ROOK_AGENT", "CLAUDE_CONFIG_DIR", "ROOK_DREAM_COMMAND", "SYSTEMCTL")}
            env.update(
                HOME=str(fake_home),
                XDG_DATA_HOME=str(xdg_data),
                XDG_STATE_HOME=str(xdg_state),
                XDG_CONFIG_HOME=str(xdg_config),
                XDG_CACHE_HOME=str(xdg_cache),
                XDG_RUNTIME_DIR=str(xdg_rt),
                PATH=f"{fake_bin}:{env.get('PATH', '')}",
            )
            env.update(extra or {})
            return env

        def run_cli(*args, extra=None):
            return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True, env=make_env(extra))

        # 1. Refusal when ~/.agents/bin/dream exists and was not installed by Rook (regular file and symlink).
        foreign_dream = fake_home / ".agents/bin/dream"
        foreign_dream.parent.mkdir(parents=True, exist_ok=True)
        foreign_dream.write_text("#!/bin/sh\necho foreign\n")
        refused = run_cli("memory", "install-shared")
        assert refused.returncode != 0, (refused.returncode, refused.stdout, refused.stderr)
        assert len(refused.stderr.strip().splitlines()) == 1 and "not installed by Rook" in refused.stderr, refused.stderr
        assert foreign_dream.read_text() == "#!/bin/sh\necho foreign\n"
        assert not (fake_home / ".agents/hooks/memory-context.sh").exists()
        assert not (fake_home / ".agents/rook-shared-manifest.json").exists()
        foreign_dream.unlink()
        target_outside = base / "sam-dream"
        target_outside.write_text("#!/bin/sh\necho sam\n")
        foreign_dream.symlink_to(target_outside)
        refused_link = run_cli("memory", "install-shared")
        assert refused_link.returncode != 0 and len(refused_link.stderr.strip().splitlines()) == 1, refused_link.stderr
        assert foreign_dream.is_symlink() and not (fake_home / ".agents/hooks/memory-context.sh").exists()
        foreign_dream.unlink()

        # 1b. No systemd (a Mac): one plain refusal, and nothing is written, not even the manifest.
        no_systemd_bin = base / "bin-no-systemd"
        no_systemd_bin.mkdir(mode=0o700)
        before = sorted(str(p) for p in fake_home.rglob("*"))
        no_systemd = run_cli("memory", "install-shared", extra={"PATH": str(no_systemd_bin)})
        assert no_systemd.returncode != 0, (no_systemd.returncode, no_systemd.stdout, no_systemd.stderr)
        assert no_systemd.stderr.strip() == ("Refused: the shared memory tidies its notes each night with a systemd "
                                             "timer, and this computer has no systemd, so Rook keeps its own memory."), \
            no_systemd.stderr
        assert sorted(str(p) for p in fake_home.rglob("*")) == before and not sys_log.exists(), "no-systemd wrote files"

        # 2. Failed install leaves a manifest that remove-shared undoes cleanly (including autoMemoryEnabled), and retry works.
        claude_settings = fake_home / ".claude/settings.json"
        claude_settings.parent.mkdir(parents=True, exist_ok=True)
        real_settings_target = base / "dotfiles-claude-settings.json"
        real_settings_target.write_text(json.dumps({
            "model": "opus",
            "theme": "dark",
            "autoMemoryEnabled": True,
            "hooks": {
                "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "/usr/bin/true"}]}],
                "SessionStart": [{"matcher": "startup", "hooks": [{"type": "command", "command": "echo existing"}]}],
            },
        }, indent=2) + "\n")
        claude_settings.symlink_to(real_settings_target)
        git_ignore = xdg_config / "git/ignore"
        git_ignore.parent.mkdir(parents=True, exist_ok=True)
        git_ignore.write_text("*.swp\n")
        preexisting_file = fake_home / ".agents/prompts/remember.md"
        preexisting_file.parent.mkdir(parents=True, exist_ok=True)
        preexisting_file.write_text("user custom remember prompt\n")

        sys_fail.write_text("1")
        failed_inst = run_cli("memory", "install-shared")
        assert failed_inst.returncode != 0 and "systemd unavailable" in failed_inst.stderr, failed_inst.stderr
        assert (fake_home / ".agents/rook-shared-manifest.json").is_file()
        assert claude_settings.is_symlink() and json.loads(claude_settings.read_text())["autoMemoryEnabled"] is False
        # Undo the partial install while systemctl is still failing.
        undo = run_cli("memory", "remove-shared")
        assert undo.returncode == 0, (undo.returncode, undo.stdout, undo.stderr)
        assert not (fake_home / ".agents/rook-shared-manifest.json").exists()
        assert not (fake_home / ".agents/bin/dream").exists()
        assert not (fake_home / ".agents/hooks/memory-context.sh").exists()
        assert preexisting_file.read_text() == "user custom remember prompt\n"
        assert claude_settings.is_symlink()
        restored_after_fail = json.loads(claude_settings.read_text())
        assert restored_after_fail["autoMemoryEnabled"] is True, restored_after_fail
        assert len(restored_after_fail["hooks"]["SessionStart"]) == 1
        assert git_ignore.read_text().splitlines() == ["*.swp"]
        sys_fail.unlink()

        # Prepare Rook's own notes (including a collision with an existing shared note) and pre-existing shared note.
        rook_shared = fake_home / "Work/.agent-memory"
        rook_shared.mkdir(parents=True, exist_ok=True)
        (rook_shared / "MEMORY.md").write_text("# Memory index\n[[prefs]] - Existing shared prefs.\n[[work-only]] - Work note.\n")
        (rook_shared / "prefs.md").write_text("---\nname: prefs\ndescription: Existing shared prefs.\n---\nExisting.\n")
        (rook_shared / "work-only.md").write_text("---\nname: work-only\ndescription: Work note.\n---\nStay shared.\n")
        own_dir = xdg_data / "rook/memory"
        own_dir.mkdir(mode=0o700, parents=True)
        (own_dir / "MEMORY.md").write_text("# Memory index\n[[prefs]] - Rook preferences.\n- [Tools](tools.md): Tools.\n")
        (own_dir / "prefs.md").write_text("---\nname: prefs\ndescription: Rook preferences.\n---\nLikes Ghostty.\n")
        (own_dir / "tools.md").write_text("---\nname: tools\ndescription: Tools.\n---\nUses ripgrep.\n")
        assert run_cli("remember", "Morning tea is oolong.").returncode == 0

        saved_home = os.environ.get("HOME")
        try:
            os.environ["HOME"] = str(fake_home)
            assert not memory.is_shared()

            # 3. Retry install succeeds; symlinked settings stays a symlink; CLAUDE_BIN recorded; collision renamed in index.
            sys_log.write_text("")
            inst = run_cli("memory", "install-shared")
            assert inst.returncode == 0, (inst.returncode, inst.stdout, inst.stderr)
            assert memory.is_shared()
            assert claude_settings.is_symlink()
            assert preexisting_file.read_text() == "user custom remember prompt\n"
            for rel in ("bin/dream", "bin/remember", "bin/memory-dir", "hooks/memory-context.sh",
                        "prompts/analyzer.md", "prompts/writer.md", "memory.conf"):
                p = fake_home / ".agents" / rel
                assert p.is_file() and not p.is_symlink(), p
            conf_text = (fake_home / ".agents/memory.conf").read_text()
            assert "PROJECT_ROOTS=" in conf_text.splitlines(), conf_text
            assert "DREAM_MAX_RUNS=12" in conf_text, conf_text
            assert f"CLAUDE_BIN={fake_claude}" in conf_text.splitlines(), conf_text
            for forbidden in (*( (saved_home,) if saved_home else () ), *filter(None, os.environ.get("ROOK_CHECK_PRIVATE_NAMES", "").split(","))):
                assert forbidden not in conf_text, (forbidden, conf_text)

            claude_after = json.loads(claude_settings.read_text())
            assert claude_after["model"] == "opus" and claude_after["theme"] == "dark"
            assert claude_after["autoMemoryEnabled"] is False, claude_after
            assert len(claude_after["hooks"]["PreToolUse"]) == 1
            assert len(claude_after["hooks"]["SessionStart"]) == 2
            assert any("memory-context.sh" in h["command"] for e in claude_after["hooks"]["SessionStart"] for h in e["hooks"])
            assert git_ignore.read_text().splitlines() == ["*.swp", ".agent-memory/"]

            svc_text = (xdg_config / "systemd/user/agent-dream.service").read_text()
            tmr_text = (xdg_config / "systemd/user/agent-dream.timer").read_text()
            assert "Nice=10" in svc_text and "Code/dreaming" not in svc_text and "git" not in svc_text
            assert "Persistent=true" in tmr_text
            sys_calls = sys_log.read_text().splitlines()
            assert "--user daemon-reload" in sys_calls and "--user enable --now agent-dream.timer" in sys_calls, sys_calls

            # Collision renamed prefs.md -> prefs-rook.md AND rewrote its index line.
            assert (rook_shared / "prefs.md").read_text().endswith("Existing.\n")
            assert (rook_shared / "prefs-rook.md").is_file() and "Likes Ghostty." in (rook_shared / "prefs-rook.md").read_text()
            assert (rook_shared / "tools.md").is_file() and "Uses ripgrep." in (rook_shared / "tools.md").read_text()
            assert (rook_shared / "rook-incoming.md").is_file() and "oolong" in (rook_shared / "rook-incoming.md").read_text()
            idx_text = (rook_shared / "MEMORY.md").read_text()
            assert "[[prefs-rook]] - Rook preferences." in idx_text and "[[rook-incoming]]" in idx_text, idx_text
            assert not (own_dir / "prefs.md").exists() and not (own_dir / "incoming.jsonl").exists()

            # In shared mode, relay.py remember refuses with one plain line pointing to ~/.agents/bin/remember.
            rem_refuse = run_cli("remember", "Should not write to own incoming.")
            assert rem_refuse.returncode != 0 and len(rem_refuse.stderr.strip().splitlines()) == 1, rem_refuse.stderr
            assert "~/.agents/bin/remember" in rem_refuse.stderr, rem_refuse.stderr
            assert not (own_dir / "incoming.jsonl").exists()

            # Standalone session hook prints instructions to read notes and save with ~/.agents/bin/remember.
            hook_run = subprocess.run(
                ["bash", str(fake_home / ".agents/hooks/memory-context.sh")],
                input=json.dumps({"cwd": str(fake_home / "Work")}),
                text=True, capture_output=True, env=make_env(),
            )
            assert hook_run.returncode == 0 and str(rook_shared) in hook_run.stdout, hook_run.stdout
            assert "Read the notes related to your task before starting." in hook_run.stdout, hook_run.stdout
            assert "~/.agents/bin/remember" in hook_run.stdout, hook_run.stdout

            # 4. Nightly dream: empty-night skip, CLAUDE_BIN without fake_bin on PATH, DREAM_MAX_RUNS clamp (>=2), and cut part progress.
            minimal_path = {"PATH": "/usr/bin:/bin"}
            empty_dream = subprocess.run([str(fake_home / ".agents/bin/dream")], text=True, capture_output=True, env=make_env(minimal_path))
            assert empty_dream.returncode == 0 and "nothing to dream" in empty_dream.stdout, (empty_dream.stdout, empty_dream.stderr)

            # Create a multi-part session (>400 KB) in ProjA plus a session in ProjB, set DREAM_MAX_RUNS=1 (must clamp to 2).
            pmem_a = fake_home / "ProjA/.agent-memory"
            pmem_a.mkdir(parents=True, exist_ok=True)
            (pmem_a / "MEMORY.md").write_text("# Memory index\n[[note]] - Note.\n")
            (pmem_a / "note.md").write_text("---\nname: note\ndescription: Note.\n---\nFact.\n")
            sfile_a = fake_home / ".claude/projects/ProjA/s1.jsonl"
            sfile_a.parent.mkdir(parents=True, exist_ok=True)
            big_lines = [json.dumps({"type": "user", "cwd": str(fake_home / "ProjA"),
                                     "message": {"content": f"line {i} " + ("x" * 70_000)}}) for i in range(10)]
            sfile_a.write_text("\n".join(big_lines) + "\n")
            os.utime(sfile_a, (time.time() - 3600,) * 2)

            pmem_b = fake_home / "ProjB/.agent-memory"
            pmem_b.mkdir(parents=True, exist_ok=True)
            (pmem_b / "MEMORY.md").write_text("# Memory index\n[[note]] - Note.\n")
            (pmem_b / "note.md").write_text("---\nname: note\ndescription: Note.\n---\nFact.\n")
            sfile_b = fake_home / ".claude/projects/ProjB/s1.jsonl"
            sfile_b.parent.mkdir(parents=True, exist_ok=True)
            sfile_b.write_text(json.dumps({"type": "user", "cwd": str(fake_home / "ProjB"),
                                           "message": {"content": "remember this rule " * 200}}) + "\n")
            os.utime(sfile_b, (time.time() - 3600,) * 2)

            (fake_home / ".agents/dream/state.json").unlink(missing_ok=True)
            orig_conf = (fake_home / ".agents/memory.conf").read_text()
            (fake_home / ".agents/memory.conf").write_text(orig_conf.replace("DREAM_MAX_RUNS=12", "DREAM_MAX_RUNS=1"))
            capped_dream = subprocess.run([str(fake_home / ".agents/bin/dream")], text=True, capture_output=True, env=make_env(minimal_path))
            assert capped_dream.returncode == 0, (capped_dream.stdout, capped_dream.stderr)
            assert int(claude_count.read_text()) == 2, claude_count.read_text()
            assert "cut s1.jsonl to 1 of" in capped_dream.stdout, capped_dream.stdout
            dream_state = json.loads((fake_home / ".agents/dream/state.json").read_text())
            assert 0 < dream_state["files"][str(sfile_a)] < len(big_lines), dream_state["files"]
            assert str(sfile_a) in dream_state["retry"] and str(sfile_b) in dream_state["retry"], dream_state["retry"]

            # Multi-block line split across a part boundary re-reads that line, then skips it once if it alone spans every kept part.
            sfile_a.unlink()
            sfile_b.unlink()
            sfile_split = fake_home / ".claude/projects/ProjA/split.jsonl"
            split_lines = [
                json.dumps({"type": "user", "cwd": str(fake_home / "ProjA"),
                            "message": {"content": "line 0 " + ("a" * 10_000)}}),
                json.dumps({"type": "user", "cwd": str(fake_home / "ProjA"),
                            "message": {"content": [{"type": "text", "text": f"blk {i} " + ("b" * 90_000)} for i in range(6)]}}),
                json.dumps({"type": "user", "cwd": str(fake_home / "ProjA"),
                            "message": {"content": "line 2 " + ("c" * 10_000)}}),
            ]
            sfile_split.write_text("\n".join(split_lines) + "\n")
            os.utime(sfile_split, (time.time() - 3600,) * 2)
            (fake_home / ".agents/dream/state.json").unlink(missing_ok=True)
            night1 = subprocess.run([str(fake_home / ".agents/bin/dream")], text=True, capture_output=True, env=make_env(minimal_path))
            assert night1.returncode == 0 and "cut split.jsonl to 1 of" in night1.stdout, (night1.stdout, night1.stderr)
            st1 = json.loads((fake_home / ".agents/dream/state.json").read_text())
            assert st1["files"][str(sfile_split)] == 1 and str(sfile_split) in st1["retry"], st1
            night2 = subprocess.run([str(fake_home / ".agents/bin/dream")], text=True, capture_output=True, env=make_env(minimal_path))
            assert night2.returncode == 0 and "single line in split.jsonl spans more than 1 part(s)" in night2.stdout, (night2.stdout, night2.stderr)
            st2 = json.loads((fake_home / ".agents/dream/state.json").read_text())
            assert st2["files"][str(sfile_split)] == 2 and str(sfile_split) in st2["retry"], st2
            night3 = subprocess.run([str(fake_home / ".agents/bin/dream")], text=True, capture_output=True, env=make_env(minimal_path))
            assert night3.returncode == 0, (night3.stdout, night3.stderr)
            st3 = json.loads((fake_home / ".agents/dream/state.json").read_text())
            assert st3["files"][str(sfile_split)] == 3 and str(sfile_split) not in st3["retry"], st3

            # bin/remember falls back to claude on PATH when CLAUDE_BIN is stale.
            stale_conf = orig_conf.replace(f"CLAUDE_BIN={fake_claude}", "CLAUDE_BIN=/nonexistent/claude")
            (fake_home / ".agents/memory.conf").write_text(stale_conf)
            rem_fallback = subprocess.run(
                [str(fake_home / ".agents/bin/remember"), "stale path fallback fact"],
                cwd=str(fake_home / "ProjA"), text=True, capture_output=True, env=make_env(),
            )
            assert rem_fallback.returncode == 0, (rem_fallback.stdout, rem_fallback.stderr)

            # 5. User-edited memory.conf is preserved on reinstall AND left in place on remove; pre-existing file kept too.
            edited_conf = orig_conf + "# user custom comment\n"
            (fake_home / ".agents/memory.conf").write_text(edited_conf)
            assert run_cli("memory", "install-shared").returncode == 0
            assert (fake_home / ".agents/memory.conf").read_text() == edited_conf

            sys_log.write_text("")
            rem = run_cli("memory", "remove-shared")
            assert rem.returncode == 0, (rem.returncode, rem.stdout, rem.stderr)
            assert not memory.is_shared()
            assert not (fake_home / ".agents/rook-shared-manifest.json").exists()
            for rel in ("bin/dream", "bin/remember", "bin/memory-dir", "hooks/memory-context.sh",
                        "prompts/analyzer.md", "prompts/writer.md"):
                assert not (fake_home / ".agents" / rel).exists(), rel
            # Edited memory.conf and pre-existing remember.md must NOT be deleted.
            assert (fake_home / ".agents/memory.conf").read_text() == edited_conf
            assert preexisting_file.read_text() == "user custom remember prompt\n"
            assert not (xdg_config / "systemd/user/agent-dream.service").exists()
            assert not (xdg_config / "systemd/user/agent-dream.timer").exists()
            rem_calls = sys_log.read_text().splitlines()
            assert "--user disable --now agent-dream.timer" in rem_calls and "--user daemon-reload" in rem_calls, rem_calls

            assert claude_settings.is_symlink()
            claude_final = json.loads(claude_settings.read_text())
            assert claude_final["model"] == "opus" and claude_final["theme"] == "dark"
            assert claude_final["autoMemoryEnabled"] is True, claude_final
            assert len(claude_final["hooks"]["PreToolUse"]) == 1
            assert len(claude_final["hooks"]["SessionStart"]) == 1
            assert claude_final["hooks"]["SessionStart"][0]["hooks"][0]["command"] == "echo existing"
            assert git_ignore.read_text().splitlines() == ["*.swp"]

            # All shared notes stayed in place; ONLY Rook's moved notes copied back to own_dir (not work-only.md).
            assert (rook_shared / "work-only.md").is_file() and (rook_shared / "prefs-rook.md").is_file()
            assert (own_dir / "prefs-rook.md").is_file() and (own_dir / "tools.md").is_file() and (own_dir / "rook-incoming.md").is_file()
            assert not (own_dir / "work-only.md").exists() and not (own_dir / "prefs.md").exists()

            # 6. autoMemoryEnabled absent before install -> removed on remove; each git repo gets its own .agent-memory.
            (fake_home / ".agents/memory.conf").unlink()
            claude_settings.unlink()
            claude_settings.write_text(json.dumps({"model": "opus"}, indent=2) + "\n")
            repo_a, repo_b = fake_home / "Code/repo-a", fake_home / "Code/repo-b"
            for repo in (repo_a, repo_b):
                repo.mkdir(parents=True)
                subprocess.run(["git", "init", "-q", str(repo)], check=True)
            inst2 = run_cli("memory", "install-shared")
            assert inst2.returncode == 0, (inst2.returncode, inst2.stdout, inst2.stderr)
            assert json.loads(claude_settings.read_text())["autoMemoryEnabled"] is False
            for repo in (repo_a, repo_b):
                md_out = subprocess.run([str(fake_home / ".agents/bin/memory-dir"), "--start", str(repo)],
                                        text=True, capture_output=True, env=make_env())
                assert md_out.returncode == 0 and md_out.stdout.strip() == f"{os.path.realpath(str(repo))}/.agent-memory", md_out.stdout
            assert run_cli("memory", "remove-shared").returncode == 0
            assert not (fake_home / ".agents/memory.conf").exists()  # Unedited memory.conf IS removed.
            restored = json.loads(claude_settings.read_text())
            assert restored == {"model": "opus"}, restored
        finally:
            if saved_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = saved_home
    print("Relay shared memory: all checks passed.")


def main():
    if sys.argv[1:] in (["-h"], ["--help"], ["help"]):
        print(_usage())
        return
    if sys.argv[1:] == ["--check"]:
        return check()
    if sys.argv[1:] == ["--check-settings"]:
        return check_settings()
    if sys.argv[1:] == ["--check-clip"]:
        return check_clip()
    if sys.argv[1:] == ["--check-memory"]:
        return check_memory()
    if sys.argv[1:] == ["--check-shared-memory"]:
        return check_shared_memory()
    if len(sys.argv) >= 2 and sys.argv[1] == "remember":
        return remember_command(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "dream":
        return dream_command(sys.argv[2:])
    if sys.argv[1:] == ["--check-herdr"]:
        return check_herdr()
    if sys.argv[1:] == ["--check-plugins"]:
        import plugin_loader  # Its check lives there, so relay.py stays small for every command.
        return plugin_loader.check()
    if len(sys.argv) >= 2 and sys.argv[1] == "herdr":
        return herdr_command(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "pi":
        return pi_command(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "memory":
        return memory_command(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "update":
        return update_command(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "restart":
        return restart_command(sys.argv[2:])
    if len(sys.argv) >= 3 and sys.argv[1:3] == ["reload", "overlay"]:
        return reload_overlay_command(sys.argv[3:])
    if sys.argv[1:] == ["daily-restart"]:
        if os.environ.get("ROOK_AGENT"):
            leave(f"Rook never restarts or reloads itself. Only {OWNER} or the build thread runs this command.")
        return daily_restart()
    if len(sys.argv) >= 2 and sys.argv[1] == "dark":
        return dark_command(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "timer":
        return timer_command(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "project":
        return project_command(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] in ("set", "get", "voices", "fonts", "dusts", "themes"):
        return settings_command(sys.argv[1:])
    if len(sys.argv) >= 2 and sys.argv[1] == "audition":
        return _onboard().audition_command(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "shared-agents":
        return _onboard().shared_agents_command(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "onboard":
        return _onboard().onboard_command(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] in ("watch", "watching"):
        return watch_command(sys.argv[1:])
    if len(sys.argv) >= 2 and sys.argv[1] == "inbox":
        return inbox_command(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "threads":
        return threads_command(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "mailbox":
        return mailbox_command(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "work":
        return work_command(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "ask":
        return ask_command(sys.argv[1:])
    if len(sys.argv) >= 2 and sys.argv[1] == "show":
        return show_command(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "media":
        return media_command(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "forge":
        return forge_command(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "clip":
        return clip_command(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "handoff":
        return handoff_command(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "device":
        return device_command(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "tell":
        tell_args = list(sys.argv[2:])
        urgent = False
        if tell_args[:1] == ["--urgent"]:
            urgent = True
            tell_args = tell_args[1:]
        if len(tell_args) > 1:
            sys.exit("Usage: relay.py tell [--urgent] [TEXT|-]")
        text = tell_args[0] if len(tell_args) == 1 and tell_args[0] != "-" else sys.stdin.read()
        if not (text := text.strip()):
            sys.exit("Give the text as an argument or on stdin.")
        parts = ["tell"]
        if urgent:
            parts.append("--urgent")
        if thread_id := os.environ.get("T3CODE_THREAD_ID", "").strip():
            parts.append(thread_id)
        answer = ask_rook(" ".join(parts), text, wait=30)
        if answer is None:
            sys.exit(f"Rook is not running: nothing answers at {INBOX}.")
        if not answer.get("ok"):
            sys.exit(answer.get("error") or "Rook did not take the message.")
        print("Rook has the message.")
        return
    if len(sys.argv) >= 2 and sys.argv[1] == "note":
        if len(sys.argv) not in (2, 3):
            sys.exit(_usage())
        text = sys.argv[2] if len(sys.argv) == 3 and sys.argv[2] != "-" else sys.stdin.read()
        if not (text := text.strip()):
            sys.exit("Give the text as an argument or on stdin.")
        write_note(text)
        print("Rook reports the note when it next starts, within ten minutes.")
        return
    if len(sys.argv) >= 2 and sys.argv[1] == "mac-access":
        return mac_access_command(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1] == "plugin":
        return plugin_command(sys.argv[2:])
    if len(sys.argv) >= 2 and (handler := _optional_command(sys.argv[1])) is not None:
        return handler(sys.argv[2:])
    if len(sys.argv) >= 2 and (handler := _plugin_command(sys.argv[1])) is not None:
        return handler(sys.argv[2:])
    if len(sys.argv) >= 2 and sys.argv[1].startswith("wow-"):
        sys.exit(f"The {sys.argv[1]} command is not installed in this copy of Rook.")
    sys.exit(_usage())


if __name__ == "__main__":
    main()
