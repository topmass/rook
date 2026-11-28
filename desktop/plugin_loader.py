"""Rook's plugin loader. A plugin is a folder with a small plugin.json that says what it adds. Discovery reads JSON
and lists files. It never imports or runs plugin code. The module is not named plugins: that is the bundled folder.

Bundled plugins live in <checkout>/plugins/<id>/ and user plugins in $XDG_CONFIG_HOME/rook/plugins/<id>/. Rook
resolves which are active once, at each agent launch, and writes the result to $XDG_RUNTIME_DIR/rook-plugins.json.
A reader takes that snapshot only when it is fresh for this checkout and the settings file as it is now. Otherwise
it resolves from the manifests itself. Nothing here raises: a broken plugin is off, with a named diagnostic.

This module imports only the standard library, so that relay.py's fallback and the checks load it fast. desk loads
only when a path is needed.
"""
import json
import os
from pathlib import Path
import re
import stat
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
BUNDLED = ROOT / "plugins"
SCHEMA = 1
SNAPSHOT_REVISION = 3  # The snapshot's own shape, apart from SCHEMA, which guard_policy.json shares.
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}\Z")
COMMAND = re.compile(r"[a-z][a-z0-9-]{0,39}\Z")
SERVER = re.compile(r"[a-z][a-z0-9]{0,39}\Z")  # No underscore: the guard splits mcp_<server>_<tool> on it.
SLOT = re.compile(r"[a-z][a-z0-9_]{0,39}\Z")
TOOL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
PROGRAM = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,63}\Z")  # A bare program name, never a path.
LABEL = re.compile(r"[a-z][a-z0-9_-]{0,39}\Z")  # An activity label, such as windows.
MANIFEST_MAX = 64 * 1024
SNAPSHOT_MAX = 1024 * 1024
FRAGMENT_MAX = {"bundled": 4000, "user": 4000}  # Characters. Every fragment is paid on every turn by every agent.
SLOT_MAX = 8000  # Characters of all fragments in one slot.
ACTIVATIONS = ("always", "auto", "opt-in")
FIELDS = {"name", "description", "version", "activation", "detect", "skills", "commands", "prompt_slots", "mcp",
          "hook_policy", "host_skills_allow", "hold_command"}
DETECTS = {"platform", "commands_on_path", "path_exists", "desktop_session", "host_skill_present"}
BUILTIN_SERVERS = ("render", "t3", "wow")
_CACHE = None


def _desk():
    import desk  # Only when a path is needed: relay.py has it loaded already.
    return desk


def user_dir():
    return _desk().config_dir() / "rook/plugins"


def settings_path():
    return _desk().config_dir() / "rook/settings.json"


def snapshot_path():
    return _desk().runtime_dir() / "rook-plugins.json"


def _log(text):
    print(f"plugins: {text}", file=sys.stderr)


def valid_settings(value):
    """The usable entries of the plugins setting, {id: true or false}, or None when it is not an object."""
    if not isinstance(value, dict):
        return None
    return {key: on for key, on in value.items() if isinstance(key, str) and ID.match(key) and isinstance(on, bool)}


