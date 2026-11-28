"""Rook's settings rules, defaults, validation, and catalogues.

Shared by desktop/rook.py and desktop/relay.py so the daemon does not depend on CLI code for
settings logic.
"""
import ast
import difflib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import unicodedata
from urllib.parse import urlparse
import urllib.request

import desk

# The settings Rook may change itself, with the range each number must stay in. Everything else is a
# change to Rook, and goes to the build thread. Pace works from about -0.5 to 0.5: negative is faster.
# Temperature is how freely the voice varies: lower is steadier, higher more varied. Above 1 words start to slip.
CONFIG = desk.config_dir() / "rook/settings.json"
RANGES = {
    "voice_pace": (-0.5, 0.5),
    "voice_volume": (0.0, 1.5),
    "voice_temperature": (0.0, 1.0),
    "smart_turn_threshold": (0.1, 0.95),
}
# User-facing 1 to 100 point scales for the three numeric voice settings (volume also accepts 0 for silent).
# settings.json keeps engine values; relay.py converts at the boundary.
POINT_SETTINGS = {
    "voice_pace": ("speed", 1, "higher is faster"),
    "voice_volume": ("volume", 0, "0 is silent"),
    "voice_temperature": ("expressiveness", 1, "higher is more varied"),
}
POINT_ALIASES = {info[0]: key for key, info in POINT_SETTINGS.items()}
# The main agent Rook runs on, each with the start of its model ids. A change takes effect at Rook's next start.
# Pi runs models of many providers, so its ids have no fixed start, and may name the provider, as provider/id.
AGENTS = {"claude": "claude-", "antigravity": "gemini-", "codex": "gpt-", "pi": ""}
EFFORTS = ("low", "medium", "high", "xhigh", "max")
# How Rook's own agent asks before it acts. full, the default (the owner, 2026-11-25), never asks. inherit starts the agent
# with no mode of Rook's, so the person's own agent settings rule. careful, automatic and full are the onboarding's three plain modes, mapped to each agent's own
# modes in harness.py and agy_harness.py. rook is what Rook forced before it had this setting: Claude Code's auto mode,
# and for Antigravity its default mode with Rook's own allow policy. Only a person who sets it gets it.
PERMISSION_MODES = ("inherit", "careful", "automatic", "full", "rook")
PERMISSION_MODE = "full"
AGENT_SETTINGS = ("agent", "agent_model", "agent_effort", "permission_mode")
# The person Rook works for, by the name Rook calls them, and the pronouns Rook uses for them. Both take effect at
# Rook's next start. Without a name, Rook says PERSON.
OWNER_NAME_RULE = r"[^\W\d_][\w .'-]{0,39}"
OWNER_PRONOUNS = ("he", "she", "they")
OWNER_PRONOUN = "they"
PERSON = "the person"
# The name Rook calls itself, when the person picks another in onboarding. It takes effect at Rook's next start.
ASSISTANT = "Rook"
# The keys that start Rook listening while held, by their input-layer names (evdev's KEY_ names without KEY_). The
# default is the --hold-key flag's. CHORD_KEYS also type, as AltGr does on many layouts: Rook waits a moment before it
# listens, and another key pressed meanwhile means typing, so it does not listen.
TALK_KEY_NAMES = ("RightAlt", "RightCtrl", "RightShift", "RightMeta", "CapsLock", "ScrollLock", "Pause", "Insert",
                  *(f"F{n}" for n in range(13, 25)))
CHORD_KEYS = ("RightAlt",)
HOLD_KEYS = "RightAlt" if desk.IS_MAC else "RightCtrl,F15,F14"  # rook.py's --hold-key default: Right Option on a Mac.
# Where Rook hands coding work: T3 Code (the default), Herdr, Pi, or none yet.
ORCHESTRATORS = ("t3", "herdr", "pi", "none")
ORCHESTRATOR = "t3"
# How the herdr plugin's prompt line names each, for a hand-off that names neither T3 Code nor Herdr.
ORCHESTRATOR_WORDS = {"t3": "T3 Code", "herdr": "Herdr", "pi": "a Pi agent in Herdr",
                      "none": "neither, because no coding tool is chosen, so ask ⟦owner⟧ which one to use"}
