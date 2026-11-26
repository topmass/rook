"""Media control, video-vs-music attention rules, and music ducking with a crash-safe restore guard.

Standard library only, sitting above desktop/desk.py so Rook and relay.py share one implementation.
"""

import json
import os
from pathlib import Path
import re
import threading
import time

import desk as _desk

# Music ducks smoothly to this fraction of its original PipeWire stream volume while Rook speaks
# and through any follow-up listening window, then returns to the exact original integer values.
DUCK_RATIO = 0.25
DUCK_STEPS = 4
DUCK_STEP_SECONDS = 0.03
# PulseAudio/PipeWire raw norm volume is 65536 (100%). Allow ~2% float rounding tolerance when checking
# whether the person manually changed the stream volume while it was ducked.
DUCK_TOLERANCE = 1310

# Known music applications (matched against MPRIS bus suffix, identity, desktop entry, or stream app/binary).
MUSIC_APPS = frozenset({
    "spotify", "spotifyd", "ncspot", "spotify_player", "rhythmbox", "clementine", "strawberry",
    "audacious", "elisa", "lollypop", "cmus", "mpd", "mopidy", "amberol", "gapless", "tidal-hifi",
    "youtube-music", "pear-desktop", "feishin", "sonixd", "supersonic", "plexamp", "quodlibet",
    "deadbeef", "cantata", "musikcube", "shortwave", "goodvibes", "nuclear",
})

# Known music web sites (matched against xesam:url or a browser window title). Checked before video sites
# so "YouTube Music" is never mistaken for YouTube video.
MUSIC_SITES = (
    "music.youtube.com", "youtube music",
    "open.spotify.com", "spotify",
    "music.apple.com", "apple music",
    "soundcloud.com", "soundcloud",
    "bandcamp.com", "bandcamp",
    "tidal.com", "tidal",
    "deezer.com", "deezer",
    "pandora.com", "pandora",
    "music.amazon.", "amazon music",
    "qobuz.com", "qobuz",
    "pocketcasts.com", "pocket casts",
    "overcast.fm", "overcast",
    "mixcloud.com", "mixcloud",
    "soma.fm", "di.fm",
)

# Dedicated video players. Treated as video when playing non-audio media with a visible window.
VIDEO_PLAYERS = frozenset({
    "vlc", "mpv", "celluloid", "haruna", "totem", "smplayer", "kodi", "clapper", "showtime", "dragon",
})

# Web sites where a focused browser window usually plays video even if the tab title omits the track title.
VIDEO_SITES = (
    "netflix.com", "netflix",
    "twitch.tv", "twitch",
    "vimeo.com", "vimeo",
    "plex", "jellyfin",
    "disneyplus.com", "disney+",
    "primevideo.com", "prime video",
    "crunchyroll.com", "crunchyroll",
    "hulu.com", "hulu",
    "dailymotion.com", "dailymotion",
    "odysee.com", "nebula.tv", "floatplane.com",
)

# Web browsers that expose a shared MPRIS player across all their tabs.
BROWSERS = frozenset({
    "chromium", "chrome", "google-chrome", "brave", "vivaldi", "edge", "microsoft-edge", "opera",
    "firefox", "zen", "librewolf", "floorp", "waterfox", "helium",
})

AUDIO_EXTENSIONS = (
    ".mp3", ".flac", ".ogg", ".opus", ".m4a", ".wav", ".aac", ".wma", ".aiff", ".alac", ".oga",
)

# PipeWire streams that Rook must never duck (its own voice and system/filter plumbing).
NEVER_DUCK_APPS = frozenset({
    "pw-play", "pw-cat", "pipewire", "wireplumber", "speech-dispatcher", "quickshell", "rook",
})

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _norm(text):
    return _NON_ALNUM.sub(" ", str(text or "").lower()).strip()


def _bus_key(bus_name):
    """Short player name from an MPRIS bus name, such as 'chromium' or 'spotify'."""
    suffix = str(bus_name or "").removeprefix("org.mpris.MediaPlayer2.")
    head = suffix.split(".", 1)[0].lower()
    if head.startswith("chromium"):
        return "chromium"
    return head


def _player_tokens(player):
    """Lowercase identifying tokens for a player from its bus name, identity, desktop entry, and process."""
    tokens = set()
    bus_k = _bus_key(player.get("bus"))
    if bus_k:
        tokens.add(bus_k)
    for field in ("identity", "desktop_entry", "process", "name"):
        raw = str(player.get(field) or "").strip().lower()
        if raw:
            tokens.add(raw)
            first = raw.split()[0]
            if first:
                tokens.add(first)
    return tokens