def _read(path, limit, follow=False):
    """Up to limit + 1 bytes of a regular file. Anything else, such as a FIFO that would block, raises ValueError."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | (0 if follow else os.O_NOFOLLOW))
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError(f"its {Path(path).name} is not a regular file")
        return handle.read(limit + 1)


def _settings_bytes():
    try:
        return _read(settings_path(), SNAPSHOT_MAX, follow=True)
    except (OSError, ValueError):
        return b""


def _choices(raw):
    try:
        data = json.loads(raw) if raw.strip() else {}
    except ValueError:
        return {}
    return (valid_settings(data.get("plugins")) or {}) if isinstance(data, dict) else {}


def _inside(root, rel, what):
    """The real absolute path of rel inside root. A path with .., an absolute path or a link out is refused."""
    if not isinstance(rel, str) or not rel or "\x00" in rel or os.path.isabs(rel) or ".." in Path(rel).parts:
        raise ValueError(f"its {what} {rel!r} must be a plain path inside the plugin folder")
    path = os.path.realpath(os.path.join(root, rel))
    if not path.startswith(root + os.sep):
        raise ValueError(f"its {what} {rel!r} leads outside the plugin folder")
    # Not guarded, on purpose: hard links inside a plugin folder, the owner of the files read, and how many slots a
    # plugin names. An enabled user plugin is trusted local code, and whoever can plant those owns the account already.
    return path


def _strings(value, pattern, what):
    if not isinstance(value, list) or not all(isinstance(item, str) and pattern.match(item) for item in value):
        raise ValueError(f"its {what} must be a list of plain names")
    return list(dict.fromkeys(value))


def _prefixes(value):
    """A checked activity_prefixes object: {program prefix: activity label}."""
    if not isinstance(value, dict) or not all(isinstance(key, str) and PROGRAM.match(key) and isinstance(label, str)
                                              and LABEL.match(label) for key, label in value.items()):
        raise ValueError("its hook policy activity_prefixes must map program names to plain labels")
    return dict(value)


def _read_manifest(folder):
    raw = _read(folder / "plugin.json", MANIFEST_MAX)
    if len(raw) > MANIFEST_MAX:
        raise ValueError(f"its plugin.json is larger than {MANIFEST_MAX // 1024} kilobytes")
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        raise ValueError("its plugin.json is not valid JSON") from None
    if not isinstance(data, dict):
        raise ValueError("its plugin.json is not a JSON object")
    return data


def _manifest(pid, folder, origin, notes):
    """One plugin's checked manifest with every path made absolute, or raise ValueError with the reason."""
    root = os.path.realpath(folder)
    data = _read_manifest(folder)
    for key in sorted(set(data) - FIELDS):
        notes.append(f"The {pid} plugin has a field Rook does not know, {key}. Rook ignores it.")
    for key in ("name", "description"):
        if not isinstance(data.get(key), str) or not data[key].strip() or len(data[key]) > 300:
            raise ValueError(f"its {key} is missing or too long")
    activation = data.get("activation", "opt-in")
    if activation not in ACTIVATIONS:
        raise ValueError(f"its activation must be one of {', '.join(ACTIVATIONS)}")
    detect = data.get("detect", {})
    if not isinstance(detect, dict):
        raise ValueError("its detect must be an object")
    for key in sorted(set(detect) - DETECTS):
        notes.append(f"The {pid} plugin has a detect field Rook does not know, {key}. Rook ignores it.")
    detect = {key: value for key, value in detect.items() if key in DETECTS}
    for key in ("platform", "desktop_session"):
        if key in detect and not isinstance(detect[key], str):
            raise ValueError(f"its detect {key} must be a word")
    if "commands_on_path" in detect:
        _strings(detect["commands_on_path"], PROGRAM, "detect commands_on_path")
    if "path_exists" in detect and not (isinstance(detect["path_exists"], list)
                                        and all(isinstance(item, str) and item for item in detect["path_exists"])):
        raise ValueError("its detect path_exists must be a list of paths")
    if "host_skill_present" in detect and not (isinstance(detect["host_skill_present"], str)
                                               and ID.match(detect["host_skill_present"])):
        raise ValueError("its detect host_skill_present must be a plain skill name")
    plugin = {"id": pid, "origin": origin, "root": root, "name": data["name"], "description": data["description"],
              "activation": activation, "detect": detect, "skills": [], "skill_names": [], "commands": None,
              "prompt_slots": {}, "mcp": [], "hook_policy": {"read_only_commands": [], "relay_commands": [],
                                                                      "activity_prefixes": {}},
              "host_skills_allow": [], "hold_command": None}
    skills = data.get("skills", [])
    if not isinstance(skills, list):
        raise ValueError("its skills must be a list of folders")
    for rel in skills:
        source = _inside(root, rel, "skills folder")
        if not os.path.isdir(source):
            raise ValueError(f"its skills folder {rel!r} is missing")
        plugin["skills"].append(source)
        for name in sorted(os.listdir(source)):
            if os.path.isfile(os.path.join(source, name, "SKILL.md")):
                if not ID.match(name):
                    raise ValueError(f"its skill name {name!r} is not a plain name")
                _inside(root, os.path.join(rel, name, "SKILL.md"), "skill")
                plugin["skill_names"].append(name)
    if "commands" in data:
        commands = data["commands"]
        if not isinstance(commands, dict) or not isinstance(commands.get("module"), str):
            raise ValueError("its commands must name a module and its command names")
        module = _inside(root, commands["module"], "command module")
        if not module.endswith(".py") or not os.path.isfile(module):
            raise ValueError(f"its command module {commands['module']!r} is not a Python file")
        names = _strings(commands.get("names"), COMMAND, "command names")
        if names:
            plugin["commands"] = {"module": module, "names": names}
    slots = data.get("prompt_slots", {})
    if not isinstance(slots, dict):
        raise ValueError("its prompt_slots must be an object")
    for slot, source in slots.items():
        if not SLOT.match(slot):
            raise ValueError(f"its prompt slot name {slot!r} is not a plain name")
        limit = FRAGMENT_MAX[origin]
        if isinstance(source, dict) and set(source) == {"text"} and isinstance(source["text"], str):
            path, text = None, source["text"]
        else:
            path = _inside(root, source, "prompt fragment")
            try:
                raw = _read(path, limit * 4, follow=True)  # UTF-8 takes at most four bytes a character.
                text = raw.decode("utf-8") if len(raw) <= limit * 4 else "x" * (limit + 1)
            except (OSError, ValueError):  # UnicodeDecodeError is a ValueError.
                raise ValueError(f"its prompt fragment {source!r} is not a readable UTF-8 text file") from None
        if len(text) > limit:
            notes.append(f"The {pid} plugin's fragment for the {slot} slot is longer than {limit} characters. "
                         "Rook leaves it out.")
            continue
        plugin["prompt_slots"][slot] = {"path": path, "text": text}
    servers = data.get("mcp", [])
    if not isinstance(servers, list):
        raise ValueError("its mcp must be a list of tool servers")
    for spec in servers:
        if not isinstance(spec, dict) or not isinstance(spec.get("name"), str) or not SERVER.match(spec["name"]):
            raise ValueError("each of its tool servers needs a plain name of letters and digits")
        command = spec.get("command")
        if (not isinstance(command, list) or not command or not all(isinstance(word, str) for word in command)
                or not PROGRAM.match(command[0])):
            raise ValueError(f"its tool server {spec['name']} needs a command that starts with a program name")
        plugin["mcp"].append({
            "name": spec["name"],
            "command": [command[0], *(_inside(root, word, "server file") if word.startswith("./") else word
                                      for word in command[1:])],
            "eager_tools": _strings(spec.get("eager_tools", []), TOOL, "eager tools"),
            "denied_tools": _strings(spec.get("denied_tools", []), TOOL, "denied tools")})
    policy = data.get("hook_policy", {})
    if not isinstance(policy, dict):
        raise ValueError("its hook_policy must be an object")
    plugin["hook_policy"] = {
        "read_only_commands": _strings(policy.get("read_only_commands", []), PROGRAM, "read-only commands"),
        "relay_commands": _strings(policy.get("relay_commands", []), COMMAND, "relay commands"),
        "activity_prefixes": _prefixes(policy.get("activity_prefixes", {}))}
    own = plugin["commands"]["names"] if plugin["commands"] else []
    if stray := [name for name in plugin["hook_policy"]["relay_commands"] if name not in own]:
        raise ValueError(f"its hook policy names relay commands it does not have: {', '.join(stray)}")
    plugin["host_skills_allow"] = _strings(data.get("host_skills_allow", []), ID, "host skills")
    # One of its own relay commands. While it exits 0, such as during a fight in a game, routine updates wait.
    if (hold := data.get("hold_command")) is not None:
        if hold not in own:
            raise ValueError("its hold_command must name one of its own relay commands")
        plugin["hold_command"] = hold
    return plugin


def _reserved():
    """Names Rook owns already, each with its owner: relay.py's own commands, the game's, and the skills."""
    commands, skills = {}, {}
    for path, owner in ((ROOT / "desktop/relay.py", "Rook's own"), (ROOT / "wow/relay_commands.py", "the game part's")):
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        if path.name == "relay.py":
            text = text.split('"""', 2)[1] if text.count('"""') >= 2 else ""  # Its usage text.
        for name in re.findall(r"relay\.py ([a-z][a-z0-9-]*)", text):
            commands.setdefault(name, owner)
    for folder, owner in ((ROOT / "skills", "Rook's own"), (ROOT / "wow/skills", "the game part's"),
                          (_desk().config_dir() / "rook/skills", "your own")):
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for name in names:
            if (folder / name / "SKILL.md").is_file():
                skills.setdefault(name, owner)
    return commands, skills, {name: "Rook's own" for name in BUILTIN_SERVERS}