# Whether each request carries a screenshot of the focused window. On by default; read at each capture.
SCREENSHOTS = ("on", "off")
# Where diagrams and the answer panel show: "off" draws them in the overlay, "on" in the stage host (stage/host.py),
# which the overlay starts when one shows and falls back from if it cannot.
# Shelved on the desktop (the owner, 2026-11-25: diagrams come from Rook's own particles, no web-style cards), so "on" is
# refused when set and ignored when saved. The stage code stays until they decide its fate.
STAGES = ("off",)
STAGE = "off"
# The monitor Rook lives on alone, on a centred stage, whatever has focus: "off" (Rook follows the focused monitor),
# or a Hyprland connector name, such as DP-2, or text in that monitor's description. Rook follows focus again while
# no connected monitor matches.
OWN_SCREEN = "off"
# When Rook keeps listening for 5 seconds after it speaks: never, after news the owner did not ask for, after a
# question to the owner, or after both. A change applies to the next answer.
LISTEN_AFTERS = ("off", "passive", "questions", "both")
LISTEN_AFTER = "off"
# Smart Turn v3.2 end-of-turn detection during listen_after(): off by default so zero extra RAM/CPU until enabled.
SMART_TURNS = ("off", "on")
SMART_TURN = "off"
# Whether a watched thread that still waits on its subagents may report its new "For Rook:" milestones before it
# finishes. Off by default, so Rook stays quiet until a thread finishes. The watcher reads it at each look.
THREAD_MILESTONES_MODES = ("off", "on")
THREAD_MILESTONES = "off"
# How much of an agent's words Rook reads back, from a T3 thread, a Herdr pane or a Pi session: one limit for all,
# about 1,000 words, so a fix to one is a fix to all.
READBACK_LIMIT = 6000
# The video-recording debug replay (Shift+right-click on the resting loop). A private developer tool: off for everyone,
# turned on only by the owner, and named in no shipped skill.
DEBUG_REPLAY_MODES = ("off", "on")
DEBUG_REPLAY = "off"
# Opt-in live thought and between-tool narration: off by default.
# beats: prompt allows brief plain-English beats between later tool calls.
# thoughts: narrates cleaned English agent_thought_chunk updates in real time.
# both: enables both brief between-tool beats and live thought narration.
SPEAK_THOUGHTS_MODES = ("off", "beats", "thoughts", "both")
SPEAK_THOUGHTS = "off"
# 0.75 avoids coin-flip mid-clause cutoffs while keeping finished turns fast.
SMART_TURN_THRESHOLD = 0.75
# Longest single recording in minutes before Rook stops and sends it. Applies to the next recording.
RECORDING_MINUTES_RANGE = (1, 30)
RECORDING_MINUTES = 10
# Rook's two voices: small is Phonon on this computer, and medium is a remote Qwen3-TTS GPU server.
# No default server address is shipped in code: configure medium_voice_url in settings.json or ROOK_MEDIUM_VOICE_URL.
VOICE_ENGINES = ("small", "medium")
MEDIUM_VOICE_URL = os.environ.get("ROOK_MEDIUM_VOICE_URL", "").strip().rstrip("/")
# The two speech-to-text models a public install offers, by AirType model name. Unset keeps AirType's own choice.
RECOGNISER_MODELS = {"en": "parakeet-unified-en-0.6b-int8", "multi": "parakeet-tdt-0.6b-v3-int8"}
MEDIUM_VOICES = ("late-night-architect", "velvet-wit", "jarvis-poe", "observatory-keeper")  # The first is the default. The server's /health lists its own.
MACHINES_CONFIG = CONFIG.with_name("machines.json")
DEFAULT_THEME_PACK = "devs"
THEMES_DIR = Path(__file__).resolve().parent.parent / "themes"
SETTINGS = ("voice", "voice_engine", "voice_medium", "font", "light_dust", "theme", "stage", "own_screen", "listen_after", "smart_turn",
            "thread_milestones", "debug_replay", "update_check", "speak_thoughts",
            "recording_minutes", *RANGES, *AGENT_SETTINGS,
            "owner_name", "owner_pronouns", "talk_keys", "orchestrator", "projects_folder", "screenshots", "assistant_name",
            "recogniser_model")
CONFIG_SETTINGS = ("medium_voice_url", "github_user", "build_threads", "plugins")
# The text fields a build thread entry may hold when it is an object: its id, and what started it.
BUILD_THREAD_FIELDS = ("thread", "machine", "provider", "model", "effort", "subagents")
KNOWN_SETTINGS_KEYS = frozenset((*SETTINGS, *CONFIG_SETTINGS, "previous"))
DISPLAY_SETTINGS = tuple(POINT_SETTINGS[k][0] if k in POINT_SETTINGS else k for k in SETTINGS)
# The fonts the overlay can show Rook's text in. The overlay owns the file. The first entry is the default.
FONTS = Path(__file__).resolve().with_name("fonts.json")
# The light theme's dust looks live in the overlay's LIGHT_LOOKS, and its LIGHT_LOOK is the default.
OVERLAY = Path(__file__).resolve().with_name("overlay.py")
DATA = desk.data_dir()