def _has_music_site(url, title=""):
    hay = f"{url or ''} {title or ''}".lower()
    return any(site in hay for site in MUSIC_SITES)


def _has_video_site(url, title=""):
    hay = f"{url or ''} {title or ''}".lower()
    return any(site in hay for site in VIDEO_SITES)


def _is_audio_url(url):
    clean = str(url or "").split("?", 1)[0].split("#", 1)[0].lower()
    return any(clean.endswith(ext) for ext in AUDIO_EXTENSIONS)


def _title_matches_window(track_title, window_title):
    """Whether a browser window title matches the MPRIS track title (active tab, not a background tab)."""
    track = _norm(track_title)
    win = _norm(window_title)
    if not track or not win:
        return False
    if track in win:
        return True
    # Long titles are sometimes truncated in browser window titles; check a strong prefix.
    if len(track) >= 18 and track[:18] in win:
        return True
    words = [w for w in track.split() if len(w) >= 3]
    if len(words) >= 2:
        hits = sum(1 for w in words[:6] if w in win)
        if hits >= min(3, len(words)):
            return True
    return False


def _window_visible(win, visible_workspaces):
    if not isinstance(win, dict):
        return False
    if win.get("hidden") or win.get("mapped") is False:
        return False
    if visible_workspaces is not None:
        ws = win.get("workspace")
        ws_id = ws.get("id") if isinstance(ws, dict) else ws
        if ws_id is not None and ws_id not in visible_workspaces:
            return False
    elif win.get("visible") is False:
        return False
    return True


def _window_fullscreen(win):
    if not isinstance(win, dict):
        return False
    return bool(win.get("fullscreen") or win.get("fullscreenClient"))


def _matching_windows(player, windows):
    """Hyprland windows that belong to this MPRIS player, by PID first, then by window class."""
    if not windows:
        return []
    pid = player.get("pid")
    if pid is not None:
        by_pid = [w for w in windows if isinstance(w, dict) and w.get("pid") == pid]
        if by_pid:
            return by_pid
    tokens = _player_tokens(player)
    matched = []
    for win in windows:
        if not isinstance(win, dict):
            continue
        cls = str(win.get("class") or win.get("initialClass") or "").lower()
        if cls and (cls in tokens or any(t in cls or cls in t for t in tokens if len(t) >= 3)):
            matched.append(win)
    return matched