def _detected(detect):
    import shutil  # Here, as hashlib below: native relay commands import this module and need neither.
    if "platform" in detect and not sys.platform.startswith(detect["platform"]):
        return False
    if any(shutil.which(program) is None for program in detect.get("commands_on_path", ())):
        return False
    if not all(os.path.exists(os.path.expanduser(path)) for path in detect.get("path_exists", ())):
        return False
    if "desktop_session" in detect:
        sessions = ":".join(os.environ.get(key, "") for key in ("XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP"))
        if detect["desktop_session"].lower() not in sessions.lower().split(":"):
            return False
    if "host_skill_present" in detect:  # Found in any one agent's folder is enough.
        name = detect["host_skill_present"]
        if not any((folder / name / "SKILL.md").is_file() for folder in host_skill_dirs().values()):
            return False
    return True


def host_skill_dirs():
    """The four agents' own skills folders, where a host skill such as a desktop's lives. The one spelling of them:
    the harnesses derive their folders from it."""
    home = Path.home()
    return {"agents": home / ".agents/skills",
            "claude": Path(os.environ.get("CLAUDE_CONFIG_DIR") or home / ".claude") / "skills",
            "gemini": home / ".gemini/config/skills",
            "codex": Path(os.environ.get("CODEX_HOME") or home / ".codex") / "skills"}


def resolve(raw=None):
    """Read every manifest and decide which plugins are active, as the snapshot's document (without the file)."""
    import hashlib
    raw = _settings_bytes() if raw is None else raw
    notes, found = [], []
    for origin, base in (("bundled", BUNDLED), ("user", user_dir())):
        try:
            names = sorted(os.listdir(base))
        except FileNotFoundError:
            continue
        except OSError as error:
            notes.append(f"Rook could not read the plugins folder {base}: {error.strerror}.")
            continue
        for name in names:
            folder = base / name
            if name.startswith(".") or not folder.is_dir():
                continue
            if not ID.match(name):
                notes.append(f"Rook skips the plugin folder {name!r}: a plugin's folder name must be a plain name.")
                continue
            if origin == "user" and folder.is_symlink():
                notes.append(f"The {name} plugin is off: its folder is a link, and Rook takes only real folders.")
                continue
            if not os.path.lexists(folder / "plugin.json"):
                notes.append(f"The {name} plugin is off: its folder has no plugin.json.")
                continue
            try:
                found.append(_manifest(name, folder, origin, notes))
            except (OSError, ValueError) as error:
                reason = error.strerror if isinstance(error, OSError) and error.strerror else str(error)
                notes.append(f"The {name} plugin is off: {reason}.")
    commands, skills, servers = _reserved()
    claims = {"plugin": {}, "command": commands, "skill": skills, "tool server": servers}
    plugins = []
    for plugin in found:
        if both := sorted(set(plugin["skill_names"]) & set(plugin["host_skills_allow"])):
            notes.append(f"The {plugin['id']} {plugin['origin']} plugin is off: it both ships and lets through the "
                         f"skill {both[0]}.")
            continue
        # A host skill each agent passes through beside Rook's skills is a skill name like any other.
        hosted = [("skill", name) for name in plugin["host_skills_allow"]]
        wanted = [("plugin", plugin["id"]), *(("command", name) for name in (plugin["commands"] or {}).get("names", ())),
                  *(("skill", name) for name in plugin["skill_names"]), *hosted,
                  *(("tool server", spec["name"]) for spec in plugin["mcp"])]
        if clash := next(((kind, name) for kind, name in wanted if name in claims[kind]), None):
            kind, name = clash
            notes.append(f"The {plugin['id']} {plugin['origin']} plugin is off: the {kind} {name} is already "
                         f"{claims[kind][name]}.")
            continue
        for kind, name in wanted:
            claims[kind][name] = "a shared host skill's" if (kind, name) in hosted else f"the {plugin['id']} plugin's"
        plugins.append(plugin)
    choices = _choices(raw)
    totals = {}
    for plugin in plugins:
        choice = choices.get(plugin["id"])
        if choice is False:
            plugin["active"], plugin["reason"] = False, "turned off in settings"
        elif not _detected(plugin["detect"]):
            plugin["active"], plugin["reason"] = False, "its setup was not found on this computer"
        elif choice is True:
            plugin["active"], plugin["reason"] = True, "turned on in settings"
        elif plugin["origin"] == "user":
            plugin["active"], plugin["reason"] = False, "a plugin you add stays off until you turn it on"
        elif plugin["activation"] == "opt-in":
            plugin["active"], plugin["reason"] = False, "off by default"
        else:
            plugin["active"], plugin["reason"] = True, ("on by default" if plugin["activation"] == "always"
                                                        else "on, because it found its setup")
        if not plugin["active"]:
            continue
        for slot, fragment in list(plugin["prompt_slots"].items()):
            if totals.get(slot, 0) + len(fragment["text"]) > SLOT_MAX:
                notes.append(f"The {plugin['id']} plugin's fragment for the {slot} slot would take that slot past "
                             f"{SLOT_MAX} characters. Rook leaves it out.")
                del plugin["prompt_slots"][slot]
            else:
                totals[slot] = totals.get(slot, 0) + len(fragment["text"])
    keep = ("id", "origin", "root", "skills", "prompt_slots", "mcp", "hook_policy", "host_skills_allow", "hold_command")
    return {
        "schema_version": SCHEMA, "snapshot_revision": SNAPSHOT_REVISION, "checkout_root": str(ROOT), "settings_sha256": hashlib.sha256(raw).hexdigest(),
        "pid": os.getpid(), "written_at": time.time(),
        "plugins": [{key: plugin[key] for key in ("id", "origin", "root", "description", "active", "reason")}
                    for plugin in plugins],
        "active_plugins": [{key: plugin[key] for key in keep} for plugin in plugins if plugin["active"]],
        # A bundled plugin's commands stay installed while it is off, as the game's do. A user plugin's code runs
        # only once it is turned on.
        "installed_commands": {name: {"plugin": plugin["id"], "module": plugin["commands"]["module"]}
                               for plugin in plugins if plugin["commands"]
                               and (plugin["origin"] == "bundled" or plugin["active"])
                               for name in plugin["commands"]["names"]},
        "diagnostics": notes}