# Process cache for light_dusts(), keyed by (path, mtime_ns).
_LIGHT_DUSTS_CACHE = None


def valid_medium_voice_url(value):
    """Return normalized http(s) URL with no embedded credentials, '' if empty, or None if invalid."""
    if not isinstance(value, str):
        return None
    url = value.strip().rstrip("/")
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        return None
    parsed = urlparse(url)
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        return None
    return url


def valid(data):
    """The allowed settings in data with values Rook can use. Anything else is ignored."""
    found = {}
    for key, value in (data.items() if isinstance(data, dict) else ()):
        if key in ("voice", "voice_medium", "font", "light_dust", "theme") and isinstance(value, str) and value.strip():
            found[key] = value.strip()
        elif key == "voice_engine" and value in VOICE_ENGINES:
            found[key] = value
        elif key == "stage" and isinstance(value, str) and value.strip().lower() in STAGES:
            found[key] = value.strip().lower()
        elif key == "own_screen" and isinstance(value, str) and value.strip():
            found[key] = "off" if value.strip().lower() == "off" else " ".join(value.split())
        elif key == "listen_after" and isinstance(value, str) and value.strip().lower() in LISTEN_AFTERS:
            found[key] = value.strip().lower()
        elif key == "smart_turn" and isinstance(value, str) and value.strip().lower() in SMART_TURNS:
            found[key] = value.strip().lower()
        elif key == "thread_milestones" and isinstance(value, str) and value.strip().lower() in THREAD_MILESTONES_MODES:
            found[key] = value.strip().lower()
        elif key == "debug_replay" and isinstance(value, str) and value.strip().lower() in DEBUG_REPLAY_MODES:
            found[key] = value.strip().lower()
        elif key == "update_check" and isinstance(value, str) and value.strip().lower() in ("on", "off"):
            found[key] = value.strip().lower()
        elif key == "speak_thoughts" and isinstance(value, str) and value.strip().lower() in SPEAK_THOUGHTS_MODES:
            found[key] = value.strip().lower()
        elif (key == "recording_minutes" and isinstance(value, int) and not isinstance(value, bool)
              and RECORDING_MINUTES_RANGE[0] <= value <= RECORDING_MINUTES_RANGE[1]):
            found[key] = value
        elif (key in RANGES and isinstance(value, (int, float)) and not isinstance(value, bool)
              and RANGES[key][0] <= value <= RANGES[key][1]):
            found[key] = float(value)
        elif isinstance(value, str) and (key == "agent" and value in AGENTS or key == "agent_effort" and value in EFFORTS
                                         or key == "permission_mode" and value in PERMISSION_MODES
                                         or key == "owner_pronouns" and value in OWNER_PRONOUNS):
            found[key] = value
        elif key in ("owner_name", "assistant_name") and isinstance(value, str) and re.fullmatch(OWNER_NAME_RULE, value.strip()):
            found[key] = value.strip()
        elif key == "talk_keys" and isinstance(value, list) and all(name in TALK_KEY_NAMES for name in value):
            found[key] = list(dict.fromkeys(value))
        elif (key == "orchestrator" and value in ORCHESTRATORS or key == "screenshots" and value in SCREENSHOTS
              or key == "recogniser_model" and value in RECOGNISER_MODELS):
            found[key] = value
        elif key == "projects_folder" and isinstance(value, str) and os.path.isabs(value) and "\n" not in value:
            found[key] = os.path.normpath(value)
        elif (key == "agent_model" and isinstance(value, str) and re.fullmatch(r"[a-z0-9][a-z0-9./-]*", value)
              and value.startswith(AGENTS.get(str(data.get("agent")), AGENTS["claude"]))):
            found[key] = value  # A model of the chosen agent only.
        elif key == "medium_voice_url" and isinstance(value, str):
            url = valid_medium_voice_url(value)
            if url is not None:
                found[key] = url
        elif key == "build_threads" and isinstance(value, dict):
            # Each name maps to a thread id, or to an object that holds the id as "thread", with what started it.
            threads = {}
            for k, v in value.items():
                if not (isinstance(k, str) and re.fullmatch(r"[a-z0-9_-]+", k.strip().lower())):
                    continue
                if isinstance(v, str) and v.strip():
                    threads[k.strip().lower()] = v.strip()
                elif isinstance(v, dict) and isinstance(v.get("thread"), str) and v["thread"].strip():
                    threads[k.strip().lower()] = {f: v[f].strip() for f in BUILD_THREAD_FIELDS
                                                  if isinstance(v.get(f), str) and v[f].strip()}
            found[key] = threads
        elif key == "plugins" and isinstance(value, dict):
            import plugin_loader  # Here: native relay commands never load it unless the file holds plugins.
            found[key] = plugin_loader.valid_settings(value)  # {plugin id: true or false}.
        elif key == "github_user" and isinstance(value, str):
            login = value.strip()
            if not login or re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", login):
                found[key] = login
    return found