def classify_player(player, windows=None, active=None, visible_workspaces=None):
    """Classify one MPRIS player as 'video', 'music', or 'idle'.

    This is the single place that decides whether the owner is clearly watching a video (hold routine
    updates, pause before urgent ones) or listening to music (do not hold, duck while Rook speaks).
    When unsure, prefer 'music' over 'video': a wrongly held update is worse than a ducked stream.

    Rule:
    1. Paused or stopped players are 'idle' (never hold, pause, or duck).
    2. Dedicated music apps (Spotify, ncspot, Rhythmbox, MPD, etc.) are always 'music'.
    3. Known music sites (YouTube Music, Spotify Web, SoundCloud, Bandcamp, etc.) in URL or the
       matching window title are 'music'.
    4. Dedicated video players (VLC, mpv, Celluloid, etc.) are 'music' for audio-only file URLs
       or when Hyprland shows no visible window (such as headless mpv --no-video); otherwise 'video'.
    5. Browsers (Chromium, Firefox, etc.) expose one MPRIS player for all tabs, so Hyprland decides:
       - Without Hyprland window info, treat as 'music' (unsure).
       - A fullscreen visible browser window is 'video', unless its title names a known music site
         or MPRIS has a track title that does not match the window (a background tab playing while
         another tab is fullscreen) and the window is not a known video site.
       - A focused visible browser window is 'video' if the window title matches the MPRIS track
         title (or names a known video site such as Netflix/Twitch where tab titles omit the track
         title), unless it is a known music site or carries a non-empty xesam:album on a non-video
         site (such as Spotify Web, whose tab title omits "Spotify").
       - A browser player in a background tab, unfocused window, or another workspace is 'music'.
    6. Any other unknown player is 'video' only when its window is fullscreen and visible; else 'music'.
    """
    if str(player.get("status") or "") != "Playing":
        return "idle"

    tokens = _player_tokens(player)
    url = str(player.get("url") or "")
    track_title = str(player.get("title") or "")
    album = str(player.get("album") or "").strip()

    # 2. Known music apps.
    if tokens & MUSIC_APPS:
        return "music"

    # 3. Known music sites in metadata URL.
    if _has_music_site(url):
        return "music"

    matched_wins = _matching_windows(player, windows) if windows is not None else None
    active_addr = active.get("address") if isinstance(active, dict) else None

    # 4. Dedicated video players.
    if tokens & VIDEO_PLAYERS:
        if _is_audio_url(url):
            return "music"
        if matched_wins is not None:
            if any(_window_visible(w, visible_workspaces) for w in matched_wins):
                return "video"
            return "music"
        return "video"

    # 5. Browsers (Chromium, Firefox, etc.).
    if tokens & BROWSERS:
        if matched_wins is None:
            return "music"
        visible_wins = [w for w in matched_wins if _window_visible(w, visible_workspaces)]
        if not visible_wins:
            return "music"

        # 5a. Fullscreen visible browser window.
        for win in visible_wins:
            if not _window_fullscreen(win):
                continue
            win_title = str(win.get("title") or "")
            if _has_music_site(url, win_title):
                return "music"
            if track_title and not _title_matches_window(track_title, win_title) and not _has_video_site(url, win_title):
                continue
            return "video"

        # 5b. Focused and visible browser window.
        focused = next((w for w in visible_wins if active_addr and w.get("address") == active_addr), None)
        if focused is not None:
            win_title = str(focused.get("title") or "")
            if _has_music_site(url, win_title):
                return "music"
            is_video_site = _has_video_site(url, win_title)
            is_youtube = "youtube" in win_title.lower() or "youtube.com" in url.lower() or "youtu.be" in url.lower()
            if album and not is_video_site and not is_youtube:
                return "music"
            if track_title:
                if _title_matches_window(track_title, win_title) or is_video_site:
                    return "video"
                return "music"
            if is_video_site or is_youtube:
                return "video"
            return "music"

        # 5c. Background tab, unfocused window, or other workspace.
        return "music"

    # 6. Unknown player: fullscreen visible window counts as video; otherwise duck, do not hold.
    if matched_wins and any(_window_visible(w, visible_workspaces) and _window_fullscreen(w) for w in matched_wins):
        return "video"
    return "music"


def _hyprland_context(timeout=0.4):
    """Fetch Hyprland clients, active window, and visible workspace ids once."""
    if not _desk.PLATFORM.supports_hyprland:
        return None, None, None
    clients = _desk.hyprland_json("clients", timeout=timeout)
    if not isinstance(clients, list):
        return None, None, None
    active = _desk.hyprland_json("activewindow", timeout=timeout)
    if not isinstance(active, dict):
        active = None
    monitors = _desk.hyprland_json("monitors", timeout=timeout)
    visible = None
    if isinstance(monitors, list):
        ids = set()
        for mon in monitors:
            if not isinstance(mon, dict):
                continue
            aw = mon.get("activeWorkspace")
            if isinstance(aw, dict) and aw.get("id") is not None:
                ids.add(aw["id"])
            sw = mon.get("specialWorkspace")
            if isinstance(sw, dict) and sw.get("id"):
                ids.add(sw["id"])
        if ids:
            visible = ids
    return clients, active, visible