def _fresh(doc, sha):
    """Whether a snapshot document is whole, for this checkout and these settings, and names only paths inside
    each plugin's own folder under the two plugin folders. A missing field or a wrong type makes it stale."""
    try:
        return _whole(doc, sha)
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def _whole(doc, sha):
    if (not isinstance(doc, dict) or doc.get("schema_version") != SCHEMA
            or doc.get("snapshot_revision") != SNAPSHOT_REVISION or doc.get("checkout_root") != str(ROOT)
            or doc.get("settings_sha256") != sha or not isinstance(doc.get("diagnostics"), list)):
        return False
    bases = {"bundled": os.path.realpath(BUNDLED), "user": os.path.realpath(user_dir())}
    roots = {}
    for plugin in doc["plugins"]:
        root = plugin["root"]
        if (not isinstance(root, str) or os.path.dirname(root) != bases[plugin["origin"]]
                or os.path.basename(root) != plugin["id"] or not isinstance(plugin["active"], bool)):
            return False
        roots[plugin["id"]] = root

    def inside(pid, path):
        return isinstance(path, str) and os.path.realpath(path).startswith(roots[pid] + os.sep)
    for plugin in doc["active_plugins"]:
        pid = plugin["id"]
        if plugin["root"] != roots[pid] or not all(inside(pid, path) for path in plugin["skills"]):
            return False
        for fragment in plugin["prompt_slots"].values():
            if not isinstance(fragment["text"], str) or fragment["path"] is not None and not inside(pid, fragment["path"]):
                return False
        for spec in plugin["mcp"]:
            if not all(isinstance(word, str) and (not word.startswith("/") or inside(pid, word))
                       for word in spec["command"]) or not SERVER.match(spec["name"]):
                return False
            _strings(spec["eager_tools"], TOOL, "eager tools")
            _strings(spec["denied_tools"], TOOL, "denied tools")
        _strings(plugin["hook_policy"]["read_only_commands"], PROGRAM, "read-only commands")
        _strings(plugin["hook_policy"]["relay_commands"], COMMAND, "relay commands")
        _prefixes(plugin["hook_policy"]["activity_prefixes"])
        _strings(plugin["host_skills_allow"], ID, "host skills")
        if plugin["hold_command"] is not None and not COMMAND.match(plugin["hold_command"]):
            return False
    origins = {plugin["id"]: plugin["origin"] for plugin in doc["plugins"]}
    active = {plugin["id"] for plugin in doc["active_plugins"]}
    return all(COMMAND.match(name) and inside(entry["plugin"], entry["module"])  # A user plugin's only when active.
               and (entry["plugin"] in active or origins[entry["plugin"]] == "bundled")
               for name, entry in doc["installed_commands"].items())


def _snapshot(sha):
    """The snapshot on disk when it is fresh, else None. A corrupt or foreign one means: resolve yourself."""
    try:
        doc = json.loads(_read(snapshot_path(), SNAPSHOT_MAX))
        return doc if _fresh(doc, sha) else None
    except Exception:  # Missing, truncated, foreign, or of another shape.
        return None