def points_to_engine(key, points):
    """Convert integer points on the 0 to 100 scale to the engine value stored in settings.json."""
    if key == "voice_pace":
        return round((50 - points) / 100, 2)
    if key == "voice_volume":
        return round(points * 0.015, 3)
    if key == "voice_temperature":
        return round(points / 100, 2)
    raise KeyError(key)


def engine_to_points(key, value):
    """Convert an engine value from settings.json or a running Rook to integer points."""
    if key == "voice_pace":
        return round(50 - 100 * value)
    if key == "voice_volume":
        return round(value / 0.015)
    if key == "voice_temperature":
        return round(value * 100)
    raise KeyError(key)


def invalid_keys(data):
    """Return sorted names of known settings keys in data whose values are invalid."""
    if not isinstance(data, dict):
        return []
    good = valid(data)
    bad = []
    for key, value in data.items():
        if key == "previous":
            if not isinstance(value, dict):
                bad.append("previous")
            else:
                prev_good = valid(value)
                for pk, pv in value.items():
                    if pk in KNOWN_SETTINGS_KEYS and pk != "previous":
                        if pk not in prev_good or (pk in ("build_threads", "plugins") and isinstance(pv, dict) and len(prev_good[pk]) != len(pv)):
                            bad.append(f"previous.{pk}")
        elif key in KNOWN_SETTINGS_KEYS:
            if key not in good:
                bad.append(key)
            elif key in ("build_threads", "plugins") and isinstance(value, dict) and len(good[key]) != len(value):
                bad.append(key)
    return sorted(set(bad))


def _read_settings_raw():
    """Return (raw dict, file mode or None) from CONFIG. Missing file gives ({}, None).
    An unreadable file, invalid JSON, or non-object raises OSError or ValueError."""
    try:
        st = CONFIG.stat()
        text = CONFIG.read_text()
    except FileNotFoundError:
        return {}, None
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{CONFIG} must contain a JSON object.")
    return data, stat.S_IMODE(st.st_mode)


def read_settings(strict=False, *, validate_current=False):
    """Return (settings, previous values) from the settings file.
    With strict=False, a missing or broken file gives ({}, {}).
    With strict=True, a missing file gives ({}, {}), while an unreadable file, invalid JSON, or non-object raises.
    Invalid values for known keys are omitted unless validate_current is set, which rejects invalid current values."""
    try:
        data, _ = _read_settings_raw()
    except (OSError, ValueError):
        if strict:
            raise
        return {}, {}
    if validate_current and (bad := invalid_keys({key: value for key, value in data.items() if key != "previous"})):
        raise ValueError(f"Invalid settings in {CONFIG}: {', '.join(bad)}.")
    return valid(data), valid(data.get("previous"))