def list_players(*, windows=None, active=None, visible_workspaces=None, timeout=0.35, budget=0.6):
    """Return active MPRIS players with playback status, metadata, and video/music classification.

    timeout caps each D-Bus or Hyprland call; budget caps total wall-clock time across all players
    so a wedged D-Bus peer cannot stall callers for seconds.
    """
    if not _desk.has_media():
        return []
    deadline = time.monotonic() + max(timeout, budget)
    listed = _desk.mpris_list(timeout=timeout)
    if not listed:
        return []
    raw_players = []
    for entry in listed:
        rem = deadline - time.monotonic()
        if rem <= 0.02:
            break
        step_t = min(timeout, rem)
        bus = entry["bus"]
        base = _desk.mpris_properties(bus, "org.mpris.MediaPlayer2", timeout=step_t)
        rem = deadline - time.monotonic()
        if rem <= 0.02:
            break
        pl = _desk.mpris_properties(bus, "org.mpris.MediaPlayer2.Player", timeout=min(timeout, rem))
        meta = pl.get("Metadata") if isinstance(pl.get("Metadata"), dict) else {}
        artists = meta.get("xesam:artist")
        if isinstance(artists, list):
            artist = ", ".join(str(a) for a in artists if a)
        else:
            artist = str(artists or "")
        identity = str(base.get("Identity") or "").strip()
        desktop_entry = str(base.get("DesktopEntry") or "").strip()
        name = identity or desktop_entry or _bus_key(bus).capitalize() or bus
        raw_players.append({
            "bus": bus,
            "pid": entry.get("pid"),
            "process": entry.get("process") or "",
            "identity": identity,
            "desktop_entry": desktop_entry,
            "name": name,
            "status": str(pl.get("PlaybackStatus") or "Stopped"),
            "title": str(meta.get("xesam:title") or "").strip(),
            "artist": artist.strip(),
            "album": str(meta.get("xesam:album") or "").strip(),
            "url": str(meta.get("xesam:url") or "").strip(),
            "art_url": str(meta.get("mpris:artUrl") or "").strip(),
            "length": meta.get("mpris:length"),
            "position": pl.get("Position"),
            "can_pause": bool(pl.get("CanPause", True)),
            "can_play": bool(pl.get("CanPlay", True)),
        })

    # Query Hyprland only when at least one player is actively playing (and windows were not injected).
    if windows is None and any(p["status"] == "Playing" for p in raw_players):
        rem = max(0.05, min(timeout, deadline - time.monotonic()))
        windows, active, visible_workspaces = _hyprland_context(timeout=rem)

    for player in raw_players:
        player["kind"] = classify_player(player, windows=windows, active=active,
                                         visible_workspaces=visible_workspaces)
    return raw_players


def attention(timeout=0.35, budget=0.6):
    """Return active video and music players right now. Empty lists when nothing plays."""
    players = list_players(timeout=timeout, budget=budget)
    return {
        "videos": [p for p in players if p["kind"] == "video"],
        "music": [p for p in players if p["kind"] == "music"],
        "players": players,
    }


# Rook keeps these fields for each player it pauses. They show whether the owner touched the player since.
PAUSE_RECORD_KEYS = ("bus", "name", "pid", "process", "identity", "desktop_entry", "title", "url", "position")
# A paused player whose position moved more than this (3 s, in microseconds) was played meanwhile.
RESUME_DRIFT_US = 3_000_000


def pause_players(players, timeout=0.35, budget=0.6):
    """Pause the given video players through MPRIS without re-querying. Return paused player dicts."""
    paused = []
    deadline = time.monotonic() + max(timeout, budget)
    for player in players or ():
        if not player.get("can_pause", True):
            continue
        rem = deadline - time.monotonic()
        if rem <= 0.02:
            break
        ok, _ = _desk.mpris_call(player["bus"], "Pause", timeout=min(timeout, rem))
        if ok:  # What it played and where, so a resume can tell whether the owner touched it since.
            paused.append({key: player.get(key) for key in PAUSE_RECORD_KEYS})
    return paused


def resume_if_still_paused(players, timeout=0.35, budget=0.6):
    """Resume only the players we paused, and only if each is still Paused on the same item at the same place.
    A changed title or address, or a position moved by more than RESUME_DRIFT_US, means the owner played, paused or
    changed it themselves meanwhile, so it stays as they left it."""
    resumed = []
    deadline = time.monotonic() + max(timeout, budget)
    for player in players or ():
        rem = deadline - time.monotonic()
        if rem <= 0.02:
            break
        step_t = min(timeout, rem)
        props = _desk.mpris_properties(player["bus"], "org.mpris.MediaPlayer2.Player", timeout=step_t)
        if str(props.get("PlaybackStatus") or "") != "Paused":
            continue
        meta = props.get("Metadata") if isinstance(props.get("Metadata"), dict) else {}
        if "title" in player and (str(meta.get("xesam:title") or "").strip(), str(meta.get("xesam:url") or "").strip()) \
                != (player.get("title") or "", player.get("url") or ""):
            continue
        was, now = player.get("position"), props.get("Position")
        if isinstance(was, int) and isinstance(now, int) and abs(now - was) > RESUME_DRIFT_US:
            continue
        rem = deadline - time.monotonic()
        if rem <= 0.02:
            break
        ok, _ = _desk.mpris_call(player["bus"], "Play", timeout=min(timeout, rem))
        if ok:
            resumed.append(player["name"])
    return resumed


def pause_videos(timeout=0.35, budget=0.6):
    """Pause every actively playing video player through MPRIS. Return the paused player names."""
    state = attention(timeout=timeout, budget=budget)
    return [p["name"] for p in pause_players(state["videos"], timeout=timeout, budget=budget)]