def publish():
    """Resolve from the manifests, write the snapshot atomically, and keep it for this process. Never raises."""
    global _CACHE
    try:
        doc = resolve()
    except Exception as error:
        _log(f"resolution failed: {error!r}")
        _CACHE = _empty(f"Rook could not resolve its plugins: {error!r}.")
        return _CACHE
    path = snapshot_path()
    temp = path.with_name(f".{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as out:
            json.dump(doc, out)
        os.replace(temp, path)
    except OSError as error:
        _log(f"could not write {path}: {error.strerror or error!r}")
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
    _CACHE = doc
    return doc


def disable(note):
    """Run this process with no plugins, after one log line: for a launch whose resolution failed or took too long."""
    global _CACHE
    _log(note)
    _CACHE = _empty(note)


def _empty(note):
    return {"failed": True, "plugins": [], "active_plugins": [], "installed_commands": {}, "diagnostics": [note]}


def activation():
    """The activation: the snapshot when fresh, else resolved from the manifests. Kept for this process."""
    global _CACHE
    if _CACHE is None:
        try:
            import hashlib
            raw = _settings_bytes()
            _CACHE = _snapshot(hashlib.sha256(raw).hexdigest()) or resolve(raw)
        except Exception as error:
            _log(f"resolution failed: {error!r}")
            _CACHE = _empty(f"Rook could not resolve its plugins: {error!r}.")
    return _CACHE


def slot_entries(slot):
    """(plugin id, exact text) for each active plugin with a fragment for this slot: bundled first, then user
    plugins, each by id."""
    return [(plugin["id"], plugin["prompt_slots"][slot]["text"]) for plugin in activation()["active_plugins"]
            if slot in plugin["prompt_slots"]]


def fragments(slot):
    """Every active plugin's fragment for this slot, joined as they are. The empty string when there is none."""
    return "".join(text for _, text in slot_entries(slot))


def hold_commands():
    """The hold commands of active plugins. While one exits 0, routine updates wait."""
    return [plugin["hold_command"] for plugin in activation()["active_plugins"] if plugin["hold_command"]]


def command(name):
    """(plugin id, absolute module path) of an installed plugin command, active or not, or None."""
    entry = activation()["installed_commands"].get(name)
    return (entry["plugin"], entry["module"]) if entry else None


def skill_dirs():
    """(bundled, user): the absolute skills folders of active plugins. Each folder holds <name>/SKILL.md."""
    active = activation()["active_plugins"]
    return (tuple(path for plugin in active if plugin["origin"] == "bundled" for path in plugin["skills"]),
            tuple(path for plugin in active if plugin["origin"] == "user" for path in plugin["skills"]))


def servers():
    """The active plugins' tool servers: name, command (program first), eager_tools and denied_tools."""
    return [spec for plugin in activation()["active_plugins"] for spec in plugin["mcp"]]


def server_configs(specs=None):
    """Launch configs for the active plugins' tool servers whose program is installed. A server whose program is
    missing is left out, with one log line."""
    import shutil
    configs = {}
    for spec in servers() if specs is None else specs:
        if program := shutil.which(spec["command"][0]):
            configs[spec["name"]] = {"command": program, "args": spec["command"][1:]}
        else:
            _log(f"the {spec['name']} tool server is left out: its program {spec['command'][0]} is not installed.")
    return configs


def guard_policy():
    """The data the Antigravity guard reads: active tool servers with their denied tools, relay commands that pass
    without a card, and programs that only read when run with no arguments."""
    active = activation()["active_plugins"]
    return {"schema_version": SCHEMA,
            "servers": {spec["name"]: {"denied_tools": spec["denied_tools"]} for spec in servers()},
            "relay_commands": [name for plugin in active for name in plugin["hook_policy"]["relay_commands"]],
            "read_only_commands": [name for plugin in active for name in plugin["hook_policy"]["read_only_commands"]]}


def activity_prefixes(cached_only=False):
    """{program prefix: activity label} from the active plugins. The first plugin to name a prefix wins. With
    cached_only, only this process's activation in memory: empty before one, and never a file read."""
    if cached_only and _CACHE is None:
        return {}
    merged = {}
    for plugin in activation()["active_plugins"]:
        for prefix, label in plugin["hook_policy"]["activity_prefixes"].items():
            merged.setdefault(prefix, label)
    return merged


def host_skills_allow():
    """The host skills that the active plugins let each agent see beside Rook's own, in plugin order."""
    return tuple(dict.fromkeys(name for plugin in activation()["active_plugins"] for name in plugin["host_skills_allow"]))


def reset_cache():
    """Forget this process's activation, so the next reader resolves again. For checks that change the setup."""
    global _CACHE
    _CACHE = None


def diagnostics():
    return list(activation()["diagnostics"])


# What the three agents get from Rook's plugins, printed as JSON by a child with scratch folders.
PLUGIN_SURFACE = r'''
import json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import agy_harness, antigravity_home, codex_harness, harness, plugin_loader
root, run = Path(sys.argv[1]).parent, Path(os.environ["XDG_RUNTIME_DIR"])
plugin_loader.publish()
servers = plugin_loader.server_configs()
gone = plugin_loader.server_configs([{"name": "gone", "command": ["no-such-program-here"]}])
def listed(folder, prefix):
    return {f"{prefix}{entry.name}": (entry / "SKILL.md").read_text() for entry in sorted(Path(folder).iterdir())
            if (entry / "SKILL.md").is_file()} if Path(folder).is_dir() else {}
argv = harness.Claude().command("p", servers, "s", root / "plugin", ())
dirs = [argv[at + 1] for at, word in enumerate(argv) if word == "--plugin-dir"]
claude = {key: text for at, folder in enumerate(dirs) for key, text in listed(Path(folder) / "skills", ("rook:", "rook-user:")[at]).items()}
home = antigravity_home.build()
agy = listed(home / "config/plugins/rook/skills", "")  # agy lists Rook's skills by bare name, as its live record shows.
for entry in json.loads((home / "config/skills.json").read_text())["entries"]:
    agy.update({key: text for key, text in listed(entry["path"], "user:").items()
                if "include_only" not in entry or key[5:] in entry["include_only"]})
codex_home = codex_harness.build_home(servers, home=run / "codex", user_home=run / "no-codex")
codex_harness.plugin_user_skills = lambda: (run / "skills-gone",)  # A skills folder removed after discovery.
codex_harness.build_home(servers, home=run / "codex-gone", user_home=run / "no-codex")
agy_harness.PERMISSIONS = "careful"  # Rook's own default is full, which allows all; the card shows otherwise.
relay = f"/usr/bin/python {root}/desktop/relay.py"
print(json.dumps({"claude": claude, "antigravity": agy, "codex": listed(codex_home / "skills", ""),
                  "claude_denied": [word for word in argv if word.startswith("mcp__")],
                  "codex_mcp": (codex_home / "config.toml").read_text().count("[mcp_servers"),
                  "setup": harness.Claude().setup({spec["name"]: spec["eager_tools"] for spec in plugin_loader.servers()}, []),
                  "guard_policy": json.loads((home / "config/guard_policy.json").read_text())
                  if (home / "config/guard_policy.json").exists() else None,
                  "gone": gone, "fragment": plugin_loader.fragments("fixture_slot"), "entries": plugin_loader.slot_entries("fixture_slot"),
                  "decide": [agy_harness.decide(*ask, ()) for ask in (
                      ("Bash", {"command": f"{relay} fixture-hello"}), ("Bash", {"command": f"{relay} get"}),
                      ("Bash", {"command": "fixture-read"}), ("Bash", {"command": "fixture-read --all"}),
                      ("Bash", {"command": "git status"}), ("Bash", {"command": "git"}),
                      ("mcp__fixture__ping", {}), ("mcp__fixture__secret", {}), ("mcp__render__show_diagram", {}))]}))
'''
# What the three agents get from the bundled Omarchy plugin, printed as JSON by a child with scratch folders.
OMARCHY_SURFACE = r'''
import json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import antigravity_home, codex_harness, harness, plugin_loader
home, run = Path.home(), Path(os.environ["XDG_RUNTIME_DIR"])
plugin_loader.publish()
codex = codex_harness.build_home({}, home=run / "codex-omarchy", user_home=run / "no-codex", agents_dir=home / ".agents",
                                 user_rook_skills=run / "no-rook-skills", wow=False)
print(json.dumps({"host": plugin_loader.host_skills_allow(), "prefixes": plugin_loader.activity_prefixes(),
                  "read_only": plugin_loader.guard_policy()["read_only_commands"],
                  "slots": {slot: plugin_loader.fragments(slot)
                            for slot in ("identity_desktop", "desktop_control", "desktop_confirmations")},
                  "claude": harness.claude_settings_data()["skillOverrides"],
                  "antigravity": antigravity_home.skills_entries(run / "rook-skills", (home / ".agents/skills",), ()),
                  "codex": codex_harness.disabled_host_skills(home / ".agents"),
                  "codex_toml": "omarchy/SKILL.md" in (codex / "config.toml").read_text(),
                  "dirs_match": plugin_loader.host_skill_dirs() == {  # One spelling: the harnesses never drift from it.
                      "agents": antigravity_home.AGENTS / "skills", "claude": harness.claude_config_dir() / "skills",
                      "gemini": antigravity_home.GEMINI_SKILLS, "codex": codex_harness.user_codex_home() / "skills"}
                  and codex_harness.AGENTS == antigravity_home.AGENTS
                  and codex_harness.GEMINI_SKILLS == antigravity_home.GEMINI_SKILLS}))
'''
FIXTURE_FILES = {
    "plugin.json": json.dumps({
        "name": "Fixture", "description": "A plugin written without editing Rook.", "skills": ["skills"],
        "commands": {"module": "relay_commands.py", "names": ["fixture-hello"]},
        "prompt_slots": {"fixture_slot": "prompts/slot.md"},
        "mcp": [{"name": "fixture", "command": ["true", "./server.py"], "eager_tools": ["ping"],
                 "denied_tools": ["secret"]}],
        "hook_policy": {"relay_commands": ["fixture-hello"], "read_only_commands": ["fixture-read", "git"]},
        "hold_command": "fixture-hello"}),
    "relay_commands.py": 'HELP = """relay.py fixture-hello       Print the fixture\'s line."""\n'
                         'COMMANDS = {"fixture-hello": lambda argv: print("The fixture plugin says hello.")}\n',
    "skills/fixture-skill/SKILL.md": "---\nname: fixture-skill\ndescription: Say hello through the fixture.\n---\n\n"
                                     "Run ⟦python⟧ ${CLAUDE_PLUGIN_ROOT}/../desktop/relay.py fixture-hello for ⟦owner⟧.\n",
    "prompts/slot.md": "Fixture line one.\n  Two spaces, a tab\there, no final newline",
    "server.py": "",
}


def check():
    """Self-check the plugin machinery with a fixture user plugin, broken manifests, stale snapshots and a broken
    guard policy, each child in scratch folders."""
    import shutil
    import subprocess
    import tempfile
    root = ROOT
    SCRIPT = Path(__file__).resolve().with_name("relay.py")
    # With --wow the checkout root comes first on sys.path. A top-level module file, or a folder with __init__.py,
    # would then shadow the desktop module of its name. A folder without one, such as memory/, does not.
    modules = {path.stem for path in (root / "desktop").glob("*.py")}
    clashes = [f"{path} shadows desktop/{path.stem}.py" for path in sorted(root.iterdir())
               if path.stem in modules and (path.suffix == ".py" or (path / "__init__.py").is_file())]
    assert not clashes, clashes
    base = Path(tempfile.mkdtemp(prefix="rook-plugins-"))
    env = {"PATH": f"{base / 'bin'}:{base / 'sys-bin'}", "HOME": str(base / "home"), "LANG": "C.UTF-8",
           **{f"XDG_{name}_HOME": str(base / name.lower()) for name in ("STATE", "CONFIG", "DATA", "CACHE")},
           "XDG_RUNTIME_DIR": str(base / "run")}
    (base / "run").mkdir(mode=0o700)
    (base / "bin").mkdir()
    (base / "sys-bin").mkdir()  # Only the system programs the checks run, so no host desktop's programs leak in.
    for program in ("true", "sh", "env", "python3", "python"):
        if found := shutil.which(program, path="/usr/bin:/bin"):
            (base / "sys-bin" / program).symlink_to(found)
    users = base / "config/rook/plugins"
    snapshot, policy = base / "run/rook-plugins.json", base / "run/rook-antigravity/config/guard_policy.json"

    def relay(*args):
        done = subprocess.run([sys.executable, str(SCRIPT), *args], env=env, capture_output=True, text=True,
                              timeout=60)
        return done.returncode, done.stdout + done.stderr

    def omarchy_surface():
        done = subprocess.run([sys.executable, "-c", OMARCHY_SURFACE, str(SCRIPT.parent)], env=env,
                              capture_output=True, text=True, timeout=120)
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    def omarchy_line():
        return next(line for line in relay("plugin", "list")[1].splitlines() if line.startswith("omarchy: "))

    def surface():  # Its stderr must hold the one line for the tool server whose program is missing.
        done = subprocess.run([sys.executable, "-c", PLUGIN_SURFACE, str(SCRIPT.parent)], env=env,
                              capture_output=True, text=True, timeout=120)
        assert done.returncode == 0 and "the gone tool server is left out" in done.stderr, done.stderr
        return json.loads(done.stdout)

    def guard(tool, args=None):
        call = {"toolCall": {"name": tool, "args": args or {}}, "workspacePaths": ["/tmp"]}
        done = subprocess.run(["/usr/bin/python3", "-I", str(SCRIPT.with_name("antigravity_home.py")), "guard"],
                              input=json.dumps(call), env=env, cwd="/tmp", capture_output=True, text=True, timeout=60)
        return json.loads(done.stdout)["decision"]

    def write(folder, files):
        for rel, text in files.items():
            (folder / rel).parent.mkdir(parents=True, exist_ok=True)
            (folder / rel).write_text(text) if isinstance(text, str) else (folder / rel).write_bytes(text)
    try:
        bare = surface()
        bare_help = relay("--help")[1]
        bare_guard = [guard("mcp_fixture_ping"), guard("run_command", {"CommandLine": "echo hi"})]
        assert bare_guard == ["deny", "allow"], bare_guard
        write(users / "fixture", FIXTURE_FILES)
        omarchy_off = ("omarchy: off, its setup was not found on this computer. Omarchy desktop control: omarchy "
                       "skill routing, browser link launcher, terminal folder lookup, and desktop confirmations.")
        herdr_off = ("herdr: off, its setup was not found on this computer. Herdr hand-offs: coding agents in Herdr's "
                     "terminal panes, here and on saved Herdr machines, and Pi's saved sessions.")
        obsidian_off = ("obsidian: off, off by default. Append explicitly dictated notes to a dedicated folder in an "
                        "Obsidian vault.")
        bundled_off = f"{herdr_off}\n{obsidian_off}\n{omarchy_off}\n"
        assert relay("plugin", "list") == (0, bundled_off + "fixture: off, a plugin you add stays off until you "
                                              "turn it on. A plugin written without editing Rook.\n")
        assert surface() == bare and relay("--help")[1] == bare_help
        assert relay("fixture-hello")[0] != 0
        assert relay("plugin", "enable", "fixture")[0] == 0
        assert relay("fixture-hello") == (0, "The fixture plugin says hello.\n")
        assert "relay.py fixture-hello       Print the fixture's line." in relay("--help")[1]
        on = surface()
        for agent, key in (("claude", "rook-user:fixture-skill"), ("antigravity", "user:fixture-skill"),
                           ("codex", "fixture-skill")):
            # Rendered as Rook's own skills are, so the plugin needs no path to Rook of its own.
            python = "/usr/bin/python" if os.path.exists("/usr/bin/python") else sys.executable
            assert on[agent][key] == FIXTURE_FILES["skills/fixture-skill/SKILL.md"].replace(
                "⟦python⟧ ${CLAUDE_PLUGIN_ROOT}", f"{python} {root}/plugin").replace("⟦owner⟧", "the person"), agent
            assert {k: v for k, v in on[agent].items() if k != key} == bare[agent], agent
        assert on["fragment"] == FIXTURE_FILES["prompts/slot.md"] and on["entries"] == [["fixture", on["fragment"]]]
        # User plugin prompt fragments allow up to 4000 characters (matching bundled plugins).
        ok_frag = "U" * 2500
        (users / "fixture/prompts/slot.md").write_text(ok_frag)
        assert surface()["fragment"] == ok_frag
        assert relay("plugin", "check")[0] == 0
        (users / "fixture/prompts/slot.md").write_text(FIXTURE_FILES["prompts/slot.md"])
        assert on["claude_denied"] == ["mcp__fixture__secret"] and on["codex_mcp"] == bare["codex_mcp"] + 1
        assert "mcp__fixture__ping" in on["setup"] and "mcp__fixture__ping" not in bare["setup"]
        assert on["guard_policy"] == {"schema_version": 1, "servers": {"fixture": {"denied_tools": ["secret"]}},
                                      "relay_commands": ["fixture-hello"], "read_only_commands": ["fixture-read", "git"]}
        assert bare["gone"] == {} and on["codex_mcp"] == bare["codex_mcp"] + 1
        # A plugin's read-only entry only adds: git status stays allowed, and bare git keeps its built-in answer.
        assert bare["decide"] == ["ask", "allow", "ask", "ask", "allow", "ask", "deny", "deny", "allow"], bare["decide"]
        assert on["decide"] == ["allow", "allow", "allow", "ask", "allow", "ask", "allow", "deny", "allow"], on["decide"]
        assert [guard("mcp_fixture_ping"), guard("mcp_fixture_secret"),
                guard("call_mcp_tool", {"ServerName": "fixture", "ToolName": "secret"})] == ["allow", "deny", "deny"]
        good_policy = policy.read_bytes()
        for broken in (None, "fifo", b"{", b'{"schema_version": 2, "servers": {"fixture": {"denied_tools": []}}, '
                                   b'"relay_commands": [], "read_only_commands": []}',
                       good_policy.replace(b'"fixture"', b'"t3"')):
            policy.unlink(missing_ok=True)
            if broken == "fifo":  # Must not hang the hook.
                os.mkfifo(policy)
            elif broken is not None:
                policy.write_bytes(broken)
            assert [guard("mcp_fixture_ping"), guard("run_command", {"CommandLine": "echo hi"})] == bare_guard, broken
        # Snapshots that must be ignored: each names a command ghost, which a fresh one would install.
        good = json.loads(snapshot.read_text())
        ghost = {"plugin": "fixture", "module": str(users / "fixture/relay_commands.py")}
        snapshot.write_text(json.dumps({**good, "installed_commands": {**good["installed_commands"], "ghost": ghost}}))
        assert relay("ghost") == (1, "The fixture plugin does not define the ghost command.\n")  # Fresh: read.
        for name, doc in (("foreign root", {**good, "checkout_root": "/elsewhere"}),
                          ("stale settings", {**good, "settings_sha256": "0" * 64}),
                          ("outside path", {**good, "installed_commands": {"ghost": {**ghost, "module": "/tmp/x.py"}}}),
                          ("outside skill", {**good, "active_plugins": [{**good["active_plugins"][0],
                                                                         "skills": ["/etc"]}]}),
                          ("bad prefixes", {**good, "active_plugins": [{**good["active_plugins"][0], "hook_policy": {
                              **good["active_plugins"][0]["hook_policy"], "activity_prefixes": {"x": "BAD LABEL"}}}]}),
                          ("old revision", {key: value for key, value in good.items() if key != "snapshot_revision"}),
                          ("old prefixes", {**good, "active_plugins": [{**good["active_plugins"][0], "hook_policy": {
                              key: value for key, value in good["active_plugins"][0]["hook_policy"].items()
                              if key != "activity_prefixes"}}]}),
                          ("old host skills", {**good, "active_plugins": [{
                              key: value for key, value in good["active_plugins"][0].items()
                              if key != "host_skills_allow"}]}),
                          ("bad host skills", {**good, "active_plugins": [{**good["active_plugins"][0],
                                                                           "host_skills_allow": ["../omarchy"]}]})):
            snapshot.write_text(json.dumps({**doc, "installed_commands": {**doc["installed_commands"],
                                                                          "ghost": doc["installed_commands"].get(
                                                                              "ghost", ghost)}}))
            assert "does not define the ghost" not in relay("ghost")[1], name
            assert relay("fixture-hello") == (0, "The fixture plugin says hello.\n"), name
        # An empty snapshot from before this revision is stale too, while the same one of this revision is read.
        empty = {**good, "active_plugins": [], "installed_commands": {}}
        snapshot.write_text(json.dumps({key: value for key, value in empty.items() if key != "snapshot_revision"}))
        assert relay("fixture-hello") == (0, "The fixture plugin says hello.\n"), "old empty"
        snapshot.write_text(json.dumps(empty))
        assert relay("fixture-hello")[0] != 0, "empty of this revision"
        snapshot.write_text(json.dumps(good)[:200])
        assert relay("fixture-hello") == (0, "The fixture plugin says hello.\n"), "truncated"
        # Manifests that must be refused, each with a named diagnostic, while Rook's own commands keep working.
        manifest = {"name": "Broken", "description": "A broken plugin."}
        bad = {"dotdot": {**manifest, "skills": ["../fixture/skills"]},
               "absolute": {**manifest, "skills": [str(users / "fixture/skills")]},
               "escape": {**manifest, "skills": ["skills"]},
               "dupget": {**manifest, "commands": {"module": "relay_commands.py", "names": ["get"]}},
               "dupskill": {**manifest, "skills": ["skills"]},
               "badhost": {**manifest, "detect": {"host_skill_present": "../omarchy"}},
               "badprefix": {**manifest, "hook_policy": {"activity_prefixes": {"omarchy": "Windows!"}}},
               "badallow": {**manifest, "host_skills_allow": ["omarchy/x"]},
               "hostsettings": {**manifest, "host_skills_allow": ["settings"]},
               "hostfixture": {**manifest, "host_skills_allow": ["fixture-skill"]},
               "selfclash": {**manifest, "skills": ["skills"], "host_skills_allow": ["selfclash"]},
               "badhold": {**manifest, "hold_command": "get"}}
        for pid, data in bad.items():
            write(users / pid, {"plugin.json": json.dumps(data), "relay_commands.py": ""})
        (users / "escape/skills").symlink_to(root / "skills")
        write(users / "dupskill", {"skills/settings/SKILL.md": "---\nname: settings\n---\n"})
        write(users / "selfclash", {"skills/selfclash/SKILL.md": "---\nname: selfclash\n---\n"})
        write(users / "badjson", {"plugin.json": "{not json"})
        write(users / "huge", {"plugin.json": '{"name": "' + "x" * (5 * 1024 * 1024) + '"}'})
        (users / "linked").symlink_to(users / "fixture")
        write(users / "hostskill", {"plugin.json": json.dumps({**manifest, "skills": ["skills"]}),
                                    "skills/omarchy/SKILL.md": "---\nname: omarchy\n---\n"})
        (users / "fifo").mkdir()
        os.mkfifo(users / "fifo/plugin.json")
        write(users / "fifofrag", {"plugin.json": json.dumps({**manifest, "prompt_slots": {"fixture_slot": "slot.md"}})})
        os.mkfifo(users / "fifofrag/slot.md")
        write(users / "toolong", {"plugin.json": json.dumps({**manifest, "prompt_slots": {"fixture_slot": "slot.md"}}),
                                  "slot.md": "X" * 4001})
        started = time.monotonic()
        code, listing = relay("plugin", "check")
        assert time.monotonic() - started < 20, "a FIFO made the plugin check wait"
        assert code == 1 and listing.startswith(bundled_off + "fixture: on, turned on in settings."), listing
        for pid, words in (("dotdot", "must be a plain path"), ("absolute", "must be a plain path"),
                           ("escape", "leads outside the plugin folder"), ("dupget", "the command get is already Rook's"),
                           ("dupskill", "the skill settings is already Rook's"), ("badjson", "is not valid JSON"),
                           ("huge", "larger than 64 kilobytes"), ("linked", "its folder is a link"),
                           ("hostskill", "the skill omarchy is already a shared host skill's"),
                           ("fifo", "its plugin.json is not a regular file"),
                           ("fifofrag", "is not a readable UTF-8 text file"),
                           ("toolong", "longer than 4000 characters. Rook leaves it out."),
                           ("badhost", "its detect host_skill_present must be a plain skill name"),
                           ("badprefix", "activity_prefixes must map program names to plain labels"),
                           ("badallow", "its host skills must be a list of plain names"),
                           ("hostsettings", "the skill settings is already Rook's own"),
                           ("hostfixture", "the skill fixture-skill is already the fixture plugin's"),
                           ("selfclash", "it both ships and lets through the skill selfclash"),
                           ("badhold", "its hold_command must name one of its own relay commands")):
            assert any(line.startswith(f"The {pid} ") and words in line for line in listing.splitlines()), (pid, listing)
        assert relay("fixture-hello") == (0, "The fixture plugin says hello.\n")
        assert relay("get", "voice_engine")[0] == 0 and "is not a setting" not in relay("get", "plugins")[1]
        for pid in (*bad, "badjson", "huge", "hostskill", "fifo", "fifofrag", "toolong"):
            shutil.rmtree(users / pid)
        (users / "linked").unlink()
        assert relay("plugin", "disable", "fixture") == (0, "The fixture plugin is off. The agent sees the change "
                                                            "at Rook's next start.\n")
        assert relay("fixture-hello")[0] != 0 and relay("--help")[1] == bare_help
        off = surface()
        assert off == bare, {key: (off[key], bare[key]) for key in off if off[key] != bare[key]}
        assert bare["guard_policy"] is None and not policy.exists() and guard("mcp_fixture_ping") == "deny"
        assert relay("plugin", "enable", "nothing")[0] == 1
        assert json.loads((base / "config/rook/settings.json").read_text())["plugins"] == {"fixture": False}
        # The bundled Omarchy plugin: on only with its program and its host skill, and off when turned off.
        (base / "bin/omarchy-launch-browser").write_text("#!/bin/sh\nexit 0\n")
        (base / "bin/omarchy-launch-browser").chmod(0o755)
        skill_md = "---\nname: omarchy\ndescription: Stand-in host skill.\n---\n"
        write(base / "home", {".agents/skills/omarchy/SKILL.md": skill_md, ".claude/skills/omarchy/SKILL.md": skill_md})
        manifest_slots = json.loads((BUNDLED / "omarchy/plugin.json").read_text())["prompt_slots"]
        on_slots = {"identity_desktop": manifest_slots["identity_desktop"]["text"],
                    "desktop_control": (BUNDLED / "omarchy/prompts/desktop_control.md").read_text(),
                    "desktop_confirmations": manifest_slots["desktop_confirmations"]["text"]}
        assert on_slots["desktop_control"].endswith(".\n\n") and on_slots["desktop_confirmations"].startswith(" ")
        assert omarchy_line() == omarchy_off.replace("off, its setup was not found on this computer",
                                                     "on, on, because it found its setup")
        shared = str(base / "home/.agents/skills")
        lit = omarchy_surface()
        assert lit == {"host": ["omarchy"], "prefixes": {"omarchy": "windows"}, "read_only": ["omarchy-cmd-terminal-cwd"],
                       "slots": on_slots, "claude": {},
                       "antigravity": [{"path": str(base / "run/rook-skills")},
                                       {"path": shared, "include_only": ["omarchy"]}],
                       "codex": [], "codex_toml": False, "dirs_match": True}, lit
        dark = {"host": [], "prefixes": {}, "read_only": [], "slots": dict.fromkeys(on_slots, ""),
                "claude": {"omarchy": "off"}, "antigravity": [{"path": str(base / "run/rook-skills")}],
                "codex": [f"{shared}/omarchy/SKILL.md"], "codex_toml": True, "dirs_match": True}
        # A missing program or skill keeps it off, even with Hyprland named in the environment.
        env.update(XDG_CURRENT_DESKTOP="Hyprland", HYPRLAND_INSTANCE_SIGNATURE="check")
        away = {"browser": [(base / "bin/omarchy-launch-browser", base / "browser.away")],
                "skill": [(base / f"home/.{agent}/skills/omarchy", base / f"{agent}.away") for agent in ("agents", "claude")]}
        for gone in (("browser",), ("skill",), ("browser", "skill")):
            moves = [move for name in gone for move in away[name]]
            for here, there in moves:
                here.rename(there)
            assert omarchy_line() == omarchy_off, (gone, omarchy_line())
            for here, there in moves:
                there.rename(here)
        # The skill in any one agent's folder is enough, and each agent's own folder setting is honored.
        for here, there in away["skill"]:
            here.rename(there)
        for agent, variable in (("claude", "CLAUDE_CONFIG_DIR"), ("codex", "CODEX_HOME"), ("gemini", None)):
            folder = base / f"elsewhere-{agent}"
            write(folder, {"skills/omarchy/SKILL.md": skill_md})
            if variable:
                env[variable] = str(folder)
            else:
                (base / "home/.gemini/config").mkdir(parents=True)
                (folder / "skills").rename(base / "home/.gemini/config/skills")
            assert omarchy_line() != omarchy_off, agent
            if variable:
                del env[variable]
                assert omarchy_line() == omarchy_off, agent
        shutil.rmtree(base / "home/.gemini")
        for here, there in away["skill"]:
            there.rename(here)
        for name in ("XDG_CURRENT_DESKTOP", "HYPRLAND_INSTANCE_SIGNATURE"):
            del env[name]
        # Turned off with every marker there: no prompt text, no policy, and each agent hides the host skill.
        assert relay("plugin", "disable", "omarchy")[0] == 0
        assert omarchy_line() == omarchy_off.replace("its setup was not found on this computer", "turned off in settings")
        assert (dimmed := omarchy_surface()) == dark, dimmed
        assert relay("plugin", "enable", "omarchy")[0] == 0 and omarchy_surface() == lit
    finally:
        shutil.rmtree(base)
    print("relay.py plugins check passed.")