def atomic_write_text(path, text, mode=0o600):
    """Atomically write text to path via a unique sibling temp file, preserving mode.
    When path is a symlink, writes through to its target so the symlink stays intact.
    Refuses to replace an existing target that is not writable (for example mode 0444)."""
    target = path.resolve() if path.is_symlink() else path
    if target.exists():
        st = target.stat()
        if not (st.st_mode & 0o222):
            raise PermissionError(f"{path} is read-only (mode {oct(stat.S_IMODE(st.st_mode))}); refusing to overwrite it.")
        if not os.access(target, os.W_OK):
            raise PermissionError(f"{path} is not writable by this user; refusing to overwrite it.")
    existed = target.parent.exists()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not existed:
        target.parent.chmod(0o700)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as out:
            os.fchmod(out.fileno(), mode)
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_settings(settings, previous, *, updated=None, removed=(), updated_build_threads=None):
    """Replace the settings file atomically, keeping symlink, file mode, unknown keys, and any
    pre-existing invalid values for keys not being updated.
    Refuses to overwrite when the existing file cannot be read/parsed, when the target is not writable,
    or when any key being written carries an invalid value.
    Return a sorted list of pre-existing invalid key names that were left alone."""
    existing, existing_mode = _read_settings_raw()
    bad_out = invalid_keys({**settings, "previous": previous})
    if bad_out:
        raise ValueError(f"Invalid value for {', '.join(bad_out)}.")
    existing_bad = set(invalid_keys(existing))
    removed_set = set(removed)
    if updated is None:
        prev_valid = valid(existing)
        updated_set = {k for k, v in settings.items() if k not in prev_valid or prev_valid[k] != v}
    else:
        updated_set = set(updated)
    mode = existing_mode if existing_mode is not None else 0o600
    unknown = {k: v for k, v in existing.items() if k not in KNOWN_SETTINGS_KEYS}
    payload = {**unknown, **settings}
    left_alone = []
    for key in sorted(existing_bad):
        if key == "previous" or key.startswith("previous."):
            continue
        if key == "build_threads" and updated_build_threads is not None and isinstance(existing.get("build_threads"), dict):
            # Preserve any other invalid entries in build_threads while updating/repairing the named key(s).
            merged_bt = dict(payload.get("build_threads") or {})
            valid_bt = valid({"build_threads": existing["build_threads"]}).get("build_threads", {})
            for bk, bv in existing["build_threads"].items():
                bk_norm = bk.strip().lower() if isinstance(bk, str) else None
                if bk_norm in updated_build_threads:
                    continue
                if bk_norm not in valid_bt or valid_bt.get(bk_norm) != (bv.strip() if isinstance(bv, str) else None):
                    merged_bt[bk] = bv
                    left_alone.append(f"build_threads.{bk}")
            if merged_bt:
                payload["build_threads"] = merged_bt
            continue
        if key not in updated_set and key not in removed_set and key in existing:
            payload[key] = existing[key]
            left_alone.append(key)
    if "previous" in existing and not isinstance(existing["previous"], dict):
        payload["previous"] = existing["previous"]
        left_alone.append("previous")
    else:
        merged_prev = dict(previous)
        existing_prev = existing.get("previous") if isinstance(existing.get("previous"), dict) else {}
        for pk, pv in existing_prev.items():
            if pk not in KNOWN_SETTINGS_KEYS:
                merged_prev.setdefault(pk, pv)
            elif f"previous.{pk}" in existing_bad and pk not in merged_prev:
                merged_prev[pk] = pv
                left_alone.append(f"previous.{pk}")
        payload["previous"] = merged_prev
    atomic_write_text(CONFIG, json.dumps(payload, indent=2) + "\n", mode=mode)
    return sorted(set(left_alone))


def voice_python(data_dir=None):
    """Return the small-voice (Phonon) Python executable: Rook's data folder first, WoWFriend's second, or None."""
    base = DATA if data_dir is None else Path(data_dir)
    # Keep the legacy wowfriend fallback: the owner's machine still holds its Phonon runtime there.
    for rel in ("rook/voice-phonon/bin/python", "wowfriend/voice-phonon/bin/python"):
        candidate = base / rel
        if candidate.exists():
            return candidate
    return None