def is_urgent(event, text="", extra=()):
    """Whether an unprompted turn is urgent enough to pause a playing video instead of waiting.

    Urgent turns are due task timers, tells marked with --urgent (source['urgent']), and notices
    beginning with 'URGENT:'. Plain timers are handled in run_timers() and are always urgent.
    """
    if event == "timer":
        return True
    if event == "inbox" and extra and isinstance(extra[0], dict) and extra[0].get("urgent"):
        return True
    if str(text or "").lstrip().upper().startswith("URGENT:"):
        return True
    return False


_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]+")
TITLE_LIMIT = 120


def safe_text(text, limit=TITLE_LIMIT):
    """Sanitize untrusted MPRIS metadata: strip ANSI/control chars and line breaks, normalize quotes, cap length."""
    cleaned = _ANSI_RE.sub(" ", str(text or ""))
    cleaned = _CTRL_RE.sub(" ", cleaned)
    cleaned = " ".join(cleaned.replace('"', "'").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(1, limit - 3)].rstrip() + "..."


def format_player_line(player):
    """One short readable status line for a single MPRIS player with untrusted metadata marked and capped."""
    status = safe_text(player.get("status") or "Stopped", 20)
    kind = player.get("kind")
    tag = f"{status} ({kind})" if status == "Playing" and kind in ("video", "music") else status
    title = safe_text(player.get("title") or "", TITLE_LIMIT)
    artist = safe_text(player.get("artist") or "", 60)
    name = safe_text(player.get("name") or _bus_key(player.get("bus")), 40)
    parts = [f"{name}: {tag}"]
    if title:
        parts.append(f'title: "{title}"')
    if artist and artist.lower() not in title.lower():
        parts.append(f'artist: "{artist}"')
    return ", ".join(parts)


def _match_named_players(players, target):
    needle = target.strip().lower()
    exact = [p for p in players if needle in (
        p["name"].lower(), _bus_key(p["bus"]), p["identity"].lower(),
        p["desktop_entry"].lower(), p["process"].lower(), p["bus"].lower(),
    )]
    if exact:
        return exact
    return [p for p in players if any(needle in field.lower() for field in (
        p["name"], p["bus"], p["identity"], p["desktop_entry"], p["process"], p["title"], p["artist"],
    ) if field)]


def control(action, target=None, timeout=1.0):
    """Run one relay.py media action (status, pause, play, toggle). Return (ok, output_text)."""
    if not _desk.has_media():
        return False, _desk.NOT_YET
    if action not in ("status", "pause", "play", "toggle"):
        return False, f"Unknown media action {action!r}. Use status, pause, play, or toggle."
    players = list_players(timeout=min(timeout, 0.5))
    if action == "status":
        if not players:
            return True, "No media players are active."
        return True, "\n".join(format_player_line(p) for p in players)

    if not players:
        return False, "No media players are active."

    candidates = _match_named_players(players, target) if target else list(players)
    if not candidates:
        names = ", ".join(p["name"] for p in players)
        return False, f"No active player matches {target!r}. Active players: {names}."

    chosen = []
    if target:
        if len(candidates) == 1:
            chosen = candidates
        elif action == "pause":
            playing = [p for p in candidates if p["status"] == "Playing"]
            chosen = playing or candidates[:1]
        elif action == "play":
            paused = [p for p in candidates if p["status"] != "Playing"]
            chosen = paused[:1] or candidates[:1]
        else:
            playing = [p for p in candidates if p["status"] == "Playing"]
            chosen = playing[:1] or candidates[:1]
    else:
        if action == "pause":
            playing = [p for p in candidates if p["status"] == "Playing"]
            if not playing:
                return True, "Nothing is playing."
            videos = [p for p in playing if p["kind"] == "video"]
            chosen = videos if len(videos) == 1 and len(playing) > 1 else playing
        elif action == "play":
            paused = [p for p in candidates if p["status"] != "Playing"]
            if not paused:
                return True, f"{candidates[0]['name']} is already playing."
            chosen = [paused[0]]
        else:  # toggle
            playing = [p for p in candidates if p["status"] == "Playing"]
            chosen = [playing[0]] if playing else [candidates[0]]

    method = {"pause": "Pause", "play": "Play", "toggle": "PlayPause"}[action]
    lines = []
    for player in chosen:
        was = player["status"]
        ok, err = _desk.mpris_call(player["bus"], method, timeout=timeout)
        if not ok:
            return False, f"Could not {action} {player['name']}: {err}"
        verb = ("Paused" if action == "pause" or (action == "toggle" and was == "Playing")
                else "Resumed" if was == "Paused" else "Playing")
        name = safe_text(player["name"], 40)
        title = safe_text(player.get("title") or "", TITLE_LIMIT)
        suffix = f', title: "{title}"' if title else ""
        lines.append(f"{verb} {name}{suffix}.")
    return True, "\n".join(lines)


def _stream_is_duckable(stream, own_pid):
    """Whether a PipeWire sink input is a real user playback stream that may be ducked."""
    if stream.get("corked") or stream.get("mute"):
        return False
    if stream.get("passive") or stream.get("virtual"):
        return False
    vols = stream.get("volumes") or []
    if not vols or all(v <= 0 for v in vols):
        return False
    if own_pid is not None and stream.get("pid") == own_pid:
        return False
    tokens = {
        str(stream.get("app") or "").strip().lower(),
        str(stream.get("binary") or "").strip().lower(),
        str(stream.get("node") or "").strip().lower(),
    } - {""}
    if tokens & NEVER_DUCK_APPS:
        return False
    if any(t.startswith("pw-play") or t.startswith("pw-cat") for t in tokens):
        return False
    return True


def _stream_matches_player(stream, player):
    if stream.get("pid") is not None and player.get("pid") is not None and stream["pid"] == player["pid"]:
        return True
    s_tokens = {
        str(stream.get("app") or "").strip().lower(),
        str(stream.get("binary") or "").strip().lower(),
        str(stream.get("node") or "").strip().lower(),
    } - {""}
    p_tokens = _player_tokens(player)
    if s_tokens & p_tokens:
        return True
    for st in s_tokens:
        for pt in p_tokens:
            if len(pt) >= 3 and len(st) >= 3 and (pt in st or st in pt):
                return True
    return False


def _stream_is_known_music_app(stream):
    tokens = {
        str(stream.get("app") or "").strip().lower(),
        str(stream.get("binary") or "").strip().lower(),
        str(stream.get("node") or "").strip().lower(),
    } - {""}
    return bool(tokens & MUSIC_APPS)


# A stream at or below about 5 percent of full volume (65536) counts as near silence.
AUDIBLE_FLOOR = 3277


def audible_streams(timeout=0.4):
    """Names of other programs' streams that make sound now, which a listen window would record from the speakers.

    A stream counts when it could be ducked (uncorked, unmuted, not Rook's own pw-play voice, not a system
    filter) and its loudest channel is above AUDIBLE_FLOOR, so music ducked to 25 percent still counts. A
    stream whose MPRIS players are all paused or stopped counts as silent, such as a video Rook paused. A
    failed stream list counts as silence, as before this check.
    """
    raw = _desk.sink_inputs(timeout=timeout) or []
    own_pid = os.getpid()
    loud = [s for s in raw if _stream_is_duckable(s, own_pid) and max(s["volumes"]) > AUDIBLE_FLOOR]
    if not loud:
        return []
    players = list_players(timeout=timeout)
    still = [p for p in players if p["status"] != "Playing"]
    playing = [p for p in players if p["status"] == "Playing"]
    return [s.get("app") or s.get("binary") or str(s["index"]) for s in loud
            if any(_stream_matches_player(s, p) for p in playing)
            or not any(_stream_matches_player(s, p) for p in still)]


def _write_private_json(path, data):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w") as out:
        os.fchmod(out.fileno(), 0o600)
        json.dump(data, out)
    temp.replace(path)