def voices():
    """Return the English voices of the installed Phonon catalogue, or an error. Rook's speech model is
    English, so the other languages' voices are left out."""
    python = voice_python()
    if python is None:
        return None, f"Could not read the voice catalogue: no local Phonon voice runtime under {DATA / 'rook/voice-phonon'}."
    try:
        listed = subprocess.run([str(python), "-c", "import json, ptts; print(json.dumps(ptts.catalog_voices()))"],
                                capture_output=True, text=True, timeout=120)
        catalogue = json.loads(listed.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        return None, f"Could not read the voice catalogue: {error}"
    return [voice for voice in catalogue if voice.get("language") == "en"], None


def fonts():
    """Return the overlay's fonts from fonts.json, each with a name and a description. A missing or broken
    file gives none, and then Rook keeps its usual look."""
    try:
        data = json.loads(FONTS.read_text())
    except (OSError, ValueError):
        return []
    return [entry for entry in data if isinstance(entry, dict) and isinstance(entry.get("name"), str)
            and entry["name"].strip()] if isinstance(data, list) else []


def font_in_force(saved):
    """Return (font name, source): the saved font while fonts.json still has it, else the default, the first
    entry. With no fonts.json, the name is None and the overlay keeps its usual look."""
    names = [entry["name"] for entry in fonts()]
    if saved.get("font") in names:
        return saved["font"], "settings file"
    return (names[0] if names else None), "default"


def light_dusts():
    """Return (looks, default): the overlay's LIGHT_LOOKS, each with a name and a description, and its LIGHT_LOOK.
    It reads overlay.py's source and never imports it, since the import loads GTK. A missing file gives none."""
    global _LIGHT_DUSTS_CACHE
    try:
        cache_key = (OVERLAY, OVERLAY.stat().st_mtime_ns)
    except OSError:
        return [], None
    if _LIGHT_DUSTS_CACHE is not None and _LIGHT_DUSTS_CACHE[0] == cache_key:
        looks, default = _LIGHT_DUSTS_CACHE[1]
        return [dict(look) for look in looks], default
    try:
        tree = ast.parse(OVERLAY.read_text())
    except (OSError, SyntaxError, ValueError):
        return [], None
    looks, default = [], None
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
            continue
        if node.targets[0].id == "LIGHT_LOOKS" and isinstance(node.value, ast.Dict):
            for key, look in zip(node.value.keys, node.value.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    fields = dict(zip(look.keys, look.values)) if isinstance(look, ast.Dict) else {}
                    text = next((v.value for k, v in fields.items() if isinstance(k, ast.Constant)
                                 and k.value == "description" and isinstance(v, ast.Constant)), None)
                    looks.append({"name": key.value, "description": text})
        elif node.targets[0].id == "LIGHT_LOOK" and isinstance(node.value, ast.Constant):
            default = node.value.value
    _LIGHT_DUSTS_CACHE = (cache_key, (looks, default))
    return [dict(look) for look in looks], default


def light_dust_in_force(saved):
    """Return (look name, source): the saved look while the overlay still has it, else the overlay's default."""
    looks, default = light_dusts()
    names = [look["name"] for look in looks]
    if saved.get("light_dust") in names:
        return saved["light_dust"], "settings file"
    return (default if default in names else None), "default"


def user_themes_dir():
    """Return the owner's own themes folder ($XDG_CONFIG_HOME/rook/themes, default ~/.config/rook/themes)."""
    cfg = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return cfg / "rook" / "themes"


def theme_packs():
    """Return installed presence theme packs from themes/ and ~/.config/rook/themes/ without importing GTK."""
    seen = {}
    for root in (THEMES_DIR, user_themes_dir()):
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if entry.name in seen:
                continue
            manifest = entry / "manifest.json"
            if not manifest.is_file():
                continue
            try:
                data = json.loads(manifest.read_text())
            except (OSError, ValueError):
                continue
            if isinstance(data, dict):
                seen[entry.name] = {
                    "name": entry.name,
                    "title": str(data.get("title") or entry.name),
                    "description": str(data.get("description") or f"{data.get('kind', 'points')} theme pack"),
                    "kind": str(data.get("kind") or "points"),
                }
    return [seen[k] for k in sorted(seen)]


def theme_pack_in_force(saved):
    """Return (pack name, source): the saved theme pack while installed, else DEFAULT_THEME_PACK."""
    names = [pack["name"] for pack in theme_packs()]
    if saved.get("theme") in names:
        return saved["theme"], "settings file"
    return (DEFAULT_THEME_PACK if DEFAULT_THEME_PACK in names else (names[0] if names else DEFAULT_THEME_PACK)), "default"


def stage_in_force(saved):
    """Return (stage, source): "on" or "off" while saved, else the default."""
    if saved.get("stage") in STAGES:
        return saved["stage"], "settings file"
    return STAGE, "default"


def own_screen_in_force(saved):
    """Return (own_screen, source): the saved monitor, or "off", while valid, else the default, off."""
    if "own_screen" in (found := valid({"own_screen": saved.get("own_screen")})):
        return found["own_screen"], "settings file"
    return OWN_SCREEN, "default"


def medium_voice_url(saved=None):
    """Return the configured medium voice server URL, or '' when none is configured."""
    env_url = os.environ.get("ROOK_MEDIUM_VOICE_URL")
    if env_url is not None:
        return env_url.strip().rstrip("/")
    if MEDIUM_VOICE_URL:
        return MEDIUM_VOICE_URL
    if saved is None:
        saved, _ = read_settings()
    return (saved.get("medium_voice_url") or "").strip().rstrip("/")


def build_threads(saved=None):
    """Return configured build thread IDs by short name from settings.json, or {} when none are configured. An entry
    stored as an object (from onboarding) gives its "thread"; build_thread_details() gives the whole object."""
    threads = build_thread_details(saved)
    return {name: entry["thread"] if isinstance(entry, dict) else entry for name, entry in threads.items()}


def build_thread_details(saved=None):
    """Return each configured build thread by short name: a thread id, or an object with "thread" and BUILD_THREAD_FIELDS."""
    if saved is None:
        saved, _ = read_settings()
    threads = saved.get("build_threads")
    return dict(threads) if isinstance(threads, dict) else {}


def medium_voice(path, timeout=3):
    """GET /health, or POST /load or /unload, on the medium voice server. Return its JSON, or None when it fails."""
    base = medium_voice_url()
    if not base:
        return None
    request = urllib.request.Request(base + path, data=None if path == "/health" else b"")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            data = json.loads(answer.read() or b"{}")
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def listen_after_in_force(saved):
    """Return (listen_after mode, source): the saved mode while valid, else the default."""
    if saved.get("listen_after") in LISTEN_AFTERS:
        return saved["listen_after"], "settings file"
    return LISTEN_AFTER, "default"


def smart_turn_in_force(saved):
    """Return (smart_turn mode, source): the saved mode while valid, else the default."""
    if saved.get("smart_turn") in SMART_TURNS:
        return saved["smart_turn"], "settings file"
    return SMART_TURN, "default"


def debug_replay_in_force(saved):
    """Return (debug_replay mode, source): the saved mode while valid, else the default (off)."""
    if saved.get("debug_replay") in DEBUG_REPLAY_MODES:
        return saved["debug_replay"], "settings file"
    return DEBUG_REPLAY, "default"


def thread_milestones_in_force(saved):
    """Return (thread_milestones mode, source): the saved mode while valid, else the default (off)."""
    if saved.get("thread_milestones") in THREAD_MILESTONES_MODES:
        return saved["thread_milestones"], "settings file"
    return THREAD_MILESTONES, "default"


def speak_thoughts_in_force(saved):
    """Return (speak_thoughts mode, source): the saved mode while valid, else the default (off)."""
    if saved.get("speak_thoughts") in SPEAK_THOUGHTS_MODES:
        return saved["speak_thoughts"], "settings file"
    return SPEAK_THOUGHTS, "default"


def smart_turn_threshold_in_force(saved):
    """Return (smart_turn_threshold, source): the saved threshold while valid, else the default."""
    value = saved.get("smart_turn_threshold")
    low, high = RANGES["smart_turn_threshold"]
    if isinstance(value, (int, float)) and not isinstance(value, bool) and low <= value <= high:
        return float(value), "settings file"
    return SMART_TURN_THRESHOLD, "default"


def recording_minutes_in_force(saved):
    """Return (recording_minutes, source): the saved whole number while valid, else the default."""
    value = saved.get("recording_minutes")
    if isinstance(value, int) and not isinstance(value, bool) and RECORDING_MINUTES_RANGE[0] <= value <= RECORDING_MINUTES_RANGE[1]:
        return value, "settings file"
    return RECORDING_MINUTES, "default"


def permission_mode_in_force(saved):
    """Return (permission_mode, source): the saved mode while valid, else the default, full."""
    if saved.get("permission_mode") in PERMISSION_MODES:
        return saved["permission_mode"], "settings file"
    return PERMISSION_MODE, "default"


def owner_name(saved=None):
    """The word Rook calls its owner by: the saved owner_name, else PERSON."""
    if saved is None:
        return owner_values()[0]
    return valid({"owner_name": saved.get("owner_name")}).get("owner_name", PERSON)


def owner_pronouns(saved=None):
    """The pronouns Rook uses for its owner: the saved owner_pronouns, else OWNER_PRONOUN."""
    if saved is None:
        return owner_values()[1]
    return valid({"owner_pronouns": saved.get("owner_pronouns")}).get("owner_pronouns", OWNER_PRONOUN)


_OWNER = []  # (name, pronouns), read once per process, when text is first rendered.


def owner_values():
    """(name, pronouns) from one plain read of the settings file: the two keys only, so nothing else is validated or
    imported. Read once per process; a change takes effect at Rook's next start."""
    if not _OWNER:
        try:
            data = json.loads(CONFIG.read_text())
        except (OSError, ValueError):
            data = {}
        data = data if isinstance(data, dict) else {}
        name = data.get("owner_name")
        name = name.strip() if isinstance(name, str) and re.fullmatch(OWNER_NAME_RULE, name.strip()) else PERSON
        pronouns = data.get("owner_pronouns")
        _OWNER.append((name, pronouns if pronouns in OWNER_PRONOUNS else OWNER_PRONOUN))
    return _OWNER[0]


def start(word):
    """word as the first word of a sentence."""
    return word[:1].upper() + word[1:]


# Owner tokens. Text that names the owner carries them; render() fills them when the text leaves Rook, and leaves
# all other text alone. A two-form phrase holds the he form, then the they form: ⟦verb:he asks|they ask⟧. The he
# form may map only its subject pronoun, for she.
TOKEN = re.compile(r"⟦([^⟦⟧]*)⟧")
OWNER_TOKEN, OWNER_START_TOKEN = "⟦owner⟧", "⟦Owner⟧"
WORDS = {"he": ("he", "she", "they"), "He": ("He", "She", "They"), "him": ("him", "her", "them"),
         "his": ("his", "her", "their"), "His": ("His", "Her", "Their"), "hers": ("his", "hers", "theirs"),
         "himself": ("himself", "herself", "themselves")}
VERB = re.compile(r"verb:([Hh]e) ([^|]+)\|([^|]+)")


def token(phrase, they=None):
    """The token for a phrase written with he: a pronoun alone, such as "his", or a verb phrase with its they form."""
    if they is None:
        if phrase not in WORDS:
            raise ValueError(f"{phrase!r} is not an owner pronoun.")
        return f"⟦{phrase}⟧"
    return f"⟦verb:{phrase}|{they}⟧"


def unknown_tokens(text):
    """The tokens in text that render() does not know."""
    return [m.group(0) for m in TOKEN.finditer(text) if m.group(1) not in WORDS
            and m.group(1) not in ("owner", "Owner", "python") and not VERB.fullmatch(m.group(1))]


def render(text, owner=None, pronouns=None):
    """text with its owner tokens filled, in one pass, so an inserted name is never read again. owner and pronouns
    are the saved ones when None. Text without tokens comes back as it is."""
    if "⟦" not in text:
        return text
    if owner is None or pronouns is None:
        saved_name, saved_pronouns = owner_values()
        owner, pronouns = owner or saved_name, pronouns or saved_pronouns
    case = OWNER_PRONOUNS.index(pronouns)

    def fill(m):
        body = m.group(1)
        if body in ("owner", "Owner"):
            return owner if body == "owner" else start(owner)
        if body == "python":  # Rook's own interpreter, for a skill's commands: /usr/bin/python does not exist on a Mac.
            return desk.python_exe()
        if body in WORDS:
            return WORDS[body][case]
        verb = VERB.fullmatch(body)
        if not verb:
            return m.group(0)
        he, rest, they = verb.groups()
        return (f"{he} {rest}" if pronouns == "he" else f"{WORDS[he][1]} {rest}" if pronouns == "she" else they)
    return TOKEN.sub(fill, text)


def talk_keys_in_force(saved, flag):
    """Return (talk key names, source): the saved list while valid, else the --hold-key flag's comma list."""
    if "talk_keys" in valid({"talk_keys": saved.get("talk_keys")}):
        return list(saved["talk_keys"]), "settings file"
    return [name.strip() for name in (flag or "").split(",") if name.strip()], "--hold-key"


def fold(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c)).strip()


def match_voice(name, catalogue, kind="voice"):
    """Return (name, error) from a catalogue of voices, or of fonts with kind="font". A near miss counts only
    when exactly one entry fits it."""
    names = [voice["name"] for voice in catalogue]
    wanted = fold(name)
    if exact := [n for n in names if fold(n) == wanted]:
        return exact[0], None
    # A word of the name, such as Aldric for Master Aldric, or a close spelling of the name or a word.
    keys = {}
    for n in names:
        for key in (fold(n), *fold(n).replace("-", " ").split()):
            keys.setdefault(key, set()).add(n)
    fits = set().union(*(keys[key] for key in difflib.get_close_matches(wanted, keys, n=5, cutoff=0.8)), keys.get(wanted, set()))
    if len(fits) == 1:
        return fits.pop(), None
    if fits:
        return None, f"{name!r} could be {', '.join(sorted(fits))}. Say which one."
    return None, f"There is no {kind} named {name!r}. Run relay.py {kind}s for the list."