class Ducker:
    """Smoothly duck active music streams while Rook speaks, with a crash-safe restore guard.

    Before the first volume change, the original per-channel PipeWire volumes are saved to
    state_path (mode 0600, atomic replace). restore() always returns each stream to its exact
    saved values unless the stream disappeared from a successful list or the person changed its
    volume while ducked. Failed lists or failed volume sets keep the note for retry, and duck()
    never saves a new original while a note for that stream still exists.
    """

    def __init__(self, state_path, *, ratio=DUCK_RATIO, steps=DUCK_STEPS,
                 step_seconds=DUCK_STEP_SECONDS, tolerance=DUCK_TOLERANCE):
        self.state_path = Path(state_path)
        self.ratio = float(ratio)
        self.steps = max(1, int(steps))
        self.step_seconds = max(0.0, float(step_seconds))
        self.tolerance = int(tolerance)
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._records = []
        self.last_skip = None

    @property
    def active(self):
        return bool(self._records)

    def has_note(self):
        return self.state_path.exists()

    def summary(self):
        return [r.get("app") or r.get("binary") or str(r.get("index")) for r in self._records]

    def cancel(self):
        """Abort an in-progress duck ramp so restore() can take over at once."""
        self._cancel.set()

    def _find_music_streams(self, timeout=0.4, state=None):
        """Find uncorked user streams that belong to playing music (never videos, calls, or Rook's voice)."""
        self.last_skip = None
        if not _desk.has_media():
            return []
        own_pid = os.getpid()
        raw = _desk.sink_inputs(timeout=timeout)
        if not raw:
            return []
        streams = [s for s in raw if _stream_is_duckable(s, own_pid)]
        if not streams:
            return []
        # Never duck while any other program uses the microphone, or when call status cannot be read.
        callers = _desk.microphone_busy(timeout=timeout)
        if callers is None:
            self.last_skip = "microphone_unknown"
            return []
        if callers:
            self.last_skip = "microphone_busy"
            return []
        state = state or attention(timeout=timeout)
        players = state["players"]
        music_players = state["music"]
        non_music_players = [p for p in players if p["kind"] != "music"]

        chosen = []
        seen = set()
        for mp in music_players:
            # Every active stream of the player's application ducks together, matched by process id or name.
            # Browsers name their streams "Playback", so a title never tells the tabs apart.
            matched = [s for s in streams if _stream_matches_player(s, mp)]
            for stream in matched:
                idx = stream["index"]
                if idx not in seen:
                    seen.add(idx)
                    chosen.append(stream)

        # A known music app without MPRIS still ducks, unless a non-music MPRIS player owns it.
        for stream in streams:
            idx = stream["index"]
            if idx in seen:
                continue
            if _stream_is_known_music_app(stream) and not any(
                _stream_matches_player(stream, p) for p in non_music_players
            ):
                seen.add(idx)
                chosen.append(stream)
        return chosen

    def duck(self, timeout=0.4, state=None):
        """Find playing music streams, save original volumes, and ramp them down smoothly.
        state is an attention() result the caller already read, so the players are read once."""
        with self._lock:
            self._cancel.clear()
            existing = self._load_records()
            if self._records and len(self._records) == len(existing):
                return False
            streams = self._find_music_streams(timeout=timeout, state=state)
            if not streams or self._cancel.is_set():
                return False
            by_index = {rec["index"]: rec for rec in existing}
            all_records = list(existing)
            to_duck = []
            for stream in streams:
                idx = stream["index"]
                saved = by_index.get(idx)
                if saved is not None and self._same_stream(saved, stream):
                    # Keep the previously saved original volume; never save a ducked value as original.
                    curr = list(stream["volumes"])
                    if len(curr) == len(saved["target"]) and any(
                        c > t + self.tolerance for c, t in zip(curr, saved["target"])
                    ):
                        saved["ramping"] = True
                        to_duck.append((saved, curr))
                    continue
                orig = list(stream["volumes"])
                target = [max(1, round(v * self.ratio)) if v > 0 else 0 for v in orig]
                if target == orig:
                    continue
                rec = {
                    "index": idx,
                    "app": stream.get("app") or "",
                    "binary": stream.get("binary") or "",
                    "original": orig,
                    "target": target,
                    "ramping": True,
                }
                all_records.append(rec)
                by_index[idx] = rec
                to_duck.append((rec, orig))
            if not to_duck or self._cancel.is_set():
                if existing:
                    self._records = existing
                return False
            # Persist before the very first volume change so a crash can always restore it.
            self._records = all_records
            _write_private_json(self.state_path, {
                "version": 1,
                "ducked_at": time.time(),
                "streams": all_records,
            })

            applied = False
            for step in range(1, self.steps + 1):
                if self._cancel.is_set():
                    break
                frac = step / self.steps
                for rec, start_vols in to_duck:
                    vals = [round(s + (t - s) * frac) for s, t in zip(start_vols, rec["target"])]
                    ok, _ = _desk.set_sink_input_volume(rec["index"], vals, timeout=timeout)
                    applied = applied or ok
                if step < self.steps and self.step_seconds > 0:
                    if self._cancel.wait(self.step_seconds):
                        break

            if not self._cancel.is_set():
                for rec, _ in to_duck:
                    rec["ramping"] = False
                _write_private_json(self.state_path, {
                    "version": 1,
                    "ducked_at": time.time(),
                    "streams": all_records,
                })
            return applied

    def _load_records(self):
        if self._records:
            return list(self._records)
        try:
            data = json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            return []
        streams = data.get("streams") if isinstance(data, dict) else None
        if not isinstance(streams, list):
            return []
        valid = []
        for rec in streams:
            if (isinstance(rec, dict) and isinstance(rec.get("index"), int)
                    and isinstance(rec.get("original"), list) and isinstance(rec.get("target"), list)
                    and rec["original"] and len(rec["original"]) == len(rec["target"])):
                valid.append(rec)
        return valid

    def _same_stream(self, rec, stream):
        if stream["index"] != rec["index"]:
            return False
        if rec.get("binary") and stream.get("binary") and rec["binary"].lower() != stream["binary"].lower():
            return False
        if rec.get("app") and stream.get("app") and rec["app"].lower() != stream["app"].lower():
            return False
        return True

    def _user_changed(self, rec, curr):
        orig = rec["original"]
        target = rec["target"]
        if len(curr) != len(orig):
            return True
        if rec.get("ramping"):
            return any(
                c < min(o, t) - self.tolerance or c > max(o, t) + self.tolerance
                for c, o, t in zip(curr, orig, target)
            )
        return any(abs(c - t) > self.tolerance for c, t in zip(curr, target))

    def restore(self, immediate=False, timeout=0.5):
        """Restore saved stream volumes unless gone from a successful list or changed by the person.

        A failed stream list, failed set call, or unverified read-back keeps the note on disk for retry.
        """
        self._cancel.set()
        with self._lock:
            records = self._load_records()
            result = {"restored": [], "dropped": [], "user_changed": [], "failed": [], "pending": 0}
            if not records:
                self._records = []
                self.state_path.unlink(missing_ok=True)
                return result
            raw = _desk.sink_inputs(timeout=timeout)
            if raw is None:
                # Stream list failed or timed out: keep every record and duck.json for retry.
                self._records = records
                result["failed"] = [r.get("app") or r.get("binary") or str(r["index"]) for r in records]
                result["pending"] = len(records)
                return result

            current = {s["index"]: s for s in raw}
            to_restore = []
            for rec in records:
                label = rec.get("app") or rec.get("binary") or str(rec["index"])
                stream = current.get(rec["index"])
                if stream is None or not self._same_stream(rec, stream):
                    result["dropped"].append(label)
                    continue
                if self._user_changed(rec, stream["volumes"]):
                    result["user_changed"].append(label)
                    continue
                to_restore.append((rec, stream["volumes"], label))

            remaining = []
            if to_restore:
                steps = 1 if immediate or self.steps <= 1 else self.steps
                final_ok = {}
                for step in range(1, steps + 1):
                    frac = step / steps
                    for rec, start_vols, _ in to_restore:
                        if step == steps:
                            vals = list(rec["original"])
                        else:
                            vals = [round(s + (o - s) * frac) for s, o in zip(start_vols, rec["original"])]
                        ok, _ = _desk.set_sink_input_volume(rec["index"], vals, timeout=timeout)
                        if step == steps:
                            final_ok[rec["index"]] = ok
                    if step < steps and self.step_seconds > 0:
                        time.sleep(self.step_seconds)

                verify_raw = _desk.sink_inputs(timeout=timeout)
                verify_map = {s["index"]: s for s in verify_raw} if verify_raw is not None else None
                for rec, _, label in to_restore:
                    if not final_ok.get(rec["index"]) or verify_map is None:
                        remaining.append(rec)
                        result["failed"].append(label)
                        continue
                    after = verify_map.get(rec["index"])
                    if after is None or not self._same_stream(rec, after):
                        result["dropped"].append(label)
                    elif (len(after["volumes"]) == len(rec["original"])
                          and all(abs(a - o) <= self.tolerance for a, o in zip(after["volumes"], rec["original"]))):
                        result["restored"].append(label)
                    else:
                        remaining.append(rec)
                        result["failed"].append(label)

            if remaining:
                self._records = remaining
                _write_private_json(self.state_path, {
                    "version": 1,
                    "ducked_at": time.time(),
                    "streams": remaining,
                })
                result["pending"] = len(remaining)
            else:
                self._records = []
                self.state_path.unlink(missing_ok=True)
            return result

    def recover(self, timeout=0.5):
        """On start-up, restore any stream left ducked by a crash, or return None if no note exists."""
        if not self.state_path.exists():
            return None
        return self.restore(immediate=True, timeout=timeout)
