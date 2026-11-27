"""Rook overlay: a swarm of golden grains at the top of the focused monitor.

Runs under the system /usr/bin/python (PyGObject and gtk4-layer-shell are
system packages). The overlay never takes keyboard focus, so the focused window keeps it.
It shows on the focused monitor. With --wow it is also World of Warcraft's companion overlay:
it shows inside the game window, in the dark look, and it reads the
game's gear card (see "reading" below).

Protocol, stdin (one JSON object per line):
    {"state": "listening"|"transcribing"|"thinking"|"permission"|"speaking"|"result"|"error"|"hidden"|"ready",
     "level": 0.02, "spoken": "short line", "details": "full answer",
     "caption": "Words being spoken.", "seconds": 3.4, "activity": "WebSearch"}
    Every key is optional, and unknown keys are ignored. "level" is raw mic or speech RMS and is auto-ranged.
    "spoken" replaces the card text. "details" with "speaking" or "result" is the
    full written answer in markdown: a click on the captions opens it in the
    last-answer panel, and so does a click on the resting loop, which keeps the last
    answer until the next one arrives. The panel is a terminal-style window of its own:
    its text can be selected and copied, each code block has a copy control, it can be
    dragged by its header, and it stays open until it is closed. A click on a link opens it in the default browser.
    The panel keeps the last ANSWER_HISTORY answers, and the arrows in its header step through them.
    {"answers": ["oldest", ..., "newest"]} seeds that history, as the companion does at start.
    "details" with "permission" describes the request on the card, and "card" is its id, which the answer echoes.
    With it, "tool" is the tool's name, "who" names the agent that asks, and "count" is how many cards wait; "count"
    alone updates that number. The Devs card shows them (see _CardFace).
    "listening" clears both; an open panel keeps the
    last answer until the next one replaces it.
    "caption" with text starts showing words under the swarm, revealed over
    "seconds" (the estimated speech length). An empty "caption" says that
    speech ended: the last sentence holds briefly, then fades. "seconds_left" without "caption" gives the voice's real
    length ("seconds") and what is left of it. The newest caption then follows the voice to its end.
    "activity" names the tool Claude is using ("" for none). While the state is
    "thinking" it picks the form the grains gather into and the label. Any
    other state change clears it. For Bash, it may name what the command runs instead (see BASH_ACTIVITIES).
    WoW mode only (--wow, with the game focused); ignored otherwise:
    "reading_label" (optional, sent with "reading") is the label shown while reading; the default
    is READING CHANGES.
    "reading" is the gear card's rectangle [x, y, w, h] in the game window's own
    coordinates. During a turn the grains fly to it, frame it, read across it,
    and return; the overlay owns that timing. It ends early if the turn ends.
    {"guide": {"text": "Hold Right Alt to answer", "until": "listening"}} holds one line under Rook in the label
    lettering. With "until": "listening", Rook's first listen changes the line to GUIDE_LISTENING, and the guide clears
    when that listen ends. {"guide": {"code": "482 913", "text": "...", "seconds": 600}} shows the code large, in the
    caption lettering at GUIDE_CODE_SCALE times its size with the label's gold rim, and the text under it. It clears
    after "seconds", when that is a finite number. The text is cut to 75 characters, and with an ellipsis to the
    window's width; the code is cut to 12 characters. {"guide": null} clears it, and a new guide replaces the old one.
    At rest the guide sits under the resting loop. In a turn, or while a send fan holds, it sits under the working form,
    and moves down under a caption while one shows. A code guide in a turn grows the caption area by GUIDE_ROOM px.
    The guide never shows while Rook is dark or hidden.
    {"dark": true} hides Rook whenever no turn shows: no resting loop, captions, or labels. A turn shows as usual
    and fades away when it ends. {"dark": false} shows Rook again.
    "quiet" with "thinking" (true or false) says whether the turn is one the owner did not ask for. With true, Rook
    stays at rest on its loop, in the same place with the same grains, and a comet of light laps the loop (see
    QUIET_LAP). It shows no label, no activity form, and no send fan. Thinking without it, or with false (a steer), shows
    the turn as usual. Any other state ends it: "speaking" pulls the swarm down, and "hidden" leaves it at rest. A quiet
    turn shows nothing while Rook is dark.
    {"stage": true} draws diagrams and the answer panel in the stage host (stage/host.py) instead of the swarm and the
    panel window, with the same messages and answers; when the host cannot start or dies, the overlay draws as before.
    {"render": {"id": "7", "diagram": {"graph": "a > b", "title": ""}}} has the swarm form a constellation (see
    desktop/constellation.py); {"render": {"id": "8", "step": 2}} lights its second node (0 for none, a list for
    several), and {"render": {"id": "9", "clear": true}} ends it. A diagram sent with "stage": true is answered but not
    shown. {"render": {"reveal": "7"}} shows it, and {"render": {"reveal": "7", "drop": true}} drops it. An old
    {"render": {"scene": ...}} gets a refusal. A diagram holds over the turn's other forms and stays SCENE_SECONDS
    (render.py) after the turn ends; the owner's next turn ends it.
    {"send": [{"id": "k1", "name": "Rook build", "project": "rook", "machine": "oak", "outcome": "pending"}, ...]}
    starts or updates the multi-thread dispatch fan. Each object in the list has:
      - "name" (required string; "thread" accepted as alias): plain-text thread title, control chars stripped, capped at
        200 chars, never parsed as Pango markup. Empty/whitespace entries are skipped.
      - "id" (optional string): stable send key (e.g. journal sends.key / tool call id) used to match outcome updates.
      - "project", "machine" (optional strings, capped at 60 chars): shown as "PROJECT · MACHINE" under a single send.
      - "outcome" (optional string): "pending" (default/unset), "landed", "failed" (or "not-landed"), or "unknown".
    When to send from the companion: send the full pending list when send intent is recorded (e.g. desktop/rook.py
    journal_send for t3_thread_send/t3_thread_launch/t3_pending_request), then send a follow-up {"send": [{"id": ...,
    "outcome": "landed"|"failed"|"unknown"}, ...]} as each send settles (send_settle). Matching every entry by id or
    name updates outcomes in place while the fan holds (extending the hold slightly so the mark settles); any new or
    unmatched list replaces an active fan; {"send": []} clears it. At most 6 rows show ("and N more" on row 6).
    stdin EOF fades the overlay out and exits.
    The media viewer:
    {"show": {"path": "/absolute/file.png", "title": "Optional short title"}} shows a picture (PNG, JPEG, WebP, GIF,
    animated or not, or anything else GdkPixbuf reads) or a video (anything GStreamer plays) in the viewer: the swarm
    flies to the middle of the monitor and opens a black box in the media's own shape, framed by its dust. A new show
    replaces the one open. {"show": "close"} closes it. A click on the viewer or its controls gives it the keyboard
    while the pointer stays on it (never in the game): Escape closes it, and Space pauses and resumes a clip or a video. A click on a picture closes
    it; a click on a video pauses it, and its small close mark closes it. On hover, controls show under the box: play
    and pause and a scrub bar for a clip or a video, and a mark that opens the file in the system's own viewer.

Protocol, stdout (one JSON object per line, one per button press or viewer change):
    {"event": "interrupt"}
    {"event": "debug_replay"}  (Shift+right-click on the resting loop; {"replay_armed": true} answers with a pulse)
    {"event": "permission", "allow": true, "answers": {...}, "card": "the id of the card it answers"}
    {"event": "shown", "path": "...", "kind": "image"|"animation"|"video", "width": 1920, "height": 1080}
    {"event": "closed", "path": "...", "why": "click"|"escape"|"close mark"|"rook"|"replaced"|"ended"|"game"|"error"}
    {"event": "show_error", "path": "...", "error": "A plain sentence that says why the file was refused."}
    {"event": "rendered", "id": "7", "ok": true, "said": "What shows."} or {..., "ok": false, "errors": [...]}

Check it without a parent process:  /usr/bin/python desktop/overlay.py --demo
Check the render tool's scenes in the engine, offscreen:  /usr/bin/python desktop/overlay.py --check-render
Draw every state to a PNG, offscreen:  /usr/bin/python desktop/overlay.py --render sheet.png
(it also writes orb_large.png beside it: loop, sphere, and the listening orb at 4x;
listen_styles.png: every listening style in silence, quiet speech, a loud syllable, and 0.5 s after it;
listen_large.png: the loud syllable of each waveform style at 4x; shapes_large.png: every activity
form at 4x; details.png: the caption's hover hint and the resting loop's LAST ANSWER hint;
panel_terminal.png: the last-answer panel; panel_history.png: its history arrows and links;
theme_compare.png: both themes side by side;
and wow_placement.png: WoW mode's placement inside a game window that does not fill its monitor)

World of Warcraft mode:  --wow  (see the top of this docstring).

Choose the listening form:  --listen orb|halo|helix|ridges|burst  (orb, the turning sphere, is the default).
Give several, as in --listen helix,halo,burst, to use the next one on each turn.
    halo: a turning gold ring; the voice sends ripples to its core.  helix: a turning double helix that swells.
    ridges: stacked ridgelines where speech moves back into depth.  burst: a seed head whose spokes open.
"""

import io
import colorsys
import ctypes
import json
import math
import os
import random
import re
import select
import shutil
import socket
import subprocess
import sys
import threading
import time
import types
from array import array
from bisect import bisect_right
from collections import OrderedDict
from ctypes import CDLL

# gtk4-layer-shell must load before libwayland-client, or layer-shell setup fails.
for _soname in ("libgtk4-layer-shell.so", "libgtk4-layer-shell.so.0"):
    try:
        CDLL(_soname)
        break
    except OSError:
        continue

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
import cairo
import devs_pack  # Data-driven Devs theme pack manifest and 3D form registry.
import pack_player  # Switchable theme pack loader and flipbook atlas player (FORMAT.md).
import constellation  # A diagram the model writes as one line, drawn by the presence's own grains.
import filament  # How a constellation looks: filament lines its grains build, light and carry home.
import render as scenes  # The dust scene format; the overlay reads its label type and timings.
import stage_link  # The stage host's link, for diagrams and the panel when the stage setting is on.
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, GObject, Graphene, Gsk, Gtk, Pango, PangoCairo
from gi.repository import Gtk4LayerShell as LayerShell

# The media viewer plays video with GStreamer when it is there; without it the viewer shows pictures only.
try:
    gi.require_version("Gst", "1.0")
    gi.require_version("GstApp", "1.0")
    gi.require_version("GstPbutils", "1.0")
    gi.require_version("GstVideo", "1.0")
    from gi.repository import Gst, GstApp, GstPbutils, GstVideo  # GstApp gives appsink its pull methods.
    Gst.init(None)
except (ImportError, ValueError):
    Gst = GstApp = GstPbutils = GstVideo = None
# A playing video goes to GTK as a paintable (gtk4paintablesink): the frames reach the GPU without a copy through
# Python. False, or a missing sink, keeps the appsink path. playbin picks the VA hardware decoders by their own rank
# (primary + 1) when gst-plugin-va is there; _Clip falls back to software decoding when they fail.
VIEW_PAINTABLE = True

STATES = {"ready", "listening", "transcribing", "thinking", "permission", "speaking", "result", "error", "hidden"}
LABELS = {"listening": "LISTENING", "transcribing": "TRANSCRIBING", "thinking": "THINKING"}

WIDTH = 740
ORB = 176
ORB_W = 230
ORB_H = ORB + 22
CAPTION_H = 160
CAPTION_W = 600
CAPTION_TOP = 36
# The working forms start at 15% of the monitor height, where WoW's overlay starts them, so the two match.
# The tallest forms leave about 20 px of empty canvas above their top grain.
TOP_SHARE = 0.15
GRAIN_INSET = 20
# The resting loop sits near the top of the monitor. The owner chose this height.
REST_SHARE = 0.05
REST_PAD = 48
FALLBACK_TOP, FALLBACK_LIFT = 72, 124
# While this window is focused, Rook steps aside for WoW's own overlay.
GAME_TITLE = "World of Warcraft"
LOOP_PERIOD = 10.5
# A quiet turn (see the protocol): a comet laps the resting loop once every QUIET_LAP s. Its head adds QUIET_PEAK to
# the grains' brightness, and the whole loop adds QUIET_LIFT. The GL tonemap compresses these: on screen the head is
# about 1.3 times as bright and the loop about 5% brighter. It fades in over QUIET_IN s and out over QUIET_OUT s.
QUIET_LAP, QUIET_PEAK, QUIET_LIFT, QUIET_IN, QUIET_OUT = 2.4, 2.2, 0.18, 0.4, 0.3
# The resting loop's look: one of REST_LOOKS, the owner's pick. Each changes only the grains' brightness, never their
# places or colour, so the GL and Cairo paths both follow it. "today" is the look before 2026-11-27 and runs no code.
# At rest a look eases in over REST_IN s once the loop has been home REST_SETTLE s: every grain drops to "dim" of today,
# but "flecks" of every 100 grains stay at today's brightness (today's sparkle grains first). Each fleck twinkles once
# every "twinkle" s (a range, each fleck its own period and phase; None holds it steady).
# A quiet turn replaces the comet: the loop rises over "rise" s to "level" of today, and a glare laps it once every
# "lap" s: the loop's own grains brighten in a soft band "band" rad wide each side of its centre, up to 1 + "peak" times
# the level, like light sliding along a metal ring. It adds no grains and no orb. When the quiet turn ends, the loop
# falls back to rest over REST_FALL s. A turn of the owner's own lights it fully in REST_OUT s.
REST_LOOK = "dense_fleck"
REST_LOOKS = {
    "today": None,
    "fleck_glare_full": {"dim": 0.3, "flecks": 8, "twinkle": (2.0, 4.0), "level": 1.0, "rise": 1.0, "lap": 4.0,
                         "peak": 1.4, "band": 0.40},
    "fleck_glare_soft": {"dim": 0.3, "flecks": 8, "twinkle": (2.0, 4.0), "level": 0.85, "rise": 1.0, "lap": 6.0,
                         "peak": 1.0, "band": 0.50},
    "sparse_fleck": {"dim": 0.27, "flecks": 4, "twinkle": None, "level": 0.9, "rise": 1.5, "lap": 5.0,
                     "peak": 1.2, "band": 0.40},
    "dense_fleck": {"dim": 0.3, "flecks": 14, "twinkle": (2.0, 4.0), "level": 1.0, "rise": 1.0, "lap": 4.0,
                    "peak": 1.4, "band": 0.40},
}
REST_SETTLE, REST_IN, REST_OUT, REST_FALL = 1.2, 2.0, 0.2, 1.5
REST_EVERY = 3
# Particle engine prototype variant: "baseline", "A" (soft HDR + depth), "B" (+ Kawase glow), "C" (+ 3D forms).
PARTICLE_VARIANT = "C"
KAWASE_BLOOM_STRENGTH = 0.38
# Optional resting stride override for A/B comparisons (1 = all 640, 2 = 320, 3 = 214, None = variant default).
REST_EVERY_OVERRIDE = None


def _rest_every():
    if REST_EVERY_OVERRIDE is not None:
        return max(1, int(REST_EVERY_OVERRIDE))
    return REST_EVERY if PARTICLE_VARIANT == "baseline" else 1
# WoW mode, reading the gear card: zoom over, frame it while the orb reads across, then return.
READ_ZOOM, READ_HOLD, READ_RETURN = 0.35, 0.8, 0.4
FRAME_GAP = 6
ORB_EVERY = 4
READING_STATES = ("listening", "transcribing", "thinking")
TICK_MS = 16
# Frames a second for quiet moments, so Rook costs the game little: the resting loop on the desktop and in the game, the
# open viewer at rest (its dust only drifts), and the viewer's dust in a turn. While a video plays the dust holds
# still and the video comes in on the display's own clock. While no frame is shown (the screen is locked or
# asleep), the overlay checks UNSEEN_FPS times a second.
REST_FPS, GAME_REST_FPS, VIEW_REST_FPS, VIEW_TURN_FPS, UNSEEN_FPS = 30, 15, 10, 20, 4
# While the GL frame draws the open viewer's dust, the viewer's own frame clock drives Rook, and the dust moves
# VIEW_GL_FPS times a second in every state (at rest, in a turn, under a video), on whole display frames.
VIEW_GL_FPS = 60
# The resting loop on screen is driven by the main window's frame clock the same way, so its steps are even: this many
# times a second on the desktop, and in the game.
REST_CLOCK_FPS, GAME_CLOCK_FPS = 60, 60
ERROR_SECONDS = 5
# The owner wants the swarm back at rest about a second after the last word: hold, fade, then rise.
REST_SECONDS = 0.0
MIN_SPAN = 0.003
PEAK_DECAY = 0.994
# A mic level under this is silence: the level at which Rook itself counts sound as speech (LISTEN_AFTER_LEVEL in rook.py).
LISTEN_SILENCE_RMS = 0.015

WORD_IN = 0.26
WORD_RISE = 6.0
SENTENCE_OUT = 0.4
# A sentence starts its fade SENTENCE_LEAD before the next one's first word, so the two never show at full strength
# together. At NEARLY_GONE of its fade a sentence is below 0.3 alpha; the next one's words wait for that, but never
# longer than BLINK behind the voice.
SENTENCE_LEAD, NEARLY_GONE, BLINK = 0.25, 0.63, 0.12
HOLD = 0.5
CAPTION_OUT = 0.6
QUICK_OUT = 0.15
FINISH_SPEED = 5.0
# A caption off the voice's real pace closes about two thirds of the gap in this many seconds.
CATCH_UP = 1.5
SECONDS_PER_CHAR = 0.053

INK = (0.035, 0.047, 0.10)
IVORY = (1.0, 0.95, 0.84)
AMBER = (0.95, 0.70, 0.28)
PALE_GOLD = (1.0, 0.92, 0.70)
DUST_BLUE = (0.40, 0.76, 1.0)
EMBER = (0.50, 0.15, 0.07)
GARNET = (0.72, 0.26, 0.24)
DUST_TONES = [tuple(a + (b - a) * k / 2 for a, b in zip(AMBER, PALE_GOLD)) for k in range(3)]

# The swarm, its labels, and the captions follow Omarchy's light or dark theme. The details panel and the
# permission card are dark surfaces in both, so they keep the colours above.
# Dark is fine additive gold dust (the Devs look). Light paints the same dust over the window in a deeper gold, because
# light cannot be added to a white page; see LIGHT_LOOKS. "round" draws grains as anti-aliased dots instead of
# squares; "rim" is (colour, extra size, alpha) under each grain; "twins" draws each grain again at these offsets.
# Grain alpha is alpha_floor + alpha_gain * level / 7, and size scales every grain; spark_alpha is the additive sparks.
# depth_floor is the least depth brightness a grain of a turning form keeps on its far side; below about 0.9 the
# dimmest grains round to nothing and the turning forms thin out. scrim_gain scales the soft wash behind the forms.
# Text: the dark theme sets the captions in a soft ink halo, on a soft ellipse behind the caption line (text_backing:
# strength, horizontal and vertical margin). The light theme sets them on crisp plates instead (caption_plate per line,
# see _plate), with no halo and every edge and glyph on whole pixels (snap). text_halos and label_halos are the halo
# passes. The dark theme sets the labels in the dust's bright gold with an ink outline around each letter (label_outline:
# width outside the letter and alpha, in label_halo's colour) and no shadow, so no backing shows behind them. The light
# theme sets them in plain ink, like its dust, with a paper-coloured hairline that cannot be seen on a white page and
# keeps the letters readable over a dark window.
# The light theme's grain model. "dust" is the dark theme's own dust: its square grains, their size, and its gold,
# painted over the window instead of added to it, because added light cannot show on a white page. Two changes let it
# read there. Each grain is nearly opaque and has a twin a pixel away ("twins" lists the offsets), which doubles the
# density. And each colour keeps its hue and saturation but has LIGHT_DEPTH of its lightness: at full lightness the
# gold is nearly as light as white paper (contrast about 1.1 to 1); at 0.52 it is a deep gold that matches the contrast
# the dark dust has on a dark desktop (about 1.5 to 1). Darkening all three channels instead turns the gold khaki.
# "grains" is the earlier light look: deeper gold, round grains on a thin umber rim.
LIGHT_DEPTH = 0.52


def _deepen(rgb):
    h, lightness, s = colorsys.rgb_to_hls(*rgb)
    return colorsys.hls_to_rgb(h, lightness * LIGHT_DEPTH, s)


LIGHT_LOOKS = {
    "dust": {"description": "Deep gold dust with a few blue flecks.",
             "tones": [_deepen(tone) for tone in DUST_TONES], "blue": _deepen(DUST_BLUE), "ember": EMBER,
             "spark": PALE_GOLD,
             "spark_alpha": 0.12, "operator": cairo.OPERATOR_OVER, "alpha_floor": 0.85, "alpha_gain": 0.15,
             "size": 1.0, "round": False, "rim": None, "twins": ((1.1, 0.7),)},
    # The dust with no cool grains: the few that the dark theme draws blue are a deep pale gold here.
    "gold": {"description": "Deep gold dust, every grain gold.",
             "tones": [_deepen(tone) for tone in DUST_TONES], "blue": _deepen(PALE_GOLD), "ember": EMBER,
             "spark": PALE_GOLD, "spark_alpha": 0.12, "operator": cairo.OPERATOR_OVER, "alpha_floor": 0.85,
             "alpha_gain": 0.15, "size": 1.0, "round": False, "rim": None, "twins": ((1.1, 0.7),)},
    # The same grain in ink, pure black or warm umber, lighter and darker grains mixed so they do not read as print.
    "black": {"description": "Black and near-black grains, like graphite.",
              "tones": [(0.0, 0.0, 0.0), (0.12, 0.12, 0.12), (0.06, 0.06, 0.06)], "blue": (0.12, 0.12, 0.12),
              "ember": EMBER, "spark": PALE_GOLD, "spark_alpha": 0.0, "operator": cairo.OPERATOR_OVER,
              "alpha_floor": 0.5, "alpha_gain": 0.5, "size": 1.0, "round": False, "rim": None, "twins": ((1.1, 0.7),)},
    "umber": {"description": "Warm brown ink grains.",
              "tones": [(0.16, 0.12, 0.09), (0.26, 0.20, 0.14), (0.10, 0.08, 0.06)], "blue": (0.26, 0.20, 0.14),
              "ember": EMBER, "spark": PALE_GOLD, "spark_alpha": 0.0, "operator": cairo.OPERATOR_OVER,
              "alpha_floor": 0.5, "alpha_gain": 0.5, "size": 1.0, "round": False, "rim": None, "twins": ((1.1, 0.7),)},
    # Black ink with Rook's gold as an accent: the few grains that the dark theme draws blue are gold here.
    "ink_gold": {"description": "Black grains with a few gold ones among them.",
                 "tones": [(0.0, 0.0, 0.0), (0.12, 0.12, 0.12), (0.06, 0.06, 0.06)], "blue": _deepen(AMBER),
                 "ember": EMBER, "spark": PALE_GOLD, "spark_alpha": 0.0, "operator": cairo.OPERATOR_OVER,
                 "alpha_floor": 0.5, "alpha_gain": 0.5, "size": 1.0, "round": False, "rim": None,
                 "twins": ((1.1, 0.7),)},
    "grains": {"description": "The first light look: round gold grains on a thin brown rim.",
               "tones": [(0.86, 0.58, 0.10), (0.94, 0.70, 0.20), (0.80, 0.52, 0.08)], "blue": (0.24, 0.55, 0.95),
               "ember": (0.80, 0.18, 0.08), "spark": PALE_GOLD, "spark_alpha": 0.3,
               "operator": cairo.OPERATOR_OVER, "alpha_floor": 0.65, "alpha_gain": 0.35, "size": 1.2,
               "round": True, "rim": ((0.34, 0.20, 0.05), 0.5, 0.45)},
}
# "dust" draws the share of grains that the dark theme makes blue in a deepened blue, which reads as teal flecks on a
# light page; "gold" makes them gold. "black" and "ink_gold" are the dust in black ink, the second with gold accents.
# Rook sends {"light_dust": name} on stdin to switch the look live; relay.py reads these names and descriptions from
# this file without importing it, so each entry keeps a plain "description" string. The light_dust setting picks one.
LIGHT_LOOK = "ink_gold"
THEMES = {
    "dark": {"tones": DUST_TONES, "blue": DUST_BLUE, "ember": EMBER, "spark": PALE_GOLD, "spark_alpha": 0.12,
             "operator": cairo.OPERATOR_ADD, "alpha_floor": 0.0, "alpha_gain": 1.0, "size": 1.0,
             "scrim": INK, "scrim_gain": 1.0, "text": IVORY, "text_halo": INK, "label": DUST_TONES[1],
             "label_halo": INK, "label_outline": (1.4, 0.92), "note": ((1, 1, 1), (0, 0, 0)),
             "text_backing": (1.0, 56, CAPTION_TOP), "depth_floor": 0.9, "round": False, "rim": None,
             "text_halos": ((10, (0.9, 0.9)), (4, (0.95, 0.8))), "label_halos": (),
             "caption_plate": None, "label_plate": None, "snap": False, "sphere_gain": 1.0},
    # The light theme's grains are one of LIGHT_LOOKS, below. Captions are the dark theme's cream, set crisp on
    # charcoal plates. Labels are plain ink letters with a paper-coloured hairline.
    "light": {**LIGHT_LOOKS[LIGHT_LOOK],
              "scrim": (0.17, 0.10, 0.03), "scrim_gain": 0.0, "text": IVORY, "text_halo": INK,
              "label": (0.17, 0.10, 0.03), "label_halo": (0.97, 0.96, 0.93), "label_outline": (0.6, 0.8),
              "text_backing": None, "depth_floor": 0.9, "lit_accent": True,
              "text_halos": (), "label_halos": (), "snap": True,
              # The plates are a neutral charcoal: softer than near-black on a white page, still plainly dark.
              "caption_plate": {"fill": (0.21, 0.21, 0.21), "fill_alpha": 0.94, "radius": 8, "pad_x": 11, "pad_y": 6},
              "label_plate": None, "sphere_gain": 0.7,
              "note": ((0.1, 0.1, 0.1), (1, 1, 1))},
}
PALETTE = THEMES["dark"]


def _use_theme(name):
    """Swap the palette. Anything that baked in the old colours must be rebuilt: see Scene.retheme. A pack's lettering
    applies in the dark theme only, so the fonts may change too: see Scene.refont."""
    global PALETTE
    PALETTE = THEMES[name]
    if _PACK_TEXT:
        _apply_lettering()


def _use_light_look(name):
    """Swap the light theme's grains for LIGHT_LOOKS[name], in place, so a light PALETTE stays THEMES["light"]. Anything
    that baked in the old colours must be rebuilt: see Scene.retheme."""
    global LIGHT_LOOK
    light = THEMES["light"]
    for key in {key for look in LIGHT_LOOKS.values() for key in look}:  # Not every look has every key, such as twins.
        light.pop(key, None)
    light.update(LIGHT_LOOKS[name])
    LIGHT_LOOK = name

GRAINS = 640
SAND, TRICKLE = 200, 40  # The hourglass's sand in its two heaps, and its trickle; the rest draw the glass.
FORM_FOR_STATE = {"listening": "ear", "transcribing": "rows", "thinking": "lattice", "speaking": "sphere",
                  "permission": "question", "error": "sink"}
# Every other tool shows the lattice and THINKING. The find_* tools are WoWFriend's game lookups, which only arrive in
# WoW mode.
ACTIVITY_FORMS = {"find_npc": "figure2_a", "find_quest": "exclaim2_a", "find_item": "chest2_a",
                  "find_upgrades": "sword3_a", "find_price": ("coins2_a", "coins2_c"), "find_object": "pickaxe3_e",
                  "WebSearch": ("globe3_a", "globe3_c"), "WebFetch": ("globe3_a", "globe3_c"), "Grep": "magnifier", "Glob": "magnifier", "Read": "scan",
                  "Edit": "writing2_b", "Write": "writing2_a", "NotebookEdit": "writing2_b", "Bash": ("prompt3_b", "prompt2_c"), "Skill": "cog2_a",
                  "recall": "book2_a", "note": "book2_a", "forget": "book2_a",
                  "t3_thread_send": "send_turbine", "t3_thread_launch": "send_turbine", "handoff": "send_turbine",
                  "t3_pending_request": "send_turbine",  # rook.py names only an answer so; a list or read reads.
                  "t3_thread_read": ("message2_c", "message3_a"), "t3_queue": ("message2_c", "message3_a"),
                  "t3_thread_list": ("overlook3_b", "overlook3_d"), "t3_thread_search": ("overlook3_b", "overlook3_d"), "t3_thread_organize": ("overlook3_b", "overlook3_d"),
                  "t3_project_list": ("overlook3_b", "overlook3_d"), "t3_project_read": ("overlook3_b", "overlook3_d"), "t3_project_create": ("overlook3_b", "overlook3_d"),
                  "t3_project_clone": ("overlook3_b", "overlook3_d"), "t3_environment_links": ("overlook3_b", "overlook3_d"),
                  "t3_environment_read": ("overlook3_b", "overlook3_d"), "orchestrator_capabilities": ("overlook3_b", "overlook3_d"), "threads": ("overlook3_b", "overlook3_d"),
                  "t3_thread_interrupt": "power",
                  "screenshot": "eye2_c", "media": ("film2_b", "film3_c"), "git": "branch3_a",
                  "windows": ("tiles2_a", "tiles2_c"), "service": "power2_a",
                  "timer": "hourglass", "background": ("spinner2_b", "spinner2_c")}
# Finding something shows the prism: file search, search commands, and WoW waypoints.
ACTIVITY_FORMS.update(dict.fromkeys(pack_player.FIND_ACTIVITIES, "prism"))
# rook.py sends one of these in place of "Bash" when it knows what the command runs.
BASH_ACTIVITIES = ("screenshot", "media", "git", "windows", "service", "timer", "handoff", "threads", "background")
BASH_ACTIVITIES += ("find", "waypoint")
# A tuple in ACTIVITY_FORMS is a rotation: each appearance of the tool's form takes the next one and holds it while it
# shows. FORM_ROTATIONS counts each rotation's appearances.
FORM_ROTATIONS = {}
# find_upgrades also prices each upgrade from the auction scan, so it shows gear and prices in turn.
ACTIVITY_TURNS = {"find_upgrades": ("find_upgrades", "find_price")}
TURN_SECONDS = 2.2
ACTIVITY_LABELS = {"find_npc": "SEARCHING THE MAP", "find_object": "FINDING THE OBJECT",
                   "find_quest": "FINDING THE QUEST", "find_item": "FINDING THE ITEM", "find_upgrades": "RANKING GEAR",
                   "find_price": "CHECKING PRICES",
                   "WebSearch": "SEARCHING THE WEB", "WebFetch": "SEARCHING THE WEB", "Grep": "SEARCHING FILES",
                   "Glob": "SEARCHING FILES", "Read": "READING", "Edit": "WRITING", "Write": "WRITING",
                   "NotebookEdit": "WRITING", "Bash": "RUNNING A COMMAND", "Skill": "LOADING A SKILL",
                   "recall": "CHECKING THE NOTEBOOK", "note": "CHECKING THE NOTEBOOK", "forget": "CHECKING THE NOTEBOOK",
                   "t3_thread_send": "SENDING TO AGENT", "t3_thread_launch": "STARTING A THREAD",
                   "handoff": "SENDING TO AGENT", "t3_thread_read": "READING A THREAD",
                   "t3_pending_request": "SENDING TO AGENT", "t3_queue": "CHECKING THE QUEUE",
                   "t3_thread_list": "LOOKING AT THREADS", "threads": "LOOKING AT THREADS",
                   "t3_thread_search": "SEARCHING THREADS", "t3_thread_organize": "SORTING THREADS",
                   "t3_project_list": "LOOKING AT PROJECTS", "t3_project_read": "LOOKING AT PROJECTS",
                   "t3_project_create": "ADDING A PROJECT", "t3_project_clone": "ADDING A PROJECT",
                   "t3_environment_links": "CHECKING THE MACHINES", "t3_environment_read": "CHECKING THE MACHINES",
                   "orchestrator_capabilities": "CHECKING T3", "t3_thread_interrupt": "STOPPING A THREAD",
                   "screenshot": "TAKING A SCREENSHOT", "media": "WORKING ON VIDEO", "git": "USING GIT",
                   "windows": "MANAGING WINDOWS", "service": "CHECKING A SERVICE", "timer": "SETTING A TIMER",
                   "background": "RUNNING A LONG JOB"}
ACTIVITY_LABELS.update(find="SEARCHING FILES", waypoint="SETTING A WAYPOINT")
# Turning speed (radians per second) of the three-dimensional forms.
SPIN = {"lattice": 0.4, "sphere": 0.25, "globe": 0.35, "ear": 0.3, "rook": 0.45}
# Plain thinking (no tool with its own form) takes turns between the lattice and the rook, this long each,
# starting on the lattice.
THINK_TURN = 4.0
# The video-recording debug replay's arm mark: the resting loop brightens this much and fades back over this long.
REPLAY_PULSE_GAIN, REPLAY_PULSE_SECONDS, REPLAY_PULSE_WIDTH = 0.25, 1.1, 0.55  # Band over full light, one lap (s), half-width (rad).
# The rook's profile as (y, radius) from the base's top up to the crown floor; y points down, the centre is 0.
ROOK_PROFILE = [(44, 34), (40, 30), (36, 25), (-14, 19), (-18, 26), (-24, 26), (-27, 21), (-44, 31)]
# Rings as (radius, y, grains): the base's bottom edge and steps, the collar, and the crown floor's two edges.
ROOK_RINGS = [(40, 58, 46), (40, 51, 38), (36, 51, 30), (36, 45, 30), (26, -18, 26), (26, -24, 26),
              (31, -44, 38), (21, -44, 22)]
ROOK_MERIDIANS, ROOK_MERIDIAN_GRAINS = 9, 18
ROOK_MERLONS, ROOK_MERLON_SHARE = 5, 0.5
ROOK_CROWN_FLOOR, ROOK_CROWN_TOP = -44, -61
# The listening form for each --listen style. The orb is the default; the others are waveform designs.
LISTEN_STYLES = {"orb": "ear", "halo": "halo", "helix": "helix", "ridges": "ridges", "burst": "burst"}
LISTEN_FORMS = set(LISTEN_STYLES.values())
# The helix sits this far below the other forms' centre. It is a slim band in silence, and centred like the rest it
# floats far above the label line, which stays fixed.
HELIX_DROP = 16
# With several styles given, each turn uses the next one.
LISTEN_CYCLE = []
# Each send takes the next send form: the turbine, then the array. A send steps the cycle as its form starts, so the
# first send is the turbine. A send form shows only while its fan does; the send tools' entries in ACTIVITY_FORMS name
# the cycle for the labels and the contact sheet, and their turn shows the thinking forms until the fan.
SEND_CYCLE = ["send_array", "send_turbine"]
# Where ripples start on the listening orb: facing the viewer, a little up and to the right.
EAR_POLE = (0.26, -0.22, 0.94)
# While Rook speaks, each syllable sends one wave over the globe, from EAR_POLE to the far side.
# SPEAK_RIPPLE is how far a full wave swells the globe, as a share of its radius.
SPEAK_RIPPLE = 0.3
# The globe's springs while it speaks. They are soft, because the waves are already smooth.
SPEAK_PACE = 1.5
# The voice envelope rises in SPEAK_ATTACK seconds and falls in SPEAK_RELEASE seconds.
SPEAK_ATTACK, SPEAK_RELEASE = 0.04, 0.12
# A syllable starts when the envelope rises this much from its last dip. Two waves start at least WAVE_GAP apart.
WAVE_RISE, WAVE_GAP = 0.1, 0.15
# A wave crosses the globe in WAVE_SECONDS. Its ring is WAVE_WIDTH radians to each side. At most WAVE_MAX run at once.
WAVE_SECONDS, WAVE_WIDTH, WAVE_MAX = 1.1, 0.7, 6
TILT = 0.38

def _font(family, px, weight=Pango.Weight.NORMAL):
    desc = Pango.FontDescription()
    desc.set_family(family)
    desc.set_weight(weight)
    desc.set_absolute_size(px * Pango.SCALE)
    return desc


CAPTION_FONT = _font("Noto Serif", 21, Pango.Weight.BOLD)
LABEL_FONT = _font("Noto Serif", 10, Pango.Weight.HEAVY)
LABEL_SPACING = 2.4
CAPTION_LINE_SPACING = 1.35
# Font options for the captions and labels, which the owner switches by voice: Rook sends {"font": name} on stdin,
# and --font sets one at start. fonts.json lists them, and its first entry is the look above, the default.
try:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts.json")) as _fonts:
        FONTS = {entry["name"]: entry for entry in json.load(_fonts)}
except (OSError, ValueError, KeyError, TypeError):
    FONTS = {}


CAPTION_SPACING = 0.0  # Letter spacing of the captions, in pixels; only a pack's lettering sets it.
_FONT_ENTRY = None  # The voice font in force, or None for fonts.json's first entry, the default.

# A pack's own lettering: the manifest's "text" block (themes/forge/FORMAT.md), resolved by _pack_lettering. LETTERING
# is that block while it applies, else None for today's lettering. It applies in the dark theme with the default voice
# font: the light theme keeps its ink labels and caption plates, and a font the owner picked by voice wins.
LETTERING = None
_PACK_TEXT = None  # The active pack's resolved text block, whether or not it applies now.
_TEXT_KINDS = {  # Each key's default, used when the block is there but leaves a key out.
    "label": {"size": 10, "weight": 900, "case": "upper", "tracking": 0.24, "color": "core", "rim": True},
    "name": {"size": 11, "weight": 900, "case": "upper", "tracking": 0.22, "color": "core", "rim": True},
    "caption": {"size": 21, "weight": 700, "case": "as written", "tracking": 0.0, "color": "core", "rim": False},
}
_FONT_FILES = set()  # Font files already added to Pango's font map.


def _use_font(entry):
    """Swap the caption and label fonts. Anything laid out in the old font must be rebuilt: see Scene.refont."""
    global _FONT_ENTRY
    _FONT_ENTRY = None if entry is next(iter(FONTS.values()), None) else entry
    _apply_lettering()


def _apply_lettering():
    """Set the caption and label fonts: the pack's lettering when it applies, else the voice font."""
    global CAPTION_FONT, CAPTION_LINE_SPACING, CAPTION_SPACING, LABEL_FONT, LABEL_SPACING, LETTERING
    LETTERING = _PACK_TEXT if _PACK_TEXT and PALETTE is THEMES["dark"] and _FONT_ENTRY is None else None
    CAPTION_SPACING = 0.0
    if LETTERING:
        caption, label = LETTERING["caption"], LETTERING["label"]
        CAPTION_FONT, LABEL_FONT = caption["font"], label["font"]
        CAPTION_LINE_SPACING, CAPTION_SPACING, LABEL_SPACING = 1.35, caption["spacing"], label["spacing"]
        return
    entry = _FONT_ENTRY or next(iter(FONTS.values()), None)
    if entry is None:
        CAPTION_FONT, CAPTION_LINE_SPACING, LABEL_FONT, LABEL_SPACING = _DEFAULT_FONTS
        return
    caption, label = entry["caption"], entry["label"]
    CAPTION_FONT = _font(caption["family"], caption["size"], Pango.Weight(caption["weight"]))
    CAPTION_LINE_SPACING = caption["line_spacing"]
    LABEL_FONT = _font(label["family"], label["size"], Pango.Weight(label["weight"]))
    LABEL_SPACING = label["spacing"]


_DEFAULT_FONTS = (CAPTION_FONT, CAPTION_LINE_SPACING, LABEL_FONT, LABEL_SPACING)


def _pack_lettering(pack):
    """A pack's text block with every key filled in and its font file loaded, or None for today's lettering. Cached on
    the pack. It never raises: a bad block or font logs once and keeps today's lettering."""
    if "_lettering" in pack:
        return pack["_lettering"]
    raw, out = pack.get("text"), None
    if isinstance(raw, dict):
        try:
            fonts = PangoCairo.FontMap.get_default()
            path = pack_player.pack_font_file(pack)
            if path and path not in _FONT_FILES:
                if not fonts.add_font_file(path):
                    raise ValueError(f"Pango could not load {os.path.basename(path)}")
                _FONT_FILES.add(path)
            family = raw.get("family", "Noto Serif")
            if family not in {f.get_name() for f in fonts.list_families()}:
                raise ValueError(f"font family {family!r} is not available")
            palette = pack.get("palette") if isinstance(pack.get("palette"), dict) else {}

            def colour(spec, fallback):
                code = palette.get(spec, spec)
                return pack_player._hex_rgb(code if isinstance(code, str) else "", fallback)

            def ranged(value, low, high, what):
                value = float(value)
                if not low <= value <= high:  # NaN fails too.
                    raise ValueError(f"{what} must be {low} to {high}")
                return value

            def stroke(name, width, alpha, rgb):
                spec = raw.get(name) or {}
                return (ranged(spec.get("width", width), 0, 3, f"{name}.width"),
                        ranged(spec.get("alpha", alpha), 0, 1, f"{name}.alpha"), colour(spec.get("color"), rgb))

            out = {"reveal": "none" if raw.get("reveal") == "none" else "spread",
                   "outline": stroke("outline", 0.6, 0.85, INK), "rim": stroke("rim", 0.32, 0.9, (0.91, 0.69, 0.29))}
            for kind, default in _TEXT_KINDS.items():
                spec = {**default, **(raw.get(kind) or {})}
                size = ranged(spec["size"], 6, 48, f"{kind}.size")
                weight = int(ranged(spec["weight"], 100, 900, f"{kind}.weight"))
                out[kind] = {"font": _font(family, size, Pango.Weight(weight)),
                             "spacing": ranged(spec["tracking"], 0, 1, f"{kind}.tracking") * size,
                             "case": spec["case"], "rim": bool(spec["rim"]),
                             "color": colour(spec["color"], (1.0, 0.953, 0.839))}
        except (ValueError, TypeError, KeyError, AttributeError, OSError, GLib.Error) as error:
            print(f"theme pack {pack.get('name')!r} text: {error}; keeping today's lettering", file=sys.stderr,
                  flush=True)
            out = None
    pack["_lettering"] = out
    return out


def _use_pack_text(pack):
    """Take the pack's lettering, at pack load. Anything laid out in the old font must be rebuilt: see Scene.refont."""
    global _PACK_TEXT
    _PACK_TEXT = _pack_lettering(pack) if isinstance(pack, dict) else None
    _apply_lettering()


def _cased(text, kind):
    """text in the case the pack's lettering sets for kind: "upper", "lower", or as written."""
    case = LETTERING[kind]["case"] if LETTERING else None
    return text.upper() if case == "upper" else text.lower() if case == "lower" else text

# The guide's line during the first listen of an {"until": "listening"} guide. The talk key holds or toggles.
GUIDE_LISTENING = "Let go, or tap again, when you're done"
# Where the top of the guide's letters sits: this far below the resting loop's centre, or in the caption area at
# GUIDE_TOP with no caption showing and at GUIDE_BELOW under a caption's two lines. GUIDE_GAP is the space between the
# code's letters and the text's. The code is the caption lettering at GUIDE_CODE_SCALE times its size, with
# GUIDE_CODE_TRACK em of extra tracking. While a code guide sits in the caption area, the area grows by GUIDE_ROOM so
# the guide under a two-line caption keeps 24 px clear of the area's bottom (see _check_render).
GUIDE_REST_DY, GUIDE_TOP, GUIDE_BELOW, GUIDE_GAP = 62, 16, 124, 11
GUIDE_CODE_SCALE, GUIDE_CODE_TRACK, GUIDE_ROOM = 1.8, 0.08, 40
# At home the main area grows only to the guide's widest line plus GUIDE_MARGIN on each side, for its outline and rim.
GUIDE_MARGIN = 20

# How strongly the small state labels are painted: 0.9 keeps them legible on white and busy pages.
LABEL_ALPHA = 0.9

# The last-answer panel: the full written answer in a terminal-style window of its own, opened from the captions or
# the resting loop. Its text can be selected and copied. It is the same dark terminal surface in both themes, with
# gold as its one accent colour, set in the owner's terminal font.
PANEL_OPEN_SECONDS = 0.2
ANSWER_HISTORY = 10  # The panel keeps this many answers; its arrows step through them.
HISTORY_BACK, HISTORY_NEXT, HISTORY_DIM = "←", "→", 0.35  # The arrows, and how faint one is at an end of the list.
LOOP_HIT = (148, 68)
# The owner can drag Rook aside. A press that moves less than DRAG_START logical pixels is a click. Rook flies home
# RETURN_SECONDS after the release.
DRAG_START = 8
RETURN_SECONDS = 4.0
# During a turn Rook follows the focused monitor once focus has stayed there this long, so a brief pass of the pointer
# over the other screen does not move it.
FOLLOW_SETTLE_MS = 600
# At rest it waits this long too, so the dust does not hop between displays each time the pointer crosses.
FOLLOW_REST_MS = 700
TERM_W = 900  # The widest it gets; a narrower monitor or game window gets less.
TERM_SHARE = 0.7  # The tallest it gets, as a share of the monitor's (or the game window's) height.
TERM_MARGIN = 16  # It always stays this far inside the monitor or the game window.
TERM_PX = 13
TERM_HEAD_H = 34
TERM_PAD_X, TERM_PAD_TOP, TERM_PAD_BOTTOM = 18, 12, 16
TERM_GAP, TERM_HEADING_GAP, TERM_CODE_INSET = 10, 18, 12
TERM_BG = (0.043, 0.047, 0.059)
TERM_FG = (0.86, 0.84, 0.78)
TERM_DIM = (0.52, 0.52, 0.55)
TERM_CODE_BG = (1.0, 0.92, 0.70, 0.055)
TERM_FONTS = ["JetBrainsMono Nerd Font", "JetBrains Mono", "Noto Sans Mono", "monospace"]
CODE_TINT = (0.76, 0.86, 0.98)
LINK_TINT = (0.96, 0.78, 0.48)

# The media viewer: a black box opens in place in the media's shape, framed by a single fine edge of dust.
# Sizes are logical pixels of the free area of the monitor (or of the game window in WoW mode).
VIEW_SHARE_W, VIEW_SHARE_H = 0.72, 0.62  # The box is at most this share of the width and of the height.
VIEW_CENTRE = 0.47  # The box's centre sits at this share of the height, a little above the middle.
VIEW_BELOW = 130  # Room kept under the box for the title or the state label and two lines of captions.
VIEW_EDGE = 24  # The box always stays this far inside the area.
VIEW_MIN = 220  # The box's shorter side never goes below this; a smaller picture sits in a wider black matte.
VIEW_TINY, VIEW_TINY_TO = 128, 192  # A picture whose longer side is at most VIEW_TINY device pixels is an icon: it
# grows by a whole factor, pixel for pixel, to about VIEW_TINY_TO logical pixels. Nothing else is ever enlarged.
VIEW_RADIUS = 6  # The black box's corner radius.
VIEW_OPEN, VIEW_IN, VIEW_OUT, VIEW_SHUT, VIEW_MORPH = 0.24, 0.26, 0.18, 0.22, 0.30  # Seconds per step; see Portal.
VIEW_MEDIA_AT = 0.06  # Media starts fading in right as the box opens, reaching full size by ~0.32 s.
VIEW_GATHER, VIEW_LAG = 0.22, 0.12  # Edge dust wakes in place and settles onto the border by ~0.34 s.
VIEW_DISSOLVE, VIEW_DISSOLVE_LAG = 0.20, 0.10  # Edge dust fades away evenly as the viewer closes.
VIEW_SWARM_FADE = 0.20  # Main resting swarm fades out on open and back in on close over this many seconds.
VIEW_END_HOLD = 1.2  # A video rests on its last frame this long, then the viewer closes.
VIEW_DRIFT, VIEW_WAVE = 10.0, 18.0
VIEW_LINE_DY, VIEW_CAPTION_DY, VIEW_STRIP = 20, 6, 32
VIEW_HOVER_GRACE = 0.8  # Seconds the viewer's controls stay after the pointer leaves, so it can reach them.
VIEW_CLOSE_SIZE = 32  # The close X in the box's top-right corner, in points: big enough to hit at once.
# Single-row edge style.
#   matte: black margin between the media and the box's edge, as a share of the media's shorter side, clamped.
#   dust, density: max grain pool and target grains per pixel of perimeter so tiny and wide boxes match.
#   round, round_max: outer corner radius as a share of the margin, capped so corners stay round with >= 8 px of black.
#   band, band_max, spread, band_glow: inset from the outer edge (capped at band_max px), radial spread, and base glow.
VIEW_FRAMES = {
    "single": {"matte": (0.030, 16, 26), "dust": 2400, "density": 0.42, "round": 1.80, "round_max": 44.0,
               "band": 0.35, "band_max": 6.0, "spread": 0.72, "band_glow": 1.75},
}
VIEW_FRAME = "single"
# Who draws the open viewer's still frame of dust: "gl", the default, draws it on the graphics chip (see _DustGL);
# "cairo" is the fallback when GL fails and the reference the GL frame is checked against. The ROOK_VIEW_DUST
# environment variable overrides it, for tests.
VIEW_DUST = os.environ.get("ROOK_VIEW_DUST", "gl")
# The main window's dust on a Wayland surface of its own (see _DustSurface), so GTK's frame clock rests while only the
# dust moves. Off until it is proven on the live screen; ROOK_DUST_SURFACE=1 turns it on for one run.
DUST_SURFACE = os.environ.get("ROOK_DUST_SURFACE") == "1"
# For a live test: ROOK_DUST_FRAMES=<file> logs each frame of the dust surface (when, the gap since the last, its cost).
DUST_FRAMES = os.environ.get("ROOK_DUST_FRAMES")
VIEW_DUCK = 0.25  # A video's sound drops to this during a turn, so Rook hears the owner over it.
VIEW_AUDIO_SINK = None  # None plays through the desktop's sound; a test sets "fakesink".


def _mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def _glide(dt, tau):
    return 1 - math.exp(-dt / tau)


def _ease_out(p):
    p = min(1.0, max(0.0, p))
    return 1 - (1 - p) ** 3


def _smooth(p):
    p = min(1.0, max(0.0, p))
    return p * p * (3 - 2 * p)


def _ease_away(p):
    """1 at the start of a fade-out, 0 at its end, gentle at both ends."""
    p = min(1.0, max(0.0, p))
    return 0.5 + 0.5 * math.cos(math.pi * p)


def _hypr(*args):
    try:
        out = subprocess.run(["hyprctl", *args, "-j"], capture_output=True, text=True, timeout=1)
        return json.loads(out.stdout)
    except Exception:
        return None


def _placement(display, game=False):
    """Monitor, left and top margins, lift (how far below the window top the working canvas starts),
    the logical height of the focused monitor, rest pad (how far below the window top the resting loop's
    centre sits), the game window's top-left corner and scale on its monitor (or None), and the bounds the
    last-answer panel must stay inside, as (x, y, width, height) in the same margin coordinates: the monitor's area
    left free by bars, or the game window within it.
    One window covers rest and work without resizing. It starts at the top edge, so grains that
    overshoot the loop on their way home are not cut off; the loop and the working forms keep their places.
    With game (WoW mode, the game focused) everything is placed inside the game window on its monitor, as
    WoWFriend placed it; otherwise as if a full-screen window filled the focused monitor."""
    monitors = _hypr("monitors") or []
    wow = next((c for c in _hypr("clients") or [] if c.get("title") == GAME_TITLE), None) if game else None
    mon = None
    if wow:
        mon = next((m for m in monitors if m.get("id") == wow.get("monitor")), None)
    if mon is None:
        mon = next((m for m in monitors if m.get("focused")), None)
    if not mon:
        return None, None, 0, FALLBACK_LIFT + FALLBACK_TOP, None, REST_PAD + FALLBACK_TOP, None, None
    gdk_mon = None
    items = display.get_monitors()
    for i in range(items.get_n_items()):
        if items.get_item(i).get_connector() == mon["name"]:
            gdk_mon = items.get_item(i)
    scale = mon.get("scale") or 1
    at = wow["at"] if wow else (mon["x"], mon["y"])
    size = wow["size"] if wow else (mon["width"], mon["height"])
    game_left, window_top = (at[0] - mon["x"]) / scale, (at[1] - mon["y"]) / scale
    left = max(0, int(game_left + size[0] / scale / 2 - WIDTH / 2))
    height = size[1] / scale
    top = max(0, int(window_top + height * REST_SHARE - REST_PAD))
    lift = max(0, int(window_top + height * TOP_SHARE) - GRAIN_INSET - top)
    # Layer-shell margins count from the area left free by exclusive bars; hyprctl reports them as reserved
    # [left, top, right, bottom].
    rl, rt, rr, rb = (mon.get("reserved") or [0, 0, 0, 0])[:4]
    free_w, free_h = mon["width"] / scale - rl - rr, mon["height"] / scale - rt - rb
    bx, by = max(0.0, game_left - rl), max(0.0, window_top - rt)
    bounds = (bx, by, min(free_w, game_left - rl + size[0] / scale) - bx, min(free_h, window_top - rt + height) - by)
    return (gdk_mon, left, 0, lift + top, height, REST_PAD + top, (game_left, window_top, scale) if wow else None,
            bounds)


def _reader_box(card, left, top, lift):
    """The surface for the reading flight, in monitor coordinates: it covers the card, the label under it,
    and the overlay's working area, so the grains can travel the whole way."""
    x, y, w, h = card
    x0, y0 = max(0, int(min(x - 30, left))), max(0, int(min(y - 30, top)))
    x1, y1 = int(max(x + w + 30, left + WIDTH)), int(max(y + h + 50, top + lift + ORB_H))
    return x0, y0, x1 - x0, y1 - y0


def _rounded_rect(cr, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def _scrim(cr, cx, cy, rx, ry, alpha, gain=None):
    """A soft ellipse in the palette's scrim colour, densest at the centre and transparent at its edge.
    gain scales it; by default the palette's scrim_gain."""
    alpha *= PALETTE["scrim_gain"] if gain is None else gain
    if alpha <= 0.002:
        return
    grad = cairo.RadialGradient(0, 0, 0, 0, 0, 1)
    for stop, a in ((0, 1.0), (0.2, 0.92), (0.45, 0.66), (0.65, 0.38), (0.82, 0.15), (0.93, 0.04), (1, 0.0)):
        grad.add_color_stop_rgba(stop, *PALETTE["scrim"], a * alpha)
    cr.save()
    cr.translate(cx, cy)
    cr.scale(rx, ry)
    cr.arc(0, 0, 1, 0, 2 * math.pi)
    cr.set_source(grad)
    cr.fill()
    cr.restore()


def _shown_lines(sentence, clock, scale):
    """Per line, the box (x0, y0, x1, y1) of the letters revealed so far and how far its first word has come in.
    A new word grows the line from where its edge already is, easing in and out, so the edge never jumps. The box
    starts a little before its word fades in, so a plate always covers the word it carries."""
    lines = {}
    for sprite, x, y, at in sentence.sprites:
        p = min(1.0, (clock - at) / WORD_IN + 0.35)
        if p <= 0:
            break
        q = p * p * (3 - 2 * p)
        # The sprite carries a 14 px pad around the word on every side; words on one line share the same y.
        w, h = sprite.get_width() / scale - 28, sprite.get_height() / scale - 28
        y0, y1 = y + 14, y + 14 + h
        line = lines.get(round(y))
        start = line[0][2] if line else x + 14
        x1 = start + (x + 14 + w - start) * q
        lines[round(y)] = ((x + 14, y0, x1, y1), q) if line is None else (
            (line[0][0], y0, max(line[0][2], x1), y1), line[1])
    return list(lines.values())


def _device_round(cr, x, y):
    """The point moved to the nearest whole device pixel, in user space, so edges and glyphs land on the pixel grid."""
    dx, dy = cr.user_to_device(x, y)
    return cr.device_to_user(round(dx), round(dy))


def _plate(cr, x, y, w, h, plate, alpha):
    """A crisp plate behind light text: a rounded rectangle whose edges land on whole device pixels, filled with the
    plate colour. No blur anywhere. Returns the rectangle and radius it drew, or None."""
    if alpha <= 0.002 or w <= 0:
        return None
    x0, y0 = _device_round(cr, x, y)
    x1, y1 = _device_round(cr, x + w, y + h)
    w, h = x1 - x0, y1 - y0
    r = min(plate["radius"], h / 2, w / 2)
    _rounded_rect(cr, x0, y0, w, h, r)
    cr.set_source_rgba(*plate["fill"], plate["fill_alpha"] * alpha)
    cr.fill()
    return x0, y0, w, h, r


def _hold(d, rise, hold, fall):
    """0 to 1 and back: eased rise, a hold, eased fall. d is the time since the start."""
    if d <= 0 or d >= rise + hold + fall:
        return 0.0
    if d < rise:
        p = d / rise
    elif d < rise + hold:
        return 1.0
    else:
        p = 1 - (d - rise - hold) / fall
    return p * p * (3 - 2 * p)


def _shape_figure(cr):
    cr.arc(0, -26, 19, 0, 2 * math.pi)
    cr.fill()
    cr.save()
    cr.translate(0, 56)
    cr.scale(48, 48)
    cr.arc(0, 0, 1, math.pi, 2 * math.pi)
    cr.restore()
    cr.fill()


def _shape_exclaim(cr):
    cr.move_to(-11, -60)
    cr.line_to(11, -60)
    cr.line_to(6, 20)
    cr.line_to(-6, 20)
    cr.close_path()
    cr.fill()
    cr.arc(0, 44, 11, 0, 2 * math.pi)
    cr.fill()


def _shape_chest(cr):
    cr.rectangle(-52, -6, 104, 48)
    cr.move_to(-52, -6)
    cr.curve_to(-52, -48, 52, -48, 52, -6)
    cr.close_path()
    cr.fill()
    cr.set_operator(cairo.OPERATOR_DEST_OUT)
    cr.set_line_width(4)
    cr.move_to(-54, -6)
    cr.line_to(54, -6)
    for x in (-30, 30):
        cr.move_to(x, -40)
        cr.line_to(x, 44)
    cr.stroke()
    cr.rectangle(-8, -12, 16, 16)
    cr.fill()


def _shape_sword(cr):
    for points in (((0, -68), (9, -54), (9, 16), (-9, 16), (-9, -54)), ((-32, 16), (32, 16), (32, 26), (-32, 26)),
                   ((-5, 26), (5, 26), (5, 48), (-5, 48))):
        cr.move_to(*points[0])
        for p in points[1:]:
            cr.line_to(*p)
        cr.close_path()
        cr.fill()
    cr.arc(0, 56, 8, 0, 2 * math.pi)
    cr.fill()


def _shape_coins(cr):
    cr.translate(0, -8)
    for dx, y in ((-4, 30), (4, 12), (-2, -6)):
        _rounded_rect(cr, dx - 42, y, 84, 15, 7)
        cr.fill()
    cr.save()
    cr.translate(-2, -14)
    cr.scale(42, 14)
    cr.arc(0, 0, 1, 0, 2 * math.pi)
    cr.restore()
    cr.fill()
    cr.set_operator(cairo.OPERATOR_DEST_OUT)
    cr.set_line_width(3.5)
    for y in (28.5, 10.5):
        cr.move_to(-50, y)
        cr.line_to(50, y)
    cr.stroke()
    cr.save()
    cr.translate(-2, -14)
    cr.scale(30, 8.5)
    cr.arc(0, 0, 1, 0, 2 * math.pi)
    cr.restore()
    cr.stroke()


def _shape_pickaxe(cr):
    cr.rotate(math.radians(35))
    cr.rectangle(-5, -46, 10, 108)
    cr.fill()
    cr.move_to(-56, -22)
    cr.curve_to(-32, -64, 32, -64, 56, -22)
    cr.curve_to(28, -46, -28, -46, -56, -22)
    cr.close_path()
    cr.fill()


def _shape_magnifier(cr):
    cr.arc(-12, -12, 36, 0, 2 * math.pi)
    cr.fill()
    cr.save()
    cr.translate(-12, -12)
    cr.rotate(math.pi / 4)
    _rounded_rect(cr, 30, -8, 46, 16, 6)
    cr.restore()
    cr.fill()
    cr.set_operator(cairo.OPERATOR_CLEAR)
    cr.arc(-12, -12, 24, 0, 2 * math.pi)
    cr.fill()
    cr.set_operator(cairo.OPERATOR_OVER)
    # A glint on the glass.
    cr.set_line_width(5)
    cr.arc(-12, -12, 15, math.radians(195), math.radians(255))
    cr.stroke()


def _shape_page(cr):
    cr.move_to(-40, -56)
    cr.line_to(16, -56)
    cr.line_to(42, -30)
    cr.line_to(42, 56)
    cr.line_to(-40, 56)
    cr.close_path()
    cr.fill()
    cr.set_operator(cairo.OPERATOR_DEST_OUT)
    cr.set_line_width(6)
    cr.move_to(13, -58)
    cr.line_to(13, -27)
    cr.line_to(44, -27)
    cr.stroke()
    for y, w in ((-38, 34), (-20, 62), (-4, 54), (12, 62), (28, 44)):
        cr.rectangle(-28, y, w, 6)
    cr.fill()


def _shape_quill(cr):
    cr.save()
    cr.translate(6, -6)
    cr.rotate(math.radians(40))
    # The vane, wider on one side, then the bare shaft and the nib.
    cr.move_to(0, -64)
    cr.curve_to(26, -44, 24, 4, 4, 30)
    cr.line_to(-4, 30)
    cr.curve_to(-16, 6, -18, -40, 0, -64)
    cr.close_path()
    cr.fill()
    cr.move_to(-5, 28)
    cr.line_to(5, 28)
    cr.line_to(3, 52)
    cr.line_to(0, 62)
    cr.line_to(-3, 52)
    cr.close_path()
    cr.fill()
    cr.set_operator(cairo.OPERATOR_CLEAR)
    cr.set_line_width(4)
    cr.move_to(0, -56)
    cr.curve_to(2, -30, 2, 0, 0, 30)
    cr.stroke()
    cr.set_line_width(5)
    for y, side in ((-38, 1), (-14, 1), (-26, -1), (0, -1)):
        cr.move_to(side * 30, y - 12)
        cr.line_to(side * 9, y)
    cr.stroke()
    cr.restore()
    cr.set_operator(cairo.OPERATOR_OVER)
    # A short stroke of ink under the nib.
    cr.set_line_width(5)
    cr.move_to(-62, 62)
    cr.curve_to(-50, 54, -40, 66, -26, 58)
    cr.stroke()


def _shape_prompt(cr):
    cr.set_line_width(17)
    cr.set_line_join(cairo.LINE_JOIN_MITER)
    cr.move_to(-50, -34)
    cr.line_to(-14, 0)
    cr.line_to(-50, 34)
    cr.stroke()
    cr.rectangle(4, 22, 46, 14)
    cr.fill()


def _shape_cog(cr):
    cr.arc(0, 0, 40, 0, 2 * math.pi)
    cr.fill()
    for k in range(8):
        cr.save()
        cr.rotate(k * math.pi / 4)
        cr.rectangle(-9, -56, 18, 20)
        cr.restore()
        cr.fill()
    cr.set_operator(cairo.OPERATOR_CLEAR)
    cr.arc(0, 0, 16, 0, 2 * math.pi)
    cr.fill()


def _shape_book(cr):
    # Two pages fall away from a raised spine, with text lines that follow their slant, and the cover below.
    slope = 0.36
    for side in (-1, 1):
        cr.move_to(side * 5, -42)
        cr.line_to(side * 64, -42 + 59 * slope)
        cr.line_to(side * 64, 38)
        cr.line_to(side * 5, 38 - 59 * slope)
        cr.close_path()
        cr.fill()
        cr.set_line_width(7)
        cr.move_to(0, 25)
        cr.line_to(side * 66, 25 + 66 * slope)
        cr.stroke()
    cr.set_operator(cairo.OPERATOR_CLEAR)
    cr.set_line_width(5)
    for y in (-27, -14, -1, 12):
        for side in (-1, 1):
            cr.move_to(side * 14, y + 14 * slope)
            cr.line_to(side * 54, y + 54 * slope)
    cr.stroke()


def _shape_question(cr):
    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(_font("Noto Serif", 128, Pango.Weight.BOLD))
    layout.set_text("?", -1)
    ink, _ = layout.get_pixel_extents()
    cr.move_to(-ink.x - ink.width / 2, -ink.y - ink.height / 2)
    PangoCairo.show_layout(cr, layout)


def _shape_message(cr):
    # Reading a thread: one speech bubble with three lines of text in it.
    cr.set_line_width(7)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    _rounded_rect(cr, -52, -42, 104, 66, 17)
    cr.stroke()
    cr.move_to(-30, 24)
    cr.line_to(-40, 46)
    cr.line_to(-12, 24)
    cr.stroke()
    for y, w in ((-22, 64), (-8, 50), (6, 58)):
        cr.move_to(-32, y)
        cr.line_to(-32 + w, y)
    cr.stroke()


def _shape_overlook(cr):
    # Looking at threads: a small cube, as the thinking lattice is a cube, hovers over three threads drawn as rows.
    # The cube shows only its near edges, a hexagon with a Y inside, so it reads crisply while it holds still.
    cr.set_line_width(5.5)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cx, cy, r = 0, -32, 25
    corner = [(cx + r * math.cos(math.pi / 6 + k * math.pi / 3), cy + r * math.sin(math.pi / 6 + k * math.pi / 3))
              for k in range(6)]
    cr.move_to(*corner[0])
    for p in corner[1:]:
        cr.line_to(*p)
    cr.close_path()
    for k in (1, 3, 5):
        cr.move_to(cx, cy)
        cr.line_to(*corner[k])
    cr.stroke()
    cr.set_line_width(6)
    for y, w in OVERLOOK_ROWS:
        cr.arc(-40, y, 5.5, 0, 2 * math.pi)
        cr.fill()
        cr.move_to(-26, y)
        cr.line_to(-26 + w, y)
        cr.stroke()


def _shape_eye(cr):
    # An open eye: the lids, the iris as a ring, the pupil, and a glint on it.
    cr.move_to(-66, 0)
    cr.curve_to(-30, -50, 30, -50, 66, 0)
    cr.curve_to(30, 50, -30, 50, -66, 0)
    cr.close_path()
    cr.fill()
    cr.set_operator(cairo.OPERATOR_CLEAR)
    cr.move_to(-54, 0)
    cr.curve_to(-24, -38, 24, -38, 54, 0)
    cr.curve_to(24, 38, -24, 38, -54, 0)
    cr.close_path()
    cr.fill()
    cr.set_operator(cairo.OPERATOR_OVER)
    cr.arc(0, 0, 24, 0, 2 * math.pi)
    cr.fill()
    cr.set_operator(cairo.OPERATOR_CLEAR)
    cr.arc(0, 0, 16, 0, 2 * math.pi)
    cr.fill()
    cr.set_operator(cairo.OPERATOR_OVER)
    cr.arc(0, 0, 10, 0, 2 * math.pi)
    cr.fill()
    cr.set_operator(cairo.OPERATOR_CLEAR)
    cr.arc(-5, -5, 3.5, 0, 2 * math.pi)
    cr.fill()


def _shape_film(cr):
    # A strip of film: its outline, a row of sprocket holes along each edge, and a play mark in its frame.
    cr.set_line_width(6)
    cr.rectangle(-66, -42, 132, 84)
    cr.stroke()
    for k in range(6):
        for y in (-32, 25):
            cr.rectangle(-54 + k * 21, y, 7, 7)
    cr.fill()
    cr.move_to(-12, -17)
    cr.line_to(18, 0)
    cr.line_to(-12, 17)
    cr.close_path()
    cr.fill()


def _shape_branch(cr):
    # A git branch: two commits on the main line, and a branch that curves away to a third.
    cr.set_line_width(8)
    cr.move_to(-26, -34)
    cr.line_to(-26, 34)
    cr.move_to(-26, 22)
    cr.curve_to(-26, -6, 30, 0, 30, -26)
    cr.stroke()
    for x, y in ((-26, -46), (-26, 46), (30, -38)):
        cr.arc(x, y, 15, 0, 2 * math.pi)
        cr.fill()
    cr.set_operator(cairo.OPERATOR_CLEAR)
    for x, y in ((-26, -46), (-26, 46), (30, -38)):
        cr.arc(x, y, 7, 0, 2 * math.pi)
        cr.fill()


def _shape_tiles(cr):
    # Tiled windows: one tall window on the left and two stacked on the right, each with a title bar.
    for x, y, w, h in ((-64, -48, 66, 96), (10, -48, 54, 44), (10, 4, 54, 44)):
        _rounded_rect(cr, x, y, w, h, 6)
        cr.fill()
    cr.set_operator(cairo.OPERATOR_CLEAR)
    for x, y, w, h in ((-58, -34, 54, 76), (16, -34, 42, 24), (16, 18, 42, 24)):
        cr.rectangle(x, y, w, h)
    cr.fill()


def _shape_power(cr):
    # The power symbol: a ring open at the top, and a bar down through the gap.
    cr.set_line_width(13)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.arc(0, 6, 44, math.radians(-55), math.radians(235))
    cr.stroke()
    cr.move_to(0, -54)
    cr.line_to(0, -6)
    cr.stroke()


def _shape_hourglass(cr):
    # The glass of the hourglass: its caps and two bulbs. The sand is grains of its own, see _form_points.
    for y in (-58, 50):
        _rounded_rect(cr, -46, y, 92, 8, 4)
        cr.fill()
    cr.set_line_width(5)
    cr.move_to(-36, -50)
    cr.curve_to(-36, -18, -6, -10, -6, 0)
    cr.curve_to(-6, 10, -36, 18, -36, 50)
    cr.move_to(36, -50)
    cr.curve_to(36, -18, 6, -10, 6, 0)
    cr.curve_to(6, 10, 36, 18, 36, 50)
    cr.stroke()


# The figure, exclaim, chest, sword, and pickaxe are World of Warcraft shapes, used only by WoW mode's tools.
SHAPES = {"figure": _shape_figure, "exclaim": _shape_exclaim, "chest": _shape_chest, "sword": _shape_sword,
          "pickaxe": _shape_pickaxe, "coins": _shape_coins, "question": _shape_question, "magnifier": _shape_magnifier, "page": _shape_page,
          "scan": _shape_page,  # Read's flat page, for a variant without the Devs forms; Devs draws its own scan.
          # The WoW tools' flat shapes, for a variant without the Devs forms; Devs draws its own (icons_wow2.py).
          "figure2_a": _shape_figure, "exclaim2_a": _shape_exclaim, "chest2_a": _shape_chest,
          "sword2_a": _shape_sword, "sword3_a": _shape_sword,
          # The system tools' flat shapes, for a variant without the Devs forms (icons_system2.py, icons_system3.py).
          "prompt3_b": _shape_prompt, "prompt2_c": _shape_prompt, "book2_a": _shape_book,
          "message2_c": _shape_message, "message3_a": _shape_message,
          "overlook3_b": _shape_overlook, "overlook3_d": _shape_overlook, "cog2_a": _shape_cog,
          "eye2_c": _shape_eye, "branch3_a": _shape_branch, "film2_b": _shape_film, "film3_c": _shape_film,
          "tiles2_a": _shape_tiles, "tiles2_c": _shape_tiles, "power2_a": _shape_power,
          "pickaxe3_e": _shape_pickaxe, "coins2_a": _shape_coins, "coins2_c": _shape_coins,
          "pickaxe2_a": _shape_pickaxe,
          "quill": _shape_quill, "writing2_a": _shape_quill, "writing2_b": _shape_quill, "prompt": _shape_prompt, "cog": _shape_cog, "book": _shape_book,
          "message": _shape_message, "overlook": _shape_overlook, "eye": _shape_eye,
          "film": _shape_film, "branch": _shape_branch, "tiles": _shape_tiles, "power": _shape_power,
          "hourglass": _shape_hourglass}
# Every formed shape rests, alive only through its grains' own drift. These two have grains that flow along a path, as
# the resting loop's do, because the flow is what they mean; see Scene._shape_motion.
SHAPE_MOTION = {"hourglass", "spinner"}
# One size system for the thinking forms: each form's scale, then its shift in x and y, so tall forms stand about
# 110 to 116 px high, round ones about 100 px across, wide ones at most 128 px wide, and every form's foot sits 40 px
# above the label line, as the hourglass's does. The hourglass is the standard and keeps its own size.
FORM_FIT = {"coins": (1.3, 0, 9.7), "eye": (1.05, 0, 19.7), "prompt": (1.22, 0, 13.0), "chest": (1.2, 0, 5.9),
            "globe": (1.16, 0, 8.0), "spinner": (1.15, 0, 8.2),
            "message": (1.12, 0, 9.2), "film": (1.0, 0, 12.7), "magnifier": (1.1, 0, 8.9), "lattice": (1.08, 0, 7.2),
            "tiles": (1.0, 0, 9.8), "book": (1.0, 0, 9.2), "figure": (1.0, 0, 1.5),
            "pickaxe": (1.0, -11, 6.8), "overlook": (1.0, 0, 4.6), "cog": (0.94, 0, 5.3), "page": (1.0, 0, 1.8),
            "exclaim": (1.0, 0, 3.8), "power": (1.0, 0, 2.2), "quill": (1.0, 7, -5.0), "branch": (1.0, 0, -1.8),
            "sword": (0.9, 0, 1.1), "rook": (0.86, 0, 0.0)}
# The overlook's thread rows as (y, length).
OVERLOOK_ROWS = ((18, 74), (34, 56), (50, 66))


def _by_angle(points):
    return sorted(points, key=lambda p: math.atan2(p[1], p[0]))


# The filled shapes put this share of their grains on their edges, not the usual 0.55, so they read as objects drawn
# in outline, as the outline shapes do, and not as boxes of noise. Their cut-out lines are edges too. The chest, the
# coins and the page cut their straight lines with DEST_OUT: cairo 1.18 paints a straight stroke on whole pixels under
# CLEAR instead of clearing it, so those lines never showed.
EDGE_SHARE = {"coins": 0.85, "chest": 0.85, "coins2_a": 0.85, "coins2_c": 0.85, "chest2_a": 0.85, "page": 0.85, "scan": 0.85, "book": 0.85, "book2_a": 0.85, "tiles": 0.85, "tiles2_a": 0.85, "tiles2_c": 0.85}


def _mask_points(name, rng, count=GRAINS):
    """Sample grain positions from a filled shape, weighted toward its outline so the silhouette reads."""
    surface = cairo.ImageSurface(cairo.FORMAT_A8, ORB, ORB)
    cr = cairo.Context(surface)
    cr.translate(ORB / 2, ORB / 2)
    SHAPES[name](cr)
    surface.flush()
    data, stride = surface.get_data(), surface.get_stride()
    edge, inner = [], []
    for y in range(1, ORB - 1):
        row = y * stride
        for x in range(1, ORB - 1):
            if data[row + x] > 127:
                solid = (data[row + x - 1] > 127 and data[row + x + 1] > 127
                         and data[row - stride + x] > 127 and data[row + stride + x] > 127)
                (inner if solid else edge).append((x, y))
    points = []
    for _ in range(count):
        x, y = rng.choice(edge if rng.random() < EDGE_SHARE.get(name, 0.55) or not inner else inner)
        points.append((x + rng.random() - ORB / 2, y + rng.random() - ORB / 2, 0.0))
    return points


def _form_points(name):
    """Each form's grain positions, sorted by angle so grains keep their side of the swarm when forms change."""
    if name in _DATA_FORMS:
        return _DATA_FORMS[name]
    rng = random.Random(sum(map(ord, name)))
    if PARTICLE_VARIANT == "C" and name in devs_pack.BUILDERS:
        return devs_pack.BUILDERS[name](GRAINS, rng)
    if name in devs_pack.SEND_FORMS:
        return devs_pack.BUILDERS[name](GRAINS, rng)
    if name == "hourglass" and PARTICLE_VARIANT == "C":
        # Variant C: lathed 3D hourglass with circular caps, curved glass ribs, waist ring, 3D sand cones, and trickle.
        sin, cos, tau = math.sin, math.cos, 2 * math.pi
        pts = []

        def h_rad(y):
            p = min(1.0, abs(y) / 44.0)
            return 4.5 + 28.5 * p * p * (3.0 - 2.0 * p)

        def h_ring(r, y, count):
            for k in range(count):
                a = tau * (k + 0.5 + rng.uniform(-0.22, 0.22)) / count
                pts.append((r * cos(a), y + rng.gauss(0, 0.35), r * sin(a), None, 0.0))

        # Top and bottom circular end caps (double-rimmed silhouette).
        for sy in (-1.0, 1.0):
            h_ring(35.0, sy * 50.0, 48)
            h_ring(28.0, sy * 50.0, 22)
            h_ring(33.0, sy * 46.0, 30)
        # Mid-bulb latitude rings and pinched waist neck ring.
        h_ring(h_rad(24.0), -24.0, 34)
        h_ring(h_rad(24.0), 24.0, 34)
        h_ring(5.2, 0.0, 26)
        # Eight curved 3D glass meridian ribs from top cap through waist to bottom cap.
        for m in range(8):
            a = tau * m / 8.0
            for k in range(22):
                y = -46.0 + 92.0 * (k + 0.5) / 22.0
                r = h_rad(y)
                pts.append((r * cos(a), y, r * sin(a), None, 0.0))
        # 3D conical sand heaps inside the top and bottom bulbs (edge-weighted on cone surfaces).
        for _ in range(56):
            u = rng.random() ** 0.65
            y = -6.0 - 22.0 * u
            rmax = max(2.0, h_rad(y) - 2.5)
            r = rmax * (0.75 + 0.25 * rng.random() if rng.random() < 0.7 else rng.random() ** 0.5)
            a = rng.uniform(0, tau)
            pts.append((r * cos(a), y, r * sin(a), None, 0.0))
        for _ in range(74):
            u = rng.random() ** 0.6
            y = 26.0 + 20.0 * u
            rmax = min(h_rad(y) - 2.5, 4.0 + 25.0 * u)
            r = rmax * (0.72 + 0.28 * rng.random() if rng.random() < 0.7 else rng.random() ** 0.5)
            a = rng.uniform(0, tau)
            pts.append((r * cos(a), y, r * sin(a), None, 0.0))
        # Live 3D falling sand trickle down the central neck.
        trickle_n = max(32, GRAINS - len(pts))
        for k in range(trickle_n):
            pts.append((0.0, 12.0, 0.0, (k + rng.random()) / trickle_n, rng.gauss(0, 1.0)))
        return _by_angle(pts[:GRAINS])
    if name == "hourglass":
        # The glass, a heap of sand left in the top bulb, a heap below, and a thin trickle between them.
        def inside(x, y):
            p = min(1.0, abs(y) / 36)
            return abs(x) < 3 + 28 * p * p * (3 - 2 * p)

        points = [(x, y, None) for x, y, _ in _mask_points(name, rng, GRAINS - SAND - TRICKLE)]
        heaps = []
        while len(heaps) < SAND:
            x, y = rng.uniform(-32, 32), rng.uniform(-34, 47)
            if inside(x, y) and (-30 < y < -6 if y < 0 else y > 47 - 19 * max(0.0, 1 - abs(x) / 30)):
                heaps.append((x, y, None))
        points += heaps
        points += [(0.0, 12.0, (k + rng.random()) / TRICKLE, rng.gauss(0, 1)) for k in range(TRICKLE)]
        return _by_angle(points)
    if name == "spinner":
        # A comet of dust on a ring: dense and bright at its head, thinning along a tail of five sixths of the ring.
        points = []
        for k in range(GRAINS):
            s = ((k + rng.random()) / GRAINS) ** 1.5
            a = -s * 5 / 3 * math.pi
            points.append((42 * math.cos(a), 42 * math.sin(a), s, rng.gauss(0, 1)))
        return _by_angle(points)
    if name in SHAPES:
        return _by_angle(_mask_points(name, rng))
    if name == "lattice":
        # A cube: 60% of the grains trace its 12 outer edges and 5% gather at its 8 corners, so it reads as a solid
        # cube, drawn in outline as the flat shapes are; the rest fill the inner lattice, at the nodes and along the bars.
        nodes = [(-33 + 22 * i, -33 + 22 * j, -33 + 22 * k) for i in range(4) for j in range(4) for k in range(4)]
        points = []
        for n in range(GRAINS):
            part = n % 20
            if part < 12:
                axis, signs = rng.randrange(3), (rng.choice((-33, 33)), rng.choice((-33, 33)))
                edge = [signs[0], signs[1]]
                edge.insert(axis, rng.uniform(-33, 33))
                points.append(tuple(v + rng.gauss(0, 0.8) for v in edge))
                continue
            if part == 12:
                points.append(tuple(rng.choice((-33, 33)) + rng.gauss(0, 1.2) for _ in range(3)))
                continue
            a = rng.choice(nodes)
            if part < 16:
                points.append(tuple(v + rng.gauss(0, 1.0) for v in a))
            else:
                axis = rng.randrange(3)
                b = list(a)
                b[axis] = a[axis] + 22 if a[axis] < 33 else a[axis] - 22
                f = rng.random()
                points.append(tuple(p + (q - p) * f for p, q in zip(a, b)))
        return _by_angle(points)
    if name == "sphere":
        golden = math.pi * (3 - math.sqrt(5))
        points = []
        for n in range(GRAINS):
            y = 1 - 2 * (n + 0.5) / GRAINS
            r = math.sqrt(1 - y * y)
            points.append((46 * r * math.cos(golden * n), 46 * y, 46 * r * math.sin(golden * n)))
        return _by_angle(points)
    if name == "globe":
        curves = [("meridian", k * math.pi / 5) for k in range(5)] + [("parallel", lat) for lat in (-0.75, 0, 0.75)]
        points = []
        for n in range(GRAINS):
            kind, at = curves[n % len(curves)]
            a = rng.uniform(0, 2 * math.pi)
            if kind == "meridian":
                points.append((44 * math.cos(a) * math.cos(at), 44 * math.sin(a), 44 * math.cos(a) * math.sin(at)))
            else:
                points.append((44 * math.cos(at) * math.cos(a), 44 * math.sin(at), 44 * math.cos(at) * math.sin(a)))
        return _by_angle(points)
    if name == "rook":
        # A chess rook turned on its vertical axis (y points down): a stepped base, a tapering waist, a collar, a
        # flared head, and a crown of five merlons with gaps between them. Rings and meridians trace the profile.
        sin, cos, tau = math.sin, math.cos, 2 * math.pi
        points = []

        def ring(r, y, n, a0=0.0, a1=tau):
            for k in range(n):
                a = a0 + (a1 - a0) * (k + 0.5 + rng.uniform(-0.2, 0.2)) / n
                points.append((r * cos(a), y + rng.gauss(0, 0.4), r * sin(a)))

        for r, y, n in ROOK_RINGS:
            ring(r, y, n)
        # Meridians follow the profile from the base's top up to the crown, evenly by length.
        # On Variant C use 16 grains per meridian (144) so all 5 merlons get 48 grains each (240) with zero truncation.
        mer_n = 16 if PARTICLE_VARIANT == "C" else ROOK_MERIDIAN_GRAINS
        length = [math.dist(a, b) for a, b in zip(ROOK_PROFILE, ROOK_PROFILE[1:])]
        for m in range(ROOK_MERIDIANS):
            a = tau * (m + 0.5) / ROOK_MERIDIANS
            for k in range(mer_n):
                d = sum(length) * (k + rng.random()) / mer_n
                for (y0, r0), (y1, r1), step in zip(ROOK_PROFILE, ROOK_PROFILE[1:], length):
                    if d <= step:
                        f = d / step
                        r, y = r0 + (r1 - r0) * f, y0 + (y1 - y0) * f
                        points.append((r * cos(a), y, r * sin(a)))
                        break
                    d -= step
        # The crown: each merlon is a block between radii 21 and 31, from the crown floor up to its top.
        span = tau / ROOK_MERLONS
        for m in range(ROOK_MERLONS):
            a0, a1 = span * m, span * m + span * ROOK_MERLON_SHARE
            if PARTICLE_VARIANT == "C":
                # 48 grains/merlon * 5 = 240 (+ 256 rings + 144 meridians = 640 exact, zero truncation).
                for k in range(14):
                    a = a0 + (a1 - a0) * (k + 0.5) / 14.0
                    points.append((31 * cos(a), ROOK_CROWN_TOP + rng.gauss(0, 0.15), 31 * sin(a)))
                for k in range(8):
                    a = a0 + (a1 - a0) * (k + 0.5) / 8.0
                    points.append((21 * cos(a), ROOK_CROWN_TOP + rng.gauss(0, 0.15), 21 * sin(a)))
                for a in (a0, a1):
                    for k in range(9):
                        y = ROOK_CROWN_FLOOR + (ROOK_CROWN_TOP - ROOK_CROWN_FLOOR) * (k + 0.5) / 9.0
                        points.append((31 * cos(a), y, 31 * sin(a)))
                    for k in range(4):
                        r = 21 + 10 * (k + 0.5) / 4.0
                        points.append((r * cos(a), ROOK_CROWN_TOP, r * sin(a)))
            else:
                ring(31, ROOK_CROWN_TOP, 12, a0, a1)
                ring(21, ROOK_CROWN_TOP, 7, a0, a1)
                for a in (a0, a1):
                    for k in range(8):
                        y = ROOK_CROWN_FLOOR + (ROOK_CROWN_TOP - ROOK_CROWN_FLOOR) * (k + 0.5) / 8
                        points.append((31 * cos(a), y, 31 * sin(a)))
                    for k in range(3):
                        r = 21 + 10 * (k + 0.5) / 3
                        points.append((r * cos(a), ROOK_CROWN_TOP, r * sin(a)))
        # Any grains left over dust the waist's surface.
        while len(points) < GRAINS:
            y = rng.uniform(-16, 34)
            r = 19 + (25 - 19) * (y + 16) / 50
            a = rng.uniform(0, tau)
            points.append((r * cos(a), y, r * sin(a)))
        return _by_angle(points[:GRAINS])
    if name == "cloud":
        points = []
        for _ in range(GRAINS):
            r = min(62.0, abs(rng.gauss(0, 24)))
            a = rng.uniform(0, 2 * math.pi)
            points.append((r * math.cos(a), r * math.sin(a) * 0.85, rng.uniform(0.15, 0.4), rng.uniform(0, 6.3)))
        return _by_angle(points)
    if name == "sink":
        points = []
        for _ in range(GRAINS):
            x = rng.gauss(0, 26)
            points.append((x, 62 - 16 * math.exp(-x * x / 1100) * rng.random() - rng.random() * 2, 0.0))
        return _by_angle(points)
    if name == "rows":
        points = []
        for row, y in enumerate((-27, -9, 9, 27)):
            x = -62 + rng.uniform(0, 6)
            while x < 56:
                length = min(rng.uniform(8, 28), 62 - x)
                for _ in range(int(length * 2.2)):
                    px = x + rng.random() * length
                    # Each grain lands when the pen passes it: rows fill in turn, left to right, over 0.75 s each.
                    points.append((px, y + rng.uniform(-1.6, 1.6), row * 0.75 + (px + 62) / 124 * 0.75, row))
                x += length + rng.uniform(5, 9)
        rng.shuffle(points)
        return _by_angle((points * (GRAINS // len(points) + 1))[:GRAINS])
    if name == "frame":
        # Most grains trace a frame just outside the card, a third of them bunched at its corners.
        # Every fourth grain belongs to the orb: a small turning sphere of dust 40 px across.
        golden = math.pi * (3 - math.sqrt(5))
        orb_count = len(range(0, GRAINS, ORB_EVERY))
        points = []
        for n in range(GRAINS):
            if n % ORB_EVERY == 0:
                k = n // ORB_EVERY
                y = 1 - 2 * (k + 0.5) / orb_count
                r = math.sqrt(1 - y * y)
                points.append((None, 20 * r * math.cos(golden * k), 20 * y, 20 * r * math.sin(golden * k)))
            else:
                points.append(((n + 0.5) / GRAINS, rng.random() < 0.33, rng.uniform(-9, 9), rng.uniform(-1.8, 1.8)))
        return points
    if name == "loop":
        # A figure-eight on its side. Each grain's place on the loop matches its side of the swarm,
        # so grains do not cross the middle when they gather into it (exact pre-engine form).
        points = []
        for n in range(GRAINS):
            angle = -math.pi + 2 * math.pi * (n + 0.5) / GRAINS
            along = math.pi / 2 - angle if abs(angle) <= math.pi / 2 else math.pi / 2 + angle
            points.append((along, rng.uniform(-1.6, 1.6)))
        return points
    if name == "ear":
        # The listening orb: a sphere drawn as stacked rings of dust, so sound can ripple across it.
        points = []
        for n in range(GRAINS):
            lat = -1.2 + (n % 11) * 0.24
            a = rng.uniform(0, 2 * math.pi)
            points.append((44 * math.cos(lat) * math.cos(a), 44 * math.sin(lat), 44 * math.cos(lat) * math.sin(a)))
        return _by_angle(points)
    # The waveform listening forms. Each entry starts with the grain's silent x and y, for _by_angle.
    if name == "halo":
        # A slim ring of dust. Every fourth grain belongs to a fainter echo ring just inside it (exact pre-engine form).
        points = []
        for n in range(GRAINS):
            a = 2 * math.pi * (n + rng.random()) / GRAINS
            echo = n % 4 == 0
            off = -7 + rng.gauss(0, 0.9) if echo else max(-3.0, min(3.0, rng.gauss(0, 1.1)))
            points.append((40 * math.cos(a), 40 * math.sin(a), a, echo, off))
        return _by_angle(points)
    if name == "helix":
        # Two strands twisted around a horizontal axis, and rungs between them.
        # In Variant C, strands have 3D braided tube cross-sections and 18 crisp 3D base-pair rungs.
        points = []
        strand_n = 460 if PARTICLE_VARIANT == "C" else 448
        rung_count, rung_per = (18, 10) if PARTICLE_VARIANT == "C" else (24, 8)
        for n in range(GRAINS):
            if n < strand_n:
                u = -1 + 2 * (n // 2 + rng.random()) / (strand_n // 2)
                turn, v = (n % 2) * math.pi, None
                if PARTICLE_VARIANT == "C":
                    # Edge-weighted 3D strand tube offset (phi around strand cross-section).
                    phi = (0.0 if rng.random() < 0.5 else math.pi) + rng.gauss(0, 0.5) if rng.random() < 0.7 else rng.uniform(0, 2 * math.pi)
                    off = (2.4 * math.cos(phi), 2.4 * math.sin(phi))
                else:
                    off = rng.gauss(0, 0.45)
            else:
                rung, k = divmod(n - strand_n, rung_per)
                u = 0.88 * (-1 + 2 * (rung + 0.5) / rung_count)
                turn = 0.0
                # Slight edge weight toward the two backbone junctions in Variant C.
                v_lin = -1 + 2 * (k + 0.5) / rung_per
                v = math.copysign(abs(v_lin) ** 0.85, v_lin) if PARTICLE_VARIANT == "C" else v_lin
                off = (0.0, 0.0) if PARTICLE_VARIANT == "C" else 0.0
            taper = 1 - u * u
            # Silent radius, how far the voice swells it (most in the middle), and how late the grain hears it.
            radius, swell, lag = 1.5 + 11 * taper, 3.0 * math.exp(-4.5 * u * u) * taper, int(abs(u) * 9)
            y = (v if v is not None else 1) * radius * math.sin(7.8 * u + turn)
            points.append((74 * u, y, u, turn, v, off, radius, swell, lag))
        return _by_angle(points)
    if name == "ridges":
        # Seven ridgelines, front (j = 0, lowest) to back. Lines further back are shorter and hold fewer grains.
        persp = [1 - 0.075 * j for j in range(7)]
        counts = [round(GRAINS * p / sum(persp)) for p in persp]
        counts[0] += GRAINS - sum(counts)
        points = []
        for j, (p, count) in enumerate(zip(persp, counts)):
            for k in range(count):
                xn = -1 + 2 * (k + rng.random()) / count
                ends = 1 - xn * xn
                # A soft hump for any sound, and a sharper peak with shoulders that only loud sound raises.
                hump = math.exp(-(xn / 0.42) ** 2) * ends
                peak = (math.exp(-(xn / 0.15) ** 2) + 0.45 * math.exp(-((abs(xn) - 0.42) / 0.12) ** 2)) * ends
                ripples = (math.sin(7.5 * xn + 1.9 * j) * ends, math.sin(13 * xn - 0.7 * j) * ends)
                points.append((72 * p * xn, 30 - 11 * j, j, hump, peak, *ripples, rng.gauss(0, 0.35)))
        return _by_angle(points)
    if name == "burst":
        # A seed head: a dense core, and 28 fine spokes of 17 grains, each ending in a small tuft.
        spokes, per = 28, 17
        core = GRAINS - spokes * per
        points = []
        for n in range(GRAINS):
            if n < core:
                r, a = abs(rng.gauss(0, 4.5)), rng.uniform(0, 2 * math.pi)
                points.append((r * math.cos(a), r * math.sin(a), None, a, r, 0.0, 0.0, 0, 0.0, 0.0))
                continue
            s, k = divmod(n - core, per)
            a = -math.pi / 2 + 2 * math.pi * s / spokes + rng.uniform(-0.03, 0.03)
            # Partner spokes, mirrored about the vertical, hear the same band of the spectrum.
            band = min(s, spokes - s)
            weight = 0.55 + 0.45 * abs(math.sin(band * 12.9898 + 4.1))
            u, side = (0.28 + 0.72 * (k + 0.5) / 14, 0.0) if k < 14 else (1 + rng.uniform(0, 0.08),
                                                                          rng.uniform(-1.8, 1.8))
            # The whole spoke stretches as one, so its grains stay evenly spaced along it.
            points.append((20 * u * math.cos(a), 20 * u * math.sin(a), s, a, u, side, weight,
                           int(band / (spokes / 2) * 7), 5 + 4 * (s * 0.618 % 1), s * 2.4))
        return _by_angle(points)
    raise KeyError(name)


_FORMS = {}
_DATA_FORMS = {}  # A user dust pack's own forms, "pack:<pack>/<icon>": [(x, y, z), ...] (see Scene.use_pack_forms).
DATA_SWAY = 0.3  # The most a pack's own form turns either way, in radians.


_FORMS_3D_C = frozenset(devs_pack.BUILDERS.keys())


def _form(name):
    key = (PARTICLE_VARIANT, name)
    if key not in _FORMS:
        _FORMS[key] = _form_points(name)
    return _FORMS[key]


def _word_weight(word):
    pause = 8 if word[-1] in ".!?" else 4 if word[-1] in ",;:" else 0
    return len(word) + 1 + pause


def _safe_utf8(text) -> str:
    """Replace any lone UTF-16 surrogates so Pango/GTK set_text/set_markup can never raise UnicodeEncodeError."""
    if not isinstance(text, str):
        return ""
    return text.encode("utf-8", "replace").decode("utf-8")


class Sentence:
    def __init__(self, text, words):
        self.text = text
        self.words = words  # (char start, char end, reveal time)
        self.first = words[0][2]
        self.fade_at, self.fade_for = math.inf, SENTENCE_OUT
        self.sprites = None
        self.scale = None
        self.lines = None  # (first reveal time, top, bottom) per line

    def build(self, cr, scale):
        """Lay out the sentence once, then cache one pre-shadowed sprite per word."""
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(CAPTION_FONT)
        layout.set_width(CAPTION_W * Pango.SCALE)
        layout.set_wrap(Pango.WrapMode.WORD)
        layout.set_alignment(Pango.Alignment.CENTER)
        layout.set_line_spacing(CAPTION_LINE_SPACING)
        if CAPTION_SPACING:
            attrs = Pango.AttrList()
            attrs.insert(Pango.attr_letter_spacing_new(int(CAPTION_SPACING * Pango.SCALE)))
            layout.set_attributes(attrs)
        self.text = _safe_utf8(self.text)
        layout.set_text(self.text, -1)
        if layout.get_line_count() == 2:
            # The narrowest width that still keeps two lines evens them out, so no word sits alone on the second.
            lo, hi = CAPTION_W // 2, CAPTION_W
            while lo < hi:
                layout.set_width((lo + hi) // 2 * Pango.SCALE)
                lo, hi = (lo, (lo + hi) // 2) if layout.get_line_count() == 2 else ((lo + hi) // 2 + 1, hi)
            layout.set_width(hi * Pango.SCALE)
        shift = (CAPTION_W - layout.get_width() / Pango.SCALE) / 2  # Keeps the narrowed lines centred.
        ink, _ = layout.get_pixel_extents()
        self.center, self.width = shift + ink.x + ink.width / 2, ink.width
        lines = []
        it = layout.get_iter()
        while True:
            line_ink, _ = it.get_line_extents()
            lines.append((it.get_line_readonly().start_index, it.get_baseline() / Pango.SCALE,
                          line_ink.y / Pango.SCALE, (line_ink.y + line_ink.height) / Pango.SCALE))
            if not it.next_line():
                break
        self.sprites, firsts = [], {}
        for start, end, at in self.words:
            index = len(self.text[:start].encode())
            pos = layout.index_to_pos(index)
            k = max(n for n, line in enumerate(lines) if line[0] <= index)
            firsts.setdefault(k, at)
            if LETTERING:  # A pack's lettering: crisp letters in a thin outline, no halo.
                kind, outline = LETTERING["caption"], LETTERING["outline"]
                sprite, sprite_baseline, pad = _word_sprite(
                    cr, self.text[start:end], scale, CAPTION_FONT, kind["color"], CAPTION_SPACING, (), outline[2],
                    outline[:2], rim=LETTERING["rim"] if kind["rim"] else None)
            else:
                sprite, sprite_baseline, pad = _word_sprite(cr, self.text[start:end], scale, CAPTION_FONT,
                                                            PALETTE["text"], halos=PALETTE["text_halos"],
                                                            halo_color=PALETTE["text_halo"])
            self.sprites.append((sprite, shift + pos.x / Pango.SCALE - pad, lines[k][1] - sprite_baseline, at))
        self.lines = [(firsts.get(k, math.inf), top, bottom) for k, (_, _, top, bottom) in enumerate(lines)]
        self.scale = scale

    def box(self, clock):
        """The text block so far: full width, growing down smoothly as each new line begins."""
        top, bottom = self.lines[0][1], self.lines[0][2]
        for (_, _, prev), (at, _, below) in zip(self.lines, self.lines[1:]):
            bottom += (below - prev) * _ease_out((clock - at) / 0.4)
        return self.center, (top + bottom) / 2, self.width, bottom - top


def _word_sprite(cr, word, scale, font=CAPTION_FONT, color=IVORY, spacing=0.0,
                 halos=((10, (0.9, 0.9)), (4, (0.95, 0.8))), halo_color=INK, outline=None, wrap=None, rim=None):
    pad = 14
    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(font)
    if wrap:  # Centred lines no wider than wrap.
        layout.set_width(int(wrap * Pango.SCALE))
        layout.set_wrap(Pango.WrapMode.WORD)
        layout.set_alignment(Pango.Alignment.CENTER)
    if spacing:
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_letter_spacing_new(int(spacing * Pango.SCALE)))
        layout.set_attributes(attrs)
    layout.set_text(_safe_utf8(word), -1)
    _, logical = layout.get_pixel_extents()
    w, h = logical.width + 2 * pad, logical.height + 2 * pad
    sprite = cairo.ImageSurface(cairo.FORMAT_ARGB32, math.ceil(w * scale), math.ceil(h * scale))
    sprite.set_device_scale(scale, scale)
    c = cairo.Context(sprite)
    # The ink halo is the text drawn at low resolution and scaled up, which blurs it softly. A wide
    # faint pass and a tight dense pass keep ivory legible over bright scenes without a panel.
    for shrink, passes in halos:
        halo = cairo.ImageSurface(cairo.FORMAT_ARGB32, max(1, math.ceil(w * scale / shrink)),
                                  max(1, math.ceil(h * scale / shrink)))
        halo.set_device_scale(scale / shrink, scale / shrink)
        hc = cairo.Context(halo)
        hc.move_to(pad - logical.x, pad - logical.y + 1)
        hc.set_source_rgba(*halo_color, 1.0)
        PangoCairo.show_layout(hc, layout)
        for alpha in passes:
            c.set_source_surface(halo, 0, 0)
            c.paint_with_alpha(alpha)
    if outline:
        # A stroke along each letter's edge, half of it outside the letter. The fill below covers the inner half.
        c.move_to(pad - logical.x, pad - logical.y)
        PangoCairo.layout_path(c, layout)
        c.set_line_width(2 * outline[0])
        c.set_line_join(cairo.LINE_JOIN_ROUND)
        c.set_source_rgba(*halo_color, outline[1])
        c.stroke()
    if rim:
        # A pack's lettering: a thin coloured line (width, alpha, colour) along the letter's edge, inside the outline.
        c.move_to(pad - logical.x, pad - logical.y)
        PangoCairo.layout_path(c, layout)
        c.set_line_width(2 * rim[0])
        c.set_line_join(cairo.LINE_JOIN_ROUND)
        c.set_source_rgba(*rim[2], rim[1])
        c.stroke()
    c.move_to(pad - logical.x, pad - logical.y)
    c.set_source_rgba(*color, 1.0)
    PangoCairo.show_layout(c, layout)
    return sprite, pad - logical.y + layout.get_baseline() / Pango.SCALE, pad - logical.x


def _grown(font, grow):
    """font at grow times its size: the same font when grow is 1."""
    if grow == 1.0:
        return font
    font, size = font.copy(), round(font.get_size() * grow)
    font.set_absolute_size(size) if font.get_size_is_absolute() else font.set_size(size)  # _font's sizes are in px.
    return font


def _lettering_sprite(cr, text, scale, kind, color=None, grow=1.0):
    """text in the pack's lettering for kind ("label" or "name"), as _word_sprite makes it: crisp letters in a thin
    outline and, where the kind has one, a rim. No halo, plate or blur. color replaces the kind's own colour, and grow
    scales its size."""
    k = LETTERING[kind]
    outline, rim = LETTERING["outline"], (LETTERING["rim"] if k["rim"] and color is None else None)
    # The rim covers the inner part of the outline, so the outline grows by the rim's width and is near opaque: the
    # ink edge then still shows outside the gold, which keeps the letters legible over bright games.
    edge = (outline[0] + rim[0], max(outline[1], 0.95)) if rim else outline[:2]
    return _word_sprite(cr, text, scale, _grown(k["font"], grow), color or k["color"], k["spacing"] * grow, (),
                        outline[2], edge, rim=rim)


# The pack's reveal ("spread"): grains spread sideways along a word from its start or its centre and settle into the
# letters, the crisp letters fade in under them as they pass, and the grains then dissolve. A point at order o (0 at
# the start, 1 at the far end) is reached at REVEAL_REACH[0] + REVEAL_REACH[1] * o seconds; all is clean type by
# REVEAL_SECONDS. Thin strokes get no grains, so the crisp letters alone carry them.
REVEAL_SECONDS, REVEAL_REACH = 0.62, (0.10, 0.26)
REVEAL_GRAINS = (6, 90)  # Grains per letter, and at most per word.
_TYPE_GEOMETRY = {}


def _type_geometry(text, font, spacing):
    """Where a _word_sprite's letters sit inside it, in the sprite's logical pixels: their ink box (x, y, w, h) and up
    REVEAL_GRAINS homes, on stroke pixels well inside the letters; then the sprite's own width and height.
    Cached per text and font."""
    key = (text, font.to_string(), spacing)
    if key not in _TYPE_GEOMETRY:
        if len(_TYPE_GEOMETRY) > 64:
            _TYPE_GEOMETRY.clear()
        layout = Pango.Layout.new(PangoCairo.FontMap.get_default().create_context())
        layout.set_font_description(font)
        if spacing:
            attrs = Pango.AttrList()
            attrs.insert(Pango.attr_letter_spacing_new(int(spacing * Pango.SCALE)))
            layout.set_attributes(attrs)
        layout.set_text(_safe_utf8(text), -1)
        ink, logical = layout.get_pixel_extents()
        ox, oy, s = 14 - logical.x, 14 - logical.y, 2  # 14 is _word_sprite's pad; sampled at twice the size.
        x0, y0 = ox + ink.x - 1, oy + ink.y - 1
        w, h = ink.width + 2, ink.height + 2
        image = cairo.ImageSurface(cairo.FORMAT_A8, max(1, w * s), max(1, h * s))
        c = cairo.Context(image)
        c.scale(s, s)
        c.move_to(ox - x0, oy - y0)
        PangoCairo.show_layout(c, layout)
        image.flush()
        data, stride = bytes(image.get_data()), image.get_stride()
        pixels = [(px, py) for py in range(image.get_height()) for px in range(image.get_width())
                  if data[py * stride + px] > 200]
        homes = random.Random(len(text)).sample(
            pixels, min(len(pixels), REVEAL_GRAINS[0] * len(text.strip()), REVEAL_GRAINS[1]))
        _TYPE_GEOMETRY[key] = ((ox + ink.x, oy + ink.y, ink.width, ink.height),
                               [(x0 + (px + 0.5) / s, y0 + (py + 0.5) / s) for px, py in homes],
                               (logical.width + 28, logical.height + 28))
    return _TYPE_GEOMETRY[key]


def _reveal_origin(ink, origin):
    """The x a reveal spreads from ("centre", "left" or "right" of the ink box) and how far it spreads."""
    ix, _, iw, _ = ink
    if origin == "centre":
        return ix + iw / 2, max(1.0, iw / 2)
    return (ix if origin == "left" else ix + iw), max(1.0, iw)


def _reveal_stops(t, origin):
    """The letters' alpha across the ink box at t, left to right: (offset 0..1, alpha) pairs for a linear gradient."""
    stops = []
    for n in range(9):
        p = n / 8
        o = abs(2 * p - 1) if origin == "centre" else p if origin == "left" else 1 - p
        # The grains ease out, so they are most of the way to their homes at about half their reach time.
        stops.append((p, _smooth((t - 0.55 * (REVEAL_REACH[0] + REVEAL_REACH[1] * o)) / 0.14)))
    return stops


def _reveal_mask(ink, t, origin, x, y, alpha):
    """The letters' reveal at t as a Cairo mask, for a sprite drawn with its top left at (x, y)."""
    ix, _, iw, _ = ink
    mask = cairo.LinearGradient(x + ix, 0, x + ix + iw, 0)
    for p, a in _reveal_stops(t, origin):
        mask.add_color_stop_rgba(p, 0, 0, 0, a * alpha)
    return mask


def _reveal_rows(geometry, t, origin, x, y):
    """The reveal's grains at t, for a sprite drawn with its top left at (x, y), as the dust engine's 11-float rows
    (see DispatchState.eval_gl_rows). Empty before and after the reveal, so a word at rest costs no grains."""
    ink, homes = geometry[:2]
    if not 0.0 <= t < REVEAL_SECONDS:
        return []
    ox, span = _reveal_origin(ink, origin)
    rows = []
    for i, (hx, hy) in enumerate(homes):
        reach = REVEAL_REACH[0] + REVEAL_REACH[1] * min(1.0, abs(hx - ox) / span) + 0.04 * ((i * 0.381966) % 1.0)
        a = 0.6 * min(1.0, t / 0.05) * (1.0 - _smooth((t - reach) / 0.2))
        if a <= 0.01:
            continue
        m = 1.0 - min(1.0, t / reach)
        gx = ox + (hx - ox) * (1.0 - m * m * m)  # Out along the word, easing into its home.
        gy = hy + (((i * 0.618034) % 1.0) - 0.5) * 5.0 * m  # A little loose height that closes as it lands.
        vx = max(-80.0, min(80.0, (hx - ox) * 3.0 * m * m / reach))
        rows.extend((x + gx, y + gy, a, 0.35, vx, 0.0, 1.0, 0.9, 1.0, float(i % 3), 1.0))
    return rows


def _paint_reveal_rows(cr, rows, cx=0.0, cy=0.0):
    """The Cairo fallback for _reveal_rows: small additive gold grains, as DispatchState.draw_strands_cairo draws."""
    if not rows:
        return
    cr.save()
    cr.set_operator(cairo.OPERATOR_ADD)
    for n in range(0, len(rows), 11):
        x, y, a = rows[n:n + 3]
        cr.set_source_rgba(*_REVEAL_TONES[int(rows[n + 9]) % 3], min(1.0, a))
        cr.arc(cx + x, cy + y, 0.9, 0.0, 2 * math.pi)
        cr.fill()
    cr.restore()


_REVEAL_TONES = ((0.949, 0.698, 0.278), (0.976, 0.812, 0.490), (1.0, 0.922, 0.698))


# The Devs permission card ("dust frame"): a dark plate whose border is Rook's gold dust. On arrival the grains drop
# to the top centre, run along the edge both ways and settle into a thin frame that closes at the bottom; at rest the
# frame breathes faintly. A tag such as CLAUDE · BASH sits in a gap of the top edge. The headline is the tool's own
# summary in the Devs lettering, the request is in quiet mono, and Allow and Decline are live from the start. Only the
# Devs lettering (LETTERING) draws it; Nova and the light theme keep the plain card.
CARD_W, CARD_PAD = 440, 18  # The card's width and inner padding, in logical px.
CARD_FALL = 48  # Clear room above the plate, where the dust falls in, as tall as in the approved clip. No clicks.
CARD_INSET = 2.5  # The dust line's distance inside the plate's edge.
CARD_LINE = 24  # The headline's line height; it has at most two lines.
CARD_ENTRANCE = 1.5  # Seconds until every part has arrived; then the card redraws only to breathe.
CARD_REST_FPS = 6
CARD_TIMES = {"who": 0.38, "summary": 0.50, "req": 0.62, "btn": 0.74}  # When each part starts to arrive.
CARD_PLATE, CARD_CHAMPAGNE, CARD_MUTED = (0.035, 0.038, 0.050), (1.0, 0.910, 0.639), (0.69, 0.67, 0.63)
CARD_HEADLINE_FONT = _font("Noto Serif", 17, Pango.Weight.BOLD)


def _card_words(tool, details):
    """The Devs card's headline and request, from the tool's name and its input (the JSON the card's details carry).
    The headline is the tool's own summary (Bash's description), else a short plain line from the tool and its main
    input. The request is what will run, cleaner than JSON for the common tools; every input key the cleaner form
    does not show is listed under it, so nothing that runs is hidden."""
    tool = tool or ""
    try:
        data = json.loads(details)
    except (TypeError, ValueError):
        data = None
    mcp = tool.startswith("mcp__") and tool.count("__") >= 2
    name = " ".join(tool.split("__", 2)[2].replace("_", " ").split()).capitalize() if mcp else f"Use {tool or 'a tool'}"
    if not isinstance(data, dict):
        return name, details or ""

    def text(key):
        value = data.get(key)
        return value if isinstance(value, str) else ""

    home = os.path.expanduser("~")
    path = text("file_path")
    shown = "~" + path[len(home):] if home != "/" and path.startswith(home + "/") else path
    short = "/".join(path.rstrip("/").split("/")[-2:])
    used, head, body = set(), name, ""
    if tool == "Bash" and text("command"):
        used = {"command", "description"}
        head, body = text("description").strip() or "Run a shell command", text("command")
    elif tool in ("Edit", "Write", "Read") and path:
        used = {"file_path"}
        head, body = f"{tool} {short}", shown
        if tool == "Edit" and "old_string" in data and "new_string" in data:
            used |= {"old_string", "new_string", "replace_all"}
            old, new = text("old_string").split("\n"), text("new_string").split("\n")
            every = ", at every match" if data.get("replace_all") is True else ""
            body += (f"\nReplaces {len(old)} line{'s' * (len(old) != 1)} with {len(new)} line{'s' * (len(new) != 1)}"
                     f"{every}\n\n" + "\n".join([f"- {line}" for line in old] + [f"+ {line}" for line in new]))
        elif tool == "Write" and "content" in data:
            used.add("content")
            lines = text("content").count("\n") + 1
            body += f"\n{lines} line{'s' * (lines != 1)}\n\n{text('content')}"
    elif tool == "WebFetch" and text("url"):
        used = {"url", "prompt"}
        head = f"Fetch {text('url').split('://', 1)[-1].split('/', 1)[0]}"
        body = text("url") + (f"\n\n{text('prompt')}" if text("prompt") else "")
    elif tool == "WebSearch" and text("query"):
        used, head, body = {"query"}, "Search the web", text("query")
    elif tool == "AskUserQuestion":
        return "Answer the question", ""
    rest = [f"{key}: {value if isinstance(value, str) else json.dumps(value)}" for key, value in data.items()
            if key not in used]
    return head, "\n".join(([body, ""] if body and rest else [body] if body else []) + rest) or "(no input)"


def _card_tag(who, tool):
    """The tag in the top edge: who asks, and the tool (an MCP tool by its server)."""
    tool = tool or "tool"
    return f"{who or 'Rook'} · {tool.split('__')[1] if tool.startswith('mcp__') and tool.count('__') >= 2 else tool}"


def _card_crisp_rect(cr, s, x, y, w, h, r):
    """A rect path on whole device pixels, centred on them for a 1 px line, so the edge never blurs."""
    def px(v):
        return (math.floor(v * s) + 0.5) / s
    _rounded_rect(cr, px(x), px(y), px(x + w) - px(x), px(y + h) - px(y), r)


def _card_frame(w, h, inset, gaps):
    """Dust homes along the frame, about 1.7 px apart and a little loose, skipping the gaps on the top edge. Each home
    keeps its arc length from the top centre, signed (right side positive), so the settle can run along the edge, and
    its resting point. Returns the homes and a function from such an arc length to its point on the frame."""
    rng, homes = random.Random(5), []
    x0, y0, x1, y1 = inset, inset, w - inset, h - inset
    edges = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
    perim = 2 * (x1 - x0 + y1 - y0)
    xc = (x0 + x1) / 2

    def point(a):
        """The frame point a px clockwise (a < 0: anticlockwise) from the top centre, and the normal grains scatter
        along."""
        a %= perim
        for (ax, ay), (bx, by) in [((xc, y0), (x1, y0))] + edges[1:] + [((x0, y0), (xc, y0))]:
            n = math.dist((ax, ay), (bx, by))
            if a <= n:
                return ax + (bx - ax) * a / n, ay + (by - ay) * a / n, (0, 1) if ay == by else (1, 0)
            a -= n
        return xc, y0, (0, 1)

    along = 0.0
    for (ax, ay), (bx, by) in edges:
        n = max(1, round(math.dist((ax, ay), (bx, by)) / 1.7))
        for k in range(n):
            f = k / n
            x, y = ax + (bx - ax) * f, ay + (by - ay) * f
            if ay == by == y0 and any(g0 <= x <= g1 for g0, g1 in gaps):
                continue
            arc = (along + math.dist((ax, ay), (x, y)) - (xc - x0)) % perim
            arc = arc if arc <= perim / 2 else arc - perim
            corner = min(math.hypot(x - cx, y - cy) for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)))
            loose = rng.gauss(0, 0.55)  # Off the line, across it, so the edge reads as dust and not a dotted rule.
            spark = rng.random() < 0.10
            rx, ry, normal = point(arc)
            homes.append({"n": loose, "a": arc, "o": abs(arc) / (perim / 2), "r": rng.uniform(0.62, 1.0),
                          "corner": corner < 9.0, "k": rng.randrange(3), "spark": spark,
                          "ph": rng.random() * math.tau, "j": rng.random(),
                          "at": (rx + normal[0] * loose, ry + normal[1] * loose)})
        along += math.dist((ax, ay), (bx, by))
    return homes, point


def _card_dust(cr, homes, point, ox, oy, t, rest):
    """The frame's grains: crisp round dots, additive gold. On arrival (t seconds in; None at rest) they drop from the
    swarm above to the top centre, then run along the edge both ways and settle, so the frame closes at the bottom
    centre last. They fall from oy above the frame, the top of the panel, so the whole fall shows. rest is the
    breathing clock."""
    cr.save()
    cr.set_operator(cairo.OPERATOR_ADD)
    top = point(0.0)
    fall = oy + top[1]
    for g in homes:
        base = 1.0 if g["corner"] else 0.78
        if g["spark"]:
            base *= 1.0 + 0.45 * (0.5 + 0.5 * math.sin(1.7 * rest + g["ph"]))
        base *= 0.88 + 0.12 * math.sin(0.9 * rest + 6 * g["j"])  # Alive at rest: a slow, slight breathing.
        x, y = g["at"]
        if t is not None:
            k = t - 0.10 * g["j"]
            if k <= 0:
                continue
            drop, loose = _smooth(k / 0.16), g["n"]
            if drop < 1.0:  # Falling from the swarm, a loose stream.
                x, y = top[0] + (g["j"] - 0.5) * 44 * (1 - drop) + loose * 4 * (1 - drop), top[1] - fall * (1 - drop)
                base *= 0.3 + 0.7 * drop  # Thin while it falls, so the stream never piles into a white bar.
            else:
                run = 1.0 - (1.0 - min(1.0, (k - 0.16) / (0.12 + 0.62 * g["o"]))) ** 3  # Eases into its home.
                x, y, normal = point(g["a"] * run)
                loose *= 1.0 + 3.0 * (1.0 - run)
                x, y = x + normal[0] * loose, y + normal[1] * loose
                base *= 1.0 + 0.5 * (1.0 - run)  # The running head is a little hotter.
        cr.set_source_rgba(*_REVEAL_TONES[g["k"]], min(1.0, base))
        cr.arc(ox + x, oy + y, 1.15 if g["spark"] else g["r"], 0, math.tau)
        cr.fill()
    cr.restore()


def _card_request_layout(text):
    """The request in quiet mono, wrapped to the card."""
    layout = Pango.Layout.new(PangoCairo.FontMap.get_default().create_context())
    layout.set_font_description(_font(_terminal_family(), 12.5))
    layout.set_width(int((CARD_W - 2 * CARD_PAD) * Pango.SCALE))
    layout.set_wrap(Pango.WrapMode.WORD_CHAR)
    layout.set_spacing(int(2 * Pango.SCALE))
    layout.set_text(_safe_utf8(text), -1)
    return layout


def _card_headline_lines(text):
    """The headline as at most two lines that fit the card; a longer one ends in an ellipsis."""
    layout = Pango.Layout.new(PangoCairo.FontMap.get_default().create_context())
    layout.set_font_description(CARD_HEADLINE_FONT)
    room = (CARD_W - 2 * CARD_PAD) * Pango.SCALE
    layout.set_width(int(room))
    layout.set_wrap(Pango.WrapMode.WORD_CHAR)
    raw = _safe_utf8(" ".join(text.split()) or " ").encode()
    layout.set_text(raw.decode(), -1)
    lines = [raw[ln.start_index:ln.start_index + ln.length].decode().strip() for ln in layout.get_lines_readonly()]
    if len(lines) > 2:
        last = " ".join(lines[1:]).split()
        layout.set_width(-1)
        while last:
            layout.set_text(" ".join(last) + "…", -1)
            if layout.get_size()[0] <= room:
                break
            last.pop()
        lines = [lines[0], " ".join(last) + "…"]
    return lines


class _CardFace:
    """One Devs card's words and dust, laid out once per card. Each draw takes t, the seconds since the card arrived,
    or None once it has; the panel also takes rest, the breathing clock. Sprites are made at the drawing scale."""

    def __init__(self, tool, who, details, count=1):
        self.headline, self.request = _card_words(tool, details)
        self.tag = _cased(_card_tag(who, tool), "label")
        self.lines = _card_headline_lines(self.headline)
        self.req_layout = _card_request_layout(self.request)
        self.req_h = self.req_layout.get_pixel_extents()[1].height if self.request else 0
        # Each request line's top and baseline, found once: a Pango iterator costs a pass over every line.
        self.req_tops, self.req_bases, lines = [], [], self.req_layout.get_iter()
        while True:
            self.req_tops.append(lines.get_line_yrange()[0] / Pango.SCALE)
            self.req_bases.append(lines.get_baseline() / Pango.SCALE)
            if not lines.next_line():
                break
        self.sprites, self.frame, self.allow_text = {}, None, "Allow"
        self.count(count)

    def count(self, count):
        """Set how many cards wait; with more than one the queue mark shows in the top edge."""
        self.queue = _cased(f"Card 1 of {count}", "label") if isinstance(count, int) and count > 1 else None
        self.frame = None

    def word(self, cr, text, kind):
        """text as a sprite in the Devs lettering, at the drawing scale: (sprite, baseline, geometry). kind is tag,
        queue, head, allow or decline."""
        s = cr.get_target().get_device_scale()[0]
        key = (text, kind, s)
        if key not in self.sprites:
            label, gold = LETTERING["label"], LETTERING["rim"]
            font, spacing, color, rim = {
                "tag": (label["font"], label["spacing"], label["color"], gold),
                "queue": (label["font"], label["spacing"], CARD_CHAMPAGNE, None),
                "head": (CARD_HEADLINE_FONT, 0.0, label["color"], None),
                "allow": (label["font"], label["spacing"], label["color"], gold),
                "decline": (label["font"], label["spacing"], CARD_MUTED, None)}[kind]
            out = LETTERING["outline"]
            edge = (out[0] + rim[0], max(out[1], 0.95)) if rim else out[:2]
            sprite, base, _ = _word_sprite(cr, text, s, font, color, spacing, (), out[2], edge, rim=rim)
            self.sprites[key] = (sprite, base, _type_geometry(text, font, spacing))
        return self.sprites[key]

    @staticmethod
    def ink_w(text):
        """The width of a label word's ink, without drawing it."""
        return _type_geometry(text, LETTERING["label"]["font"], LETTERING["label"]["spacing"])[0][2]

    @staticmethod
    def mid(word, cy):
        """The baseline that centres the word's ink on cy."""
        ink, base = word[2][0], word[1]
        return cy + ink[3] / 2 - (ink[1] + ink[3] - base)

    @staticmethod
    def put(cr, word, x, base_y, t=None, origin="left", alpha=1.0):
        """Ink left at x, baseline at base_y, with the Devs reveal while t (seconds into it) is under REVEAL_SECONDS."""
        sprite, base, geometry = word
        ink = geometry[0]
        sx, sy = x - ink[0], base_y - base
        if t is not None and t <= 0:
            return
        cr.set_source_surface(sprite, sx, sy)
        if t is None or t >= REVEAL_SECONDS:
            cr.paint_with_alpha(alpha)
            return
        cr.mask(_reveal_mask(ink, t, origin, sx, sy, alpha))
        _paint_reveal_rows(cr, _reveal_rows(geometry, t, origin, sx, sy))

    def draw_panel(self, cr, w, h, t, rest):
        """The plate, the dust frame, the tag and the queue mark, in a panel w by h. The plate starts CARD_FALL down."""
        s = cr.get_target().get_device_scale()[0]
        oy, ph = CARD_FALL, h - CARD_FALL
        _card_crisp_rect(cr, s, 0, oy, w, ph, 2)
        cr.set_source_rgba(*CARD_PLATE, 0.96 * (1.0 if t is None else _smooth((t - 0.22) / 0.4)))
        cr.fill()
        if self.frame is None or self.frame[0] != (w, ph):
            gaps = [(CARD_PAD - 7, CARD_PAD + self.ink_w(self.tag) + 7)]
            if self.queue:
                gaps.append((w - CARD_PAD - self.ink_w(self.queue) - 7, w - CARD_PAD + 7))
            self.frame = ((w, ph), *_card_frame(w, ph, CARD_INSET, gaps))
        _card_dust(cr, self.frame[1], self.frame[2], 0, oy, t, rest)
        tag = self.word(cr, self.tag, "tag")
        base = self.mid(tag, oy + CARD_INSET)  # The tag's ink centres on the dust line.
        self.put(cr, tag, CARD_PAD, base, None if t is None else t - CARD_TIMES["who"])
        if self.queue:
            queue = self.word(cr, self.queue, "queue")
            self.put(cr, queue, w - CARD_PAD - queue[2][0][2], base,
                     None if t is None else t - CARD_TIMES["who"] - 0.08, alpha=0.85)

    def draw_headline(self, cr, t):
        """The headline lines, their first baseline 18 px down and CARD_LINE apart."""
        for n, line in enumerate(self.lines):
            self.put(cr, self.word(cr, line, "head"), 0, 18 + n * CARD_LINE,
                     None if t is None else t - CARD_TIMES["summary"] - 0.06 * n)

    def draw_request(self, cr, t, top=0.0, bottom=math.inf):
        """The request's lines between top and bottom, the part of it in view: a long request costs no more than a
        short one. The layout is made once per card. It is never updated to the context, which lays out every line
        again."""
        cr.save()
        if t is not None:
            cr.push_group()
        cr.set_source_rgba(*TERM_FG, 0.92)
        n = max(0, bisect_right(self.req_tops, top) - 1)
        while n < len(self.req_tops) and self.req_tops[n] <= bottom:
            cr.move_to(0, self.req_bases[n])
            PangoCairo.show_layout_line(cr, self.req_layout.get_line_readonly(n))
            n += 1
        if t is not None:  # A left-to-right wipe on the reveal's clock: the mono takes no grains.
            cr.pop_group_to_source()
            mask = cairo.LinearGradient(0, 0, CARD_W - 2 * CARD_PAD, 0)
            for p, a in _reveal_stops(t - CARD_TIMES["req"], "left"):
                mask.add_color_stop_rgba(p, 0, 0, 0, a)
            cr.mask(mask)
        cr.restore()

    def button_text(self, primary):
        return _cased(self.allow_text if primary else "Decline", "label")

    def draw_button(self, cr, primary, t, hover=False):
        """Allow, a small crisp gold button, or Decline, a muted hairline one: 24 px tall, 15 px either side."""
        s = cr.get_target().get_device_scale()[0]
        a = 1.0 if t is None else _smooth((t - CARD_TIMES["btn"]) / 0.22)
        word = self.word(cr, self.button_text(primary), "allow" if primary else "decline")
        _card_crisp_rect(cr, s, 0, 0, word[2][0][2] + 30, 24, 3)
        gold = LETTERING["rim"][2]
        if primary:
            cr.set_source_rgba(*gold, (0.30 if hover else 0.20) * a)
            cr.fill_preserve()
            cr.set_source_rgba(*gold, 0.95 * a)
        else:
            cr.set_source_rgba(*CARD_MUTED, (0.6 if hover else 0.34) * a)
        cr.set_line_width(1.0 / s)
        cr.stroke()
        self.put(cr, word, 15, self.mid(word, 12),
                 None if t is None else t - CARD_TIMES["btn"] - (0.06 if primary else 0.0), "centre", a)


def _caption_pages(words):
    """Split one sentence's words into pages of at most two caption lines, so a long sentence never runs out of the
    caption area. A page ends at the last clause break (a comma, semicolon, colon, or dash) in the second half of
    what fits, else where the second line is full. When the rest of the sentence would make a short last page, the
    break moves back to an earlier clause break, or else evens out the two pages, so no page holds a word or two
    alone. The lines are measured a little narrower than they are drawn, so a page fits at every scale."""
    layout = Pango.Layout.new(PangoCairo.FontMap.get_default().create_context())
    layout.set_font_description(CAPTION_FONT)
    layout.set_width((CAPTION_W - 16) * Pango.SCALE)
    layout.set_wrap(Pango.WrapMode.WORD)
    if CAPTION_SPACING:
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_letter_spacing_new(int(CAPTION_SPACING * Pango.SCALE)))
        layout.set_attributes(attrs)

    def fits(part):
        layout.set_text(_safe_utf8(" ".join(part)), -1)
        return layout.get_line_count() <= 2

    def clause(word):
        return re.search(r"[,;:]$|^[-\u2013\u2014]$", word)

    pages = []
    while words:
        if fits(words):
            pages.append(words)
            break
        n = 1
        while n + 1 < len(words) and fits(words[:n + 1]):
            n += 1
        cut = next((k for k in range(n, n // 2, -1) if clause(words[k - 1])), n)
        if fits(words[cut:]) and 2 * len(" ".join(words[cut:])) < len(" ".join(words[:cut])):
            early = next((k for k in range(cut - 1, 0, -1) if clause(words[k - 1]) and fits(words[k:])), None)
            if early is None:
                early = cut
                while (early > 1 and len(" ".join(words[early:])) < len(" ".join(words[:early]))
                       and fits(words[early - 1:])):
                    early -= 1
            cut = early
        pages.append(words[:cut])
        words = words[cut:]
    return pages


class Caption:
    """One spoken text, split into sentences, and long sentences into pages of two lines, whose words reveal on a
    clock paced to the voice. Each page shows in turn as its first word is spoken."""

    def __init__(self, text, seconds):
        if not isinstance(seconds, (int, float)) or seconds <= 0:
            seconds = len(text) * SECONDS_PER_CHAR
        self.text, self.seconds = text, seconds
        self.lay_out()
        self.reveal = self.sentences[-1].words[-1][2] + WORD_IN
        self.clock = 0.0
        self.speed, self.voice = 1.0, None
        self.ended = False
        self.fade_at = math.inf
        self.fade_for = CAPTION_OUT

    def lay_out(self, start=None):
        """Split the text into pages in the current caption font. start is the index of a word that must begin a
        page: laying out again in another font mid-caption keeps the page on screen starting at the same word, so the
        words already spoken stay as they were and the clock goes on where it is."""
        seconds = self.seconds
        parts = [p for p in re.split(r"(?<=[.!?])\s+", " ".join(self.text.split())) if p]
        total = sum(_word_weight(w) for p in parts for w in p.split())
        self.sentences, at, index = [], 0, 0
        for part in parts:
            words = part.split(" ")
            cut = start - index if start is not None and index < start < index + len(words) else len(words)
            index += len(words)
            for page in [p for half in (words[:cut], words[cut:]) if half for p in _caption_pages(half)]:
                words, start = [], 0
                for word in page:
                    words.append((start, start + len(word), seconds * at / total))
                    at += _word_weight(word)
                    start += len(word) + 1
                self.sentences.append(Sentence(" ".join(page), words))
        for old, new in zip(self.sentences, self.sentences[1:]):
            # The old page fades once its last word is nearly in. A page break mid-sentence leaves little time, so there
            # the old page fades faster and the new one waits up to BLINK.
            old.fade_at = max(new.first - SENTENCE_LEAD, old.words[-1][2] + 0.6 * WORD_IN)
            old.fade_for = min(SENTENCE_OUT, max(QUICK_OUT, (new.first + BLINK - old.fade_at) / NEARLY_GONE))
            hold = min(BLINK, max(0.0, old.fade_at + NEARLY_GONE * old.fade_for - new.first))
            new.words = [(a, b, at + hold) for a, b, at in new.words]
            new.first = new.words[0][2]

    def relayout(self):
        """Lay out again after a font change, with the page on screen still starting at its first word."""
        start = count = 0
        for sentence in self.sentences:
            if sentence.first > self.clock:
                break
            start, count = count, count + len(sentence.words)
        self.lay_out(start)

    def fade(self, now, seconds):
        if now + seconds < self.fade_at + self.fade_for:
            self.fade_at, self.fade_for = now, seconds

    def retime(self, seconds, left):
        """The voice really lasts seconds, with left still to come. From now on the words follow the voice: they
        speed up when behind and wait when ahead. Words on screen stay, and no page is skipped."""
        self.speed = self.seconds / max(seconds, 0.1)
        self.voice = self.seconds * (1 - left / max(seconds, 0.1))  # Where the voice is now, on the caption's clock.

    def step(self, now, dt):
        speed = self.speed
        if self.voice is not None:
            self.voice += dt * speed
            speed = max(0.0, speed + (self.voice - self.clock) / CATCH_UP)
        self.clock += dt * (FINISH_SPEED if self.ended else speed)
        if self.ended and self.clock >= self.reveal and self.fade_at == math.inf:
            self.fade_at = now + HOLD

    def alpha(self, now):
        return 1.0 if now < self.fade_at else _ease_away((now - self.fade_at) / self.fade_for)

    def gone(self, now):
        return now >= self.fade_at + self.fade_for

    def visible(self):
        """(sentence, sentence alpha) for every sentence on screen at this clock."""
        shown = []
        for s in self.sentences:
            if self.clock < s.first:
                break
            out = _ease_away((self.clock - s.fade_at) / s.fade_for)
            if out > 0:
                shown.append((s, out))
        return shown


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(round(c * 255) for c in rgb)


def _escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _emphasis(markup):
    """Bold and italic on escaped text. An underscore inside a word (file_name) is not emphasis."""
    bold = rf'<span weight="600" foreground="{_hex(PALE_GOLD)}">\1</span>'
    markup = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", bold, markup, flags=re.S)
    markup = re.sub(r"(?<!\w)__(?=\S)(.+?)(?<=\S)__(?!\w)", bold, markup, flags=re.S)
    markup = re.sub(r"(?<![\w*])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\w*])", r"<i>\1</i>", markup, flags=re.S)
    return re.sub(r"(?<!\w)_(?=[^\s_])(.+?)(?<=[^\s_])_(?!\w)", r"<i>\1</i>", markup, flags=re.S)


def _md_inline(text):
    """One run of markdown text as Pango markup. Code, links, and backslash escapes are set aside first,
    so emphasis never reaches inside them."""
    kept = []

    def keep(markup):
        kept.append(markup)
        return f"\x00{len(kept) - 1}\x00"

    def link(url):
        # The address rides in font_features: Pango accepts any string there, HarfBuzz ignores one that names no
        # feature, and the panel's text buffer keeps it on the link's tag, where a click reads it.
        return (f'<span foreground="{_hex(LINK_TINT)}" underline="single" '
                f'font_features="{_escape(url).replace(chr(34), "&quot;")}">')

    text = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|>])", lambda m: keep(_escape(m[1])), text)
    text = re.sub(r"`([^`\n]+)`", lambda m: keep(f'<span foreground="{_hex(CODE_TINT)}">{_escape(m[1])}</span>'), text)
    text = re.sub(r"\[([^\]\n]+)\]\(\s*<?([^)\s>]*)>?(?:\s+\"[^\"]*\")?\s*\)",
                  lambda m: keep(link(m[2]) + _emphasis(_escape(m[1])) + "</span>"), text)
    # A bare address shows without its scheme and "www.", which is all a reader needs.
    text = re.sub(r"<?(https?://(?:www\.)?([^\s<>()]*[^\s<>().,;:!?'\"]))>?",
                  lambda m: keep(link(m[1]) + _escape(m[2]) + "</span>"), text)
    text = _emphasis(_escape(text))
    return re.sub("\x00(\\d+)\x00", lambda m: kept[int(m[1])], text)


def _checked(markup, raw):
    """The markup if Pango accepts it, or the plain escaped text, so a stray * or _ cannot break the panel."""
    try:
        Pango.parse_markup(markup, -1, "\x00")
        return markup
    except GLib.Error:
        return _escape(raw)


_BULLET = re.compile(r"( *)[-*+] +(.*)")
_NUMBER = re.compile(r"( *)(\d{1,3})[.)] +(.*)")
_HEADING = re.compile(r"(#{1,6}) +(.*?)[ #]*")
_RULE = re.compile(r" {0,3}([-*_])( *\1){2,} *")
_TABLE_ROW = re.compile(r" *\|.*\| *")


def _md_blocks(text):
    """The written answer as blocks for the last-answer panel, each a tuple whose text is Pango markup:
    ("lead", m), ("para", m), ("heading", level, m), ("item", depth, marker, m), ("table", rows), ("rule",),
    and ("code", language, raw text) for a fenced code block.
    The first paragraph is the spoken one, so it becomes the lead."""
    lines = text.replace("\x00", "").replace("\t", "    ").splitlines()
    blocks, para, i = [], [], 0

    def inline(raw):
        return _checked(_md_inline(raw), raw)

    def flush():
        if para:
            blocks.append(("para", inline("\n".join(para))))
            para.clear()

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        i += 1
        if not stripped:
            flush()
        elif stripped.startswith("```"):
            flush()
            lang, code = stripped[3:].strip(), []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i].rstrip())
                i += 1
            i += 1
            if code:
                blocks.append(("code", lang, "\n".join(code)))
        elif _RULE.fullmatch(line):
            flush()
            blocks.append(("rule",))
        elif heading := _HEADING.fullmatch(stripped):
            flush()
            blocks.append(("heading", min(3, len(heading[1])), inline(heading[2])))
        elif (_TABLE_ROW.fullmatch(line) and i < len(lines) and "-" in lines[i] and "|" in lines[i]
              and set(lines[i].strip()) <= set("|:- ")):
            flush()
            rows = [line]
            i += 1
            while i < len(lines) and _TABLE_ROW.fullmatch(lines[i]):
                rows.append(lines[i])
                i += 1
            blocks.append(("table", [[inline(cell.strip()) for cell in row.strip().strip("|").split("|")]
                                     for row in rows]))
        elif item := _BULLET.fullmatch(line) or _NUMBER.fullmatch(line):
            flush()
            body = [item[item.lastindex]]
            # Indented lines that follow an item continue it.
            while (i < len(lines) and lines[i].startswith("  ") and lines[i].strip()
                   and not (_BULLET.fullmatch(lines[i]) or _NUMBER.fullmatch(lines[i]))):
                body.append(lines[i].strip())
                i += 1
            marker = "•" if item.re is _BULLET else item[2] + "."
            blocks.append(("item", 1 if len(item[1]) >= 2 else 0, marker, inline(" ".join(body))))
        else:
            para.append(stripped.lstrip("> ") if stripped.startswith(">") else stripped)
    flush()
    if blocks and blocks[0][0] == "para":
        blocks[0] = ("lead", blocks[0][1])
    return blocks


_TERM_FAMILY = []


def _terminal_family():
    """The owner's terminal font, read once from Omarchy, then the fallbacks, as one Pango family list."""
    if not _TERM_FAMILY:
        try:
            current = subprocess.run(["omarchy", "font", "current"], capture_output=True, text=True,
                                     timeout=2).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            current = ""
        _TERM_FAMILY.extend(dict.fromkeys(([current] if current else []) + TERM_FONTS))
    return ",".join(_TERM_FAMILY)


def _code_copy_text(raw):
    """A code block's text for the clipboard: without "$ " shell prompts and without trailing blank lines, so a
    one-line command pastes with no newline."""
    lines = [line[2:] if line.startswith("$ ") else line for line in raw.split("\n")]
    return "\n".join(lines).strip("\n")


def _plain(markup):
    try:
        return Pango.parse_markup(markup, -1, "\x00")[2]
    except GLib.Error:
        return markup


def _table_lines(rows):
    """A table as monospace lines of Pango markup, its columns padded to line up, with a rule under the header."""
    columns = max(len(row) for row in rows)
    rows = [row + [""] * (columns - len(row)) for row in rows]
    widths = [max(len(_plain(row[c])) for row in rows) for c in range(columns)]
    lines = []
    for r, row in enumerate(rows):
        lines.append("   ".join(cell + " " * (widths[c] - len(_plain(cell))) for c, cell in enumerate(row)).rstrip())
        if r == 0:
            lines.append(f'<span foreground="{_hex(AMBER)}" alpha="45%">'
                         + "   ".join("─" * w for w in widths) + "</span>")
    return lines


def _terminal_paragraphs(blocks, ch, rule_chars):
    """The answer as terminal paragraphs: (style, markup, space above, left margin, hanging indent, code block
    background, raw code to copy or None, space below, no wrap). The live panel and the render use the same list."""
    out = []

    def add(style, markup, gap=0, left=TERM_PAD_X, hang=0, code=False, copy=None, below=0, nowrap=False):
        out.append((style, markup, gap, left, hang, code, copy, below, nowrap))

    rule = f'<span foreground="{_hex(AMBER)}" alpha="40%">' + "─" * rule_chars + "</span>"
    before = None
    for k, block in enumerate(blocks):
        kind = block[0]
        gap = 0 if k == 0 else 3 if kind == before == "item" else TERM_GAP
        if kind == "lead":
            add("lead", block[1], gap)
            add("rule", rule, 6, nowrap=True)
        elif kind == "para":
            add("body", block[1], gap)
        elif kind == "heading":
            hashes = f'<span foreground="{_hex(AMBER)}" weight="normal">{"#" * block[1]} </span>'
            add("heading", hashes + block[2], TERM_HEADING_GAP if k else 0)
        elif kind == "item":
            _, depth, marker, markup = block
            marker = "◦" if marker == "•" and depth else marker
            hang = (len(marker) + 1) * ch
            add("body", f'<span foreground="{_hex(AMBER)}">{marker}</span> {markup}', gap,
                TERM_PAD_X + depth * 2 * ch + hang, hang)
        elif kind == "rule":
            add("rule", rule, gap, nowrap=True)
        elif kind == "table":
            for r, line in enumerate(_table_lines(block[1])):
                add("thead" if r == 0 else "table", line, gap if r == 0 else 0, nowrap=True)
        elif kind == "code":
            _, lang, raw = block
            lines = raw.split("\n")
            add("codehead", _escape(lang or "code"), gap, TERM_PAD_X + TERM_CODE_INSET, code=True, copy=raw, below=4)
            for n, line in enumerate(lines):
                add("code", _escape(line) or " ", 0, TERM_PAD_X + TERM_CODE_INSET, code=True,
                    below=8 if n == len(lines) - 1 else 0)
        before = kind
    return out


def _panel_rect(bounds, centre_x, anchor_y, moved=None, natural_h=None):
    """Where the last-answer panel goes, in layer-shell margin coordinates: (x, y, width, height, height cap).
    bounds is the free area of the monitor, or the game window in WoW mode. By default the panel sits centred under
    the swarm with its top where the captions start; moved is where the owner dragged it. It stays fully inside
    bounds, so a tall panel moves up as far as it must."""
    bx, by, bw, bh = bounds
    w = int(min(TERM_W, bw - 2 * TERM_MARGIN))
    cap = int(min(TERM_SHARE * bh, bh - 2 * TERM_MARGIN))
    h = cap if natural_h is None else int(min(natural_h, cap))
    x, y = moved if moved else (centre_x - w / 2, anchor_y)
    x = min(max(x, bx + TERM_MARGIN), bx + bw - TERM_MARGIN - w)
    y = min(max(y, by + TERM_MARGIN), by + bh - TERM_MARGIN - h)
    return int(x), int(y), w, h, cap


def _hypr_socket(request, raw=False):
    """One request on Hyprland's command socket (as hyprctl -j would make), without starting a process. With raw, the
    answer's text, not JSON."""
    path = os.path.join(os.environ.get("XDG_RUNTIME_DIR", ""), "hypr",
                        os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", ""), ".socket.sock")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            sock.connect(path)
            sock.sendall(request.encode())
            data = b""
            while chunk := sock.recv(65536):
                data += chunk
        return data.decode(errors="replace").strip() if raw else json.loads(data)
    except (OSError, ValueError):
        return None


NO_ANIM_RULE = ('/eval hl.layer_rule({ name = "rook-overlay-no-anim", match = { namespace = "^rook-overlay$" }, '
                'no_anim = true })')


def _no_layer_anim(why):
    """Hyprland must not animate Rook's layer when it resizes: a send's narrow slid Rook in from the side. A runtime
    layer rule for the rook-overlay namespace only, in Hyprland's Lua (0.56 takes no keyword for it). A config reload
    drops it, so it is set again then. Skipped without Hyprland; a failure is one log line, and Rook goes on."""
    if not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return False
    answer = _hypr_socket(NO_ANIM_RULE, raw=True)
    if answer != "ok":
        print(f"Hyprland may still animate Rook's layer ({why}): {answer or 'no answer'}", file=sys.stderr, flush=True)
    return answer == "ok"


class Page:
    """The terminal paragraphs laid out with Pango, as the panel's text view lays them out: the render's stand-in
    for the live widget, which cannot be drawn offscreen."""

    STYLES = {"lead": (IVORY, "600"), "body": (TERM_FG, "normal"), "heading": (PALE_GOLD, "bold"),
              "rule": (TERM_FG, "normal"), "thead": (PALE_GOLD, "bold"), "table": (TERM_FG, "normal"),
              "codehead": (TERM_DIM, "normal"), "code": (CODE_TINT, "normal")}

    def __init__(self, text):
        self.text = text
        self.blocks = _md_blocks(text)
        self.width = None
        self.height = 0.0
        self.placed = []  # ("text", x, y, layout, h) or ("code", y, h) or ("copy", x, y)

    def lay_out(self, context, width):
        if width == self.width:
            return
        self.width, self.placed = width, []
        font = _font(_terminal_family(), TERM_PX)
        ch = context.get_metrics(font, None).get_approximate_char_width() / Pango.SCALE
        rule_chars = int((width - 2 * TERM_PAD_X) / ch) - 1
        y = TERM_PAD_TOP
        for style, markup, gap, left, hang, code, copy, below, nowrap in _terminal_paragraphs(self.blocks, ch, rule_chars):
            y += gap
            colour, weight = self.STYLES[style]
            layout = Pango.Layout.new(context)
            layout.set_font_description(font)
            if not nowrap:
                layout.set_wrap(Pango.WrapMode.WORD_CHAR)
                layout.set_width(int((width - TERM_PAD_X - (left - hang)) * Pango.SCALE))
                layout.set_indent(int(-hang * Pango.SCALE))
            prefix = ""
            if copy is not None:
                # The copy control sits first on the code block's header line, as in the live panel.
                prefix = " " * 7
                self.placed.append(("copy", left, y))
            layout.set_markup(_safe_utf8(f'<span foreground="{_hex(colour)}" weight="{weight}">{prefix}{markup}</span>'), -1)
            h = layout.get_pixel_extents()[1].height + (6 if copy is not None else 0)
            if code:
                self.placed.append(("code", y, h + below))
            self.placed.append(("text", left - hang, y + (3 if copy is not None else 0), layout, h))
            y += h + below
        self.height = y + TERM_PAD_BOTTOM

    def draw(self, cr, x0, y0, top, bottom):
        """Draw the parts that fall between top and bottom, in page coordinates, with the page at (x0, y0)."""
        for item in self.placed:
            if item[0] == "code":
                _, y, h = item
                cr.rectangle(x0, y0 + y, self.width, h)
                cr.set_source_rgba(*TERM_CODE_BG)
                cr.fill()
        for item in self.placed:
            if item[0] == "text":
                _, x, y, layout, h = item
                if y + h < top or y > bottom:
                    continue
                cr.move_to(x0 + x, y0 + y)
                PangoCairo.show_layout(cr, layout)
            elif item[0] == "copy":
                _, x, y = item
                _term_button(cr, x0 + x, y0 + y + 1, "copy")


def _term_button(cr, x, y, text, alpha=1.0):
    """A small terminal button: a thin gold outline and gold text, as the panel's CSS draws its buttons. alpha dims
    it, as the CSS dims a history arrow at the end of the list."""
    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(_font(_terminal_family(), 11))
    layout.set_text(_safe_utf8(text), -1)
    _, logical = layout.get_pixel_extents()
    w, h = logical.width + 14, 20
    _rounded_rect(cr, x + 0.5, y + 0.5, w, h, 4)
    cr.set_source_rgba(*AMBER, 0.45 * alpha)
    cr.set_line_width(1)
    cr.stroke()
    cr.move_to(x + 7.5, y + (h - logical.height) / 2 + 0.5)
    cr.set_source_rgba(*PALE_GOLD, 0.95 * alpha)
    PangoCairo.show_layout(cr, layout)
    return w


def _paint_answer_panel(cr, w, h, page, scroll, history=(1, 1)):
    """The render's stand-in for the last-answer panel, with the live panel's numbers: the dark terminal surface
    and gold hairline, the header (title, history arrows and position, copy all, close mark), the page scrolled to
    scroll, and the scroll mark. history is (the answer shown, counted from the oldest, how many the panel keeps)."""
    _rounded_rect(cr, 0.5, 0.5, w - 1, h - 1, 10)
    cr.set_source_rgba(*TERM_BG, 0.97)
    cr.fill_preserve()
    cr.set_source_rgba(*AMBER, 0.35)
    cr.set_line_width(1)
    cr.stroke()
    title = PangoCairo.create_layout(cr)
    title.set_font_description(_font(_terminal_family(), 12, Pango.Weight.BOLD))
    title.set_markup(f'<span foreground="{_hex(PALE_GOLD)}">rook</span>'
                     f'<span foreground="{_hex(TERM_DIM)}" weight="normal"> · last answer</span>', -1)
    cr.move_to(14, (TERM_HEAD_H - title.get_pixel_extents()[1].height) / 2)
    PangoCairo.show_layout(cr, title)
    close = PangoCairo.create_layout(cr)
    close.set_font_description(_font(_terminal_family(), 13))
    close.set_text("✕", -1)
    cw = close.get_pixel_extents()[1].width
    cr.move_to(w - 14 - cw, (TERM_HEAD_H - close.get_pixel_extents()[1].height) / 2)
    cr.set_source_rgba(*PALE_GOLD, 0.7)
    PangoCairo.show_layout(cr, close)
    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(_font(_terminal_family(), 11))
    layout.set_text("copy all", -1)
    x = w - 14 - cw - 14 - layout.get_pixel_extents()[1].width - 14
    _term_button(cr, x, (TERM_HEAD_H - 20) / 2, "copy all")
    # The history, right to left as the live header packs it with 8 pixels between: back, position, forward.
    shown, count = history
    layout.set_text(HISTORY_NEXT, -1)
    x -= 8 + layout.get_pixel_extents()[1].width + 14
    _term_button(cr, x, (TERM_HEAD_H - 20) / 2, HISTORY_NEXT, 1.0 if shown < count else HISTORY_DIM)
    position = PangoCairo.create_layout(cr)
    position.set_font_description(_font(_terminal_family(), 12))
    position.set_markup(f'<span foreground="{_hex(TERM_DIM)}">{shown} / {count}</span>', -1)
    x -= 8 + position.get_pixel_extents()[1].width
    cr.move_to(x, (TERM_HEAD_H - position.get_pixel_extents()[1].height) / 2)
    PangoCairo.show_layout(cr, position)
    layout.set_text(HISTORY_BACK, -1)
    x -= 8 + layout.get_pixel_extents()[1].width + 14
    _term_button(cr, x, (TERM_HEAD_H - 20) / 2, HISTORY_BACK, 1.0 if shown > 1 else HISTORY_DIM)
    cr.rectangle(1, TERM_HEAD_H, w - 2, 1)
    cr.set_source_rgba(*AMBER, 0.18)
    cr.fill()
    view = h - TERM_HEAD_H - 1
    cr.save()
    cr.rectangle(1, TERM_HEAD_H + 1, w - 2, view - 1)
    cr.clip()
    page.draw(cr, 0, TERM_HEAD_H + 1 - scroll, scroll, scroll + view)
    cr.restore()
    room = page.height - view
    if room > 0:
        thumb = max(24.0, view * view / page.height)
        _rounded_rect(cr, w - 7, TERM_HEAD_H + 3 + (view - 6 - thumb) * scroll / room, 3, thumb, 1.5)
        cr.set_source_rgba(*AMBER, 0.45)
        cr.fill()


def _term_css():
    """The panel's CSS: the dark terminal surface, the header, the gold buttons, selection, and the scroll mark."""
    family = ", ".join(f'"{f}"' if " " in f else f for f in _terminal_family().split(","))
    amber = ", ".join(str(round(c * 255)) for c in AMBER)
    bg = ", ".join(str(round(c * 255)) for c in TERM_BG)
    return f"""
    .rook-term {{ background-color: rgba({bg}, 0.97); border: 1px solid rgba({amber}, 0.35); border-radius: 10px; }}
    .rook-term label, .rook-term textview, .rook-term button, .rook-card button, .rook-card .card-text {{
        font-family: {family}; }}
    .rook-card .card-text {{ color: {_hex(TERM_FG)}; font-size: {TERM_PX}px; }}
    .rook-card entry {{ background: rgba(255, 255, 255, 0.04); box-shadow: none; color: {_hex(TERM_FG)};
                        border: 1px solid rgba({amber}, 0.35); border-radius: 4px; font-family: {family};
                        font-size: {TERM_PX}px; }}
    .rook-card entry:focus-within {{ border-color: rgba({amber}, 0.7); outline: none; }}
    .rook-term .term-head {{ min-height: {TERM_HEAD_H}px; padding: 0 10px 0 14px;
                             border-bottom: 1px solid rgba({amber}, 0.18); }}
    .rook-term .term-head label {{ font-size: 12px; }}
    .rook-term textview, .rook-term textview text {{ background: transparent; color: {_hex(TERM_FG)};
                                                     font-size: {TERM_PX}px; }}
    .rook-term textview text selection {{ background-color: rgba({amber}, 0.35); color: #fff6e0; }}
    .rook-term button.term, .rook-card button {{ background: none; box-shadow: none; border: 1px solid rgba({amber}, 0.45);
                              border-radius: 4px; min-height: 20px; min-width: 0; padding: 0 7px;
                              color: {_hex(PALE_GOLD)}; font-size: 11px; }}
    .rook-term button.term.close {{ border-color: transparent; font-size: 13px; }}
    .rook-term button.term:disabled {{ opacity: {HISTORY_DIM}; }}
    .rook-term button.term:hover, .rook-card button:hover {{ background-color: rgba({amber}, 0.16); }}
    .rook-card button.primary {{ background-color: rgba({amber}, 0.16); border-color: rgba({amber}, 0.7); }}
    .rook-card button.primary:hover {{ background-color: rgba({amber}, 0.26); }}
    .rook-card button.devs-face, .rook-card button.devs-face:hover {{ background: none; border: none; padding: 0;
                                                                     min-height: 0; min-width: 0; }}
    .rook-card.devs scrollbar {{ background: transparent; border: none; }}
    .rook-card.devs scrollbar slider {{ background-color: rgba({amber}, 0.45); min-width: 3px; border-radius: 2px; }}
    .rook-term button.term.done {{ color: #a8e6a1; border-color: rgba(168, 230, 161, 0.6); }}
    .rook-term scrollbar {{ background: transparent; border: none; }}
    .rook-term scrollbar slider {{ background-color: rgba({amber}, 0.45); min-width: 3px; min-height: 24px;
                                   border-radius: 2px; }}
    .rook-term undershoot, .rook-term overshoot {{ background: none; }}
    """


class _TermView(Gtk.TextView):
    """The panel's text view. It paints the code blocks' background edge to edge, as the render does: a text tag's
    paragraph background would start at the text's own margin, with no room before the code."""

    def do_snapshot_layer(self, layer, snapshot):
        if layer != Gtk.TextViewLayer.BELOW_TEXT:
            return
        buffer = self.get_buffer()
        tag = buffer.get_tag_table().lookup("codebg")
        if tag is None:
            return
        colour = Gdk.RGBA()
        colour.red, colour.green, colour.blue, colour.alpha = TERM_CODE_BG
        it = buffer.get_start_iter()
        if not it.starts_tag(tag) and not it.forward_to_tag_toggle(tag):
            return
        while it.starts_tag(tag):
            top = self.get_iter_location(it).y  # Below the space above the block, which belongs to the page.
            it.forward_to_tag_toggle(tag)
            end = it.copy()
            end.backward_char()
            y, h = self.get_line_yrange(end)
            snapshot.append_color(colour, Graphene.Rect().init(0, top, self.get_width(), y + h - top))
            if not it.forward_to_tag_toggle(tag):
                break


def _open_link(url):
    """Open an http or https address with the desktop's default handler, which hands it to the running browser. The
    handler comes from the scheme alone: Gio's launch_default_for_uri would fetch the address when no handler is set."""
    try:
        handler = Gio.AppInfo.get_default_for_uri_scheme(GLib.Uri.peek_scheme(url))
        if handler is None:
            raise GLib.Error("no default browser is set")
        handler.launch_uris([url], None)
    except GLib.Error as exc:
        print(f"link: could not open {url}: {exc.message}", file=sys.stderr, flush=True)


def _fill_buffer(buffer, paragraphs):
    """Put terminal paragraphs into a text buffer: a tag per style (made first, so the colours inside the markup win
    over them), and tags for the space above and below, the margins with their hanging indent, no wrapping, and the
    code blocks' background. Returns the anchors where the code blocks' copy controls go, with their raw code."""
    table = buffer.get_tag_table()

    def tag(name, **props):
        found = table.lookup(name)
        if found is None:
            found = Gtk.TextTag(name=name)
            for key, value in props.items():
                found.set_property(key, value)
            table.add(found)
        return found

    for style, (colour, weight) in Page.STYLES.items():
        tag(style, foreground=_hex(colour), weight={"normal": 400, "600": 600, "bold": 700}[weight])
    tag("nowrap", wrap_mode=Gtk.WrapMode.NONE)
    tag("codebg")  # Marks the code blocks; _TermView paints their background.
    buffer.set_text("", 0)
    anchors = []
    for n, (style, markup, gap, left, hang, code, copy, below, nowrap) in enumerate(paragraphs):
        if n:
            buffer.insert(buffer.get_end_iter(), "\n")
        start = buffer.get_char_count()
        if copy is not None:
            anchors.append((buffer.create_child_anchor(buffer.get_end_iter()), copy))
            buffer.insert(buffer.get_end_iter(), "  ")
        buffer.insert_markup(buffer.get_end_iter(), _safe_utf8(markup), -1)
        first, last = buffer.get_iter_at_offset(start), buffer.get_end_iter()
        names = [style, tag(f"gap{gap}", pixels_above_lines=int(gap)).get_property("name"),
                 tag(f"below{below}", pixels_below_lines=int(below)).get_property("name"),
                 tag(f"left{int(left)}-{int(hang)}", left_margin=int(left), indent=-int(hang)).get_property("name")]
        if nowrap:
            names.append("nowrap")
        if code:
            names.append("codebg")
        for name in names:
            buffer.apply_tag_by_name(name, first, last)
    return anchors


def _lerp_rect(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def _view_corner_radius(margin, bw, bh, style):
    """Outer corner radius for the viewer box: keeps the owner's rounded corner while leaving at least 8 px of black
    diagonally between the outer corner arc and the media's corner."""
    sq2 = math.sqrt(2.0)
    safe = max(0.0, (sq2 * margin - 8.0) / (sq2 - 1.0))
    return min(style["round"] * margin, style.get("round_max", 44.0), safe, bw / 2, bh / 2)


class Portal:
    """The media viewer's timeline and geometry. Rects are (x, y, w, h) in scene coordinates.
    The black box opens right in place over VIEW_OPEN while the media fades in (VIEW_IN) and a single row of dust
    settles onto the box's outer edge. Closing fades the media out (VIEW_OUT), eases the box back (VIEW_SHUT), and
    thins the edge dust away."""

    def __init__(self, now, box, media, start):
        self.at = now
        self.box_to = self.box_from = box
        self.media_to = self.media_from = media
        self.morph_at = -math.inf
        self.start = start
        self.media_at = now + VIEW_MEDIA_AT
        self.closing = None

    def replace(self, now, box, media):
        """A new media while this one shows or closes: take over from the current open progress and morph cleanly."""
        if self.closing is not None:
            p = self.opened(now)
            self.closing = None
            self.at = now - p * VIEW_OPEN
        self.box_from, self.media_from = self.box(now), self.media_rect(now)
        self.box_to, self.media_to = box, media
        self.morph_at = now
        self.media_at = max(self.media_at, now + 0.35 * VIEW_MORPH)

    def close(self, now):
        if self.closing is None:
            self.closing = now

    def _morph(self, now):
        return _smooth((now - self.morph_at) / VIEW_MORPH)

    def box(self, now):
        return _lerp_rect(self.box_from, self.box_to, self._morph(now))

    def media_rect(self, now):
        return _lerp_rect(self.media_from, self.media_to, self._morph(now))

    def _shut_at(self):
        return self.closing + 0.45 * VIEW_OUT

    def released(self, now):
        """True once the closing box has eased away."""
        return self.closing is not None and now >= self._shut_at() + VIEW_SHUT

    def opened(self, now):
        """How far the box has opened: 0 at start, 1 at full size, reversing on close."""
        p = min(1.0, max(0.0, (now - self.at) / VIEW_OPEN))
        if self.closing is not None:
            p = min(p, 1 - min(1.0, max(0.0, (now - self._shut_at()) / VIEW_SHUT)))
        return p

    def margin(self, now):
        bx, by, _, _ = self.box(now)
        mx, my, _, _ = self.media_rect(now)
        return max(0.0, min(mx - bx, my - by))

    def shape(self, now):
        """The box's rounded rect right now: (x, y, w, h, corner radius). Eases gently from 94% to 100% in place."""
        bx, by, bw, bh = self.box(now)
        style = VIEW_FRAMES[VIEW_FRAME]
        margin = self.margin(now)
        rr = _view_corner_radius(margin, bw, bh, style)
        p = self.opened(now)
        if p >= 1:
            return bx, by, bw, bh, rr
        k = 0.94 + 0.06 * _ease_out(p)
        w, h = bw * k, bh * k
        r = min(rr * k, w / 2, h / 2)
        return bx + (bw - w) / 2, by + (bh - h) / 2, w, h, r

    def centre(self, now):
        """The box's centre in scene coordinates."""
        x, y, w, h = self.box(now)
        return x + w / 2, y + h / 2

    def media_in(self, now):
        """How far the media has come in: 0 before, 1 in place, and back to 0 as it leaves."""
        p = _ease_out((now - self.media_at) / VIEW_IN)
        if self.closing is not None:
            p *= 1 - _smooth((now - self.closing) / VIEW_OUT)
        return p

    def core(self, now):
        """The black fill as drawn now: (x, y, w, h, radius, alpha)."""
        x, y, w, h, r = self.shape(now)
        alpha = _smooth(self.opened(now) / 0.55)
        return x, y, w, h, r, alpha

    def settled(self, now):
        """True once the box is open, media is in, edge dust has settled, and no morph is running."""
        return (self.closing is None and now > self.at + VIEW_LAG + VIEW_GATHER + 0.04
                and now > self.media_at + VIEW_IN + 0.04 and now > self.morph_at + VIEW_MORPH
                and self.opened(now) >= 1)

    def done(self, now):
        return self.closing is not None and now > max(self._shut_at() + VIEW_SHUT,
                                                      self.closing + VIEW_DISSOLVE_LAG + VIEW_DISSOLVE) + 0.02


class _MediaError(Exception):
    """A file the viewer refuses, with a plain sentence that says why."""


def _view_layout(bounds, natural, scale):
    """Where the viewer puts a media of natural (width, height) pixels in bounds (x, y, w, h), at this monitor scale:
    (box, media, pixels, nearest). box and media are (x, y, w, h) in bounds' coordinates; media sits on whole device
    pixels; pixels is the size to decode it to; nearest is True for an icon that grows pixel for pixel.
    The box has the media's shape, so nothing is cropped, stretched, or barred. It is at most VIEW_SHARE_W of the width
    and VIEW_SHARE_H of the height, with VIEW_BELOW kept free under it. A picture is never enlarged, except an icon."""
    bx, by, fw, fh = bounds
    nw, nh = max(1, natural[0]), max(1, natural[1])
    nearest = max(nw, nh) <= VIEW_TINY
    k = max(1, int(VIEW_TINY_TO * scale // max(nw, nh))) if nearest else 1
    # The media's logical size at one device pixel per picture pixel (k for an icon), then fitted under the caps.
    w, h = nw * k / scale, nh * k / scale
    share, least, most = VIEW_FRAMES[VIEW_FRAME]["matte"]
    cap_w = min(VIEW_SHARE_W * fw, fw - 2 * VIEW_EDGE) - 2 * most
    cap_h = min(VIEW_SHARE_H * fh, fh - VIEW_BELOW - 2 * VIEW_EDGE) - 2 * most
    f = min(1.0, cap_w / w, cap_h / h)
    if f < 1:
        nearest = False
    pw, ph = max(1, round(w * f * scale)), max(1, round(h * f * scale))
    w, h = pw / scale, ph / scale
    matte = min(most, max(least, share * min(w, h)))
    grow = max(1.0, (VIEW_MIN - 2 * matte) / min(w, h))
    box_w = min(w * grow + 2 * matte, fw - 2 * VIEW_EDGE)
    box_h = min(h * grow + 2 * matte, fh - VIEW_BELOW - 2 * VIEW_EDGE)
    x = bx + (fw - box_w) / 2
    y = by + min(max(VIEW_EDGE, fh * VIEW_CENTRE - box_h / 2), fh - VIEW_BELOW - VIEW_EDGE - box_h)
    x, y = round(x), round(y)
    box = (x, y, round(box_w), round(box_h))
    mx = round((x + (box[2] - w) / 2) * scale) / scale
    my = round((y + (box[3] - h) / 2) * scale) / scale
    return box, (mx, my, w, h), (pw, ph), nearest


def _pixbuf_surface(pixbuf, scale):
    """A Cairo image of a pixbuf, at the monitor's device scale. It goes through a fast PNG in memory, since GDK's
    direct way is deprecated; it runs in the worker thread, once per picture or frame."""
    ok, data = pixbuf.save_to_bufferv("png", ["compression"], ["1"])
    surface = cairo.ImageSurface.create_from_png(io.BytesIO(data))
    surface.set_device_scale(scale, scale)
    return surface


class _Picture:
    """A still picture, or an animated one (GIF or WebP), at the box's device pixels. frame(t) gives the image for t
    seconds on its view's clock; version changes when the frame does. An animated WebP decodes in a thread ahead of
    the play head (see _load_webp): it plays from its first frame, waits when the decoder falls behind, and loops only
    once every frame is in. Each frame is kept, so later loops decode nothing. pause, play and seek move its own clock."""

    MAX_FRAMES = 240  # ponytail: a longer GIF loops its first 240 frames; decode on the fly if that matters.
    # An animated WebP keeps every frame, as textures of at most this many bytes in all. A longer clip is held smaller
    # and the GPU scales it up. ponytail: every frame stays in memory, since libwebp takes 12 to 18 ms a frame here, which
    # is 36 to 55% of a core at 30 frames a second; a disk cache of raw frames is the upgrade if RAM matters more.
    MAX_BYTES = 1 << 29  # 512 MiB: a game shares this machine's RAM, so a long clip is held a little smaller.

    def __init__(self, frames, size, kind, done=True):
        self.frames, self.ends = [], []  # (Cairo image or Gdk.Texture, seconds it shows), and when each frame ends.
        self.size, self.kind, self.textures = size, kind, {}
        self.length, self.done, self.closed = 0.0, done, False
        self.total = None  # The file's own length in seconds, when it says, before every frame is in.
        self.shift, self.held = 0.0, None  # How far the clip lags its view's clock, and where it paused.
        for frame, d in frames:
            self.add(frame, d)

    def add(self, frame, d):
        self.frames.append((frame, d))
        self.length += d
        self.ends.append(self.length)

    @property
    def playing(self):
        return self.held is None

    def at(self, t):
        """Seconds into the loop at t on the view's clock."""
        t = self.held if self.held is not None else t - self.shift
        if not self.done and t > self.length:  # The decoder is behind: hold its newest frame until it catches up.
            self.shift += t - self.length
            t = self.length
        return t % self.length if self.done and self.length > 0 else t

    def pause(self, t):
        self.held = self.at(t)

    def play(self, t):
        if self.held is not None:
            self.shift, self.held = t - self.held, None

    def seek(self, to, t):
        to = max(0.0, min(to, self.length))
        if self.held is not None:
            self.held = to
        else:
            self.shift = t - to

    def frame(self, t):
        if len(self.frames) == 1 or self.length <= 0:
            return self.frames[0][0], 0
        n = min(bisect_right(self.ends, self.at(t)), len(self.frames) - 1)
        return self.frames[n][0], n

    def close(self):
        self.closed = True  # The decoder thread stops at its next frame.
        self.frames, self.ends, self.textures = [], [], {}


class _WebPData(ctypes.Structure):
    _fields_ = [("bytes", ctypes.c_char_p), ("size", ctypes.c_size_t)]


class _WebPAnimOptions(ctypes.Structure):
    _fields_ = [("color_mode", ctypes.c_int), ("use_threads", ctypes.c_int), ("pad", ctypes.c_uint32 * 7)]


class _WebPAnimInfo(ctypes.Structure):
    _fields_ = [("width", ctypes.c_uint32), ("height", ctypes.c_uint32), ("loops", ctypes.c_uint32),
                ("background", ctypes.c_uint32), ("frames", ctypes.c_uint32), ("pad", ctypes.c_uint32 * 4)]


def _load_webp(path, bounds, scale):
    """An animated WebP through libwebp's own decoder, which GdkPixbuf's loader uses too: every frame the file holds,
    each for its own time, as textures at the box's device pixels. The first frame is decoded here and the rest in a
    thread of low priority, ahead of the play head. None for a still, or when libwebp is missing."""
    try:
        lib = CDLL("libwebpdemux.so.2")
    except OSError:
        return None
    abi, bgra = 0x0107, 8  # WEBP_DEMUX_ABI_VERSION, and MODE_bgrA: premultiplied BGRA, as Cairo and GDK keep it.
    lib.WebPAnimDecoderNewInternal.restype = ctypes.c_void_p
    lib.WebPAnimDecoderNewInternal.argtypes = [ctypes.POINTER(_WebPData), ctypes.POINTER(_WebPAnimOptions), ctypes.c_int]
    lib.WebPAnimDecoderGetInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_WebPAnimInfo)]
    lib.WebPAnimDecoderGetNext.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),
                                           ctypes.POINTER(ctypes.c_int)]
    lib.WebPAnimDecoderDelete.argtypes = [ctypes.c_void_p]
    with open(path, "rb") as f:
        raw = f.read()
    options = _WebPAnimOptions()
    if not lib.WebPAnimDecoderOptionsInitInternal(ctypes.byref(options), abi):
        return None
    options.color_mode = bgra
    data = _WebPData(raw, len(raw))  # The decoder reads raw in place, so raw lives as long as the frames below.
    dec = lib.WebPAnimDecoderNewInternal(ctypes.byref(data), ctypes.byref(options), abi)
    if not dec:
        return None  # GdkPixbuf reads it, or says why not.
    info = _WebPAnimInfo()
    if not lib.WebPAnimDecoderGetInfo(dec, ctypes.byref(info)) or info.frames < 2:
        lib.WebPAnimDecoderDelete(dec)
        return None
    w, h, count = info.width, info.height, info.frames
    box, media, (pw, ph), nearest = _view_layout(bounds, (w, h), scale)
    k = min(1.0, math.sqrt(_Picture.MAX_BYTES / (pw * ph * 4 * count)))
    pw, ph = max(1, int(pw * k)), max(1, int(ph * k))

    def frames(raw=raw):
        buf, ends, before = ctypes.POINTER(ctypes.c_uint8)(), ctypes.c_int(), 0
        try:
            for _ in range(count):  # The file's own frame count ends the loop, never a frame's pixels.
                if not lib.WebPAnimDecoderGetNext(dec, ctypes.byref(buf), ctypes.byref(ends)):
                    raise _MediaError(f"Rook could not read the picture {os.path.basename(path)}: a frame is damaged.")
                if (pw, ph) == (w, h):
                    pixels, stride = ctypes.string_at(buf, w * h * 4), w * 4
                else:
                    canvas = (ctypes.c_uint8 * (w * h * 4)).from_address(ctypes.addressof(buf.contents))
                    src = cairo.ImageSurface.create_for_data(canvas, cairo.FORMAT_ARGB32, w, h, w * 4)
                    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, pw, ph)
                    cr = cairo.Context(out)
                    cr.scale(pw / w, ph / h)
                    cr.set_source_surface(src)
                    cr.get_source().set_filter(cairo.FILTER_NEAREST if nearest else cairo.FILTER_GOOD)
                    cr.set_operator(cairo.OPERATOR_SOURCE)
                    cr.paint()
                    out.flush()
                    pixels, stride = bytes(out.get_data()), out.get_stride()
                texture = Gdk.MemoryTexture.new(pw, ph, Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED,
                                                GLib.Bytes.new(pixels), stride)
                yield texture, max(0.02, (ends.value - before) / 1000)  # libwebp gives each frame's end time.
                before = ends.value
        finally:
            lib.WebPAnimDecoderDelete(dec)

    rest = frames()
    pic = _Picture([next(rest)], (w, h), "animation", done=False)
    at, total = 12, 0  # Each ANMF chunk holds its frame's duration in milliseconds, 24 bits at byte 12.
    while at + 8 <= len(raw):
        size = int.from_bytes(raw[at + 4:at + 8], "little")
        if raw[at:at + 4] == b"ANMF":
            total += int.from_bytes(raw[at + 20:at + 23], "little")
        at += 8 + size + (size & 1)
    pic.total = total / 1000 or None

    def decode():
        os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 10)  # The decoder yields to Rook and the game.
        try:
            for frame in rest:
                if pic.closed:
                    break
                pic.add(*frame)
        except _MediaError:
            pass  # A damaged frame ends the clip there.
        finally:
            rest.close()
            pic.done = True
    threading.Thread(target=decode, daemon=True).start()
    return box, media, pic


def _load_picture(path, info, bounds, scale):
    fmt, nw, nh = info
    if fmt.get_name() == "webp" and (webp := _load_webp(path, bounds, scale)) is not None:
        return webp
    try:
        anim = GdkPixbuf.PixbufAnimation.new_from_file(path)
        if not anim.is_static_image():
            # Step through the frames on a clock of their own, from a fixed start, so the decode is repeatable.
            start = GLib.TimeVal()
            it = anim.get_iter(start)
            first = it.get_pixbuf()
            box, media, (pw, ph), nearest = _view_layout(bounds, (first.get_width(), first.get_height()), scale)
            interp = GdkPixbuf.InterpType.NEAREST if nearest else GdkPixbuf.InterpType.HYPER
            # One loop is enough: stop when the first frame comes back, when a play-once animation ends, or at the
            # caps on frames, length and memory.
            frames, ms, seen = [], 0, first.get_pixels()
            while len(frames) < _Picture.MAX_FRAMES and ms < 20000 and len(frames) * pw * ph * 4 < 160e6:
                delay = it.get_delay_time()
                frames.append((_pixbuf_surface(it.get_pixbuf().scale_simple(pw, ph, interp), scale),
                               max(0.02, (delay if delay > 0 else 100) / 1000)))
                if delay < 0:
                    break
                ms += max(20, delay)
                at = GLib.TimeVal()
                at.tv_sec, at.tv_usec = ms // 1000, ms % 1000 * 1000
                it.advance(at)
                if it.get_pixbuf().get_pixels() == seen:
                    break
            return box, media, _Picture(frames, (first.get_width(), first.get_height()), "animation")
        # A still: decode near the size it shows at, turn it as the camera said, then scale it to the exact pixels.
        box, media, (pw, ph), nearest = _view_layout(bounds, (nw, nh), scale)
        if nearest:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
        else:
            side = max(pw, ph)
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, side, side, True) if max(nw, nh) > side else (
                GdkPixbuf.Pixbuf.new_from_file(path))
        pixbuf = pixbuf.apply_embedded_orientation() or pixbuf
        shape = (pixbuf.get_width(), pixbuf.get_height())
        if (shape[0] > shape[1]) != (nw > nh) and nw != nh:
            # The camera's turn swapped the sides: lay it out again the way it shows.
            box, media, (pw, ph), nearest = _view_layout(bounds, (nh, nw), scale)
        if shape != (pw, ph):
            pixbuf = pixbuf.scale_simple(pw, ph, GdkPixbuf.InterpType.NEAREST if nearest else GdkPixbuf.InterpType.HYPER)
        return box, media, _Picture([(_pixbuf_surface(pixbuf, scale), 0.0)], (nw, nh), "image")
    except GLib.Error as error:
        raise _MediaError(f"Rook could not read the picture {os.path.basename(path)}: {error.message}.") from None


def _srgb_curve(_pad, info):
    """A probe on the paintable sink's pad: an SDR video's caps say its curve is sRGB's. GTK would otherwise undo the
    BT.709 camera curve and brighten the dark and middle tones. Players and ffmpeg send the values to the screen as
    they are, which is what BT.709 video is made to look like on an sRGB screen."""
    event = info.get_event()
    if event is None or event.type != Gst.EventType.CAPS:
        return Gst.PadProbeReturn.OK
    caps = event.parse_caps()
    s = caps.get_structure(0)
    fmt = s.get_string("format")
    if fmt != "DMA_DRM" and not (GstVideo.video_format_get_info(GstVideo.VideoFormat.from_string(fmt)).flags
                                 & GstVideo.VideoFormatFlags.YUV):
        return Gst.PadProbeReturn.OK  # RGB frames keep their own colours.
    # What the stream leaves untagged is filled in as GStreamer does for a YUV picture of its size (BT.709 for HD).
    guess = GstVideo.VideoInfo.new()
    guess.set_format(GstVideo.VideoFormat.NV12, s.get_int("width")[1], s.get_int("height")[1])
    colorimetry = GstVideo.VideoColorimetry()
    if not (s.has_field("colorimetry") and colorimetry.from_string(s.get_string("colorimetry"))):
        colorimetry = guess.colorimetry
    for part in ("range", "matrix", "transfer", "primaries"):
        if int(getattr(colorimetry, part)) == 0:  # Unknown.
            setattr(colorimetry, part, getattr(guess.colorimetry, part))
    sdr = (GstVideo.VideoTransferFunction.BT709, GstVideo.VideoTransferFunction.BT601,
           GstVideo.VideoTransferFunction.BT2020_10, GstVideo.VideoTransferFunction.BT2020_12)
    if colorimetry.transfer in sdr:
        colorimetry.transfer = GstVideo.VideoTransferFunction.SRGB
        caps = caps.copy()
        caps.set_value("colorimetry", colorimetry.to_string())
        info.set_event(Gst.Event.new_caps(caps))
    return Gst.PadProbeReturn.OK


def _on_main(func):
    """Run func on the main thread and wait for it. gtk4paintablesink hands out its paintable only there; the main
    thread owns GLib's default context (Gtk.Application.run takes it), so the sink's own calls go there too."""
    if threading.current_thread() is threading.main_thread():
        return func()
    done, out = threading.Event(), []

    def run():
        try:
            out.append(func())
        finally:
            done.set()
        return False
    GLib.idle_add(run)
    done.wait()
    if not out:
        raise _MediaError("Rook could not hand the video to GTK.")
    return out[0]


class _Clip:
    """A video, played by GStreamer: the picture scaled to the box's device pixels by GStreamer itself and handed over
    as BGRx frames, the sound to the desktop. With VIEW_PAINTABLE live frames go to GTK as a paintable instead, at
    the video's own size, and the GPU scales them. In step mode (renders) frames are taken in order on a virtual
    clock and the sound goes nowhere."""

    kind = "video"

    def __init__(self, path, size, pixels, scale, step=False):
        self.size, self.scale, self.step_mode = size, scale, step
        self.pixels = pixels
        self.stride = cairo.Format.RGB24.stride_for_width(pixels[0])
        self.data, self._surface, self.version, self.pts = None, None, 0, -1.0
        self.textures = {}
        self.playing = self.ended = False
        self.error = None
        self.paintable = self._frame_signal = None
        self.fresh = False
        self.decoders = []
        if not self._open(path) and any(name.startswith("va") for name in self.decoders):
            # The VA decoder failed this file: play it once more in software, with VA out of playbin's choice.
            # ponytail: the rank change is process-wide for the moment of this preroll; a file loading at the same
            # time in another thread would also decode in software.
            va = [f for f in (Gst.ElementFactory.find(n) for n in self.decoders if n.startswith("va")) if f]
            ranks = [f.get_rank() for f in va]
            for f in va:
                f.set_rank(Gst.Rank.NONE)
            try:
                ok = self._open(path)
            finally:
                for f, rank in zip(va, ranks):
                    f.set_rank(rank)
            if not ok:
                raise _MediaError(f"Rook could not play the video {os.path.basename(path)}.")
        elif self.pipe is None:
            raise _MediaError(f"Rook could not play the video {os.path.basename(path)}.")

    def _open(self, path):
        """Build the pipeline and bring it to its first frame. False, with the pipeline closed, when it fails."""
        step = self.step_mode
        self.pipe = Gst.ElementFactory.make("playbin", None)
        self.pipe.set_property("uri", Gst.filename_to_uri(path))
        self.decoders = []
        self.pipe.connect("element-setup", self._element_setup)
        w, h = self.pixels
        if VIEW_PAINTABLE and not step and Gst.ElementFactory.find("gtk4paintablesink") is not None:
            # GTK takes the frames itself: as dmabuf or GL textures where it can, so nothing passes through Python.
            # Each new frame bumps version, which the viewer's frame clock watches (see _video_frame).
            sink = Gst.ElementFactory.make("gtk4paintablesink", None)
            sink.get_static_pad("sink").add_probe(Gst.PadProbeType.EVENT_DOWNSTREAM, _srgb_curve)
            _on_main(lambda: self._take_paintable(sink.get_property("paintable"), w * h))
            self.sink = None
        else:
            sink = Gst.parse_bin_from_description(
                "videoconvert ! videoscale ! video/x-raw,format=BGRx,width=%d,height=%d,pixel-aspect-ratio=1/1 ! "
                "appsink name=frames max-buffers=%d drop=%s sync=%s" % (
                    w, h, 4 if step else 1, "false" if step else "true", "false" if step else "true"), True)
            self.sink = sink.get_by_name("frames")
            if not isinstance(self.sink, GstApp.AppSink):
                raise _MediaError("GStreamer's appsink is missing, so Rook cannot play video.")
        self.pipe.set_property("video-sink", sink)
        audio = "fakesink" if step else VIEW_AUDIO_SINK
        if audio:
            self.pipe.set_property("audio-sink", Gst.ElementFactory.make(audio, None))
        self.bus = self.pipe.get_bus()
        self.pipe.set_state(Gst.State.PAUSED)
        result, _, _ = self.pipe.get_state(5 * Gst.SECOND)
        if result == Gst.StateChangeReturn.FAILURE:
            self.close()
            return False
        if self.sink is not None:
            poster = self.sink.try_pull_preroll(0)
            if poster is not None:
                self._take(poster)
        return True

    def _element_setup(self, _pipe, element):
        """Note each decoder playbin picks, so a failed VA decode can be retried in software."""
        factory = element.get_factory()
        if factory is not None and "Decoder" in (factory.get_metadata("klass") or ""):
            self.decoders.append(factory.get_name())

    def _take_paintable(self, paintable, pixels):
        self.paintable = self.data = paintable
        if self.size[0] * self.size[1] > 2 * pixels:
            # A video with more than twice the box's pixels: mipmaps keep the GPU's scaling smooth.
            paintable.set_property("scaling-filter", Gsk.ScalingFilter.TRILINEAR)
            paintable.set_property("use-scaling-filter", True)
        self._frame_signal = paintable.connect("invalidate-contents", self._new_frame)

    def _new_frame(self, _paintable):
        self.fresh = True  # frame() counts it, on the viewer's frame clock.

    def _take(self, sample):
        """Keep the frame as the decoder's bytes: copied out of GStreamer, then into the bytes the texture keeps,
        which is as few copies as Python allows. The viewer's texture is made straight from them; a Cairo surface is
        made only when a Cairo painter asks for one (see surface)."""
        buf = sample.get_buffer()
        ok, info = buf.map(Gst.MapFlags.READ)
        if not ok:
            return
        try:
            if info.size < self.stride * self.pixels[1]:
                return
            self.data, self._surface = GLib.Bytes.new(info.data), None
        finally:
            buf.unmap(info)
        self.version += 1
        self.pts = buf.pts / Gst.SECOND if buf.pts != Gst.CLOCK_TIME_NONE else self.pts
        self.textures = {}

    @property
    def surface(self):
        """The newest frame as a Cairo surface, for the offscreen renders."""
        if self._surface is None and self.data is not None:
            w, h = self.pixels
            self._surface = cairo.ImageSurface.create_for_data(bytearray(self.data.get_data()), cairo.FORMAT_RGB24,
                                                               w, h, self.stride)
            self._surface.set_device_scale(self.scale, self.scale)
        return self._surface

    def frame(self, t=None):
        """The newest frame: in step mode the frame for t seconds into the video, as a Cairo surface for the renders;
        live, as the decoder's bytes, which the viewer's texture is made from, or the sink's paintable."""
        if self.step_mode and t is not None and self.playing:
            while self.pts < t and not self.ended:
                sample = self.sink.try_pull_sample(Gst.SECOND)
                if sample is None:
                    self.ended = True
                    break
                self._take(sample)
        elif self.paintable is not None:
            if self.fresh:
                self.fresh, self.version = False, self.version + 1
        elif self.playing:
            sample = self.sink.try_pull_sample(0)
            if sample is not None:
                self._take(sample)
        return (self.surface if self.step_mode else self.data), self.version

    def poll(self):
        """Read the bus: the end of the video, or an error."""
        while (message := self.bus.pop_filtered(Gst.MessageType.EOS | Gst.MessageType.ERROR)) is not None:
            if message.type == Gst.MessageType.EOS:
                self.ended = True
            else:
                self.error = message.parse_error()[0].message

    def play(self):
        if not self.playing or self.ended:
            if self.ended:
                self.pipe.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, 0)
                self.ended, self.pts = False, -1.0
            self.pipe.set_state(Gst.State.PLAYING)
            self.playing = True

    def pause(self):
        if self.playing:
            self.pipe.set_state(Gst.State.PAUSED)
            self.playing = False

    def where(self):
        """(seconds played, seconds long), or None until GStreamer knows both."""
        if self.pipe is None:
            return None
        (ok, at), (known, length) = self.pipe.query_position(Gst.Format.TIME), self.pipe.query_duration(Gst.Format.TIME)
        return (at / Gst.SECOND, length / Gst.SECOND) if ok and known and length > 0 else None

    def seek(self, seconds):
        if self.pipe is not None:
            self.pipe.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, int(seconds * Gst.SECOND))
            self.ended, self.pts = False, -1.0

    def volume(self, value):
        if abs(self.pipe.get_property("volume") - value) > 0.01:
            self.pipe.set_property("volume", value)

    def close(self):
        if self.pipe is not None:
            self.pipe.set_state(Gst.State.NULL)
            self.pipe = None
        if self._frame_signal is not None:
            self.paintable.disconnect(self._frame_signal)
        self.paintable = self._frame_signal = None
        self.data, self._surface, self.textures = None, None, {}


def _discover(path):
    """The video's display size, or None when GStreamer does not see a video in it."""
    if Gst is None:
        return None
    try:
        info = GstPbutils.Discoverer.new(5 * Gst.SECOND).discover_uri(Gst.filename_to_uri(path))
    except GLib.Error:
        return None
    streams = [s for s in info.get_video_streams() if not s.is_image()]
    if not streams:
        return None
    s = streams[0]
    w, h = s.get_width(), s.get_height()
    num, den = s.get_par_num() or 1, s.get_par_denom() or 1
    return (round(w * num / den), h) if w and h else None


def _load_media(path, bounds, scale, step=False):
    """Check and decode a file for the viewer: (box, media, media object). It reads the file's own bytes to tell its
    type, never its name. Raises _MediaError with a plain sentence when the viewer refuses it. Runs in a worker thread
    in the live overlay."""
    if not isinstance(path, str) or not path.strip():
        raise _MediaError("No file was given to show.")
    path = os.path.expanduser(path.strip())
    name = os.path.basename(path)
    if not os.path.isabs(path):
        raise _MediaError(f"The path to {name} must be absolute.")
    if not os.path.isfile(path):
        raise _MediaError(f"There is no file at {path}.")
    if not os.access(path, os.R_OK):
        raise _MediaError(f"Rook cannot read {name}.")
    if os.path.getsize(path) == 0:
        raise _MediaError(f"{name} is empty.")
    info = GdkPixbuf.Pixbuf.get_file_info(path)
    if info is not None and info[0] is not None and info[1] > 0 and info[2] > 0:
        return _load_picture(path, info, bounds, scale)
    size = _discover(path)
    if size is None:
        if Gst is None:
            raise _MediaError(f"{name} is not a picture, and video needs GStreamer, which Rook cannot load.")
        raise _MediaError(f"{name} is not a picture or a video that Rook can show.")
    box, media, pixels, _ = _view_layout(bounds, size, scale)
    # A video is never enlarged pixel for pixel, even a small one. It is decoded at its own size and the GPU scales it
    # into the box, which costs the CPU nothing; only a video with more than twice the box's pixels is made smaller
    # in GStreamer first, since each frame is copied on the overlay's thread.
    if size[0] * size[1] <= 2 * pixels[0] * pixels[1]:
        pixels = size
    return box, media, _Clip(path, size, pixels, scale, step)



def _check_viewer():
    """The media viewer, offscreen: an animated WebP keeps every frame for its own time, even a frame that repeats the
    first, and pauses and seeks; a clip plays while it decodes; a new show replaces the open one; a hand close during
    a load keeps the newer show, and Rook's own close drops it; the hover controls fit the media."""
    import tempfile
    # A 2x2 WebP of four frames, black, white, black, white, for 40, 80, 120 and 260 ms.
    webp = bytes.fromhex(
        "52494646e400000057454250565038580a00000002000000010000010000414e494d06000000ffffffff0000414e4d4626000000000000"
        "000000010000010000280000025650384c0e0000002f01400000071011fd0f4444ff03414e4d462a00000000000000000001000001000050"
        "0000005650384c110000002f0140000007d0fffef7bfff8188e87f0000414e4d46260000000000000000000100000100007800000056"
        "50384c0e0000002f01400000071011fd0f4444ff03414e4d462a000000000000000000010000010000040100005650384c110000002f"
        "0140000007d0fffef7bfff8188e87f0000")
    with tempfile.TemporaryDirectory(prefix="rook_viewer_") as tmp:
        clip = os.path.join(tmp, "clip.webp")
        with open(clip, "wb") as f:
            f.write(webp)
        _, _, pic = _load_media(clip, (0, 0, 1920, 1080), 1.0)
        deadline = time.monotonic() + 5
        while not pic.done and time.monotonic() < deadline:
            time.sleep(0.01)
        assert pic.done and [round(d, 3) for _, d in pic.frames] == [0.04, 0.08, 0.12, 0.26], pic.frames
        assert pic.total == 0.5 and abs(pic.length - 0.5) < 1e-9, (pic.total, pic.length)
        assert [pic.frame(t)[1] for t in (0.01, 0.05, 0.13, 0.3, 0.52, 0.56)] == [0, 1, 2, 3, 0, 1]
        pic.pause(0.13)
        assert pic.frame(5.0)[1] == 2 and not pic.playing
        pic.play(5.0)
        assert pic.frame(5.12)[1] == 3, pic.at(5.12)
        pic.seek(0.05, 6.0)
        assert pic.frame(6.0)[1] == 1
        pic.close()
        # While the decoder is behind, the clip holds its newest frame and then goes on from there, never skipping.
        live = _Picture([("a", 0.1)], (2, 2), "animation", done=False)
        assert live.frame(0.5) == ("a", 0)
        live.add("b", 0.1)
        assert live.frame(0.55) == ("b", 1), live.at(0.55)

        stills = []
        for n, colour in enumerate((0x000000ff, 0xffffffff)):
            pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 4, 4)
            pixbuf.fill(colour)
            stills.append(os.path.join(tmp, f"still{n}.png"))
            pixbuf.savev(stills[-1], "png", [], [])
        a, b = stills
        events, drawn = [], []
        ov = Overlay.__new__(Overlay)
        ov.scene, ov.quitting, ov.left, ov.top, ov.bounds, ov.monitor = Scene(0.0), False, 0, 0, (0, 0, 1920, 1080), None
        ov._media_job, ov._media_loaded, ov._staged, ov._video_clock, ov._viewer_region = 0, None, None, None, None
        ov.media = ov.media_leaving = ov.media_path = None
        ov.media_title, ov.media_paused, ov._media_ended_at, ov.opacity = "", False, None, 1.0
        ov.flight = ov.return_at = None
        ov.wow = ov.in_game = ov._viewer_hover = ov._scrubbing = False
        visible = [False]
        ov.viewer = types.SimpleNamespace(set_visible=lambda v: visible.__setitem__(0, v), get_visible=lambda: visible[0],
                                          set_opacity=lambda _v: None, get_surface=lambda: None)
        ov.viewer_area = types.SimpleNamespace(queue_draw=lambda: drawn.append(1))
        ov._emit, ov._jump_home, ov._centre, ov._monitor_scale = events.append, lambda: None, lambda: (960, 540), lambda: 1.0
        ov._place = lambda _why: None
        modes = []
        saved = LayerShell.set_keyboard_mode, LayerShell.set_monitor
        LayerShell.set_keyboard_mode = lambda _win, mode: modes.append(mode)
        LayerShell.set_monitor = lambda *_: None

        def show(path, close=None):
            events.clear()
            ov._show_media({"path": path, "title": os.path.basename(path)})
            if close:
                ov._close_media(close)
            until = time.monotonic() + 5
            while ov._media_loaded is None and time.monotonic() < until:
                time.sleep(0.01)
            ov._step_viewer(time.monotonic())
            return [(e["event"], os.path.basename(e["path"]), e.get("why")) for e in events]
        try:
            assert show(a) == [("shown", "still0.png", None)]
            assert show(b) == [("closed", "still0.png", "replaced"), ("shown", "still1.png", None)]
            assert ov.media_path == b and visible[0]
            # The owner clicks the open picture away while the next one loads: the next one still shows.
            assert show(a, close="click") == [("closed", "still1.png", "click"), ("shown", "still0.png", None)]
            assert ov.media_path == a
            # Rook's own close drops a load under way.
            assert show(b, close="rook") == [("closed", "still0.png", "rook")]
            # Hover controls: a picture has the open mark and the X; a clip adds play and the scrub bar, and Space-style
            # pause toggles it. A click gives the viewer the keyboard only while the pointer is on it, never a pass over.
            show(a)
            later = time.monotonic() + 5
            assert ov._view_controls(later) == {} and modes[-1] == LayerShell.KeyboardMode.NONE
            ov._viewer_hovered(True)
            assert set(ov._view_controls(later)) == {"row", "open", "close"}
            assert modes[-1] == LayerShell.KeyboardMode.ON_DEMAND
            assert show(clip)[-1] == ("shown", "clip.webp", None)
            controls = ov._view_controls(later)
            assert set(controls) == {"row", "open", "play", "scrub", "close"} and controls["scrub"][2] > 0, controls
            ov._toggle_pause()
            assert ov.media_paused and not ov.media.playing

            def middle(rect):
                return rect[0] + rect[2] / 2, rect[1] + rect[3] / 2
            # A click on a clip plays or pauses it; it never closes it.
            box = ov._viewer_rects(later)[0]
            real_now, time.monotonic = time.monotonic, lambda: later
            try:
                ov._viewer_clicked(None, 1, *middle(box))
                assert not ov.media_paused and ov.scene.view.closing is None, "a click on a clip closed it"
                # The pointer leaves on its way to the controls: they stay for the grace, and the row keeps the pointer.
                ov._viewer_hovered(False)
                assert set(ov._view_controls(later)) >= {"play", "scrub"}, "the controls left with the pointer"
                assert modes[-1] == LayerShell.KeyboardMode.ON_DEMAND
                ov._viewer_hovered(True)
                ov._viewer_hovered(False)
                ov._viewer_hover_until = later - 1
                ov._viewer_hover_ended()
                assert modes[-1] == LayerShell.KeyboardMode.NONE and ov._view_controls(later) == {}
                assert len(ov._viewer_rects(later)) >= 2, "the controls row left the input region"
                # The X in the top-right corner lights under the pointer, and closes it.
                ov._viewer_hovered(True)
                ov._viewer_pointer_moved(None, *middle(ov._view_controls(later)["close"]))
                assert ov._close_hot, "the X did not light under the pointer"
                ov._viewer_pointer_moved(None, *middle(box))
                assert not ov._close_hot, "the X stayed lit off the pointer"
                ov._viewer_clicked(None, 1, *middle(ov._view_controls(later)["close"]))
                assert ov.scene.view.closing is not None, "the X did not close the viewer"
            finally:
                time.monotonic = real_now
            ov._viewer_hover = False
            ov.wow = ov.in_game = True
            ov._viewer_hovered(True)
            assert modes[-1] == LayerShell.KeyboardMode.NONE, "the viewer took the keyboard in the game"
        finally:
            LayerShell.set_keyboard_mode, LayerShell.set_monitor = saved
            ov._drop_media()
    print("viewer: every WebP frame at its own time, pause and seek, decode ahead, replace, close during a load, "
          "hover controls with a grace, the X, click to pause: ok")

# The render tool's scenes (see render.py). A diagram grows the swarm past GRAINS for as long as it shows.
TITLE_GROW = 1.2  # A constellation's title is this much larger than its names.
RENDER_FADE = 0.4  # How long a diagram's extra grains take to come in, and to fade once they are not needed.
RENDER_LOOSEN = 0.08  # The arrival burst when one scene or step follows another; a full one would scatter the morph.
RENDER_HOLD = 1.2  # The overlay keeps its larger canvas this long after a scene ends, while the grains fly back.
RENDER_FPS = 30  # How often a scene moves once it has formed, so a scene on screen costs the game less.
RENDER_TYPE = {kind: (_font("Noto Serif", px, Pango.Weight.HEAVY), spacing)
               for kind, (px, spacing, _) in scenes.LABEL_TYPE.items()}
RENDER_TOP = 12  # A tall scene moves down until its top, labels too, sits this far below the canvas's top.


def _interleave(form):
    """Spread the swarm's own grains evenly round a larger form's angle order, so the swarm keeps its sides as it
    arrives; the extra grains fill the gaps. form["parents"] gives each extra grain the swarm grain beside it."""
    n = form["budget"]
    core = [g * n // GRAINS for g in range(GRAINS)]
    taken = set(core)
    order = core + [k for k in range(n) if k not in taken]
    for key in ("x", "y", "part", "move", "bright", "owner", "bright_base", "grain_u", "swarm", "recs"):
        if key in form:
            form[key] = [form[key][k] for k in order]
    form["parents"] = list(range(GRAINS)) + [k * GRAINS // n for k in order[GRAINS:]]


# The answer to an old scene request: the filament diagram replaced the scene tool (2026-11-27).
SCENE_GONE = ("show_scene and show_step are gone. Call show_diagram with a graph such as \"browser > dns > server\", or "
              "start your answer with the {diagram} mark.")


def _scene_step_answer(steps, step):
    """The answer for a step of a scene with these steps: what shows, or why the step is wrong."""
    if isinstance(step, list) and step and all(type(s) is int and 0 < s <= len(steps) for s in step):
        return {"ok": True, "said": f"Showing steps {', '.join(map(str, step))} of {len(steps)}."}
    if isinstance(step, bool) or not isinstance(step, int) or not 0 <= step <= len(steps):
        return {"ok": False, "error": f"The scene has {len(steps)} steps. Give 1 to {len(steps)}, or 0 for "
                                      "the whole scene."}
    caption = steps[step - 1]["caption"] if step else ""
    return {"ok": True, "said": f"Showing step {step} of {len(steps)}." + (f" Caption: {caption}" if caption else "")}


DISPATCH_R = 60.0        # Presence half-width (logical px)
DISPATCH_REACH = 150.0   # Strand reach past presence edge
DISPATCH_GAP = 12.0      # Gap between strand end (mark) and thread name
DISPATCH_PITCH = 34.0    # Vertical row spacing
DISPATCH_MAX_ROWS = 6    # At most 6 rows; row 6 becomes "and N more" when > 6 sends arrive
DISPATCH_MAX_W = 380.0   # Max rendered name width (logical px)
DISPATCH_EDGE = 24.0     # Screen edge margin
DISPATCH_FORM = 0.30     # Wait before the first strand when the send form is already formed (s)
DISPATCH_STAGGER = 0.09  # Beat between strands leaving (s)
DISPATCH_TRAVEL = 0.56   # Strand flight to its name (s)
DISPATCH_LAND = 0.22     # The strand's head fades over its slow last stretch, then the name's reveal starts (s)
DISPATCH_HOLD = 2.20     # Hold after all rows settle (s); a second longer by the owner's ask, 2026-11-25
DISPATCH_MIN_SHOW = 1.75  # A turn moving on starts the teardown no sooner than this after the names land (s)
DISPATCH_MAX_WAIT = 8.0  # Max hold while any row is still pending (s); closes quietly at 8 s
DISPATCH_OUT = 0.70      # Teardown: strands draw back into the ports, names dissolve, the form gathers (s)
DISPATCH_GRAINS = 70     # Dust grains per strand
DISPATCH_RAW_CAP = 200   # Hard cap on raw thread title characters before layout
# Each send's window trace (Overlay._trace_send): where it goes, how many lines it keeps, how long it runs on after the
# fan, and for how long after a width change it also asks Hyprland where the layer is.
SEND_TRACE = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "rook",
                          "overlay-send-trace.jsonl")
SEND_TRACE_LINES, SEND_TRACE_AFTER, SEND_TRACE_HYPR = 2000, 2.0, 0.25
# The trace is a diagnostic: off unless ROOK_SEND_TRACE=1, so a send makes no Hyprland requests and writes no file.
SEND_TRACE_ON = os.environ.get("ROOK_SEND_TRACE") == "1"
# The states a turn moves on to after a send: the fan's teardown plays before their form. Any other state ends it at once.
FAN_TEARDOWN_STATES = ("speaking", "result", "ready", "error")

# Lit gold oklch(88% 0.11 84) and Nova core-pink mix, plus quiet outcome-mark colours (stage/dispatch.md).
_DISPATCH_DEVS_INK = (0.957, 0.824, 0.522)
_DISPATCH_DEVS_QUIET = (190 / 255.0, 184 / 255.0, 170 / 255.0)
_DISPATCH_NOVA_INK = (1.0, 0.650, 0.920)
_DISPATCH_NOVA_QUIET = (196 / 255.0, 170 / 255.0, 230 / 255.0)
_DISPATCH_LIGHT_QUIET = (0.78, 0.76, 0.72)


def _dispatch_rand(k: float) -> float:
    v = math.sin(k * 127.1 + 311.7) * 43758.5453
    return v - math.floor(v)


def _dispatch_ease(t: float) -> float:
    x = min(1.0, max(0.0, t))
    return 1.0 - (1.0 - x) ** 3


def _glint(since: float) -> float:
    """The landed mark's glint: a quick bloom as the strand lands, then a slow fade."""
    since = max(0.0, since)
    return _smooth(since / 0.06) * (1.0 - _dispatch_ease(since / 0.48))


def _clean_dispatch_text(raw, cap: int = DISPATCH_RAW_CAP) -> str:
    """Sanitize untrusted thread titles/project/machine strings: fix lone surrogates, strip control chars, cap length."""
    if not isinstance(raw, str):
        return ""
    safe = _safe_utf8(raw)
    cleaned = "".join(" " if (ord(c) < 32 or ord(c) == 127) else c for c in safe)
    cleaned = " ".join(cleaned.split())
    return cleaned[:cap]


def _norm_dispatch_outcome(val):
    if not isinstance(val, str):
        return None
    s = val.strip().lower()
    if s in ("", "pending"):
        return None
    if s == "landed":
        return "landed"
    if s in ("failed", "not-landed", "not_landed", "error"):
        return "not-landed"
    if s == "unknown":
        return "unknown"
    return None


def _fit_dispatch_name(layout, full: str, max_px: float) -> tuple[str, int, int]:
    """Cut a long name in the middle (40% head, whole-word tail) so it fits within max_px."""
    full = _safe_utf8(full)
    layout.set_text(full, -1)
    w, h = layout.get_pixel_size()
    if w <= max_px:
        return full, w, h
    keep = len(full) - 2
    while keep > 8:
        head = math.ceil(keep * 0.4)
        tail = full[len(full) - (keep - head):]
        m = re.search(r"[\s:/-]", tail[:8])
        if m:
            tail = tail[m.start() + 1:]
        cand = f"{full[:head].rstrip()}…{tail.lstrip()}"
        layout.set_text(cand, -1)
        cw, ch = layout.get_pixel_size()
        if cw <= max_px:
            return cand, cw, ch
        keep -= 2
    # Hard safety trim for extreme narrow screens or wide glyphs.
    short = full
    while len(short) > 2:
        short = short[:-1]
        cand = short.rstrip() + "…"
        layout.set_text(cand, -1)
        cw, ch = layout.get_pixel_size()
        if cw <= max_px:
            return cand, cw, ch
    layout.set_text("…", -1)
    cw, ch = layout.get_pixel_size()
    return "…", cw, ch


def _short_name(title: str, cap: int = 22) -> str:
    """A thread name for a pack's lettering: the words before a colon when they stand alone, else whole words up to
    cap characters and an ellipsis."""
    head = title.split(":")[0].strip()
    text = head if len(head) >= 3 else title.strip()
    if len(text) <= cap:
        return text
    return text[:cap - 1].rsplit(" ", 1)[0].rstrip(" ,;-") + "…"


def _lettered_text(name: str, more: bool, room: float) -> str:
    """A thread name as a pack's lettering shows it: the length rule (_short_name) in the name's case, or on a screen
    too narrow for that, the middle cut of the whole name alone, so it never has two ellipses."""
    kind = LETTERING["name"]
    text = _cased(name if more else _short_name(name), "name")
    layout = Pango.Layout.new(PangoCairo.FontMap.get_default().create_context())
    layout.set_font_description(kind["font"])
    attrs = Pango.AttrList()
    attrs.insert(Pango.attr_letter_spacing_new(int(kind["spacing"] * Pango.SCALE)))
    layout.set_attributes(attrs)
    layout.set_text(text, -1)
    if layout.get_pixel_size()[0] <= room:
        return text
    return _fit_dispatch_name(layout, _cased(name, "name"), room)[0]


def _name_spot(row, geometry, ex, ry):
    """The top left of a lettered name's sprite: its letters start DISPATCH_GAP from the strand end, on the side
    away from the presence, and their ink is centred on the strand's height."""
    ix, iy, iw, ih = geometry[0]
    return (ex + DISPATCH_GAP - ix if row["side"] > 0 else ex - DISPATCH_GAP - ix - iw), ry - iy - ih / 2.0


class DispatchState:
    """Multi-thread send fan: strands curving out of the send form's ports to plain-text names and quiet outcome marks.
    lead is the wait before the first strand: the time the send form needs to assemble."""

    def __init__(self, items, now: float, hold: float = DISPATCH_HOLD, rest_anchor: bool = False,
                 lead: float = DISPATCH_FORM):
        self.rest_anchor = bool(rest_anchor)
        self.ports = None  # The send form's two ports this frame, {1: right, -1: left}, set by Scene.update.
        parsed = []
        for entry in (items if isinstance(items, list) else []):
            if not isinstance(entry, dict):
                continue
            name = _clean_dispatch_text(entry.get("name") if "name" in entry else entry.get("thread"))
            if not name:
                continue
            parsed.append({
                "id": str(entry["id"]) if entry.get("id") is not None else None,
                "name": name,
                "project": _clean_dispatch_text(entry.get("project"), 60),
                "machine": _clean_dispatch_text(entry.get("machine"), 60),
                "outcome": _norm_dispatch_outcome(entry.get("outcome")),
                "settled": None,
                "more": False,
            })
        self.folded_rows = []
        shown = list(parsed)
        if len(parsed) > DISPATCH_MAX_ROWS:
            self.folded_rows = parsed[DISPATCH_MAX_ROWS - 1:]
            extra = len(self.folded_rows)
            shown = parsed[:DISPATCH_MAX_ROWS - 1] + [{
                "id": None, "name": f"and {extra} more", "project": "", "machine": "",
                "outcome": None, "settled": None, "more": True,
            }]
        self.t0 = now
        self.hold = max(0.0, float(hold))
        self.rows = []
        self._side_mode = None
        n = len(shown)
        for i, item in enumerate(shown):
            grains = []
            for gk in range(DISPATCH_GRAINS):
                lag = _dispatch_rand(gk + i * DISPATCH_GRAINS) * 0.5
                p0 = _dispatch_rand(gk * 3.1 + i)
                dx_o = _dispatch_rand(gk + 0.3 + i * 17.0) - 0.5
                dy_o = _dispatch_rand(gk + 0.6 + i * 19.0) - 0.5
                grains.append((lag, p0, gk * 2.3, dx_o, dy_o, gk % 5 == 0, gk % 3 == 0, gk % 3))
            where = ""
            if n == 1 and not item["more"]:
                parts = [p for p in (item["project"], item["machine"]) if p]
                where = " · ".join(parts).upper()
            self.rows.append({
                "id": item["id"],
                "name": item["name"],
                "where": where,
                "more": item["more"],
                "side": 1.0,
                "y_off": 0.0,
                "ex": 0.0,
                "path": (0.0,) * 8,
                "begin": lead + i * DISPATCH_STAGGER,
                "outcome": item["outcome"],
                "settled": None,
                "grains": grains,
            })
        self._apply_side_mode("both")
        self.landed_at = (lead + max(0, n - 1) * DISPATCH_STAGGER + DISPATCH_TRAVEL) if n else 0.0
        self.end_at = 0.0
        self.total = 0.0
        self.cut = None  # When leave() began the teardown, seconds after t0; outcomes then move it no more.
        self._recompute_schedule(0.0)
        self._fit_cache: dict[tuple, tuple[str, int, int]] = {}
        self._rooms = (DISPATCH_MAX_W, DISPATCH_MAX_W)  # The last layout's (left, right) name room.
        self._lettered: dict[tuple, tuple] = {}  # Names in a pack's lettering: (sprite, geometry) by name, room, scale.
        self._geometry: dict[tuple, tuple] = {}  # Their _type_geometry by name, room and lettering.
        self._tex_cache: dict[tuple, dict] = {}
        self._mark_cache: dict[tuple, dict] = {}

    def _tracked_rows(self):
        return [r for r in self.rows if not r["more"]] + self.folded_rows

    def _recompute_schedule(self, t_rel: float):
        """Hold until every row (visible and folded) has settled + hold, or DISPATCH_MAX_WAIT (8 s), whichever comes first."""
        if not self.rows:
            self.end_at = self.total = 0.0
            return
        if self.cut is not None:
            self.end_at, self.total = self.cut, self.cut + DISPATCH_OUT
            return
        if self.hold == 0.0:
            self.end_at = self.total = math.inf
            return
        tracked = self._tracked_rows()
        all_settled = bool(tracked) and all(r["outcome"] is not None for r in tracked)
        if all_settled:
            settled_t = max(self.landed_at, t_rel)
            self.end_at = min(DISPATCH_MAX_WAIT, settled_t + self.hold)
        else:
            self.end_at = max(self.landed_at + self.hold, DISPATCH_MAX_WAIT)
        self.total = self.end_at + DISPATCH_OUT

    def _apply_side_mode(self, mode: str):
        if mode == self._side_mode:
            return
        self._side_mode = mode
        n = len(self.rows)
        if mode == "right":
            sides = [1.0] * n
            per_side = (n, 0)
        elif mode == "left":
            sides = [-1.0] * n
            per_side = (0, n)
        else:
            sides = [-1.0 if (i % 2) else 1.0 for i in range(n)]
            per_side = ((n + 1) // 2, n // 2)
        seen = {1.0: 0, -1.0: 0}
        for row, side in zip(self.rows, sides):
            j = seen[side]
            seen[side] += 1
            k_side = per_side[0] if side > 0 else per_side[1]
            y_off = (j - (k_side - 1) / 2.0) * DISPATCH_PITCH
            sx = side * DISPATCH_R * 0.9
            sy = 0.0
            ex = side * (DISPATCH_R + DISPATCH_REACH)
            ey = y_off
            c1x, c1y = sx + side * (DISPATCH_REACH * 0.5), sy
            c2x, c2y = ex - side * (DISPATCH_REACH * 0.45), ey
            row["side"] = side
            row["y_off"] = y_off
            row["ex"] = ex
            row["path"] = (sx, sy, c1x, c1y, c2x, c2y, ex, ey)

    def layout_for_canvas(self, cx: float, canvas_w: float, mon_w: float) -> tuple[float, float]:
        """Choose both/right/left side mode from available room around cx; return (left_room, right_room) for text."""
        avail_l = max(0.0, cx - DISPATCH_EDGE)
        avail_r = max(0.0, min(float(canvas_w), float(mon_w)) - cx - DISPATCH_EDGE)
        min_side = DISPATCH_R + DISPATCH_REACH + DISPATCH_GAP + 100.0
        if avail_l < min_side and avail_r >= min_side:
            self._apply_side_mode("right")
        elif avail_r < min_side and avail_l >= min_side:
            self._apply_side_mode("left")
        else:
            self._apply_side_mode("both")
        room_l = min(DISPATCH_MAX_W, max(80.0, avail_l - (DISPATCH_R + DISPATCH_REACH + DISPATCH_GAP)))
        room_r = min(DISPATCH_MAX_W, max(80.0, avail_r - (DISPATCH_R + DISPATCH_REACH + DISPATCH_GAP)))
        self._rooms = (room_l, room_r)
        return room_l, room_r

    def leave(self, now: float):
        """Begin the teardown now, unless it has begun: the turn has moved on."""
        t = now - self.t0
        if self.hold > 0.0 and t < self.end_at:
            # The names stay up a beat after they land, even when the turn moves on at once.
            self.cut = max(t, min(self.end_at, self.landed_at + DISPATCH_MIN_SHOW))
            self._recompute_schedule(t)

    def active(self, now: float) -> bool:
        return bool(self.rows) and (self.hold == 0.0 or (now - self.t0) < self.total)

    def leaving(self, now: float) -> bool:
        """True once the hold finishes and the fan is fading/draining out (triggers Nova reverse dispatch_in)."""
        return bool(self.rows) and self.hold > 0.0 and (now - self.t0) >= self.end_at

    def tip_levels(self, now: float) -> dict[int, float]:
        """Per-side tip glow level {1: right, -1: left} in [0, 1] matching themes/forge/presence.js."""
        tips = {1: 0.0, -1: 0.0}
        if not self.rows:
            return tips
        t = max(0.0, now - self.t0)
        for row in self.rows:
            s_in = _smooth(max(0.0, min(1.0, (t - row["begin"] + 0.12) / 0.12)))
            s_out = 1.0 - _smooth(max(0.0, min(1.0, (t - row["begin"] - DISPATCH_TRAVEL - 0.25) / 0.35)))
            side_i = 1 if row["side"] > 0 else -1
            tips[side_i] = max(tips[side_i], s_in * s_out)
        return tips

    def nova_strand_data(self, now: float, tip_at: dict | None = None, y_off: float = 0.0) -> list[dict]:
        """Sample Nova plasma strands (originating at icons.dispatch.tips) + comet head positions/angles."""
        if not self.rows:
            return []
        t = max(0.0, now - self.t0)
        out = 0.0 if self.hold == 0.0 else pack_player._ease_in_out_cubic((t - self.end_at) / DISPATCH_OUT)
        if out >= 0.999:
            return []
        fade = 1.0 - out
        tips = tip_at or {1: (0.83, 0.5), -1: (0.17, 0.5)}
        out_list = []
        for row in self.rows:
            tl = t - row["begin"]
            if tl < 0.0:
                continue
            head, _arrive, since = self._row_timing(row, t)
            arrived = tl >= DISPATCH_TRAVEL
            drain = _smooth(max(0.0, min(1.0, since / 0.70))) if (row["outcome"] == "not-landed" and since >= 0.0) else 0.0
            to_u = head * (1.0 - drain)
            side = row["side"]
            side_i = 1 if side > 0 else -1
            ta = tips.get(side_i, (0.83, 0.5) if side > 0 else (0.17, 0.5))
            sx = (ta[0] - 0.5) * pack_player.REAL_SIZE
            sy = (ta[1] - 0.5) * pack_player.REAL_SIZE + y_off
            ex = row["ex"]
            ey = row["y_off"] + y_off
            path = (sx, sy, sx + side * (DISPATCH_REACH * 0.5), sy, ex - side * (DISPATCH_REACH * 0.45), ey, ex, ey)
            pts = []
            if to_u > 0.005:
                steps = 40
                for k in range(steps + 1):
                    pts.append(self._at3(path, to_u * k / steps))
            head_pos = None
            head_angle = 0.0
            if not arrived:
                p0 = self._at3(path, head)
                p1 = self._at3(path, max(0.0, head - 0.02))
                head_pos = p0
                head_angle = math.atan2(p0[1] - p1[1], p0[0] - p1[0])
            out_list.append({
                "pts": pts,
                "alpha": fade * (0.85 if arrived else 1.0),
                "head_pos": head_pos,
                "head_angle": head_angle,
                "head_tl": tl,
                "head_alpha": fade,
                "side": side,
            })
        return out_list

    def draw_nova_strands_cairo(self, cr, cx: float, cy: float, now: float, palette_dict: dict,
                                tip_at: dict | None = None):
        """Draw Nova plasma strands (pink glow, ink underlay, violet->pink gradient, marching white beads) in Cairo."""
        strands = self.nova_strand_data(now, tip_at=tip_at, y_off=0.0)
        if not strands:
            return
        ink = pack_player._hex_rgb(palette_dict.get("ink", "#150B33"), (0.082, 0.043, 0.200))
        violet = pack_player._hex_rgb(palette_dict.get("violet", "#8A45FF"), (0.541, 0.271, 1.0))
        pink = pack_player._hex_rgb(palette_dict.get("pink", "#FF5BD8"), (1.0, 0.357, 0.847))
        core = pack_player._hex_rgb(palette_dict.get("core", "#FFF4FF"), (1.0, 0.957, 1.0))
        cr.save()
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        for st in strands:
            pts = st["pts"]
            if len(pts) < 2:
                continue
            alpha = st["alpha"]
            def _trace():
                cr.new_path()
                cr.move_to(cx + pts[0][0], cy + pts[0][1])
                for px, py in pts[1:]:
                    cr.line_to(cx + px, cy + py)
            cr.set_dash([])
            _trace()
            cr.set_source_rgba(*pink, alpha * 0.16)
            cr.set_line_width(7.0)
            cr.stroke()
            _trace()
            cr.set_source_rgba(*ink, alpha * 0.55)
            cr.set_line_width(3.4)
            cr.stroke()
            grad = cairo.LinearGradient(cx + pts[0][0], cy + pts[0][1], cx + pts[-1][0], cy + pts[-1][1])
            grad.add_color_stop_rgba(0.0, *violet, alpha)
            grad.add_color_stop_rgba(1.0, *pink, alpha)
            _trace()
            cr.set_source(grad)
            cr.set_line_width(1.8)
            cr.stroke()
            length = sum(math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]) for k in range(1, len(pts)))
            phase = ((now / 2.4) % 1.0) * 11.2 * max(1, round(length / 11.2))
            _trace()
            cr.set_dash([2.2, 9.0], -phase)
            cr.set_source_rgba(*core, alpha * 0.90)
            cr.set_line_width(1.1)
            cr.stroke()
        cr.restore()

    def update_outcomes(self, items, now: float) -> bool:
        """Update outcomes in place for visible and folded rows; ignore unmatched outcome-only updates without clearing."""
        if not self.rows or not isinstance(items, list) or not items:
            return False
        outcome_only = all(
            isinstance(e, dict) and not _clean_dispatch_text(e.get("name") if "name" in e else e.get("thread"))
            for e in items
        )
        tracked = self._tracked_rows()
        matched = []
        for entry in items:
            if not isinstance(entry, dict):
                return outcome_only
            eid = str(entry["id"]) if entry.get("id") is not None else None
            ename = _clean_dispatch_text(entry.get("name") if "name" in entry else entry.get("thread"))
            found = None
            for row in tracked:
                if eid is not None and row["id"] is not None and row["id"] == eid:
                    found = row
                    break
                if ename and row["name"] == ename:
                    found = row
                    break
            if found is None:
                if outcome_only:
                    continue
                return False
            matched.append((found, _norm_dispatch_outcome(entry.get("outcome"))))
        if not matched:
            return outcome_only
        t = max(0.0, now - self.t0)
        for row, outcome in matched:
            if outcome != row["outcome"]:
                row["outcome"] = outcome
                if outcome is not None:
                    row["settled"] = max(t, row.get("begin", 0.0) + DISPATCH_TRAVEL)
                else:
                    row["settled"] = None
        if not self.leaving(now):  # A late outcome never reopens a teardown.
            self._recompute_schedule(t)
        return True

    @staticmethod
    def _at3(path, u: float) -> tuple[float, float]:
        sx, sy, c1x, c1y, c2x, c2y, ex, ey = path
        m = 1.0 - u
        m2, u2 = m * m, u * u
        return (m2 * m * sx + 3.0 * m2 * u * c1x + 3.0 * m * u2 * c2x + u2 * u * ex,
                m2 * m * sy + 3.0 * m2 * u * c1y + 3.0 * m * u2 * c2y + u2 * u * ey)

    @staticmethod
    def _tan3(path, u: float) -> tuple[float, float]:
        sx, sy, c1x, c1y, c2x, c2y, ex, ey = path
        m = 1.0 - u
        return (3.0 * m * m * (c1x - sx) + 6.0 * m * u * (c2x - c1x) + 3.0 * u * u * (ex - c2x),
                3.0 * m * m * (c1y - sy) + 6.0 * m * u * (c2y - c1y) + 3.0 * u * u * (ey - c2y))

    def row_path(self, row):
        """A row's strand curve: from the send form's port on its side when the form has ports, else the default."""
        if self.ports is None:
            return row["path"]
        px, py = self.ports[1 if row["side"] > 0 else -1]
        return (px, py, px + row["side"] * DISPATCH_REACH * 0.45, py) + row["path"][4:]

    def _row_timing(self, row, t: float):
        begin = row["begin"]
        # A gentle ease out: the head is half way at a third of the flight and still moving through its last tenth.
        head = 1.0 - (1.0 - min(1.0, max(0.0, (t - begin) / DISPATCH_TRAVEL))) ** 1.8
        arrive = _dispatch_ease((t - (begin + DISPATCH_TRAVEL - 0.22)) / 0.26)
        if row["outcome"] is not None and row["settled"] is None:
            row["settled"] = max(t, begin + DISPATCH_TRAVEL)
        since = -1.0 if row["settled"] is None else (t - row["settled"])
        return head, arrive, since

    def eval_gl_rows(self, now: float, y_off: float = 0.0) -> list[float]:
        """Build 11-float vertex rows for all live strand grains and comet heads (drawn by _DustGL)."""
        if not self.rows:
            return []
        t = max(0.0, now - self.t0)
        out = 0.0 if self.hold == 0.0 else _dispatch_ease((t - self.end_at) / DISPATCH_OUT)
        if out >= 0.999:
            return []
        fade_out = 1.0 - out ** 3  # The strands draw back into the ports (and the ports into the centre) as they go.
        rows_out: list[float] = []
        sin = math.sin
        at3 = self._at3
        tan3 = self._tan3
        for row in self.rows:
            head, _arrive, since = self._row_timing(row, t)
            if head <= 0.001:
                continue
            begin = row["begin"]
            lost = row["outcome"] == "not-landed"
            path = self.row_path(row)
            # One strand from the fire through the hold, with no switch at the landing: the body's grains flow along
            # the path and show behind the head, every third grain also rides the head as its comet tail, and both
            # ease into the resting look across the landing (settle), so nothing jumps there.
            settle = _smooth((t - begin - DISPATCH_TRAVEL + 0.14) / 0.34)
            drain = _dispatch_ease(since / 0.7) if lost and since >= 0.0 else 0.0
            dim = 1.0 - _dispatch_ease(since / 0.9) if lost and since >= 0.0 else 1.0
            edge = head + 0.08 * settle
            for lag, p0, jph, dx_o, dy_o, big, bright3, tone_i in row["grains"]:
                flow = (p0 + (t - begin) / 2.4) % 1.0
                fly, rest = (0.62, 0.62) if bright3 else (0.45, 0.24)
                parts = [(flow, (fly + (rest - fly) * settle) * _smooth((edge - flow) / 0.08), 40.0)]
                if bright3 and settle < 1.0:
                    k = lag * 2.0
                    parts.append((head - 0.16 * k, 0.9 * (1.0 - 0.7 * k) * (1.0 - settle), 65.0))
                for u, a, speed in parts:
                    u *= (1.0 - drain) * (1.0 - out)
                    a *= dim
                    if u <= 0.0 or u > 1.0 or a <= 0.01:
                        continue
                    gx, gy = at3(path, u)
                    gy += y_off + sin(jph + t * 4.0) * 1.6
                    vx, vy = tan3(path, u)
                    vs = speed * (1.0 - settle) / (math.hypot(vx, vy) or 1.0)
                    rad = 2.15 if big else 1.55
                    b_val = 0.90 if (big or bright3) else 0.65
                    rows_out.extend((gx, gy, a * fade_out * 1.15, 0.35, vx * vs, vy * vs, rad, b_val, 1.0,
                                     float(tone_i), 1.0))
            u_h = head * (1.0 - out)
            if head < 1.0 and u_h > 0.0:
                # The head fades as it slows into the strand's end, so it hands over to the name's reveal: no pop. A
                # teardown in flight draws it back with the strand.
                land = 1.0 - _smooth((t - begin - DISPATCH_TRAVEL + DISPATCH_LAND) / DISPATCH_LAND)
                a_h = 0.75 * (1.0 - out) * fade_out * land
                if a_h > 0.01:
                    hx, hy = at3(path, u_h)
                    rows_out.extend((hx, hy + y_off, a_h, 0.85, 0.0, 0.0, 14.0, 0.95, 1.0, 2.0, 1.0))
        return rows_out

    def _lettered_name(self, row, room: float, scale: float):
        """A row's name in the pack's lettering: its sprite and _type_geometry, cached per name, room and scale."""
        key = (row["name"], int(round(room)), row["more"], round(scale, 3), id(LETTERING))
        if key not in self._lettered:
            text = _lettered_text(row["name"], row["more"], room)
            probe = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1))
            sprite = _lettering_sprite(probe, text, scale, "name", _DISPATCH_DEVS_QUIET if row["more"] else None)[0]
            self._lettered[key] = (sprite, self._row_geometry(row, room))
        return self._lettered[key]

    def _row_geometry(self, row, room: float):
        """A row's name lettered for room: its _type_geometry, cached per name, room and lettering."""
        key = (row["name"], int(round(room)), row["more"], id(LETTERING))
        if key not in self._geometry:
            kind = LETTERING["name"]
            text = _lettered_text(row["name"], row["more"], room)
            self._geometry[key] = _type_geometry(text, kind["font"], kind["spacing"])
        return self._geometry[key]

    def _reveal_at(self, row, t: float) -> float:
        """Seconds into a name's reveal at t (s after t0): it starts as the strand lands, and in the teardown it runs
        back to 0 as the strand draws back, so the name dissolves from its far end into the strand. The reveal's
        mask alone fades the name out then. A name whose strand had not landed when the teardown began never shows."""
        if self.hold > 0.0 and t > self.end_at:
            at_end = self.end_at - (row["begin"] + DISPATCH_TRAVEL)
            if at_end <= 0.0:
                return -1.0
            return min(at_end, REVEAL_SECONDS) * (1.0 - _dispatch_ease((t - self.end_at) / DISPATCH_OUT)) - 1e-6
        return t - (row["begin"] + DISPATCH_TRAVEL)

    def reveal_rows(self, now: float, y_off: float = 0.0) -> list[float]:
        """The names' reveal grains for the dust engine (see _reveal_rows), relative to the presence centre. A name
        has grains only in its first REVEAL_SECONDS and in the teardown, when the reveal runs backwards: the name
        dissolves into dust that runs back to its strand."""
        if not LETTERING or LETTERING["reveal"] != "spread":
            return []
        t = max(0.0, now - self.t0)
        rows: list[float] = []
        for row in self.rows:
            t_r = self._reveal_at(row, t)
            if 0.0 <= t_r < REVEAL_SECONDS:
                geometry = self._row_geometry(row, self._rooms[0 if row["side"] < 0 else 1])
                sx, sy = _name_spot(row, geometry, row["ex"], row["y_off"] + y_off)
                rows += _reveal_rows(geometry, t_r, "left" if row["side"] > 0 else "right", sx, sy)
        return rows

    def draw_strands_cairo(self, cr, cx: float, cy: float, now: float, palette, is_nova: bool = False):
        """Fast C-native Cairo fallback for strand grains and comet heads (< 0.4 ms)."""
        rows_gl = self.eval_gl_rows(now, 0.0)
        if not rows_gl:
            return
        light = palette["operator"] != cairo.OPERATOR_ADD
        if is_nova:
            cols = ((0.541, 0.271, 1.0), (1.0, 0.357, 0.847), (1.0, 0.957, 1.0))
        elif light:
            lt = devs_pack.LOOK["light"]
            cols = (lt["amber_far"], lt["amber_mid"], lt["amber_near"])
        else:
            cols = ((0.949, 0.698, 0.278), (0.976, 0.812, 0.490), (1.0, 0.922, 0.698))
        cr.save()
        cr.set_operator(cairo.OPERATOR_OVER if light else cairo.OPERATOR_ADD)
        tau = 2.0 * math.pi
        for idx in range(0, len(rows_gl), 11):
            gx, gy, da, _, _, _, rad, _, _, tone_f, _ = rows_gl[idx:idx + 11]
            r_c, g_c, b_c = cols[int(tone_f) % 3]
            if rad > 8.0:
                pat = cairo.RadialGradient(cx + gx, cy + gy, 0.0, cx + gx, cy + gy, rad)
                pat.add_color_stop_rgba(0.0, r_c, g_c, b_c, min(1.0, da * 0.75))
                pat.add_color_stop_rgba(1.0, r_c, g_c, b_c, 0.0)
                cr.set_source(pat)
                cr.arc(cx + gx, cy + gy, rad, 0.0, tau)
                cr.fill()
            else:
                cr.set_source_rgba(r_c, g_c, b_c, min(1.0, da * 0.85))
                cr.arc(cx + gx, cy + gy, rad * 0.72, 0.0, tau)
                cr.fill()
        cr.restore()

    def draw_overlay(self, cr, cx: float, cy: float, now: float, mon_w: float, palette, is_nova: bool = False):
        """Draw the thread names (plain text, middle-cut, facing the presence), single-send subtitle, and outcome marks."""
        if not self.rows:
            return
        t = max(0.0, now - self.t0)
        out = 0.0 if self.hold == 0.0 else _dispatch_ease((t - self.end_at) / DISPATCH_OUT)
        if out >= 0.999:
            return
        light = (palette["operator"] != cairo.OPERATOR_ADD) and not is_nova
        fam = "IBM Plex Sans" if is_nova else (CAPTION_FONT.get_family() or "Noto Serif")
        wt_main = Pango.Weight.SEMIBOLD if is_nova else Pango.Weight.BOLD
        desc_main = _font(fam, 21, wt_main)
        desc_more = _font(fam, 21, Pango.Weight.NORMAL)
        desc_where = _font(LABEL_FONT.get_family() or fam, 11, Pango.Weight.SEMIBOLD)
        ink_rgb = _DISPATCH_NOVA_INK if is_nova else _DISPATCH_DEVS_INK
        quiet_rgb = _DISPATCH_NOVA_QUIET if is_nova else (_DISPATCH_LIGHT_QUIET if light else _DISPATCH_DEVS_QUIET)
        mark_rgb = (1.0, 0.957, 1.0) if is_nova else ((0.44, 0.26, 0.04) if light else (1.0, 0.922, 0.698))
        shade_rgb = (0.06, 0.03, 0.14) if is_nova else ((0.21, 0.21, 0.21) if light else INK)
        room_l, room_r = self.layout_for_canvas(cx, mon_w, mon_w)
        tau = 2.0 * math.pi

        layout = PangoCairo.create_layout(cr)
        cr.save()
        for row in self.rows:
            head, arrive, since = self._row_timing(row, t)
            show = arrive * (1.0 - out)
            if show <= 0.005:
                continue
            lost = row["outcome"] == "not-landed"
            dim = 0.55 if lost else (0.80 if row["outcome"] == "unknown" else 1.0)
            fade = (dim + (1.0 - dim) * (1.0 - _dispatch_ease(since / 0.40))) if since >= 0.0 else 1.0
            name_alpha = show * fade
            side = row["side"]
            room = room_r if side > 0 else room_l
            room_key = int(round(room))
            ex = cx + row["ex"]
            ry = cy + row["y_off"]

            # A row whose strand had not landed when the teardown began shows no mark or subtitle.
            landed_ok = self.hold == 0.0 or t <= self.end_at or self.end_at >= row["begin"] + DISPATCH_TRAVEL
            # 1) Outcome mark at strand end (rows still pending at 8 s close quietly with no mark).
            if landed_ok and head >= 1.0 and not row["more"] and not (row["outcome"] is None and out > 0.001):
                m_show = show * _smooth((t - row["begin"] - DISPATCH_TRAVEL) / 0.12)  # It fades in as the strand lands.
                cr.save()
                if is_nova:
                    # Nova vector marks (presence.js): thin ink rim so every mark holds on dark and light desktops.
                    nv_ink = (0.082, 0.043, 0.200)
                    nv_violet = (0.541, 0.271, 1.0)
                    nv_pink = (1.0, 0.357, 0.847)
                    nv_core = (1.0, 0.957, 1.0)
                    nv_quiet = (0.627, 0.549, 0.878)
                    cr.set_operator(cairo.OPERATOR_OVER)
                    def _nv_dot(dx_c, dy_c, rad, col, a_val):
                        cr.new_path()
                        cr.arc(dx_c, dy_c, rad + 0.6, 0.0, tau)
                        cr.set_source_rgba(*nv_ink, min(1.0, a_val * 0.60))
                        cr.fill()
                        cr.new_path()
                        cr.arc(dx_c, dy_c, rad, 0.0, tau)
                        cr.set_source_rgba(*col, min(1.0, a_val))
                        cr.fill()
                    if row["outcome"] is None:
                        br = 0.45 + 0.35 * (0.5 + 0.5 * math.sin(t * 4.0))
                        _nv_dot(ex, ry, 2.1, nv_violet, m_show * br)
                    elif row["outcome"] == "landed":
                        _nv_dot(ex, ry, 2.6, nv_pink, m_show)
                        g = 1.0 - min(1.0, max(0.0, since) / 0.50)
                        if g > 0.01 and since > 0.0:
                            r_g = 7.0 * (0.6 + 0.4 * g)
                            cr.new_path()
                            cr.move_to(ex - r_g, ry)
                            cr.curve_to(ex - r_g * 0.25, ry, ex, ry - r_g * 0.25, ex, ry - r_g)
                            cr.curve_to(ex, ry - r_g * 0.25, ex + r_g * 0.25, ry, ex + r_g, ry)
                            cr.curve_to(ex + r_g * 0.25, ry, ex, ry + r_g * 0.25, ex, ry + r_g)
                            cr.curve_to(ex, ry + r_g * 0.25, ex - r_g * 0.25, ry, ex - r_g, ry)
                            cr.close_path()
                            cr.set_source_rgba(*nv_core, min(1.0, m_show * g * _smooth(since / 0.06)))
                            cr.fill()
                    elif lost:
                        cr.new_path()
                        cr.arc(ex, ry, 3.0, 0.0, tau)
                        cr.set_source_rgba(*nv_ink, min(1.0, m_show * 0.50))
                        cr.set_line_width(2.6)
                        cr.stroke_preserve()
                        cr.set_source_rgba(*nv_quiet, min(1.0, m_show))
                        cr.set_line_width(1.3)
                        cr.stroke()
                    else:
                        for n_g in (0, 1, 2):
                            _nv_dot(ex - side * n_g * 5.0, ry, 1.6, nv_quiet, m_show)
                elif row["outcome"] is None:
                    cr.set_operator(cairo.OPERATOR_OVER if light else cairo.OPERATOR_ADD)
                    br = 0.45 + 0.35 * math.sin(t * 8.0)
                    cr.set_source_rgba(*mark_rgb, min(1.0, m_show * br))
                    cr.new_path()
                    cr.arc(ex, ry, 2.1, 0.0, tau)
                    cr.fill()
                elif row["outcome"] == "landed":
                    cr.set_operator(cairo.OPERATOR_OVER if light else cairo.OPERATOR_ADD)
                    cr.set_source_rgba(*mark_rgb, min(1.0, m_show))
                    cr.new_path()
                    cr.arc(ex, ry, 2.6, 0.0, tau)
                    cr.fill()
                    glint = m_show * 0.70 * _glint(since)
                    if glint > 0.01:
                        pat = cairo.RadialGradient(ex, ry, 0.0, ex, ry, 14.0)
                        pat.add_color_stop_rgba(0.0, *mark_rgb, min(1.0, glint))
                        pat.add_color_stop_rgba(1.0, *mark_rgb, 0.0)
                        cr.set_source(pat)
                        cr.new_path()
                        cr.arc(ex, ry, 14.0, 0.0, tau)
                        cr.fill()
                elif lost:
                    cr.set_operator(cairo.OPERATOR_OVER)
                    ring_rgb = (0.36, 0.32, 0.28) if light else quiet_rgb
                    cr.set_source_rgba(*ring_rgb, min(1.0, m_show * 0.85))
                    cr.set_line_width(1.3)
                    cr.new_path()
                    cr.arc(ex, ry, 3.4, 0.0, tau)
                    cr.stroke()
                else:  # unknown: three quiet grains 5 px apart extending back along the strand
                    cr.set_operator(cairo.OPERATOR_OVER if light else cairo.OPERATOR_ADD)
                    dot_rgb = (0.36, 0.32, 0.28) if light else quiet_rgb
                    cr.set_source_rgba(*dot_rgb, min(1.0, m_show))
                    for n_g in (0, 1, 2):
                        cr.new_path()
                        cr.arc(ex - side * n_g * 5.0, ry, 1.6, 0.0, tau)
                        cr.fill()
                cr.restore()

            # 2) Plain-text middle-cut thread name, facing the presence, with soft shade backing. A pack's lettering
            # draws it crisp from a cached sprite instead, revealed as it arrives, with no backing.
            if LETTERING and not is_nova:
                sprite, geometry = self._lettered_name(row, room, cr.get_target().get_device_scale()[0])
                sx, sy = _device_round(cr, *_name_spot(row, geometry, ex, ry))
                t_r = self._reveal_at(row, t)  # The name shows from its strand's landing.
                cr.set_operator(cairo.OPERATOR_OVER)
                cr.set_source_surface(sprite, sx, sy)
                if LETTERING["reveal"] == "spread" and 0.0 <= t_r < REVEAL_SECONDS:
                    origin = "left" if side > 0 else "right"
                    cr.mask(_reveal_mask(geometry[0], t_r, origin, sx, sy, fade))
                    _paint_reveal_rows(cr, _reveal_rows(geometry, t_r, origin, sx, sy))
                else:
                    cr.paint_with_alpha((1.0 - out) * fade if t_r >= 0.0 else 0.0)
                tx, th = sx + geometry[0][0], geometry[0][3]
            else:
                desc = desc_more if row["more"] else desc_main
                layout.set_font_description(desc)
                ckey = (row["name"], room_key, fam, row["more"])
                if ckey not in self._fit_cache:
                    self._fit_cache[ckey] = _fit_dispatch_name(layout, row["name"], room)
                shown_txt, tw, th = self._fit_cache[ckey]
                layout.set_text(shown_txt, -1)
                slide_x = side * (-14.0 * (1.0 - arrive) + 10.0 * out)
                tx = (ex + DISPATCH_GAP + slide_x) if side > 0 else (ex - DISPATCH_GAP - tw + slide_x)
                ty = ry - th / 2.0

                cr.set_operator(cairo.OPERATOR_OVER)
                if light:
                    _rounded_rect(cr, tx - 7.0, ty - 4.0, tw + 14.0, th + 8.0, 8.0)
                    cr.set_source_rgba(*shade_rgb, 0.92 * name_alpha)
                    cr.fill()
                else:
                    # Soft shade pill behind the name (matches spoken captions and stage.css).
                    for pad_x, pad_y, a_bg in ((16.0, 7.0, 0.16), (10.0, 4.0, 0.30)):
                        _rounded_rect(cr, tx - pad_x, ty - pad_y, tw + 2 * pad_x, th + 2 * pad_y, (th + 2 * pad_y) / 2.0)
                        cr.set_source_rgba(*shade_rgb, a_bg * name_alpha)
                        cr.fill()
                    cr.move_to(tx, ty + 1.0)
                    cr.set_source_rgba(*shade_rgb, 0.65 * name_alpha)
                    PangoCairo.show_layout(cr, layout)

                cr.move_to(tx, ty)
                cr.set_source_rgba(*(quiet_rgb if row["more"] else ink_rgb), name_alpha)
                PangoCairo.show_layout(cr, layout)

            # 3) Single-send subtitle: PROJECT · MACHINE in 11 px label type.
            if row["where"] and landed_ok:
                w_alpha = _smooth((t - row["begin"] - DISPATCH_TRAVEL - 0.18) / 0.28) * (1.0 - out)  # After the name.
                if w_alpha > 0.005:
                    layout.set_font_description(desc_where)
                    layout.set_text(row["where"], -1)
                    ww, wh = layout.get_pixel_size()
                    if light:
                        _rounded_rect(cr, tx - 6.0, ry + th / 2.0 + 1.0, ww + 12.0, wh + 4.0, 5.0)
                        cr.set_source_rgba(*shade_rgb, 0.85 * w_alpha)
                        cr.fill()
                    cr.move_to(tx, ry + th / 2.0 + 2.0)
                    cr.set_source_rgba(*quiet_rgb, 0.88 * w_alpha)
                    PangoCairo.show_layout(cr, layout)
        cr.restore()

    @staticmethod
    def _surface_to_texture(img: cairo.ImageSurface):
        img.flush()
        return Gdk.MemoryTexture.new(img.get_width(), img.get_height(),
                                     Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED,
                                     GLib.Bytes.new(bytes(img.get_data())), img.get_stride())

    def _get_mark_textures(self, scale: float, palette, is_nova: bool) -> dict:
        """Render the small static outcome-mark textures once per (palette, is_nova, scale): zero per-frame alloc."""
        key = (id(palette), bool(is_nova), round(scale, 3))
        cached = self._mark_cache.get(key)
        if cached is not None:
            return cached
        light = (palette["operator"] != cairo.OPERATOR_ADD) and not is_nova
        quiet_rgb = _DISPATCH_NOVA_QUIET if is_nova else (_DISPATCH_LIGHT_QUIET if light else _DISPATCH_DEVS_QUIET)
        mark_rgb = (1.0, 0.957, 1.0) if is_nova else ((0.44, 0.26, 0.04) if light else (1.0, 0.922, 0.698))
        nv_ink, nv_violet, nv_pink, nv_core, nv_quiet = (
            (0.082, 0.043, 0.200), (0.541, 0.271, 1.0), (1.0, 0.357, 0.847), (1.0, 0.957, 1.0), (0.627, 0.549, 0.878)
        )
        tau = 2.0 * math.pi

        def _make(lw, lh, draw_fn):
            img = cairo.ImageSurface(cairo.FORMAT_ARGB32, max(1, math.ceil(lw * scale)), max(1, math.ceil(lh * scale)))
            img.set_device_scale(scale, scale)
            c = cairo.Context(img)
            draw_fn(c, lw / 2.0, lh / 2.0)
            return self._surface_to_texture(img), lw, lh

        def _dot_nv(c, cx_m, cy_m, r, col):
            c.new_path(); c.arc(cx_m, cy_m, r + 0.6, 0.0, tau); c.set_source_rgba(*nv_ink, 0.60); c.fill()
            c.new_path(); c.arc(cx_m, cy_m, r, 0.0, tau); c.set_source_rgba(*col, 1.0); c.fill()

        def _draw_pending(c, cx_m, cy_m):
            if is_nova:
                _dot_nv(c, cx_m, cy_m, 2.1, nv_violet)
            else:
                c.set_source_rgba(*mark_rgb, 1.0); c.arc(cx_m, cy_m, 2.1, 0.0, tau); c.fill()

        def _draw_landed(c, cx_m, cy_m):
            if is_nova:
                _dot_nv(c, cx_m, cy_m, 2.6, nv_pink)
            else:
                c.set_source_rgba(*mark_rgb, 1.0); c.arc(cx_m, cy_m, 2.6, 0.0, tau); c.fill()

        def _draw_glint(c, cx_m, cy_m):
            if is_nova:
                r_g = 7.0
                c.move_to(cx_m - r_g, cy_m)
                c.curve_to(cx_m - r_g * 0.25, cy_m, cx_m, cy_m - r_g * 0.25, cx_m, cy_m - r_g)
                c.curve_to(cx_m, cy_m - r_g * 0.25, cx_m + r_g * 0.25, cy_m, cx_m + r_g, cy_m)
                c.curve_to(cx_m + r_g * 0.25, cy_m, cx_m, cy_m + r_g * 0.25, cx_m, cy_m + r_g)
                c.curve_to(cx_m, cy_m + r_g * 0.25, cx_m - r_g * 0.25, cy_m, cx_m - r_g, cy_m)
                c.close_path(); c.set_source_rgba(*nv_core, 1.0); c.fill()
            else:
                pat = cairo.RadialGradient(cx_m, cy_m, 0.0, cx_m, cy_m, 14.0)
                pat.add_color_stop_rgba(0.0, *mark_rgb, 0.70)
                pat.add_color_stop_rgba(1.0, *mark_rgb, 0.0)
                c.set_source(pat); c.arc(cx_m, cy_m, 14.0, 0.0, tau); c.fill()

        def _draw_ring(c, cx_m, cy_m):
            if is_nova:
                c.arc(cx_m, cy_m, 3.0, 0.0, tau)
                c.set_source_rgba(*nv_ink, 0.50); c.set_line_width(2.6); c.stroke_preserve()
                c.set_source_rgba(*nv_quiet, 1.0); c.set_line_width(1.3); c.stroke()
            else:
                ring_rgb = (0.36, 0.32, 0.28) if light else quiet_rgb
                c.arc(cx_m, cy_m, 3.4, 0.0, tau)
                c.set_source_rgba(*ring_rgb, 0.85); c.set_line_width(1.3); c.stroke()

        def _draw_unk(side_s):
            def _fn(c, cx_m, cy_m):
                dot_rgb = (0.36, 0.32, 0.28) if light else quiet_rgb
                for n_g in (0, 1, 2):
                    dx_c = cx_m - side_s * n_g * 5.0
                    if is_nova:
                        _dot_nv(c, dx_c, cy_m, 1.6, nv_quiet)
                    else:
                        c.new_path(); c.set_source_rgba(*dot_rgb, 1.0); c.arc(dx_c, cy_m, 1.6, 0.0, tau); c.fill()
            return _fn

        res = {
            "pending": _make(12.0, 12.0, _draw_pending),
            "landed": _make(12.0, 12.0, _draw_landed),
            "glint": _make(32.0, 32.0, _draw_glint),
            "not-landed": _make(14.0, 14.0, _draw_ring),
            "unknown_1": _make(28.0, 12.0, _draw_unk(1.0)),
            "unknown_-1": _make(28.0, 12.0, _draw_unk(-1.0)),
        }
        self._mark_cache[key] = res
        return res

    def _get_row_textures(self, cx: float, canvas_w: float, mon_w: float, scale: float, palette, is_nova: bool) -> list[dict]:
        """Bake each row's plain-text name pill + optional subtitle once per layout/theme/scale change (zero per-frame alloc)."""
        room_l, room_r = self.layout_for_canvas(cx, canvas_w, mon_w)
        key = (self._side_mode, int(round(room_l)), int(round(room_r)), id(palette), bool(is_nova), round(scale, 3),
               id(LETTERING))
        cached = self._tex_cache.get(key)
        if cached is not None:
            return cached
        light = (palette["operator"] != cairo.OPERATOR_ADD) and not is_nova
        fam = "IBM Plex Sans" if is_nova else (CAPTION_FONT.get_family() or "Noto Serif")
        wt_main = Pango.Weight.SEMIBOLD if is_nova else Pango.Weight.BOLD
        desc_main = _font(fam, 21, wt_main)
        desc_more = _font(fam, 21, Pango.Weight.NORMAL)
        desc_where = _font(LABEL_FONT.get_family() or fam, 11, Pango.Weight.SEMIBOLD)
        ink_rgb = _DISPATCH_NOVA_INK if is_nova else _DISPATCH_DEVS_INK
        quiet_rgb = _DISPATCH_NOVA_QUIET if is_nova else (_DISPATCH_LIGHT_QUIET if light else _DISPATCH_DEVS_QUIET)
        shade_rgb = (0.06, 0.03, 0.14) if is_nova else ((0.21, 0.21, 0.21) if light else INK)
        probe = cairo.ImageSurface(cairo.FORMAT_ARGB32, 4, 4)
        layout = PangoCairo.create_layout(cairo.Context(probe))
        out = []
        for row in self.rows:
            room = room_r if row["side"] > 0 else room_l
            geometry = None
            if LETTERING and not is_nova:
                # A pack's lettering: the name's crisp sprite, placed by its ink box (see _name_spot).
                sprite, geometry = self._lettered_name(row, room, scale)
                pad_x, pad_y, tw, th = geometry[0]
                lw, lh = sprite.get_width() / scale, sprite.get_height() / scale
                name_tex, lay = self._surface_to_texture(sprite), layout
            else:
                desc = desc_more if row["more"] else desc_main
                layout.set_font_description(desc)
                ckey = (row["name"], int(round(room)), fam, row["more"])
                if ckey not in self._fit_cache:
                    self._fit_cache[ckey] = _fit_dispatch_name(layout, row["name"], room)
                shown_txt, tw, th = self._fit_cache[ckey]
                pad_x = 10.0 if light else 18.0
                pad_y = 6.0 if light else 9.0
                lw, lh = tw + 2.0 * pad_x, th + 2.0 * pad_y
                img = cairo.ImageSurface(cairo.FORMAT_ARGB32, max(1, math.ceil(lw * scale)), max(1, math.ceil(lh * scale)))
                img.set_device_scale(scale, scale)
                c = cairo.Context(img)
                lay = PangoCairo.create_layout(c)
                lay.set_font_description(desc)
                lay.set_text(shown_txt, -1)
                if light:
                    _rounded_rect(c, pad_x - 7.0, pad_y - 4.0, tw + 14.0, th + 8.0, 8.0)
                    c.set_source_rgba(*shade_rgb, 0.92)
                    c.fill()
                else:
                    for px_b, py_b, a_bg in ((16.0, 7.0, 0.16), (10.0, 4.0, 0.30)):
                        _rounded_rect(c, pad_x - px_b, pad_y - py_b, tw + 2 * px_b, th + 2 * py_b, (th + 2 * py_b) / 2.0)
                        c.set_source_rgba(*shade_rgb, a_bg)
                        c.fill()
                    c.move_to(pad_x, pad_y + 1.0)
                    c.set_source_rgba(*shade_rgb, 0.65)
                    PangoCairo.show_layout(c, lay)
                c.move_to(pad_x, pad_y)
                c.set_source_rgba(*(quiet_rgb if row["more"] else ink_rgb), 1.0)
                PangoCairo.show_layout(c, lay)
                name_tex = self._surface_to_texture(img)
            sub_entry = None
            if row["where"]:
                lay.set_font_description(desc_where)
                lay.set_text(row["where"], -1)
                ww, wh = lay.get_pixel_size()
                spx, spy = 8.0, 4.0
                slw, slh = ww + 2.0 * spx, wh + 2.0 * spy
                simg = cairo.ImageSurface(cairo.FORMAT_ARGB32, max(1, math.ceil(slw * scale)), max(1, math.ceil(slh * scale)))
                simg.set_device_scale(scale, scale)
                sc = cairo.Context(simg)
                slay = PangoCairo.create_layout(sc)
                slay.set_font_description(desc_where)
                slay.set_text(row["where"], -1)
                if light:
                    _rounded_rect(sc, spx - 6.0, spy - 1.0, ww + 12.0, wh + 4.0, 5.0)
                    sc.set_source_rgba(*shade_rgb, 0.85)
                    sc.fill()
                sc.move_to(spx, spy)
                sc.set_source_rgba(*quiet_rgb, 0.88)
                PangoCairo.show_layout(sc, slay)
                sub_entry = (self._surface_to_texture(simg), slw, slh, spx, spy)
            out.append({
                "tex": name_tex, "lw": lw, "lh": lh, "tw": tw, "th": th,
                "pad_x": pad_x, "pad_y": pad_y, "sub": sub_entry, "geometry": geometry,
            })
        self._tex_cache[key] = out
        return out

    def append_gl_overlay(self, snap, cx: float, cy: float, canvas_w: float, now: float, mon_w: float,
                          scale: float, palette, is_nova: bool = False):
        """Composite cached row name and mark textures via GSK transform + opacity (zero per-frame texture allocs)."""
        if not self.rows:
            return
        t = max(0.0, now - self.t0)
        out = 0.0 if self.hold == 0.0 else _dispatch_ease((t - self.end_at) / DISPATCH_OUT)
        if out >= 0.999:
            return
        row_texs = self._get_row_textures(cx, canvas_w, mon_w, scale, palette, is_nova)
        marks = self._get_mark_textures(scale, palette, is_nova)

        def _blit(tex, x, y, w, h, alpha):
            if alpha <= 0.004:
                return
            snap.push_opacity(min(1.0, alpha))
            snap.append_texture(tex, Graphene.Rect().init(x, y, w, h))
            snap.pop()

        for row, rtex in zip(self.rows, row_texs):
            head, arrive, since = self._row_timing(row, t)
            show = arrive * (1.0 - out)
            if show <= 0.005:
                continue
            lost = row["outcome"] == "not-landed"
            dim = 0.55 if lost else (0.80 if row["outcome"] == "unknown" else 1.0)
            fade = (dim + (1.0 - dim) * (1.0 - _dispatch_ease(since / 0.40))) if since >= 0.0 else 1.0
            name_alpha = show * fade
            side = row["side"]
            ex = cx + row["ex"]
            ry = cy + row["y_off"]
            # A row whose strand had not landed when the teardown began shows no mark or subtitle.
            landed_ok = self.hold == 0.0 or t <= self.end_at or self.end_at >= row["begin"] + DISPATCH_TRAVEL
            # 1) Outcome mark (rows still pending at 8 s close quietly with no mark)
            if landed_ok and head >= 1.0 and not row["more"] and not (row["outcome"] is None and out > 0.001):
                m_show = show * _smooth((t - row["begin"] - DISPATCH_TRAVEL) / 0.12)  # It fades in as the strand lands.
                if row["outcome"] is None:
                    br = (0.45 + 0.35 * (0.5 + 0.5 * math.sin(t * 4.0))) if is_nova else (0.45 + 0.35 * math.sin(t * 8.0))
                    mtex, mw, mh = marks["pending"]
                    _blit(mtex, ex - mw / 2.0, ry - mh / 2.0, mw, mh, m_show * br)
                elif row["outcome"] == "landed":
                    mtex, mw, mh = marks["landed"]
                    _blit(mtex, ex - mw / 2.0, ry - mh / 2.0, mw, mh, m_show)
                    g = 1.0 - min(1.0, max(0.0, since) / 0.50) if is_nova else _glint(since)
                    if g > 0.01 and since > 0.0:
                        gtex, gw, gh = marks["glint"]
                        sc_g = (0.6 + 0.4 * g) if is_nova else 1.0
                        g *= _smooth(since / 0.06) if is_nova else 1.0
                        _blit(gtex, ex - gw * sc_g / 2.0, ry - gh * sc_g / 2.0, gw * sc_g, gh * sc_g, m_show * g)
                elif lost:
                    mtex, mw, mh = marks["not-landed"]
                    _blit(mtex, ex - mw / 2.0, ry - mh / 2.0, mw, mh, m_show)
                else:
                    mtex, mw, mh = marks["unknown_1" if side > 0 else "unknown_-1"]
                    _blit(mtex, ex - mw / 2.0, ry - mh / 2.0, mw, mh, m_show)
            # 2) Cached name pill sprite positioned with slide_x and opacity. A pack's lettering does not slide: its
            # letters fade in under a mask that follows the reveal's grains (see _reveal_stops).
            geometry = rtex["geometry"]
            slide_x = 0.0 if geometry else side * (-14.0 * (1.0 - arrive) + 10.0 * out)
            tx = (ex + DISPATCH_GAP + slide_x) if side > 0 else (ex - DISPATCH_GAP - rtex["tw"] + slide_x)
            ty = ry - rtex["th"] / 2.0
            x0, y0 = tx - rtex["pad_x"], ty - rtex["pad_y"]
            t_r = self._reveal_at(row, t)  # The name's reveal starts as its strand lands, and runs back as it goes.
            if geometry and LETTERING["reveal"] == "spread" and 0.0 <= t_r < REVEAL_SECONDS:
                ix, _, iw, _ = geometry[0]
                stops = []
                for p, a in _reveal_stops(t_r, "left" if side > 0 else "right"):
                    stop = Gsk.ColorStop()
                    stop.offset, stop.color = p, Gdk.RGBA(red=1.0, green=1.0, blue=1.0, alpha=a)
                    stops.append(stop)
                snap.push_mask(Gsk.MaskMode.ALPHA)
                snap.append_linear_gradient(Graphene.Rect().init(x0, y0, rtex["lw"], rtex["lh"]),
                                            Graphene.Point().init(x0 + ix, y0), Graphene.Point().init(x0 + ix + iw, y0),
                                            stops)
                snap.pop()
                _blit(rtex["tex"], x0, y0, rtex["lw"], rtex["lh"], fade)
                snap.pop()
            elif geometry:
                _blit(rtex["tex"], x0, y0, rtex["lw"], rtex["lh"], (1.0 - out) * fade if t_r >= 0.0 else 0.0)
            else:
                _blit(rtex["tex"], x0, y0, rtex["lw"], rtex["lh"], name_alpha)
            # 3) Cached single-send subtitle sprite
            if rtex["sub"] is not None and landed_ok:
                w_alpha = _smooth((t - row["begin"] - DISPATCH_TRAVEL - 0.18) / 0.28) * (1.0 - out)  # After the name.
                if w_alpha > 0.005:
                    stex, slw, slh, spx, spy = rtex["sub"]
                    _blit(stex, tx - spx, ry + rtex["th"] / 2.0 + 2.0 - spy, slw, slh, w_alpha)


class Scene:
    """Everything the overlay paints, driven by protocol messages and a clock so --render draws it offscreen."""

    def __init__(self, now):
        self.state = "hidden"
        self.dark = False
        self.state_at = now
        self.last = now
        self.moved_at = now  # When the grains last moved; see step.
        self.view_still = False  # True while the open viewer's dust holds still for a playing video; see step.
        self.view_video = False  # True while a video plays in the open viewer; see step.
        self.activity = ""
        self.activity_at = 0.0
        self.pending = 0.0
        self.level = 0.0
        self.heard = [0.0] * 32  # Recent microphone levels, newest first, one per step.
        self.level_at = -math.inf
        self.said = 0.0  # The last speech level Rook sent, held until the next one.
        self.env = self.env_was = self.trough = 0.0  # The voice envelope, its last value and its last dip.
        self.armed = True  # True once the envelope has dipped, so the next rise starts a wave.
        self.waves = []  # [start, loudness] for each wave on the speaking globe.
        self.floor = 1.0
        self.peak = 0.0
        self.voice = 0.0
        self.intensity = 0.8
        self.err = 0.0
        self.share = 0.035
        self.cohesion = 1.0
        self.loosen = 0.0
        self.helix_fade = 0.0  # How far the grains have reached the helix, so its strands come and go with them.
        self.ripple_env, self.ripple_at = 0.0, now  # The ripples ring's voice envelope and when it last moved.
        self.ring_turn = 0.0  # How far the ripples ring's rim has turned, in radians.
        # Its ripple slots as [start, loudness, life, turn], how near the next ripple is, and the last one's turn.
        self.ripples = [[-math.inf, 0.0, 1.0, 1.0] for _ in range(devs_pack.RIPPLE_SLOTS)]
        self.ripple_due, self.ripple_spin = 1.0, 1.0
        self.form, self.prev, self.form_at = "cloud", "cloud", -math.inf
        rng = random.Random(3)
        n = GRAINS
        self.x = [rng.uniform(-80, 80) for _ in range(n)]
        self.y = [rng.uniform(-80, 80) for _ in range(n)]
        self.vx, self.vy = [0.0] * n, [0.0] * n
        self.depth = [1.0] * n
        self.z = [0.0] * n  # Normalized depth in [-1, 1] for 3D depth sizing and warmth (0 on flat forms).
        self._target_z = [0.0] * n
        self.omega = [rng.uniform(7.5, 10.0) for _ in range(n)]
        self.delay = [rng.uniform(0, 0.3) for _ in range(n)]
        self.curl = [rng.uniform(-0.7, 0.7) for _ in range(n)]
        # Shimmer frequencies are whole multiples of the loop's, so the resting loop repeats exactly.
        beat = 2 * math.pi / LOOP_PERIOD
        self.freq = [round(rng.uniform(5, 13) / beat) * beat for _ in range(n)]
        self.phase = [rng.uniform(0, 6.3) for _ in range(n)]
        self.loose_until = [-math.inf] * n
        # Most grains are dim; a few are bright sparks.
        self.base = [rng.uniform(0.85, 1.0) if rng.random() < 0.04 else rng.uniform(0.5, 0.8) if rng.random() < 0.1
                     else rng.uniform(0.18, 0.5) for _ in range(n)]
        self.size = [1.0 + 0.8 * b for b in self.base]
        self.tone = [rng.randrange(3) for _ in range(n)]
        self.blue_rank = [rng.random() for _ in range(n)]
        # Loose grains and idle gestures run on fixed-seed schedules, so they are irregular but repeatable.
        self.loose_rng = random.Random(9)
        self.loose_carry = 0.0
        self.idle_rng = random.Random(41)
        self.gesture = (-math.inf, "ripple", 0, 0.0, 0.0)
        self.next_gesture = now + 4.0
        self.vignette = (0.0, 0.0, 50.0, 50.0)
        self.home = False
        self.quiet, self.quiet_mix = False, 0.0  # A quiet turn thinks now, and how far its comet has faded in.
        self.rest_dim, self.glare_mix = 0.0, 0.0  # How far REST_LOOK's rest and its quiet glare have eased in.
        self.extra = 1.0
        self.lift = FALLBACK_LIFT
        self.rest_pad = REST_PAD  # How far below the canvas top the resting loop's centre sits.
        self.all_idx = list(range(n))
        self.rest_idx = list(range(0, n, _rest_every()))
        self.idx = self.all_idx
        self.rest_vignette = None
        # WoW mode, reading the gear card: start time, the card in scene coordinates, and how the game maps onto the
        # scene. game_origin is None outside the game, so the reading keys are ignored there.
        self.reading = None
        self.reading_label = "READING CHANGES"
        self.read_rect = (0.0, 0.0, 1.0, 1.0)
        self.read_mix = 0.0
        self.game_origin = None
        self.game_scale = 1.0
        self.pace = 1.0
        self.delay_scale = 1.0
        self.thinking_since = None  # When plain thinking began, for its turns between the lattice and the rook.
        self.think_plan = None  # A debug replay's thinking: (seconds per form, which other form), until the next state.
        self.replay_pulse_at = -math.inf  # When the debug replay was armed, for the loop's faint pulse.
        self.label_anchor = None
        self.label = ""
        self.label_alpha = 0.0
        self.label_at = -math.inf  # When the label took a new text: its reveal runs from here (see _reveal_rows).
        self.label_shown = ""  # The last text the label showed.
        self.label_sprites = {}
        self.guide = None  # The held guide asked for: {"text", "code", "until", "ends", "heard"}; see handle.
        self.guide_shown = None  # What the guide draws now: (text, code, home), or None.
        self.guide_alpha, self.guide_at, self.guide_y, self.guide_w = 0.0, -math.inf, GUIDE_TOP, 0
        self.captions = []
        self.caption_gone_at = -math.inf
        # Pointer hints, set by the window: over the captions (they open the answer) or over the resting loop.
        self.caption_hint = False
        self.caption_hint_mix = 0.0
        self.caption_box = None  # The caption text block in caption-area coordinates, as last drawn.
        self.rest_hint = False
        self.waiting = ""
        # The media viewer's act, while it shows (see Portal), and how far its look has taken over the swarm's.
        self.view = None
        self.view_mix = 0.0
        self.swarm_vis = 1.0  # Main swarm opacity share: fades out over VIEW_SWARM_FADE on viewer open and back on close.
        self.scene_mix = 0.0  # Fades the vignette out under a render scene, whose node outlines carry the contrast.
        self.dust = None  # The frame's own dust, made at the first show; see _make_dust.
        self.dust_vis = 0.0
        self.dust_active = 0
        self._dust_sorted = None
        self.dust_gl = False  # True while the GL frame draws the still viewer's dust; see _DustGL.
        self.dust_turn = ("hidden", 0.0, (0.0,) * 32)
        # The render tool's scene: the scene on screen and when it came, its form, the form a morph leaves, when it
        # began to end, and the grains past GRAINS a diagram adds (see render_command).
        self.render = None
        self.render_form = self.render_old = None
        self.render_since = self.render_end = None
        self.render_gone = -math.inf
        self.render_reach_px = 0
        self.render_width_px = WIDTH  # The canvas width while a scene shows: a constellation's own, else WIDTH.
        self.size_k = 1.0  # How large grains are drawn against their own size: a scene's GRAIN_SCALE while it shows.
        self.fade_at = None
        self.grown_at = -math.inf
        self.big_idx = None
        # The main window's grains can run their springs on the chip (see _DustGL.draw_main): spring_gl says the chip
        # may run them, springs_on_gpu that it does now, with the targets Python works out each step in spring_steps.
        self.spring_gl = self.springs_on_gpu = False
        self.grains_read = True  # Whether Python reads the chip's grains each frame (see _move and poll_springs).
        self.spring_steps, self.spring_kicks, self.spring_back = [], [], None
        self.spring_idx, self.spring_k = None, 1.0  # The grains the chip held at the last step, and their size.
        self.spring_unloose = False
        # Active presence theme pack ("devs" points engine by default, or any FORMAT.md flipbook pack such as "nova").
        self.pack_name = pack_player.DEFAULT_PACK
        self.pack = pack_player.load_pack(self.pack_name)
        self.pack_kind = self.pack.get("kind", "points")
        _use_pack_text(self.pack)  # Loads its font now, not on the first draw.
        self.think_forms = devs_pack.THINK_OTHERS  # The thinking rotation after the rook: a pack's, then Devs' own.
        self.pack_notes = ()  # The refusals last said for the pack's forms, so a reload says them only when they change.
        self.flipbook = None
        self._cairo_flipbook = None
        # Multi-thread send fan (None when idle -> zero per-frame cost).
        self.dispatch = None
        self.dispatch_hold = DISPATCH_HOLD
        self.monitor_width = 2000.0
        self.fanned_at = None  # The activity_at of the activity whose send fan has shown; after it, no send form.

    def dispatch_active(self, now=None):
        """True while a multi-thread dispatch fan is animating in the active thinking turn, or tearing down after it;
        clears expired or stale fans."""
        t = self.last if now is None else now
        # Off thinking, a fan lives on only through its teardown, scheduled by leave() (cut) or already leaving.
        if self.dispatch is None or self.dark or (
                self.state != "thinking" and self.dispatch.cut is None and not self.dispatch.leaving(t)):
            self.dispatch = None
            return False
        if not self.dispatch.active(t):
            self.dispatch = None
            return False
        return True

    def send_clock(self, now):
        """For the send forms: when the first strand leaves its port, and how far the form has gathered into its
        centre as the fan leaves, 0 to 1."""
        ds = self.dispatch
        if ds is None or not ds.rows:
            return self.form_at + devs_pack.SEND_FIRE, 0.0
        gather = 0.0 if ds.hold == 0.0 else min(1.0, max(0.0, (now - ds.t0 - ds.end_at) / DISPATCH_OUT))
        return ds.t0 + ds.rows[0]["begin"], gather

    def dispatch_leaving(self, now=None):
        if self.dispatch is None:
            return False
        return self.dispatch.leaving(self.last if now is None else now)

    def dispatch_tip_levels(self, now=None):
        if not self.dispatch_active(now):
            return {1: 0.0, -1: 0.0}
        return self.dispatch.tip_levels(self.last if now is None else now)

    def rest_y_offset(self):
        """Vertical offset (logical px) from working centre to the resting loop anchor (0 when lift <= 0)."""
        return (self.rest_pad - self.lift - ORB / 2) if self.lift > 0 else 0.0

    def dispatch_y_offset(self):
        if self.pack_kind == "flipbook" and pack_player.has_dispatch_bake(self.pack):
            return self.rest_y_offset()
        return self.rest_y_offset() if (self.dispatch is not None and self.dispatch.rest_anchor) else 0.0

    def dispatch_canvas_width(self):
        """Logical width needed for the active dispatch fan, clamped to the current monitor width."""
        mon_w = max(float(WIDTH), float(self.monitor_width or 2000.0))
        half = min(DISPATCH_R + DISPATCH_REACH + DISPATCH_GAP + DISPATCH_MAX_W + DISPATCH_EDGE, mon_w / 2.0)
        width = max(WIDTH, min(int(math.floor(mon_w)), int(math.ceil(half * 2.0))))
        return width - (width - WIDTH) % 2  # WIDTH's parity: a centred window keeps the presence on whole pixels.

    def dispatch_nova_standin(self, now=None):
        """True when Nova is active during a dispatch and its forge-baked dispatch flipbook has not landed yet."""
        return (self.pack_kind == "flipbook" and self.dispatch_active(now)
                and not pack_player.has_dispatch_bake(self.pack))

    def dispatch_gl_rows(self, now=None):
        """The dust engine's extra grains: the dispatch fan's strands, and the lettering's reveal grains."""
        t = self.last if now is None else now
        reveal = self.reveal_gl_rows(t)
        if not self.dispatch_active(now):
            return reveal
        y_off = self.dispatch_y_offset()
        rows = self.dispatch.eval_gl_rows(t, y_off)
        rows += self.dispatch.reveal_rows(t, y_off)
        rows += reveal
        return rows

    def draw_dispatch_overlay(self, cr, cx, cy, now):
        if not self.dispatch_active(now):
            return
        self.dispatch.draw_overlay(cr, cx, cy + self.dispatch_y_offset(), now, self.monitor_width, PALETTE,
                                   is_nova=(self.pack_kind == "flipbook"))

    def use_pack_forms(self, forms, problems):
        """A user dust pack's own forms come first in the thinking rotation after the rook, then Devs' own. A refused
        file is named in one sentence and left out. Other packs' forms are dropped, but for the one on screen."""
        if tuple(problems) != self.pack_notes:
            for note in problems:
                print(f"theme pack {self.pack_name}: {note}", file=sys.stderr, flush=True)
            self.pack_notes = tuple(problems)
        keep = {*forms, self.form, self.prev}
        for key in [key for key in _DATA_FORMS if key not in keep]:
            del _DATA_FORMS[key]
            SPIN.pop(key, None)
            _FORMS.pop((PARTICLE_VARIANT, key), None)
        for key, (points, spin) in forms.items():
            _FORMS.pop((PARTICLE_VARIANT, key), None)
            _DATA_FORMS[key], SPIN[key] = points, spin
        self.think_forms = tuple(forms) + devs_pack.THINK_OTHERS

    def fallback_to_devs(self, now=None, reason=""):
        """Safely fall back to Devs on the live GL path after any pack error (logs once, never raises)."""
        if reason:
            print(f"theme pack fallback to {pack_player.DEFAULT_PACK}: {reason}", file=sys.stderr, flush=True)
        self.pack_name = pack_player.DEFAULT_PACK
        try:
            self.pack = pack_player.load_pack(self.pack_name)
        except Exception:
            self.pack = {"name": self.pack_name, "kind": "points", "icons": {}, "states": {}}
        self.pack_kind = "points"
        self.use_pack_forms({}, [])
        _use_pack_text(self.pack)
        self.refont()
        self.flipbook = None
        self._cairo_flipbook = None
        self.springs_on_gpu = False
        self.spring_steps.clear()
        pack_player.ATLAS_LOADER.reset_for_pack(None)

    def set_pack(self, name, now=None, themes_dir=None):
        """Switch the active presence theme pack after full validation. Any failure logs once and falls back to Devs."""
        t = self.last if now is None else now
        tdir = pack_player.THEMES_DIR if themes_dir is None else themes_dir
        if not isinstance(name, str) or not name.strip():
            self.fallback_to_devs(t, f"invalid theme pack name {name!r}")
            return False
        pack_player.ATLAS_LOADER.clear_failed()
        if name == self.pack_name and themes_dir is None and (self.pack_kind != "flipbook" or self.flipbook is not None):
            if self.pack.get("_user") and self.pack_kind == "points":  # A newly forged form joins without a restart.
                try:
                    self.use_pack_forms(*pack_player.pack_forms(pack_player.load_pack(name, reload=True)))
                except Exception as exc:
                    print(f"theme pack {name}: its forms could not be read again ({exc})", file=sys.stderr, flush=True)
            return True
        try:
            pack = pack_player.validate_pack(name, themes_dir=tdir)
            kind = pack.get("kind", "points")
            flipbook = None
            cairo_fb = None
            pack_player.ATLAS_LOADER.reset_for_pack(pack)
            if kind == "flipbook":
                flipbook = pack_player.FlipbookPresence(pack)
                flipbook.set_state(pack_player.map_overlay_state(self), t)
                flipbook.prefetch_warm()
                cairo_fb = pack_player.CairoFlipbookPlayer()
            forms, problems = pack_player.pack_forms(pack)
        except Exception as exc:
            self.fallback_to_devs(t, f"pack '{name}' rejected ({exc})")
            return False
        self.pack_name = name
        self.pack = pack
        self.pack_kind = kind
        self.use_pack_forms(forms, problems)
        _use_pack_text(pack)
        self.refont()
        self.flipbook = flipbook
        self._cairo_flipbook = cairo_fb
        if kind == "flipbook":
            self.spring_steps.clear()
        else:
            self.springs_on_gpu = False
        return True

    def open_view(self, now, box, media):
        """Start the viewer's act, or take over from an open or closing viewer. box and media are scene rects."""
        self.dispatch = None
        if self.view is not None:
            self.view.replace(now, box, media)
            return
        self.end_render(now, at_once=True)
        xs, ys = [self.x[i] for i in self.idx], [self.y[i] for i in self.idx]
        self.view = Portal(now, box, media, (sum(xs) / len(xs), sum(ys) / len(ys)))
        self.reading = None
        if self.dust is None or self.dust["style"] != VIEW_FRAME:
            self._make_dust()

    def _make_dust(self):
        """The frame's single edge of dust: evenly spaced grains around the box with the swarm's tone mix.
        Each point stores (u, pull, off, lag_frac) so Cairo and GL share the exact gather and drift math."""
        rng = random.Random(23)
        golden = (math.sqrt(5) - 1) / 2
        points = []
        count = VIEW_FRAMES[VIEW_FRAME]["dust"]
        for n in range(count):
            u = (n * golden + 0.37) % 1
            pull = rng.uniform(-2.0, 8.0)
            off = rng.gauss(0, 0.7)
            lag_frac = rng.random()
            points.append((u, pull, off, lag_frac, 0.0))
        base = [rng.uniform(0.86, 0.96) if rng.random() < 0.03 else rng.uniform(0.70, 0.84) if rng.random() < 0.09
                else rng.uniform(0.46, 0.68) for _ in range(count)]
        self.dust = {"style": VIEW_FRAME, "count": count, "points": points, "base": base,
                     "size": [1.10 + 0.55 * b for b in base], "tone": [rng.randrange(3) for _ in range(count)],
                     "blue": [1.0] * count,
                     "freq": [rng.uniform(1.5, 4.0) for _ in range(count)],
                     "phase": [rng.uniform(0, 6.3) for _ in range(count)],
                     "x": [0.0] * count, "y": [0.0] * count, "depth": [1.0] * count}

    def dust_count(self, now):
        """How many pool grains sit on the current perimeter so tiny and wide boxes keep one fine dust density."""
        d, v = self.dust, self.view
        if d is None or v is None:
            return 0
        _, _, bw, bh, rr = v.shape(now)
        style = VIEW_FRAMES[VIEW_FRAME]
        band = min(style["band"] * v.margin(now), style.get("band_max", 6.0))
        rr_arc = max(0.0, rr - band) if rr > band else rr
        per = 2 * (bw + bh - 4 * rr) + 2 * math.pi * rr_arc
        return min(d["count"], max(260, round(per * style["density"])))

    def _step_dust(self, now):
        """Place the frame's single-row edge dust for now. Skips Python placement when GL draws the frame."""
        v, d = self.view, self.dust
        vis = 0.0 if (v.closing is not None and now > v.closing + VIEW_DISSOLVE_LAG + VIEW_DISSOLVE) else 1.0
        self.dust_vis = vis
        self.dust_active = self.dust_count(now)
        self.dust_turn = (self.state, self.voice, tuple(self.heard))
        if vis <= 0.002 or self.dust_gl:
            return
        tx, ty, tb = self._portal_places(d["points"], range(self.dust_active), now, d["count"],
                                         (d["freq"], d["phase"]))
        d["x"], d["y"], d["depth"] = tx, ty, tb

    def _dust_buckets(self):
        """The frame's dust sorted for _paint_grains, cached per step."""
        if self._dust_sorted is not None and self._dust_sorted[0] == (self.moved_at, PALETTE is THEMES["light"]):
            return self._dust_sorted[1]
        d = self.dust
        x, y, depth, base, tone, blue = d["x"], d["y"], d["depth"], d["base"], d["tone"], d["blue"]
        k, share = self.intensity * 7 * self.dust_vis, self.share
        buckets, sparks = [[] for _ in range(32)], []
        for i in range(self.dust_active):
            level = int(base[i] * depth[i] * k)
            if level <= 0:
                continue
            buckets[(3 if blue[i] < share else tone[i]) * 8 + min(7, level)].append(i)
            if base[i] > 0.85:
                sparks.append(i)
        self._dust_sorted = ((self.moved_at, PALETTE is THEMES["light"]), (x, y, d["size"], buckets, sparks))
        return self._dust_sorted[1]

    def draw_view_edges(self, regions, now, centre):
        """Draw the viewer's single-row edge dust in the four narrow strips round the box, each grain at most once."""
        cx, cy = centre
        share = self.share
        d = self.dust
        dx, dy, dbase, ddepth, dtone, dblue = d["x"], d["y"], d["base"], d["depth"], d["tone"], d["blue"]
        k = self.intensity * 7 * self.dust_vis
        bounds = [(rx - cx, ry - cy, rx + rw - cx, ry + rh - cy) for _, (rx, ry, rw, rh) in regions]
        parts = [([[] for _ in range(32)], []) for _ in regions]
        (a0, b0, c0, d0), (a1, b1, c1, d1), (a2, b2, c2, d2), (a3, b3, c3, d3) = (bounds + [(0, 0, 0, 0)] * 4)[:4]
        part0, part1, part2, part3 = (parts + [None] * 4)[:4]
        for i in range(self.dust_active):
            base = dbase[i]
            level = int(base * ddepth[i] * k)
            if level <= 0:
                continue
            gx, gy = dx[i], dy[i]
            if a0 <= gx < c0 and b0 <= gy < d0:
                part = part0
            elif a1 <= gx < c1 and b1 <= gy < d1:
                part = part1
            elif a2 <= gx < c2 and b2 <= gy < d2:
                part = part2
            elif a3 <= gx < c3 and b3 <= gy < d3:
                part = part3
            else:
                continue
            key = (3 if dblue[i] < share else dtone[i]) * 8 + (level if level < 7 else 7)
            part[0][key].append(i)
            if base > 0.85:
                part[1].append((key, i))
        for (cr, _), (buckets, sparks) in zip(regions, parts):
            self._paint_grains(cr, cx, cy, dx, dy, d["size"], buckets, [i for _, i in sorted(sparks)], 1.0)

    def close_view(self, now):
        """Close the viewer: fade the media out, ease the box away, and thin the edge dust."""
        if self.view is not None:
            self.view.close(now)

    # ---- the render tool's scenes ----
    def render_command(self, spec, now):
        """Show a diagram, light a step of the diagram on screen, or clear it."""
        if not isinstance(spec, dict):
            return {"ok": False, "error": "A render request needs a diagram, a step, or clear."}
        shown = self.render is not None and self.render_end is None
        if spec.get("clear"):
            self.end_render(now)
            return {"ok": True, "said": "Cleared." if shown else "Nothing was on screen."}
        if "step" in spec:
            step = spec["step"]
            if not shown:
                return {"ok": False, "error": "No scene is on screen. Show one first."}
            steps = self.render["scene"]["steps"]
            answer = _scene_step_answer(steps, step)
            if answer["ok"]:
                self.render_form["con"].light(step, now)
            return answer
        if "diagram" in spec:
            scene, form = self.diagram_form(spec["diagram"])
            if form is None:
                return {"ok": False, "error": "A diagram needs two nodes joined by > or -."}
            return self.render_commit(scene, form, now)
        return {"ok": False, "error": SCENE_GONE}

    def diagram_form(self, doc):
        """A constellation's scene and form from {"graph", "title"} or a mark's inside, its names measured in their
        own lettering. Both are None when the graph has fewer than two nodes. Repairs go to stderr for the builders,
        never back to the model."""
        doc = doc if isinstance(doc, dict) else {"graph": str(doc)}
        title, graph = str(doc.get("title") or "").strip(), str(doc.get("graph") or "")
        probe = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1))

        def measure(text, grow=1.0):
            sprite = self._diagram_sprite(probe, text, 1.0, grow)
            return sprite.get_width() - 28, sprite.get_height() - 28  # Less the sprite's 14 px pad each side.

        title, nodes, con, repairs = constellation.make(f"{title} | {graph}" if title else graph, measure,
                                                        measure_title=lambda text: measure(text, TITLE_GROW))
        if repairs:
            print(f"diagram repairs: {'; '.join(repairs)} in {graph[:200]!r}", file=sys.stderr, flush=True)
        if con is None:
            return None, None
        scene = {"name": title or "diagram", "title": title, "size": "diagram", "parts": [], "nodes": len(nodes),
                 "steps": [{"caption": ""} for _ in nodes]}
        form = {"kind": "constellation", "name": scene["name"], "title": title, "caption": "", "scene": scene,
                "budget": len(con.recs), "recs": con.recs, "size": con.plan["size"], "step": None,
                "parts": [], "labels": [], "notes": []}
        _interleave(form)  # The swarm's own grains spread over every node; the extra ones are born beside them.
        form["con"] = constellation.Constellation(con.plan, nodes, form["recs"])
        return scene, form

    def _diagram_sprite(self, cr, text, scale, grow=1.0):
        """A constellation name in the send names' lettering, at grow times its size, cached per text, size, scale and
        lettering."""
        key = ("diagram", text, scale, grow, id(LETTERING), id(PALETTE))
        if key not in self.label_sprites:
            if LETTERING:
                sprite = _lettering_sprite(cr, text, scale, "name", grow=grow)[0]
            else:
                font, spacing = RENDER_TYPE["icon"]
                sprite = _word_sprite(cr, text, scale, _grown(font, grow), PALETTE["label"], spacing * grow,
                                      PALETTE["label_halos"],
                                      PALETTE["label_halo"], PALETTE["label_outline"])[0]
            self.label_sprites[key] = sprite
        return self.label_sprites[key]

    def diagram_names(self, now):
        """What a constellation's names show now: (text, x, y, alpha, grow) for each name and the title, x and y the
        top left of its ink box about the drawing's centre, grow its size against a name's. Empty when no constellation
        shows."""
        form = self.render_form
        if self.render is None or form is None or form.get("kind") != "constellation" or self.form != "render":
            return ()
        con, t = form["con"], now - self.render_since - form["start"]
        fade = 1.0 if self.render_end is None else max(0.0, 1 - (now - self.render_end) / RENDER_FADE)
        out = [(text, box[0], box[1], con.name_alpha(k, t, now) * fade, 1.0)
               for k, (text, box) in enumerate(zip(con.plan["labels"], con.plan["names"]))]
        if con.plan["title_box"]:
            box = con.plan["title_box"]
            out.append((con.plan["title"].upper(), box[0], box[1], con.title_alpha(t) * fade, TITLE_GROW))
        return [row for row in out if row[3] > 0.004]

    def filament_frame(self, now):
        """A constellation's filament layer now: (Constellation, seconds since its reveal, how far below Rook's centre
        the drawing sits), or None when no constellation shows."""
        form = self.render_form
        if self.render is None or form is None or form.get("kind") != "constellation" or self.form != "render":
            return None
        return form["con"], now - self.render_since - form["start"], self.render["dy"]

    def render_commit(self, scene, form, now):
        """Attach a prepared scene form and start its entrance on the active scene."""
        self.dispatch = None
        prev_state = (self.render, self.render_form, self.render_old, self.render_since, self.render_end)
        shown = self.render is not None and self.render_end is None
        self.render = {"scene": scene, "at": now}
        if not shown:
            self.render_since = now
        self.render_end = None
        try:
            self._render_set(form, now)
        except Exception:
            self.render, self.render_form, self.render_old, self.render_since, self.render_end = prev_state
            raise
        return self.render_said(scene, form)

    @staticmethod
    def render_said(scene, form):
        """The answer for a diagram that shows, or that is staged to show at the reveal."""
        return {"ok": True, "said": f"Showing {scene['nodes']} nodes."}

    def drop_render(self, now):
        """Drop a failed scene at once and return the swarm to its normal size."""
        self.render = self.render_form = self.render_old = self.render_end = None
        self.render_gone = now
        self.fade_at = None
        self.big_idx = None
        for values in (self.x, self.y, self.vx, self.vy, self.depth, self.omega, self.delay, self.curl,
                       self.freq, self.phase, self.loose_until, self.base, self.size, self.tone, self.blue_rank):
            if len(values) > GRAINS:
                del values[GRAINS:]
        if self.size_k != 1.0:
            self.size_k = 1.0
            self.size = [1.0 + 0.8 * b for b in self.base]
        self.idx = self.all_idx
        self.spring_steps.clear()
        if self.form == "render":
            self.form = FORM_FOR_STATE.get(self.state, "loop")
            self.form_at = now
        if self.prev in ("render", "render_old"):
            self.prev = self.form

    def end_render(self, now, at_once=False):
        """End the scene: a diagram's extra grains fade first, then the swarm moves on. The viewer ends it at once."""
        if self.render is not None:
            if at_once:
                self.render_end = now - RENDER_FADE - 0.01
            elif self.render_end is None:
                self.render_end = now
            self.render_form["con"].end(self.render_end)  # The lines hand the drawing back to the grains.

    def _render_set(self, form, now):
        """Make form the scene's form. A form that follows a form on screen morphs, with a small arrival burst."""
        old = self.render_form
        if self.form == "render":
            self.render_old, self.prev, self.form_at = old, "render_old", now
            self.loosen, self.delay_scale = RENDER_LOOSEN, 1.0
        form["start"] = now - self.render_since
        self.render_form = form
        h = form["size"][1] - 2 * constellation.PAD
        # Centred on Rook, and moved down only as far as its top needs to stay on the canvas.
        self.render["dy"] = dy = max(0.0, h / 2 - (self.lift + ORB / 2 - RENDER_TOP))
        self.render["bottom"] = h / 2 + dy
        self.render["lit"] = None

    def render_reach(self, now):
        """How far below the working centre the canvas must reach while a scene shows, or None."""
        if self.render is not None:
            self.render_reach_px = int(self.render["bottom"] + constellation.PAD)  # Its own bounds and a margin.
            self.render_width_px = min(WIDTH, self.render_form["size"][0])
        elif now - self.render_gone > RENDER_HOLD:
            return None
        return self.render_reach_px

    def _size_swarm(self, form, now):
        """Draw a scene's grains at its GRAIN_SCALE; grow the swarm to a scene's grains, fade the extra grains once they
        are not needed, then drop them."""
        k = scenes.GRAIN_SCALE.get(self.render_form["kind"], 1.0) if form == "render" else 1.0
        if k != self.size_k:
            # Rebuilt from base by the same sum as at the start, so the swarm's own sizes come back exactly.
            self.size_k, self.size = k, [(1.0 + 0.8 * b) * k for b in self.base]
        need = self.render_form["budget"] if form == "render" and self.render_end is None else GRAINS
        if len(self.x) > need:
            self.fade_at = now if self.fade_at is None else self.fade_at
            if form != "render" or now - self.fade_at > RENDER_FADE:
                for values in (self.x, self.y, self.vx, self.vy, self.depth, self.z, self.omega, self.delay, self.curl,
                               self.freq, self.phase, self.loose_until, self.base, self.size, self.tone,
                               self.blue_rank):
                    del values[max(GRAINS, need):]
                self.big_idx, self.fade_at = list(range(len(self.x))), None
            return
        self.fade_at = None
        if len(self.x) == need or (now < self.form_at + 0.31 * self.delay_scale
                                   and self.prev not in ("render", "render_old")):
            return  # The form the swarm leaves holds only the swarm's own grains; new ones wait until it lets go.
        if self.springs_on_gpu and self.spring_back is not None:
            self.spring_back()  # The parents' places from the chip, exact: in a settled scene Python reads none.
        # New grains are born beside their parents, with the swarm's own mix of grains, from a fixed seed.
        rng, beat = random.Random(len(self.x) + need), 2 * math.pi / LOOP_PERIOD
        parents = self.render_form["parents"]
        for i in range(len(self.x), need):
            p = parents[i]
            self.x.append(self.x[p] + rng.uniform(-2, 2))
            self.y.append(self.y[p] + rng.uniform(-2, 2))
            self.vx.append(self.vx[p])
            self.vy.append(self.vy[p])
            self.depth.append(0.0)
            self.z.append(0.0)
            self.omega.append(rng.uniform(7.5, 10.0))
            self.delay.append(rng.uniform(0, 0.3))
            self.curl.append(rng.uniform(-0.7, 0.7))
            self.freq.append(round(rng.uniform(5, 13) / beat) * beat)
            self.phase.append(rng.uniform(0, 6.3))
            self.loose_until.append(-math.inf)
            self.base.append(rng.uniform(0.85, 1.0) if rng.random() < 0.04 else rng.uniform(0.5, 0.8)
                             if rng.random() < 0.1 else rng.uniform(0.18, 0.5))
            self.size.append((1.0 + 0.8 * self.base[-1]) * self.size_k)
            self.tone.append(rng.randrange(3))
            self.blue_rank.append(rng.random())
        self.big_idx, self.grown_at = list(range(need)), now

    def _render_targets(self, form, now):
        """A constellation's form now: its targets come from its own light state, with depth, as a presence form's do.
        A diagram's extra grains come in, and fade out, over RENDER_FADE."""
        tx, ty, tb, self._target_z = form["con"].targets(now - self.render_since - form["start"], now,
                                                          (self.render or {}).get("dy") or 0.0)
        if len(self.x) > GRAINS and (level := self.render_level(now)) < 1.0:
            tb = tb[:GRAINS] + [b * level for b in tb[GRAINS:]]
        return tx, ty, tb

    def render_level(self, now):
        """How far a diagram's extra grains have come in, or faded out: 0 to 1 (see RENDER_FADE)."""
        level = min(1.0, (now - self.grown_at) / RENDER_FADE)
        if self.fade_at is not None:
            level *= max(0.0, 1 - (now - self.fade_at) / RENDER_FADE)
        return level

    def _render_labels_moment(self, now):
        """What of now _render_labels draws: nothing while its alpha is too low to draw, else that alpha and where the
        moved parts fly. Equal moments draw the same pixels."""
        return repr([(text, round(alpha, 3)) for text, _, _, alpha, _ in self.diagram_names(now)])

    def _render_labels(self, cr, cx, cy):
        """A constellation's names and title, each a cached sprite at its own alpha."""
        r, now = self.render, self.last
        scale = cr.get_target().get_device_scale()[0]
        for text, x, y, alpha, grow in self.diagram_names(now):
            sprite = self._diagram_sprite(cr, text, scale, grow)
            cr.set_source_surface(sprite, *_device_round(cr, cx + x - 14, cy + r["dy"] + y - 14))
            cr.paint_with_alpha(alpha)

    def handle(self, msg, now):
        pack = msg.get("pack")
        if isinstance(pack, str):
            self.set_pack(pack, now)
        elif isinstance(msg.get("theme"), str) and msg["theme"] not in THEMES:
            self.set_pack(msg["theme"], now)
        level = msg.get("level")
        if isinstance(level, (int, float)):
            self.pending = max(self.pending, float(level))
            self.said = max(0.0, float(level))
            self.level_at = now
        if isinstance(msg.get("dark"), bool):
            self.dark = msg["dark"]
            if self.dark:
                self.dispatch = None
        if "guide" in msg:
            guide, self.guide = msg["guide"], None
            if isinstance(guide, dict):
                text, code, seconds = guide.get("text"), guide.get("code"), guide.get("seconds")
                text, code = (" ".join(v.split())[:cap].strip() if isinstance(v, str) else ""
                              for v, cap in ((text, 75), (code, 12)))
                timed = isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and math.isfinite(seconds)
                if text or code:
                    self.guide = {"text": text, "code": code, "until": guide.get("until"), "heard": False,
                                  "ends": now + seconds if timed else math.inf}
        state = msg.get("state")
        if state in STATES:
            if state in FAN_TEARDOWN_STATES and self.dispatch_active(now):
                # The turn moves on: the fan's teardown plays first, and the next state's form follows from it.
                self.dispatch.leave(now)
            elif state != "thinking":
                # The owner speaking, a card, or Rook hidden ends the fan at once.
                self.dispatch = None
            elif (state != self.state or ("activity" not in msg and "send" not in msg)) and self.dispatch_active(now):
                # Thinking again mid-turn (as when a spoken line ends) or a fresh turn: the fan's teardown plays.
                self.dispatch.leave(now)
        if state in STATES and state != self.state:
            guide = self.guide
            if guide and guide["heard"]:
                self.guide = None  # The first listen has ended.
            elif guide and guide["until"] == "listening" and state == "listening":
                guide["text"], guide["code"], guide["heard"] = GUIDE_LISTENING, "", True
            self.state, self.state_at = state, now
            self.pending = max(0.0, float(level)) if isinstance(level, (int, float)) else 0.0
            self.said = self.pending
            if state not in READING_STATES:
                self.reading = None
            if state != "thinking":
                self.activity = ""
            if state == "listening":
                self.level = 0.0
                self.heard[:] = [0.0] * len(self.heard)
                self.clear_captions(now)
                self.end_render(now)
                if LISTEN_CYCLE:
                    LISTEN_CYCLE.append(LISTEN_CYCLE.pop(0))
                    FORM_FOR_STATE["listening"] = LISTEN_STYLES[LISTEN_CYCLE[0]]
            elif state in ("result", "error", "hidden"):
                for c in self.captions:
                    c.ended = True
        if state in STATES:
            self.quiet = state == "thinking" and msg.get("quiet") is True
            plan = msg.get("think") if state == "thinking" else None
            turn, other = (plan.get("turn"), plan.get("other")) if isinstance(plan, dict) else (None, None)
            ok = (isinstance(turn, (int, float)) and not isinstance(turn, bool) and 0.3 <= turn <= 10
                  and isinstance(other, int) and not isinstance(other, bool) and other >= 0)
            self.think_plan = (float(turn), other) if ok else None
        if "send" in msg:
            raw_send = msg.get("send")
            items = [raw_send] if isinstance(raw_send, dict) else (raw_send if isinstance(raw_send, list) else [])
            if self.state != "thinking" and not self.dark and self.dispatch_active(now):
                pass  # The fan's teardown plays out; nothing joins it.
            elif not items or self.state != "thinking" or self.dark or self.quiet:
                # While speaking (or any state other than active thinking), never show a send fan over the active form.
                self.dispatch = None
            elif self.dispatch is not None and self.dispatch.active(now) and self.dispatch.update_outcomes(items, now):
                pass
            else:
                outcome_only = all(
                    isinstance(e, dict) and not _clean_dispatch_text(e.get("name") if "name" in e else e.get("thread"))
                    for e in items
                )
                if not outcome_only:
                    # The strands wait for the send form to assemble; Nova's baked fan keeps its own timing.
                    lead = DISPATCH_FORM
                    if not (self.pack_kind == "flipbook" and pack_player.has_dispatch_bake(self.pack)):
                        start = self.form_at if self.form in devs_pack.SEND_FORMS else now
                        lead = max(DISPATCH_FORM, start + devs_pack.SEND_FIRE - now)
                    ds = DispatchState(items, now, hold=self.dispatch_hold, rest_anchor=bool(self.home), lead=lead)
                    self.dispatch = ds if ds.rows else None
        if isinstance(msg.get("activity"), str) and msg["activity"] != self.activity:
            self.activity, self.activity_at = msg["activity"], now
        waiting = msg.get("waiting")
        if isinstance(waiting, str):
            self.waiting = waiting.strip()
        card = msg.get("reading")
        if (isinstance(card, list) and len(card) == 4 and all(isinstance(v, (int, float)) for v in card)
                and self.game_origin is not None and self.state in READING_STATES and self.view is None):
            ox, oy = self.game_origin
            k = self.game_scale
            self.read_rect = (ox + card[0] / k, oy + card[1] / k, card[2] / k, card[3] / k)
            self.reading = now
            label = msg.get("reading_label")
            self.reading_label = label if isinstance(label, str) and label else "READING CHANGES"
            if self.form == "frame":
                self.prev, self.form_at, self.loosen = "frame", now, 1.0
        caption = msg.get("caption")
        if isinstance(caption, str):
            if caption.strip():
                showing = [c for c in self.captions if not c.gone(now)]
                for c in showing:
                    c.fade(now, BLINK / NEARLY_GONE)
                self.captions.append(Caption(caption, msg.get("seconds")))
                if showing:  # The new speech's first word waits a blink, until the old caption has nearly gone.
                    self.captions[-1].clock = -BLINK
            else:
                for c in self.captions:
                    c.ended = True
        left, seconds = msg.get("seconds_left"), msg.get("seconds")
        if (isinstance(left, (int, float)) and isinstance(seconds, (int, float)) and caption is None
                and self.captions and not self.captions[-1].ended):
            self.captions[-1].retime(seconds, left)

    def clear_captions(self, now):
        for c in self.captions:
            c.fade(now, QUICK_OUT)

    def retheme(self):
        """Drop every cached image that baked in the old palette; each is rebuilt on its next draw."""
        self.label_sprites = {}
        self.rest_vignette = None
        for c in self.captions:
            for s in c.sentences:
                s.scale = None

    def refont(self):
        """After _use_font: drop the label images and lay the captions out again in the new font."""
        self.retheme()
        for c in self.captions:
            c.relayout()

    def resting(self, now):
        return bool(self.captions) or now - max(self.state_at, self.caption_gone_at) < REST_SECONDS

    def is_home(self, now, held=False):
        """True when no turn is showing: the swarm rests in the loop at the top of the monitor."""
        s = self.state
        if s in ("ready", "hidden") or (s == "thinking" and self.quiet):
            return True
        if s == "result":
            return not (held or self.resting(now))
        if s == "error":
            return not (held or now - self.state_at < ERROR_SECONDS)
        return False

    def replay_pulse(self, tb, lit, now, points, flow):
        """The debug replay's arm mark on the resting loop: one band of the loop's own grains comes back up to its full,
        undimmed light (lit) and runs once round the figure eight from the crossing, as the quiet glare does, then is
        gone. No label or card, so it is safe on camera."""
        since = now - self.replay_pulse_at
        if 0 <= since < REPLAY_PULSE_SECONDS:
            head = 2 * math.pi * _ease_out(since / REPLAY_PULSE_SECONDS)
            fade = math.sin(math.pi * since / REPLAY_PULSE_SECONDS)  # In and out, so the band never pops.
            for i in self.idx:
                d = (points[i][0] + flow - head + math.pi) % (2 * math.pi) - math.pi  # From the crossing, round the eight.
                if abs(d) < REPLAY_PULSE_WIDTH:
                    w = fade * (0.5 + 0.5 * math.cos(math.pi * d / REPLAY_PULSE_WIDTH))
                    tb[i] += (lit[i] * (1 + REPLAY_PULSE_GAIN) - tb[i]) * w

    def scatter(self):
        """Appearing: the grains start as loose dust around the canvas and drift in."""
        rng = random.Random(17)
        for i in range(GRAINS):
            a, r = rng.uniform(0, 2 * math.pi), rng.uniform(50, 86)
            self.x[i], self.y[i] = r * math.cos(a), r * math.sin(a)
            self.vx[i], self.vy[i] = rng.uniform(-20, 20), rng.uniform(-20, 20)
        self.loosen = 1.0

    def _normalize(self, rms):
        self.floor = min(self.floor, rms)
        self.peak = max(rms, self.floor + (self.peak - self.floor) * PEAK_DECAY)
        if rms < LISTEN_SILENCE_RMS:
            return 0.0  # Room noise, not the owner. The auto-range would blow it up and make the silent ring dance.
        n = (rms - self.floor) / max(self.peak - self.floor, MIN_SPAN)
        return min(1.0, max(0.0, n)) ** 0.55

    def label_text(self, now):
        if self.form == "render" or self.dispatch_active(now):
            return ""  # A scene or dispatch fan draws its own labels beside it, not on the icon.
        if self.home and self.rest_hint:
            return "LAST ANSWER"
        if self.home and self.waiting:
            return self.waiting
        if self.quiet:
            return ""
        if self.reading is not None and now < self.reading + READ_ZOOM + READ_HOLD:
            return self.reading_label
        if self.state == "thinking" and self.activity and not (
                ACTIVITY_FORMS.get(self.activity) in devs_pack.SEND_FORMS and self.fanned_at == self.activity_at):
            return ACTIVITY_LABELS.get(self.shown_activity(now), "THINKING")  # After its fan, a send thinks on.
        return LABELS.get(self.state, "")

    def shown_activity(self, now):
        turns = ACTIVITY_TURNS.get(self.activity)
        return turns[int((now - self.activity_at) / TURN_SECONDS) % len(turns)] if turns else self.activity

    def step(self, now, held=False):
        dt = min(0.1, max(0.0, now - self.last))
        self.last = now
        self.home = self.is_home(now, held)
        # Speaking levels are 0..1; only listening feeds the mic auto-range.
        if self.pending > 0 and self.state == "speaking":
            target = min(1.0, self.pending) ** 0.55
        elif self.pending > 0 and self.state == "listening":
            target = self._normalize(self.pending)
        else:
            target = 0.0
        self.pending = 0.0
        self.level = max(target, self.level * math.exp(-dt / 0.1))
        self.heard.insert(0, self.level)
        self.heard.pop()
        s, t = self.state, now
        # Rook's voice as a smooth envelope, so each syllable is one swell and not a run of 50 ms steps.
        said = min(1.0, self.said) ** 0.55 if s == "speaking" and now - self.level_at < 0.3 else 0.0
        self.env += (said - self.env) * _glide(dt, SPEAK_ATTACK if said > self.env else SPEAK_RELEASE)
        if self.env < self.env_was and not self.armed:
            self.armed, self.trough = True, self.env
        self.trough = min(self.trough, self.env)
        if self.armed and self.env - self.trough > WAVE_RISE and now - max(
                (w[0] for w in self.waves), default=-math.inf) >= WAVE_GAP:
            self.waves = (self.waves + [[now, self.env]])[-WAVE_MAX:]
            self.armed = False
        self.env_was = self.env
        # A new wave takes its syllable's peak loudness, which the envelope reaches in a moment.
        self.waves = [w for w in self.waves if now - w[0] < WAVE_SECONDS]
        for w in self.waves:
            if now - w[0] < 0.2:
                w[1] = max(w[1], self.env)
        if s == "speaking":
            voice = self.level if now - self.level_at < 0.3 else (
                0.5 + 0.28 * math.sin(t * 5.3) + 0.22 * math.sin(t * 2.1 + 1.3))
        else:
            voice = 0.0
        self.voice += (voice - self.voice) * _glide(dt, 0.1)
        goal = (1.05 if self.rest_hint else 0.85) if self.home else {"listening": 0.8 + 0.4 * self.level, "speaking": 0.9 + 0.3 * self.voice,
                                       "error": 0.45, "result": 0.75 + 0.06 * math.sin(t * 2 * math.pi / 5.5)}.get(s, 0.9)
        self.intensity += (goal - self.intensity) * _glide(dt, 0.25)
        if self.quiet or self.quiet_mix:
            on = self.quiet and self.form == "loop" and not self.dark
            self.quiet_mix = min(1.0, self.quiet_mix + dt / QUIET_IN) if on else max(0.0, self.quiet_mix - dt / QUIET_OUT)
        look = REST_LOOKS[REST_LOOK]
        if look:
            home = self.home and self.form == "loop"
            settled = home and now - self.form_at > REST_SETTLE
            self.rest_dim = min(1.0, self.rest_dim + dt / REST_IN) if settled else max(0.0, self.rest_dim - dt / REST_OUT)
            on = home and self.quiet and not self.dark
            self.glare_mix = (min(1.0, self.glare_mix + dt / look["rise"]) if on else
                              max(0.0, self.glare_mix - dt / REST_FALL) if home else 0.0)
        self.err += ((1.0 if s == "error" and not self.home else 0.0) - self.err) * _glide(dt, 0.8)
        share = 0.035 if self.quiet else 0.09 if s == "thinking" and self.activity else 0.06 if s == "thinking" else 0.035
        self.share += (share - self.share) * _glide(dt, 0.8)
        self.cohesion += ((0.4 if s == "error" else 1.0) - self.cohesion) * _glide(dt, 0.3)
        if self.reading is not None and now > self.reading + READ_ZOOM + READ_HOLD + READ_RETURN + 0.3:
            self.reading = None
        reading = self.reading is not None and now < self.reading + READ_ZOOM + READ_HOLD
        self.read_mix += ((1.0 if self.reading is not None else 0.0) - self.read_mix) * _glide(dt, 0.15)
        if self.reading is not None:
            self.share += (0.06 - self.share) * _glide(dt, 0.3)
        if self.view is not None and self.view.done(now):
            self.view = None
        if self.view is not None or self.view_mix:
            self.view_mix += ((1.0 if self.view is not None else 0.0) - self.view_mix) * _glide(dt, 0.15)
            if self.view is None and self.view_mix < 0.002:
                self.view_mix = 0.0
        if self.form == "render" or self.scene_mix:
            self.scene_mix += ((1.0 if self.form == "render" else 0.0) - self.scene_mix) * _glide(dt, 0.1)
            if self.form != "render" and self.scene_mix < 0.002:
                self.scene_mix = 0.0
        # While the viewer is open and still, its dust and the swarm in it move VIEW_TURN_FPS times a second at most;
        # a turn's level, labels and captions still step every time.
        # While a video plays they hold still when Cairo draws the dust (view_still), in a turn too, so the video's
        # frames keep the thread. While the GL frame draws it, they move VIEW_GL_FPS times a second throughout.
        fps = VIEW_GL_FPS if self.dust_gl else VIEW_TURN_FPS
        moving = (self.view is None or not self.view.settled(now)
                  or (not self.view_still and now - self.moved_at > 1 / fps - 0.005))
        nova_standin = self.dispatch_nova_standin(now)
        if (self.pack_kind == "flipbook" and self.flipbook is not None and not nova_standin
                and self.view is None and self.render is None and self.reading is None):
            # Flipbook pack (e.g. Nova) needs no particle targets, spring integration, or compute queues.
            self.spring_steps.clear()
            self.springs_on_gpu = False
            self.moved_at = now
            # The viewer faded the presence out; it fades back here, since this branch skips the one below.
            self.swarm_vis = min(1.0, self.swarm_vis + dt / VIEW_SWARM_FADE)
        elif self.view is not None:
            self.swarm_vis = max(0.0, self.swarm_vis - dt / VIEW_SWARM_FADE)
            if self.springs_on_gpu and self.spring_back is not None:
                self.spring_back()
            self.springs_on_gpu = False
            if moving:
                self._step_dust(now)
            if self.swarm_vis > 0.002:
                # Keep the main swarm alive during its 0.2 s fade-out so it never freezes while visible.
                self.loosen *= math.exp(-dt / 0.26)
                resting = self.home and self.form == "loop"
                self.extra += ((0.0 if resting else 1.0) - self.extra) * _glide(dt, 0.35 if resting else 0.15)
                self.idx = self.rest_idx if resting and self.extra < 0.01 else self.all_idx
                if len(self.x) > GRAINS:
                    self.idx = self.big_idx
                self._move(now, min(0.1, max(0.0, dt)))
                self.moved_at = now
            elif moving:
                self.moved_at = now
        else:
            if self.render is not None:
                if self.render_end is None and self.state not in READING_STATES + ("permission", "speaking") and (
                        now - max(self.render["at"], self.state_at) > scenes.SCENE_SECONDS):
                    self.end_render(now)
                if self.render_end is not None and (len(self.x) <= GRAINS or now - self.render_end > RENDER_FADE):
                    self.render, self.render_gone = None, now
            if self.dispatch_active(now):
                self.fanned_at = self.activity_at  # Under a scene or the card too: after it, the label thinks on.
            if self.render is not None and not reading:
                # A scene holds over every form of the turn but the viewer and the card.
                form = "render"
            elif self.dispatch_active(now) and not reading:
                form = devs_pack.SEND_FORMS[0]
            elif self.home:
                form = "loop"
            elif reading:
                form = "frame"
            elif (s == "thinking" and self.shown_activity(now) in ACTIVITY_FORMS
                  and ACTIVITY_FORMS[self.shown_activity(now)] not in devs_pack.SEND_FORMS):
                # A send form shows only with its fan (above), never a lone device before or after it.
                form = ACTIVITY_FORMS[self.shown_activity(now)]
                if form.__class__ is tuple:
                    if self.form not in form:
                        FORM_ROTATIONS[form] = FORM_ROTATIONS.get(form, -1) + 1
                    form = self.form if self.form in form else form[FORM_ROTATIONS[form] % len(form)]
            elif s == "thinking":
                # Plain thinking alternates the rook with the theme pack's thinking icons, THINK_TURN seconds each.
                if self.thinking_since is None:
                    self.thinking_since = now
                each, first = self.think_plan or (THINK_TURN, 0)
                turn = int((now - self.thinking_since) / each)
                if PARTICLE_VARIANT == "C":
                    others = self.think_forms
                    form = devs_pack.THINK_ANCHOR if turn % 2 == 0 else others[(turn // 2 + first) % len(others)]
                else:
                    form = ("lattice", "rook")[turn % 2]
            else:
                form = FORM_FOR_STATE.get(s, "cloud")
            if form in devs_pack.SEND_FORMS:
                if self.form not in devs_pack.SEND_FORMS:
                    SEND_CYCLE.append(SEND_CYCLE.pop(0))  # A new send takes the next send form.
                form = SEND_CYCLE[0]
            if form not in ("lattice", "rook", *self.think_forms):
                self.thinking_since = None
            if form != self.form:
                # Flights to and from the card are fast: stiffer springs and shorter delays.
                fast = "frame" in (form, self.form)
                self.pace, self.delay_scale = ((2.4 if form == "frame" else 2.0), 0.35) if fast else (1.0, 1.0)
                self.prev, self.form, self.form_at = self.form, form, now
                # A constellation pours out along its own paths: a scattering burst would blur its glyphs.
                self.loosen = RENDER_LOOSEN if form == "render" and self.render_form.get("kind") == "constellation" \
                    else 1.0
                self.loose_until = [-math.inf] * len(self.x)
                self.spring_unloose = True  # The chip's grains let go of their loose springs too (see _DustGL.step_springs).
            if self.dispatch is not None:  # The strands leave the send form's ports as the form turns.
                self.dispatch.ports = (devs_pack.send_ports(form, now - self.form_at, self.send_clock(now)[1])
                                       if form in devs_pack.SEND_FORMS else None)
            self._size_swarm(form, now)
            if self.swarm_vis < 1.0:
                self.swarm_vis = min(1.0, self.swarm_vis + dt / VIEW_SWARM_FADE)
            self.loosen *= math.exp(-dt / 0.26)
            if (self.form in LISTEN_FORMS or self.form == "sphere") and now - self.form_at > 0.9:
                # Once formed, the listening form's and the speaking globe's grains answer the voice within a frame
                # or two.
                self.pace += ((SPEAK_PACE if self.form == "sphere" else 2.2) - self.pace) * _glide(dt, 0.2)
            # At rest only every third grain stays; the rest dim away, then stop moving until a turn needs them.
            resting = self.home and self.form == "loop"
            self.extra += ((0.0 if resting else 1.0) - self.extra) * _glide(dt, 0.35 if resting else 0.15)
            self.idx = self.rest_idx if resting and self.extra < 0.01 else self.all_idx
            if len(self.x) > GRAINS:
                self.idx = self.big_idx
            if now >= self.next_gesture:
                rng = self.idle_rng
                a = rng.uniform(0, 2 * math.pi)
                self.gesture = (now, rng.choice(("ripple", "gather")), rng.randrange(GRAINS),
                                22 * math.cos(a), 18 * math.sin(a))
                self.next_gesture = now + rng.uniform(5, 10)
            if moving:
                # The main window's grains, in every form and scene. When the grains drawn change (the resting third, all
                # of them, or a scene's larger swarm) or their size does, the chip hands them back and takes the new.
                springs = self.spring_gl
                if (self.springs_on_gpu and (not springs or self.idx is not self.spring_idx or self.size_k != self.spring_k)
                        and self.spring_back is not None):
                    self.spring_back()  # The chip's grains, back in x, y, vx and vy for the steps here.
                self.spring_idx, self.spring_k = self.idx, self.size_k
                self.springs_on_gpu = springs
                self._move(now, min(0.1, max(0.0, now - self.moved_at)))
                self.moved_at = now

        target = self.label_text(now)
        if self.pack_kind == "flipbook" and self.flipbook is not None:
            self.flipbook.set_state(pack_player.map_overlay_state(self), now)
        if self.label != target:
            self.label_alpha -= dt / 0.18
            if self.label_alpha <= 0:
                if target and target != self.label_shown:  # The same text shown again does not replay its reveal.
                    self.label_at, self.label_shown = now, target
                self.label, self.label_alpha = target, 0.0
                x0, y0, _, h = self.read_rect
                self.label_anchor = ((x0 - FRAME_GAP, y0 + h + FRAME_GAP + 14) if target == "READING CHANGES"
                                     else (0, self.rest_pad - self.lift - ORB / 2 + 42)
                                     if target == "LAST ANSWER" or (self.home and target and target == self.waiting)
                                     else None)
        elif self.label:
            self.label_alpha = min(1.0, self.label_alpha + dt / 0.3)
        if self.guide or self.guide_shown:
            self._step_guide(now, dt)
        hint = 1.0 if self.caption_hint and self.captions else 0.0
        if hint != self.caption_hint_mix:
            self.caption_hint_mix += (hint - self.caption_hint_mix) * _glide(dt, 0.1)
            if abs(hint - self.caption_hint_mix) < 0.01:
                self.caption_hint_mix = hint

        for c in self.captions:
            c.step(now, dt)
        if self.captions:
            self.captions = [c for c in self.captions if not c.gone(now)]
            if not self.captions:
                self.caption_gone_at = now

    def _targets(self, name, now):
        """Where each grain belongs in a form right now: x and y lists, and a brightness factor list, fitted to the
        size system (see FORM_FIT)."""
        tx, ty, tb = self._form_targets(name, now)
        if name not in FORM_FIT:
            return tx, ty, tb
        k, dx, dy = FORM_FIT[name]
        return [x * k + dx for x in tx], [y * k + dy for y in ty], tb

    def _rest_look(self, look, points, flow, tb, now):
        """REST_LOOK on the loop's brightness tb: the dim rest with its flecks, and the quiet turn's glare."""
        rest, glare = _smooth(self.rest_dim), _smooth(self.glare_mix)
        if not rest and not glare:
            return
        dim, cut, twinkle, level = look["dim"], look["flecks"], look["twinkle"], look["level"]
        centre, tau, exp, sin = now * 2 * math.pi / look["lap"], 2 * math.pi, math.exp, math.sin
        peak, band = look["peak"], look["band"]
        sparkles = round(float(devs_pack.LOOK.get("sparkle_fraction", 0.12)) * 100)
        for i in self.idx:
            h = (i * 2654435761) & 0xFFFFFFFF
            if h % 100 < cut:  # A fleck: today's sparkle grains first, as the shaders pick them (sparkle_fraction).
                f = 1.0 if twinkle is None else 0.8 + 0.35 * sin(
                    tau * now / (twinkle[0] + (twinkle[1] - twinkle[0]) * (h >> 8 & 255) / 255) + (h >> 16 & 1023))
            else:  # The other sparkle grains dim to the plain grains' light, so only the flecks sparkle.
                f = dim * 0.3 if h % 100 < sparkles else dim
            f = 1.0 + (f - 1.0) * rest
            if glare:
                # The glare keys on the grain's place on the loop, as the comet does: a soft band, no orb.
                d = (points[i][0] + flow - centre + math.pi) % tau - math.pi
                f += (level * (1.0 + peak * exp(-(d / band) ** 2)) - f) * glare
            tb[i] *= f

    def _form_targets(self, name, now):
        """Where each grain belongs in a form right now, at the form's own size."""
        self._target_z = [0.0] * GRAINS
        if name in ("render", "render_old"):
            return self._render_targets(self.render_form if name == "render" else self.render_old, now)
        points = _form(name)
        if PARTICLE_VARIANT == "C" and name in devs_pack.BUILDERS:
            out = devs_pack.eval_targets(name, points, self, now)
            if out is not None:
                tx, ty, tb, tz = out
                self._target_z = tz
                return tx, ty, tb
        if name == "frame":
            return self._frame_targets(points, now)
        if name in LISTEN_FORMS and name != "ear":
            return self._wave_targets(name, points, now)
        if name == "loop":
            tx, ty, tb = [0.0] * GRAINS, [0.0] * GRAINS, [0.0] * GRAINS
            flow = now * 2 * math.pi / LOOP_PERIOD
            rest_y = self.rest_pad - self.lift - ORB / 2
            sin, cos = math.sin, math.cos
            for i in self.idx:
                along, offset = points[i]
                a = along + flow
                sa, ca = sin(a), cos(a)
                tx[i] = 60 * sa
                ty[i] = rest_y + 26 * 2 * sa * ca + offset
                # The strand through the crossing at a = 0 is in front; the other passes behind it.
                tb[i] = 0.55 + 0.225 * (ca + 1)
            lit = tb[:] if 0 <= now - self.replay_pulse_at < REPLAY_PULSE_SECONDS else None  # Before the dim rest.
            look = REST_LOOKS[REST_LOOK]
            if look:
                self._rest_look(look, points, flow, tb, now)
            elif self.quiet_mix:
                # A quiet turn: only brightness changes. The comet keys on each grain's place on the loop, so it follows
                # the figure eight through the crossing: a soft head 0.24 rad ahead of it and a tail 1.2 rad behind.
                glow, head, tau, exp = _smooth(self.quiet_mix), now * 2 * math.pi / QUIET_LAP, 2 * math.pi, math.exp
                for i in self.idx:
                    d = (points[i][0] + flow - head + math.pi) % tau - math.pi
                    pulse = exp(-(d / 0.24) ** 2) if d > 0 else (1 + d / 1.2) ** 3 if d > -1.2 else 0.0
                    tb[i] *= 1 + glow * (QUIET_LIFT + QUIET_PEAK * pulse)
            if lit is not None:
                self.replay_pulse(tb, lit, now, points, flow)
            return tx, ty, tb
        if name in SHAPE_MOTION:
            return self._shape_motion(name, points, now - self.form_at)
        if name in SHAPES or name == "sink":
            key = "static:" + name
            if key not in _FORMS:
                _FORMS[key] = ([p[0] for p in points], [p[1] for p in points], [1.0] * GRAINS)
            return _FORMS[key]
        tx, ty, tb = [], [], []
        sin, cos = math.sin, math.cos
        if name in SPIN:
            a = now * SPIN[name]
            if name in _DATA_FORMS:  # A pack's own form sways, so a flat one never turns edge-on: spin sets the pace.
                a = DATA_SWAY * math.sin(a)
            ca, sa, ct, st = cos(a), sin(a), cos(TILT), sin(TILT)
            # The speaking globe carries a wave for each syllable of Rook's voice. With no levels for 0.3 s it
            # keeps the old wobble on the voice fallback instead.
            fresh = name == "sphere" and now - self.level_at < 0.3
            v = self.voice if name == "sphere" and not fresh else 0.0
            heard = self.heard if name == "ear" else None
            # Each wave is a ring: its angle from the pole and its strength. It fades in over its first 0.12 s
            # and fades out as it nears the far side.
            rings = []
            for start, loud in self.waves if fresh else ():
                p = (now - start) / WAVE_SECONDS
                fade = _smooth(min(1.0, p / 0.12)) * cos(math.pi / 2 * p)
                rings.append((math.pi * p, 0.5 * loud * fade))
            acos, ring_w = math.acos, math.pi / WAVE_WIDTH
            floor = PALETTE["depth_floor"]
            soft = PARTICLE_VARIANT != "baseline"
            tz = []
            for x, y, z in points:
                v_band = 0.0
                if v:
                    v_band = 0.5 + 0.5 * sin(0.11 * y - 6.8 * now)
                    wave = sin(0.11 * y - 6.8 * now) * cos(0.06 * x + 1.8 * now)
                    swell = 1.0 + 0.10 * v + 0.025 * v * wave
                    x, y, z = x * swell, y * swell, z * swell
                x1, z1 = x * ca + z * sa, z * ca - x * sa
                y2, z2 = y * ct - z1 * st, y * st + z1 * ct
                if heard:
                    # Each sound starts a ripple where the orb faces the viewer, a little off-centre, and
                    # the ripple spreads over the orb to its far side: a grain further from that point
                    # answers the level heard a moment earlier.
                    away = 1 - (x1 * EAR_POLE[0] + y2 * EAR_POLE[1] + z2 * EAR_POLE[2]) / 44
                    ripple = heard[min(len(heard) - 1, int(away * 14))] ** 1.2
                    swell = 1 + 0.05 * heard[0] + 0.26 * ripple
                    x1, y2, z2 = x1 * swell, y2 * swell, z2 * swell + 30 * ripple
                elif rings:
                    # A raised cosine across each ring, so the swell has no hard edge.
                    away = acos(max(-1.0, min(1.0, (x1 * EAR_POLE[0] + y2 * EAR_POLE[1] + z2 * EAR_POLE[2]) / 46)))
                    wave = 0.0
                    for at, strength in rings:
                        u = away - at
                        if -WAVE_WIDTH < u < WAVE_WIDTH:
                            wave += strength * (1 + cos(u * ring_w))
                    if wave:
                        swell = 1 + SPEAK_RIPPLE * wave
                        x1, y2, z2 = x1 * swell, y2 * swell, z2 * swell + 30 * wave
                tx.append(x1)
                ty.append(y2)
                if soft:
                    if name == "rook":
                        # Shade the rook by horizontal rotation depth z1 (not tilted y*st + z1*ct) so the crown
                        # stays as bright and solid as the base and far battlements never vanish into shadow.
                        zn = max(-1.0, min(1.0, z1 / 40.0))
                        b_d = 0.58 + 0.70 * ((0.5 + 0.5 * zn) ** 1.15)
                    else:
                        b_d, zn = devs_pack._depth_shade(z2, 46.0)
                    if v:
                        b_d *= 0.90 + 0.52 * v * v_band
                    tb.append(b_d)
                    tz.append(zn)
                else:
                    tb.append(max(floor, 0.75 + z2 / 90))
            if soft:
                self._target_z = tz
            if name == "sphere" and PALETTE["sphere_gain"] != 1.0:
                # Painted ink overlaps where added light would not, so the light theme dims the speaking sphere, or it
                # reads as a dense dark ball.
                gain = PALETTE["sphere_gain"]
                tb = [b * gain for b in tb]
        elif name == "rows":
            elapsed = now - self.state_at if self.state == "transcribing" else 99.0
            row = min(3, int(elapsed / 0.75))
            pen = -62 + 124 * min(1.0, max(0.0, elapsed / 0.75 - row))
            rows_y = (-27, -9, 9, 27)
            for x, y, written, r in points:
                if written <= elapsed:
                    tx.append(x)
                    ty.append(y)
                    tb.append(1.0)
                else:
                    # Grains not yet written wait ahead of the pen as a fine comet 24 px long. It is brightest and
                    # narrowest at the pen and fades and widens away from it, so the pen reads as dust, not a spot.
                    u = written * 37 % 1
                    tx.append(min(66.0, pen + 2 + 24 * u))
                    ty.append(rows_y[row] + (y - rows_y[r]) * (0.6 + 1.3 * u))
                    tb.append(0.75 - 0.4 * u)
        else:
            breath = 1 + 0.05 * sin(now * 2 * math.pi / 5.5)
            g0, kind, start, gx, gy = self.gesture
            d = now - g0
            ripple = d * 55 if kind == "ripple" and d < 1.6 else 0.0
            gather = _hold(d, 0.45, 0.5, 0.7) if kind == "gather" else 0.0
            for i, (x, y, f, ph) in enumerate(points):
                px = x * breath + 3 * sin(now * f + ph)
                py = y * breath + 3 * cos(now * f * 1.3 + ph)
                if ripple:
                    r = math.hypot(px, py) or 1.0
                    push = 5 * math.exp(-((r - ripple) / 7) ** 2)
                    px, py = px + px / r * push, py + py / r * push
                if gather and (i - start) % GRAINS < 50:
                    px, py = px + (gx - px) * 0.85 * gather, py + (gy - py) * 0.85 * gather
                tx.append(px)
                ty.append(py)
                tb.append(1.0)
        return tx, ty, tb

    def _shape_motion(self, name, points, d):
        """The three shapes whose grains flow, d seconds after they began to form. Each flowing grain runs its path,
        fades out at its end, waits unseen at the start while it flies back, and fades in again, so no grain ever
        crosses the shape in sight. Brightness never changes at a stroke: in the first second the unseen grains
        come in from full, so none blinks out while the shape forms."""
        sin, cos = math.sin, math.cos
        tx, ty, tb = [p[0] for p in points], [p[1] for p in points], [1.0] * GRAINS
        arrive = max(0.0, 1 - d)

        def ease(u, a, b):
            """0 before a, 1 after b, smooth between."""
            p = min(1.0, max(0.0, (u - a) / (b - a)))
            return p * p * (3 - 2 * p)

        if name == "spinner":
            # The comet runs round its ring, one turn in about five seconds; every grain keeps its place in it.
            head = d * 1.25
            for i, (_, _, s, side) in enumerate(points):
                a = head - s * 5 / 3 * math.pi
                r = 42 + side * (0.6 + 2.4 * s)
                tx[i], ty[i], tb[i] = r * cos(a), r * sin(a), 1.3 - 0.8 * s
            return tx, ty, tb
        # The hourglass: a thin trickle falls from the neck onto the heap below, faster as it falls.
        if PARTICLE_VARIANT == "C":
            # Lathed 3D hourglass turning slowly in space with 3D sand cones and falling trickle.
            a = d * 0.36 + 0.45
            ca, sa, ct, st = cos(a), sin(a), cos(0.32), sin(0.32)
            hidden = 0.25
            tz = [0.0] * GRAINS
            for i, (px, py, pz, phase, side) in enumerate(points):
                if phase is None:
                    x1 = px * ca + pz * sa
                    z1 = pz * ca - px * sa
                    y2 = py * ct - z1 * st
                    z2 = py * st + z1 * ct
                    persp = 1.0 / (1.0 - z2 / 320.0)
                    tx[i], ty[i] = x1 * persp, y2 * persp
                    zn = max(-1.0, min(1.0, z2 / 44.0))
                    tb[i] = 0.28 + 1.04 * ((0.5 + 0.5 * zn) ** 1.15)
                    tz[i] = zn
                else:
                    c = (phase + d / 1.3) % 1.0
                    if c < hidden:
                        fx, fy, fz = 1.2 * side, -3.0 - 3.0 * (phase * 37 % 1), 0.0
                        y2 = fy * ct - fz * st
                        z2 = fy * st + fz * ct
                        tx[i], ty[i] = fx, y2
                        tb[i] = arrive
                        tz[i] = max(-1.0, min(1.0, z2 / 44.0))
                    else:
                        u = (c - hidden) / (1.0 - hidden)
                        fx = side * (0.4 + 0.9 * u)
                        fy = -3.0 + 31.0 * u * u
                        fz = 0.8 * sin(phase * 19.0 + u * 4.0)
                        y2 = fy * ct - fz * st
                        z2 = fy * st + fz * ct
                        persp = 1.0 / (1.0 - z2 / 320.0)
                        tx[i], ty[i] = fx * persp, y2 * persp
                        look = ease(u, 0.0, 0.15) * (1.0 - ease(u, 0.8, 1.0))
                        tb[i] = arrive + (1.0 - arrive) * look * 1.25
                        tz[i] = max(-1.0, min(1.0, z2 / 44.0))
            self._target_z = tz
            return tx, ty, tb
        hidden = 0.25
        for i, p in enumerate(points):
            if p[2] is None:
                continue
            c = (p[2] + d / 1.3) % 1
            if c < hidden:
                tx[i], ty[i], tb[i] = 1.5 * p[3], -3 - 3 * (p[2] * 37 % 1), arrive
                continue
            u = (c - hidden) / (1 - hidden)
            tx[i], ty[i] = p[3] * (0.4 + 0.8 * u), -3 + 31 * u * u
            tb[i] = arrive + (1 - arrive) * ease(u, 0.0, 0.15) * (1 - ease(u, 0.8, 1.0)) * 1.2
        return tx, ty, tb

    def _wave_targets(self, name, points, now):
        """The waveform listening forms. heard[0] is the voice now; the mean of heard is the voice held over
        the last half second, so a short burst and a sustained phrase look different."""
        heard = self.heard
        held = sum(heard) / len(heard)
        breath = math.sin(now * 2 * math.pi / 5.5)
        sin, cos, pi = math.sin, math.cos, math.pi
        tx, ty, tb = [0.0] * GRAINS, [0.0] * GRAINS, [1.0] * GRAINS
        if name == "halo":
            # The waveform bent into a ring: the voice pushes the radius out and in, mirrored left and right,
            # strongest at the top and bottom. The echo ring answers a moment later (exact pre-engine motion).
            spin = now * 0.12
            radius = 40 + 1.5 * breath + 7 * held
            p1, p2 = now * 3.0, now * 4.7
            # A slow three-lobed sway, sin(3 th - now / 2), from the grain's own sine and cosine.
            sway_s, sway_c = 1.3 * cos(now * 0.5), 1.3 * sin(now * 0.5)
            for i, (_, _, a, echo, off) in enumerate(points):
                th = a + spin
                c, s = cos(th), sin(th)
                m = abs((th - pi / 2) % (2 * pi) - pi)  # 0 at the top, pi at the bottom, on either side
                lv = heard[6] if echo else heard[0]
                # A fine waveform, about 24 crests a side, so a loud syllable throws out a crown of spikes.
                # In silence a faint trace of it stays, so the ring reads as a waveform at rest.
                wave = 0.7 * sin(24 * m + p1) + 0.3 * sin(37 * m - p2)
                d = 30 * (lv + 0.06) * (0.3 + 0.7 * s * s) * wave
                if d < 0:
                    d *= 0.4
                r = (radius + off * (1 + 0.5 * lv) + d + sway_s * (3 * s - 4 * s * s * s)
                     - sway_c * (4 * c * c * c - 3 * c))
                tx[i], ty[i] = r * c, r * s
                tb[i] = (0.5 if echo else 1.0) + 0.03 * abs(d)
        elif name == "helix":
            if PARTICLE_VARIANT == "C":
                # Variant C: true 3D rotating double helix with braided strand tubes, visible base-pair rungs, and perspective.
                twist, spin = 0.105 * (1 + 0.35 * held), now * 1.1
                yaw = 0.26 + 0.32 * sin(now * 0.35)
                pitch = 0.24
                cy_r, sy_r = cos(yaw), sin(yaw)
                cp_r, sp_r = cos(pitch), sin(pitch)
                tz = [0.0] * GRAINS
                for i, (x, _, u, turn, v, off, radius, swell, lag) in enumerate(points):
                    lv = heard[lag]
                    r = radius * (1 + swell * lv)
                    ph = twist * x + spin + turn
                    s, c = sin(ph), cos(ph)
                    if v is None:
                        oy, oz = off
                        px = x
                        py = r * s + oy
                        pz = r * c + oz
                        rung_scale = 1.0
                    else:
                        px = x
                        py = v * r * s
                        pz = v * r * c
                        # Keep base-pair rungs clearly visible even in silence, brightening with voice.
                        rung_scale = 0.68 + 0.32 * lv
                    x1 = px * cy_r + pz * sy_r
                    z1 = pz * cy_r - px * sy_r
                    y2 = py * cp_r - z1 * sp_r
                    z2 = py * sp_r + z1 * cp_r
                    persp = 1.0 / (1.0 - z2 / 320.0)
                    tx[i], ty[i] = x1 * persp, HELIX_DROP + y2 * persp
                    zn = max(-1.0, min(1.0, z2 / 48.0))
                    d_norm = 0.5 + 0.5 * zn
                    tb[i] = rung_scale * (0.34 + 0.98 * (d_norm ** 1.12))
                    tz[i] = zn
                self._target_z = tz
                return tx, ty, tb
            # A slender turning double helix. The voice swells its middle and tightens the twist a little;
            # each swell spreads from the middle to the tapered ends.
            twist, spin = 0.105 * (1 + 0.35 * held), now * 1.1
            for i, (x, _, u, turn, v, off, radius, swell, lag) in enumerate(points):
                lv = heard[lag]
                r = radius * (1 + swell * lv)
                ph = twist * x + spin + turn
                s, c = sin(ph), cos(ph)
                tx[i] = x
                if v is None:
                    ty[i], tb[i] = HELIX_DROP + r * s + off, max(PALETTE["depth_floor"], 0.7 + 0.45 * c)
                else:
                    ty[i], tb[i] = HELIX_DROP + v * r * s, 0.3 + 0.18 * v * c + 0.6 * lv
        elif name == "ridges":
            # Each line further back shows the voice from a moment earlier, so speech moves back into depth.
            lv = [heard[4 * j] for j in range(7)]
            height = [44 * (1 - 0.075 * j) for j in range(7)]
            calm = [(1.3 * sin(now * (0.55 + 0.07 * j) + 2.3 * j), 0.8 * sin(now * (0.9 + 0.05 * j) + 1.1 * j))
                    for j in range(7)]
            mound = 3 + 0.8 * breath
            top = [[99.0] * 40 for _ in range(7)]
            for i, (x, base, j, hump, peak, r1, r2, off) in enumerate(points):
                level = lv[j]
                rise = height[j] * (level * 0.55 * hump + level * level * 0.6 * peak) + mound * hump
                a, b = calm[j]
                y = base - rise - a * r1 - b * r2 + off
                tx[i], ty[i] = x, y
                tb[i] = (1 - 0.09 * j) * (1 + 0.04 * rise)
                k = min(39, max(0, int((x + 80) / 4)))
                if y < top[j][k]:
                    top[j][k] = y
            # A raised line hides the lines behind it, like a ridge in front of a valley: horizon[j] is the
            # highest point of every nearer line, in 4 px columns.
            horizon = [top[0]]
            for j in range(1, 6):
                horizon.append([min(a, b) for a, b in zip(horizon[-1], top[j])])
            horizon.insert(0, None)
            for i, p in enumerate(points):
                j = p[2]
                if j and ty[i] > horizon[j][min(39, max(0, int((tx[i] + 80) / 4)))] - 1:
                    tb[i] *= 0.15
        elif name == "burst":
            # A seed head. The voice lengthens every spoke, each by its own band, so a loud syllable opens it
            # like a bloom and it settles back.
            spin = now * 0.09
            length = 20 + 2 * breath + 5 * held
            core = 1 + 0.3 * heard[0]
            for i, (_, _, s, a, u, side, weight, lag, f, ph) in enumerate(points):
                if s is None:
                    th, r = a + spin * 1.7, u * core + 0.6 * sin(now * 1.3 + a * 3)
                    tx[i], ty[i], tb[i] = r * cos(th), r * sin(th), 1.25
                    continue
                th = a + spin
                ln = length + 48 * heard[lag] * weight * (0.78 + 0.22 * sin(now * f + ph))
                c, sn = cos(th), sin(th)
                r = u * ln
                tx[i], ty[i] = r * c - side * sn, r * sn + side * c
                tb[i] = (1.15 if side else 0.55 + 0.35 * u) * (1 + 0.012 * (ln - 20))
        return tx, ty, tb

    def _frame_targets(self, points, now):
        """A frame of dust just outside the card, drifting slowly clockwise, with the orb reading along its top."""
        x0, y0, w, h = self.read_rect
        left, top = x0 - FRAME_GAP, y0 - FRAME_GAP
        width, height = w + 2 * FRAME_GAP, h + 2 * FRAME_GAP
        perimeter = 2 * (width + height)
        corners = (height / 2, height / 2 + width, 1.5 * height + width, 1.5 * height + 2 * width)
        start = self.reading if self.reading is not None else now - READ_ZOOM - READ_HOLD
        p = min(1.0, max(0.0, (now - start - READ_ZOOM) / READ_HOLD))
        orb_x, orb_y = left + 22 + (width - 44) * p * p * (3 - 2 * p), top
        turn = now * 0.8
        ca, sa = math.cos(turn), math.sin(turn)
        drift = now * 14
        tx, ty, tb = [0.0] * GRAINS, [0.0] * GRAINS, [1.0] * GRAINS
        for i in self.idx:
            frac, a, b, c = points[i]
            if frac is None:
                tx[i] = orb_x + a * ca + c * sa
                ty[i] = orb_y + b
                tb[i] = 0.8 + (c * ca - a * sa) / 40
                continue
            along = frac * perimeter
            if a:
                nearest = corners[0]
                for corner in corners[1:]:
                    if abs(corner - along) < abs(nearest - along):
                        nearest = corner
                along = nearest + b
            else:
                along += drift
            along %= perimeter
            # Walk clockwise from the middle of the left edge.
            if along < corners[0]:
                tx[i], ty[i] = left - c, top + height / 2 - along
            elif along < corners[1]:
                tx[i], ty[i] = left + along - corners[0], top - c
            elif along < corners[2]:
                tx[i], ty[i] = left + width + c, top + along - corners[1]
            elif along < corners[3]:
                tx[i], ty[i] = left + width - (along - corners[2]), top + height + c
            else:
                tx[i], ty[i] = left - c, top + height - (along - corners[3])
        return tx, ty, tb

    def _portal_places(self, points, idx, now, count, shimmer=None):
        """Place the single fine edge of dust around the viewer box, matching _FRAME_GLSL."""
        v = self.view
        style = VIEW_FRAMES[VIEW_FRAME]
        sin, cos, pi, exp = math.sin, math.cos, math.pi, math.exp
        bx, by, bw, bh = v.box(now)
        margin = v.margin(now)
        band = min(style["band"] * margin, style.get("band_max", 6.0))
        spread, band_glow = style["spread"], style["band_glow"]
        rr_full = _view_corner_radius(margin, bw, bh, style)
        rr_full_arc = max(0.0, rr_full - band) if rr_full > band else rr_full
        drift = now * VIEW_DRIFT / (2 * (bw + bh - 4 * rr_full) + 2 * pi * rr_full_arc)
        sx, sy, sw0, sh0, rr = v.shape(now)
        rr_arc = max(0.0, rr - band) if rr > band else rr
        sw, sh, arc = sw0 - 2 * rr, sh0 - 2 * rr, pi * rr_arc / 2
        per = 2 * (sw + sh) + 4 * arc
        ends = []
        for length in (sw, arc, sh, arc, sw, arc, sh, arc):
            ends.append((ends[-1] if ends else 0.0) + length / per)
        wave = now / VIEW_WAVE
        s, heard, voice = self.state, self.heard, self.voice
        turn = s not in ("ready", "hidden", "result")
        bottom = (ends[3] + ends[4]) / 2
        head = now * 0.42
        open_el = max(0.0, now - v.at)
        close_el = (now - v.closing) if v.closing is not None else -1.0
        gathering = open_el < VIEW_LAG + VIEW_GATHER or close_el >= 0.0
        top_x, right_x, right_y = sx + rr, sx + sw0, sy + rr
        bottom_x, bottom_y, left_y = sx + sw0 - rr, sy + sh0, sy + sh0 - rr
        arcs = {k: -pi / 2 + (k // 2) * pi / 2 for k in (1, 3, 5, 7)}
        centres = {k: (sx + sw0 - rr if k in (1, 3) else sx + rr, sy + rr if k in (1, 7) else sy + sh0 - rr)
                   for k in (1, 3, 5, 7)}
        freq, phase = shimmer if shimmer is not None else (None, None)
        has_shimmer = shimmer is not None
        tx, ty, tb = [0.0] * count, [0.0] * count, [0.0] * count
        for i in idx:
            u, pull, off, lag_frac, _ = points[i]
            g = 1.0
            if gathering:
                g = _ease_out((open_el - lag_frac * VIEW_LAG) / VIEW_GATHER)
                if close_el >= 0.0:
                    g = min(g, 1.0 - _smooth((close_el - (1.0 - lag_frac) * VIEW_DISSOLVE_LAG) / VIEW_DISSOLVE))
                if g <= 0.0:
                    continue
            q = (u + drift) % 1
            o = off * spread - band + (1.0 - g) * pull
            glow = (band_glow + 0.18 * cos(2 * pi * (q - wave))) * g
            if turn:
                if s == "listening":
                    d = abs((q - bottom + 0.5) % 1 - 0.5) * 2
                    level = heard[min(31, int(d * 20))] ** 1.2
                    o += 10 * level
                    glow *= 1 + 0.6 * level
                elif s == "speaking":
                    o += 4 * voice
                    glow *= 1 + 0.4 * voice
                elif s in ("thinking", "transcribing"):
                    glow *= 0.65 + 1.0 * exp(-((head - q) % 1) * 10)
            if not rr:
                if q < ends[0]:
                    ex, ey = sx + q * per, sy - o
                elif q < ends[2]:
                    ex, ey = sx + sw0 + o, sy + (q - ends[0]) * per
                elif q < ends[4]:
                    ex, ey = sx + sw0 - (q - ends[2]) * per, sy + sh0 + o
                else:
                    ex, ey = sx - o, sy + sh0 - (q - ends[4]) * per
            else:
                k = min(7, bisect_right(ends, q))
                t = (q - (ends[k - 1] if k else 0.0)) * per
                if k == 0:
                    ex, ey = top_x + t, sy - o
                elif k == 2:
                    ex, ey = right_x + o, right_y + t
                elif k == 4:
                    ex, ey = bottom_x - t, bottom_y + o
                elif k == 6:
                    ex, ey = sx - o, left_y - t
                else:
                    a = arcs[k] + (t / rr_arc if rr_arc > 0 else 0.0)
                    nx, ny = cos(a), sin(a)
                    ccx, ccy = centres[k]
                    ex, ey = ccx + rr * nx + nx * o, ccy + rr * ny + ny * o
            if has_shimmer:
                p = now * freq[i] + phase[i]
                tx[i], ty[i], tb[i] = ex + 0.5 * sin(p), ey + 0.5 * cos(p * 1.3), glow
            else:
                tx[i], ty[i], tb[i] = ex, ey, glow
        return tx, ty, tb

    def frame_settings(self, now):
        """Settings for _FRAME_GLSL to place the single-row edge dust on GPU for open, morph, still, and close."""
        v, style = self.view, VIEW_FRAMES[VIEW_FRAME]
        bx, by, bw, bh = v.box(now)
        margin = v.margin(now)
        band = min(style["band"] * margin, style.get("band_max", 6.0))
        rr_full = _view_corner_radius(margin, bw, bh, style)
        rr_full_arc = max(0.0, rr_full - band) if rr_full > band else rr_full
        drift = now * VIEW_DRIFT / (2 * (bw + bh - 4 * rr_full) + 2 * math.pi * rr_full_arc)
        sx, sy, sw0, sh0, rr = v.shape(now)
        rr_arc = max(0.0, rr - band) if rr > band else rr
        sw, sh, arc = sw0 - 2 * rr, sh0 - 2 * rr, math.pi * rr_arc / 2
        per = 2 * (sw + sh) + 4 * arc
        ends = []
        for length in (sw, arc, sh, arc, sw, arc, sh, arc):
            ends.append((ends[-1] if ends else 0.0) + length / per)
        s, voice, heard = self.dust_turn
        turn = (0 if s in ("ready", "hidden", "result") else 1 if s == "listening" else 2 if s == "speaking"
                else 3 if s in ("thinking", "transcribing") else 4)
        return {"shape": (sx, sy, sw0, sh0), "rr": rr, "rr_arc": rr_arc, "per": per, "ends": ends,
                "drift": drift % 1, "wave": now / VIEW_WAVE % 1, "head": now * 0.42 % 1,
                "bottom": (ends[3] + ends[4]) / 2, "band": band, "spread": style["spread"],
                "band_glow": style["band_glow"], "open_el": min(10.0, max(0.0, now - v.at)),
                "close_el": (now - v.closing) if v.closing is not None else -1.0,
                "turn": turn, "voice": voice, "heard": heard}

    def _move(self, now, dt):
        tx, ty, tb = self._targets(self.form, now)
        tz = self._target_z
        old = None
        old_z = None
        if now < self.form_at + 0.31 * self.delay_scale:
            old = self._targets(self.prev, now)
            old_z = self._target_z
        self._helix_arrival(now, tx, ty)
        # A long step is split into steps of at most 0.034 s, so the springs stay stable at a low frame rate.
        # Stiffer springs, such as the speaking globe's, take shorter steps.
        limit = min(0.034, 0.075 / self.pace)
        steps = 1 if dt <= limit else math.ceil(dt / limit)
        pace, dscale = self.pace, self.delay_scale
        self.carry_loose(now, dt)
        if self.springs_on_gpu:
            # The chip runs this step (see _DustGL.step_springs): the targets and settings below, for the grains drawn.
            # The old form may hold fewer grains than a scene's grown swarm; the new ones take their own target.
            n_tz, n_oz, n_old = len(tz), len(old_z) if old_z else 0, len(old[0]) if old is not None else 0
            held = None if old is None else [v for i in self.idx for v in (
                (old[0][i], old[1][i], old[2][i], old_z[i] if i < n_oz else 0.0)
                if i < n_old else (tx[i], ty[i], tb[i], tz[i] if i < n_tz else 0.0))]
            goals = [v for i in self.idx for v in (tx[i], ty[i], tb[i], tz[i] if i < n_tz else 0.0)]
            self.spring_steps.append((now, dt / steps, steps, pace, self.cohesion,
                                      (30 + 580 * self.loosen) * pace * pace, self.extra, self.spring_kicks,
                                      goals, held, self.form_at, dscale, self.spring_unloose))
            self.spring_kicks, self.spring_unloose = [], False
            # At rest the grains ride their targets (the loop has no loose grains), and once a scene has settled they
            # keep to them but for a few loose ones: then the vignette follows the targets, and the chip's grains
            # need not come back each frame (see _DustGL.poll_springs).
            settled = self.form == "render" and self.render_end is None and now - self.form_at > 1.5
            self.grains_read = self.idx is not self.rest_idx and not settled
            self._follow_grains(dt, *((self.x, self.y) if self.grains_read else (tx, ty)))
            return
        self.spring_unloose = False
        glide, dt = dt, dt / steps
        z_glide = _glide(glide, 0.14)
        x, y, vx, vy, depth, z = self.x, self.y, self.vx, self.vy, self.depth, self.z
        omega, delay, curl, freq, phase, loose = self.omega, self.delay, self.curl, self.freq, self.phase, self.loose_until
        cohesion, start = self.cohesion, self.form_at
        jitter = (30 + 580 * self.loosen) * self.pace * self.pace
        sin, cos = math.sin, math.cos
        n_tz = len(tz)
        n_oz = len(old_z) if old_z is not None else 0
        for i in self.idx:
            since = now - start - delay[i] * dscale
            if old is not None and since < 0:
                gx, gy, depth[i] = old[0][i], old[1][i], old[2][i]
                gz = old_z[i] if i < n_oz else 0.0
            else:
                gx, gy, depth[i] = tx[i], ty[i], tb[i]
                gz = tz[i] if i < n_tz else 0.0
            z[i] += (gz - z[i]) * z_glide
            w = omega[i] * cohesion * pace
            k = w * w * (0.03 if loose[i] > now else 1.0)
            bend = curl[i] * k * 0.5 * (1 - since * 2 * pace) if 0 < since < 0.5 / pace else 0.0
            p = now * freq[i] + phase[i]
            jx, jy = jitter * sin(p), jitter * cos(p * 2)
            for _ in range(steps):
                dx, dy = gx - x[i], gy - y[i]
                ax = k * dx - 1.1 * w * vx[i]
                ay = k * dy - 1.1 * w * vy[i]
                if bend:
                    # Pulled along a slight curve, like filings drawn to a magnet.
                    ax -= bend * dy
                    ay += bend * dx
                ax += jx
                ay += jy
                vx[i] += ax * dt
                vy[i] += ay * dt
                x[i] += vx[i] * dt
                y[i] += vy[i] * dt
        self._follow_grains(glide)

    def _helix_arrival(self, now, tx, ty):
        """helix_fade from the grains' mean distance to the helix: 1 within 3 px, 0 past 12 px. Leaving the helix,
        the distance is to the helix they leave, so its strands fade as the grains go. It only rises while the helix
        holds and only falls while it leaves, so a voice swell or a late read of the chip's grains never flickers it."""
        leaving = self.form != "helix"
        if leaving:
            out = (devs_pack.eval_targets("helix", _form("helix")[::8], self, now)
                   if self.helix_fade > 0.0 and self.prev == "helix" and self.idx is not self.rest_idx else None)
            if out is None:
                self.helix_fade = 0.0
                return
            goals = zip(range(0, GRAINS, 8), out[0], out[1])  # Every eighth grain's place on the helix it leaves.
        else:
            goals = ((i, tx[i], ty[i]) for i in range(0, GRAINS, 8))
        d = sum(math.hypot(self.x[i] - gx, self.y[i] - gy) for i, gx, gy in goals) / len(range(0, GRAINS, 8))
        fade = min(1.0, max(0.0, (12.0 - d) / 9.0))
        self.helix_fade = min(self.helix_fade, fade) if leaving else max(self.helix_fade, fade)

    def _follow_grains(self, glide, x=None, y=None):
        """The vignette follows the grains themselves (or x and y, their targets), so it travels with them between
        rest and work."""
        x, y = (self.x, self.y) if x is None else (x, y)
        xs, ys = (x[::_rest_every()], y[::_rest_every()]) if self.home else (x, y)
        left, right, high, low = min(xs), max(xs), min(ys), max(ys)
        margin = 22 if self.home else 36
        goal = (sum(xs) / len(xs), sum(ys) / len(ys), min(86.0, max(48.0, (right - left) / 2 + margin)),
                min(86.0 if not self.home else float(REST_PAD), max(46.0, (low - high) / 2 + margin)))
        k = _glide(glide, 0.06)
        self.vignette = tuple(a + (b - a) * k for a, b in zip(self.vignette, goal))

    def carry_loose(self, now, dt):
        """A few percent of grains are always slipping loose and drifting back, once a form has settled.
        Never in the resting loop, which repeats exactly."""
        if self.home or self.loosen > 0.05:
            return
        self.loose_carry += GRAINS * 0.025 * dt
        rng = self.loose_rng
        while self.loose_carry >= 1:
            self.loose_carry -= 1
            i = rng.randrange(GRAINS)
            until, kx, ky = now + rng.uniform(0.8, 1.6), rng.uniform(-14, 14), rng.uniform(-14, 14)
            self.loose_until[i] = until
            self.vx[i] += kx
            self.vy[i] += ky
            if self.springs_on_gpu:
                self.spring_kicks.append((i, kx, ky, until))

    def draw_swarm(self, cr, w, now, top=0.0, centre=None, zoom=1.0, label=True, soft=None):
        """Draw the grains around the working centre: the middle of the canvas below top, or an explicit
        centre for the reading surface. zoom shrinks the layout but keeps the grains their real size."""
        use_soft = _OFFSCREEN_SOFT if soft is None else soft
        cx, cy = centre if centre else (w / 2, top + ORB / 2)
        if (self.pack_kind == "flipbook" and self.flipbook is not None and self.form != "render"
                and not self.dispatch_nova_standin(now)):
            try:
                state_name = pack_player.map_overlay_state(self)
                self.flipbook.set_state(state_name, now)
                lv = pack_player.state_level_for_scene(self.pack, state_name, self)
                rest_dy = self.rest_y_offset()
                tip_levels = self.dispatch_tip_levels(now)
                baked_dispatch = pack_player.has_dispatch_bake(self.pack)
                self._cairo_flipbook.draw(cr, self.flipbook, cx, cy, pack_player.REAL_SIZE / zoom, now, lv,
                                          tip_levels=tip_levels, rest_dy=rest_dy)
                if self.dispatch_active(now):
                    dy_off = self.dispatch_y_offset()
                    if baked_dispatch:
                        tip_at = self.flipbook.dispatch_tip_at()
                        self.dispatch.draw_nova_strands_cairo(cr, cx, cy + dy_off, now, self.flipbook.palette,
                                                              tip_at=tip_at)
                        head_quads = []
                        for st in self.dispatch.nova_strand_data(now, tip_at=tip_at, y_off=0.0):
                            if st["head_pos"] is not None:
                                hq = self.flipbook.sprite_quad("strand_head", st["head_tl"], st["head_pos"],
                                                               30.0 / zoom, st["head_angle"], st["head_alpha"])
                                if hq is not None:
                                    head_quads.append(hq)
                        if head_quads:
                            self._cairo_flipbook.draw_quads(cr, head_quads, cx, cy + dy_off,
                                                            pack_player.REAL_SIZE / zoom)
                    else:
                        self.dispatch.draw_strands_cairo(cr, cx, cy + dy_off, now, PALETTE, is_nova=True)
                    self.draw_dispatch_overlay(cr, cx, cy, now)
                elif label:
                    self._label(cr, cx, cy, zoom)
                if label:
                    self.draw_guide(cr, cx, cy + self.rest_y_offset() + GUIDE_REST_DY, True)
                return
            except Exception as exc:
                self.fallback_to_devs(now, f"Cairo flipbook draw failed ({exc})")
        use_scrim = PARTICLE_VARIANT == "baseline" or bool(devs_pack.LOOK.get("scrim_enabled", False))
        if use_scrim:
            vx, vy, rx, ry = self.vignette
            alpha = 0.32 * (0.3 + 0.7 * self.extra) * (1 - self.read_mix) * (1 - self.view_mix) * (1 - self.scene_mix)
            if self.idx is self.rest_idx:
                under = self.rest_scrim(cr.get_target().get_device_scale()[0], cx, cy)
                if under is not None:
                    cr.set_source_surface(under[0], *under[1])
                    cr.paint()
            else:
                _scrim(cr, cx + vx, cy + vy, rx, ry, alpha)
        if PARTICLE_VARIANT != "baseline" and use_soft:
            self._paint_grains_soft(cr, cx, cy, zoom, now)
        elif PARTICLE_VARIANT != "baseline":
            self._paint_grains_fast(cr, cx, cy, zoom, now)
        else:
            buckets = [[] for _ in range(32)]
            x, y, depth, base, tone, blue, size = self.x, self.y, self.depth, self.base, self.tone, self.blue_rank, self.size
            intensity, share, extra = self.intensity * 7, self.share, self.extra
            rest_every = _rest_every()
            sparks = []
            for i in self.idx:
                level = int(base[i] * depth[i] * intensity * (1.0 if i % rest_every == 0 else extra))
                if level <= 0:
                    continue
                buckets[(3 if blue[i] < share else tone[i]) * 8 + min(7, level)].append(i)
                if base[i] > 0.85:
                    sparks.append(i)
            self._paint_grains(cr, cx, cy, x, y, size, buckets, sparks, zoom)
        frame = self.filament_frame(now) if self.render is not None else None
        if frame is not None:  # A constellation's lines, as the GL passes draw them (see _DustGL._filament).
            con, t, dy = frame
            light = PALETTE["operator"] != cairo.OPERATOR_ADD
            filament.draw(cr, con.elements, con.lines(t, now, light), cx, cy + dy, light)
        if self.dispatch_active(now):
            self.dispatch.draw_strands_cairo(cr, cx, cy + self.dispatch_y_offset(), now, PALETTE,
                                             is_nova=(self.pack_kind == "flipbook"))
            self.draw_dispatch_overlay(cr, cx, cy, now)
        if label:
            self._label(cr, cx, cy, zoom, grains=True)
            self.draw_guide(cr, cx, cy + self.rest_y_offset() + GUIDE_REST_DY, True)
            if self.render is not None and self.form == "render":
                self._render_labels(cr, cx, cy)

    def _paint_grains_fast(self, cr, cx, cy, zoom, now=0.0):
        """Fast C-native Cairo fallback (< 1 ms/frame) for dark/light themes, flights, and reader box.

        Never drops dim grains (all visible grains draw into 4 luminance levels), uses REST_EVERY at rest on Cairo,
        and matches GL's lit area and brightness within ~25% across every form.
        """
        if not self.idx:
            return
        palette = PALETTE
        light = palette["operator"] != cairo.OPERATOR_ADD
        x, y, depth, z = self.x, self.y, self.depth, self.z
        base, tone, blue = self.base, self.tone, self.blue_rank
        intensity, err = self.intensity, self.err
        look = devs_pack.LOOK
        share = 0.0 if light else min(self.share, float(look.get("blue_max_share", 0.02)))
        extra = self.extra
        grow = palette["size"] * self.size_k / zoom
        sp_cut = int(round(float(look.get("sparkle_fraction", 0.12)) * 100))
        resting_cairo = self.home and self.form == "loop"
        indices = self.idx[::REST_EVERY] if resting_cairo else self.idx
        rest_boost = (1.18 if light else 1.62) if resting_cairo else 1.0

        cr.save()
        if PARTICLE_VARIANT == "C" and self.helix_fade > 0.01:
            strands = devs_pack.eval_helix_strands(self, now, samples=36)
            if strands:
                cr.set_operator(cairo.OPERATOR_OVER if light else cairo.OPERATOR_ADD)
                cr.set_line_cap(cairo.LINE_CAP_ROUND)
                cr.set_line_join(cairo.LINE_JOIN_ROUND)
                sc_col = ((0.68, 0.43, 0.07, 0.42 * intensity * self.helix_fade) if light
                          else (1.0, 0.72, 0.22, 0.24 * intensity * self.helix_fade))
                cr.set_source_rgba(*sc_col)
                cr.set_line_width((3.4 if light else 4.6) / zoom)
                for strand in strands:
                    if len(strand) >= 2:
                        cr.move_to(cx + strand[0][0], cy + strand[0][1])
                        for pt in strand[1:]:
                            cr.line_to(cx + pt[0], cy + pt[1])
                        cr.stroke()

        buckets = [[] for _ in range(16)]  # 4 tones x 4 alpha levels (all 4 drawn; dim grains never dropped)
        sparks = []
        for i in indices:
            d_val = depth[i] * (1.0 if i % REST_EVERY == 0 else extra) if resting_cairo else depth[i]
            if d_val <= 0.002:
                continue
            val = base[i] * d_val * intensity
            if val <= 0.002:
                continue
            if (((i * 2654435761) & 0xFFFFFFFF) % 100) < sp_cut:
                sparks.append(i)
            else:
                lv = min(3, max(0, int(val * 3.6)))
                t_idx = 3 if blue[i] < share else tone[i]
                buckets[t_idx * 4 + lv].append(i)

        cr.set_operator(cairo.OPERATOR_OVER if light else cairo.OPERATOR_ADD)
        if light:
            lt = look["light"]
            cols = (lt["amber_far"], lt["amber_mid"], lt["amber_near"], lt["accent_rgb"])
            sp_rgb = lt["sparkle_core"]
            l_gain = float(lt.get("size_gain", 1.32)) * rest_boost
            a_mul = 1.48 if resting_cairo else 1.0
            alphas = tuple(min(0.95, v * a_mul) for v in (0.24, 0.34, 0.46, 0.60))
            rads = tuple((1.12 + 0.17 * lv) * grow * l_gain for lv in range(4))
            sp_rad = 1.65 * grow * l_gain
            sp_alpha = min(0.95, 0.62 * a_mul)
        else:
            cols = ((1.0, 0.60, 0.14), (1.0, 0.72, 0.24), (1.0, 0.83, 0.42), (0.82, 0.96, 1.0))
            sp_rgb = (1.0, 0.94, 0.72)
            alphas = (0.14, 0.21, 0.29, 0.39)
            rads = tuple((1.84 + 0.26 * lv) * grow * rest_boost for lv in range(4))
            sp_rad = 2.95 * grow * rest_boost
            sp_alpha = 0.42
        ember = (0.86, 0.34, 0.16)
        rect = cr.rectangle
        for t_idx, rgb in enumerate(cols):
            r_c, g_c, b_c = _mix(rgb, ember, err)
            for lv in range(4):
                bkt = buckets[t_idx * 4 + lv]
                if not bkt:
                    continue
                h = rads[lv] * 0.8862  # Square with exact area pi * r^2 (4x faster than cr.arc in Cairo).
                d = h * 2.0
                for i in bkt:
                    rect(cx + x[i] - h, cy + y[i] - h, d, d)
                cr.set_source_rgba(r_c, g_c, b_c, min(1.0, alphas[lv] * intensity))
                cr.fill()
        if sparks:
            sr_c, sg_c, sb_c = _mix(sp_rgb, ember, err)
            h = sp_rad * 0.8862
            d = h * 2.0
            for i in sparks:
                rect(cx + x[i] - h, cy + y[i] - h, d, d)
            cr.set_source_rgba(sr_c, sg_c, sb_c, min(1.0, sp_alpha * intensity))
            cr.fill()
        cr.restore()

    def rest_scrim(self, scale, cx, cy):
        """The vignette as a cached image and its top-left corner round (cx, cy), or None when invisible."""
        if PARTICLE_VARIANT != "baseline" and not devs_pack.LOOK.get("scrim_enabled", False):
            return None
        vx, vy, rx, ry = self.vignette
        alpha = 0.32 * (0.3 + 0.7 * self.extra) * (1 - self.read_mix) * (1 - self.view_mix) * (1 - self.scene_mix)
        key = (round(rx), round(ry), round(alpha, 3), scale, PALETTE["scrim"], PALETTE["scrim_gain"])
        if key[2] * key[5] <= 0.002:
            return None
        if self.rest_vignette is None or self.rest_vignette[0] != key:
            image = cairo.ImageSurface(cairo.FORMAT_ARGB32, math.ceil(2 * key[0] * scale), math.ceil(2 * key[1] * scale))
            image.set_device_scale(scale, scale)
            _scrim(cairo.Context(image), key[0], key[1], key[0], key[1], key[2])
            self.rest_vignette = (key, image)
        return self.rest_vignette[1], (cx + vx - key[0], cy + vy - key[1])

    def main_scrim(self, scale, cx, cy):
        """The scrim draw_swarm paints under the grains round (cx, cy), cached by size and alpha, or None when invisible."""
        return self.rest_scrim(scale, cx, cy)

    def _paint_grains_soft(self, cr, cx, cy, zoom, now=0.0):
        """Soft round HDR sprites driven by themes/devs/manifest.json: fine amber dust, 10% hot white-gold sparkles,
        selective bright-grain bloom, and clean burnished amber cores with a faint warm shadow on light backgrounds."""
        if not self.idx:
            return
        target = cr.get_target()
        has_size = hasattr(target, "get_width") and hasattr(target, "get_height")
        tw = target.get_width() if has_size else 0
        th = target.get_height() if has_size else 0
        dev_scale = target.get_device_scale()[0]
        if has_size and (tw <= 0 or th <= 0):
            return
        look = devs_pack.LOOK
        palette = PALETTE
        light = palette["operator"] != cairo.OPERATOR_ADD
        x, y, vx, vy, depth, z = self.x, self.y, self.vx, self.vy, self.depth, self.z
        base, tone, blue = self.base, self.tone, self.blue_rank
        intensity, err = self.intensity, self.err
        share = 0.0 if light else min(self.share, float(look.get("blue_max_share", 0.02)))
        extra = self.extra
        grow = palette["size"] * self.size_k
        rest_every = _rest_every()
        u2d = cr.user_to_device

        d_base = float(look.get("sprite_base_px", 2.70))
        d_span = float(look.get("sprite_span_px", 1.55))
        d_fl_near = float(look.get("sprite_floor_px", 2.75))
        d_fl_far = float(look.get("sprite_far_floor_px", 2.15))
        z_gain = float(look.get("depth_size_gain", 0.28))
        sp_cut = int(round(float(look.get("sparkle_fraction", 0.12)) * 100))
        tw_rate = float(look.get("twinkle_rate", 1.55))
        t_anim = now % _TIME_WRAP
        streak_k = float(look.get("streak_strength", 1.0))
        sin = math.sin
        hypot = math.hypot

        # Gather visible grains in exact device pixels and find their tight bounding box.
        pts = []
        min_x, min_y, max_x, max_y, max_r = 1e9, 1e9, -1e9, -1e9, 0.0
        n_z = len(z)
        n_v = len(vx)
        l_gain = float(look["light"].get("size_gain", 1.32)) if light else 1.0
        for i in self.idx:
            fade = 1.0 if i % rest_every == 0 else extra
            d_val = depth[i] * fade
            if d_val <= 0.002:
                continue
            b = base[i]
            zi = z[i] if i < n_z else 0.0
            is_spark = (((i * 2654435761) & 0xFFFFFFFF) % 100) < sp_cut
            twk = (0.68 + 0.56 * (0.5 + 0.5 * sin(t_anim * tw_rate + i * 1.6180339887))) if is_spark else 1.0
            d_nom = (d_base + d_span * b) * grow * (1.08 if is_spark else 1.0)
            z_mul = 1.0 + z_gain * zi
            d_floor = (d_fl_far if zi < -0.15 else d_fl_near) * min(1.0, self.size_k)
            r = 0.5 * max(d_floor, d_nom * z_mul) * l_gain * dev_scale
            gx, gy = u2d(cx + x[i], cy + y[i])
            gx *= dev_scale
            gy *= dev_scale
            if has_size and (gx < -32 or gy < -32 or gx > tw + 32 or gy > th + 32):
                continue
            vxi = vx[i] if i < n_v else 0.0
            vyi = vy[i] if i < n_v else 0.0
            spd = hypot(vxi, vyi)
            stretch = min(1.35, ((spd - 18.0) / 145.0) * streak_k) if (streak_k > 0.0 and spd > 18.0) else 0.0
            pts.append((gx, gy, r, b, d_val, zi, 3 if blue[i] < share else tone[i], is_spark, twk,
                        i, x[i], y[i], vxi / spd if stretch > 0.0 else 1.0, vyi / spd if stretch > 0.0 else 0.0, stretch))
            r_eff = r * (1.0 + stretch)
            if gx < min_x:
                min_x = gx
            if gy < min_y:
                min_y = gy
            if gx > max_x:
                max_x = gx
            if gy > max_y:
                max_y = gy
            if r_eff > max_r:
                max_r = r_eff
        if not pts:
            return

        strands = []
        if PARTICLE_VARIANT == "C" and self.helix_fade > 0.01:
            raw_strands = devs_pack.eval_helix_strands(self, now)
            for strand in raw_strands:
                d_pts = []
                for sx, sy, zn, b_d, lv, sf in strand:
                    px_s, py_s = u2d(cx + sx, cy + sy)
                    px_s *= dev_scale
                    py_s *= dev_scale
                    d_pts.append((px_s, py_s, zn, b_d, lv, sf))
                    if px_s < min_x:
                        min_x = px_s
                    if py_s < min_y:
                        min_y = py_s
                    if px_s > max_x:
                        max_x = px_s
                    if py_s > max_y:
                        max_y = py_s
                strands.append(d_pts)

        use_bloom = (not light) and PARTICLE_VARIANT in ("B", "C")
        spark_r = float(look.get("spark_radius_px", 3.5)) * dev_scale * min(1.0, self.size_k)
        pad = math.ceil(max(max_r * 1.4, spark_r, 6.0 * dev_scale) + (18 * dev_scale if use_bloom else 4))
        x0 = int(math.floor(min_x)) - pad
        y0 = int(math.floor(min_y)) - pad
        x1 = int(math.ceil(max_x)) + pad + 1
        y1 = int(math.ceil(max_y)) + pad + 1
        if has_size:
            x0 = max(0, x0)
            y0 = max(0, y0)
            x1 = min(tw, x1)
            y1 = min(th, y1)
        bw, bh = x1 - x0, y1 - y0
        if bw <= 0 or bh <= 0:
            return

        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, bw, bh)
        out = surf.get_data()
        stride = surf.get_stride()
        if light:
            _raster_soft_light(pts, x0, y0, bw, bh, intensity, err, dev_scale, out, stride, strands=strands)
        else:
            _raster_soft_hdr(pts, x0, y0, bw, bh, intensity, err, spark_r, use_bloom, out, stride,
                             now=t_anim, dev_scale=dev_scale, size_k=self.size_k, strands=strands)
        surf.mark_dirty()
        surf.set_device_scale(dev_scale, dev_scale)
        cr.save()
        cr.identity_matrix()
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.set_source_surface(surf, x0 / dev_scale, y0 / dev_scale)
        cr.paint()
        cr.restore()

    def _paint_grains(self, cr, cx, cy, x, y, size, buckets, sparks, zoom):
        """Paint grains sorted into buckets by colour and level (colour * 8 + level), and the sparks, in the theme's
        grain model around (cx, cy)."""
        palette = PALETTE
        floor, gain, grow = palette["alpha_floor"], palette["alpha_gain"], palette["size"]
        cr.set_operator(palette["operator"])
        round_ = palette["round"]
        twins = [(dx / zoom, dy / zoom) for dx, dy in palette.get("twins") or ()]

        def grain(gx, gy, s):
            for dx, dy in ((0.0, 0.0), *twins):
                if round_:
                    cr.new_sub_path()
                    cr.arc(gx + dx, gy + dy, s / 2, 0, 2 * math.pi)
                else:
                    cr.rectangle(gx + dx - s / 2, gy + dy - s / 2, s, s)

        rect, sub, arc, tau = cr.rectangle, cr.new_sub_path, cr.arc, 2 * math.pi

        def grains(bucket, extra=0.0, fixed=None):
            """Each grain's path, by the same arithmetic as grain(): inlined for the usual single grain, since a call
            per grain is a good part of the cost when thousands are drawn."""
            if twins:
                for i in bucket:
                    grain(cx + x[i], cy + y[i], fixed if fixed is not None else (size[i] * grow + extra) / zoom)
            elif round_:
                for i in bucket:
                    s = fixed if fixed is not None else (size[i] * grow + extra) / zoom
                    sub()
                    arc(cx + x[i], cy + y[i], s / 2, 0, tau)
            else:
                for i in bucket:
                    s = fixed if fixed is not None else (size[i] * grow + extra) / zoom
                    h = s / 2
                    rect(cx + x[i] - h, cy + y[i] - h, s, s)

        if palette["rim"]:
            rim, extra, rim_alpha = palette["rim"]
            for bucket in buckets:
                grains(bucket, extra)
            cr.set_source_rgba(*rim, rim_alpha)
            cr.fill()
        for colour, rgb in enumerate(palette["tones"] + [palette["blue"]]):
            rgb = _mix(rgb, palette["ember"], self.err)
            for level in range(1, 8):
                bucket = buckets[colour * 8 + level]
                if not bucket:
                    continue
                grains(bucket)
                cr.set_source_rgba(*rgb, floor + gain * level / 7)
                cr.fill()
        grains(sparks, fixed=3.6 / zoom)
        # Sparks always add light: a glow in the dark theme, a sheen on painted gold in the light one.
        cr.set_operator(cairo.OPERATOR_ADD)
        cr.set_source_rgba(*_mix(palette["spark"], palette["ember"], self.err), palette["spark_alpha"] * self.intensity)
        cr.fill()
        cr.set_operator(cairo.OPERATOR_OVER)

    def _label(self, cr, cx, cy, zoom=1.0, in_view=False, fade=1.0, grains=False):
        """State labels sit centred under the working form; LAST ANSWER sits under the resting loop; the reading
        label sits under the frame's left corner; in_view places the label under the viewer box scaled by fade.
        A pack's lettering reveals a new label (see _reveal_rows); grains paints its grains here, for Cairo."""
        alpha = LABEL_ALPHA * _ease_out(self.label_alpha) * fade
        if not self.label or self.label_alpha <= 0.01 or alpha <= 0.005:
            return
        sprite, w, h = self._label_sprite(cr, self.label)
        x, y, offset, origin = self._label_spot(cx, cy, w, in_view)
        if PALETTE["label_plate"]:
            cr.save()
            cr.translate(x, y)
            cr.scale(1 / zoom, 1 / zoom)
            ix, iy, iw, ih = self._label_ink(cr, self.label)
            if self.label != "READING CHANGES":
                offset = -(ix + iw / 2)
            self._plated_label(cr, self.label, offset, -(iy + ih / 2), alpha)
            cr.restore()
            return
        cr.save()
        cr.translate(x, y)
        cr.scale(1 / zoom, 1 / zoom)
        cr.set_source_surface(sprite, offset, -h / 2)
        t = self.last - self.label_at
        if LETTERING and LETTERING["reveal"] == "spread" and t < REVEAL_SECONDS and not in_view:
            geometry = self._label_geometry()
            cr.mask(_reveal_mask(geometry[0], t, origin, offset, -h / 2, alpha))
            if grains:
                _paint_reveal_rows(cr, _reveal_rows(geometry, t, origin, offset, -h / 2))
        else:
            cr.paint_with_alpha(alpha)
        cr.restore()

    def _label_spot(self, cx, cy, w, in_view=False):
        """Where _label puts a label sprite w wide: the point (x, y) its middle left edge is offset from, the x offset,
        and the side its reveal spreads from."""
        if in_view and self.view is not None:
            bx, by, bw, bh = self.view.box(self.last)
            return cx + bx + bw / 2, cy + by + bh + VIEW_LINE_DY, -(w - LABEL_SPACING) / 2, "centre"
        if self.label == "READING CHANGES":
            return cx + self.label_anchor[0], cy + self.label_anchor[1], -14, "left"
        if self.label_anchor:
            return cx + self.label_anchor[0], cy + self.label_anchor[1], -(w - LABEL_SPACING) / 2, "centre"
        return cx, cy + ORB / 2 + 9, -(w - LABEL_SPACING) / 2, "centre"

    def _label_geometry(self):
        return _type_geometry(_cased(self.label, "label"), LABEL_FONT, LABEL_SPACING)

    def reveal_gl_rows(self, now):
        """The label's reveal grains for the dust engine, relative to the working centre; empty at rest."""
        t = now - self.label_at
        if (not LETTERING or LETTERING["reveal"] != "spread" or not 0.0 <= t < REVEAL_SECONDS or not self.label
                or self.label_alpha <= 0.01 or PALETTE["label_plate"]):
            return []
        geometry = self._label_geometry()
        w, h = geometry[2]
        x, y, offset, origin = self._label_spot(0.0, 0.0, w)
        return _reveal_rows(geometry, t, origin, x + offset, y - h / 2)

    def _step_guide(self, now, dt):
        """The guide fades out, then reveals its new text or place, as the label does. In a turn it glides down under a
        caption and back up."""
        if self.guide and now >= self.guide["ends"]:
            self.guide = None
        slot = GUIDE_BELOW if self.captions else GUIDE_TOP
        # A send fan that still holds after the turn keeps the guide where the turn had it.
        target = (self.guide["text"], self.guide["code"], self.home and not self.dispatch_active(now)) if (
            self.guide and not self.dark and self.state != "hidden") else None
        if self.guide_shown != target:
            self.guide_alpha -= dt / 0.18
            if self.guide_alpha <= 0:
                self.guide_shown, self.guide_alpha, self.guide_at, self.guide_y = target, 0.0, now, slot
                # Measured once per guide: the area at home grows only to this width (see Overlay._size_canvas).
                self.guide_w = max((_type_geometry(*line)[0][2] for line in _guide_lines(*target[:2])),
                                   default=0) if target else 0
        elif target:
            self.guide_alpha = min(1.0, self.guide_alpha + dt / 0.3)
        if self.guide_y != slot:
            self.guide_y = slot if abs(slot - self.guide_y) < 0.1 else self.guide_y + (slot - self.guide_y) * _glide(
                dt, 0.25)

    def guide_key(self, dim=0.0):
        """A key for what draw_guide paints. Equal keys paint the same pixels."""
        if self.guide_shown is None or self.guide_alpha <= 0.0:
            return None
        return (self.guide_shown, round(self.guide_alpha, 3), round(min(REVEAL_SECONDS, self.last - self.guide_at), 3),
                round(self.guide_y, 1), round(dim, 3), id(PALETTE), id(self.label_sprites))

    def draw_guide(self, cr, x, y, home, dim=0.0):
        """The held guide, its letters centred on x with their top at y, when it sits at home (under the resting loop)
        or not (in the caption area): the code large in the caption lettering, then the text in the label lettering. It
        comes in with the label's reveal, its grains painted here in Cairo as the captions are, and fades out."""
        shown = self.guide_shown
        alpha = _ease_out(self.guide_alpha) * (1 - dim)
        if shown is None or shown[2] != home or alpha <= 0.005:
            return
        text, code, _ = shown
        scale = cr.get_target().get_device_scale()[0]
        t = self.last - self.guide_at
        reveal = LETTERING and LETTERING["reveal"] == "spread" and t < REVEAL_SECONDS
        key = ("guide", text, code, scale)
        if key not in self.label_sprites:  # Laid out once per guide, as a caption is.
            lines = []
            for n, (line, font, spacing) in enumerate(_guide_lines(text, code)):
                if n or not code:
                    lines.append((self._label_sprite(cr, line)[0], _type_geometry(line, font, spacing), LABEL_ALPHA))
                    continue
                if LETTERING:  # The label's core, gold rim and dark edge (see _lettering_sprite), scaled to the size.
                    outline, rim = LETTERING["outline"], LETTERING["rim"]
                    rim = (rim[0] * GUIDE_CODE_SCALE, rim[1], rim[2])
                    edge = (outline[0] * GUIDE_CODE_SCALE + rim[0], max(outline[1], 0.95))
                    sprite = _word_sprite(cr, line, scale, font, LETTERING["caption"]["color"], spacing, (),
                                          outline[2], edge, rim=rim)[0]
                else:
                    sprite = _word_sprite(cr, line, scale, font, PALETTE["text"], spacing, PALETTE["text_halos"],
                                          PALETTE["text_halo"])[0]
                lines.append((sprite, _type_geometry(line, font, spacing), 1.0))
            self.label_sprites[key] = lines
        plate = PALETTE["caption_plate"]
        for n, (sprite, geometry, a) in enumerate(self.label_sprites[key]):
            ix, iy, iw, ih = geometry[0]
            sx, sy = x - ix - iw / 2, y - iy  # The letters' ink, not the sprite, is centred and stacked.
            if plate and code and n == 0:  # The light theme's ivory code needs its caption plate.
                _plate(cr, sx + ix - plate["pad_x"], y - plate["pad_y"], iw + 2 * plate["pad_x"],
                       ih + 2 * plate["pad_y"], plate, alpha)
            cr.set_source_surface(sprite, sx, sy)
            if reveal:
                cr.mask(_reveal_mask(geometry[0], t, "centre", sx, sy, a * alpha))
                _paint_reveal_rows(cr, _reveal_rows(geometry, t, "centre", sx, sy))
            else:
                cr.paint_with_alpha(a * alpha)
            y += ih + GUIDE_GAP

    def _label_sprite(self, cr, text):
        """A cached label in the label style: the sprite and its width and height in logical pixels."""
        scale = cr.get_target().get_device_scale()[0]
        key = (text, scale)
        if key not in self.label_sprites:
            if LETTERING:
                self.label_sprites[key] = _lettering_sprite(cr, _cased(text, "label"), scale, "label")[0]
            else:
                self.label_sprites[key] = _word_sprite(cr, text, scale, LABEL_FONT, PALETTE["label"], LABEL_SPACING,
                                                       PALETTE["label_halos"], PALETTE["label_halo"],
                                                       PALETTE["label_outline"])[0]
        sprite = self.label_sprites[key]
        return sprite, sprite.get_width() / scale, sprite.get_height() / scale

    def _label_ink(self, cr, text):
        """The label's letters' ink box (x, y, width, height) inside its sprite, cached: the plate fits the letters,
        so its padding is even and the capitals sit optically centred."""
        key = ("ink", text)
        if key not in self.label_sprites:
            layout = PangoCairo.create_layout(cr)
            layout.set_font_description(LABEL_FONT)
            attrs = Pango.AttrList()
            attrs.insert(Pango.attr_letter_spacing_new(int(LABEL_SPACING * Pango.SCALE)))
            layout.set_attributes(attrs)
            layout.set_text(_safe_utf8(text), -1)
            ink, logical = layout.get_pixel_extents()
            self.label_sprites[key] = (14 + ink.x - logical.x, 14 + ink.y - logical.y, ink.width, ink.height)
        return self.label_sprites[key]

    def _plated_label(self, cr, text, sx, sy, alpha):
        """A label in the light theme: its plate fitted to the letters, then the letters, both on whole pixels. The
        letters keep LABEL_ALPHA's softness; the plate does not, so it matches the caption plates' tone."""
        sprite = self._label_sprite(cr, text)[0]
        plate = PALETTE["label_plate"]
        ix, iy, iw, ih = self._label_ink(cr, text)
        _plate(cr, sx + ix - plate["pad_x"], sy + iy - plate["pad_y"], iw + 2 * plate["pad_x"], ih + 2 * plate["pad_y"],
               plate, min(1.0, alpha / LABEL_ALPHA))
        cr.set_source_surface(sprite, *_device_round(cr, sx, sy))
        cr.paint_with_alpha(alpha)

    def caption_key(self, w, now, dim=0.0):
        """A key for what draw_caption paints at now. Equal keys paint the same pixels."""
        if not self.captions:
            return None
        plate = bool(PALETTE["caption_plate"])
        parts = []
        for c in self.captions:
            ca = c.alpha(now) * (1 - dim)
            for s, out in c.visible():
                a = out * ca
                clock = c.clock
                words = []
                for _, _, at in s.words:
                    p = (clock - at) / WORD_IN
                    q = p + 0.35 if plate else 0.0
                    if p <= 0 and q <= 0:
                        break
                    words.append((min(1.0, max(0.0, p)), min(1.0, max(0.0, q)) if plate else 0.0))
                lines = () if s.lines is None else tuple(
                    min(1.0, max(0.0, (clock - at) / 0.4)) for at, _, _ in s.lines[1:])
                parts.append((id(s), s.scale, a, min(1.0, max(0.0, (clock - s.first) / 0.3)), lines, tuple(words)))
        if not parts:
            return None
        return (w, id(PALETTE), self.caption_hint_mix, tuple(parts))

    def draw_caption(self, cr, w, now, dim=0.0):
        """The spoken words. With the pointer over them they brighten a little and READ MORE shows beneath."""
        scale = cr.get_target().get_device_scale()[0]
        left, top = (w - CAPTION_W) / 2, CAPTION_TOP
        shown = []
        for c in self.captions:
            ca = c.alpha(now) * (1 - dim)
            for s, out in c.visible():
                if s.scale != scale:
                    s.build(cr, scale)
                shown.append((c, s, out * ca))
        self.caption_box = None
        if not shown:
            return
        weight = sum(a * _ease_out((c.clock - s.first) / 0.3) for c, s, a in shown)
        total = sum(a for *_, a in shown)
        plates = []
        if weight > 0.001:
            boxes = [(a, s.box(c.clock)) for c, s, a in shown]
            bx, by, bw, bh = (sum(a * box[i] for a, box in boxes) / total for i in range(4))
            plate = PALETTE["caption_plate"]
            if plate:
                # A plate per line, as wide as that line's shown words: it grows with them, wraps with them, and
                # fades with the caption.
                for c, s, a in shown:
                    for (x0, y0, x1, y1), k in _shown_lines(s, c.clock, scale):
                        plates.append(_plate(cr, left + x0 - plate["pad_x"], top + y0 - plate["pad_y"],
                                             x1 - x0 + 2 * plate["pad_x"], y1 - y0 + 2 * plate["pad_y"], plate, a * k))
            elif not LETTERING:  # A pack's lettering has no soft backing: its outline keeps it legible.
                gain, pad_x, pad_y = PALETTE["text_backing"]
                _scrim(cr, left + bx, top + by, bw / 2 + pad_x, bh / 2 + pad_y, 0.2 * min(1.0, weight), gain)
            self.caption_box = (left + bx - bw / 2, top + by - bh / 2, bw, bh)
        hint = self.caption_hint_mix
        cr.save()
        if PALETTE["caption_plate"]:
            # The words show only on their plates: a word coming in is revealed by its plate's edge as it fades, so
            # no letter ever sits on the bare page.
            for box in filter(None, plates):
                _rounded_rect(cr, *box)
            cr.clip()
        for c, s, a in shown:
            for sprite, x, y, at in s.sprites:
                p = (c.clock - at) / WORD_IN
                if p <= 0:
                    break
                e = _ease_out(p)
                at = (left + x, top + y + WORD_RISE * (1 - e))
                cr.set_source_surface(sprite, *(_device_round(cr, *at) if PALETTE["snap"] else at))
                cr.paint_with_alpha(e * a)
                if hint > 0:
                    cr.set_operator(cairo.OPERATOR_ADD)
                    cr.paint_with_alpha(0.22 * hint * e * a)
                    cr.set_operator(cairo.OPERATOR_OVER)
        cr.restore()
        if hint > 0 and self.caption_box:
            sprite, sw, sh = self._label_sprite(cr, "READ MORE")
            bx, by, bw, bh = self.caption_box
            if PALETTE["label_plate"]:
                ix, iy, iw, ih = self._label_ink(cr, "READ MORE")
                self._plated_label(cr, "READ MORE", bx + bw / 2 - ix - iw / 2, by + bh + 22 - iy - ih / 2,
                                   0.9 * hint * min(1.0, total))
                return
            cr.set_source_surface(sprite, bx + bw / 2 - (sw - LABEL_SPACING) / 2, by + bh + 22 - sh / 2)
            cr.paint_with_alpha(0.9 * hint * min(1.0, total))


def _view_media_rect(rect, p):
    """The media's rect as it comes in or leaves: a slight settle from 96% to full size."""
    x, y, w, h = rect
    k = 0.96 + 0.04 * p
    return x + w * (1 - k) / 2, y + h * (1 - k) / 2, w * k, h * k


_TITLES = {}


def _fit_title(text, width):
    """The title in capitals, cut with an ellipsis to fit width in the label font."""
    key = (text, round(width), LABEL_FONT.to_string(), LABEL_SPACING)
    if key not in _TITLES:
        layout = Pango.Layout.new(PangoCairo.FontMap.get_default().create_context())
        layout.set_font_description(LABEL_FONT)
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_letter_spacing_new(int(LABEL_SPACING * Pango.SCALE)))
        layout.set_attributes(attrs)
        words = " ".join(_safe_utf8(text).upper().split())
        cut = words
        while True:
            layout.set_text(cut, -1)
            if layout.get_pixel_extents()[1].width <= width or len(cut) <= 1:
                break
            words = words[:-1].rstrip()
            cut = words + "…"
        _TITLES[key] = cut
    return _TITLES[key]


def _guide_lines(text, code):
    """The guide's lines as (text, font, spacing), the code first: the code in the caption lettering at
    GUIDE_CODE_SCALE times its size, and the text in the label lettering, cut with an ellipsis to fit the window."""
    lines = []
    if code:
        font = CAPTION_FONT.copy()
        font.set_absolute_size(CAPTION_FONT.get_size() * GUIDE_CODE_SCALE)
        lines.append((code, font, CAPTION_SPACING * GUIDE_CODE_SCALE + GUIDE_CODE_TRACK * font.get_size() / Pango.SCALE))
    if text:
        text = _fit_title(text, WIDTH - 2 * GUIDE_MARGIN)
        lines.append((_cased(text, "label") if LETTERING else text, LABEL_FONT, LABEL_SPACING))
    return lines


def _paint_view_line(cr, scene, now, centre, line, mark):
    """The line under the box: the title (or PAUSED), which gives way to the state label in a turn, and for a video a
    small close mark at the box's right edge. Both in the label style."""
    v = scene.view
    if v is None:
        return
    cx, cy = centre
    bx, by, bw, bh = v.box(now)
    p = v.media_in(now)
    x, y = cx + bx + bw / 2, cy + by + bh + VIEW_LINE_DY
    shown = scene.label_alpha if scene.label else 0.0
    alpha = LABEL_ALPHA * p * (1 - _ease_out(shown))
    if line and alpha > 0.01:
        sprite, w, h = scene._label_sprite(cr, _fit_title(line, bw - 60))
        cr.set_source_surface(sprite, x - (w - LABEL_SPACING) / 2, y - h / 2)
        cr.paint_with_alpha(alpha)
    if mark and p > 0.01:
        mx, size = cx + bx + bw - 7, 4.5
        cr.save()
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for width, rgb, a in ((2 * PALETTE["label_outline"][0] + 1.6, PALETTE["label_halo"], PALETTE["label_outline"][1]),
                              (1.6, PALETTE["label"], 1.0)):
            cr.move_to(mx - size, y - size)
            cr.line_to(mx + size, y + size)
            cr.move_to(mx + size, y - size)
            cr.line_to(mx - size, y + size)
            cr.set_line_width(width)
            cr.set_source_rgba(*rgb, a * LABEL_ALPHA * p)
            cr.stroke()
        cr.restore()


def _paint_view_controls(cr, controls, playing, progress):
    """The viewer's hover controls, drawn like the close mark beside them: label-gold marks with the label's halo and
    no plates, so they sit on the line under the box as the title does. A play or pause mark, the scrub bar as a
    hairline the gold fills along to a small bead of the same line, and an "open in the system viewer" arrow.
    controls are the rects from Overlay._view_controls; progress runs from 0 to 1, or is None."""
    halo_w, halo_a = PALETTE["label_outline"]
    def ink(path, width=1.6, fill=False, alpha=1.0):
        for w, rgb, a in ((2 * halo_w + width, PALETTE["label_halo"], halo_a), (width, PALETTE["label"], 1.0)):
            path()
            cr.set_line_width(w)
            cr.set_source_rgba(*rgb, a * alpha * LABEL_ALPHA)
            if fill and rgb is PALETTE["label"]:
                cr.fill_preserve()
            cr.stroke()
    cr.save()
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    if "play" in controls:
        x, y, w, h = controls["play"]
        cx, cy = x + w / 2, y + h / 2
        if playing:
            ink(lambda: (cr.move_to(cx - 2.5, cy - 4.5), cr.line_to(cx - 2.5, cy + 4.5),
                         cr.move_to(cx + 2.5, cy - 4.5), cr.line_to(cx + 2.5, cy + 4.5)), width=2.0)
        else:
            ink(lambda: (cr.move_to(cx - 3, cy - 5), cr.line_to(cx + 4.5, cy), cr.line_to(cx - 3, cy + 5),
                         cr.close_path()), width=1.2, fill=True)
    if "scrub" in controls and controls["scrub"][2] > 0:
        x, y, w, h = controls["scrub"]
        x0, x1, cy = x + 4, x + w - 4, y + h / 2
        ink(lambda: (cr.move_to(x0, cy), cr.line_to(x1, cy)), width=2.4, alpha=0.45)
        if progress is not None:
            head = x0 + (x1 - x0) * max(0.0, min(1.0, progress))
            ink(lambda: (cr.move_to(x0, cy), cr.line_to(head, cy)), width=3.2)
            ink(lambda: (cr.new_sub_path(), cr.arc(head, cy, 4.2, 0, 2 * math.pi)), width=1.0, fill=True)
    if "open" in controls:
        x, y, w, h = controls["open"]
        cx, cy = x + w / 2, y + h / 2
        ink(lambda: (cr.move_to(cx - 4, cy + 4), cr.line_to(cx + 4, cy - 4),
                     cr.move_to(cx - 1, cy - 4), cr.line_to(cx + 4, cy - 4), cr.line_to(cx + 4, cy + 1)))
    cr.restore()


def _paint_view_close(cr, rect, hot=False):
    """The viewer's close X in its own node at rect: a soft disc in the label halo's colour, so it reads over any
    picture, under a label-gold X with the label's halo, as the other controls are drawn. While the pointer is on it
    (hot), the disc fills more and a gold ring circles it, so the press target is plain."""
    x, y, w, h = rect
    cx, cy, r, arm = x + w / 2, y + h / 2, w / 2, w * 0.2
    cr.save()
    cr.set_source_rgba(*PALETTE["label_halo"], 0.7 if hot else 0.45)  # Dark under the dark theme's gold, light under the light one's brown.
    cr.arc(cx, cy, r - 1, 0, 2 * math.pi)
    cr.fill()
    if hot:
        cr.set_line_width(1.6)
        cr.set_source_rgba(*PALETTE["label"], LABEL_ALPHA)
        cr.arc(cx, cy, r - 1.8, 0, 2 * math.pi)
        cr.stroke()
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    for width, rgb, a in ((2 * PALETTE["label_outline"][0] + 2.0, PALETTE["label_halo"], PALETTE["label_outline"][1]),
                          (2.0, PALETTE["label"], 1.0)):
        cr.move_to(cx - arm, cy - arm)
        cr.line_to(cx + arm, cy + arm)
        cr.move_to(cx + arm, cy - arm)
        cr.line_to(cx - arm, cy + arm)
        cr.set_line_width(width)
        cr.set_source_rgba(*rgb, a * LABEL_ALPHA)
        cr.stroke()
    cr.restore()


def _view_caption_origin(scene, now, centre):
    """Where the captions' area starts while the viewer shows: centred under the box, below its line."""
    bx, by, bw, bh = scene.view.box(now)
    return centre[0] + bx + bw / 2 - WIDTH / 2, centre[1] + by + bh + VIEW_CAPTION_DY


def _paint_media(cr, surface, rect, alpha):
    """A media frame, decoded at the box's device pixels, painted into rect (smaller while it comes in)."""
    if surface is None or alpha <= 0.002:
        return
    x, y, w, h = rect
    sw = surface.get_width() / surface.get_device_scale()[0]
    cr.save()
    cr.translate(x, y)
    cr.scale(w / sw, w / sw)
    cr.set_source_surface(surface, 0, 0)
    cr.get_source().set_filter(cairo.FILTER_GOOD)
    cr.paint_with_alpha(alpha)
    cr.restore()


# Soft-sprite HDR LUTs and rasterizers driven by themes/devs/manifest.json (Cairo offscreen path matching GL).
_SOFT_K_LUT = [math.exp(-float(devs_pack.LOOK.get("gaussian_k", 4.2)) * (k / 255.0)) * (1.0 - k / 255.0) for k in range(256)]
_SOFT_SPARK_LUT = [math.exp(-float(devs_pack.LOOK.get("spark_k", 3.2)) * (k / 255.0)) * (1.0 - k / 255.0) for k in range(256)]
_SOFT_RIM_LUT = [(1.0 - k / 255.0) ** 2 for k in range(256)]
_SRGB_LUT = [
    min(255, int((12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1.0 / 2.4)) - 0.055) * 255.0 + 0.5))
    for c in (k / 1023.0 for k in range(1024))
]
_DARK_LOOK = devs_pack.LOOK["dark"]
_SOFT_TONES_LIN = tuple(tuple(c) for c in _DARK_LOOK["tones_lin"]) + (tuple(_DARK_LOOK["accent_lin"]),)
_SOFT_EMBER_LIN = tuple(_DARK_LOOK["ember_lin"])


def _bilinear3(buf, w, h, fx, fy):
    """Clamp-to-edge bilinear sample of a 3-channel float array at pixel-centre coords (fx, fy)."""
    if fx < 0.0:
        fx = 0.0
    elif fx > w - 1.0:
        fx = w - 1.0
    if fy < 0.0:
        fy = 0.0
    elif fy > h - 1.0:
        fy = h - 1.0
    x0 = int(fx)
    y0 = int(fy)
    x1 = x0 + 1 if x0 + 1 < w else x0
    y1 = y0 + 1 if y0 + 1 < h else y0
    tx = fx - x0
    ty = fy - y0
    w00 = (1.0 - tx) * (1.0 - ty)
    w10 = tx * (1.0 - ty)
    w01 = (1.0 - tx) * ty
    w11 = tx * ty
    i00 = (y0 * w + x0) * 3
    i10 = (y0 * w + x1) * 3
    i01 = (y1 * w + x0) * 3
    i11 = (y1 * w + x1) * 3
    return (
        buf[i00] * w00 + buf[i10] * w10 + buf[i01] * w01 + buf[i11] * w11,
        buf[i00 + 1] * w00 + buf[i10 + 1] * w10 + buf[i01 + 1] * w01 + buf[i11 + 1] * w11,
        buf[i00 + 2] * w00 + buf[i10 + 2] * w10 + buf[i01 + 2] * w01 + buf[i11 + 2] * w11,
    )


def _kawase_down(src, sw, sh, soft_knee=False):
    """Dual Kawase 5-tap downsample (center*4 + 4 half-pixel diagonals) / 8."""
    dw = max(1, (sw + 1) // 2)
    dh = max(1, (sh + 1) // 2)
    dst = array("f", [0.0]) * (dw * dh * 3)
    samp = _bilinear3
    for y in range(dh):
        cy = (y + 0.5) * 2.0 - 0.5
        row = y * dw * 3
        for x in range(dw):
            cx = (x + 0.5) * 2.0 - 0.5
            r0, g0, b0 = samp(src, sw, sh, cx, cy)
            r1, g1, b1 = samp(src, sw, sh, cx - 1.0, cy - 1.0)
            r2, g2, b2 = samp(src, sw, sh, cx + 1.0, cy - 1.0)
            r3, g3, b3 = samp(src, sw, sh, cx - 1.0, cy + 1.0)
            r4, g4, b4 = samp(src, sw, sh, cx + 1.0, cy + 1.0)
            r = (4.0 * r0 + r1 + r2 + r3 + r4) * 0.125
            g = (4.0 * g0 + g1 + g2 + g3 + g4) * 0.125
            b = (4.0 * b0 + b1 + b2 + b3 + b4) * 0.125
            if soft_knee:
                # Bloom only the brightest ~15% sparkles and hot overlapping clusters; keep fine dust crisp.
                lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
                thr = float(devs_pack.LOOK.get("bloom_threshold", 0.58))
                knee = float(devs_pack.LOOK.get("bloom_knee", 0.35))
                if lum <= thr:
                    k = 0.0
                else:
                    ex = lum - thr
                    k = ex / (ex + knee)
                r *= k
                g *= k
                b *= k
            di = row + x * 3
            dst[di] = r
            dst[di + 1] = g
            dst[di + 2] = b
    return dst, dw, dh


def _kawase_up(src, sw, sh, dw, dh):
    """Dual Kawase 8-tap tent upsample (4 cardinal*1 + 4 diagonal*2) / 12."""
    dst = array("f", [0.0]) * (dw * dh * 3)
    samp = _bilinear3
    sx = sw / float(dw)
    sy = sh / float(dh)
    inv12 = 1.0 / 12.0
    for y in range(dh):
        cy = (y + 0.5) * sy - 0.5
        row = y * dw * 3
        for x in range(dw):
            cx = (x + 0.5) * sx - 0.5
            ra, ga, ba = samp(src, sw, sh, cx - 1.0, cy)
            rb, gb, bb = samp(src, sw, sh, cx + 1.0, cy)
            rc, gc, bc = samp(src, sw, sh, cx, cy - 1.0)
            rd, gd, bd = samp(src, sw, sh, cx, cy + 1.0)
            re, ge, be = samp(src, sw, sh, cx - 0.5, cy - 0.5)
            rf, gf, bf = samp(src, sw, sh, cx + 0.5, cy - 0.5)
            rg, gg, bg = samp(src, sw, sh, cx - 0.5, cy + 0.5)
            rh, gh, bh = samp(src, sw, sh, cx + 0.5, cy + 0.5)
            di = row + x * 3
            dst[di] = (ra + rb + rc + rd + 2.0 * (re + rf + rg + rh)) * inv12
            dst[di + 1] = (ga + gb + gc + gd + 2.0 * (ge + gf + gg + gh)) * inv12
            dst[di + 2] = (ba + bb + bc + bd + 2.0 * (be + bf + bg + bh)) * inv12
    return dst


def _add_kawase_bloom(hdr, bw, bh):
    """Two-level Dual Kawase bloom (full -> 1/2 -> 1/4 -> 1/2 -> full), added warm into linear HDR."""
    if bw < 8 or bh < 8:
        return
    l1, w1, h1 = _kawase_down(hdr, bw, bh, soft_knee=True)
    l2, w2, h2 = _kawase_down(l1, w1, h1, soft_knee=False)
    u1 = _kawase_up(l2, w2, h2, w1, h1)
    # Blend a touch of the tighter half-res glow with the wider quarter-res mist for organic dust air.
    for i in range(len(u1)):
        u1[i] = 0.72 * u1[i] + 0.28 * l1[i]
    # Bilinearly add upsampled half-res bloom directly into full-res HDR (matches GL linear texture sampling).
    strength = float(devs_pack.LOOK.get("bloom_strength", KAWASE_BLOOM_STRENGTH))
    tr, tg, tb = devs_pack.LOOK.get("bloom_tint", (1.0, 0.90, 0.64))
    sr, sg, sb = strength * tr, strength * tg, strength * tb
    samp = _bilinear3
    sx = w1 / float(bw)
    sy = h1 / float(bh)
    for y in range(bh):
        cy = (y + 0.5) * sy - 0.5
        row = y * bw * 3
        for x in range(bw):
            cx = (x + 0.5) * sx - 0.5
            br, bg, bb = samp(u1, w1, h1, cx, cy)
            i = row + x * 3
            hdr[i] += br * sr
            hdr[i + 1] += bg * sg
            hdr[i + 2] += bb * sb


def _raster_helix_strands_hdr(hdr, strands, x0, y0, bw, bh, intensity, err, dev_scale, size_k, en_gain):
    """Add continuous 3D glowing gold helix strands into linear HDR (exact match to _DustGL _STRAND_FRAG)."""
    if not strands:
        return
    er, eg, eb = _SOFT_EMBER_LIN
    e1 = 1.0 - err
    sk = min(1.0, size_k)
    exp = math.exp
    for strand in strands:
        if len(strand) < 2:
            continue
        # Per-strand max accumulation prevents joint overlap brightening (matches GL mitered triangle strip).
        sr_buf = array("f", [0.0]) * (bw * bh)
        sg_buf = array("f", [0.0]) * (bw * bh)
        sb_buf = array("f", [0.0]) * (bw * bh)
        sw_buf = array("f", [0.0]) * (bw * bh)
        for p0, p1 in zip(strand, strand[1:]):
            ax, ay, z0, b0, lv0, f0 = p0
            bx, by, z1, b1, lv1, f1 = p1
            if f0 <= 0.002 and f1 <= 0.002:
                continue
            ax -= x0
            ay -= y0
            bx -= x0
            by -= y0
            vx, vy = bx - ax, by - ay
            seg_len2 = vx * vx + vy * vy
            if seg_len2 < 1e-6:
                continue
            inv_len2 = 1.0 / seg_len2
            hw0 = (2.15 + 0.65 * z0 + 0.55 * lv0) * dev_scale * sk
            hw1 = (2.15 + 0.65 * z1 + 0.55 * lv1) * dev_scale * sk
            rmax = max(hw0, hw1) + 1.0
            ix0 = max(0, int(math.floor(min(ax, bx) - rmax)))
            ix1 = min(bw - 1, int(math.ceil(max(ax, bx) + rmax)))
            iy0 = max(0, int(math.floor(min(ay, by) - rmax)))
            iy1 = min(bh - 1, int(math.ceil(max(ay, by) + rmax)))
            for py in range(iy0, iy1 + 1):
                dy0 = (py + 0.5) - ay
                row = py * bw
                for px in range(ix0, ix1 + 1):
                    dx0 = (px + 0.5) - ax
                    t = (dx0 * vx + dy0 * vy) * inv_len2
                    if t < 0.0:
                        t = 0.0
                    elif t > 1.0:
                        t = 1.0
                    rx = dx0 - vx * t
                    ry = dy0 - vy * t
                    hw = hw0 + (hw1 - hw0) * t
                    u2 = (rx * rx + ry * ry) / (hw * hw)
                    if u2 >= 1.0:
                        continue
                    w = exp(-4.0 * u2) * (1.0 - u2)
                    idx = row + px
                    if w > sw_buf[idx]:
                        zn = z0 + (z1 - z0) * t
                        bd = b0 + (b1 - b0) * t
                        lv = lv0 + (lv1 - lv0) * t
                        sf = f0 + (f1 - f0) * t
                        en = 0.56 * bd * (0.85 + 0.35 * lv) * intensity * sf * en_gain
                        cr = (1.0 * e1 + er * err) * en
                        cg = ((0.66 + 0.14 * zn) * e1 + eg * err) * en
                        cb = ((0.14 + 0.12 * max(0.0, zn)) * e1 + eb * err) * en
                        sw_buf[idx] = w
                        sr_buf[idx] = cr * w
                        sg_buf[idx] = cg * w
                        sb_buf[idx] = cb * w
        for idx in range(bw * bh):
            if sw_buf[idx] > 0.0:
                hi = idx * 3
                hdr[hi] += sr_buf[idx]
                hdr[hi + 1] += sg_buf[idx]
                hdr[hi + 2] += sb_buf[idx]


def _raster_soft_hdr(pts, x0, y0, bw, bh, intensity, err, spark_r, use_bloom, out, stride,
                     now=0.0, dev_scale=1.0, size_k=1.0, strands=()):
    """Splat round/elliptical Gaussian motes (molten gold dust, metallic micro-facet glints, 12% hot champagne
    sparkles, optional helix gold strands) into linear HDR, bloom only the brightest clusters, and tone-map
    with triangular IGN dither to clean premultiplied BGRA."""
    hdr = array("f", [0.0]) * (bw * bh * 3)
    look = devs_pack.LOOK
    dark = look["dark"]
    k_lut = _SOFT_K_LUT
    s_lut = _SOFT_SPARK_LUT
    tones = _SOFT_TONES_LIN
    er, eg, eb = _SOFT_EMBER_LIN
    e1 = 1.0 - err
    pal = [(r * e1 + er * err, g * e1 + eg * err, b * e1 + eb * err) for r, g, b in tones]
    spr0, spg0, spb0 = dark["spark_lin"]
    sp_r = spr0 * e1 + er * err
    sp_g = spg0 * e1 + eg * err
    sp_b = spb0 * e1 + eb * err
    gl_r = 1.0 * e1 + er * err
    gl_g = 0.84 * e1 + eg * err
    gl_b = 0.44 * e1 + eb * err
    en_gain = float(look.get("energy_gain", 1.22))
    sp_boost = float(look.get("sparkle_boost", 2.25))
    glint_k = float(look.get("glint_strength", 1.0))
    dither_k = float(look.get("dither_strength", 1.0))
    sqrt = math.sqrt
    sin = math.sin

    if strands:
        _raster_helix_strands_hdr(hdr, strands, x0, y0, bw, bh, intensity, err, dev_scale, size_k, en_gain)

    for gx, gy, rad, b, d_val, zi, t_idx, is_spark, tw, gid, lx_sc, ly_sc, vx_d, vy_d, stretch in pts:
        lx = gx - x0
        ly = gy - y0
        norm_b = 0.0 if b <= 0.18 else 1.0 if b >= 1.0 else (b - 0.18) / 0.82
        if is_spark:
            en = (0.72 + 0.28 * norm_b) * sp_boost * tw * d_val * intensity * en_gain
            cr, cg, cb = sp_r * en, sp_g * en, sp_b * en
        else:
            en = (0.38 + 0.50 * norm_b) * d_val * intensity * en_gain
            tr, tg, tb_c = pal[t_idx]
            if t_idx < 3 and zi != 0.0:
                tg = max(0.34, min(0.95, tg * (1.0 + 0.12 * zi)))
                tb_c = max(0.03, min(0.60, tb_c * (1.0 + 0.28 * zi)))
            cr, cg, cb = tr * en, tg * en, tb_c * en
        if glint_k > 0.0 and t_idx < 3:
            # Journey-style micro-facet metallic gold glint aligned with studio key light H = (-0.30, -0.42, 0.856).
            h1 = (((gid * 1597334677) & 0xFFFF) / 32768.0) - 1.0
            h2 = (((gid * 3812015801) & 0xFFFF) / 32768.0) - 1.0
            nx = lx_sc / 52.0 + 0.55 * h1
            ny = ly_sc / 52.0 + 0.55 * h2
            nz = max(0.05, 0.65 + 0.55 * zi) + 0.25 * sin(now * 0.9 + gid * 0.73)
            inv_n = 1.0 / (sqrt(nx * nx + ny * ny + nz * nz) or 1.0)
            ndh = (nx * (-0.30) + ny * (-0.42) + nz * 0.856) * inv_n
            if ndh > 0.55:
                spec = (ndh ** 20.0) * 1.45 * glint_k * d_val * intensity * en_gain
                cr += gl_r * spec
                cg += gl_g * spec
                cb += gl_b * spec

        if stretch > 0.01:
            r_maj = rad * (1.0 + stretch)
            r_min = rad / sqrt(1.0 + 0.50 * stretch)
            inv_maj = 1.0 / r_maj
            inv_min = 1.0 / r_min
            ix0 = max(0, int(math.floor(lx - r_maj)))
            ix1 = min(bw - 1, int(math.ceil(lx + r_maj)))
            iy0 = max(0, int(math.floor(ly - r_maj)))
            iy1 = min(bh - 1, int(math.ceil(ly + r_maj)))
            for py in range(iy0, iy1 + 1):
                dy = (py + 0.5) - ly
                row_off = py * bw
                for px in range(ix0, ix1 + 1):
                    dx = (px + 0.5) - lx
                    pa = (dx * vx_d + dy * vy_d) * inv_maj
                    pp = (-dx * vy_d + dy * vx_d) * inv_min
                    u2 = pa * pa + pp * pp
                    if u2 >= 1.0:
                        continue
                    w = k_lut[int(u2 * 255.0)]
                    idx = (row_off + px) * 3
                    hdr[idx] += cr * w
                    hdr[idx + 1] += cg * w
                    hdr[idx + 2] += cb * w
        else:
            inv_r2 = 1.0 / (rad * rad)
            ix0 = max(0, int(math.floor(lx - rad)))
            ix1 = min(bw - 1, int(math.ceil(lx + rad)))
            iy0 = max(0, int(math.floor(ly - rad)))
            iy1 = min(bh - 1, int(math.ceil(ly + rad)))
            for py in range(iy0, iy1 + 1):
                dy = (py + 0.5) - ly
                dy2 = dy * dy
                row_off = py * bw
                for px in range(ix0, ix1 + 1):
                    dx = (px + 0.5) - lx
                    u2 = (dx * dx + dy2) * inv_r2
                    if u2 >= 1.0:
                        continue
                    w = k_lut[int(u2 * 255.0)]
                    idx = (row_off + px) * 3
                    hdr[idx] += cr * w
                    hdr[idx + 1] += cg * w
                    hdr[idx + 2] += cb * w
        if is_spark:
            se = 0.28 * tw * d_val * intensity
            scr, scg, scb = sp_r * se, sp_g * se, sp_b * se
            inv_sr2 = 1.0 / (spark_r * spark_r)
            sx0 = max(0, int(math.floor(lx - spark_r)))
            sx1 = min(bw - 1, int(math.ceil(lx + spark_r)))
            sy0 = max(0, int(math.floor(ly - spark_r)))
            sy1 = min(bh - 1, int(math.ceil(ly + spark_r)))
            for py in range(sy0, sy1 + 1):
                dy = (py + 0.5) - ly
                dy2 = dy * dy
                row_off = py * bw
                for px in range(sx0, sx1 + 1):
                    dx = (px + 0.5) - lx
                    u2 = (dx * dx + dy2) * inv_sr2
                    if u2 >= 1.0:
                        continue
                    w = s_lut[int(u2 * 255.0)]
                    idx = (row_off + px) * 3
                    hdr[idx] += scr * w
                    hdr[idx + 1] += scg * w
                    hdr[idx + 2] += scb * w

    if use_bloom and "_add_kawase_bloom" in globals():
        _add_kawase_bloom(hdr, bw, bh)

    # Rich amber-to-champagne filmic tone curve + triangular IGN dither -> sRGB premultiplied BGRA.
    srgb = _SRGB_LUT
    exp = math.exp
    expo = float(look.get("tonemap_exposure", 1.52))
    hr, hg, hb = look.get("highlight_target", (1.0, 0.89, 0.54))
    hknee = float(look.get("highlight_knee", 1.55))
    hcap = float(look.get("highlight_cap", 0.48))
    dith_amp = (0.5 / 255.0) * dither_k
    for py in range(bh):
        src_row = py * bw * 3
        dst_row = py * stride
        gy_p = y0 + py
        for px in range(bw):
            si = src_row + px * 3
            r = hdr[si]
            g = hdr[si + 1]
            b = hdr[si + 2]
            if r <= 1e-4 and g <= 1e-4 and b <= 1e-4:
                continue
            y = 0.2126 * r + 0.7152 * g + 0.0722 * b
            if y <= 1e-5:
                continue
            y_tm = 1.0 - exp(-expo * y)
            t_hot = y / (y + hknee)
            hot = min(hcap, t_hot * t_hot * 0.88 if t_hot > 0.0 else 0.0)
            sc = y_tm / y
            m1 = 1.0 - hot
            lr = r * sc * m1 + hr * y_tm * hot
            lg = g * sc * m1 + hg * y_tm * hot
            lb = b * sc * m1 + hb * y_tm * hot
            if dith_amp > 0.0:
                ign = (52.9829189 * ((0.06711056 * (x0 + px) + 0.00583715 * gy_p) % 1.0)) % 1.0
                tri = ign * 2.0 - 1.0
                d_val_q = (1.0 - sqrt(1.0 - tri) if tri >= 0.0 else sqrt(1.0 + tri) - 1.0) * dith_amp
                ir = max(0, min(255, int(srgb[1023 if lr >= 1.0 else int(lr * 1023.0)] + d_val_q * 255.0 + 0.5)))
                ig = max(0, min(255, int(srgb[1023 if lg >= 1.0 else int(lg * 1023.0)] + d_val_q * 255.0 + 0.5)))
                ib = max(0, min(255, int(srgb[1023 if lb >= 1.0 else int(lb * 1023.0)] + d_val_q * 255.0 + 0.5)))
            else:
                ir = srgb[1023 if lr >= 1.0 else int(lr * 1023.0)]
                ig = srgb[1023 if lg >= 1.0 else int(lg * 1023.0)]
                ib = srgb[1023 if lb >= 1.0 else int(lb * 1023.0)]
            ia = ir if ir >= ig and ir >= ib else (ig if ig >= ib else ib)
            di = dst_row + px * 4
            out[di] = ib
            out[di + 1] = ig
            out[di + 2] = ir
            out[di + 3] = ia


def _raster_soft_light(pts, x0, y0, bw, bh, intensity, err, dev_scale, out, stride, strands=()):
    """Clean light-theme gold dust: deep burnished amber-to-copper-gold cores with optional helix bronze strands."""
    lt = devs_pack.LOOK["light"]
    sh_r, sh_g, sh_b = lt["shadow_rgb"]
    sh_ox, sh_oy = lt["shadow_offset_px"]
    sh_ox *= dev_scale
    sh_oy *= dev_scale
    sh_sc = float(lt.get("shadow_scale", 1.08))
    sh_al = float(lt.get("shadow_alpha", 0.16))
    af = lt["amber_far"]
    am = lt["amber_mid"]
    an = lt["amber_near"]
    sc_rgb = lt["sparkle_core"]
    ac_rgb = lt["accent_rgb"]

    n = bw * bh
    sh_a = array("f", [0.0]) * n
    core_r = array("f", [0.0]) * n
    core_g = array("f", [0.0]) * n
    core_b = array("f", [0.0]) * n
    core_a = array("f", [0.0]) * n
    rim_lut = _SOFT_RIM_LUT
    k_lut = _SOFT_K_LUT

    # Sort far-to-near so near bright burnished-amber grains sit cleanly over recessed far grains.
    if strands:
        exp = math.exp
        for strand in strands:
            if len(strand) < 2:
                continue
            for p0, p1 in zip(strand, strand[1:]):
                ax, ay, z0, b0, lv0, f0 = p0
                bx, by, z1, b1, lv1, f1 = p1
                if f0 <= 0.002 and f1 <= 0.002:
                    continue
                ax -= x0
                ay -= y0
                bx -= x0
                by -= y0
                vx_s, vy_s = bx - ax, by - ay
                seg_l2 = vx_s * vx_s + vy_s * vy_s
                if seg_l2 < 1e-6:
                    continue
                inv_l2 = 1.0 / seg_l2
                hw = (1.9 + 0.5 * max(z0, z1) + 0.4 * max(lv0, lv1)) * dev_scale
                ix0 = max(0, int(math.floor(min(ax, bx) - hw)))
                ix1 = min(bw - 1, int(math.ceil(max(ax, bx) + hw)))
                iy0 = max(0, int(math.floor(min(ay, by) - hw)))
                iy1 = min(bh - 1, int(math.ceil(max(ay, by) + hw)))
                for py in range(iy0, iy1 + 1):
                    dy0 = (py + 0.5) - ay
                    row_off = py * bw
                    for px in range(ix0, ix1 + 1):
                        dx0 = (px + 0.5) - ax
                        t = max(0.0, min(1.0, (dx0 * vx_s + dy0 * vy_s) * inv_l2))
                        rx, ry = dx0 - vx_s * t, dy0 - vy_s * t
                        u2 = (rx * rx + ry * ry) / (hw * hw)
                        if u2 >= 1.0:
                            continue
                        w = exp(-4.0 * u2) * (1.0 - u2)
                        sf = f0 + (f1 - f0) * t
                        a = min(0.55, 0.45 * sf * intensity * w)
                        idx = row_off + px
                        if a > core_a[idx]:
                            core_r[idx] = am[0] * a
                            core_g[idx] = am[1] * a
                            core_b[idx] = am[2] * a
                            core_a[idx] = a
    ordered = sorted(pts, key=lambda p: p[5])
    for gx, gy, rad, b, d_val, zi, t_idx, is_spark, tw, *_rest in ordered:
        lx = gx - x0
        ly = gy - y0
        norm_b = 0.0 if b <= 0.18 else 1.0 if b >= 1.0 else (b - 0.18) / 0.82
        d_cl = max(0.25, min(1.35, d_val)) * intensity

        # 1) Optional warm drop shadow (skipped completely when shadow_alpha == 0 for crisp light bronze).
        if sh_al > 0.001:
            r_sh = rad * sh_sc
            inv_rs2 = 1.0 / (r_sh * r_sh)
            a_sh = min(0.28, sh_al * (0.55 + 0.45 * norm_b) * min(1.15, d_cl))
            slx, sly = lx + sh_ox, ly + sh_oy
            ix0 = max(0, int(math.floor(slx - r_sh)))
            ix1 = min(bw - 1, int(math.ceil(slx + r_sh)))
            iy0 = max(0, int(math.floor(sly - r_sh)))
            iy1 = min(bh - 1, int(math.ceil(sly + r_sh)))
            for py in range(iy0, iy1 + 1):
                dy = (py + 0.5) - sly
                dy2 = dy * dy
                row_off = py * bw
                for px in range(ix0, ix1 + 1):
                    dx = (px + 0.5) - slx
                    u2 = (dx * dx + dy2) * inv_rs2
                    if u2 >= 1.0:
                        continue
                    a = a_sh * rim_lut[int(u2 * 255.0)]
                    idx = row_off + px
                    sh_a[idx] = a + sh_a[idx] * (1.0 - a)

        # 2) Clean burnished amber-to-copper-gold core (warm red-amber hue, never olive).
        r_core = rad * 1.02
        inv_rc2 = 1.0 / (r_core * r_core)
        a_core = min(0.98, (0.58 + 0.38 * norm_b + (0.18 if is_spark else 0.0)) * min(1.25, 0.55 + 0.55 * d_cl))
        if t_idx == 3:
            cr, cg, cb = ac_rgb
        elif is_spark:
            cr, cg, cb = sc_rgb
        else:
            # Depth + tone ramp from deep burnished amber (far) through copper-gold (mid) to sunlit honey (near).
            u_z = max(0.0, min(1.0, 0.5 + 0.45 * zi + 0.12 * (t_idx - 1)))
            if u_z < 0.5:
                f = u_z * 2.0
                cr = af[0] + (am[0] - af[0]) * f
                cg = af[1] + (am[1] - af[1]) * f
                cb = af[2] + (am[2] - af[2]) * f
            else:
                f = (u_z - 0.5) * 2.0
                cr = am[0] + (an[0] - am[0]) * f
                cg = am[1] + (an[1] - am[1]) * f
                cb = am[2] + (an[2] - am[2]) * f
        if err > 0.0:
            cr = cr * (1.0 - err) + 0.70 * err
            cg = cg * (1.0 - err) + 0.18 * err
            cb = cb * (1.0 - err) + 0.10 * err
        cx0 = max(0, int(math.floor(lx - r_core)))
        cx1 = min(bw - 1, int(math.ceil(lx + r_core)))
        cy0 = max(0, int(math.floor(ly - r_core)))
        cy1 = min(bh - 1, int(math.ceil(ly + r_core)))
        for py in range(cy0, cy1 + 1):
            dy = (py + 0.5) - ly
            dy2 = dy * dy
            row_off = py * bw
            for px in range(cx0, cx1 + 1):
                dx = (px + 0.5) - lx
                u2 = (dx * dx + dy2) * inv_rc2
                if u2 >= 1.0:
                    continue
                a = a_core * k_lut[int(u2 * 255.0)]
                idx = row_off + px
                inv = 1.0 - a
                core_r[idx] = cr * a + core_r[idx] * inv
                core_g[idx] = cg * a + core_g[idx] * inv
                core_b[idx] = cb * a + core_b[idx] * inv
                core_a[idx] = a + core_a[idx] * inv

    # Composite burnished amber core OVER faint warm chestnut shadow.
    for py in range(bh):
        row_off = py * bw
        dst_row = py * stride
        for px in range(bw):
            idx = row_off + px
            sa = sh_a[idx]
            ca = core_a[idx]
            if sa <= 1e-4 and ca <= 1e-4:
                continue
            inv_c = 1.0 - ca
            pr = core_r[idx] + sh_r * sa * inv_c
            pg = core_g[idx] + sh_g * sa * inv_c
            pb = core_b[idx] + sh_b * sa * inv_c
            pa = ca + sa * inv_c
            di = dst_row + px * 4
            out[di] = min(255, int(pb * 255.0 + 0.5))
            out[di + 1] = min(255, int(pg * 255.0 + 0.5))
            out[di + 2] = min(255, int(pr * 255.0 + 0.5))
            out[di + 3] = min(255, int(pa * 255.0 + 0.5))


def _paint_portal(cr, scene, now, centre, frame=None, leaving=None, line="", mark=False, captions=True):
    """Paint the whole viewer in one Cairo picture: black box, media, single-row edge dust, title line, and captions."""
    v = scene.view
    if v is None:
        scene.draw_swarm(cr, 0, now, centre=centre)
        return
    cx, cy = centre
    x, y, w, h, r, a = v.core(now)
    if a > 0.002:
        _rounded_rect(cr, cx + x, cy + y, w, h, r)
        cr.set_source_rgba(0, 0, 0, a)
        cr.fill()
    p = v.media_in(now)
    mx, my, mw, mh = _view_media_rect(v.media_rect(now), p)
    mr = (cx + mx, cy + my, mw, mh)
    if leaving is not None:
        gone = _smooth((now - v.morph_at) / VIEW_OUT)
        lx, ly, lw, lh = _view_media_rect(v.media_from, 1 - gone)
        _paint_media(cr, leaving, (cx + lx, cy + ly, lw, lh), 1 - gone)
    if frame is not None and p > 0.002:
        _paint_media(cr, frame, mr, p)
    if scene.dust is not None and scene.dust_vis > 0.002:
        scene._paint_grains(cr, cx, cy, *scene._dust_buckets(), 1.0)
    _paint_view_line(cr, scene, now, centre, line, mark)
    if scene.label and p > 0.002:
        scene._label(cr, cx, cy, in_view=True, fade=p)
    if captions and scene.captions and p > 0.002:
        cr.save()
        cr.translate(*_view_caption_origin(scene, now, centre))
        scene.draw_caption(cr, WIDTH, now, dim=1.0 - p)
        cr.restore()


_FRAME_GLSL = """
uniform int turn;
uniform float rr, rr_arc, per, ends[8], drift, wave, head, bottom, band;
uniform float spread, band_glow, open_el, close_el, gather_lag, gather_dur, dissolve_lag, dissolve_dur;
uniform float voice, heard[32];
uniform vec4 shape;

// Place one grain (u, pull, off, lag_frac) on the viewer's single-row edge, matching Scene._portal_places.
vec3 frame_place(vec4 point) {
    float u = point.x, pull = point.y, off = point.z, lag = point.w;
    float p_in = clamp((open_el - lag * gather_lag) / gather_dur, 0.0, 1.0);
    float g = 1.0 - pow(1.0 - p_in, 3.0);
    if (close_el >= 0.0) {
        float p_out = clamp((close_el - (1.0 - lag) * dissolve_lag) / dissolve_dur, 0.0, 1.0);
        g = min(g, 1.0 - p_out * p_out * (3.0 - 2.0 * p_out));
    }
    if (g <= 0.0) return vec3(0.0, 0.0, 0.0);
    float q = mod(u + drift, 1.0);
    float o = off * spread - band + (1.0 - g) * pull;
    float glow = (band_glow + 0.18 * cos(6.283185307 * (q - wave))) * g;
    if (turn == 1) {
        float level = pow(heard[min(31, int(abs(mod(q - bottom + 0.5, 1.0) - 0.5) * 40.0))], 1.2);
        o += 10.0 * level;
        glow *= 1.0 + 0.6 * level;
    } else if (turn == 2) {
        o += 4.0 * voice;
        glow *= 1.0 + 0.4 * voice;
    } else if (turn == 3) {
        glow *= 0.65 + exp(-mod(head - q, 1.0) * 10.0);
    }
    float sx = shape.x, sy = shape.y, sw0 = shape.z, sh0 = shape.w;
    vec2 e;
    if (rr <= 0.0) {
        if (q < ends[0]) e = vec2(sx + q * per, sy - o);
        else if (q < ends[2]) e = vec2(sx + sw0 + o, sy + (q - ends[0]) * per);
        else if (q < ends[4]) e = vec2(sx + sw0 - (q - ends[2]) * per, sy + sh0 + o);
        else e = vec2(sx - o, sy + sh0 - (q - ends[4]) * per);
    } else {
        int k = 0;
        for (int j = 0; j < 8; j++) if (ends[j] <= q) k = j + 1;
        k = min(7, k);
        float s = (q - (k > 0 ? ends[k - 1] : 0.0)) * per;
        if (k == 0) e = vec2(sx + rr + s, sy - o);
        else if (k == 2) e = vec2(sx + sw0 + o, sy + rr + s);
        else if (k == 4) e = vec2(sx + sw0 - rr - s, sy + sh0 + o);
        else if (k == 6) e = vec2(sx - o, sy + sh0 - rr - s);
        else {
            float a = -1.5707963268 + float(k / 2) * 1.5707963268 + (rr_arc > 0.0 ? s / rr_arc : 0.0);
            vec2 n = vec2(cos(a), sin(a));
            vec2 c = vec2((k == 1 || k == 3) ? sx + sw0 - rr : sx + rr, (k == 1 || k == 7) ? sy + rr : sy + sh0 - rr);
            e = c + rr * n + n * o;
        }
    }
    return vec3(e, glow);
}
"""

_DUST_VERT = """#version 430 core
layout(location = 0) in vec4 a0;  // The frame's dust: u, lane, off, depth. The swarm: x, y, depth, 0.
layout(location = 1) in vec4 a1;  // The frame's dust: freq, phase of x, phase of y, base. The swarm: 0, 0, 0, base.
layout(location = 2) in vec3 a2;  // size, tone, blue rank
uniform int mode, spark, twins;
uniform float k, share, grow, t, scale;
uniform vec4 regions[4], clips[4];  // Each strip in scene coordinates, and where it lies in the atlas, in pixels.
uniform vec2 origins[4], twin, size_px;  // The scene's origin in the atlas, for each strip.
flat out vec4 clip;
flat out vec2 centre;
flat out float half_size;
flat out int group;
""" + _FRAME_GLSL + """
// The frame's own dust, with its fine shimmer.
vec3 frame_dust() {
    vec3 p = frame_place(a0);
    return vec3(p.xy + 0.5 * vec2(sin(t * a1.x + a1.y), cos(t * a1.x * 1.3 + a1.z)), p.z);
}

void main() {
    vec3 p = mode == 0 ? frame_dust() : a0.xyz;
    float base = a1.w;
    int level = int(base * p.z * k);
    int r = 4;
    for (int j = 3; j >= 0; j--)
        if (regions[j].x <= p.x && p.x < regions[j].z && regions[j].y <= p.y && p.y < regions[j].w) r = j;
    // The fill this grain belongs to: 4 colours by 7 levels, then the sparks (29 total).
    group = spark == 1 ? 28 : (a2.z < share ? 3 : int(a2.y)) * 7 + min(7, level) - 1;
    centre = origins[min(r, 3)] + p.xy * scale;
    clip = clips[min(r, 3)];
    half_size = 0.5 * (spark == 1 ? 3.6 : a2.x * grow) * scale;
    vec2 corner = vec2(gl_VertexID & 1, gl_VertexID >> 1);
    vec2 reach_px = vec2(half_size + 1.0) + (twins == 1 ? abs(twin) : vec2(0.0));
    gl_Position = vec4((centre + (corner * 2.0 - 1.0) * reach_px) / size_px * 2.0 - 1.0, 0.0, 1.0);
    if (level <= 0 || r == 4 || (spark == 1 && base <= 0.85)) gl_Position = vec4(-2.0, -2.0, 0.0, 1.0);
}
"""

_DUST_FRAG = """#version 430 core
flat in vec4 clip;
flat in vec2 centre;
flat in float half_size;
flat in int group;
uniform vec2 twin;
uniform int twins;
uniform int capacity;
layout(std430, binding = 0) buffer Count { uint used; };
layout(std430, binding = 1) buffer Nodes { uvec4 node[]; };
layout(r32ui, binding = 0) uniform coherent uimage2D firsts;

// The part of this pixel that a square covers, kept in the pixel's list with the square's fill, for _RESOLVE_FRAG.
void keep(vec2 lo, vec2 hi, vec2 pixel) {
    vec2 a = max(lo, max(pixel, clip.xy)), b = min(hi, min(pixel + 1.0, clip.zw));
    if (b.x <= a.x || b.y <= a.y) return;
    uint i = atomicAdd(used, 1u);
    if (i >= uint(capacity)) return;
    uint next = imageAtomicExchange(firsts, ivec2(pixel), i);
    node[i] = uvec4(packHalf2x16(a - pixel), packHalf2x16(b - pixel), uint(group), next);
}

void main() {
    vec2 pixel = floor(gl_FragCoord.xy), lo = centre - half_size, hi = centre + half_size;
    keep(lo, hi, pixel);
    if (twins == 1) keep(lo + twin, hi + twin, pixel);
}
"""

_SPRING_COMP = """#version 430 core
layout(local_size_x = 64) in;
struct Spring { vec4 pos; vec4 spring; vec4 more; };
// pos: x, y, vx, vy. spring: omega, freq, phase of x, phase of y. more: delay, curl, when its spring is loose again
// (seconds from the epoch), and the grain's index in the swarm.
layout(std430, binding = 2) buffer Springs { Spring grain[]; };
layout(std430, binding = 3) buffer Rows { float row[]; };  // Instance rows for _DUST_VERT, 11 floats each.
layout(std430, binding = 4) buffer Kicks { vec4 kick[]; };  // instance, dvx, dvy, loose until
layout(std430, binding = 5) buffer Targets { vec4 target[]; };  // x, y, glow, straight per grain; then the old form's
uniform float now_t, dt, pace, cohesion, jitter, extra, start_t, dscale;
uniform int steps, count, kicks, rest_every, has_old, unloose;
// Scene._move: each grain's spring pulls it to its target, after its own delay (the old form's target until then),
// along a slight curve at first, with its own shimmer of jitter; a grain kicked loose has a weak spring for a while.
void main() {
    uint i = gl_GlobalInvocationID.x;
    if (i >= uint(count)) return;
    Spring g = grain[i];
    if (unloose == 1) g.more.z = -1e9;  // A new form: no grain is loose (Scene.step).
    for (int j = 0; j < kicks; j++)
        if (uint(kick[j].x) == i) { g.pos.zw += kick[j].yz; g.more.z = kick[j].w; }
    float since = now_t - start_t - g.more.x * dscale;
    vec4 goal = has_old == 1 && since < 0.0 ? target[uint(count) + i] : target[i];
    float w = g.spring.x * cohesion * pace;
    float k = w * w * (g.more.z > now_t ? 0.03 : 1.0);
    float bend = since > 0.0 && since < 0.5 / pace && goal.w < 1.5 ? g.more.y * k * 0.5 * (1.0 - since * 2.0 * pace)
                                                                   : 0.0;  // w >= 1.5 is a grain that flies straight.
    vec2 jit = jitter * vec2(sin(now_t * g.spring.y + g.spring.z), cos(2.0 * now_t * g.spring.y + g.spring.w));
    for (int n = 0; n < steps; n++) {
        vec2 d = goal.xy - g.pos.xy;
        vec2 a = k * d - 1.1 * w * g.pos.zw + bend * vec2(-d.y, d.x) + jit;
        g.pos.zw += a * dt;
        g.pos.xy += g.pos.zw * dt;
    }
    grain[i] = g;
    uint index = uint(g.more.w);
    row[i * 11u] = g.pos.x;
    row[i * 11u + 1u] = g.pos.y;
    row[i * 11u + 2u] = goal.z * (index % uint(rest_every) == 0u ? 1.0 : extra);  // As draw_swarm dims it.
    float target_z = goal.w < 1.5 ? goal.w : 0.0;
    float zg = 1.0 - exp(-dt * float(steps) / 0.14);
    row[i * 11u + 3u] = mix(row[i * 11u + 3u], target_z, zg);
    row[i * 11u + 4u] = g.pos.z;
    row[i * 11u + 5u] = g.pos.w;
}
"""

_TIME_WRAP = 40.0 * math.pi  # Seamless common period for twinkle (1.55 -> 31 cycles) and glint (0.90 -> 18 cycles).


def _build_soft_shaders(look):
    """Build live GLSL soft-grain, Kawase bloom, and warm-gold tonemap shaders directly from devs_pack.LOOK."""
    dk = look["dark"]
    t0, t1, t2 = dk["tones_lin"]
    acc = dk["accent_lin"]
    emb = dk["ember_lin"]
    spk = dk["spark_lin"]
    lt = look["light"]
    laf, lam, lan = lt["amber_far"], lt["amber_mid"], lt["amber_near"]
    lsc, lac = lt["sparkle_core"], lt["accent_rgb"]
    lsh_rgb = lt.get("shadow_rgb", (0.34, 0.20, 0.06))
    lsh_off = lt.get("shadow_offset_px", (0.70, 0.90))
    lsh_sc = float(lt.get("shadow_scale", 1.08))
    lsh_al = float(lt.get("shadow_alpha", 0.16))
    l_gain = float(lt.get("size_gain", 1.32))
    bt = look.get("bloom_tint", (1.0, 0.78, 0.30))
    ht = look.get("highlight_target", (1.0, 0.89, 0.54))
    sp_cut = int(round(float(look.get("sparkle_fraction", 0.12)) * 100))
    soft_vert = f"""#version 430 core
layout(location = 0) in vec4 a0;  // x, y, depth_bright, z_norm
layout(location = 1) in vec4 a1;  // vx, vy, rad_override, base
layout(location = 2) in vec3 a2;  // size, tone, blue rank
uniform int spark, light_mode, color_set;
uniform float intensity, share, grow, size_k, scale, err, u_time, glint_k, streak_k;
uniform vec2 origin, size_px;
out vec2 v_uv;
flat out vec3 v_col;
flat out float v_alpha;
void main() {{
    float b = a1.w;
    float d_val = a0.z;
    uint gid = uint(gl_InstanceID);
    bool is_spark = ((gid * 2654435761u) % 100u) < {sp_cut}u;
    if (d_val <= 0.002 || (spark == 1 && (!is_spark || light_mode > 0))) {{
        gl_Position = vec4(-2.0, -2.0, 0.0, 1.0);
        v_uv = vec2(0.0);
        v_col = vec3(0.0);
        v_alpha = 0.0;
        return;
    }}
    float zi = clamp(a0.w, -1.0, 1.0);
    float tw = is_spark ? (0.68 + 0.56 * (0.5 + 0.5 * sin(u_time * {float(look.get("twinkle_rate", 1.55)):.4f} + float(gid) * 1.6180339887))) : 1.0;
    float rad;
    vec3 col;
    float alpha = 1.0;
    vec2 l_off = vec2(0.0);
    vec3 ember = vec3({emb[0]:.4f}, {emb[1]:.4f}, {emb[2]:.4f});
    vec3 sp_col = color_set == 1 ? vec3(0.96, 0.90, 1.00) : mix(vec3({spk[0]:.4f}, {spk[1]:.4f}, {spk[2]:.4f}), ember, err);
    float stretch = 0.0;
    vec2 vdir = vec2(1.0, 0.0);
    if (spark == 1) {{
        rad = {float(look.get("spark_radius_px", 3.5)):.4f} * scale * min(1.0, size_k);
        col = sp_col * (0.28 * tw * d_val * intensity);
    }} else {{
        float d_nom = ({float(look.get("sprite_base_px", 2.70)):.4f} + {float(look.get("sprite_span_px", 1.55)):.4f} * b) * grow * size_k * (is_spark ? 1.08 : 1.0);
        float d_floor = (zi < -0.15 ? {float(look.get("sprite_far_floor_px", 2.15)):.4f} : {float(look.get("sprite_floor_px", 2.75)):.4f}) * min(1.0, size_k);
        rad = a1.z > 0.0 ? a1.z * scale : 0.5 * max(d_floor, d_nom * (1.0 + {float(look.get("depth_size_gain", 0.28)):.4f} * zi)) * scale;
        float norm_b = clamp((b - 0.18) / 0.82, 0.0, 1.0);
        float blue_cut = light_mode > 0 ? 0.0 : min(share, {float(look.get("blue_max_share", 0.02)):.4f});
        int t = a2.z < blue_cut ? 3 : int(a2.y);
        if (light_mode == 2 && color_set == 0) {{
            // Warm chestnut drop shadow pass for light theme (matches _raster_soft_light).
            rad *= {l_gain * lsh_sc:.4f};
            float d_cl = clamp(d_val, 0.25, 1.35) * intensity;
            alpha = min(0.28, {lsh_al:.4f} * (0.55 + 0.45 * norm_b) * min(1.15, d_cl));
            col = vec3({lsh_rgb[0]:.4f}, {lsh_rgb[1]:.4f}, {lsh_rgb[2]:.4f});
            l_off = vec2({float(lsh_off[0]):.4f}, {float(lsh_off[1]):.4f}) * scale;
        }} else if (light_mode == 1 && color_set == 0) {{
            rad *= {l_gain * 1.02:.4f};
            float d_cl = clamp(d_val, 0.25, 1.35) * intensity;
            alpha = clamp((0.58 + 0.38 * norm_b + (is_spark ? 0.18 : 0.0)) * min(1.25, 0.55 + 0.55 * d_cl), 0.0, 0.98);
            if (t == 3) {{
                col = vec3({lac[0]:.4f}, {lac[1]:.4f}, {lac[2]:.4f});
            }} else if (is_spark) {{
                col = vec3({lsc[0]:.4f}, {lsc[1]:.4f}, {lsc[2]:.4f});
            }} else {{
                float u_z = clamp(0.5 + 0.45 * zi + 0.12 * (float(t) - 1.0), 0.0, 1.0);
                vec3 c_far = vec3({laf[0]:.4f}, {laf[1]:.4f}, {laf[2]:.4f});
                vec3 c_mid = vec3({lam[0]:.4f}, {lam[1]:.4f}, {lam[2]:.4f});
                vec3 c_near = vec3({lan[0]:.4f}, {lan[1]:.4f}, {lan[2]:.4f});
                col = u_z < 0.5 ? mix(c_far, c_mid, u_z * 2.0) : mix(c_mid, c_near, (u_z - 0.5) * 2.0);
            }}
            col = mix(col, vec3(0.70, 0.18, 0.10), err);
        }} else if (color_set == 1) {{
            // Nova plasma stand-in (violet, pink, white-lavender core, cyan) until forge dispatch flipbook lands.
            int nt = int(gid % 4u);
            col = nt == 0 ? vec3(0.32, 0.10, 0.98)
                : nt == 1 ? vec3(0.95, 0.14, 0.72)
                : nt == 2 ? vec3(0.95, 0.88, 1.00)
                : vec3(0.10, 0.80, 0.98);
            col *= (0.45 + 0.55 * norm_b) * d_val * intensity * 1.15;
        }} else {{
            float en_gain = {float(look.get("energy_gain", 1.22)):.4f};
            if (is_spark) {{
                col = sp_col * ((0.72 + 0.28 * norm_b) * {float(look.get("sparkle_boost", 2.25)):.4f} * tw * d_val * intensity * en_gain);
            }} else {{
                col = t == 3 ? vec3({acc[0]:.4f}, {acc[1]:.4f}, {acc[2]:.4f})
                    : t == 0 ? vec3({t0[0]:.4f}, {t0[1]:.4f}, {t0[2]:.4f})
                    : t == 1 ? vec3({t1[0]:.4f}, {t1[1]:.4f}, {t1[2]:.4f})
                    : vec3({t2[0]:.4f}, {t2[1]:.4f}, {t2[2]:.4f});
                col = mix(col, ember, err);
                if (t < 3 && zi != 0.0) {{
                    col.g = clamp(col.g * (1.0 + 0.12 * zi), 0.34, 0.95);
                    col.b = clamp(col.b * (1.0 + 0.28 * zi), 0.03, 0.60);
                }}
                col *= (0.38 + 0.50 * norm_b) * d_val * intensity * en_gain;
            }}
            if (glint_k > 0.0 && (is_spark || t < 3)) {{
                float h1 = float((gid * 1597334677u) & 65535u) / 32768.0 - 1.0;
                float h2 = float((gid * 3812015801u) & 65535u) / 32768.0 - 1.0;
                vec3 nrm = normalize(vec3(a0.x / 52.0 + 0.55 * h1, a0.y / 52.0 + 0.55 * h2,
                                          max(0.05, 0.65 + 0.55 * zi) + 0.25 * sin(u_time * 0.9 + float(gid) * 0.73)));
                float ndh = dot(nrm, vec3(-0.30, -0.42, 0.856));
                if (ndh > 0.55) {{
                    vec3 glint_col = mix(vec3(1.0, 0.84, 0.44), ember, err);
                    col += glint_col * (pow(ndh, 20.0) * 1.45 * glint_k * d_val * intensity * en_gain);
                }}
            }}
        }}
        float spd = length(a1.xy);
        if (streak_k > 0.0 && spd > 18.0 && a1.z <= 8.0) {{
            stretch = min(1.35, ((spd - 18.0) / 145.0) * streak_k);
            vdir = a1.xy / spd;
        }}
    }}
    vec2 corner = vec2(gl_VertexID & 1, gl_VertexID >> 1) * 2.0 - 1.0;
    vec2 centre = origin + a0.xy * scale + l_off;
    float r_maj = rad * (1.0 + stretch);
    float r_min = rad / sqrt(1.0 + 0.50 * stretch);
    vec2 vperp = vec2(-vdir.y, vdir.x);
    vec2 offs = vdir * (corner.x * (r_maj + 0.5)) + vperp * (corner.y * (r_min + 0.5));
    gl_Position = vec4((centre + offs) / size_px * 2.0 - 1.0, 0.0, 1.0);
    v_uv = vec2(corner.x * ((r_maj + 0.5) / r_maj), corner.y * ((r_min + 0.5) / r_min));
    v_col = col;
    v_alpha = alpha;
}}
"""
    soft_frag = f"""#version 430 core
in vec2 v_uv;
flat in vec3 v_col;
flat in float v_alpha;
uniform int spark, light_mode;
out vec4 result;
void main() {{
    float u2 = dot(v_uv, v_uv);
    if (u2 >= 1.0) discard;
    if (light_mode == 2) {{
        float w = (1.0 - u2) * (1.0 - u2);
        float a = clamp(v_alpha * w, 0.0, 1.0);
        result = vec4(v_col * a, a);
    }} else if (light_mode == 1) {{
        float w = exp(-{float(look.get("gaussian_k", 3.95)):.4f} * u2) * (1.0 - u2);
        float a = clamp(v_alpha * w, 0.0, 1.0);
        result = vec4(v_col * a, a);
    }} else {{
        float w = exp((spark == 1 ? -{float(look.get("spark_k", 3.4)):.4f} : -{float(look.get("gaussian_k", 3.95)):.4f}) * u2) * (1.0 - u2);
        result = vec4(v_col * w, 0.0);
    }}
}}
"""
    kawase_down = f"""#version 430 core
uniform sampler2D src_tex;
uniform vec2 half_px;
uniform int soft_knee;
out vec4 result;
void main() {{
    vec2 uv = gl_FragCoord.xy / vec2(textureSize(src_tex, 0)) * 2.0;
    vec3 c = texture(src_tex, uv).rgb * 4.0
           + texture(src_tex, uv - half_px).rgb
           + texture(src_tex, uv + half_px).rgb
           + texture(src_tex, uv + vec2(half_px.x, -half_px.y)).rgb
           + texture(src_tex, uv + vec2(-half_px.x, half_px.y)).rgb;
    c *= 0.125;
    if (soft_knee == 1) {{
        float lum = dot(c, vec3(0.2126, 0.7152, 0.0722));
        float ex = max(0.0, lum - {float(look.get("bloom_threshold", 0.46)):.4f});
        c *= ex > 0.0 ? ex / (ex + {float(look.get("bloom_knee", 0.34)):.4f}) : 0.0;
    }}
    result = vec4(c, 1.0);
}}
"""
    tonemap = f"""#version 430 core
uniform sampler2D hdr_tex;
uniform sampler2D bloom_tex;
uniform sampler2D under;
uniform int has_bloom, has_under, nova_tm;
uniform float bloom_strength, dither_k;
uniform vec2 under_at;
out vec4 result;
float lin2srgb(float c) {{
    c = clamp(c, 0.0, 1.0);
    return c <= 0.0031308 ? 12.92 * c : 1.055 * pow(c, 1.0 / 2.4) - 0.055;
}}
void main() {{
    ivec2 ip = ivec2(gl_FragCoord.xy);
    vec2 uv = gl_FragCoord.xy / vec2(textureSize(hdr_tex, 0));
    vec3 rgb = texelFetch(hdr_tex, ip, 0).rgb;
    vec3 btint = nova_tm == 1 ? vec3(0.75, 0.52, 1.00) : vec3({bt[0]:.4f}, {bt[1]:.4f}, {bt[2]:.4f});
    if (has_bloom == 1) rgb += bloom_strength * btint * texture(bloom_tex, uv).rgb;
    vec4 s = vec4(0.0);
    if (has_under == 1) {{
        vec2 p = gl_FragCoord.xy - under_at - 0.5, f = fract(p);
        ivec2 q = ivec2(floor(p)), sz = textureSize(under, 0);
        vec4 t0 = all(greaterThanEqual(q, ivec2(0))) && all(lessThan(q, sz)) ? texelFetch(under, q, 0) : vec4(0.0);
        vec4 t1 = all(greaterThanEqual(q + ivec2(1, 0), ivec2(0))) && all(lessThan(q + ivec2(1, 0), sz)) ? texelFetch(under, q + ivec2(1, 0), 0) : vec4(0.0);
        vec4 t2 = all(greaterThanEqual(q + ivec2(0, 1), ivec2(0))) && all(lessThan(q + ivec2(0, 1), sz)) ? texelFetch(under, q + ivec2(0, 1), 0) : vec4(0.0);
        vec4 t3 = all(greaterThanEqual(q + ivec2(1, 1), ivec2(0))) && all(lessThan(q + ivec2(1, 1), sz)) ? texelFetch(under, q + ivec2(1, 1), 0) : vec4(0.0);
        s = mix(mix(t0, t1, f.x), mix(t2, t3, f.x), f.y);
    }}
    float y = dot(rgb, vec3(0.2126, 0.7152, 0.0722));
    vec4 g = vec4(0.0);
    if (y > 1e-5) {{
        float y_tm = 1.0 - exp(-{float(look.get("tonemap_exposure", 1.52)):.4f} * y);
        float t_hot = y / (y + {float(look.get("highlight_knee", 1.55)):.4f});
        float hot = min({float(look.get("highlight_cap", 0.48)):.4f}, t_hot * t_hot * 0.88);
        vec3 htarg = nova_tm == 1 ? vec3(1.00, 0.94, 1.00) : vec3({ht[0]:.4f}, {ht[1]:.4f}, {ht[2]:.4f});
        vec3 lin = rgb * (y_tm / y) * (1.0 - hot) + htarg * (y_tm * hot);
        vec3 sr = vec3(lin2srgb(lin.r), lin2srgb(lin.g), lin2srgb(lin.b));
        if (dither_k > 0.0) {{
            float ign = fract(52.9829189 * fract(dot(floor(gl_FragCoord.xy), vec2(0.06711056, 0.00583715))));
            float tri = ign * 2.0 - 1.0;
            float dq = sign(tri) * (1.0 - sqrt(1.0 - abs(tri))) * (0.5 / 255.0) * dither_k;
            sr = clamp(sr + vec3(dq), 0.0, 1.0);
        }}
        g = vec4(sr, max(sr.r, max(sr.g, sr.b)));
    }}
    result = g + s * (1.0 - g.a);
}}
"""
    return soft_vert, soft_frag, kawase_down, tonemap


_SOFT_VERT, _SOFT_FRAG, _KAWASE_DOWN_FRAG, _TONEMAP_FRAG = _build_soft_shaders(devs_pack.LOOK)

_STRAND_VERT = """#version 430 core
layout(location = 0) in vec4 a_pos_uv;  // screen_x, screen_y, across (-1..+1), alpha_mul
layout(location = 1) in vec3 a_col;     // linear HDR gold or sRGB Nova plasma color
uniform vec2 size_px;
out float v_across;
out float v_alpha;
out vec3 v_col;
void main() {
    gl_Position = vec4(a_pos_uv.xy / size_px * 2.0 - 1.0, 0.0, 1.0);
    v_across = a_pos_uv.z;
    v_alpha = a_pos_uv.w;
    v_col = a_col;
}
"""

_STRAND_FRAG = """#version 430 core
in float v_across;
in float v_alpha;
in vec3 v_col;
uniform int light_mode;
out vec4 result;
void main() {
    float u2 = v_across * v_across;
    if (u2 >= 1.0) discard;
    if (light_mode == 2) {
        // Crisp anti-aliased premultiplied ribbon (Nova plasma core, ink underlay, marching beads).
        float a = smoothstep(1.0, 0.45, abs(v_across)) * v_alpha;
        result = vec4(v_col * a, a);
    } else if (light_mode == 3) {
        // Soft Gaussian premultiplied glow ribbon (Nova outer plasma halo).
        float a = exp(-3.5 * u2) * (1.0 - u2) * v_alpha;
        result = vec4(v_col * a, a);
    } else {
        float w = exp(-4.0 * u2) * (1.0 - u2);
        if (light_mode == 1) {
            float a = clamp(0.45 * w, 0.0, 1.0);
            result = vec4(v_col * a, a);
        } else {
            result = vec4(v_col * w, 0.0);
        }
    }
}
"""

# A constellation's filament layer (filament.py): one quad over the drawing's texture, whose texels say each pixel's
# core and ink coverage, how far along its stroke it lies, and its element. The element's state comes per frame as
# three vec4 uniforms (Constellation.lines). mode 0 adds the glow into the HDR frame for the bloom, mode 1 puts the
# ink edge under what is drawn, mode 2 draws the cores over it.
_FILAMENT_VERT = """#version 430 core
uniform vec4 rect;  // The texture's left, top, width and height in device pixels.
uniform vec2 size_px;
void main() {
    vec2 corner = vec2(gl_VertexID & 1, gl_VertexID >> 1);
    gl_Position = vec4((rect.xy + corner * rect.zw) / size_px * 2.0 - 1.0, 0.0, 1.0);
}
"""
_FILAMENT_FRAG = f"""#version 430 core
uniform sampler2D art;
uniform vec4 rect, hot_rgb;
uniform int mode;
uniform float amount;  // Of the glow: all of it before the bloom, then most of it taken back (see _draw_soft_hdr).
uniform vec4 fa[{filament.MAX_ELEMENTS}], fb[{filament.MAX_ELEMENTS}], fc[{filament.MAX_ELEMENTS}];
out vec4 result;
void main() {{
    vec4 t = texelFetch(art, ivec2(gl_FragCoord.xy - rect.xy), 0);
    int e = int(t.a * 255.0 + 0.5) - 1;
    if (e < 0) discard;
    vec4 a = fa[e], b = fb[e], c = fc[e];  // See Constellation.lines for the twelve values.
    float s = t.b;
    if (b.x <= 0.001 || s > b.x + 0.003) discard;  // Not drawn on yet.
    bool hot = b.y > 0.0 && (b.z > 0.5 ? 1.0 - s : s) <= b.y + 0.003;
    vec3 col = hot ? hot_rgb.rgb : a.rgb;
    float alpha = hot ? c.z : a.a, glow = hot ? c.w : b.w;
    if (c.y > 0.5 && s >= b.x - 0.05) {{  // The pen of light at the tip of a line that draws on.
        col = hot_rgb.rgb;
        alpha = max(alpha, c.z);
        glow = max(glow, c.w);
    }}
    if (mode == 0) {{
        result = vec4(vec3({filament.GLOW_LIN[0]:.4f}, {filament.GLOW_LIN[1]:.4f}, {filament.GLOW_LIN[2]:.4f})
                      * ({filament.GLOW_K:.4f} * glow * t.g * amount), 0.0);
    }} else if (mode == 1) {{
        float k = t.g * min(0.55, 0.6 * alpha);
        result = vec4(vec3({filament.INK[0]:.4f}, {filament.INK[1]:.4f}, {filament.INK[2]:.4f}) * k, k);
    }} else {{
        float k = t.r * min(1.0, alpha);
        result = vec4(col * k, k);
    }}
}}
"""

_KAWASE_UP_FRAG = """#version 430 core
uniform sampler2D src_tex;
uniform sampler2D tap_tex;
uniform vec2 half_px;
uniform float mix_tap;
out vec4 result;
void main() {
    vec2 uv = gl_FragCoord.xy * half_px;
    vec3 c = texture(src_tex, uv + vec2(-half_px.x * 2.0, 0.0)).rgb
           + texture(src_tex, uv + vec2(half_px.x * 2.0, 0.0)).rgb
           + texture(src_tex, uv + vec2(0.0, -half_px.y * 2.0)).rgb
           + texture(src_tex, uv + vec2(0.0, half_px.y * 2.0)).rgb
           + (texture(src_tex, uv + vec2(-half_px.x, -half_px.y)).rgb
            + texture(src_tex, uv + vec2(half_px.x, -half_px.y)).rgb
            + texture(src_tex, uv + vec2(-half_px.x, half_px.y)).rgb
            + texture(src_tex, uv + vec2(half_px.x, half_px.y)).rgb) * 2.0;
    c /= 12.0;
    if (mix_tap > 0.0) c = mix(c, texture(tap_tex, uv).rgb, mix_tap);
    result = vec4(c, 1.0);
}
"""

# Flipbook theme pack atlas player (FORMAT.md): one textured quad per live layer/sprite, premultiplied alpha.
_ATLAS_VERT = """#version 430 core
uniform vec2 u_origin;     // icon/sprite centre in device pixels
uniform vec2 u_viewport;   // FBO width, height in device pixels
uniform vec2 u_pivot;      // normalized pivot inside cell (default 0.5, 0.5)
uniform vec2 u_grid;       // atlas [cols, rows]
uniform vec2 u_cell_xy;    // cell [col, row]
uniform vec2 u_quad_size;  // drawn quad [width, height] in device pixels (supports stretch)
uniform float u_angle;     // rotation in radians around pivot (0 for icons, tangent angle for sprites)
out vec2 v_uv;
void main() {
    vec2 corner = vec2(gl_VertexID & 1, gl_VertexID >> 1);
    vec2 local = (corner - u_pivot) * u_quad_size;
    float ca = cos(u_angle), sa = sin(u_angle);
    vec2 rot = vec2(local.x * ca - local.y * sa, local.x * sa + local.y * ca);
    vec2 screen = u_origin + rot;
    gl_Position = vec4(screen / u_viewport * 2.0 - 1.0, 0.0, 1.0);
    v_uv = (u_cell_xy + corner) / u_grid;
}
"""

_ATLAS_FRAG = """#version 430 core
in vec2 v_uv;
uniform sampler2D u_atlas;
uniform float u_alpha;
out vec4 result;
void main() {
    vec4 c = texture(u_atlas, v_uv);
    result = vec4(c.rgb * c.a, c.a) * u_alpha;
}
"""

_RESOLVE_VERT = """#version 430 core
void main() { gl_Position = vec4(vec2(gl_VertexID & 1, gl_VertexID >> 1) * 4.0 - 1.0, 0.0, 1.0); }
"""

_RESOLVE_FRAG = """#version 430 core
layout(std430, binding = 1) buffer Nodes { uvec4 node[]; };
layout(r32ui, binding = 0) uniform uimage2D firsts;
uniform vec4 colour[29];  // Each fill's colour times its alpha, and its alpha, in eight bits (0 to 255).
uniform int add[29];      // 1 where the fill adds light, 0 where it paints over.
uniform sampler2D under;  // What Cairo paints before the grains (the resting scrim), when has_under is 1.
uniform int has_under, skip_dust;
uniform vec2 under_at;    // Where its top-left corner lies, in this texture's pixels.
out vec4 result;
const int MAXN = 128;
vec4 box[MAXN];
int fill[MAXN];
float xs[2 * MAXN], y0[MAXN], y1[MAXN];

// The area of the pixel that the squares box[a..b) cover together: their union, as one Cairo fill covers it.
float covered(int a, int b) {
    if (b - a == 1) return (box[a].z - box[a].x) * (box[a].w - box[a].y);
    int m = 0;
    for (int k = a; k < b; k++) { xs[m++] = box[k].x; xs[m++] = box[k].z; }
    for (int k = 1; k < m; k++) { float v = xs[k]; int j = k - 1; while (j >= 0 && xs[j] > v) { xs[j + 1] = xs[j]; j--; } xs[j + 1] = v; }
    float total = 0.0;
    for (int k = 0; k + 1 < m; k++) {
        float x0 = xs[k], x1 = xs[k + 1];
        if (x1 <= x0) continue;
        int c = 0;
        for (int q = a; q < b; q++)
            if (box[q].x <= x0 && box[q].z >= x1) {
                float lo = box[q].y, hi = box[q].w;
                int j = c - 1;
                while (j >= 0 && y0[j] > lo) { y0[j + 1] = y0[j]; y1[j + 1] = y1[j]; j--; }
                y0[j + 1] = lo; y1[j + 1] = hi; c++;
            }
        float length = 0.0, start = 0.0, stop = -1.0;
        for (int j = 0; j < c; j++) {
            if (y0[j] > stop) { length += max(0.0, stop - start); start = y0[j]; stop = y1[j]; }
            else stop = max(stop, y1[j]);
        }
        total += (x1 - x0) * (length + max(0.0, stop - start));
    }
    return total;
}

// Every fill that touches this pixel, in Cairo's order: the frame's dust, colour by colour and level by level, its
// sparks, then the same for the swarm's grains.
void main() {
    int n = 0;
    if (skip_dust == 0) {
        uint i = imageLoad(firsts, ivec2(gl_FragCoord.xy)).r;
        while (i != 0xFFFFFFFFu && n < MAXN) {
            uvec4 v = node[i];
            box[n] = vec4(unpackHalf2x16(v.x), unpackHalf2x16(v.y));
            fill[n] = int(v.z);
            n++;
            i = v.w;
        }
        for (int a = 1; a < n; a++) {
            vec4 b = box[a]; int g = fill[a]; int j = a - 1;
            while (j >= 0 && fill[j] > g) { box[j + 1] = box[j]; fill[j + 1] = fill[j]; j--; }
            box[j + 1] = b; fill[j + 1] = g;
        }
    }
    vec4 s = vec4(0.0);
    if (has_under == 1) {
        // Bilinear, between the image's pixel centres, as Cairo samples a surface painted at a fractional offset.
        vec2 p = gl_FragCoord.xy - under_at - 0.5, f = fract(p);
        ivec2 q = ivec2(floor(p)), size = textureSize(under, 0);
        vec4 t[4];
        for (int k = 0; k < 4; k++) {
            ivec2 c = q + ivec2(k & 1, k >> 1);
            t[k] = all(greaterThanEqual(c, ivec2(0))) && all(lessThan(c, size)) ? texelFetch(under, c, 0) : vec4(0.0);
        }
        s = mix(mix(t[0], t[1], f.x), mix(t[2], t[3], f.x), f.y);
    }
    // Each fill as pixman lays it down, in eight bits with its rounding at every step, so many fills on one pixel
    // add up as Cairo's do: the fill's colour, already eight bits (see _DustGL._fills), times the pixel's coverage.
    uvec4 d = uvec4(round(s * 255.0));
    int a = 0;
    while (a < n) {
        int g = fill[a], b = a;
        while (b < n && fill[b] == g) b++;
        uint m = uint(round(clamp(covered(a, b), 0.0, 1.0) * 255.0));
        uvec4 v = uvec4(colour[g]) * m + 128u;
        v = (v + (v >> 8u)) >> 8u;
        if (add[g] == 1) {
            d = min(d + v, uvec4(255u));
        } else {
            uvec4 k = d * (255u - v.a) + 128u;
            d = v + ((k + (k >> 8u)) >> 8u);
        }
        a = b;
    }
    result = vec4(d) / 255.0;
}
"""


def _gl_functions():
    """The GL calls _DustGL makes, through ctypes on glvnd's libOpenGL."""
    lib = ctypes.CDLL("libOpenGL.so.0")
    u, i, f, p, n = ctypes.c_uint, ctypes.c_int, ctypes.c_float, ctypes.c_void_p, ctypes.c_ssize_t
    table = {
        "glCreateShader": (u, u), "glShaderSource": (None, u, i, ctypes.POINTER(ctypes.c_char_p), p),
        "glCompileShader": (None, u), "glGetShaderiv": (None, u, u, ctypes.POINTER(i)),
        "glGetShaderInfoLog": (None, u, i, p, ctypes.c_char_p), "glCreateProgram": (u,),
        "glAttachShader": (None, u, u), "glLinkProgram": (None, u), "glGetProgramiv": (None, u, u, ctypes.POINTER(i)),
        "glGetProgramInfoLog": (None, u, i, p, ctypes.c_char_p), "glUseProgram": (None, u),
        "glGetUniformLocation": (i, u, ctypes.c_char_p), "glUniform1i": (None, i, i), "glUniform1f": (None, i, f),
        "glUniform2f": (None, i, f, f), "glUniform4f": (None, i, f, f, f, f),
        "glUniform2fv": (None, i, i, ctypes.POINTER(f)),
        "glUniform1fv": (None, i, i, ctypes.POINTER(f)), "glUniform4fv": (None, i, i, ctypes.POINTER(f)),
        "glUniform1iv": (None, i, i, ctypes.POINTER(i)), "glGenBuffers": (None, i, ctypes.POINTER(u)),
        "glBindBuffer": (None, u, u), "glBufferData": (None, u, n, p, u), "glGenVertexArrays": (None, i, ctypes.POINTER(u)),
        "glBindVertexArray": (None, u), "glEnableVertexAttribArray": (None, u),
        "glVertexAttribPointer": (None, u, i, u, ctypes.c_ubyte, i, p), "glVertexAttribDivisor": (None, u, u),
        "glGenTextures": (None, i, ctypes.POINTER(u)), "glDeleteTextures": (None, i, ctypes.POINTER(u)),
        "glBindTexture": (None, u, u), "glActiveTexture": (None, u), "glTexStorage2D": (None, u, i, u, i, i),
        "glTexParameteri": (None, u, u, i), "glGenFramebuffers": (None, i, ctypes.POINTER(u)),
        "glBindFramebuffer": (None, u, u), "glFramebufferTexture2D": (None, u, u, u, u, i),
        "glCheckFramebufferStatus": (u, u), "glViewport": (None, i, i, i, i), "glDisable": (None, u),
        "glEnable": (None, u), "glBlendFunc": (None, u, u), "glBlendEquation": (None, u),
        "glScissor": (None, i, i, i, i),
        "glGenerateMipmap": (None, u), "glDeleteShader": (None, u),
        "glColorMask": (None, ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_ubyte),
        "glDrawArrays": (None, u, i, i), "glDrawArraysInstanced": (None, u, i, i, i),
        "glBindBufferBase": (None, u, u, u), "glBufferSubData": (None, u, n, n, p), "glMemoryBarrier": (None, u),
        "glBindImageTexture": (None, u, u, i, ctypes.c_ubyte, i, u, u),
        "glClearTexSubImage": (None, u, i, i, i, i, i, i, i, u, u, p),
        "glDispatchCompute": (None, u, u, u), "glGetBufferSubData": (None, u, n, n, p),
        "glTexImage2D": (None, u, i, i, i, i, i, u, u, p), "glPixelStorei": (None, u, i),
        "glBlitFramebuffer": (None, i, i, i, i, i, i, i, i, u, u), "glClearColor": (None, f, f, f, f), "glClear": (None, u),
        "glClientWaitSync": (u, p, u, ctypes.c_uint64), "glBufferStorage": (None, u, n, p, u),
        "glCopyBufferSubData": (None, u, u, n, n, n), "glDeleteBuffers": (None, i, ctypes.POINTER(u)),
        "glFenceSync": (p, u, u), "glDeleteSync": (None, p), "glFlush": (None,), "glGetError": (u,),
        "glReadPixels": (None, i, i, i, i, u, u, p),
    }
    gl = types.SimpleNamespace()
    for name, (restype, *argtypes) in table.items():
        fn = getattr(lib, name)
        fn.restype, fn.argtypes = restype, argtypes
        setattr(gl, name[2:], fn)
    return gl


class _DustGL:
    """The open viewer's still frame of dust, drawn by the graphics chip: the frame's own dust and the swarm's grains in
    the four strips round the box, as Scene.draw_view_edges paints them with Cairo. The frame's dust lives on the chip,
    and the chip works out its places from the time and a few settings (Scene.frame_settings) by the arithmetic of
    _portal_still; the swarm's grains, which move by their springs, come from Python. Grains of one colour and level
    merge where they overlap, as one Cairo fill merges them: each pixel keeps a list of the squares that touch it and
    their fill, and the resolve pass covers the pixel by the exact union of each fill's squares, not by adding them, so
    the dust keeps its look. Each strip is a GL texture made in a context of GTK's own and handed to GSK with
    Gdk.GLTextureBuilder, which GTK's renderer takes without a copy through the CPU."""

    FILLS = 29  # 4 colours by 7 levels, then the sparks.
    CAPACITY = 1 << 19  # Squares kept per strip: about five times what the densest frame needs.
    MAX_ATLAS_VRAM = 44 * 1024 * 1024  # 44 MiB LRU cap for resident flipbook atlases (fits dispatch 27.5 MiB + rook 16 MiB).

    def __init__(self, display, context=None):
        """display: GDK's display, for a GL context of GTK's own; or context: one with make_current and
        clear_current, such as the dust surface's own EGL context (_EGLContext), already current."""
        if context is None:
            context = display.create_gl_context()
            context.set_allowed_apis(Gdk.GLAPI.GL)
            context.set_required_version(4, 4)
            context.realize()
        self.ctx = context
        self.ctx.make_current()
        self.window_tex, self.window_size, self.fill_cache = None, (0, 0), None
        self.read_buf, self.read_size = 0, 0  # poll_springs' copy of the grains (see _draw_main).
        gl = self.gl = _gl_functions()
        self.dust_prog = self._program((0x8B31, _DUST_VERT), (0x8B30, _DUST_FRAG))
        self.resolve_prog = self._program((0x8B31, _RESOLVE_VERT), (0x8B30, _RESOLVE_FRAG))
        self.spring_prog = self._program((0x91B9, _SPRING_COMP))  # GL_COMPUTE_SHADER
        self.soft_prog = self._program((0x8B31, _SOFT_VERT), (0x8B30, _SOFT_FRAG))
        self.strand_prog = self._program((0x8B31, _STRAND_VERT), (0x8B30, _STRAND_FRAG))
        self.fil_prog = self._program((0x8B31, _FILAMENT_VERT), (0x8B30, _FILAMENT_FRAG))
        self.fil_tex, self.fil_key, self.fil_size, self.fil_at = None, None, (0, 0), None  # See _filament.
        self.kawase_down_prog = self._program((0x8B31, _RESOLVE_VERT), (0x8B30, _KAWASE_DOWN_FRAG))
        self.kawase_up_prog = self._program((0x8B31, _RESOLVE_VERT), (0x8B30, _KAWASE_UP_FRAG))
        self.tonemap_prog = self._program((0x8B31, _RESOLVE_VERT), (0x8B30, _TONEMAP_FRAG))
        self.atlas_prog = self._program((0x8B31, _ATLAS_VERT), (0x8B30, _ATLAS_FRAG))
        self.atlas_texs = OrderedDict()  # LRU cache path -> (tex_id, nbytes), bounded by MAX_ATLAS_VRAM.
        self.atlas_bytes = 0
        self.hdr_tex, self.hdr_size = None, (0, 0)
        self.bloom_texs, self.bloom_size = (), (0, 0)  # (half_a, quarter, half_b) RGBA16F for 2-level Dual Kawase.
        self.uniforms = {}
        self.sent = {}  # (program, uniform) -> the (type, value) it holds now; see _set.
        ids = (ctypes.c_uint * 14)()
        gl.GenVertexArrays(5, ids)
        gl.GenBuffers(9, ctypes.cast(ctypes.byref(ids, 20), ctypes.POINTER(ctypes.c_uint)))
        (self.dust_vao, self.empty_vao, self.main_vao, self.strand_vao, self.dispatch_vao,
         self.dust_buf, self.count_buf, self.node_buf, self.kick_buf, self.spring_buf, self.main_rows,
         self.target_buf, self.strand_buf, self.dispatch_buf) = ids[:14]
        gl.BindVertexArray(self.strand_vao)
        gl.BindBuffer(0x8892, self.strand_buf)
        gl.EnableVertexAttribArray(0)
        gl.VertexAttribPointer(0, 4, 0x1406, 0, 28, ctypes.c_void_p(0))
        gl.EnableVertexAttribArray(1)
        gl.VertexAttribPointer(1, 3, 0x1406, 0, 28, ctypes.c_void_p(16))
        under = (ctypes.c_uint * 1)()
        gl.GenTextures(1, under)
        self.under_tex, self.under_key = under[0], None
        gl.BindTexture(0x0DE1, self.under_tex)
        gl.TexParameteri(0x0DE1, 0x2801, 0x2600)  # GL_TEXTURE_MIN_FILTER: GL_NEAREST, so texelFetch has a whole texture
        # The main window's grains (see draw_main): their springs, which rows they write, and a fence for reading back.
        self.springs_owned, self.spring_idx, self.spring_epoch, self.spring_fence = False, None, 0.0, None
        self.spring_sparks = False
        gl.BindBuffer(0x90D2, self.kick_buf)
        gl.BufferData(0x90D2, 16, None, 0x88E8)
        for vao, buf in ((self.dust_vao, self.dust_buf), (self.main_vao, self.main_rows),
                         (self.dispatch_vao, self.dispatch_buf)):
            gl.BindVertexArray(vao)
            gl.BindBuffer(0x8892, buf)  # GL_ARRAY_BUFFER
            for loc, size, offset in ((0, 4, 0), (1, 4, 16), (2, 3, 32)):
                gl.EnableVertexAttribArray(loc)
                gl.VertexAttribPointer(loc, size, 0x1406, 0, 44, ctypes.c_void_p(offset))  # GL_FLOAT, 11 floats each
                gl.VertexAttribDivisor(loc, 1)
        gl.BindBuffer(0x90D2, self.count_buf)  # GL_SHADER_STORAGE_BUFFER
        gl.BufferData(0x90D2, 4, None, 0x88E8)
        fbo = (ctypes.c_uint * 1)()
        gl.GenFramebuffers(1, fbo)
        self.out_fbo = fbo[0]
        self.head, self.head_size = None, (0, 0)
        self.dust_key, self.dust_count, self.dust_sparks, self.epoch = None, 0, False, 0.0
        self.free = []  # (texture, sync, size) that GSK has let go of, for the next strips.
        self.readback = None  # Offscreen callers set a w * h * 4 bytearray: each frame is read into it (BGRA).
        self._check("setting up")
        self.ctx.clear_current()

    @staticmethod
    def supports(palette):
        """GL draws dark and light Devs soft-dust plus dark baseline; baseline round+rim light stays with Cairo."""
        if PARTICLE_VARIANT != "baseline":
            return True
        return not palette["round"] and not palette["rim"] and len(palette.get("twins") or ()) <= 1

    def _check(self, doing):
        error = self.gl.GetError()
        if error:
            raise RuntimeError(f"GL error {error:#x} while {doing}")

    def _program(self, *stages):
        gl = self.gl
        prog = gl.CreateProgram()
        for kind, src in stages:
            shader = gl.CreateShader(kind)
            text = ctypes.c_char_p(src.encode())
            gl.ShaderSource(shader, 1, ctypes.byref(text), None)
            gl.CompileShader(shader)
            ok = ctypes.c_int()
            gl.GetShaderiv(shader, 0x8B81, ctypes.byref(ok))
            if not ok.value:
                log = ctypes.create_string_buffer(4096)
                gl.GetShaderInfoLog(shader, 4096, None, log)
                raise RuntimeError("a shader did not compile: " + log.value.decode(errors="replace").strip())
            gl.AttachShader(prog, shader)
        gl.LinkProgram(prog)
        ok = ctypes.c_int()
        gl.GetProgramiv(prog, 0x8B82, ctypes.byref(ok))
        if not ok.value:
            log = ctypes.create_string_buffer(4096)
            gl.GetProgramInfoLog(prog, 4096, None, log)
            raise RuntimeError("the shaders did not link: " + log.value.decode(errors="replace").strip())
        return prog

    def _u(self, prog, name):
        key = (prog, name)
        if key not in self.uniforms:
            self.uniforms[key] = self.gl.GetUniformLocation(prog, name.encode())
        return self.uniforms[key]

    def _set(self, prog, **values):
        """Set uniforms of prog, which is in use. A program keeps its uniforms, so a value it already holds is not
        sent again (the type is part of the value: an int goes as Uniform1i, a float as Uniform1f)."""
        gl, sent = self.gl, self.sent
        for name, value in values.items():
            key, held = (prog, name), (type(value), value)
            if sent.get(key) == held:
                continue
            sent[key] = held
            loc = self._u(prog, name)
            if isinstance(value, int):
                gl.Uniform1i(loc, value)
            elif isinstance(value, float):
                gl.Uniform1f(loc, value)
            elif len(value) == 2:
                gl.Uniform2f(loc, *value)
            else:
                gl.Uniform4f(loc, *value)

    def _upload(self, buf, rows):
        data = array("f", rows)
        self.gl.BindBuffer(0x8892, buf)
        self.gl.BufferData(0x8892, len(data) * 4, data.buffer_info()[0], 0x88E8)  # GL_DYNAMIC_DRAW

    def _load_dust(self, scene, now):
        """The frame's own dust, once per dust and every hour: its fixed numbers, with each grain's shimmer phases
        counted from an epoch near now, so the chip's single precision keeps them smooth."""
        d = scene.dust
        key = (id(d), id(d["points"]))
        if key == self.dust_key and now - self.epoch < 3600:
            return
        self.epoch, tau = now, 2 * math.pi
        rows, sparks = [], False
        for (u, lane, off, depth, _), f, ph, base, size, tone, blue in zip(d["points"], d["freq"], d["phase"], d["base"],
                                                                           d["size"], d["tone"], d["blue"]):
            p = now * f + ph
            rows += (u, lane, off, depth, f, p % tau, 1.3 * p % tau, base, size, tone, blue)
            if base > 0.85:
                sparks = True
        self._upload(self.dust_buf, rows)
        self.dust_key, self.dust_count, self.dust_sparks = key, d["count"], sparks

    @staticmethod
    def _fills(palette, scene):
        """Each fill's colour, as _paint_grains sets it, and whether it adds light or paints over: the 28 groups of
        colour and level, then the sparks."""
        floor, gain = palette["alpha_floor"], palette["alpha_gain"]
        add = 1 if palette["operator"] == cairo.OPERATOR_ADD else 0
        colours, adds = [], []
        for rgb in palette["tones"] + [palette["blue"]]:
            rgb = _mix(rgb, palette["ember"], scene.err)
            for level in range(1, 8):
                a = floor + gain * level / 7
                colours += _DustGL._eight(rgb, a)
                adds.append(add)
        spark = _mix(palette["spark"], palette["ember"], scene.err)
        colours += _DustGL._eight(spark, palette["spark_alpha"] * scene.intensity)
        adds.append(1)
        return colours, adds

    @staticmethod
    def _eight(rgb, alpha):
        """A source colour as Cairo hands it to pixman: premultiplied, rounded to 16 bits, then cut to 8."""
        return tuple((int(v * alpha * 65535.0 + 0.5) >> 8) for v in rgb) + ((int(alpha * 65535.0 + 0.5) >> 8),)

    def _frame_uniforms(self, prog, settings):
        """The frame's settings (Scene.frame_settings) for _FRAME_GLSL in prog."""
        self._set(prog, rr=float(settings["rr"]), rr_arc=float(settings["rr_arc"]), per=float(settings["per"]),
                  shape=settings["shape"], drift=float(settings["drift"]), wave=float(settings["wave"]),
                  head=float(settings["head"]), bottom=float(settings["bottom"]), band=float(settings["band"]),
                  spread=float(settings["spread"]), band_glow=float(settings["band_glow"]),
                  open_el=float(settings["open_el"]), close_el=float(settings["close_el"]),
                  gather_lag=float(VIEW_LAG), gather_dur=float(VIEW_GATHER),
                  dissolve_lag=float(VIEW_DISSOLVE_LAG), dissolve_dur=float(VIEW_DISSOLVE),
                  turn=settings["turn"], voice=float(settings["voice"]))
        self.gl.Uniform1fv(self._u(prog, "ends"), 8, (ctypes.c_float * 8)(*settings["ends"]))
        self.gl.Uniform1fv(self._u(prog, "heard"), 32, (ctypes.c_float * 32)(*settings["heard"][:32]))

    # ---- the main window's grains ----
    def _upload_springs(self, scene, now):
        """The grains the main window draws (scene.idx) onto the chip, where their springs left them in Python: their
        state, and their rows for drawing. Times count from an epoch near now, for the chip's single precision."""
        tau, state, rows, sparks = 2 * math.pi, [], [], False
        rest_every = _rest_every()
        n_z = len(scene.z)
        for i in scene.idx:
            p = now * scene.freq[i] + scene.phase[i]
            until = scene.loose_until[i]
            state += (scene.x[i], scene.y[i], scene.vx[i], scene.vy[i], scene.omega[i], scene.freq[i], p % tau,
                      2 * p % tau, scene.delay[i], scene.curl[i], until - now if until > -1e9 else -1e9, i)
            zi = scene.z[i] if i < n_z else 0.0
            rows += (scene.x[i], scene.y[i], scene.depth[i] * (1.0 if i % rest_every == 0 else scene.extra), zi,
                     scene.vx[i], scene.vy[i], 0.0, scene.base[i], scene.size[i], scene.tone[i], scene.blue_rank[i])
            if scene.base[i] > 0.85:
                sparks = True
        self._upload(self.spring_buf, state)
        self._upload(self.main_rows, rows)
        self.springs_owned, self.spring_idx, self.spring_epoch, self.spring_fence = True, scene.idx, now, None
        self.spring_sparks = sparks

    def step_springs(self, scene):
        """Run the steps Scene._move left for the chip (scene.spring_steps), in order, as _move would have run them."""
        gl, prog = self.gl, self.spring_prog
        if not scene.spring_steps:
            return
        if not self.springs_owned:
            self._upload_springs(scene, scene.spring_steps[0][0])
        gl.UseProgram(prog)
        gl.BindBufferBase(0x90D2, 2, self.spring_buf)
        gl.BindBufferBase(0x90D2, 3, self.main_rows)
        gl.BindBufferBase(0x90D2, 4, self.kick_buf)
        gl.BindBufferBase(0x90D2, 5, self.target_buf)
        place = None
        count, epoch = len(self.spring_idx), self.spring_epoch
        self._set(prog, count=count, rest_every=_rest_every())
        for now, dt, steps, pace, cohesion, jitter, extra, kicks, targets, old, start, dscale, unloose in scene.spring_steps:
            if kicks:
                place = place or {i: k for k, i in enumerate(self.spring_idx)}
                self._upload(self.kick_buf, [v for i, kx, ky, until in kicks
                                             for v in (place.get(i, -1), kx, ky, until - epoch)])
            self._upload(self.target_buf, targets + (old or []))
            self._set(prog, now_t=float(now - epoch), dt=float(dt), steps=steps, pace=float(pace),
                      cohesion=float(cohesion), jitter=float(jitter), extra=float(extra), kicks=len(kicks),
                      start_t=float(start - epoch), dscale=float(dscale), has_old=1 if old else 0,
                      unloose=1 if unloose else 0)
            gl.DispatchCompute((count + 63) // 64, 1, 1)
            gl.MemoryBarrier(0xFFFFFFFF)
        scene.spring_steps.clear()

    def _draw_under(self, gl, under, scale):
        """Draw the Cairo scrim texture under the dust, or clear to transparent when none is active."""
        if under is None:
            gl.ClearColor(0.0, 0.0, 0.0, 0.0)
            gl.Clear(0x4000)
            return
        image, (ux, uy) = under
        if self.under_key is not image:
            image.flush()
            gl.BindTexture(0x0DE1, self.under_tex)
            gl.PixelStorei(0x0CF2, image.get_stride() // 4)
            pixels = ctypes.c_char.from_buffer(image.get_data())
            gl.TexImage2D(0x0DE1, 0, 0x8058, image.get_width(), image.get_height(), 0, 0x80E1, 0x1401,
                          ctypes.addressof(pixels))
            gl.PixelStorei(0x0CF2, 0)
            self.under_key = image
        gl.Disable(0x0BE2)
        gl.UseProgram(self.resolve_prog)
        self._set(self.resolve_prog, has_under=1, skip_dust=1, under=0, under_at=(ux * scale, uy * scale))
        gl.ActiveTexture(0x84C0)
        gl.BindTexture(0x0DE1, self.under_tex)
        gl.BindVertexArray(self.empty_vao)
        gl.DrawArrays(5, 0, 4)

    def _ensure_hdr(self, w, h):
        """Ensure a small GL_RGBA16F offscreen texture of (w, h) for soft-sprite HDR accumulation."""
        gl = self.gl
        if self.hdr_size == (w, h) and self.hdr_tex is not None:
            return self.hdr_tex
        if self.hdr_tex is not None:
            gl.DeleteTextures(1, (ctypes.c_uint * 1)(self.hdr_tex))
        tid = (ctypes.c_uint * 1)()
        gl.GenTextures(1, tid)
        self.hdr_tex, self.hdr_size = tid[0], (w, h)
        gl.BindTexture(0x0DE1, self.hdr_tex)
        gl.TexImage2D(0x0DE1, 0, 0x881A, w, h, 0, 0x1908, 0x140B, None)  # GL_RGBA16F, GL_RGBA, GL_HALF_FLOAT
        gl.TexParameteri(0x0DE1, 0x2801, 0x2601)  # GL_LINEAR
        gl.TexParameteri(0x0DE1, 0x2800, 0x2601)
        gl.TexParameteri(0x0DE1, 0x2802, 0x812F)  # GL_CLAMP_TO_EDGE
        gl.TexParameteri(0x0DE1, 0x2803, 0x812F)
        return self.hdr_tex

    def _ensure_bloom(self, w, h):
        """Ensure three tiny RGBA16F textures (half, quarter, half_up) for two-level Dual Kawase bloom."""
        gl = self.gl
        if self.bloom_size == (w, h) and self.bloom_texs:
            return self.bloom_texs
        if self.bloom_texs:
            gl.DeleteTextures(len(self.bloom_texs), (ctypes.c_uint * len(self.bloom_texs))(*self.bloom_texs))
        w1, h1 = max(1, (w + 1) // 2), max(1, (h + 1) // 2)
        w2, h2 = max(1, (w1 + 1) // 2), max(1, (h1 + 1) // 2)
        tids = (ctypes.c_uint * 3)()
        gl.GenTextures(3, tids)
        for tid, tw, th in ((tids[0], w1, h1), (tids[1], w2, h2), (tids[2], w1, h1)):
            gl.BindTexture(0x0DE1, tid)
            gl.TexImage2D(0x0DE1, 0, 0x881A, tw, th, 0, 0x1908, 0x140B, None)
            gl.TexParameteri(0x0DE1, 0x2801, 0x2601)
            gl.TexParameteri(0x0DE1, 0x2800, 0x2601)
            gl.TexParameteri(0x0DE1, 0x2802, 0x812F)
            gl.TexParameteri(0x0DE1, 0x2803, 0x812F)
        self.bloom_texs, self.bloom_size = (tids[0], tids[1], tids[2]), (w, h)
        return self.bloom_texs

    def _draw_kawase_bloom(self, gl, hdr, W, H):
        """Run two-level Dual Kawase blur (full -> 1/2 -> 1/4 -> 1/2) on the small swarm box; return half_up tex."""
        if W < 8 or H < 8:
            return None
        t_half, t_qtr, t_up = self._ensure_bloom(W, H)
        w1, h1 = max(1, (W + 1) // 2), max(1, (H + 1) // 2)
        w2, h2 = max(1, (w1 + 1) // 2), max(1, (h1 + 1) // 2)
        gl.BindVertexArray(self.empty_vao)
        gl.BindFramebuffer(0x8D40, self.out_fbo)
        # Down 0 -> 1 (half res) with soft cluster knee (1.0 source texel offset matches Cairo _kawase_down).
        gl.FramebufferTexture2D(0x8D40, 0x8CE0, 0x0DE1, t_half, 0)
        gl.Viewport(0, 0, w1, h1)
        gl.UseProgram(self.kawase_down_prog)
        gl.ActiveTexture(0x84C0)
        gl.BindTexture(0x0DE1, hdr)
        self._set(self.kawase_down_prog, src_tex=0, half_px=(1.0 / W, 1.0 / H), soft_knee=1)
        gl.DrawArrays(5, 0, 4)
        # Down 1 -> 2 (quarter res).
        gl.FramebufferTexture2D(0x8D40, 0x8CE0, 0x0DE1, t_qtr, 0)
        gl.Viewport(0, 0, w2, h2)
        gl.BindTexture(0x0DE1, t_half)
        self._set(self.kawase_down_prog, src_tex=0, half_px=(1.0 / w1, 1.0 / h1), soft_knee=0)
        gl.DrawArrays(5, 0, 4)
        # Up 2 -> 1 (half res, mixed 72/28 with tighter half-res glow).
        gl.FramebufferTexture2D(0x8D40, 0x8CE0, 0x0DE1, t_up, 0)
        gl.Viewport(0, 0, w1, h1)
        gl.UseProgram(self.kawase_up_prog)
        gl.ActiveTexture(0x84C0)
        gl.BindTexture(0x0DE1, t_qtr)
        gl.ActiveTexture(0x84C1)
        gl.BindTexture(0x0DE1, t_half)
        self._set(self.kawase_up_prog, src_tex=0, tap_tex=1, half_px=(1.0 / w1, 1.0 / h1), mix_tap=0.28)
        gl.DrawArrays(5, 0, 4)
        gl.ActiveTexture(0x84C0)
        return t_up

    def _draw_helix_strands_gl(self, gl, scene, W, H, centre, scale, light=False):
        """Draw the two continuous 3D glowing gold helix strands as mitered triangle strips (matches Cairo)."""
        if PARTICLE_VARIANT != "C" or scene.helix_fade <= 0.01:
            return
        strands = devs_pack.eval_helix_strands(scene, scene.last)
        if not strands:
            return
        er, eg, eb = (0.70, 0.18, 0.10) if light else _SOFT_EMBER_LIN
        err = float(scene.err)
        e1 = 1.0 - err
        am = devs_pack.LOOK["light"]["amber_mid"]
        en_gain = float(devs_pack.LOOK.get("energy_gain", 1.22))
        intensity = float(scene.intensity)
        sk = min(1.0, float(scene.size_k))
        ox, oy = centre[0] * scale, centre[1] * scale
        prog = self.strand_prog
        gl.UseProgram(prog)
        self._set(prog, size_px=(float(W), float(H)), light_mode=1 if light else 0)
        gl.BindVertexArray(self.strand_vao)
        for strand in strands:
            n = len(strand)
            if n < 2:
                continue
            verts = []
            for k, (sx, sy, zn, bd, lv, sf) in enumerate(strand):
                px = ox + sx * scale
                py = oy + sy * scale
                k0 = max(0, k - 1)
                k1 = min(n - 1, k + 1)
                tx = (strand[k1][0] - strand[k0][0]) * scale
                ty = (strand[k1][1] - strand[k0][1]) * scale
                tl = math.hypot(tx, ty) or 1.0
                nx, ny = -ty / tl, tx / tl
                hw = ((1.9 + 0.5 * zn + 0.4 * lv) if light else (2.15 + 0.65 * zn + 0.55 * lv)) * scale * sk
                if light:
                    en = min(1.0, sf * intensity)
                    cr = (am[0] * e1 + er * err) * en
                    cg = (am[1] * e1 + eg * err) * en
                    cb = (am[2] * e1 + eb * err) * en
                else:
                    en = 0.56 * bd * (0.85 + 0.35 * lv) * intensity * sf * en_gain
                    cr = (1.0 * e1 + er * err) * en
                    cg = ((0.66 + 0.14 * zn) * e1 + eg * err) * en
                    cb = ((0.14 + 0.12 * max(0.0, zn)) * e1 + eb * err) * en
                verts.extend((px - nx * hw, py - ny * hw, -1.0, 0.0, cr, cg, cb))
                verts.extend((px + nx * hw, py + ny * hw, 1.0, 0.0, cr, cg, cb))
            arr = (ctypes.c_float * len(verts))(*verts)
            gl.BindBuffer(0x8892, self.strand_buf)
            gl.BufferData(0x8892, ctypes.sizeof(arr), arr, 0x88E8)
            gl.DrawArrays(5, 0, n * 2)  # GL_TRIANGLE_STRIP

    def _filament(self, gl, scene, W, H, centre, scale, mode, light=False, amount=1.0):
        """A constellation's filament layer, one pass of it (see _FILAMENT_FRAG) into the bound frame. The drawing's
        texture is made once per diagram and scale; per frame only its elements' state goes up, once for all passes.
        Nothing happens without a constellation, and then it returns False."""
        frame = scene.filament_frame(scene.last) if scene.render is not None else None
        if frame is None:
            if self.fil_tex is not None:  # The last diagram's texture goes with it.
                gl.DeleteTextures(1, (ctypes.c_uint * 1)(self.fil_tex))
                self.fil_tex = self.fil_key = None
            return False
        con, t, dy = frame
        prog = self.fil_prog
        gl.UseProgram(prog)
        gl.ActiveTexture(0x84C0)
        if self.fil_key is None or self.fil_key[0] is not con.elements or self.fil_key[1] != scale:
            data, tw, th = filament.art(con.elements, con.plan["size"], scale)
            if self.fil_tex is None:
                ids = (ctypes.c_uint * 1)()
                gl.GenTextures(1, ids)
                self.fil_tex = ids[0]
            gl.BindTexture(0x0DE1, self.fil_tex)
            gl.TexImage2D(0x0DE1, 0, 0x8058, tw, th, 0, 0x1908, 0x1401, data)  # GL_RGBA8 from GL_RGBA bytes
            gl.TexParameteri(0x0DE1, 0x2801, 0x2600)  # GL_NEAREST: one level, so texelFetch sees a whole texture
            gl.TexParameteri(0x0DE1, 0x2800, 0x2600)
            self.fil_key, self.fil_size, self.fil_at = (con.elements, scale), (tw, th), None
        gl.BindTexture(0x0DE1, self.fil_tex)
        if self.fil_at != (scene.last, con, light):
            self.fil_at = (scene.last, con, light)
            st, n = con.lines(t, scene.last, light), filament.MAX_ELEMENTS
            for name, at in (("fa", 0), ("fb", 4), ("fc", 8)):
                values = [st[j + at + q] for j in range(0, len(st), 12) for q in range(4)]
                gl.Uniform4fv(self._u(prog, name), n, (ctypes.c_float * (4 * n))(*values))
        tw, th = self.fil_size
        hot = filament.LIGHT[filament.HOT] if light else filament.HOT
        self._set(prog, art=0, mode=mode, amount=float(amount), size_px=(float(W), float(H)), hot_rgb=(*hot, 1.0),
                  rect=(float(round(centre[0] * scale) - tw // 2), float(round((centre[1] + dy) * scale) - th // 2),
                        float(tw), float(th)))
        gl.Enable(0x0BE2)
        gl.BlendFunc(*((1, 1), (0x0305, 1), (1, 0x0303))[mode])  # Add; under what is there; premultiplied over.
        gl.BindVertexArray(self.empty_vao)
        gl.DrawArrays(5, 0, 4)
        return True

    def _draw_soft_hdr(self, gl, palette, scene, W, H, centre, scale, under, out_tex):
        """Render soft round/elliptical grains (+ helix gold strands) into RGBA16F and tone-map onto out_tex."""
        hdr = self._ensure_hdr(W, H)
        gl.BindFramebuffer(0x8D40, self.out_fbo)
        gl.FramebufferTexture2D(0x8D40, 0x8CE0, 0x0DE1, hdr, 0)
        gl.Viewport(0, 0, W, H)
        gl.ClearColor(0.0, 0.0, 0.0, 0.0)
        gl.Clear(0x4000)
        gl.Enable(0x0BE2)
        gl.BlendFunc(1, 1)  # Pure linear HDR additive accumulation.
        self._draw_helix_strands_gl(gl, scene, W, H, centre, scale, light=False)
        prog = self.soft_prog
        gl.UseProgram(prog)
        look = devs_pack.LOOK
        cset = 1 if scene.dispatch_nova_standin(scene.last) else 0
        self._set(prog, light_mode=0, color_set=cset, intensity=float(scene.intensity), share=float(scene.share),
                  grow=float(palette["size"]), size_k=float(scene.size_k), scale=float(scale), err=float(scene.err),
                  u_time=float(scene.last % _TIME_WRAP), glint_k=float(look.get("glint_strength", 1.0)),
                  streak_k=float(look.get("streak_strength", 1.0)),
                  origin=(centre[0] * scale, centre[1] * scale), size_px=(float(W), float(H)))
        gl.BindVertexArray(self.main_vao)
        self._set(prog, spark=0)
        gl.DrawArraysInstanced(5, 0, 4, len(self.spring_idx))
        self._set(prog, spark=1)
        gl.DrawArraysInstanced(5, 0, 4, len(self.spring_idx))
        drows = scene.dispatch_gl_rows(scene.last)
        if drows:
            self._upload(self.dispatch_buf, drows)
            gl.BindVertexArray(self.dispatch_vao)
            self._set(prog, spark=0)
            gl.DrawArraysInstanced(5, 0, 4, len(drows) // 11)
        glowed = self._filament(gl, scene, W, H, centre, scale, 0)  # A constellation's glow, for the bloom to spread.
        gl.Disable(0x0BE2)
        bloom_tex = self._draw_kawase_bloom(gl, hdr, W, H) if (
            PARTICLE_VARIANT in ("B", "C") and hasattr(self, "_draw_kawase_bloom")) else None
        if glowed:  # Once spread, most of the glow comes out again, so the line stays a crisp core in a soft glow.
            gl.BindFramebuffer(0x8D40, self.out_fbo)
            gl.FramebufferTexture2D(0x8D40, 0x8CE0, 0x0DE1, hdr, 0)
            gl.Viewport(0, 0, W, H)
            gl.BlendEquation(0x800B)  # GL_FUNC_REVERSE_SUBTRACT: what is there, less the glow.
            try:
                self._filament(gl, scene, W, H, centre, scale, 0, amount=1.0 - filament.GLOW_KEEP)
            finally:
                gl.BlendEquation(0x8006)  # GL_FUNC_ADD, always: every later pass blends by adding.
            gl.Disable(0x0BE2)
        # Resolve HDR (+ optional bloom) through the warm-gold (or Nova plasma) tone curve onto out_tex.
        gl.BindFramebuffer(0x8D40, self.out_fbo)
        gl.FramebufferTexture2D(0x8D40, 0x8CE0, 0x0DE1, out_tex, 0)
        gl.Viewport(0, 0, W, H)
        if under is not None:
            image, (ux, uy) = under
            if self.under_key is not image:
                image.flush()
                gl.BindTexture(0x0DE1, self.under_tex)
                gl.PixelStorei(0x0CF2, image.get_stride() // 4)
                pixels = ctypes.c_char.from_buffer(image.get_data())
                gl.TexImage2D(0x0DE1, 0, 0x8058, image.get_width(), image.get_height(), 0, 0x80E1, 0x1401,
                              ctypes.addressof(pixels))
                gl.PixelStorei(0x0CF2, 0)
                self.under_key = image
        tprog = self.tonemap_prog
        gl.UseProgram(tprog)
        gl.ActiveTexture(0x84C0)
        gl.BindTexture(0x0DE1, hdr)
        gl.ActiveTexture(0x84C1)
        gl.BindTexture(0x0DE1, bloom_tex or hdr)
        gl.ActiveTexture(0x84C2)
        gl.BindTexture(0x0DE1, self.under_tex)
        self._set(tprog, hdr_tex=0, bloom_tex=1, under=2, has_bloom=1 if bloom_tex else 0, nova_tm=cset,
                  bloom_strength=float(look.get("bloom_strength", 0.48)),
                  dither_k=float(look.get("dither_strength", 1.0)),
                  has_under=1 if under is not None else 0,
                  under_at=(under[1][0] * scale, under[1][1] * scale) if under is not None else (0.0, 0.0))
        gl.BindVertexArray(self.empty_vao)
        gl.DrawArrays(5, 0, 4)
        gl.ActiveTexture(0x84C0)
        if scene.render is not None:  # A constellation's ink edge, then its crisp cores, over the frame.
            self._filament(gl, scene, W, H, centre, scale, 1)
            self._filament(gl, scene, W, H, centre, scale, 2)
            gl.Disable(0x0BE2)

    def _draw_soft_light(self, gl, palette, scene, W, H, centre, scale, under, out_tex):
        """Render burnished-amber light-theme soft round grains (+ chestnut shadow + helix/dispatch strands) via GL."""
        gl.BindFramebuffer(0x8D40, self.out_fbo)
        gl.FramebufferTexture2D(0x8D40, 0x8CE0, 0x0DE1, out_tex, 0)
        gl.Viewport(0, 0, W, H)
        self._draw_under(gl, under, scale)
        gl.Enable(0x0BE2)
        gl.BlendFunc(1, 0x0303)  # Premultiplied OVER.
        prog = self.soft_prog
        gl.UseProgram(prog)
        look = devs_pack.LOOK
        self._set(prog, color_set=0, spark=0, intensity=float(scene.intensity), share=0.0,
                  grow=float(palette["size"]), size_k=float(scene.size_k), scale=float(scale), err=float(scene.err),
                  u_time=float(scene.last % _TIME_WRAP), glint_k=0.0,
                  streak_k=float(look.get("streak_strength", 1.0)),
                  origin=(centre[0] * scale, centre[1] * scale), size_px=(float(W), float(H)))
        gl.BindVertexArray(self.main_vao)
        if float(look["light"].get("shadow_alpha", 0.0)) > 0.001:
            self._set(prog, light_mode=2)
            gl.DrawArraysInstanced(5, 0, 4, len(self.spring_idx))
        self._draw_helix_strands_gl(gl, scene, W, H, centre, scale, light=True)
        gl.UseProgram(prog)
        gl.BindVertexArray(self.main_vao)
        self._set(prog, light_mode=1)
        gl.DrawArraysInstanced(5, 0, 4, len(self.spring_idx))
        drows = scene.dispatch_gl_rows(scene.last)
        if drows:
            self._upload(self.dispatch_buf, drows)
            gl.BindVertexArray(self.dispatch_vao)
            gl.DrawArraysInstanced(5, 0, 4, len(drows) // 11)
        self._filament(gl, scene, W, H, centre, scale, 2, light=True)  # A constellation's lines, in amber.
        gl.Disable(0x0BE2)

    def _spring_state(self, scene, buf=None):
        """Copy the chip's grains into the scene's x, y, vx and vy: from buf (poll_springs' copy), or from the chip's
        own buffer, which holds them after every step."""
        count = len(self.spring_idx)
        data = (ctypes.c_float * (count * 12))()
        self.gl.BindBuffer(0x90D2, buf or self.spring_buf)
        self.gl.GetBufferSubData(0x90D2, 0, ctypes.sizeof(data), data)
        idx = self.spring_idx
        first, step = (idx[0], idx[1] - idx[0] if count > 1 else 1) if count else (0, 0)
        if step > 0 and idx[-1] == first + step * (count - 1):
            # Every index list is an even run (all grains, the resting third, a scene's swarm): one slice a column.
            # A scene's extra grains may be gone already (Scene._size_swarm), so only the grains still there.
            keep = max(0, min(count, (len(scene.x) - first + step - 1) // step))
            stop = first + step * keep
            for column, values in enumerate((scene.x, scene.y, scene.vx, scene.vy)):
                values[first:stop:step] = data[column:keep * 12:12]
            return
        for k, i in enumerate(idx):
            if i < len(scene.x):  # A scene's extra grains may be gone already (Scene._size_swarm).
                scene.x[i], scene.y[i], scene.vx[i], scene.vy[i] = data[k * 12:k * 12 + 4]

    def follow(self, scene):
        """poll_springs, from outside a frame: the tick reads the grains before the scene steps, so what follows the
        grains in Python (the scrim) is one frame behind them, not two."""
        if self.springs_owned and self.spring_fence is not None:
            self.ctx.make_current()
            try:
                self.poll_springs(scene)
            finally:
                self.ctx.clear_current()

    def poll_springs(self, scene):
        """Keep Python's copy of the grains a frame behind the chip, for what reads them there (the scrim follows the
        grains): read the last frame's state once its fence says the chip has finished it, never waiting."""
        if self.springs_owned and self.spring_fence is not None and scene.grains_read:
            # At rest and in a settled scene nothing reads the grains in Python (the vignette follows their
            # targets): they come back only when the chip gives them up (read_springs).
            if self.gl.ClientWaitSync(self.spring_fence, 0, 0) in (0x911A, 0x911C):  # ALREADY_SIGNALED, CONDITION_SATISFIED
                self.gl.DeleteSync(self.spring_fence)
                self.spring_fence = None
                self._spring_state(scene, self.read_buf)

    def read_springs(self, scene):
        """The chip's grains back into Python, after the steps still waiting, when Python's springs take over again."""
        if not self.springs_owned:
            scene.spring_steps.clear()
            return
        self.ctx.make_current()
        try:
            self.step_springs(scene)
            self._spring_state(scene)
            if self.spring_fence is not None:
                self.gl.DeleteSync(self.spring_fence)
            self.springs_owned, self.spring_fence = False, None
            self._check("reading the grains back")
        finally:
            self.ctx.clear_current()

    def draw_main(self, scene, w, h, centre, scale, under, window=False):
        """The main window's grains as one texture of w x h logical pixels, as draw_swarm paints them with Cairo
        round centre: what lies under them first (under: the scrim's image and where its top-left corner goes, or
        None), then the grains, fill by fill. Their springs run here first (see step_springs). With window, the
        frame goes to the current window surface instead (the dust surface), and nothing is returned."""
        self.ctx.make_current()
        try:
            return self._draw_main(self.gl, PALETTE, scene, w, h, centre, scale, under, window)
        finally:
            self.ctx.clear_current()

    def _ensure_atlas(self, path, allow_upload=True):
        """Return (tex_id, uploaded, error) for one flipbook atlas; decodes off-thread and uploads <= 1/frame."""
        entry = self.atlas_texs.get(path)
        if entry is not None:
            self.atlas_texs.move_to_end(path)
            return entry[0], False, None
        fail = pack_player.ATLAS_LOADER.failure(path)
        if fail is not None:
            return None, False, fail
        if not os.path.isfile(path):
            return None, False, f"atlas missing: {path}"
        if not allow_upload:
            pack_player.ATLAS_LOADER.prefetch(path)
            return None, False, None
        decoded = pack_player.ATLAS_LOADER.pop_ready(path)
        if decoded is None:
            pack_player.ATLAS_LOADER.prefetch(path)
            return None, False, None
        raw, aw, ah, rowstride = decoded
        gl = self.gl
        tid = (ctypes.c_uint * 1)()
        gl.GenTextures(1, tid)
        tex = tid[0]
        gl.BindTexture(0x0DE1, tex)
        gl.PixelStorei(0x0CF2, rowstride // 4)
        gl.TexImage2D(0x0DE1, 0, 0x8058, aw, ah, 0, 0x1908, 0x1401, raw)  # GL_RGBA8 from straight GL_RGBA
        gl.PixelStorei(0x0CF2, 0)
        gl.TexParameteri(0x0DE1, 0x2801, 0x2601)  # GL_LINEAR
        gl.TexParameteri(0x0DE1, 0x2800, 0x2601)  # GL_LINEAR
        gl.TexParameteri(0x0DE1, 0x2802, 0x812F)  # GL_CLAMP_TO_EDGE
        gl.TexParameteri(0x0DE1, 0x2803, 0x812F)  # GL_CLAMP_TO_EDGE
        nbytes = aw * ah * 4
        self.atlas_texs[path] = (tex, nbytes)
        self.atlas_bytes += nbytes
        return tex, True, None

    def _trim_atlases(self, keep_paths, max_bytes=None):
        """Evict flipbook atlas textures (all when keep_paths is None, or LRU beyond max_bytes)."""
        if keep_paths is None:
            if self.atlas_texs:
                tids = [t for t, _ in self.atlas_texs.values()]
                self.gl.DeleteTextures(len(tids), (ctypes.c_uint * len(tids))(*tids))
                self.atlas_texs.clear()
                self.atlas_bytes = 0
            pack_player.ATLAS_LOADER.keep_only(None)
            return
        if max_bytes is None:
            stale = [p for p in self.atlas_texs if p not in keep_paths]
            if stale:
                tids = []
                for p in stale:
                    tex, nb = self.atlas_texs.pop(p)
                    self.atlas_bytes = max(0, self.atlas_bytes - nb)
                    tids.append(tex)
                self.gl.DeleteTextures(len(tids), (ctypes.c_uint * len(tids))(*tids))
            return
        evict = []
        for p in list(self.atlas_texs.keys()):
            if self.atlas_bytes <= max_bytes:
                break
            if p in keep_paths:
                continue
            tex, nb = self.atlas_texs.pop(p)
            self.atlas_bytes = max(0, self.atlas_bytes - nb)
            evict.append(tex)
        if evict:
            self.gl.DeleteTextures(len(evict), (ctypes.c_uint * len(evict))(*evict))

    def _draw_nova_strands_gl(self, gl, scene, W, H, cx_px, cy_px, scale, strands):
        """Draw Nova plasma strands (pink glow, ink underlay, violet->pink core, marching white beads) on GPU."""
        if not strands:
            return
        pal = scene.flipbook.palette if scene.flipbook else {}
        ink = pack_player._hex_rgb(pal.get("ink", "#150B33"), (0.082, 0.043, 0.200))
        violet = pack_player._hex_rgb(pal.get("violet", "#8A45FF"), (0.541, 0.271, 1.0))
        pink = pack_player._hex_rgb(pal.get("pink", "#FF5BD8"), (1.0, 0.357, 0.847))
        core = pack_player._hex_rgb(pal.get("core", "#FFF4FF"), (1.0, 0.957, 1.0))
        prog = self.strand_prog
        gl.UseProgram(prog)
        gl.Enable(0x0BE2)
        gl.BlendFunc(1, 0x0303)  # Premultiplied OVER
        gl.BindVertexArray(self.strand_vao)
        self._set(prog, size_px=(float(W), float(H)))

        def _draw_ribbon(pts_px, hw, col_fn, alpha_val, mode):
            n = len(pts_px)
            if n < 2:
                return
            verts = []
            for k, (px, py) in enumerate(pts_px):
                k0, k1 = max(0, k - 1), min(n - 1, k + 1)
                tx = pts_px[k1][0] - pts_px[k0][0]
                ty = pts_px[k1][1] - pts_px[k0][1]
                tl = math.hypot(tx, ty) or 1.0
                nx, ny = -ty / tl, tx / tl
                u = k / (n - 1)
                cr_c, cg_c, cb_c = col_fn(u)
                verts.extend((px - nx * hw, py - ny * hw, -1.0, alpha_val, cr_c, cg_c, cb_c))
                verts.extend((px + nx * hw, py + ny * hw, 1.0, alpha_val, cr_c, cg_c, cb_c))
            arr = (ctypes.c_float * len(verts))(*verts)
            gl.BindBuffer(0x8892, self.strand_buf)
            gl.BufferData(0x8892, ctypes.sizeof(arr), arr, 0x88E8)
            self._set(prog, light_mode=mode)
            gl.DrawArrays(5, 0, n * 2)

        now = float(scene.last % _TIME_WRAP)
        for st in strands:
            pts = st["pts"]
            if len(pts) < 2:
                continue
            pts_px = [(cx_px + x * scale, cy_px + y * scale) for x, y in pts]
            alpha = float(st["alpha"])
            # 1) Soft outer pink glow (7 px wide)
            _draw_ribbon(pts_px, 4.0 * scale, lambda _u: pink, alpha * 0.24, 3)
            # 2) Ink underlay (3.4 px wide, carries line on light desktop)
            _draw_ribbon(pts_px, 1.8 * scale, lambda _u: ink, alpha * 0.55, 2)
            # 3) Violet -> pink plasma core (1.8 px wide)
            _draw_ribbon(pts_px, 1.05 * scale,
                         lambda u: (violet[0] + (pink[0] - violet[0]) * u,
                                    violet[1] + (pink[1] - violet[1]) * u,
                                    violet[2] + (pink[2] - violet[2]) * u),
                         alpha, 2)
            # 4) Marching white core beads (one pass every 2.4 s, spacing 11.2 logical px)
            cum = [0.0]
            for k in range(1, len(pts)):
                cum.append(cum[-1] + math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]))
            total_l = cum[-1]
            if total_l > 4.0:
                step_l = 11.2
                n_beads = max(1, int(round(total_l / step_l)))
                phase = ((now / 2.4) % 1.0) * step_l * n_beads
                pos = phase % step_l
                bead_hw = 0.85 * scale
                while pos < total_l - 1.5:
                    # Locate segment at arc length pos and pos + 2.2
                    seg_pts = []
                    for d_l in (pos, min(total_l, pos + 2.2)):
                        lo, hi = 0, len(cum) - 1
                        while lo + 1 < hi:
                            mid = (lo + hi) // 2
                            if cum[mid] <= d_l:
                                lo = mid
                            else:
                                hi = mid
                        span = (cum[hi] - cum[lo]) or 1.0
                        f = max(0.0, min(1.0, (d_l - cum[lo]) / span))
                        bx = pts_px[lo][0] + (pts_px[hi][0] - pts_px[lo][0]) * f
                        by = pts_px[lo][1] + (pts_px[hi][1] - pts_px[lo][1]) * f
                        seg_pts.append((bx, by))
                    _draw_ribbon(seg_pts, bead_hw, lambda _u: core, alpha * 0.90, 2)
                    pos += step_l
        gl.Disable(0x0BE2)

    def _draw_flipbook_gl(self, gl, scene, W, H, centre, scale):
        """Draw the active FORMAT.md flipbook pack; on any missing/corrupt atlas fall back to Devs on GL."""
        try:
            gl.ClearColor(0.0, 0.0, 0.0, 0.0)
            gl.Clear(0x4000)
            presence = scene.flipbook
            state_name = pack_player.map_overlay_state(scene)
            presence.set_state(state_name, scene.last)
            lv = pack_player.state_level_for_scene(scene.pack, state_name, scene)
            rest_dy = scene.rest_y_offset()
            tip_levels = scene.dispatch_tip_levels(scene.last)
            quads = presence.draw_list(scene.last, lv, tip_levels=tip_levels, rest_dy=rest_dy)
            nxt = presence.peek_next_path(scene.last)
            if nxt and nxt not in self.atlas_texs:
                pack_player.ATLAS_LOADER.prefetch(nxt)
            ox, oy = centre[0] * scale, centre[1] * scale
            base_px = pack_player.REAL_SIZE * scale
            keep_paths = set()
            uploads = 0

            def _render_atlas_quads(qlist, base_ox, base_oy):
                nonlocal uploads
                if not qlist:
                    return True
                prog = self.atlas_prog
                gl.UseProgram(prog)
                gl.BindVertexArray(self.empty_vao)
                gl.Enable(0x0BE2)  # GL_BLEND
                gl.ActiveTexture(0x84C0)
                self._set(prog, u_viewport=(float(W), float(H)), u_atlas=0)
                for q in qlist:
                    path = q["path"]
                    keep_paths.add(path)
                    tex, did_upload, err = self._ensure_atlas(path, allow_upload=(uploads == 0))
                    if err is not None:
                        gl.Disable(0x0BE2)
                        scene.fallback_to_devs(scene.last, f"flipbook atlas failed ({err})")
                        self._trim_atlases(None)
                        return False
                    if did_upload:
                        uploads += 1
                    if tex is None:
                        continue
                    cols, rows = q["cols"], q["rows"]
                    cx_i = q["cell_idx"] % cols
                    cy_i = q["cell_idx"] // cols
                    qbase = (float(q["size_px"]) * scale) if q.get("size_px") is not None else base_px
                    qw = qbase * q["scale"]
                    qh = qw * q["stretch"]
                    qox, qoy = q.get("offset") or (0.0, 0.0)
                    qdy = float(q.get("dy", 0.0))
                    gl.BindTexture(0x0DE1, tex)
                    gl.BlendFunc(1, 1 if q["additive"] else 0x0303)  # Premultiplied over (flash too, CP7).
                    self._set(prog, u_origin=(float(base_ox + qox * scale), float(base_oy + (qdy + qoy) * scale)),
                              u_pivot=(float(q["pivot"][0]), float(q["pivot"][1])),
                              u_grid=(float(cols), float(rows)), u_cell_xy=(float(cx_i), float(cy_i)),
                              u_quad_size=(float(qw), float(qh)), u_angle=float(q.get("angle", 0.0)),
                              u_alpha=float(q["alpha"]))
                    gl.DrawArrays(5, 0, 4)
                gl.Disable(0x0BE2)
                return True

            if not _render_atlas_quads(quads, ox, oy):
                return False

            # Baked Nova dispatch: draw plasma strands on GPU, then turn baked strand_head sprites along each tangent.
            if scene.dispatch_active(scene.last) and pack_player.has_dispatch_bake(scene.pack):
                tip_at = presence.dispatch_tip_at()
                dy_px = (centre[1] + scene.dispatch_y_offset()) * scale
                strands = scene.dispatch.nova_strand_data(scene.last, tip_at=tip_at, y_off=0.0)
                if strands:
                    self._draw_nova_strands_gl(gl, scene, W, H, centre[0] * scale, dy_px, scale, strands)
                    head_quads = []
                    for st in strands:
                        if st["head_pos"] is not None:
                            hq = presence.sprite_quad("strand_head", st["head_tl"], st["head_pos"],
                                                      30.0, st["head_angle"], st["head_alpha"])
                            if hq is not None:
                                head_quads.append(hq)
                    if head_quads and not _render_atlas_quads(head_quads, centre[0] * scale, dy_px):
                        return False

            for name in presence.live_icon_names():
                spec = presence.icons.get(name)
                if spec and "_image_path" in spec:
                    keep_paths.add(spec["_image_path"])
            if nxt:
                keep_paths.add(nxt)
            self._trim_atlases(keep_paths, max_bytes=self.MAX_ATLAS_VRAM)
            pack_player.ATLAS_LOADER.keep_only(keep_paths)
            return True
        except Exception as exc:
            gl.Disable(0x0BE2)
            scene.fallback_to_devs(scene.last, f"GL flipbook draw failed ({exc})")
            self._trim_atlases(None)
            return False

    def _draw_main(self, gl, palette, scene, w, h, centre, scale, under, window=False):
        W, H = max(1, math.ceil(w * scale)), max(1, math.ceil(h * scale))
        reuse_tex = None
        if (scene.pack_kind == "flipbook" and scene.flipbook is not None and scene.form != "render"
                and not scene.dispatch_nova_standin(scene.last)):
            tex = self._window_texture(W, H) if window else self._texture(W, H)
            gl.Disable(0x0B71)
            gl.Disable(0x0C11)
            gl.BindFramebuffer(0x8D40, self.out_fbo)
            gl.FramebufferTexture2D(0x8D40, 0x8CE0, 0x0DE1, tex, 0)
            gl.Viewport(0, 0, W, H)
            if self._draw_flipbook_gl(gl, scene, W, H, centre, scale):
                if not pack_player.has_dispatch_bake(scene.pack):
                    drows = scene.dispatch_gl_rows(scene.last)
                    if drows:
                        self._upload(self.dispatch_buf, drows)
                        prog = self.soft_prog
                        gl.UseProgram(prog)
                        gl.Enable(0x0BE2)
                        gl.BlendFunc(1, 1)
                        self._set(prog, light_mode=0, color_set=1, spark=0, intensity=float(scene.intensity), share=0.0,
                                  grow=float(palette["size"]), size_k=float(scene.size_k), scale=float(scale), err=0.0,
                                  u_time=float(scene.last % _TIME_WRAP), glint_k=0.0, streak_k=1.0,
                                  origin=(centre[0] * scale, centre[1] * scale), size_px=(float(W), float(H)))
                        gl.BindVertexArray(self.dispatch_vao)
                        gl.DrawArraysInstanced(5, 0, 4, len(drows) // 11)
                        gl.Disable(0x0BE2)
                if window:
                    gl.BindFramebuffer(0x8CA8, self.out_fbo)
                    gl.BindFramebuffer(0x8CA9, 0)
                    gl.BlitFramebuffer(0, 0, W, H, 0, H, W, 0, 0x4000, 0x2600)
                    gl.BindFramebuffer(0x8D40, 0)
                    self._check("drawing the flipbook surface")
                    return None
                sync = gl.FenceSync(0x9117, 0)
                gl.Flush()
                self._check("drawing the flipbook main window")
                return self._build(tex, sync, W, H)
            reuse_tex = tex
        if self.atlas_texs:
            self._trim_atlases(None)
        self.poll_springs(scene)
        if not self.springs_owned:
            self._upload_springs(scene, scene.last)
        self.step_springs(scene)
        # The fills' colours change only with the palette, the error tint and the intensity: kept between frames.
        key = (palette["alpha_floor"], palette["alpha_gain"], palette["operator"], tuple(palette["tones"]),
               palette["blue"], palette["ember"], palette["spark"], palette["spark_alpha"], scene.err, scene.intensity)
        if self.fill_cache is None or self.fill_cache[0] != key:
            colours, adds = self._fills(palette, scene)
            spark_on = any(colours[-4:])
            self.fill_cache = (key, (ctypes.c_float * len(colours))(*colours), (ctypes.c_int * len(adds))(*adds),
                               spark_on)
        tex = reuse_tex if reuse_tex is not None else (self._window_texture(W, H) if window else self._texture(W, H))
        gl.Disable(0x0B71)
        gl.Disable(0x0C11)  # GL_SCISSOR_TEST
        gl.BindFramebuffer(0x8D40, self.out_fbo)
        gl.FramebufferTexture2D(0x8D40, 0x8CE0, 0x0DE1, tex, 0)
        gl.Viewport(0, 0, W, H)

        if PARTICLE_VARIANT != "baseline":
            if palette["operator"] == cairo.OPERATOR_ADD or scene.dispatch_nova_standin(scene.last):
                # Variants A/B/C dark (or Nova dispatch stand-in): HDR sprites + Kawase bloom + tone map.
                self._draw_soft_hdr(gl, palette, scene, W, H, centre, scale, under, tex)
            else:
                # Variants A/B/C light: direct burnished-amber soft round sprites on GL (premultiplied over).
                self._draw_soft_light(gl, palette, scene, W, H, centre, scale, under, tex)
        else:
            prog = self.dust_prog
            gl.UseProgram(prog)
            twins = [(dx * scale, dy * scale) for dx, dy in palette.get("twins") or ()]
            self._set(prog, share=float(scene.share), grow=float(palette["size"]), t=0.0, scale=float(scale),
                      twins=1 if twins else 0, twin=twins[0] if twins else (0.0, 0.0), size_px=(float(W), float(H)),
                      capacity=self.CAPACITY)
            gl.Uniform4fv(self._u(prog, "regions"), 4, (ctypes.c_float * 16)(-1e9, -1e9, 1e9, 1e9, *[0.0] * 12))
            gl.Uniform2fv(self._u(prog, "origins"), 4, (ctypes.c_float * 8)(centre[0] * scale, centre[1] * scale, *[0.0] * 6))
            gl.Uniform4fv(self._u(prog, "clips"), 4, (ctypes.c_float * 16)(0.0, 0.0, W, H, *[0.0] * 12))
            rx0, ry0, rx1, ry1 = 0, 0, W, H
            gl.UseProgram(self.resolve_prog)
            gl.Uniform4fv(self._u(self.resolve_prog, "colour"), self.FILLS, self.fill_cache[1])
            gl.Uniform1iv(self._u(self.resolve_prog, "add"), self.FILLS, self.fill_cache[2])
            if under is not None:
                image, (ux, uy) = under
                if self.under_key is not image:
                    image.flush()
                    gl.BindTexture(0x0DE1, self.under_tex)
                    gl.PixelStorei(0x0CF2, image.get_stride() // 4)  # GL_UNPACK_ROW_LENGTH
                    pixels = ctypes.c_char.from_buffer(image.get_data())
                    gl.TexImage2D(0x0DE1, 0, 0x8058, image.get_width(), image.get_height(), 0, 0x80E1, 0x1401,
                                  ctypes.addressof(pixels))  # GL_RGBA8 from GL_BGRA bytes, as Cairo keeps them
                    gl.PixelStorei(0x0CF2, 0)
                    self.under_key = image
                self._set(self.resolve_prog, has_under=1, skip_dust=0, under=0, under_at=(ux * scale, uy * scale))
            else:
                self._set(self.resolve_prog, has_under=0, skip_dust=0)
            self._heads(W, H)
            gl.Disable(0x0BE2)
            gl.BindBufferBase(0x90D2, 0, self.count_buf)
            gl.BindBufferBase(0x90D2, 1, self.node_buf)
            gl.BindImageTexture(0, self.head, 0, 0, 0, 0x88BA, 0x8236)
            gl.BindBuffer(0x90D2, self.count_buf)
            gl.BufferSubData(0x90D2, 0, 4, (ctypes.c_uint * 1)(0))
            if rx1 > rx0 and ry1 > ry0:
                gl.ClearTexSubImage(self.head, 0, rx0, ry0, 0, rx1 - rx0, ry1 - ry0, 1, 0x8D94, 0x1405,
                                    (ctypes.c_uint * 1)(0xFFFFFFFF))
            gl.MemoryBarrier(0xFFFFFFFF)
            gl.ColorMask(0, 0, 0, 0)
            gl.UseProgram(prog)
            self._set(prog, mode=1, k=float(scene.intensity * 7))
            gl.BindVertexArray(self.main_vao)
            # Skip the spark pass when no grain qualifies or the spark colour is zero.
            for spark in ((0, 1) if self.spring_sparks and self.fill_cache[3] else (0,)):
                self._set(prog, spark=spark)
                gl.DrawArraysInstanced(5, 0, 4, len(self.spring_idx))
            gl.MemoryBarrier(0xFFFFFFFF)
            gl.ColorMask(1, 1, 1, 1)
            gl.UseProgram(self.resolve_prog)
            if under is not None:
                # Bound only now: making the output texture above binds over texture unit 0.
                gl.ActiveTexture(0x84C0)
                gl.BindTexture(0x0DE1, self.under_tex)
            gl.BindVertexArray(self.empty_vao)
            gl.DrawArrays(5, 0, 4)
            gl.Disable(0x0C11)
            gl.Disable(0x0BE2)
        if self.spring_fence is None:
            # For poll_springs, next frame: a copy of the grains in cached memory, as the chip's own buffer is slow
            # for the processor to read (about 0.8 ms for a scene's grains), and a fence that says it is done.
            size = len(self.spring_idx) * 48
            if size > self.read_size:
                if self.read_buf:
                    gl.DeleteBuffers(1, (ctypes.c_uint * 1)(self.read_buf))
                ids = (ctypes.c_uint * 1)()
                gl.GenBuffers(1, ids)
                self.read_buf, self.read_size = ids[0], size
                gl.BindBuffer(0x8F37, self.read_buf)  # GL_COPY_WRITE_BUFFER
                gl.BufferStorage(0x8F37, size, None, 0x0001 | 0x0200)  # GL_MAP_READ_BIT, GL_CLIENT_STORAGE_BIT
            gl.BindBuffer(0x8F36, self.spring_buf)  # GL_COPY_READ_BUFFER
            gl.BindBuffer(0x8F37, self.read_buf)
            gl.CopyBufferSubData(0x8F36, 0x8F37, 0, 0, size)
            self.spring_fence = gl.FenceSync(0x9117, 0)
        if window:
            # Onto the window, whose rows run from the bottom: the frame is flipped as it is copied.
            gl.BindFramebuffer(0x8CA8, self.out_fbo)  # GL_READ_FRAMEBUFFER
            gl.BindFramebuffer(0x8CA9, 0)  # GL_DRAW_FRAMEBUFFER: the window
            gl.BlitFramebuffer(0, 0, W, H, 0, H, W, 0, 0x4000, 0x2600)  # GL_COLOR_BUFFER_BIT, GL_NEAREST
            gl.BindFramebuffer(0x8D40, 0)
            self._check("drawing the dust surface")
            return None
        sync = gl.FenceSync(0x9117, 0)
        gl.Flush()
        self._check("drawing the main window")
        return self._build(tex, sync, W, H)

    def _window_texture(self, w, h):
        """The dust surface's own frame, drawn here and then copied onto the window; kept from frame to frame."""
        if self.window_size != (w, h):
            if self.window_tex is not None:
                self.gl.DeleteTextures(1, (ctypes.c_uint * 1)(self.window_tex))
            ids = (ctypes.c_uint * 1)()
            self.gl.GenTextures(1, ids)
            self.gl.BindTexture(0x0DE1, ids[0])
            self.gl.TexStorage2D(0x0DE1, 1, 0x8058, w, h)
            self.window_tex, self.window_size = ids[0], (w, h)
        return self.window_tex

    def catch_up(self, scene):
        """Run the steps waiting for the chip now, while no frame is drawn to run them (a locked screen)."""
        self.ctx.make_current()
        try:
            self.step_springs(scene)
            self._check("stepping the springs")
        finally:
            self.ctx.clear_current()

    def _heads(self, w, h):
        """Each pixel's first square in its list (an index into the node buffer), as large as the largest strip so far."""
        gl = self.gl
        if w <= self.head_size[0] and h <= self.head_size[1]:
            return
        w, h = max(w, self.head_size[0]), max(h, self.head_size[1])
        if self.head is not None:
            gl.DeleteTextures(1, (ctypes.c_uint * 1)(self.head))
        else:  # The squares' lists (CAPACITY * 16 bytes, 8 MB) are made on first use: the default look never uses them.
            gl.BindBuffer(0x90D2, self.node_buf)
            gl.BufferData(0x90D2, self.CAPACITY * 16, None, 0x88E8)
        ids = (ctypes.c_uint * 1)()
        gl.GenTextures(1, ids)
        gl.BindTexture(0x0DE1, ids[0])
        gl.TexStorage2D(0x0DE1, 1, 0x8236, w, h)  # GL_R32UI
        self.head, self.head_size = ids[0], (w, h)

    def _texture(self, w, h):
        """A strip's texture: one GSK has let go of, if one fits, or a new one."""
        gl = self.gl
        while self.free:
            tex, sync, size = self.free.pop()
            gl.DeleteSync(sync)
            if size == (w, h):
                return tex
            gl.DeleteTextures(1, (ctypes.c_uint * 1)(tex))
        ids = (ctypes.c_uint * 1)()
        gl.GenTextures(1, ids)
        gl.BindTexture(0x0DE1, ids[0])
        gl.TexStorage2D(0x0DE1, 1, 0x8058, w, h)  # GL_RGBA8
        return ids[0]

    def draw(self, scene, rects, now, centre, scale, clips=None):
        """The strips for the viewer frame at now, as [(texture, where the texture goes, the strip it shows)], each
        (x, y, w, h) in the viewer's coordinates: the texture is drawn where it goes, clipped to the strip. rects are the
        four disjoint assignment regions; clips (defaulting to rects) are the render/clip bounds, widened at strip seams."""
        gl, palette = self.gl, PALETTE
        self.ctx.make_current()
        try:
            return self._draw(gl, palette, scene, rects, now, centre, scale, clips or rects)
        finally:
            self.ctx.clear_current()

    def _draw(self, gl, palette, scene, rects, now, centre, scale, clip_rects):
        self._load_dust(scene, now)
        cx, cy = centre
        settings = scene.frame_settings(now)
        regions = [(rx - cx, ry - cy, rx + rw - cx, ry + rh - cy) for rx, ry, rw, rh in rects]
        twins = [(dx * scale, dy * scale) for dx, dy in palette.get("twins") or ()]
        colours, adds = self._fills(palette, scene)
        spark_on = any(colours[-4:])

        prog = self.dust_prog
        gl.UseProgram(prog)
        self._set(prog, share=float(scene.share), grow=float(palette["size"]), t=float(now - self.epoch),
                  scale=float(scale), twins=1 if twins else 0, twin=twins[0] if twins else (0.0, 0.0))
        self._frame_uniforms(prog, settings)
        gl.Uniform4fv(self._u(prog, "regions"), 4,
                      (ctypes.c_float * 16)(*[v for r in (regions + [(0, 0, 0, 0)] * 4)[:4] for v in r]))
        gl.Uniform1i(self._u(prog, "capacity"), self.CAPACITY)
        gl.UseProgram(self.resolve_prog)
        gl.Uniform4fv(self._u(self.resolve_prog, "colour"), self.FILLS, (ctypes.c_float * len(colours))(*colours))
        gl.Uniform1iv(self._u(self.resolve_prog, "add"), self.FILLS, (ctypes.c_int * len(adds))(*adds))
        self._set(self.resolve_prog, has_under=0, skip_dust=0)

        boxes = []
        for rx, ry, rw, rh in clip_rects:
            if rw <= 0 or rh <= 0:
                boxes.append((0, 0, 0, 0))
                continue
            x0, y0 = math.floor(rx * scale), math.floor(ry * scale)
            boxes.append((x0, y0, max(1, math.ceil((rx + rw) * scale) - x0), max(1, math.ceil((ry + rh) * scale) - y0)))
        (_, _, tw, th), (_, _, bw, bh), (_, _, lw, lh), (_, _, rw_, rh_) = boxes
        places = ((0, 0), (0, th), (0, th + bh), (lw, th + bh))
        w, h = max(tw, bw, lw + rw_, 1), max(th + bh + max(lh, rh_), 1)
        origins, clips = [], []
        for (x0, y0, bw_, bh_), (ax, ay) in zip(boxes, places):
            origins += (cx * scale - x0 + ax, cy * scale - y0 + ay)
            clips += (ax, ay, ax + bw_, ay + bh_)
        self._heads(w, h)
        tex = self._texture(w, h)
        gl.Disable(0x0B71)  # GL_DEPTH_TEST
        gl.Disable(0x0BE2)  # GL_BLEND
        gl.BindBufferBase(0x90D2, 0, self.count_buf)
        gl.BindBufferBase(0x90D2, 1, self.node_buf)
        gl.BindImageTexture(0, self.head, 0, 0, 0, 0x88BA, 0x8236)  # GL_READ_WRITE, GL_R32UI
        gl.BindFramebuffer(0x8D40, self.out_fbo)
        gl.FramebufferTexture2D(0x8D40, 0x8CE0, 0x0DE1, tex, 0)
        gl.Viewport(0, 0, w, h)
        gl.BindBuffer(0x90D2, self.count_buf)
        gl.BufferSubData(0x90D2, 0, 4, (ctypes.c_uint * 1)(0))
        gl.ClearTexSubImage(self.head, 0, 0, 0, 0, w, h, 1, 0x8D94, 0x1405,  # GL_RED_INTEGER, GL_UNSIGNED_INT
                            (ctypes.c_uint * 1)(0xFFFFFFFF))
        gl.MemoryBarrier(0xFFFFFFFF)
        gl.ColorMask(0, 0, 0, 0)
        gl.UseProgram(prog)
        self._set(prog, size_px=(float(w), float(h)), mode=0, k=float(scene.intensity * 7 * scene.dust_vis))
        gl.Uniform2fv(self._u(prog, "origins"), 4, (ctypes.c_float * 8)(*origins))
        gl.Uniform4fv(self._u(prog, "clips"), 4, (ctypes.c_float * 16)(*clips))
        gl.BindVertexArray(self.dust_vao)
        count = min(self.dust_count, scene.dust_count(now))
        for spark in ((0, 1) if self.dust_sparks and spark_on else (0,)):
            self._set(prog, spark=spark)
            gl.DrawArraysInstanced(5, 0, 4, count)  # GL_TRIANGLE_STRIP
        gl.MemoryBarrier(0xFFFFFFFF)
        gl.ColorMask(1, 1, 1, 1)
        gl.UseProgram(self.resolve_prog)
        gl.BindVertexArray(self.empty_vao)
        gl.DrawArrays(5, 0, 4)
        sync = gl.FenceSync(0x9117, 0)  # GL_SYNC_GPU_COMMANDS_COMPLETE
        gl.Flush()
        atlas = self._build(tex, sync, w, h)
        out = [(atlas, ((x0 - ax) / scale, (y0 - ay) / scale, w / scale, h / scale),
                (x0 / scale, y0 / scale, bw_ / scale, bh_ / scale))
               for (x0, y0, bw_, bh_), (ax, ay) in zip(boxes, places) if bw_]
        self._check("drawing the frame")
        return out

    def _build(self, tex, sync, w, h):
        if self.readback is not None:  # Offscreen (themes/forge/dust_preview.py): the frame's pixels, no GDK texture.
            self.gl.BindFramebuffer(0x8D40, self.out_fbo)
            self.gl.ReadPixels(0, 0, w, h, 0x80E1, 0x1401, (ctypes.c_char * (w * h * 4)).from_buffer(self.readback))
            self.free.append((tex, sync, (w, h)))
            return None
        builder = Gdk.GLTextureBuilder()
        builder.set_context(self.ctx)
        builder.set_id(tex)
        builder.set_width(w)
        builder.set_height(h)
        builder.set_format(Gdk.MemoryFormat.R8G8B8A8_PREMULTIPLIED)
        builder.set_sync(sync)
        # GSK lets go of the texture when no frame needs it; the next strips reuse it.
        return builder.build(lambda *_: self.free.append((tex, sync, (w, h))), 1)


class _WlMessage(ctypes.Structure):
    _fields_ = [("name", ctypes.c_char_p), ("signature", ctypes.c_char_p), ("types", ctypes.c_void_p)]


class _WlInterface(ctypes.Structure):
    _fields_ = [("name", ctypes.c_char_p), ("version", ctypes.c_int), ("method_count", ctypes.c_int),
                ("methods", ctypes.c_void_p), ("event_count", ctypes.c_int), ("events", ctypes.c_void_p)]


class _Wayland:
    """The parts of libwayland-client, libwayland-egl and libEGL the dust surface uses, through ctypes, with the
    core interfaces libwayland-client exports and wp_viewporter (stable, but not exported) written out here."""

    def __init__(self):
        wl = self.wl = ctypes.CDLL("libwayland-client.so.0")
        vp, u32, ci = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int
        for name, res, args in (("wl_display_create_queue", vp, [vp]), ("wl_event_queue_destroy", None, [vp]),
                                ("wl_proxy_create_wrapper", vp, [vp]), ("wl_proxy_wrapper_destroy", None, [vp]),
                                ("wl_proxy_set_queue", None, [vp, vp]), ("wl_proxy_get_version", u32, [vp]),
                                ("wl_proxy_add_listener", ci, [vp, vp, vp]), ("wl_proxy_destroy", None, [vp]),
                                ("wl_display_roundtrip_queue", ci, [vp, vp]),
                                ("wl_display_dispatch_queue_pending", ci, [vp, vp]),
                                ("wl_display_prepare_read_queue", ci, [vp, vp]), ("wl_display_read_events", ci, [vp]),
                                ("wl_display_cancel_read", None, [vp]), ("wl_display_get_fd", ci, [vp]),
                                ("wl_display_flush", ci, [vp]), ("wl_display_get_error", ci, [vp])):
            fn = getattr(wl, name)
            fn.restype, fn.argtypes = res, args
        self.marshal = wl.wl_proxy_marshal_flags
        self.marshal.restype = vp
        self.iface = {n: ctypes.addressof(ctypes.c_void_p.in_dll(wl, f"wl_{n}_interface"))
                      for n in ("registry", "compositor", "subcompositor", "surface", "subsurface", "region",
                                "callback")}
        # wp_viewporter: destroy, get_viewport(new_id wp_viewport, object wl_surface). wp_viewport: destroy,
        # set_source(fixed x4), set_destination(int, int). Neither has events.
        self.viewport_iface, self.viewporter_iface = _WlInterface(), _WlInterface()
        none = (ctypes.c_void_p * 4)()
        get_types = (ctypes.c_void_p * 2)(ctypes.addressof(self.viewport_iface), self.iface["surface"])
        self._keep = [none, get_types]
        viewport_msgs = (_WlMessage * 3)((b"destroy", b"", ctypes.addressof(none)),
                                         (b"set_source", b"ffff", ctypes.addressof(none)),
                                         (b"set_destination", b"ii", ctypes.addressof(none)))
        viewporter_msgs = (_WlMessage * 2)((b"destroy", b"", ctypes.addressof(none)),
                                           (b"get_viewport", b"no", ctypes.addressof(get_types)))
        self._keep += [viewport_msgs, viewporter_msgs]
        self.viewport_iface.name, self.viewport_iface.version = b"wp_viewport", 1
        self.viewport_iface.method_count, self.viewport_iface.methods = 3, ctypes.addressof(viewport_msgs)
        self.viewporter_iface.name, self.viewporter_iface.version = b"wp_viewporter", 1
        self.viewporter_iface.method_count, self.viewporter_iface.methods = 2, ctypes.addressof(viewporter_msgs)
        self.iface["viewport"] = ctypes.addressof(self.viewport_iface)
        self.iface["viewporter"] = ctypes.addressof(self.viewporter_iface)
        self.wlegl = ctypes.CDLL("libwayland-egl.so.1")
        self.wlegl.wl_egl_window_create.restype = vp
        self.wlegl.wl_egl_window_create.argtypes = [vp, ci, ci]
        self.wlegl.wl_egl_window_resize.argtypes = [vp, ci, ci, ci, ci]
        self.wlegl.wl_egl_window_destroy.argtypes = [vp]
        egl = self.egl = ctypes.CDLL("libEGL.so.1")
        for name, res, args in (("eglGetPlatformDisplay", vp, [ctypes.c_uint, vp, vp]),
                                ("eglInitialize", ctypes.c_uint, [vp, vp, vp]), ("eglBindAPI", ctypes.c_uint, [ctypes.c_uint]),
                                ("eglChooseConfig", ctypes.c_uint, [vp, vp, vp, ci, vp]),
                                ("eglCreateContext", vp, [vp, vp, vp, vp]),
                                ("eglCreatePlatformWindowSurface", vp, [vp, vp, vp, vp]),
                                ("eglMakeCurrent", ctypes.c_uint, [vp, vp, vp, vp]),
                                ("eglSwapInterval", ctypes.c_uint, [vp, ci]), ("eglSwapBuffers", ctypes.c_uint, [vp, vp]),
                                ("eglDestroySurface", ctypes.c_uint, [vp, vp]),
                                ("eglDestroyContext", ctypes.c_uint, [vp, vp]), ("eglGetError", ctypes.c_int, [])):
            fn = getattr(egl, name)
            fn.restype, fn.argtypes = res, args

    def call(self, proxy, opcode, *args, iface=None, version=None, flags=0):
        """wl_proxy_marshal_flags: a request on proxy; with iface, the new object it creates."""
        version = self.wl.wl_proxy_get_version(proxy) if version is None else version
        return self.marshal(ctypes.c_void_p(proxy), ctypes.c_uint32(opcode),
                            ctypes.c_void_p(self.iface[iface] if iface else None), ctypes.c_uint32(version),
                            ctypes.c_uint32(flags), *args)


class _EGLContext:
    """The dust surface's own GL context, on GDK's Wayland display, with make_current and clear_current as a
    GdkGLContext has, so _DustGL draws with it. GDK's own idea of the current context is cleared first."""

    def __init__(self, way, edpy, ctx, surface):
        self.way, self.edpy, self.context, self.surface = way, edpy, ctx, surface

    def make_current(self):
        Gdk.GLContext.clear_current()
        if not self.way.egl.eglMakeCurrent(self.edpy, self.surface, self.surface, self.context):
            raise RuntimeError(f"eglMakeCurrent failed ({self.way.egl.eglGetError():#x})")

    def clear_current(self):
        self.way.egl.eglMakeCurrent(self.edpy, None, None, None)


class _DustSurface:
    """The main window's dust on a Wayland surface of its own: a subsurface just below the window's surface, drawn by
    the GPU through EGL (the same GL frame as _DustGL.draw_main), on its own frame callbacks. GTK then draws only
    the text, and its frame clock stays idle while only the dust moves. The subsurface moves, shows and hides with
    the window. Any failure tears it down; the overlay then draws the dust in GTK (see Overlay._surface_down)."""

    def __init__(self, overlay):
        self.overlay = overlay
        way = self.way = _Wayland()
        gtk = ctypes.CDLL("libgtk-4.so.1")
        gtk.gdk_wayland_display_get_wl_display.restype = ctypes.c_void_p
        gtk.gdk_wayland_display_get_wl_display.argtypes = [ctypes.c_void_p]
        gtk.gdk_wayland_surface_get_wl_surface.restype = ctypes.c_void_p
        gtk.gdk_wayland_surface_get_wl_surface.argtypes = [ctypes.c_void_p]

        def gobject(obj):  # PyGObject keeps the GObject pointer right after PyObject_HEAD.
            return ctypes.c_void_p.from_address(id(obj) + 16).value

        win = overlay.win
        self.display = gtk.gdk_wayland_display_get_wl_display(gobject(win.get_display()))
        self.parent = gtk.gdk_wayland_surface_get_wl_surface(gobject(win.get_surface()))
        if not self.display or not self.parent:
            raise RuntimeError("no Wayland display or window surface")
        wl = way.wl
        self.queue = wl.wl_display_create_queue(self.display)
        self.objects = {}
        wrapper = wl.wl_proxy_create_wrapper(self.display)
        wl.wl_proxy_set_queue(wrapper, self.queue)
        registry = way.call(wrapper, 1, None, iface="registry")
        wl.wl_proxy_wrapper_destroy(wrapper)
        found = {}

        def on_global(_data, _reg, name, interface, version):
            try:  # An exception must never leave a ctypes callback.
                found[interface.decode()] = (name, version)
            except Exception:  # noqa: BLE001
                pass

        self._global = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p,
                                        ctypes.c_uint32)(on_global)
        self._remove = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32)(lambda *_: None)
        self._registry_listener = (ctypes.c_void_p * 2)(ctypes.cast(self._global, ctypes.c_void_p),
                                                        ctypes.cast(self._remove, ctypes.c_void_p))
        wl.wl_proxy_add_listener(registry, self._registry_listener, None)
        wl.wl_display_roundtrip_queue(self.display, self.queue)
        for need in ("wl_compositor", "wl_subcompositor", "wp_viewporter"):
            if need not in found:
                raise RuntimeError(f"the compositor offers no {need}")

        def bind(interface, version):
            name, offered = found[interface]
            v = min(version, offered)
            return way.call(registry, 0, ctypes.c_uint32(name), ctypes.c_char_p(interface.encode()), ctypes.c_uint32(v),
                            None, iface=interface.split("_", 1)[1], version=v)

        self.compositor = bind("wl_compositor", 4)
        self.subcompositor = bind("wl_subcompositor", 1)
        self.viewporter = bind("wp_viewporter", 1)
        self.registry = registry
        # The window's surface, as a wrapper on this queue: the frame callbacks are asked of it (see _next_frame).
        self.window_surface = wl.wl_proxy_create_wrapper(self.parent)
        wl.wl_proxy_set_queue(self.window_surface, self.queue)
        self.surface = way.call(self.compositor, 0, None, iface="surface")
        self.sub = way.call(self.subcompositor, 1, None, ctypes.c_void_p(self.surface), ctypes.c_void_p(self.parent),
                            iface="subsurface")
        way.call(self.sub, 3, ctypes.c_void_p(self.parent))  # place_below: the text stays on top.
        # The subsurface stays synchronized: each frame commits the window's surface after its own (_next_frame), so
        # Hyprland applies both at once, buffer ready, and draws them.
        region = way.call(self.compositor, 1, None, iface="region")
        way.call(self.surface, 5, ctypes.c_void_p(region))  # set_input_region: empty, so input reaches the window.
        way.call(region, 0, flags=1)  # destroy
        self.viewport = way.call(self.viewporter, 1, None, ctypes.c_void_p(self.surface), iface="viewport")
        # EGL: desktop GL 4.4 core, as _DustGL needs, on the same display GDK uses.
        egl = way.egl
        self.edpy = egl.eglGetPlatformDisplay(0x31D8, self.display, None)  # EGL_PLATFORM_WAYLAND_KHR
        if not self.edpy or not egl.eglInitialize(self.edpy, None, None):
            raise RuntimeError("EGL would not start on the Wayland display")
        egl.eglBindAPI(0x30A2)  # EGL_OPENGL_API
        attrs = (ctypes.c_int * 15)(0x3033, 0x0004, 0x3024, 8, 0x3023, 8, 0x3022, 8, 0x3021, 8, 0x3040, 0x0008,
                                    0x3038, 0, 0)  # a window, RGBA8, OpenGL
        config, count = ctypes.c_void_p(), ctypes.c_int()
        if not egl.eglChooseConfig(self.edpy, attrs, ctypes.byref(config), 1, ctypes.byref(count)) or not count.value:
            raise RuntimeError("no EGL configuration with alpha")
        self.size, self.scale, self.at = (1, 1), 1.0, (0, 0)
        self.window = way.wlegl.wl_egl_window_create(self.surface, 1, 1)
        self.esurf = egl.eglCreatePlatformWindowSurface(self.edpy, config, self.window, None)
        context = egl.eglCreateContext(self.edpy, config, None, (ctypes.c_int * 7)(
            0x3098, 4, 0x30FB, 4, 0x30FD, 0x1, 0x3038))  # version 4.4, core profile
        if not self.esurf or not context:
            raise RuntimeError(f"EGL surface or context failed ({egl.eglGetError():#x})")
        self.ctx = _EGLContext(way, self.edpy, context, self.esurf)
        self.ctx.make_current()
        egl.eglSwapInterval(self.edpy, 0)  # Frames go on the frame callbacks below, never blocking.
        self.gl = _DustGL(None, self.ctx)
        self.ctx.make_current()
        # The frame callback waiting for the compositor (one at a time), whether it has come, and whether the surface
        # is torn down (then nothing touches the queue, the surface or the context again).
        self.callback, self.frame_due, self.dead, self.broken, self.ticks, self.id = None, False, False, None, {}, 0
        self._done = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32)(self._frame_done)
        self._frame_listener = (ctypes.c_void_p * 1)(ctypes.cast(self._done, ctypes.c_void_p))
        self.ctx.clear_current()
        self.log, self.logged_at = (open(DUST_FRAMES, "a", buffering=1) if DUST_FRAMES else None), None
        self.source = _QueueSource(self)
        self.source.attach(None)
        wl.wl_display_flush(self.display)
        self.drained = threading.Event()  # pump has emptied the queue: _read may read again.
        self.reader = threading.Thread(target=self._read, name="dust-surface-reader", daemon=True)
        self.reader.start()

    # ---- the frame clock: GTK's add_tick_callback and remove_tick_callback, on the surface's frame callbacks ----
    def add_tick_callback(self, fn):
        self.id += 1
        self.ticks[self.id] = fn
        if self.callback is None and not self.dead:
            try:
                self._next_frame()  # Start the frame callbacks.
                self.way.wl.wl_display_flush(self.display)
            except Exception as error:  # noqa: BLE001 - frame() tears the surface down on the next turn.
                self.broken, self.frame_due = f"asking for a frame failed: {error}", True
        return self.id

    def remove_tick_callback(self, tick_id):
        self.ticks.pop(tick_id, None)

    def _read(self):
        """A thread that reads the display for this surface's queue and wakes the main loop. Other threads read the
        display too (Mesa's Vulkan presents for GTK), and an event they read leaves no sign on the socket, so the
        main loop alone could sleep on a frame callback that has come. This thread never dispatches: pump does,
        on the main loop. It holds a read for at most 50 ms, and close() stops it before the queue goes."""
        wl, context = self.way.wl, GLib.MainContext.default()
        fd = wl.wl_display_get_fd(self.display)
        while not self.dead:
            self.drained.clear()
            if wl.wl_display_prepare_read_queue(self.display, self.queue) != 0:
                context.wakeup()  # Events wait in the queue for pump.
                self.drained.wait(0.05)
                continue
            try:
                ready = select.select([fd], [], [], 0.05)[0]
            except (OSError, ValueError):
                ready = []
            if ready and not self.dead:
                wl.wl_display_read_events(self.display)
                context.wakeup()
            else:
                wl.wl_display_cancel_read(self.display)

    def pump(self):
        """Run the frame callbacks already read into this surface's queue (by _read, GDK or Mesa), from
        _QueueSource on every turn of the main loop. True when a frame is due."""
        if not self.dead and self.way.wl.wl_display_dispatch_queue_pending(self.display, self.queue) < 0:
            self.broken = f"the display failed (error {self.way.wl.wl_display_get_error(self.display)})"
            self.frame_due = True  # frame() tears the surface down, outside this dispatch.
        self.drained.set()
        return self.frame_due and not self.dead

    def _frame_done(self, _data, callback, _time):
        """The compositor's frame callback (a ctypes callback inside pump): only note it; the frame runs from
        _QueueSource, outside libwayland's dispatch, so a failure there can tear the surface down safely."""
        try:
            self.way.wl.wl_proxy_destroy(callback)
            if callback == self.callback:
                self.callback = None
            self.frame_due = True
        except Exception:  # noqa: BLE001 - an exception must never leave a ctypes callback.
            pass

    def frame(self):
        """A frame of the display: run the ticks; if none drew, ask for the next frame all the same."""
        self.frame_due = False
        try:
            if self.broken:
                raise RuntimeError(self.broken)
            for tick_id, fn in list(self.ticks.items()):
                if self.dead:
                    return
                if not fn(self, None):
                    self.ticks.pop(tick_id, None)
            if self.ticks and not self.dead and self.callback is None:
                self._next_frame()
                self.way.wl.wl_display_flush(self.display)
        except Exception as error:  # noqa: BLE001 - any failure: GTK draws the dust from here on.
            if not self.dead:
                self.overlay._surface_down("the dust surface's frame failed", error)

    # ---- drawing ----
    presented, last = 0, None

    def place(self, x, y, w, h, scale):
        """Where the window's drawing area lies in the window, its size in logical pixels, and the window's scale."""
        size = (max(1, math.ceil(w * scale)), max(1, math.ceil(h * scale)))
        if (round(x), round(y)) != self.at:
            self.at = (round(x), round(y))
            self.way.call(self.sub, 1, ctypes.c_int32(self.at[0]), ctypes.c_int32(self.at[1]))  # set_position
        if size != self.size or scale != self.scale or (w, h) != getattr(self, "logical", None):
            self.size, self.scale, self.logical = size, scale, (w, h)
            self.way.wlegl.wl_egl_window_resize(self.window, size[0], size[1], 0, 0)
            self.way.call(self.viewport, 2, ctypes.c_int32(max(1, round(w))), ctypes.c_int32(max(1, round(h))))

    def present(self, draw):
        """One frame: draw (a function that draws with self.gl into the window), or nothing at all (a clear frame),
        then the swap, which commits the subsurface, and _next_frame."""
        if self.dead:
            return
        start = time.monotonic()
        self.ctx.make_current()
        try:
            self.last = draw
            if draw is None:
                gl = self.gl.gl
                gl.BindFramebuffer(0x8D40, 0)
                gl.Viewport(0, 0, *self.size)
                gl.ClearColor(0, 0, 0, 0)
                gl.Clear(0x4000)
            else:
                draw(self.gl)
                self.ctx.make_current()  # draw_main lets go of the context; the swap needs it.
            if not self.way.egl.eglSwapBuffers(self.edpy, self.esurf):
                raise RuntimeError(f"eglSwapBuffers failed ({self.way.egl.eglGetError():#x})")
            self._next_frame()
            self.presented += 1
        finally:
            self.ctx.clear_current()
            Gdk.GLContext.clear_current()
        self.way.wl.wl_display_flush(self.display)
        if self.log is not None:
            end = time.monotonic()
            gap = (start - self.logged_at) * 1000 if self.logged_at is not None else 0.0
            self.log.write(f"{start:.4f} gap {gap:.2f} ms, took {(end - start) * 1000:.2f} ms, "
                           f"{'clear' if draw is None else 'tick'}\n")
            self.logged_at = start

    def _next_frame(self):
        """A frame callback for the next frame (unless one is on its way), and a commit of the window's surface.
        Hyprland (0.56) takes no damage from a layer surface's subsurfaces, and drops a bare damage that comes while a
        page flip is pending. So the subsurface stays synchronized, the frame callback is asked of the window's
        surface, and the window's surface is committed after the subsurface: Hyprland applies both at once and
        schedules the frame as for any surface that waits on a callback. GTK leaves nothing pending between its own
        frames, so this commit carries only the subsurface's frame and position."""
        if self.callback is None:
            callback = self.way.call(self.window_surface, 3, None, iface="callback")  # frame
            if not callback:
                raise RuntimeError("the compositor gave no frame callback")
            self.callback = callback
            self.way.wl.wl_proxy_add_listener(callback, self._frame_listener, None)
        self.way.call(self.window_surface, 6)  # wl_surface.commit

    def close(self):
        """Tear the surface down, quietly: each step may fail if the window or the display is already gone. From
        here on nothing touches the queue, the surface or the context: the frame callback goes before the queue,
        and the queue is never dispatched again."""
        if self.dead:
            return
        self.dead = True
        self.ticks.clear()
        way, wl = self.way, self.way.wl
        callback, self.callback = self.callback, None
        for step in (lambda: self.source.destroy(), lambda: self.reader.join(1.0),
                     lambda: wl.wl_proxy_destroy(callback) if callback else None,
                     lambda: wl.wl_proxy_wrapper_destroy(self.window_surface),
                     lambda: self.log.close() if self.log is not None else None,
                     lambda: self.ctx.clear_current(),
                     lambda: way.egl.eglDestroySurface(self.edpy, self.esurf),
                     lambda: way.egl.eglDestroyContext(self.edpy, self.ctx.context),
                     lambda: way.wlegl.wl_egl_window_destroy(self.window),
                     lambda: way.call(self.viewport, 0, flags=1), lambda: way.call(self.sub, 0, flags=1),
                     lambda: way.call(self.surface, 0, flags=1), lambda: way.call(self.viewporter, 0, flags=1),
                     lambda: way.call(self.subcompositor, 0, flags=1), lambda: wl.wl_proxy_destroy(self.compositor),
                     lambda: wl.wl_proxy_destroy(self.registry), lambda: wl.wl_display_flush(self.display),
                     lambda: wl.wl_event_queue_destroy(self.queue)):
            try:
                step()
            except Exception:  # noqa: BLE001 - tearing down; the rest still runs.
                pass
        Gdk.GLContext.clear_current()


class _QueueSource(GLib.Source):
    """Runs the dust surface's frames from the main loop: it looks at the surface's queue on every turn (see
    _DustSurface.pump), and runs the frame outside libwayland's dispatch."""

    def __init__(self, surface):
        super().__init__()
        self.surface = surface

    def prepare(self):
        return self.surface.pump(), -1

    def check(self):
        return self.surface.pump()

    def dispatch(self, _callback, _args):
        self.surface.frame()
        return True


class _ViewerArea(Gtk.Widget):
    """The viewer window's one widget. It composes each frame as render nodes (see Overlay._snapshot_viewer): the
    black box and the media are drawn by the GPU, and only the dust is drawn with Cairo, around the box's edge."""

    def __init__(self, app):
        super().__init__()
        self.app = app

    def do_snapshot(self, snapshot):
        self.app._snapshot_viewer(snapshot, self.get_width(), self.get_height())


class _MainArea(Gtk.DrawingArea):
    """The main window's drawing area. While the chip runs the grains' springs, it draws them with GL (see
    Overlay._snapshot_main); otherwise it draws with Cairo, as any drawing area does."""

    def __init__(self, app, **props):
        super().__init__(**props)
        self.app = app

    def do_snapshot(self, snapshot):
        if not self.app._snapshot_main(snapshot, self.get_width(), self.get_height()):
            Gtk.DrawingArea.do_snapshot(self, snapshot)


class Overlay(Gtk.Application):
    def __init__(self, demo=False, theme=None, wow=False, pack=None):
        super().__init__(flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.demo = demo
        self.theme = theme  # "light" or "dark" from --theme; None follows the desktop.
        self.wow = wow  # WoW mode: show in the game too, placed and drawn as WoWFriend's overlay was.
        self._initial_pack = pack
        self._followed = "dark"  # The theme from --theme or the desktop; WoW mode draws the game in the dark look.
        self._interface = None
        self._theme_shown = None  # The theme last applied and logged.
        self.spoken = ""
        self.details = ""  # This turn's written answer; it makes the captions clickable.
        # The last written answer, kept across turns so the resting loop can reopen it, and its panel.
        self.answer = ""  # The answer the panel shows: the newest, or an older one the arrows stepped back to.
        self.answers = []  # The last ANSWER_HISTORY answers, oldest first.
        self.answer_at = 0  # Where self.answer is in self.answers.
        self.answer_open = False
        self.answer_mix = 0.0
        self.answer_win = None
        # The stage host, when the stage setting is on, and whether it shows the panel.
        self.stage_on = False
        self.stage = stage_link.StageLink(self._from_stage)
        self._stage_panel = False
        self._answer_shown = None  # The answer the panel holds now.
        self._answer_size = None  # ((answer, width), content height), so dragging does not lay the answer out again.
        self._answer_xy = (0, 0)
        self.panel_pos = None  # Where the owner dragged the panel, kept until Rook restarts.
        self._drag = None
        self.bounds = None
        self.opacity = 0.0
        self.card_mix = 0.0
        self.quitting = False
        self.hovered = False
        self.scene = Scene(time.monotonic())
        if self._initial_pack:
            self.scene.set_pack(self._initial_pack, self.scene.last)
        self._render_seq, self._render_queue = 0, []
        self._staged = None  # (request id, scene, form) of a baked scene that waits for Rook's reveal.
        self._name_textures = {}  # A constellation's names as textures, per text, scale and lettering.
        self._probe_cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1))
        self.monitor = self.left = self.top = None
        # True while the WoW window is focused. Without WoW mode Rook then hides everything, because WoW's own
        # overlay takes over; in WoW mode Rook is that overlay.
        self.game_focused = False
        self.in_game = False  # WoW mode: placed inside the game window, so drawn in the game's dark look.
        self.dark = False  # Rook is dark: hidden whenever no turn shows.
        self.reader = self.reader_box = None
        self.reader_ready = False
        self._buffer = b""
        self._region_key = None
        self._caption_drawn = False
        self._caption_key = None  # What the caption area last queued to draw.
        self._caption_h = CAPTION_H  # The caption area's height: taller while a code guide shows in a turn.
        self._tick_ms = TICK_MS  # The tick timer's interval now; see _again.
        self._viewer_clock = None  # The frame clock callback while one drives the ticks; see _clock_tick.
        self._clock_on = None  # The widget whose frame clock that is.
        self._clock_at = -math.inf  # When it last ran a tick.
        self._clock_ran = False  # Whether it has run one since the standby timer last looked; see _tick.
        self._timer = 0  # The tick timer's source; see _again.
        self._shown_at = -math.inf  # When the main window last drew; it draws on every tick while shown. See _pace.
        self._home_was = None
        self._focus_sock = None
        self._focus_buffer = b""
        # Dragging Rook aside: its home margins, the drag in progress, when it flies home, and the flight's surface box.
        self.home_xy = None
        self.carry = None
        self.return_at = None
        self.flight = None
        # When the window last mapped, and a pending placement after the monitors changed.
        self._mapped_at = 0.0
        self._replace_pending = None
        # A monitor focus change during a turn: the monitor's name, and the timer that waits for it to settle.
        self._focus_name = None
        self._focus_why = ""
        self._focus_move = None
        # The media viewer: its window, the media showing, the one it replaces while that leaves, the line under the
        # box, the file being checked and decoded in a worker thread, and when a video ended.
        self.viewer = None
        self.viewer_ready = False
        self._viewer_hover = self._scrubbing = False  # The pointer is over the box or its controls; a scrub drags.
        self._viewer_hover_until = 0.0  # After the pointer leaves, the controls stay until this monotonic time.
        self._close_hot = False  # The pointer is on the close X, which then shows its ring.
        self.media = self.media_leaving = None
        self._video_clock = None  # The viewer's frame clock callback while a video plays; see _video_frame.
        self._edges = None  # The open viewer's dust strips as render nodes, kept until the dust moves.
        self._dust_gl = None  # The GL frame (_DustGL) once made, when VIEW_DUST is "gl"; False once it has failed.
        self._surface = None  # The dust surface (_DustSurface) while it is up; see DUST_SURFACE.
        self._labels = None  # The labels over the chip's grains, as (key, texture); see _append_labels.
        self._surface_lost = False  # True after a failure, until the next placement tries the surface again.
        self._text_key = None  # What the main window's text showed when GTK last drew it, while the surface draws dust.
        self.scene.spring_back = self._spring_back
        self.media_path = self.media_title = ""
        self.media_paused = False
        self._media_job, self._media_loaded = 0, None
        self._media_ended_at = None
        self._viewer_region = None

    # ---- window ----
    def do_activate(self):
        Gtk.Settings.get_default().props.gtk_interface_color_scheme = Gtk.InterfaceColorScheme.DARK
        self._build_window()
        self._build_answer()
        self._build_reader()
        self._build_viewer()
        if self.theme:
            self._followed = self.theme
            self._set_theme(self._theme_now())
        else:
            self._watch_theme()
        _no_layer_anim("Rook started")  # Before the window first maps, so the rule holds from its first frame.
        self._place("Rook started")
        if not self.demo:
            self._watch_focus()
            self.win.get_display().get_monitors().connect("items-changed", self._monitors_changed)
            GLib.timeout_add_seconds(10, self._check_screen)
            GLib.timeout_add_seconds(1, self._check_focus)
        self._apply_state()
        self.win.set_visible(False)

        if self.demo:
            self._run_demo()
        else:
            GLib.unix_fd_add_full(GLib.PRIORITY_DEFAULT, sys.stdin.fileno(), GLib.IO_IN | GLib.IO_HUP, self._on_stdin)
        # Building every form up front (about 150 ms, most of it the send forms) keeps a first-time form from stalling
        # a frame.
        for name in [*SHAPES, *SPIN, "cloud", "sink", "rows", FORM_FOR_STATE["listening"], *devs_pack.SEND_FORMS]:
            _form(name)
        self._timer = GLib.timeout_add(TICK_MS, self._tick)
        self.hold()

    def _build_window(self):
        win = Gtk.ApplicationWindow(application=self)
        win.set_default_size(WIDTH, -1)
        win.set_resizable(False)
        LayerShell.init_for_window(win)
        LayerShell.set_namespace(win, "rook-overlay")
        LayerShell.set_layer(win, LayerShell.Layer.OVERLAY)
        LayerShell.set_keyboard_mode(win, LayerShell.KeyboardMode.NONE)

        # The only CSS: a transparent window so the Cairo orb floats over the desktop.
        css = Gtk.CssProvider()
        css.load_from_string("window.rook { background: transparent; }" + _term_css())
        Gtk.StyleContext.add_provider_for_display(win.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        win.add_css_class("rook")

        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        column.set_size_request(WIDTH, -1)
        self.column = column
        self._win_width = WIDTH
        self._dispatch_cx = None  # The presence's x in the window while it is wider for a fan (None: WIDTH / 2).
        self._widen_to = None  # A wider window's (left margin, presence x), held until GTK has laid the width out.
        self._centred = False  # The compositor centres the window (no left anchor): a fan widens it about Rook.
        # See _trace_send; False keeps the trace off.
        self._trace, self._trace_end, self._trace_hypr, self._drawn = None if SEND_TRACE_ON else False, None, 0, None
        motion = Gtk.EventControllerMotion()
        motion.connect("enter", lambda *_: self._hover(True))
        motion.connect("leave", lambda *_: self._hover(False))
        column.add_controller(motion)
        self.area = _MainArea(self, content_width=ORB_W, content_height=self.scene.lift + ORB_H,
                              halign=Gtk.Align.CENTER)
        self.area.set_draw_func(self._draw_main)
        loop_drag = Gtk.GestureDrag()
        loop_drag.connect("drag-begin", self._carry_begin)
        loop_drag.connect("drag-update", self._carry_update)
        loop_drag.connect("drag-end", self._carry_end)
        self.area.add_controller(loop_drag)
        # Shift+right-click on the resting loop arms or disarms the video-recording debug replay (rook.py).
        replay_click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        replay_click.connect("released", self._replay_clicked)
        self.area.add_controller(replay_click)
        loop_motion = Gtk.EventControllerMotion()
        loop_motion.connect("motion", lambda _c, x, y: self._loop_pointer(x, y))
        loop_motion.connect("leave", lambda *_: self._loop_pointer(-1, -1))
        self.area.add_controller(loop_motion)
        column.append(self.area)

        # The card and the answer panel (in its default place) cover the caption area; the captions dim under them.
        lower = Gtk.Overlay(halign=Gtk.Align.CENTER)
        self.caption_area = Gtk.DrawingArea(content_width=WIDTH, content_height=CAPTION_H)
        # While the viewer has faded the main swarm out, it draws the captions under its box instead.
        self.caption_area.set_draw_func(
            lambda _a, cr, w, _h: self.scene.swarm_vis <= 0.002 or self._draw_captions(cr, w))
        caption_click = Gtk.GestureClick()
        caption_click.connect("released", self._caption_clicked)
        self.caption_area.add_controller(caption_click)
        caption_motion = Gtk.EventControllerMotion()
        caption_motion.connect("enter", lambda *_: setattr(self.scene, "caption_hint", True))
        caption_motion.connect("leave", lambda *_: setattr(self.scene, "caption_hint", False))
        self.caption_area.add_controller(caption_motion)
        lower.set_child(self.caption_area)
        stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, halign=Gtk.Align.CENTER,
                        valign=Gtk.Align.START)

        # Card: a Cairo-painted panel under default-theme widgets, for the Stop button and the permission form.
        self.card = Gtk.Overlay(margin_start=12, margin_end=12, halign=Gtk.Align.CENTER)
        panel = Gtk.DrawingArea()
        panel.set_draw_func(self._draw_panel)
        self.card.set_child(panel)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["rook-card"])
        for side in ("top", "bottom", "start", "end"):
            getattr(body, f"set_margin_{side}")(14)
        self.spoken_label = Gtk.Label(wrap=True, xalign=0, max_width_chars=48, css_classes=["card-text"])
        body.append(self.spoken_label)
        self.stop_btn = self._button("Stop", self._stop)
        self.stop_btn.set_halign(Gtk.Align.CENTER)
        body.append(self.stop_btn)
        self.permission_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        # What the tool would do, shown when the request has no questions to answer.
        self.request_label = Gtk.Label(wrap=True, xalign=0, yalign=0, max_width_chars=60,
                                       css_classes=["card-text"])
        self.request_view = Gtk.ScrolledWindow(child=self.request_label, propagate_natural_height=True,
                                               propagate_natural_width=True, max_content_height=320)
        self.request_view.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.permission_box.append(self.request_view)
        self.permission_fields = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, visible=False)
        self.permission_box.append(self.permission_fields)
        permission_row = Gtk.Box(spacing=6)
        self.allow_btn = self._button("Allow", lambda *_: self._permission(True))
        self.allow_btn.add_css_class("primary")  # The card's gold marks Allow as the main choice.
        permission_row.append(self.allow_btn)
        self.decline_btn = self._button("Decline", lambda *_: self._permission(False))
        permission_row.append(self.decline_btn)
        self.permission_box.append(permission_row)
        self.permission_row, self.card_body, self.card_panel = permission_row, body, panel
        # The Devs card (see _CardFace) draws its headline, request and button faces itself. The request scrolls when
        # long, and the buttons are real buttons, live from the start.
        self.face, self.card_details, self.card_at, self._card_breath = None, "", 0.0, 0.0
        self.devs_head = Gtk.DrawingArea(content_width=CARD_W - 2 * CARD_PAD, visible=False)
        self.devs_head.set_draw_func(lambda _a, cr, _w, _h: self._devs_draw(_CardFace.draw_headline, cr,
                                                                            self._card_t()))
        self.devs_request = Gtk.DrawingArea(content_width=CARD_W - 2 * CARD_PAD)
        self.devs_request.set_draw_func(lambda _a, cr, _w, _h: self._devs_draw(
            _CardFace.draw_request, cr, self._card_t(), *self._request_in_view()))
        self.devs_request_view = Gtk.ScrolledWindow(child=self.devs_request, propagate_natural_height=True,
                                                    max_content_height=320, visible=False)
        self.devs_request_view.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.devs_request_view.get_vadjustment().connect("value-changed", lambda *_: self.devs_request.queue_draw())
        self.permission_box.prepend(self.devs_request_view)
        self.permission_box.prepend(self.devs_head)
        self.devs_row = Gtk.Box(spacing=8, halign=Gtk.Align.END, margin_top=10, visible=False)
        self.devs_buttons = []
        for primary in (False, True):  # Decline, then Allow at the right.
            face = Gtk.DrawingArea(content_height=25)
            button = Gtk.Button(child=face, focusable=False, focus_on_click=False, css_classes=["devs-face"])
            button.connect("clicked", lambda *_, allow=primary: self._permission(allow))
            button.connect("state-flags-changed", lambda *_, area=face: area.queue_draw())
            face.set_draw_func(lambda _a, cr, _w, _h, b=button, p=primary: self._devs_draw(
                _CardFace.draw_button, cr, p, self._card_t(), bool(b.get_state_flags() & Gtk.StateFlags.PRELIGHT)))
            self.devs_row.append(button)
            self.devs_buttons.append(face)
        self.permission_box.append(self.devs_row)
        body.append(self.permission_box)
        self.answer_fields = []
        self.card_id = None  # The id of the card on show, which its answer names.
        self.card.add_overlay(body)
        self.card.set_measure_overlay(body, True)
        stack.append(self.card)

        lower.add_overlay(stack)
        lower.set_measure_overlay(stack, True)
        column.append(lower)

        win.set_child(column)
        win.connect("map", lambda *_: setattr(self, "_region_key", None))
        win.connect("map", lambda *_: setattr(self, "_mapped_at", time.monotonic()))
        if DUST_SURFACE:
            win.connect("map", lambda *_: GLib.idle_add(self._surface_up, "the window was placed"))
            win.connect("unmap", lambda *_: self._surface_down("the window was taken off the screen"))
        self.win = win

    def _place(self, why="Rook was placed"):
        """Follow the focused monitor, or in WoW mode the focused game window: its centre, and the resting and
        working heights. While the owner has Rook dragged aside, Rook first flies home and is placed when it lands.
        A move to another monitor is logged with why, so the journal shows every follow."""
        self._widen_to = None  # A wider window's margin, worked out from the old place, must not land after this.
        if self.scene.view is not None:
            # The viewer holds Rook where it is; it is placed again once the swarm is home.
            return
        carried = self.carry is not None and self.carry[3]
        if carried or self.flight is not None or self._away():
            if not carried and self.flight is None:
                self.return_at = 0.0
            return
        in_game = self.wow and self.game_focused
        monitor, left, top, lift, height, self.scene.rest_pad, game, self.bounds = _placement(
            self.win.get_display(), in_game)
        old = self.monitor.get_connector() if self.monitor is not None else None
        new = monitor.get_connector() if monitor is not None else None
        if new != old:
            print(f"moved from {old} to {new}: {why}", file=sys.stderr, flush=True)
        self.monitor, self.left, self.top = monitor, left, top
        self.home_xy = (left, top)
        if self.bounds is not None:
            self.scene.monitor_width = float(self.bounds[2])
        if in_game != self.in_game:
            # The look changes with the place, so a turn that ends after focus moved keeps one look throughout.
            self.in_game = in_game
            self._set_theme(self._theme_now())
        if monitor is not None:
            LayerShell.set_monitor(self.win, monitor)
        LayerShell.set_anchor(self.win, LayerShell.Edge.TOP, True)
        LayerShell.set_margin(self.win, LayerShell.Edge.TOP, top)
        # At home on the desktop Rook sits at the centre of the free area, where the compositor centres a window that
        # only the top edge anchors. A send's fan then widens the window about Rook in the commit that draws the new
        # width, and no margin moves while it shows (see _size_canvas). Elsewhere the left margin places it.
        self._centred = left is None or (game is None and self.bounds is not None
                                         and abs(left + WIDTH / 2 - (self.bounds[0] + self.bounds[2] / 2)) <= 0.5)
        if self._centred:
            self._dispatch_cx = None
        elif self._dispatch_cx is not None:  # A fan's wide window: the margin puts Rook home, not the window's edge.
            self.left = round(left + WIDTH / 2 - self._dispatch_cx)
        LayerShell.set_anchor(self.win, LayerShell.Edge.LEFT, not self._centred)
        if left is not None:
            LayerShell.set_margin(self.win, LayerShell.Edge.LEFT, self.left)
        if lift != self.scene.lift:
            self.scene.lift = lift
            self.area.set_content_height(lift + ORB_H)
        if self.answer_open:
            self._answer_keyboard()
            self._place_answer()
        self._stage_context()
        self.scene.game_origin = None
        if game and left is not None:
            x, y, self.scene.game_scale = game
            self.scene.game_origin = (x - self._centre()[0], y - self._centre()[1])
        self._region_key = None
        if DUST_SURFACE and self._surface is None and self.win.get_mapped():
            GLib.idle_add(self._surface_up, why)  # After a failure, each placement tries the surface again.

    # ---- staying on screen ----
    # A layer surface lives on one output. When that output goes away (an external monitor drops out while it
    # sleeps), Hyprland closes the surface, and gtk4-layer-shell ignores the close by default, so GTK still thinks the
    # window is mapped and nothing shows. Only a new surface on a live monitor brings Rook back.
    def _replace(self, why):
        """Give the window a new layer surface on the monitor _place picks, and log why."""
        shown = self.win.get_visible()
        self.win.set_visible(False)
        self._place(f"placed again: {why}")
        if shown:
            self.win.set_visible(True)
        where = self.monitor.get_connector() if self.monitor is not None else "the compositor's choice of monitor"
        print(f"placed again on {where} at {self.left},{self.top}: {why}", file=sys.stderr, flush=True)

    def _monitors_changed(self, *_):
        """GDK's monitor list changed: a monitor came, went or woke. Wait a moment, so a burst of changes and
        Hyprland's own monitor list settle, then place Rook again."""
        if self._replace_pending is None:
            self._replace_pending = GLib.timeout_add(300, self._monitors_settled)

    def _monitors_settled(self):
        self._replace_pending = None
        self._replace("the monitors changed")
        return False

    def _off_screen(self):
        """True when the window has been mapped for a while, Hyprland has a monitor, and no monitor holds the overlay's
        layer. Without Hyprland's answer it is False, so nothing changes."""
        if not self.win.get_mapped() or time.monotonic() - self._mapped_at < 2.0:
            return False
        layers = _hypr_socket("j/layers")
        if not isinstance(layers, dict) or not layers:
            return False
        return not any(layer.get("namespace") == "rook-overlay" for monitor in layers.values()
                       for level in (monitor.get("levels") or {}).values() for layer in level)

    def _check_screen(self):
        """A backstop every 10 seconds, for a lost surface that no monitor change announced."""
        if self._off_screen():
            self._replace("Hyprland showed no overlay layer")
        return True

    def _centre(self):
        """The working centre in monitor coordinates. A fan's wider window moves the left margin, not the presence."""
        cx = WIDTH / 2 if self._dispatch_cx is None else self._dispatch_cx
        return self.left + cx, self.top + self.scene.lift + ORB / 2

    # ---- theme ----
    def _watch_theme(self):
        """Follow Omarchy's theme: it sets the GNOME color-scheme on every theme change. Without the schema, stay dark."""
        source = Gio.SettingsSchemaSource.get_default()
        schema = source.lookup("org.gnome.desktop.interface", True) if source else None
        if schema is None or not schema.has_key("color-scheme"):
            return
        self._interface = Gio.Settings.new("org.gnome.desktop.interface")
        self._interface.connect("changed::color-scheme", lambda *_: self._follow_theme())
        self._follow_theme()
        # A running overlay once missed the change signal. A read sees the current value even then, so re-read
        # every 2 seconds as a backstop: a missed signal costs at most that.
        GLib.timeout_add_seconds(2, self._follow_theme)

    def _follow_theme(self):
        self._followed = "light" if self._interface.get_string("color-scheme") == "prefer-light" else "dark"
        self._set_theme(self._theme_now())
        return True

    def _theme_now(self):
        """The followed theme, except that WoW mode draws the game in the dark look the owner approved there."""
        return "dark" if self.in_game else self._followed

    def _set_theme(self, name):
        if PALETTE is not THEMES[name]:
            _use_theme(name)
            self.scene.refont()  # The pack's lettering applies in the dark theme only.
            self._caption_key = None
            self.area.queue_draw()
            self.caption_area.queue_draw()
        if name != self._theme_shown:
            self._theme_shown = name
            print(f"theme: {name}", file=sys.stderr, flush=True)
        self._stage_context()

    # ---- reading the gear card ----
    def _build_reader(self):
        """A second, input-free surface for the flight to the gear card and for the flight home after a drag. It
        shows only during a flight."""
        reader = Gtk.Window(application=self)
        LayerShell.init_for_window(reader)
        LayerShell.set_namespace(reader, "rook-reading")
        LayerShell.set_layer(reader, LayerShell.Layer.OVERLAY)
        LayerShell.set_keyboard_mode(reader, LayerShell.KeyboardMode.NONE)
        LayerShell.set_anchor(reader, LayerShell.Edge.TOP, True)
        LayerShell.set_anchor(reader, LayerShell.Edge.LEFT, True)
        reader.add_css_class("rook")
        self.reader_area = Gtk.DrawingArea()
        self.reader_area.set_draw_func(self._draw_reader)
        reader.set_child(self.reader_area)
        reader.connect("map", self._reader_mapped)
        self.reader = reader
        self.reader_box = None
        self.reader_rect = None
        self.reader_ready = False

    def _reader_mapped(self, *_):
        surface = self.reader.get_surface()
        if surface is not None:
            surface.set_input_region(cairo.Region())
            self.reader_ready = True

    def _sync_reader(self):
        """Open the reading surface when a reading or a flight home starts, follow a new card, and close it when the
        grains are home."""
        if self.reader is None:
            return
        reading = self.scene.reading is not None and self.left is not None
        if not reading and self.flight is None:
            if self.reader_box is not None:
                self.reader.set_visible(False)
                self.reader_box, self.reader_rect, self.reader_ready = None, None, False
            return
        key = self.scene.read_rect if reading else self.flight
        if self.reader_rect != key:
            if reading:
                cx, cy = self._centre()
                x, y, w, h = self.scene.read_rect
                self.reader_box = _reader_box((cx + x, cy + y, w, h), self.left, self.top, self.scene.lift)
            else:
                self.reader_box = self.flight
            self.reader_rect = key
            if self.monitor is not None:
                LayerShell.set_monitor(self.reader, self.monitor)
            LayerShell.set_margin(self.reader, LayerShell.Edge.LEFT, self.reader_box[0])
            LayerShell.set_margin(self.reader, LayerShell.Edge.TOP, self.reader_box[1])
            self.reader_area.set_content_width(self.reader_box[2])
            self.reader_area.set_content_height(self.reader_box[3])
            self.reader.set_visible(True)
        self.reader.set_opacity(self.opacity)
        self.reader_area.queue_draw()

    def _draw_reader(self, _area, cr, w, _h):
        if self.reader_box is not None:
            cx, cy = self._centre()
            self.scene.draw_swarm(cr, w, time.monotonic(), centre=(cx - self.reader_box[0], cy - self.reader_box[1]))

    def _drop_bad_scene(self, where, error, now):
        """Drop a broken scene so one bad diagram never freezes the overlay."""
        print(f"dropped scene after {where} failed: {type(error).__name__}", file=sys.stderr, flush=True)
        self.scene.drop_render(now)
        self._labels = None
        if isinstance(self._dust_gl, _DustGL):
            self._dust_gl.springs_owned = False
        if self._surface is not None:
            self._surface.gl.springs_owned = False

    def _canvas_cx(self, w):
        """The presence's x in the main area, w wide and centred in the window: its x in the window, less the area's.
        From the window's laid-out width, so a frame that GTK draws before a resize lands keeps the presence in place.
        A window the compositor centres has the presence at its centre, and the area is centred in it."""
        if self._centred:
            return w / 2.0
        x = float(self._dispatch_cx) if self._dispatch_cx is not None else WIDTH / 2.0
        return x - ((self.column.get_width() or self._win_width) - w) / 2.0

    def _draw_main(self, _area, cr, w, _h):
        now = time.monotonic()
        self._shown_at = now
        # While the reading surface draws or the viewer has faded the main swarm out, draw nothing here.
        if not (self.reader_box is not None and self.reader_ready) and self.scene.swarm_vis > 0.002:
            centre = (self._canvas_cx(w), self.scene.lift + ORB / 2)
            self._drawn = (w, centre[0])
            try:
                self.scene.draw_swarm(cr, w, now, self.scene.lift, centre=centre)
            except Exception as error:
                if self.scene.render is None:
                    raise
                self._drop_bad_scene("draw", error, now)
                self.scene.draw_swarm(cr, w, now, self.scene.lift, centre=centre)

    # ---- the media viewer ----
    def _build_viewer(self):
        """The viewer's window: a full-monitor layer surface for the media box, its single-row edge dust, and captions.
        It takes the pointer only on the box (and the video close mark and captions), and the keyboard on demand."""
        win = Gtk.Window(application=self)
        LayerShell.init_for_window(win)
        LayerShell.set_namespace(win, "rook-viewer")
        LayerShell.set_layer(win, LayerShell.Layer.OVERLAY)
        LayerShell.set_keyboard_mode(win, LayerShell.KeyboardMode.NONE)
        for edge in (LayerShell.Edge.TOP, LayerShell.Edge.BOTTOM, LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT):
            LayerShell.set_anchor(win, edge, True)
        win.add_css_class("rook")
        area = _ViewerArea(self)
        click = Gtk.GestureClick()
        click.connect("released", self._viewer_clicked)
        area.add_controller(click)
        hover = Gtk.EventControllerMotion()
        hover.connect("enter", lambda *_: self._viewer_hovered(True))
        hover.connect("leave", lambda *_: self._viewer_hovered(False))
        hover.connect("motion", self._viewer_pointer_moved)
        area.add_controller(hover)
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", lambda g, x, y: self._viewer_scrub(g, x, y, 0.0))
        drag.connect("drag-update", lambda g, dx, dy: self._viewer_scrub(g, *g.get_start_point()[1:], dx))
        drag.connect("drag-end", lambda *_: setattr(self, "_scrubbing", False))
        area.add_controller(drag)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._viewer_key)
        win.add_controller(keys)
        win.set_child(area)
        win.connect("map", self._viewer_mapped)
        self.viewer, self.viewer_area = win, area

    def _viewer_mapped(self, *_):
        self._viewer_region = None
        self.viewer_ready = self.viewer.get_surface() is not None
        self._update_viewer_region()

    def _viewer_drawing(self):
        return self.viewer is not None and self.viewer_ready and self.viewer.get_visible()

    def _monitor_scale(self):
        if self.monitor is not None and hasattr(self.monitor, "get_scale"):
            return self.monitor.get_scale()
        return float(self.win.get_scale_factor() or 1)

    def _show_media(self, spec):
        """{"show": {"path": ..., "title": ...}} shows a file; {"show": "close"} closes the viewer. The file is checked
        and decoded in a worker thread, and the swarm moves only once it is ready; a refused file moves nothing."""
        if spec == "close":
            self._close_media("rook")
            return
        path = spec.get("path") if isinstance(spec, dict) else None
        title = spec.get("title") if isinstance(spec, dict) else None
        title = " ".join(title.split()) if isinstance(title, str) else ""
        self._media_job += 1
        job, bounds, scale = self._media_job, self.bounds or (0, 0, 1920, 1080), self._monitor_scale()

        def load():
            try:
                self._media_loaded = (job, path, title, _load_media(path, bounds, scale), None)
            except _MediaError as error:
                self._media_loaded = (job, path, title, None, str(error))
            except Exception as error:  # A broken file must never take the overlay down.
                self._media_loaded = (job, path, title, None, f"Rook could not open that file: {error}.")
        threading.Thread(target=load, daemon=True).start()

    def _start_view(self, path, title, box, media_rect, media):
        now = time.monotonic()
        if self.quitting or self.left is None:  # Dark does not refuse it.
            media.close()
            self._emit({"event": "show_error", "path": path,
                        "error": "Rook cannot place the viewer: Hyprland named no monitor."})
            return
        self._jump_home()
        self.flight = self.return_at = None
        cx, cy = self._centre()
        scene, old = self.scene, self.media
        was_closing = scene.view is not None and scene.view.closing is not None
        replacing = scene.view is not None and old is not None
        scene.open_view(now, (box[0] - cx, box[1] - cy, box[2], box[3]),
                        (media_rect[0] - cx, media_rect[1] - cy, media_rect[2], media_rect[3]))
        if self._staged:  # The viewer ends a scene, so a staged one never shows over it.
            self._cancel_render()
        if self.media_leaving is not None:
            self.media_leaving[0].close()
            self.media_leaving = None
        if replacing:
            surface, version = old.frame(now - scene.view.at) if old.kind != "video" else (old.data, old.version)
            if old.kind == "video":
                old.pause()
            self.media_leaving = (old, surface, version)
            if not was_closing:
                self._emit({"event": "closed", "path": self.media_path, "why": "replaced"})
        elif old is not None:
            old.close()
        self.media, self.media_path, self.media_title = media, path, title
        self.media_paused, self._media_ended_at = False, None
        if self.monitor is not None:
            LayerShell.set_monitor(self.viewer, self.monitor)
        self._viewer_hovered(self._viewer_hover and replacing)  # A new viewer waits for the pointer to come.
        self.viewer.set_visible(True)
        self._viewer_region = None
        self._emit({"event": "shown", "path": path, "kind": media.kind, "width": media.size[0],
                    "height": media.size[1]})

    def _close_media(self, why):
        """Close the viewer: fade the media out and ease the box and edge dust away. Only Rook's own close drops a file
        still loading. A hand close, an end or an error closes what shows, and a newer show still opens."""
        if why == "rook":
            self._media_job += 1
        view = self.scene.view
        if view is None or view.closing is not None:
            return
        self.scene.close_view(time.monotonic())
        if self.media is not None and self.media.kind == "video":
            self.media.pause()
        self._viewer_hover = False
        LayerShell.set_keyboard_mode(self.viewer, LayerShell.KeyboardMode.NONE)
        self._viewer_region = None
        self._emit({"event": "closed", "path": self.media_path, "why": why})

    def _drop_media(self):
        if self._video_clock is not None:
            self.viewer_area.remove_tick_callback(self._video_clock)
            self._video_clock = None
        for media in (self.media, self.media_leaving[0] if self.media_leaving else None):
            if media is not None:
                media.close()
        self.media = self.media_leaving = None

    def _toggle_pause(self):
        media = self.media
        if media is None or media.kind == "image" or self.scene.view is None or self.scene.view.closing is not None:
            return
        if media.kind == "animation":
            t = time.monotonic() - self.scene.view.media_at
            media.pause(t) if media.playing else media.play(t)
            self.media_paused = not media.playing
        elif media.playing:
            media.pause()
            self.media_paused = True
        else:
            media.play()
            self.media_paused, self._media_ended_at = False, None

    def _viewer_quiet(self, now):
        """True while the open viewer moves only slowly: no turn. Its dust then moves VIEW_REST_FPS times a second; a
        video's frames come in on the display's own clock (see _video_frame)."""
        v = self.scene.view
        return v is not None and v.settled(now) and self.scene.state in ("ready", "hidden", "result")

    def _step_viewer(self, now):
        """Take a file the worker has finished, run the video (start, duck under a turn, end), let a replaced media go,
        and hide the window once the swarm is home."""
        loaded, self._media_loaded = self._media_loaded, None
        if loaded is not None:
            job, path, title, result, error = loaded
            if job != self._media_job:
                if result is not None:
                    result[2].close()
            elif error:
                self._emit({"event": "show_error", "path": path if isinstance(path, str) else "", "error": error})
            else:
                self._start_view(path, title, *result)
        view, media = self.scene.view, self.media
        if view is not None and media is not None and media.kind == "video":
            media.poll()
            if media.error:
                self._emit({"event": "show_error", "path": self.media_path, "error": media.error})
                media.error = None
                self._close_media("error")
            elif view.closing is None:
                if now >= view.media_at and not media.playing and not self.media_paused and not media.ended:
                    media.play()
                media.volume(1.0 if self.scene.state in ("ready", "hidden", "result") else VIEW_DUCK)
                if media.ended and self._media_ended_at is None:
                    self._media_ended_at = now
                if self._media_ended_at is not None and now > self._media_ended_at + VIEW_END_HOLD:
                    self._close_media("ended")
            media.frame()
            if media.playing and self._video_clock is None:
                self._video_clock = self.viewer_area.add_tick_callback(self._video_frame)
        if self.media_leaving is not None and (view is None or now > view.morph_at + VIEW_OUT):
            self.media_leaving[0].close()
            self.media_leaving = None
        if self.viewer is None or not self.viewer.get_visible():
            return
        if view is None:
            # The ring has reached home: the main window draws the swarm again.
            self.viewer.set_visible(False)
            self.viewer_ready = False
            self._drop_media()
            self._place("the viewer closed")
            return
        self.viewer.set_opacity(self.opacity)
        self._update_viewer_region()
        self.viewer_area.queue_draw()

    def _video_frame(self, area, _clock):
        """On the display's own clock while a video plays: take the newest frame, if one came, and draw it. The
        appsink keeps only the newest frame, so a late one is dropped, never queued. The rest of the viewer is drawn
        from the dust strips already made (see _snapshot_viewer), so a frame costs little."""
        media = self.media
        if media is None or media.kind != "video" or not media.playing or self.scene.view is None:
            self._video_clock = None
            return False
        version = media.version
        media.frame()
        if media.version != version:
            area.queue_draw()
        return True

    def _viewer_rects(self, now):
        """Where the viewer takes the pointer, in its own coordinates: the box once it is open, the close mark of a
        video, and the captions while they can open the answer."""
        view = self.scene.view
        if view is None or view.closing is not None or view.opened(now) < 0.5:
            return []
        cx, cy = self._centre()
        bx, by, bw, bh = view.box(now)
        rects = [(cx + bx, cy + by, bw, bh)]
        if (row := self._view_controls(now, always=True).get("row")) is not None:
            rects.append(row)
        if self.scene.captions and self.scene.caption_box and self.details.strip() and not self.answer_open:
            ox, oy = _view_caption_origin(self.scene, now, (cx, cy))
            x, y, w, h = self.scene.caption_box
            rects.append((ox + x - 12, oy + y - 8, w + 24, h + 40))
        return [tuple(int(round(v)) for v in rect) for rect in rects]

    def _update_viewer_region(self):
        surface = self.viewer.get_surface()
        if surface is None:
            return
        rects = self._viewer_rects(time.monotonic())
        key = tuple(rects)
        if key != self._viewer_region:
            self._viewer_region = key
            surface.set_input_region(cairo.Region([cairo.RectangleInt(*rect) for rect in rects]))

    def _viewer_clicked(self, _gesture, _n, x, y):
        now = time.monotonic()
        view = self.scene.view
        if view is None or view.closing is not None:
            return
        rects = self._viewer_rects(now)

        def inside(rect):
            return rect[0] <= x < rect[0] + rect[2] and rect[1] <= y < rect[1] + rect[3]
        moving = self.media is not None and self.media.kind in ("video", "animation")
        controls = self._view_controls(now)
        if "close" in controls and inside(controls["close"]):
            self._close_media("close mark")
        elif "scrub" in controls and inside(controls["scrub"]):
            return  # The drag gesture seeks.
        elif "play" in controls and inside(controls["play"]):
            self._toggle_pause()
        elif "open" in controls and inside(controls["open"]):
            self._open_elsewhere()
        elif rects and inside(rects[0]):
            if moving:
                self._toggle_pause()
            else:
                self._close_media("click")
        else:
            self._caption_clicked()

    def _viewer_key(self, _controller, keyval, _code, _state):
        if keyval == Gdk.KEY_Escape:
            self._close_media("escape")
            return True
        if keyval == Gdk.KEY_space:
            self._toggle_pause()
            return True
        return False

    def _viewer_hovered(self, over):
        """The pointer came onto the box or its controls, or left them. While the pointer is on it, a click gives the viewer
        the keyboard, for Space and Escape. Passing over it never takes the owner's typing, and the game never loses it.
        After the pointer leaves, the controls stay VIEW_HOVER_GRACE seconds, so a pointer on its way to them, or a
        compositor that sends leave and enter as the keyboard mode changes, never makes them vanish."""
        if over:
            self._viewer_hover_until = 0.0
            if not self._viewer_hover:
                self._viewer_hover = True
                game = self.wow and self.in_game
                LayerShell.set_keyboard_mode(self.viewer, LayerShell.KeyboardMode.NONE if game
                                             else LayerShell.KeyboardMode.ON_DEMAND)
        elif self._viewer_hover:
            self._viewer_hover_until = time.monotonic() + VIEW_HOVER_GRACE
            GLib.timeout_add(int(VIEW_HOVER_GRACE * 1000) + 20, self._viewer_hover_ended)
        self.viewer_area.queue_draw()

    def _viewer_pointer_moved(self, _controller, x, y):
        """The pointer moved over the viewer: the close X lights while it is on it. A redraw only when that changes."""
        close = self._view_controls(time.monotonic()).get("close")
        hot = close is not None and close[0] <= x < close[0] + close[2] and close[1] <= y < close[1] + close[3]
        if hot != self._close_hot:
            self._close_hot = hot
            self.viewer_area.queue_draw()

    def _viewer_hover_ended(self):
        """The grace after the pointer left has run out with no return: hide the controls and give back the keyboard."""
        if self._viewer_hover and self._viewer_hover_until and time.monotonic() >= self._viewer_hover_until:
            self._viewer_hover, self._viewer_hover_until, self._close_hot = False, 0.0, False
            LayerShell.set_keyboard_mode(self.viewer, LayerShell.KeyboardMode.NONE)
            self.viewer_area.queue_draw()
        return False

    def _view_controls(self, now, always=False):
        """The hover controls of the open box, as rects in the viewer's coordinates: "row" under the box takes the
        pointer, "play" and "scrub" show for a clip or a video, "open" for any file, and "close", an X in the box's
        top-right corner. Empty while the pointer is elsewhere, unless always, which the input region uses so the
        pointer can reach the row before the controls show."""
        view, media = self.scene.view, self.media
        if (not (always or self._viewer_hover) or media is None or view is None or view.closing is not None
                or view.opened(now) < 0.5):
            return {}
        cx, cy = self._centre()
        bx, by, bw, bh = view.box(now)
        x, y, yc = cx + bx, cy + by + bh, cy + by + bh + VIEW_LINE_DY
        controls = {"row": (x - 7, y, bw + 14, VIEW_LINE_DY + 14)}
        controls["close"] = (x + bw - VIEW_CLOSE_SIZE - 6, cy + by + 6, VIEW_CLOSE_SIZE, VIEW_CLOSE_SIZE)
        open_x = x + bw - 7
        controls["open"] = (open_x - 14, yc - 14, 28, 28)
        if media.kind != "image":
            controls["play"] = (x - 7, yc - 14, 28, 28)
            controls["scrub"] = (x + 28, yc - 14, max(0, open_x - 22 - x - 28), 28)
        return {k: tuple(int(round(v)) for v in r) for k, r in controls.items()}

    def _media_progress(self, now):
        """How far the clip or video has played, from 0 to 1, or None."""
        media, view = self.media, self.scene.view
        if media is None or view is None or media.kind == "image":
            return None
        if media.kind == "animation":
            total = media.total or media.length
            return min(1.0, media.at(now - view.media_at) / total) if total > 0 else None
        where = media.where()
        return where[0] / where[1] if where else None

    def _viewer_scrub(self, _gesture, x, y, dx):
        """A press or drag on the scrub bar moves the clip or video there."""
        now = time.monotonic()
        scrub = self._view_controls(now).get("scrub")
        if scrub is None or not (self._scrubbing or (scrub[0] <= x < scrub[0] + scrub[2]
                                                     and scrub[1] <= y < scrub[1] + scrub[3])):
            return
        self._scrubbing = True
        to = max(0.0, min(1.0, (x + dx - scrub[0]) / max(1, scrub[2])))
        media = self.media
        if media.kind == "animation":
            media.seek(to * (media.total or media.length), now - self.scene.view.media_at)
        elif (where := media.where()) is not None:
            media.seek(to * where[1])
            self._media_ended_at = None
        self.viewer_area.queue_draw()

    def _open_elsewhere(self):
        """Open the file in the system's own viewer. Rook's viewer stays open."""
        try:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", self.media_path],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        except OSError as error:
            self._emit({"event": "show_error", "path": self.media_path, "error": f"Rook could not open it: {error}."})

    def _media_texture(self, media, surface, version):
        """The media frame as a GPU texture, made once per frame: the box and the media cost the CPU nothing more."""
        texture = media.textures.get(version)
        if texture is None:
            if media.kind == "video":
                # surface is the decoder's bytes (see _Clip._take); the texture keeps them, with no copy here.
                texture = Gdk.MemoryTexture.new(*media.pixels, Gdk.MemoryFormat.B8G8R8X8, surface, media.stride)
                media.textures = {}
            else:
                surface.flush()
                texture = Gdk.MemoryTexture.new(surface.get_width(), surface.get_height(),
                                                Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED,
                                                GLib.Bytes.new(bytes(surface.get_data())), surface.get_stride())
            media.textures[version] = texture
        return texture

    def _dust_on_gpu(self):
        """True when the GL frame draws the viewer's edge dust: chosen, not failed, and a look it can draw."""
        return VIEW_DUST == "gl" and self._dust_gl is not False and _DustGL.supports(PALETTE)

    def _spring_back(self):
        """The main window's grains back from the chip into Python (see Scene.step), from whichever GL frame holds
        them: GTK's, or the dust surface's."""
        if self._surface is not None and self._surface.gl.springs_owned:
            try:
                self._surface.gl.read_springs(self.scene)
            except Exception as error:
                self._surface_down("reading the grains back failed", error)
        if isinstance(self._dust_gl, _DustGL) and self._dust_gl.springs_owned:
            try:
                self._dust_gl.read_springs(self.scene)
            except Exception as error:  # A driver error: Cairo draws from here on, from Python's copy a frame behind.
                print(f"the GL grains failed, so Cairo draws them: {error}", file=sys.stderr, flush=True)
                self._dust_gl = False
        self.scene.spring_steps.clear()

    def _springs_to(self, gl):
        """Before gl draws the main window's grains: if the other GL frame holds them, they come back to Python first,
        so gl takes them up from there."""
        for other in (self._dust_gl, self._surface.gl if self._surface is not None else None):
            if isinstance(other, _DustGL) and other is not gl and other.springs_owned:
                other.read_springs(self.scene)

    # ---- the dust surface (DUST_SURFACE) ----
    def _surface_up(self, why):
        """Put the dust on a surface of its own, below the window's, when the window is placed. A failure is logged
        once; GTK draws the dust until the next placement tries again."""
        if not DUST_SURFACE or self._surface is not None or not self.win.get_mapped() or self.quitting:
            return False
        try:
            self._surface = _DustSurface(self)
        except Exception as error:
            print(f"the dust surface could not start, so GTK draws the dust: {error}", file=sys.stderr, flush=True)
            self._surface_lost = True
            return False
        where = self.monitor.get_connector() if self.monitor is not None else "the compositor's choice of monitor"
        print(f"the dust surface is up on {where}{' again' if self._surface_lost else ''}: {why}", file=sys.stderr,
              flush=True)
        self._surface_lost = False
        self._text_key = None
        return False

    def _surface_down(self, why, error=None):
        """Tear the dust surface down and draw the dust in GTK again at once. The grains come back to Python first
        when they can."""
        surface, self._surface = self._surface, None
        if surface is None:
            return
        if error is None:
            try:
                if surface.gl.springs_owned:
                    surface.gl.read_springs(self.scene)
            except Exception as failure:
                error = failure
        if error is not None:
            self._surface_lost = True
            print(f"the dust surface failed, so GTK draws the dust: {why}: {error}", file=sys.stderr, flush=True)
            self.scene.spring_steps.clear()
            surface.gl.springs_owned = False
        else:
            print(f"the dust surface is down: {why}", file=sys.stderr, flush=True)
        if self._clock_on is surface:
            self._viewer_clock = self._clock_on = None
            self._restart_timer()
        surface.close()
        self.area.queue_draw()

    def _surface_drawing(self):
        """True while the dust surface draws the main window's dust: it is up, the chip runs the grains (or flipbook),
        and the window shows them whole (no viewer fade, no reading surface, no fade)."""
        return (self._surface is not None and (self.scene.springs_on_gpu or self.scene.pack_kind == "flipbook")
                and self.opacity == 1.0 and self.scene.swarm_vis >= 1.0
                and not (self.reader_box is not None and self.reader_ready) and not self._viewer_drawing())

    def _present_surface(self):
        """Draw this tick's dust on the dust surface. GTK draws the window again only when its text changes."""
        surface, scene = self._surface, self.scene
        if not self._surface_drawing():
            if surface.last is not None:
                surface.present(None)  # Clear it: the window draws the dust now.
            return
        ok, bounds = self.area.compute_bounds(self.win)
        if not ok:
            return
        w, h = bounds.get_width(), bounds.get_height()
        scale = self.win.get_surface().get_scale() if self.win.get_surface() else self._monitor_scale()
        cx, cy = self._canvas_cx(w), scene.lift + ORB / 2
        under = scene.main_scrim(scale, cx, cy)
        surface.place(bounds.get_x(), bounds.get_y(), w, h, scale)
        self._springs_to(surface.gl)
        try:
            surface.present(lambda gl: gl.draw_main(scene, w, h, (cx, cy), scale, under, window=True))
        except Exception as error:
            if scene.render is None:
                raise
            self._drop_bad_scene("surface_draw", error, time.monotonic())
            return
        self._shown_at = time.monotonic()

    def _main_gl(self):
        """The GL frame that draws the main window's grains: the dust surface's while it is up, else GTK's."""
        return self._surface.gl if self._surface is not None else self._gl()

    def _gl(self):
        """The GL frame, made on first use; None when GL is not chosen or has failed (logged once)."""
        if not self._dust_on_gpu():
            return None
        if self._dust_gl is None:
            try:
                self._dust_gl = _DustGL(self.viewer.get_display())
            except Exception as error:  # No GL, or a driver error: Cairo draws from here on.
                print(f"the viewer's GL frame failed, so Cairo draws it: {error}", file=sys.stderr, flush=True)
                self._dust_gl = False
                return None
        return self._dust_gl

    def _snapshot_main(self, snap, w, h):
        """The main window's grains drawn by the chip while it runs their springs (Scene.springs_on_gpu): the scrim and
        the grains in one GL texture, as draw_swarm paints them, and the labels in Cairo over them. False when Cairo
        draws the area instead: a turn, the viewer or the reading surface drawing the grains, or no GL."""
        scene = self.scene
        if self._surface is not None and self._surface_drawing():
            # The dust surface draws the dust; GTK draws only the text over it.
            self._append_labels(snap, w, h, self._monitor_scale())
            return True
        if ((not scene.springs_on_gpu and scene.pack_kind != "flipbook")
                or (self.reader_box is not None and self.reader_ready) or scene.swarm_vis <= 0.002
                or self._gl() is None):
            return False
        self._shown_at = time.monotonic()
        scale = self._monitor_scale()
        cx, cy = self._canvas_cx(w), scene.lift + ORB / 2
        self._drawn = (w, cx)
        try:
            self._springs_to(self._dust_gl)
        except Exception as error:
            print(f"the GL grains failed, so Cairo draws them: {error}", file=sys.stderr, flush=True)
            self._dust_gl = False
            return False
        under = scene.main_scrim(scale, cx, cy)
        try:
            texture = self._dust_gl.draw_main(scene, w, h, (cx, cy), scale, under)
        except Exception as error:
            if scene.render is not None:
                self._drop_bad_scene("gl_draw", error, time.monotonic())
                return False
            print(f"the GL grains failed, so Cairo draws them: {error}", file=sys.stderr, flush=True)
            self._dust_gl = False
            scene.springs_on_gpu = scene.spring_gl = False
            scene.spring_steps.clear()
            return False
        snap.append_texture(texture, Graphene.Rect().init(0, 0, texture.get_width() / scale,
                                                           texture.get_height() / scale))
        try:
            self._append_labels(snap, w, h, scale)
        except Exception as error:
            if scene.render is None:
                raise
            self._drop_bad_scene("labels", error, time.monotonic())
        return True

    def _append_labels(self, snap, w, h, scale):
        """The labels over the chip's grains, as draw_swarm paints them, from a texture painted again only when
        they change. Active dispatch rows composite cached per-row textures via GSK transform + opacity (zero alloc)."""
        scene = self.scene
        cx, cy = self._canvas_cx(w), scene.lift + ORB / 2
        state = scene.label if scene.label and scene.label_alpha > 0.01 else None
        render = scene.render if scene.render is not None and scene.form == "render" else None
        names = scene.diagram_names(scene.last)
        if names:
            render = None  # A constellation's names are textures of their own (below), not part of this layer.
        dispatch = scene.dispatch if scene.dispatch_active(scene.last) else None
        guide = scene.guide_key() if scene.guide_shown and scene.guide_shown[2] else None
        if state is not None or render is not None or guide is not None:
            fading = render is not None and (scene.last - render["at"] < 0.5 + scenes.LABELS_AFTER
                                             or scene.render_end is not None)
            key = (state, round(scene.label_alpha, 3),
                   min(REVEAL_SECONDS, round(scene.last - scene.label_at, 3)) if LETTERING else None,
                   scene.label_anchor, id(PALETTE), id(scene.label_sprites), w, h,
                   round(cx, 1), scale, None if render is None else (id(scene.render_form), repr(render["lit"]),
                                                                      render["dy"], render["bottom"],
                                                                      scene._render_labels_moment(scene.last)
                                                                      if fading else None), guide)
            if self._labels is None or self._labels[0] != key:
                image = cairo.ImageSurface(cairo.FORMAT_ARGB32, math.ceil(w * scale), math.ceil(h * scale))
                image.set_device_scale(scale, scale)
                cr = cairo.Context(image)
                scene._label(cr, cx, cy)
                scene.draw_guide(cr, cx, cy + scene.rest_y_offset() + GUIDE_REST_DY, True)
                if render is not None:
                    scene._render_labels(cr, cx, cy)
                image.flush()
                texture = Gdk.MemoryTexture.new(image.get_width(), image.get_height(),
                                                Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED,
                                                GLib.Bytes.new(bytes(image.get_data())), image.get_stride())
                self._labels = (key, texture)
            texture = self._labels[1]
            snap.append_texture(texture, Graphene.Rect().init(0, 0, texture.get_width() / scale,
                                                               texture.get_height() / scale))
        for text, x, y, alpha, grow in names:
            key = (text, scale, grow, id(LETTERING), id(PALETTE))
            if key not in self._name_textures:
                if len(self._name_textures) > 64:
                    self._name_textures.clear()
                sprite = scene._diagram_sprite(self._probe_cr, text, scale, grow)
                self._name_textures[key] = (DispatchState._surface_to_texture(sprite),
                                            sprite.get_width() / scale, sprite.get_height() / scale)
            texture, tw, th = self._name_textures[key]
            # On whole device pixels, so GSK never resamples the letters.
            left = round((cx + x - 14) * scale) / scale
            top = round((cy + scene.render["dy"] + y - 14) * scale) / scale
            snap.push_opacity(min(1.0, alpha))
            snap.append_texture(texture, Graphene.Rect().init(left, top, tw, th))
            snap.pop()
        if dispatch is not None:
            dispatch.append_gl_overlay(snap, cx, cy + scene.dispatch_y_offset(), w, scene.last,
                                       scene.monitor_width, scale, PALETTE, is_nova=(scene.pack_kind == "flipbook"))

    def _caption_dim(self):
        return max(self.card_mix, _ease_out(self.answer_mix) if self.panel_pos is None else 0.0)

    def _draw_captions(self, cr, w):
        """The caption area: the spoken words, and the guide in a turn. The guide steps aside for READ MORE."""
        scene, dim = self.scene, self._caption_dim()
        scene.draw_caption(cr, w, time.monotonic(), dim)
        scene.draw_guide(cr, w / 2, scene.guide_y, False, max(dim, scene.caption_hint_mix))

    def _gl_edges(self, snap, rects, clips, centre):
        """The viewer frame's strips drawn by the GL frame into snap, as of the dust's last move. False when Cairo must
        draw them: the GL frame is not chosen, or GL failed, which is logged once and leaves Cairo drawing for good."""
        if not self._dust_on_gpu():
            return False
        scene = self.scene
        try:
            if self._dust_gl is None:
                self._dust_gl = _DustGL(self.viewer.get_display())
            parts = self._dust_gl.draw(scene, rects, scene.moved_at, centre, self._monitor_scale(), clips=clips)
        except Exception as error:  # No GL, or a driver error: Cairo draws the frame from here on.
            print(f"the viewer's GL frame failed, so Cairo draws it: {error}", file=sys.stderr, flush=True)
            self._dust_gl = False
            scene.dust_gl = False
            scene._step_dust(scene.moved_at)
            return False
        for texture, rect, strip in parts:
            snap.push_clip(Graphene.Rect().init(*strip))
            snap.append_texture(texture, Graphene.Rect().init(*rect))
            snap.pop()
        return True

    def _snapshot_viewer(self, snap, w, h):
        """Compose one viewer frame: black box, media texture, four narrow edge strips of dust, title line, and captions.
        Every dust grain sits on the box edge and is painted at most once, via GL or single-pass Cairo strips."""
        now, scene = time.monotonic(), self.scene
        view = scene.view
        cx, cy = centre = self._centre()

        def cairo_node(x, y, nw, nh):
            return snap.append_cairo(Graphene.Rect().init(x, y, max(0.0, nw), max(0.0, nh)))

        if view is None:
            return
        x, y, bw, bh, r, a = view.core(now)
        if a > 0.002:
            rect = Graphene.Rect().init(cx + x, cy + y, bw, bh)
            rounded = Gsk.RoundedRect()
            rounded.init_from_rect(rect, r)
            snap.push_rounded_clip(rounded)
            snap.append_color(Gdk.RGBA(red=0, green=0, blue=0, alpha=a), rect)
            snap.pop()

        def texture(media, surface, version, rect, alpha):
            if surface is None or alpha <= 0.002:
                return
            snap.push_opacity(alpha)
            if isinstance(surface, Gdk.Paintable):
                snap.save()
                snap.translate(Graphene.Point().init(rect[0], rect[1]))
                surface.snapshot(snap, rect[2], rect[3])
                snap.restore()
            else:
                snap.append_texture(self._media_texture(media, surface, version), Graphene.Rect().init(*rect))
            snap.pop()

        if self.media_leaving is not None:
            gone = _smooth((now - view.morph_at) / VIEW_OUT)
            lx, ly, lw, lh = _view_media_rect(view.media_from, 1 - gone)
            texture(self.media_leaving[0], self.media_leaving[1], self.media_leaving[2], (cx + lx, cy + ly, lw, lh),
                    1 - gone)
        p = view.media_in(now)
        surface = version = None
        if self.media is not None:
            surface, version = ((self.media.data, self.media.version) if self.media.kind == "video"
                                else self.media.frame(now - view.media_at))
        if surface is not None and p > 0.002:
            mx, my, mw, mh = _view_media_rect(view.media_rect(now), p)
            texture(self.media, surface, version, (cx + mx, cy + my, mw, mh), p)
        if scene.dust is not None and scene.dust_vis > 0.002:
            s = VIEW_STRIP
            pad_in = max(16.0, min(view.margin(now), 26.0, bw / 2 - 1.0, bh / 2 - 1.0))
            x0, y0, x1, y1 = cx + x - s, cy + y - s, cx + x + bw + s, cy + y + bh + s
            ix0, iy0 = cx + x + pad_in, cy + y + pad_in
            ix1, iy1 = cx + x + bw - pad_in, cy + y + bh - pad_in
            rects = [
                (x0, y0, max(0.0, x1 - x0), max(0.0, iy0 - y0)),
                (x0, iy1, max(0.0, x1 - x0), max(0.0, y1 - iy1)),
                (x0, iy0, max(0.0, ix0 - x0), max(0.0, iy1 - iy0)),
                (ix1, iy0, max(0.0, x1 - ix1), max(0.0, iy1 - iy0)),
            ]
            # Widen each strip's clip by 2 px on its seam sides (iy0, iy1) so grains on the seam are never cropped.
            seam = 2.0
            clips = [
                (x0, y0, max(0.0, x1 - x0), max(0.0, iy0 - y0) + seam if iy0 > y0 else 0.0),
                (x0, iy1 - seam, max(0.0, x1 - x0), max(0.0, y1 - iy1) + seam if y1 > iy1 else 0.0),
                (x0, iy0 - seam, max(0.0, ix0 - x0), max(0.0, iy1 - iy0) + 2 * seam if iy1 > iy0 else 0.0),
                (ix1, iy0 - seam, max(0.0, x1 - ix1), max(0.0, iy1 - iy0) + 2 * seam if iy1 > iy0 else 0.0),
            ]
            key = (scene.moved_at, PALETTE is THEMES["light"], tuple(rects))
            if self._edges is None or self._edges[0] != key:
                edges = Gtk.Snapshot()
                if not self._gl_edges(edges, rects, clips, centre):
                    scene.draw_view_edges([(edges.append_cairo(Graphene.Rect().init(
                        rx, ry, max(0.0, nw), max(0.0, nh))), rect)
                        for rect, (rx, ry, nw, nh) in zip(rects, clips)], now, centre)
                self._edges = (key, edges.to_node())
            if self._edges[1] is not None:
                snap.append_node(self._edges[1])
        bx, by, bw, bh = view.box(now)
        line = "PAUSED" if self.media_paused else self.media_title
        mark = False  # The X in the box's corner closes every file now (see _view_controls).
        label = p > 0.002 and bool(scene.label)
        controls = self._view_controls(now)
        if (close := controls.get("close")) is not None:
            _paint_view_close(cairo_node(*close), close, self._close_hot)
        if line or mark or label or controls:
            cr = cairo_node(cx + bx - 12, cy + by + bh + 4, bw + 24, VIEW_LINE_DY + 28)
            _paint_view_line(cr, scene, now, centre, "" if controls else line, mark)
            if controls:
                _paint_view_controls(cr, controls, not self.media_paused, self._media_progress(now))
            if label:
                scene._label(cr, cx, cy, in_view=True, fade=p)
        if scene.captions and p > 0.002:
            ox, oy = _view_caption_origin(scene, now, centre)
            cr = cairo_node(ox, oy, WIDTH, CAPTION_H)
            cr.translate(ox, oy)
            scene.draw_caption(cr, WIDTH, now, dim=1.0 - p)

    # ---- focus: step aside for WoW, follow the focused monitor ----
    def _watch_focus(self):
        """Learn focus from Hyprland's event socket; poll hyprctl once a second if the socket is unavailable."""
        self._poll_focus()
        path = os.path.join(os.environ.get("XDG_RUNTIME_DIR", ""), "hypr",
                            os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", ""), ".socket2.sock")
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(path)
            sock.setblocking(False)
        except OSError:
            GLib.timeout_add(1000, self._poll_focus)
            return
        self._focus_sock = sock
        GLib.unix_fd_add_full(GLib.PRIORITY_DEFAULT, sock.fileno(), GLib.IO_IN | GLib.IO_HUP, self._on_focus_events)

    def _poll_focus(self):
        window = _hypr("activewindow")
        self._set_focus(isinstance(window, dict) and window.get("title") == GAME_TITLE)
        return True

    def _on_focus_events(self, _fd, _cond):
        try:
            chunk = self._focus_sock.recv(65536)
        except BlockingIOError:
            return True
        except OSError:
            chunk = b""
        if not chunk:
            self._focus_sock.close()
            print("focus events stopped: Rook now checks focus once a second", file=sys.stderr, flush=True)
            GLib.timeout_add(1000, self._poll_focus)
            return False
        self._focus_buffer += chunk
        *lines, self._focus_buffer = self._focus_buffer.split(b"\n")
        for line in lines:
            if line.startswith(b"activewindow>>"):
                # The event is "class,title"; a title may itself contain commas.
                title = line[len(b"activewindow>>"):].decode(errors="replace").partition(",")[2]
                self._set_focus(title == GAME_TITLE)
            elif line.startswith((b"focusedmon>>", b"focusedmonv2>>")):
                # The event is "monitor,workspace". Hyprland sends it when the pointer crosses to another monitor
                # too.
                name = line.partition(b">>")[2].decode(errors="replace").partition(",")[0]
                self._follow(name, "Hyprland reported focus there")
            elif line.startswith(b"configreloaded>>"):
                _no_layer_anim("Hyprland reloaded its config")
        return True

    def _follow(self, name, why):
        """Focus is on the monitor called name. Rook waits for focus to settle there, FOLLOW_REST_MS at rest and
        FOLLOW_SETTLE_MS during a turn (see _follow_focus)."""
        self._focus_name, self._focus_why = name, why
        if self._focus_move is not None:
            GLib.source_remove(self._focus_move)
        rest = self.scene.is_home(time.monotonic(), self._held())
        self._focus_move = GLib.timeout_add(FOLLOW_REST_MS if rest else FOLLOW_SETTLE_MS, self._follow_focus)

    def _check_focus(self):
        """A backstop once a second: ask Hyprland which monitor has focus, so a missed event or a lost event socket
        never leaves Rook behind. A socket request costs well under a millisecond; it starts no process."""
        monitors = _hypr_socket("j/monitors")
        name = next((m.get("name") for m in monitors if m.get("focused")), None) if isinstance(monitors, list) else None
        if name and self.monitor is not None and name != self.monitor.get_connector() and self._focus_move is None:
            self._follow(name, "the focus check found it there")
        return True

    def _follow_focus(self):
        """Focus has stayed on another monitor. At rest Rook moves there. During a turn the swarm dissolves here and
        gathers there, as it does when Rook appears. The state, the label and the captions carry over. In a turn Rook
        stays put while the viewer or the answer panel is open, while it is dragged aside or flying home, and in the
        game; it is placed when the turn ends, as before."""
        self._focus_move = None
        now = time.monotonic()
        old = self.monitor.get_connector() if self.monitor is not None else None
        if self._focus_name == old:
            return False
        if self.scene.is_home(now, self._held()):
            self._place(f"at rest, {self._focus_why}")
            return False
        if not (self.wow and (self.in_game or self.game_focused)):
            self._regather(f"during a turn, {self._focus_why}")
        return False

    def _regather(self, why):
        """In a turn, the swarm dissolves here and gathers where _place puts it now. It stays put while the viewer or
        the answer panel is open, while it is dragged aside or flying home, and while it is hidden."""
        if (self.scene.view is not None or self.answer_open or self.carry is not None or self.flight is not None
                or self._away() or not self._should_show(time.monotonic())):
            return
        self.opacity = 0.0
        self.win.set_opacity(0.0)
        self._place(why)
        self.scene.scatter()

    def _set_focus(self, game):
        """game is True while the WoW window is focused. In WoW mode the answer panel closes when the game loses
        focus, as WoWFriend's did, and Rook moves between the game and the desktop at rest (_tick places it again when
        a turn ends); the look moves with it (see _place). In a turn, a scene shown on the desktop follows the game
        when it takes focus. Without WoW mode, game focus changes nothing."""
        if not self.wow:
            return
        if game != self.game_focused:
            if not game:
                self._close_answer()
            self.game_focused = game
            if self.scene.is_home(time.monotonic(), self._held()):
                self._place("the game's focus changed")
            elif game and not self.in_game and self.scene.render is not None and self.scene.render_end is None:
                # A scene that showed on the desktop follows the owner back into the game, where they are looking.
                self._regather("a scene followed the game's focus")
        self._apply_state()

    def _button(self, label, handler):
        button = Gtk.Button(label=label, focusable=False, focus_on_click=False)
        button.connect("clicked", handler)
        return button

    # ---- protocol ----
    def _emit(self, event):
        try:
            print(json.dumps(event), flush=True)
        except (BrokenPipeError, OSError):
            self.quitting = True

    def _on_stdin(self, fd, _cond):
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            chunk = b""
        if not chunk:
            self.quitting = True
            return False
        self._buffer += chunk
        *lines, self._buffer = self._buffer.split(b"\n")
        for line in lines:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if isinstance(msg, dict):
                try:
                    self.handle(msg)
                except Exception as exc:
                    print(f"overlay ignored bad stdin message ({type(exc).__name__}: {exc})", file=sys.stderr, flush=True)
        return True

    def handle(self, msg):
        if isinstance(msg.get("dark"), bool):
            self.dark = msg["dark"]
            self.scene.dark = msg["dark"]
            if self.dark:
                self.scene.dispatch = None
        if isinstance(msg.get("stage"), bool) and msg["stage"] != self.stage_on:
            self.stage_on = msg["stage"]
            if not self.stage_on:
                self._stage_fall_back("the stage setting is off")
        if isinstance(msg.get("font"), str):
            self._set_font(msg["font"])
        if isinstance(msg.get("light_dust"), str):
            self._set_light_dust(msg["light_dust"])
        if "show" in msg:
            self._show_media(msg["show"])
        if "render" in msg:
            self._handle_render(msg["render"])
        if msg.get("replay_armed") is True:
            self.scene.replay_pulse_at = time.monotonic()
        if isinstance(msg.get("answers"), list):
            if seeded := [text for text in msg["answers"] if isinstance(text, str) and text.strip()][-ANSWER_HISTORY:]:
                self.answers, self.answer, self.answer_at = seeded, seeded[-1], len(seeded) - 1
                self._show_history()
        previous = self.scene.state
        prev_pack = self.scene.pack_name
        self.scene.handle(msg, time.monotonic())
        if self.scene.pack_name != prev_pack:
            self.area.queue_draw()
            self._stage_context()
        if self.scene.state == "listening" and self._staged and "render" not in msg:
            # The owner spoke while a scene was baking or staged, so cancel the stale scene and reply.
            self._cancel_render()
        if self.scene.state != previous and self.opacity == 0 and self._should_show(time.monotonic()):
            self.scene.scatter()
        if self.scene.state != previous and self.scene.state == "listening":
            self.spoken = self.details = ""
        if isinstance(msg.get("spoken"), str):
            self.spoken = msg["spoken"]
        details = msg.get("details")
        if isinstance(details, str):
            if self.scene.state == "permission":
                self.request_label.set_label(_safe_utf8(details))
                self.card_details = details
            else:
                self.details = details
                if details.strip():
                    self._set_answer(details)
        if msg.get("state") == "permission":
            self._open_card(msg)
        elif "count" in msg and self.face is not None:  # The queue behind the card grew.
            self.face.count(msg["count"])
            self.card_panel.queue_draw()
        self._apply_state()
        if self.scene.state != previous and self._off_screen():
            # A turn never plays to an invisible overlay.
            self._replace(f"the state {self.scene.state} came while the overlay was off screen")

    def _cancel_render(self):
        """Cancel a staged diagram and its queued steps, replying to each cancelled request. Return whether a staged
        diagram was dropped."""
        staged, self._staged = self._staged is not None, None
        if not staged:
            return False
        self._render_seq += 1
        cancelled = [item.get("id") if isinstance(item, dict) else None for item in self._render_queue]
        self._render_queue.clear()
        for req_id in cancelled:
            self._emit({"event": "rendered", "id": req_id, "ok": False, "error": "Replaced before it showed."})
        return staged

    def _handle_render(self, spec):
        """Handle a render request: a diagram shows or waits staged for the reveal, and steps wait with it."""
        req_id = spec.get("id") if isinstance(spec, dict) else None
        if isinstance(spec, dict) and "scene" in spec and not spec.get("clear"):  # The old scene tool.
            self._emit({"event": "rendered", "id": req_id, "ok": False, "error": SCENE_GONE})
            return
        if isinstance(spec, dict) and "reveal" in spec:
            staged = self._staged and self._staged[0] == spec["reveal"]
            if spec.get("drop") and staged:
                self._cancel_render()
            elif staged:
                self._reveal_render()
            return
        if self._staged:
            if isinstance(spec, dict) and (spec.get("clear") or "diagram" in spec):
                if self._cancel_render() and spec.get("clear"):  # The model was told it shows, so it is cleared.
                    self.scene.end_render(time.monotonic())
                    self._emit({"event": "rendered", "id": req_id, "ok": True, "said": "Cleared."})
                    return
            else:
                if isinstance(spec, dict) and "step" in spec:
                    # The model may wait on this step before it speaks, so it is answered now and lit at the reveal.
                    answer = _scene_step_answer(self._staged[1]["steps"], spec["step"])
                    self._emit({"event": "rendered", "id": req_id, **answer})
                    if not answer["ok"]:
                        return
                self._render_queue.append(spec)
                return
        if isinstance(spec, dict) and "diagram" in spec and not spec.get("clear"):
            try:  # A few ms on the main loop: no bake, no thread.
                scene, form = self.scene.diagram_form(spec["diagram"])
            except Exception as error:
                self._emit({"event": "rendered", "id": req_id, "ok": False, "error": f"The diagram failed: {error!r}."})
                return
            if form is None:
                self._emit({"event": "rendered", "id": req_id, "ok": False,
                            "error": "A diagram needs two nodes joined by > or -."})
            elif spec.get("stage") is True:  # Rook reveals it when its voice starts the answer.
                self._staged = (req_id, scene, form)
                self._emit({"event": "rendered", "id": req_id, **self.scene.render_said(scene, form)})
            else:
                self._emit({"event": "rendered", "id": req_id,
                            **self.scene.render_commit(scene, form, time.monotonic())})
                self._apply_state()
            return
        try:
            answer = self.scene.render_command(spec, time.monotonic())
        except Exception as error:  # A diagram that could not be drawn; Rook goes on.
            answer = {"ok": False, "error": f"The diagram could not be drawn: {error!r}. Simplify it and try again."}
        self._emit({"event": "rendered", "id": req_id, **answer})

    def _drain_render(self, seq):
        """Run the queued step commands, unless a cancel came first."""
        if seq != self._render_seq:
            return False
        queued, self._render_queue = self._render_queue, []
        for item in queued:
            self._handle_render(item)
        return False

    def _reveal_render(self):
        """Show the staged diagram, then light the steps that waited for it."""
        req_id, scene, form = self._staged
        self._staged = None
        now = time.monotonic()
        try:
            self.scene.render_commit(scene, form, now)
            self._apply_state()
        except Exception as error:
            self._drop_bad_scene("reveal", error, now)
            self._drain_render(self._render_seq)
            return
        self._drain_render(self._render_seq)

    # ---- the stage host ----
    def _staging(self):
        return self.stage_on and self.stage.usable()

    def _stage_context(self):
        """The stage follows the presence: its theme, light or dark, its screen, and where the captions end."""
        geo = self.monitor.get_geometry() if self.monitor is not None else None
        self.stage.set(theme=self.scene.pack_name if self.scene.pack_name in ("devs", "nova") else "devs",
                       mode=self._theme_now(), monitor=[geo.x, geo.y, geo.width, geo.height] if geo else None,
                       top=round((self.top or 0) + self.scene.lift + ORB_H + CAPTION_H - 24))

    def _stage_panel_message(self):
        return {"panel": {"text": self.answer}, "index": len(self.answers) - 1 - self.answer_at,
                "count": len(self.answers)}

    def _stage_hide(self):
        self._stage_panel = False
        self.stage.hide()

    def _stage_fall_back(self, why):
        """The stage cannot draw: the panel it showed goes back to the overlay at once."""
        panel, self._stage_panel = self._stage_panel, False
        self.stage.hide()
        if panel:
            self._open_answer()
            print(f"stage: {why}; the overlay draws it", file=sys.stderr, flush=True)

    def _from_stage(self, data):
        """Events from the stage host: the user's picks, copies, links and closes, and its failures."""
        event = data.get("event")
        if event == "failed":
            self._stage_fall_back(data.get("error") or "the stage failed")
        elif event == "pick" and isinstance(data.get("data"), int) and self.answers:
            self.answer_at = max(0, min(len(self.answers) - 1, len(self.answers) - 1 - data["data"]))
            self.answer = self.answers[self.answer_at]
            self._show_history()
            self.stage.send(self._stage_panel_message())
        elif event == "history" and self.answers:
            self.stage.send({"history": [{"text": text} for text in reversed(self.answers)],
                             "now": len(self.answers) - 1 - self.answer_at})
        elif event == "copy" and isinstance(data.get("data"), str):
            self._wl_copy(data["data"])
        elif event == "link" and str(data.get("href", "")).startswith(("https://", "http://")):
            _open_link(data["href"])
        elif event == "close":
            if self._stage_panel:
                self._close_answer()
            else:
                self._stage_hide()

    def _set_font(self, name):
        if name not in FONTS:
            print(f"font: no option named {name!r}", file=sys.stderr, flush=True)
            return
        _use_font(FONTS[name])
        self.scene.refont()
        self._caption_key = None
        self.area.queue_draw()
        self.caption_area.queue_draw()

    def _set_light_dust(self, name):
        """The light theme's dust. In the dark theme it is kept and shows when the theme turns light."""
        if name not in LIGHT_LOOKS:
            print(f"light_dust: no look named {name!r}", file=sys.stderr, flush=True)
            return
        if name != LIGHT_LOOK:
            _use_light_look(name)
            self.scene.retheme()
            self._caption_key = None
            self.area.queue_draw()
            self.caption_area.queue_draw()

    def _set_pack(self, name):
        """Switch the active presence theme pack (e.g. 'devs' or 'nova')."""
        self.scene.set_pack(name, time.monotonic())
        self.area.queue_draw()

    def _apply_state(self):
        s = self.scene.state
        safe_spoken = _safe_utf8(self.spoken)
        self.spoken_label.set_label(safe_spoken)
        # The card is an overlay child, which GTK sizes narrower than a wrapping label's natural width; a minimum
        # of the text's own length (up to the wrap width) keeps a short line on one line and a long one 48 wide.
        self.spoken_label.set_width_chars(min(len(safe_spoken), 48))
        devs = self._devs_card()  # Its tag and queue mark say what the spoken line says.
        self.spoken_label.set_visible(bool(self.spoken) and s in ("ready", "permission", "error") and not devs)
        self.stop_btn.set_visible(s in ("thinking", "speaking"))
        self.permission_box.set_visible(s == "permission")
        questions = bool(self.answer_fields)
        for widget, on in ((self.devs_head, devs), (self.devs_request_view, devs and not questions),
                           (self.devs_row, devs), (self.request_view, not devs and not questions),
                           (self.permission_row, not devs)):
            widget.set_visible(on)
        if self.card_body.has_css_class("devs") != devs:
            self.card_body.set_css_classes(["rook-card", "devs"] if devs else ["rook-card"])
        for side, px in (("top", CARD_FALL + 22), ("bottom", 16), ("start", CARD_PAD), ("end", CARD_PAD)):
            getattr(self.card_body, f"set_margin_{side}")(px if devs else 14)
        home = self.scene.is_home(time.monotonic(), self._held())
        self.card.set_visible(not home and (s in ("permission", "error") or (
            self.hovered and s in ("thinking", "speaking"))))
        keyboard = LayerShell.KeyboardMode.ON_DEMAND if s == "permission" and self.answer_fields else LayerShell.KeyboardMode.NONE
        if LayerShell.get_keyboard_mode(self.win) != keyboard:
            LayerShell.set_keyboard_mode(self.win, keyboard)
        if self._should_show(time.monotonic()) and not self.quitting:
            self.win.set_visible(True)
        self._region_key = None

    def _stop(self, *_):
        self.scene.clear_captions(time.monotonic())
        self._emit({"event": "interrupt"})

    def _hover(self, value):
        # The resting loop is not part of the turn, so hovering it neither shows the card nor holds a turn open.
        self.hovered = value and not self.scene.home
        self._apply_state()

    def _held(self):
        """Hovering keeps an error open."""
        return self.hovered and self.scene.state == "error"

    # ---- the written answer ----
    def _build_answer(self):
        """The last-answer panel: a layer-shell window of its own, so it can be wider than the overlay, move, and take
        keyboard focus on demand for copying, while the overlay itself never takes focus. Its body is a read-only text
        view, so the text can be selected and copied."""
        win = Gtk.Window(application=self)
        LayerShell.init_for_window(win)
        LayerShell.set_namespace(win, "rook-answer")
        LayerShell.set_layer(win, LayerShell.Layer.OVERLAY)
        LayerShell.set_keyboard_mode(win, LayerShell.KeyboardMode.NONE)
        LayerShell.set_anchor(win, LayerShell.Edge.TOP, True)
        LayerShell.set_anchor(win, LayerShell.Edge.LEFT, True)
        win.add_css_class("rook")
        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        frame.add_css_class("rook-term")
        header = Gtk.Box(spacing=8)
        header.add_css_class("term-head")
        title = Gtk.Label(xalign=0, hexpand=True)
        title.set_markup(f'<span foreground="{_hex(PALE_GOLD)}" weight="bold">rook</span>'
                         f'<span foreground="{_hex(TERM_DIM)}"> · last answer</span>')
        header.append(title)
        self.history_back = self._term_button(HISTORY_BACK, lambda _b: self._step_history(-1))
        self.history_label = Gtk.Label()
        self.history_next = self._term_button(HISTORY_NEXT, lambda _b: self._step_history(1))
        for widget in (self.history_back, self.history_label, self.history_next):
            header.append(widget)
        header.append(self._term_button("copy all", lambda b: self._copy(self.answer, b, "copy all")))
        close = self._term_button("✕", lambda _b: self._close_answer())
        close.add_css_class("close")
        header.append(close)
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._drag_begin)
        drag.connect("drag-update", self._drag_update)
        header.add_controller(drag)
        view = _TermView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                            left_margin=TERM_PAD_X, right_margin=TERM_PAD_X, top_margin=TERM_PAD_TOP,
                            bottom_margin=TERM_PAD_BOTTOM)
        # A click on a link opens it, unless the press selected text; the pointer is a hand over a link.
        click = Gtk.GestureClick()
        click.connect("released", lambda _g, _n, x, y: (url := self._link_at(x, y))
                      and not view.get_buffer().get_has_selection() and _open_link(url))
        view.add_controller(click)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", lambda _m, x, y: view.set_cursor_from_name(
            "pointer" if self._link_at(x, y) else "text"))
        view.add_controller(motion)
        scroll = Gtk.ScrolledWindow(child=view)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        frame.append(header)
        frame.append(scroll)
        win.set_child(frame)
        # With keyboard focus (after a click in the panel): Ctrl+C is the text view's own; Ctrl+Shift+C copies the
        # selection too, as in a terminal; Escape closes the panel.
        keys = Gtk.ShortcutController()
        keys.add_shortcut(Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string("<Control><Shift>c"),
                                           Gtk.CallbackAction.new(lambda *_: view.emit("copy-clipboard") or True)))
        keys.add_shortcut(Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string("Escape"),
                                           Gtk.CallbackAction.new(lambda *_: self._close_answer() or True)))
        win.add_controller(keys)
        self.answer_win, self.answer_frame, self.answer_scroll, self.answer_view = win, frame, scroll, view
        self._show_history()

    def _link_at(self, x, y):
        """The http or https address of the link at (x, y) in the text view, or None."""
        view = self.answer_view
        found, it = view.get_iter_at_location(*view.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, int(x), int(y)))
        for tag in it.get_tags() if found else ():
            if (url := tag.props.font_features or "").startswith(("http://", "https://")):
                return url
        return None

    def _show_history(self):
        """The header's position, as "3 / 10" counted from the oldest, and the arrows, each dimmed at its end."""
        count = len(self.answers)
        self.history_label.set_markup(f'<span foreground="{_hex(TERM_DIM)}">{self.answer_at + 1 if count else 0}'
                                      f' / {count}</span>')
        self.history_back.set_sensitive(self.answer_at > 0)
        self.history_next.set_sensitive(self.answer_at < count - 1)

    def _step_history(self, step):
        if 0 <= self.answer_at + step < len(self.answers):
            self.answer_at += step
            self.answer = self.answers[self.answer_at]
            self._show_history()
            self._show_answer()

    def _term_button(self, label, handler):
        button = Gtk.Button(label=label, focusable=False, focus_on_click=False, valign=Gtk.Align.CENTER)
        button.add_css_class("term")
        button.connect("clicked", handler)
        return button

    def _copy(self, text, button=None, label="copy"):
        """Put text on the clipboard and show "copied" on the button for a moment. With the panel holding keyboard
        focus, GTK's own clipboard is used. Without it (WoW mode, or before any click brought focus) a layer surface
        cannot be sure to own the selection, so wl-copy sets it through Hyprland's data-control protocol."""
        if not text:
            return
        if not (self.answer_win.is_active() and self._gdk_copy(text)) and not self._wl_copy(text):
            self._gdk_copy(text)
        if button is not None:
            button.set_label("copied")
            button.add_css_class("done")

            def back():
                button.set_label(label)
                button.remove_css_class("done")
                return False
            GLib.timeout_add(1200, back)

    def _gdk_copy(self, text):
        try:
            self.answer_win.get_clipboard().set(GObject.Value(GObject.TYPE_STRING, text))
            return True
        except (TypeError, GLib.Error):
            return False

    @staticmethod
    def _wl_copy(text):
        if not shutil.which("wl-copy"):
            return False
        try:
            subprocess.run(["wl-copy"], input=text.encode(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=2, check=True)
            return True
        except (OSError, subprocess.SubprocessError):
            return False

    def _show_answer(self, keep_scroll=False):
        """Fill the panel with the last answer as terminal paragraphs, with a copy control on each code block, then
        size and place it."""
        view = self.answer_view
        adj = self.answer_scroll.get_vadjustment()
        keep = adj.get_value() if keep_scroll else 0.0
        font = _font(_terminal_family(), TERM_PX)
        ch = view.get_pango_context().get_metrics(font, None).get_approximate_char_width() / Pango.SCALE
        width = _panel_rect(self.bounds or (0, 0, 1920, 1080), 0, 0)[2]
        paragraphs = _terminal_paragraphs(_md_blocks(self.answer), ch, int((width - 2 * TERM_PAD_X) / ch) - 1)
        for anchor, raw in _fill_buffer(view.get_buffer(), paragraphs):
            view.add_child_at_anchor(self._term_button(
                "copy", lambda b, raw=raw: self._copy(_code_copy_text(raw), b, "copy")), anchor)
        self._answer_shown = self.answer
        self._place_answer()
        adj.set_value(keep)
        if keep:
            # Refilling the buffer clamps the scroll to the empty view, and the text view measures its lines over the
            # next frames; set the scroll again until it holds.
            tries = [12]

            def hold():
                adj.set_value(keep)
                tries[0] -= 1
                return abs(adj.get_value() - keep) > 0.5 and tries[0] > 0
            GLib.timeout_add(TICK_MS, hold)

    def _place_answer(self):
        """Size the panel to its answer, up to its cap, and keep it inside its bounds: by default centred under the
        swarm where the captions start, or where the owner dragged it. Its height comes from the same Pango layout
        the render uses, because a text view measures its lines only once it shows them."""
        bounds = self.bounds or (0, 0, 1920, 1080)
        centre = (self.left or 0) + WIDTH / 2
        anchor = (self.top or 0) + self.scene.lift + ORB_H
        w, cap = _panel_rect(bounds, centre, anchor)[2], _panel_rect(bounds, centre, anchor)[4]
        key = (self.answer, w)
        if self._answer_size is None or self._answer_size[0] != key:
            page = Page(self.answer)
            page.lay_out(self.answer_view.get_pango_context(), w - 2)
            self._answer_size = (key, page.height)
        content = int(min(self._answer_size[1], cap - TERM_HEAD_H - 2))
        x, y, w, h, cap = _panel_rect(bounds, centre, anchor, self.panel_pos, TERM_HEAD_H + 2 + content)
        self.answer_scroll.set_min_content_height(-1)  # GTK wants min <= max at every step.
        self.answer_scroll.set_max_content_height(content)
        self.answer_scroll.set_min_content_height(content)
        self.answer_frame.set_size_request(w, h)
        self.answer_win.set_default_size(w, h)
        if self.monitor is not None:
            LayerShell.set_monitor(self.answer_win, self.monitor)
        LayerShell.set_margin(self.answer_win, LayerShell.Edge.LEFT, x)
        LayerShell.set_margin(self.answer_win, LayerShell.Edge.TOP, y)
        self._answer_xy = (x, y)

    def _answer_keyboard(self):
        """The panel takes keyboard focus only when clicked, to copy with the keyboard, and never in the game."""
        mode = LayerShell.KeyboardMode.NONE if self.wow and self.in_game else LayerShell.KeyboardMode.ON_DEMAND
        if LayerShell.get_keyboard_mode(self.answer_win) != mode:
            LayerShell.set_keyboard_mode(self.answer_win, mode)

    def _drag_begin(self, _gesture, _x, _y):
        self._drag = (_hypr_socket("j/cursorpos"), self._answer_xy)

    def _drag_update(self, _gesture, dx, dy):
        """Move the panel with the pointer by its header. Hyprland's cursor position makes the move absolute; without
        it the drag offset, which is relative to the moving panel, adds to where the panel is."""
        start, (x0, y0) = self._drag or (None, self._answer_xy)
        now = _hypr_socket("j/cursorpos") if start else None
        if now:
            x, y = x0 + now["x"] - start["x"], y0 + now["y"] - start["y"]
        else:
            x, y = self._answer_xy[0] + dx, self._answer_xy[1] + dy
        self.panel_pos = (x, y)
        self._place_answer()

    def _set_answer(self, text):
        """A new written answer becomes the newest in the history, and the panel shows it. An open panel shows it in
        place: from the top for a new answer, at the same scroll for more of the answer already shown."""
        newest = self.answers[-1] if self.answers else ""
        if text == newest:
            return
        same = bool(newest) and newest.strip().split("\n\n")[0] == text.strip().split("\n\n")[0]
        self.answers = (self.answers[:-1] if same else self.answers[1 - ANSWER_HISTORY:]) + [text]
        same = same and self.answer == newest
        self.answer, self.answer_at = text, len(self.answers) - 1
        self._show_history()
        if self._stage_panel:
            self.stage.send(self._stage_panel_message())
        if self.answer_open:
            self._show_answer(keep_scroll=same)

    def _open_answer(self):
        if not self.answer or self.answer_open or self._stage_panel:
            return
        if self.answer_at != len(self.answers) - 1:  # The panel opens on the newest answer.
            self.answer, self.answer_at = self.answers[-1], len(self.answers) - 1
            self._show_history()
        if self._staging():
            self._stage_context()
            if self.stage.send(self._stage_panel_message()):
                self._stage_panel = True
                return
        self.answer_open = True
        self._answer_keyboard()
        if self._answer_shown != self.answer:
            self._show_answer()
        else:
            self._place_answer()
            self.answer_scroll.get_vadjustment().set_value(0)
        self.answer_win.set_opacity(0.0)
        self.answer_win.set_visible(True)

    def _close_answer(self, at_once=False):
        """Close the panel: only from its close mark, Escape, a click on the resting loop or the captions, or when
        Rook steps aside (the game takes focus without WoW mode, or loses it in WoW mode)."""
        if self._stage_panel:
            self._stage_hide()
        self.answer_open = False
        if at_once:
            self.answer_mix = 0.0
            self.answer_win.set_visible(False)
        self._region_key = None

    def _toggle_answer(self):
        if self.answer_open or self._stage_panel:
            self._close_answer()
        else:
            self._open_answer()

    def _caption_clicked(self, *_):
        if self.details.strip() and self.scene.captions:
            self._toggle_answer()

    def _on_loop(self, x, y):
        w, h = LOOP_HIT
        cx = self._canvas_cx(self.area.get_width() or self._win_width)
        return self.scene.home and abs(x - cx) <= w / 2 and abs(y - self.scene.rest_pad) <= h / 2

    # ---- dragging Rook aside ----
    def _away(self):
        if self.home_xy is None:
            return False
        # Account for temporary horizontal expansion during a dispatch fan so the presence never reads as dragged away.
        cx = float(self._dispatch_cx) if self._dispatch_cx is not None else WIDTH / 2.0  # The presence's x in the window.
        base_left = round(self.left + cx - WIDTH / 2.0) if self.left is not None else self.left
        return (base_left, self.top) != self.home_xy

    def _carry_begin(self, _gesture, x, y):
        self.carry = [_hypr_socket("j/cursorpos"), (self.left, self.top), (x, y), False]

    def _carry_update(self, _gesture, dx, dy):
        """Move Rook with the pointer once it has moved DRAG_START pixels. A new drag cancels the wait or the flight
        home. In the game and without Hyprland's placement Rook stays put, and the press is only a click."""
        start, (x0, y0), _, moving = self.carry
        if not moving:
            if math.hypot(dx, dy) < DRAG_START:
                return
            self.carry[3] = True
            self.return_at = self.flight = None
            if self._centred and self._win_width != WIDTH and self.left is not None:
                # A wide, centred window goes to the left margin as drawn: its left edge, and Rook's x in it.
                off = (self._win_width - WIDTH) // 2
                self.left, self._dispatch_cx = self.left - off, WIDTH / 2.0 + off
                self.carry[1] = (self.left, self.top)
                x0 = self.left
        if self.in_game or self.left is None:
            return
        now = _hypr_socket("j/cursorpos") if start else None
        if now:
            x, y = x0 + now["x"] - start["x"], y0 + now["y"] - start["y"]
        else:
            x, y = self.left + dx, self.top + dy
        if self.bounds:
            # The resting loop stays whole on its own monitor.
            bx, by, bw, bh = self.bounds
            x = min(max(x, bx + LOOP_HIT[0] / 2 - WIDTH / 2), bx + bw - LOOP_HIT[0] / 2 - WIDTH / 2)
            y = min(max(y, by + LOOP_HIT[1] / 2 - self.scene.rest_pad), by + bh - LOOP_HIT[1] / 2 - self.scene.rest_pad)
        self._move_window(round(x), round(y))

    def _replay_clicked(self, gesture, _n, x, y):
        """A right-click on the resting loop. On Wayland an overlay with no keyboard focus never learns that Shift is
        held, so Rook reads Shift from the keyboard itself and decides; shift says what GTK saw, which may be False."""
        if self._on_loop(x, y):
            self._emit({"event": "debug_replay",
                        "shift": bool(gesture.get_current_event_state() & Gdk.ModifierType.SHIFT_MASK)})

    def _carry_end(self, _gesture, _dx, _dy):
        _, _, (x, y), moving = self.carry
        self.carry = None
        if not moving:
            if self._on_loop(x, y) and self.answer:
                self._toggle_answer()
        elif self._away():
            self.return_at = time.monotonic() + RETURN_SECONDS
        else:
            self._place("a drag ended")

    def _move_window(self, x, y):
        if self._centred:  # Off its home, the left margin places the window.
            self._centred = False
            LayerShell.set_anchor(self.win, LayerShell.Edge.LEFT, True)
        self.left, self.top = x, y
        LayerShell.set_margin(self.win, LayerShell.Edge.LEFT, x)
        LayerShell.set_margin(self.win, LayerShell.Edge.TOP, y)
        if self.answer_open:
            self._place_answer()

    def _step_home(self, now):
        """The flight home: open the reading surface over the way home, then move the window home with the grains
        kept where they are on screen, so the swarm's own springs fly them home. The surface closes once every
        grain is back inside the window, and Rook is placed again. An open answer panel keeps Rook aside at rest."""
        if (self.return_at is not None and now >= self.return_at and self.carry is None
                and not (self.answer_open and self.scene.home)):
            self.return_at = None
            if self._away():
                (ax, ay), (hx, hy) = (self.left, self.top), self.home_xy
                pad = int(0.15 * math.hypot(ax - hx, ay - hy))
                x0, y0 = min(ax, hx) - pad, min(ay, hy) - pad
                x1, y1 = max(ax, hx) + WIDTH + pad, max(ay, hy) + self.scene.lift + ORB_H + pad
                if self.bounds:
                    bx, by, bw, bh = self.bounds
                    x0, y0, x1, y1 = max(x0, bx), max(y0, by), min(x1, bx + bw), min(y1, by + bh)
                self.flight = (int(x0), int(y0), int(x1 - x0), int(y1 - y0))
        if self.flight is None:
            return
        scene = self.scene
        if self._away():
            if self.reader_ready:
                self._jump_home()
                scene.prev, scene.form_at, scene.loosen = scene.form, now, 1.0
            return
        top = scene.lift + ORB / 2
        if all(abs(scene.x[i]) < ORB_W / 2 - 6 and 6 - top < scene.y[i] < ORB_H - ORB / 2 - 6 for i in scene.idx):
            self.flight = None
            self._place("Rook flew home")

    def _jump_home(self):
        """Move a dragged Rook home at once, with every grain kept where it is on screen."""
        if not self._away():
            return
        scene = self.scene
        dx, dy = self.left - self.home_xy[0], self.top - self.home_xy[1]
        self._move_window(*self.home_xy)
        for i in scene.idx:
            scene.x[i] += dx
            scene.y[i] += dy
        vx, vy, rx, ry = scene.vignette
        scene.vignette = (vx + dx, vy + dy, rx, ry)

    def _loop_pointer(self, x, y):
        self.scene.rest_hint = bool(self.answer) and self._on_loop(x, y)

    def _step_answer(self, dt):
        """Ease the panel open or closed, following the overlay's own fade. Nothing to do while it is closed."""
        goal = 1.0 if self.answer_open else 0.0
        if self.answer_mix != goal:
            self.answer_mix = min(1.0, max(0.0, self.answer_mix + (dt if self.answer_open else -dt) / PANEL_OPEN_SECONDS))
            if self.answer_mix == 0.0:
                self.answer_win.set_visible(False)
            if self.scene.captions:
                self.caption_area.queue_draw()
        if self.answer_win.get_visible():
            self.answer_win.set_opacity(_ease_out(self.answer_mix) * self.opacity)

    def _should_show(self, now):
        """Rook shows everywhere, at rest and in a turn, except at rest while dark. The media viewer shows while dark
        too: the owner asked for it."""
        return not (self.dark and self.scene.view is None and self.scene.is_home(now, self._held()))

    def _show_permission(self, questions):
        while child := self.permission_fields.get_first_child():
            self.permission_fields.remove(child)
        self.answer_fields = []
        for question in questions:
            label = _safe_utf8(question["question"])
            self.permission_fields.append(Gtk.Label(label=label, wrap=True, xalign=0, css_classes=["card-text"],
                                                    width_chars=min(len(label), 48), max_width_chars=48))
            options = _safe_utf8("\n".join(option["label"] for option in question.get("options", [])))
            if options:
                self.permission_fields.append(Gtk.Label(label=options, wrap=True, xalign=0, max_width_chars=48,
                                                        css_classes=["card-text"]))
            entry = Gtk.Entry(placeholder_text="Your answer")
            self.permission_fields.append(entry)
            self.answer_fields.append((question["question"], entry))
        self.permission_fields.set_visible(bool(questions))
        self.allow_btn.set_label("Send answers" if questions else "Allow")
        if self.face is not None:
            self.face.allow_text = self.allow_btn.get_label()
            self.devs_head.set_content_height(len(self.face.lines) * CARD_LINE + 2)
            self.devs_request.set_content_height(max(1, self.face.req_h))
            for face, primary in zip(self.devs_buttons, (False, True)):
                face.set_content_width(math.ceil(_CardFace.ink_w(self.face.button_text(primary))) + 31)
            for area in (self.card_panel, self.devs_head, self.devs_request, *self.devs_buttons):
                area.queue_draw()

    def _open_card(self, msg):
        """Show the card a permission message brings: its id, a fresh Devs face or none, and its form."""
        if msg.get("card") != self.card_id or self.face is None:
            self.card_at = time.monotonic()  # A new card arrives; the same card again does not replay it.
        if msg.get("card") != self.card_id:  # A new card's request starts at its top, not where the last one was.
            for view in (self.request_view, self.devs_request_view):
                view.get_vadjustment().set_value(0)
        self.card_id = msg.get("card")  # The answer names this card, so a late tap never answers the next one.
        # The face is built fresh for this card, or there is none: never the card before's words under this id.
        self.face = None
        try:
            if LETTERING:
                self.face = _CardFace(msg.get("tool"), msg.get("who"), self.card_details, msg.get("count", 1))
            self._show_permission(msg.get("questions") or [])
        except Exception as exc:
            print(f"overlay: the Devs card failed ({type(exc).__name__}: {exc}); showing the plain card",
                  file=sys.stderr, flush=True)
            self.face = None
            self._show_permission(msg.get("questions") or [])

    def _devs_draw(self, draw, cr, *args):
        """Draw a part of the Devs card with draw, a _CardFace method, and return whether it drew. A failure logs,
        drops the face and shows the plain card from the next frame, with this card's own request and id."""
        if not self._devs_card():
            return False
        try:
            draw(self.face, cr, *args)
            return True
        except Exception as exc:
            print(f"overlay: drawing the Devs card failed ({type(exc).__name__}: {exc}); showing the plain card",
                  file=sys.stderr, flush=True)
            self.face = None
            self.card_panel.queue_draw()
            GLib.idle_add(self._apply_state)
            return False

    def _request_in_view(self):
        """The part of the Devs card's request in view, top and bottom, in its own pixels."""
        scroll = self.devs_request_view.get_vadjustment()
        return scroll.get_value(), scroll.get_value() + max(scroll.get_page_size(), 320)

    def _devs_card(self):
        """Whether the card on show is the Devs permission card: the Devs lettering is on and a card waits."""
        return self.face is not None and LETTERING is not None and self.scene.state == "permission"

    def _card_t(self):
        """Seconds since the Devs card arrived, or None once it has fully arrived."""
        t = time.monotonic() - self.card_at
        return None if t >= CARD_ENTRANCE else t

    def _permission(self, allow):
        event = {"event": "permission", "allow": allow, **({"card": self.card_id} if self.card_id else {})}
        if allow and self.answer_fields:
            answers = {label: entry.get_text().strip() for label, entry in self.answer_fields}
            if not all(answers.values()):
                return
            event["answers"] = answers
        self._emit(event)

    # ---- animation ----
    def _again(self, fps):
        """Run the next tick at fps: the timer is set again only when its pace changes."""
        ms = max(TICK_MS, round(1000 / fps)) if fps < 1000 / TICK_MS else TICK_MS
        if ms == self._tick_ms:
            return True
        self._tick_ms = ms
        self._timer = GLib.timeout_add(ms, self._tick)
        return False

    def _pace(self, now, show):
        """How often to tick now. Full speed while anything moves quickly; slower in the quiet moments (see
        REST_FPS), and slowest while no frame of Rook's has been shown for a second: the screen is locked or asleep."""
        if self.quitting or not show or self.opacity != 1.0 or self.flight is not None:
            return 1000 / TICK_MS
        if now - self._shown_at > 1.0 and now - self._mapped_at > 2.0:
            return UNSEEN_FPS
        if (self.scene.captions or self._caption_drawn
                or self.answer_mix != (1.0 if self.answer_open else 0.0)):
            return 1000 / TICK_MS
        if (self.scene.pack_kind == "flipbook" and self.scene.flipbook is not None
                and (self.scene.flipbook.changing(now) or self.scene.dispatch_active(now))):
            return 1000 / TICK_MS
        if self.scene.idx is self.scene.rest_idx:
            return GAME_REST_FPS if self.game_focused or self.in_game else REST_FPS
        if self.scene.form == "render" and now - self.scene.form_at > 1.5:
            return RENDER_FPS
        if self._viewer_quiet(now):
            return VIEW_REST_FPS
        return 1000 / TICK_MS

    def _clock_widget(self):
        """The widget whose frame clock drives the ticks now, or None for the tick timer, which would beat against the
        display: the viewer while the GL frame draws its dust, and the main window while the swarm rests in its loop on
        screen. Hidden (dark mode, the game without WoW mode) or in a turn, the timer paces Rook as before."""
        if self.quitting:
            return None
        if self.viewer_ready and self.viewer.get_visible() and self.scene.view is not None and self._dust_on_gpu():
            return self.viewer_area
        if (self.scene.view is None and self.win.get_visible() and self.opacity == 1.0 and self.flight is None
                and self.reader_box is None and self._should_show(time.monotonic())):
            # The dust surface's own frame callbacks while it draws the dust, so GTK's frame clock can rest.
            return self._surface if self._surface is not None and self._surface_drawing() else self.area
        return None

    def _clocked(self):
        return self._clock_widget() is not None

    def _clock_fps(self):
        scene = self.scene
        if self._clock_on is self.viewer_area:
            return VIEW_GL_FPS
        if (scene.pack_kind == "flipbook" and scene.flipbook is not None
                and (scene.flipbook.changing(scene.last) or scene.dispatch_active(scene.last))):
            return VIEW_GL_FPS
        if scene.idx is scene.rest_idx:
            return GAME_CLOCK_FPS if self.game_focused or self.in_game else REST_CLOCK_FPS
        if scene.form == "render" and scene.last - scene.form_at > 1.5 and not scene.springs_on_gpu:
            return RENDER_FPS  # A formed scene moves slowly when Cairo draws it, so it costs the game less.
        return VIEW_GL_FPS

    def _clock_tick(self, _area, _clock):
        """Each frame of the display: tick at most _clock_fps times a second, on whole display frames. Once no widget
        needs the frame clock, the tick timer takes over again."""
        if not self._clocked():
            self._viewer_clock = None
            self._restart_timer()
            return False
        now = time.monotonic()
        if now - self._clock_at >= 1 / self._clock_fps() - 0.004:
            self._clock_at, self._clock_ran = now, True
            self._tick(clocked=True)
        return True

    def _restart_timer(self):
        if self._timer:
            GLib.source_remove(self._timer)
        self._tick_ms = TICK_MS
        self._timer = GLib.timeout_add(TICK_MS, self._tick)

    def _tick(self, clocked=False):
        if not clocked and self._viewer_clock is not None and self._clock_ran:
            self._clock_ran = False
            return True  # The viewer's frame clock ticks; this timer only stands by.
        now = time.monotonic()
        show = not self.quitting and self._should_show(now)
        if (not show and self.opacity == 0 and not self.win.get_visible() and not self.quitting
                and self._media_loaded is None):  # A file loaded while dark still opens the viewer.
            return True if clocked else self._again(UNSEEN_FPS * 2)
        home = self.scene.is_home(now, self._held())
        if home != self._home_was:
            self._home_was = home
            if home:
                # A turn has ended: follow the focused monitor if it changed during the turn.
                self._place("a turn ended")
            elif self.carry is None and self._away():
                # A new turn sends a dragged Rook home first, so the turn shows where it always does.
                self.return_at = now
            self._apply_state()
        dt = 1 / self._clock_fps() if clocked else self._tick_ms / 1000
        self._step_answer(dt)
        media = self.media
        self.scene.view_video = media is not None and media.kind == "video" and media.playing
        self.scene.dust_gl = self._dust_on_gpu()
        # The main window's springs go to the chip only once GL is known to work here, so a failed start keeps Cairo,
        # and not while the reading surface draws the grains or while a flipbook pack (Nova) is active.
        flipbook_active = (self.scene.pack_kind == "flipbook" and self.scene.flipbook is not None
                           and self.scene.form != "render" and not self.scene.dispatch_nova_standin(now))
        self.scene.spring_gl = ((not flipbook_active) and self._main_gl() is not None
                                and self.reader_box is None and self.flight is None)
        if not flipbook_active and self.scene.springs_on_gpu and self.scene.spring_gl:
            try:
                self._main_gl().follow(self.scene)
            except Exception as error:
                if self._surface is None:
                    raise
                self._surface_down("following the grains failed", error)
        self.scene.view_still = self.scene.view_video and not self.scene.dust_gl
        try:
            self.scene.step(now, self._held())
        except Exception as error:
            if self.scene.render is None:
                raise
            self._drop_bad_scene("step", error, now)
            self.scene.step(now, self._held())
        self._size_canvas(now)
        self._trace_send(now)
        if (not flipbook_active and len(self.scene.spring_steps) > 30
                and self._surface is not None and self._surface.gl.springs_owned):
            # No frame has drawn the grains' steps for a while (the screen is locked): the chip runs them now.
            try:
                self._surface.gl.catch_up(self.scene)
            except Exception as error:
                self._surface_down("catching up failed", error)
        if not flipbook_active and len(self.scene.spring_steps) > 30 and isinstance(self._dust_gl, _DustGL):
            # No frame has drawn the grains' steps for a while (the screen is locked): the chip runs them now.
            try:
                self._dust_gl.catch_up(self.scene)
            except Exception as error:
                print(f"the GL grains failed, so Cairo draws them: {error}", file=sys.stderr, flush=True)
                self._dust_gl = False
        self.opacity += ((1.0 if show else 0.0) - self.opacity) * _glide(dt, 0.11 if show else 0.12)
        if show and self.opacity > 0.995:
            self.opacity = 1.0
        if not show and self.opacity < 0.01:
            self.opacity = 0.0
            if self.quitting:
                self._drop_media()
                self.quit()
                return False
            if self.win.get_visible():
                self.win.set_visible(False)
        self.card_mix += ((1.0 if self.card.get_visible() else 0.0) - self.card_mix) * _glide(dt, 0.08)
        self.win.set_opacity(self.opacity)
        vis = _smooth(self.scene.swarm_vis)
        self.area.set_opacity(vis)
        self.caption_area.set_opacity(vis)
        guide = self.scene.guide_shown
        caption_h = CAPTION_H + GUIDE_ROOM if guide and guide[1] and not guide[2] else CAPTION_H  # A code in a turn.
        if self._caption_h != caption_h:
            self._caption_h = caption_h
            self.caption_area.set_content_height(caption_h)
        self._step_home(now)
        self._update_input_region()
        self._sync_reader()
        self._step_viewer(now)
        if self._surface is not None:
            try:
                self._present_surface()
            except Exception as error:
                self._surface_down("drawing the dust failed", error)
        if self._surface is not None and self._surface_drawing():
            # Only the text is GTK's now: draw the window again when the text it shows changes.
            scene = self.scene
            key = (scene.label, round(scene.label_alpha, 3), scene.rest_hint, scene.guide_key(),
                   now if (scene.render is not None and scene.form == "render") or scene.dispatch_active(now) else None)
            if key != self._text_key:
                self._text_key = key
                self.area.queue_draw()
        elif self.scene.swarm_vis > 0.002 or self._text_key != "hidden":
            self._text_key = "hidden" if self.scene.swarm_vis <= 0.002 else None
            self.area.queue_draw()
        caption_key = None if self.scene.swarm_vis <= 0.002 else self.scene.caption_key(WIDTH, now, self._caption_dim())
        if self.scene.guide_shown and not self.scene.guide_shown[2] and self.scene.swarm_vis > 0.002:
            caption_key = (caption_key, self.scene.guide_key(self._caption_dim()))
        if caption_key is not None:
            caption_key = (caption_key, self._monitor_scale())
        if caption_key != self._caption_key:
            self._caption_key = caption_key
            self.caption_area.queue_draw()
        self._caption_drawn = bool(self.scene.captions)
        if self._devs_card() and self.card.get_visible():
            # The Devs card redraws every tick while it arrives, then only its frame, CARD_REST_FPS times a second.
            if now - self.card_at < CARD_ENTRANCE + 0.1:
                for area in (self.card_panel, self.devs_head, self.devs_request, *self.devs_buttons):
                    area.queue_draw()
            elif now - self._card_breath >= 1 / CARD_REST_FPS:
                self._card_breath = now
                self.card_panel.queue_draw()
        widget = self._clock_widget()
        if widget is not None:
            # A frame clock ticks from here on (see _clock_tick). The timer stands by, slowly, for a display that stops
            # sending frames, as a locked screen does.
            if self._viewer_clock is not None and self._clock_on is not widget:
                self._clock_on.remove_tick_callback(self._viewer_clock)
                self._viewer_clock = None
            if self._viewer_clock is None:
                self._clock_on, self._viewer_clock = widget, widget.add_tick_callback(self._clock_tick)
            return True if clocked else self._again(UNSEEN_FPS)
        if self._viewer_clock is not None:
            # No widget needs the frame clock: the timer takes over at once.
            self._clock_on.remove_tick_callback(self._viewer_clock)
            self._viewer_clock = None
            if clocked:
                self._restart_timer()
                return False
        return self._again(self._pace(now, show))

    def _size_canvas(self, now):
        """A scene or active dispatch fan gets the width it needs without ever shifting the presence on screen."""
        if self.carry is not None or self.flight is not None:
            # Never resize or shift margins mid-drag or mid-flight; apply once the drag/flight completes.
            return
        reach = self.scene.render_reach(now)
        if reach is not None:
            size = (self.scene.render_width_px, self.scene.lift + ORB // 2 + max(ORB_H - ORB // 2, reach))
            win_w = WIDTH
        elif self.scene.dispatch_active(now):
            win_w = self.scene.dispatch_canvas_width()
            size = (win_w, self.scene.lift + ORB_H)
        else:
            guide = self.scene.guide_shown and self.scene.guide_shown[2]  # At home it may be wider than the loop.
            width = min(WIDTH, max(ORB_W, 2 * math.ceil(self.scene.guide_w / 2 + GUIDE_MARGIN))) if guide else ORB_W
            size = (width, self.scene.lift + ORB_H)
            win_w = WIDTH
        if self._centred:
            # The compositor centres the window, so it grows and shrinks about the presence in the same commit as the
            # frame drawn at the new width, and a frame GTK draws at the old width still has the presence centred.
            if win_w != self._win_width:
                self._win_width = win_w
                self.column.set_size_request(win_w, -1)
        elif self._widen_to is not None and self.column.get_width() >= self._win_width:
            # GTK has laid the wider window out: its margin moves now, in the same commit as the frame drawn for it.
            self.left, self._dispatch_cx = self._widen_to
            self._widen_to = None
            LayerShell.set_margin(self.win, LayerShell.Edge.LEFT, self.left)
        if win_w != self._win_width:
            old_cx = float(self._dispatch_cx) if self._dispatch_cx is not None else WIDTH / 2.0
            self._widen_to = None
            cur_left = self.left if self.left is not None else (self.home_xy[0] if self.home_xy else 0)
            pres_x = cur_left + old_cx
            bx, bw = (self.bounds[0], self.bounds[2]) if self.bounds is not None else (0, int(self.scene.monitor_width or 2000))
            if win_w == WIDTH:
                new_left = int(round(pres_x - WIDTH / 2.0))
                new_cx = None
            else:
                new_left = int(round(pres_x - win_w / 2.0))
                new_left = max(int(bx), min(int(bx + bw - win_w), new_left))
                # Pin the presence to its exact screen pixel (new_left + new_cx == pres_x) even at screen edges.
                new_cx = float(pres_x - new_left)
            self._win_width = win_w
            self.column.set_size_request(win_w, -1)
            if not (self.left is not None or (self.home_xy is not None and self.home_xy[0] is not None)):
                self._dispatch_cx = new_cx
            elif win_w > WIDTH:
                # The margin set now would move the window before GTK draws it wider: the presence would jump aside
                # for a frame. It grows to the right first, the presence kept where it is, and moves once laid out.
                self._dispatch_cx = old_cx
                self._widen_to = (new_left, new_cx)
            else:
                self.left, self._dispatch_cx = new_left, new_cx
                LayerShell.set_margin(self.win, LayerShell.Edge.LEFT, new_left)
        if self.scene.dispatch_active(now):
            pres = win_w / 2.0 if self._centred else self._widen_to[1] if self._widen_to else (
                self._dispatch_cx or WIDTH / 2.0)
            self.scene.dispatch.layout_for_canvas(pres, win_w, self.scene.monitor_width)
        if (self.area.get_content_width(), self.area.get_content_height()) != size:
            self.area.set_content_width(size[0])
            self.area.set_content_height(size[1])

    def _trace_send(self, now):
        """_trace_step, which must never stop the clock: an error turns the trace off for this run, logged once."""
        if self._trace is False:
            return
        try:
            self._trace_step(now)
        except Exception as error:
            print(f"the send trace is off: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
            self._trace = False

    def _trace_step(self, now):
        """Each send's window, from its fan's start to SEND_TRACE_AFTER seconds after the fan has gone: one JSON line
        per tick, kept in memory and appended to SEND_TRACE when the send ends, so a frame costs a few microseconds.
        The file keeps about its last SEND_TRACE_LINES lines. For SEND_TRACE_HYPR seconds after the width changes,
        each line also holds the layer's x and width as Hyprland has them."""
        scene = self.scene
        active = scene.dispatch_active(now)
        if self._trace is None:
            if not active:
                return
            self._trace, self._trace_end, self._trace_hypr = [{
                "send": time.strftime("%Y-%m-%d %H:%M:%S"), "t": round(now, 4),
                "monitor": self.monitor.get_connector() if self.monitor is not None else None,
                "free_w": self.bounds[2] if self.bounds else None, "scale": self._monitor_scale()}], None, now
        elif self._trace[-1].get("req_w", self._win_width) != self._win_width:
            self._trace_hypr = now
        self._trace_end = None if active else self._trace_end or now + SEND_TRACE_AFTER
        hypr = None
        if now - self._trace_hypr < SEND_TRACE_HYPR:
            layers = _hypr_socket("j/layers")
            hypr = next(([layer.get("x"), layer.get("w")] for monitor in (layers or {}).values()
                         if isinstance(monitor, dict) for level in (monitor.get("levels") or {}).values()
                         for layer in level if layer.get("namespace") == "rook-overlay"), None)
        ds = scene.dispatch if active else None
        since = now - ds.t0 if ds is not None else 0.0
        phase = ("gone" if ds is None else "assembly" if since < ds.rows[0]["begin"] else "fire"
                 if since < ds.landed_at else "hold" if since < ds.end_at else "leaving")
        laid, area_w = self.column.get_width(), self.area.get_width()
        drawn = None if self._drawn is None else round((laid - self._drawn[0]) / 2 + self._drawn[1], 2)
        # The grains' mean x in the window (Python's copy, a frame behind the chip), and on the screen by Hyprland's x.
        grain_x = None if drawn is None or not scene.idx else round(
            drawn + sum(scene.x[i] for i in scene.idx) / len(scene.idx), 2)
        self._trace.append({
            "grain_x": grain_x, "screen_x": None if hypr is None or grain_x is None else round(hypr[0] + grain_x, 2),
            "t": round(now, 4), "req_w": self._win_width, "laid_w": laid, "area_w": area_w,
            "anchor": "centre" if self._centred else "left", "left": self.left,
            "margin": LayerShell.get_margin(self.win, LayerShell.Edge.LEFT), "hypr": hypr,
            "canvas_cx": round(self._canvas_cx(area_w or self._win_width), 2), "drawn_x": drawn,
            "form": scene.form, "phase": phase, "widen_to": self._widen_to})
        if self._trace_end is None or now < self._trace_end:
            return
        lines, self._trace = self._trace, None
        try:
            os.makedirs(os.path.dirname(SEND_TRACE), exist_ok=True)
            with open(SEND_TRACE, "a") as f:
                f.write("".join(json.dumps(line) + "\n" for line in lines))
            if os.path.getsize(SEND_TRACE) > SEND_TRACE_LINES * 225:  # About 225 bytes a line: trim at 450 KB.
                with open(SEND_TRACE) as f:
                    keep = f.readlines()[-SEND_TRACE_LINES:]
                with open(SEND_TRACE, "w") as f:
                    f.writelines(keep)
        except OSError as error:
            print(f"the send trace was not written: {error}", file=sys.stderr, flush=True)

    def _input_rects(self):
        """Where the window takes the pointer; everywhere else goes to the windows below. During a turn the working form
        and its label reach down to the card, so hovering never crosses a gap. The captions take it while they
        can open an answer. The resting loop takes it always, so the owner can drag Rook aside; in the game only while
        there is a last answer. The whole window moves with a drag, so its home spot is free while Rook is away. The
        answer panel is a window of its own."""
        scene, rects = self.scene, []

        def origin(widget):
            ok, bounds = widget.compute_bounds(self.win)
            return (bounds.get_x(), bounds.get_y(), bounds.get_width(), bounds.get_height()) if ok else None

        # While the viewer shows, the swarm is at its box, so the home spot takes no input; the viewer's window does.
        working = scene.state in ("thinking", "speaking") and not scene.home and scene.view is None
        loop = scene.home and (bool(self.answer) or not self.in_game) and scene.view is None
        if (working or loop) and (area := origin(self.area)):
            x, y, w, _ = area
            cx_a = self._canvas_cx(w)
            if working:
                rects.append((x + cx_a - ORB / 2, y + scene.lift, ORB, ORB_H))
            else:
                rects.append((x + cx_a - LOOP_HIT[0] / 2, y + scene.rest_pad - LOOP_HIT[1] / 2, *LOOP_HIT))
        if self.card.get_visible() and (card := origin(self.card)):
            fall = CARD_FALL if self._devs_card() else 0  # The room the dust falls through takes no pointer.
            rects.append((card[0], card[1] + fall, card[2], max(0, card[3] - fall)))
        if (scene.captions and scene.caption_box and self.details.strip() and not self.answer_open
                and not self._viewer_drawing() and (captions := origin(self.caption_area))):
            bx, by, bw, bh = scene.caption_box
            rects.append((captions[0] + bx - 12, captions[1] + by - 8, bw + 24, bh + 40))
        return [tuple(int(round(v)) for v in rect) for rect in rects]

    def _update_input_region(self):
        surface = self.win.get_surface()
        if surface is None:
            return
        rects = self._input_rects()
        key = tuple(rects)
        if key == self._region_key:
            return
        self._region_key = key
        surface.set_input_region(cairo.Region([cairo.RectangleInt(*rect) for rect in rects]))

    def _draw_panel(self, _area, cr, w, h):
        """The card under Stop and the permission form: the answer panel's surface, hairline, and corner. The Devs
        permission card draws its own plate and dust frame."""
        if self._devs_draw(_CardFace.draw_panel, cr, w, h, self._card_t(), time.monotonic() - self.card_at):
            return
        _rounded_rect(cr, 0.5, 0.5, w - 1, h - 1, 10)
        cr.set_source_rgba(*TERM_BG, 0.97)
        cr.fill_preserve()
        cr.set_source_rgba(*_mix(AMBER, GARNET, self.scene.err), 0.35)
        cr.set_line_width(1)
        cr.stroke()

    # ---- demo ----
    def _run_demo(self):
        script = [
            (0.0, {"state": "ready"}),
            (5.0, {"state": "listening"}),
            (7.8, {"state": "transcribing"}),
            (9.6, {"state": "thinking"}),
            (10.6, {"activity": "WebSearch"}),
            (11.0, {"caption": "I am checking your monitor settings and the Hyprland notes on scaling.", "seconds": 3.4}),
            (14.5, {"caption": ""}),
            (14.6, {"activity": "Bash"}),
            (17.6, {"state": "speaking",
                    "caption": "Your laptop screen runs at scale 1.6. Scale 1.25 gives you more room on it.",
                    "seconds": 4.5,
                    "details": "Full answer.\n\nYour laptop screen runs at scale 1.6, the largest of your two.\n" * 6}),
            (22.4, {"caption": ""}),
            (22.4, {"state": "result"}),
            (30.0, {"state": "error", "spoken": "Claude Code did not answer. Try again."}),
            (38.0, {"state": "hidden"}),
        ]
        start = time.monotonic()

        def feed():
            elapsed = time.monotonic() - start
            while script and script[0][0] <= elapsed:
                self.handle(script.pop(0)[1])
            if self.scene.state == "listening":
                self.handle({"level": _speech(elapsed)})
            if not script and self.scene.state == "hidden":
                GLib.timeout_add(1200, lambda: setattr(self, "quitting", True))
                return False
            return True

        GLib.timeout_add(33, feed)


def _speech(t):
    """A speech-like microphone level: 1.5 s phrases of syllables with uneven stress, then a pause."""
    phrase, into = divmod(t, 2.6)
    if into > 1.5:
        return 0.002
    syllable, at = divmod(into, 0.19)
    stress = 0.3 + 0.7 * abs(math.sin(phrase * 12.9898 + syllable * 78.233))
    return 0.002 + 0.08 * stress * math.sin(math.pi * at / 0.19) ** 2


def _phrase(t):
    """One phrase that starts at 1 s, for the listening stills."""
    return _speech(t - 1.0) if 1.0 <= t < 2.5 else 0.002


def _simulate(script, until, mic=_speech, lift=FALLBACK_LIFT, game=None, rest_pad=REST_PAD):
    """Run a Scene on a virtual clock at the overlay's frame rate, feeding it a script of messages.
    The last step lands exactly on until. game is the game window's origin in scene coordinates (WoW mode)."""
    scene, t, script = Scene(0.0), 0.0, sorted(script, key=lambda item: item[0])
    scene.lift, scene.game_origin, scene.rest_pad = lift, game, rest_pad
    while t < until:
        while script and script[0][0] <= t:
            scene.handle(script.pop(0)[1], t)
        if scene.state == "listening":
            scene.handle({"level": mic(t)}, t)
        scene.step(t)
        t += TICK_MS / 1000
    scene.step(until)
    return scene, until


def _backdrop(cr, w, h):
    """A mid-tone, textured stand-in for a game scene: forest, pale sky, warm stone. The light theme gets a pale desktop."""
    if PALETTE is THEMES["light"]:
        _backdrop_light(cr, w, h)
        return
    grad = cairo.LinearGradient(0, 0, w, h)
    grad.add_color_stop_rgb(0, 0.20, 0.26, 0.18)
    grad.add_color_stop_rgb(0.4, 0.55, 0.60, 0.64)
    grad.add_color_stop_rgb(0.7, 0.72, 0.70, 0.66)
    grad.add_color_stop_rgb(1, 0.50, 0.40, 0.28)
    cr.rectangle(0, 0, w, h)
    cr.set_source(grad)
    cr.fill()
    rng = random.Random(11)
    for _ in range(260):
        x, y, r = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(8, 70)
        tone = rng.uniform(0.15, 0.95)
        blob = cairo.RadialGradient(x, y, 0, x, y, r)
        blob.add_color_stop_rgba(0, tone * rng.uniform(0.85, 1.1), tone, tone * rng.uniform(0.7, 1.0), 0.32)
        blob.add_color_stop_rgba(1, tone, tone, tone, 0)
        cr.arc(x, y, r, 0, 2 * math.pi)
        cr.set_source(blob)
        cr.fill()


def _backdrop_light(cr, w, h):
    """A pale desktop: near-white, with pale grey windows and a few darker ones, so mixed content can be judged."""
    cr.rectangle(0, 0, w, h)
    cr.set_source_rgb(0.97, 0.97, 0.96)
    cr.fill()
    rng = random.Random(11)
    for _ in range(int(w * h / 40000) + 4):
        x, y, pw, ph = rng.uniform(-100, w), rng.uniform(-60, h), rng.uniform(120, 520), rng.uniform(60, 300)
        tone = rng.choice((0.93, 0.90, 0.86, 0.80, 0.70, 0.45, 0.18)) if rng.random() < 0.8 else 1.0
        _rounded_rect(cr, x, y, pw, ph, 10)
        cr.set_source_rgba(tone, tone, tone * 0.98, 0.85)
        cr.fill()


def _out(path):
    """Files drawn in the light theme get a _light suffix, so both sets sit side by side."""
    root, ext = os.path.splitext(path)
    return root + "_light" + ext if PALETTE is THEMES["light"] else path


def _thinking_on(tool):
    return [(0.0, {"state": "transcribing"}), (0.5, {"state": "thinking"}), (0.6, {"activity": tool})]


# Cells for --render: (label, message script, moment to draw, microphone).
RENDER_STATES = [
    ("transcribing", [(0.0, {"state": "listening"}), (1.0, {"state": "transcribing"})], 2.6, _speech),
    ("thinking", [(0.0, {"state": "transcribing"}), (0.5, {"state": "thinking"})], 3.0, _speech),
    ("speaking", [(0.0, {"state": "thinking"}), (0.5, {"state": "speaking"})], 3.0, _speech),
    ("result", [(0.0, {"state": "speaking"}), (0.5, {"state": "result"})], 3.4, _speech),
    ("permission", [(0.0, {"state": "thinking"}), (0.5, {"state": "permission"})], 3.0, _speech),
    ("error", [(0.0, {"state": "thinking"}), (0.5, {"state": "error"})], 4.0, _speech),
    ("thinking, rook turn", [(0.0, {"state": "transcribing"}), (0.5, {"state": "thinking"})], 0.5 + THINK_TURN + 3.0,
     _speech),
]
LISTEN = [(0.0, {"state": "listening"})]
LISTEN_MOMENTS = [("silence", 0.8), ("onset", 1.1), ("a loud syllable enters", 1.86),
                  ("the phrase mid-way across", 2.6), ("the phrase leaving", 3.8)]
# WoW mode's game tools. find_upgrades shows the sword first, then takes turns with the coins.
RENDER_WOW_ACTIVITIES = ["find_npc", "find_quest", "find_item", "find_upgrades", "find_price", "find_object"]
SENDS = ("t3_thread_send", "t3_thread_launch", "handoff")
RENDER_ROW = 8  # Activity cells per row of the sheet.


def _activity_scenes():
    """(note, scene, time) for every activity form, settled: one tool per desktop form, each send in the cycle, the
    rook, which plain thinking turns to after THINK_TURN seconds on the lattice, then WoW mode's game tools."""
    seen, desktop = set(), []
    for tool, form in ACTIVITY_FORMS.items():
        if form not in seen and tool not in RENDER_WOW_ACTIVITIES and tool not in SENDS:
            seen.add(form)
            desktop.append(tool)
    # Each send takes the next send form, so two sends show both, held once assembled.
    sends = []
    for _ in devs_pack.SEND_FORMS:
        scene, t = _simulate(_thinking_on(SENDS[0]) + [(0.6, {"send": [{"id": "c", "name": "A thread"}]})], 4.0, lift=0)
        sends.append((f"{SENDS[0]}: {scene.form}", scene, t))
    return [(f"{tool}: {ACTIVITY_FORMS[tool]}", *_simulate(_thinking_on(tool), 3.0, lift=0))
            for tool in desktop] + sends + [
        ("thinking: rook", *_simulate(_thinking_on(""), 0.5 + THINK_TURN + 3.0, lift=0))] + [
        (f"{tool}: {ACTIVITY_FORMS[tool]}", *_simulate(_thinking_on(tool), 2.6, lift=0))
        for tool in RENDER_WOW_ACTIVITIES]


TRANSITION = _thinking_on("WebSearch") + [(3.0, {"state": "speaking"})]
REST = [(0.0, {"state": "ready"})]
REST_SETTLED = 12.0
DESCENT = REST + [(8.0, {"state": "listening"})]
RETURN = [(0.0, {"state": "speaking"}), (0.5, {"state": "result"})]
# The owner's 3310 by 1434 game window at the monitor's corner puts the working centre at (1655, 283).
READ_GAME, READ_LIFT, READ_CARD = (-1655.0, -283.0), 172, [11, 196, 1064, 420]
READING = [(0.0, {"state": "ready"}), (1.0, {"state": "listening"}), (2.5, {"reading": READ_CARD})]


def _card_stand_in(cr, x, y, w, h):
    """A dark card with a gold border and faint lines of text, where the game would draw the gear card."""
    cr.rectangle(x, y, w, h)
    cr.set_source_rgba(0.06, 0.05, 0.04, 0.88)
    cr.fill_preserve()
    cr.set_source_rgba(0.85, 0.68, 0.30, 0.9)
    cr.set_line_width(3)
    cr.stroke()
    for row in range(9):
        cr.rectangle(x + 24, y + 30 + row * 42, w * (0.35 + 0.4 * ((row * 7) % 5) / 4), 14)
    cr.set_source_rgba(0.75, 0.75, 0.72, 0.35)
    cr.fill()


_OFFSCREEN_SOFT = False


def render(path, scale=2):
    """Write the contact sheet to path, and the resting loop, the sphere, and the listening orb at 4x
    to orb_large.png beside it."""
    gap = 24
    width = 3 * WIDTH + 4 * gap
    tall = FALLBACK_LIFT + ORB_H
    zoom = 0.4
    reading_h = 520 * zoom
    # The activity forms take RENDER_ROW cells a row: the desktop ones and the rook, then WoW mode's game tools.
    scenes = _activity_scenes()
    split = len(scenes) - len(RENDER_WOW_ACTIVITIES)
    parts = [scenes[k:min(k + RENDER_ROW, split)] for k in range(0, split, RENDER_ROW)]
    parts += [scenes[k:k + RENDER_ROW] for k in range(split, len(scenes), RENDER_ROW)]
    shift = (len(parts) - 1) * (ORB_H + gap)
    height = gap + 5 * (ORB_H + gap) + shift + 2 * (tall + gap) + 2 * (reading_h + gap) + ORB_H + CAPTION_H + gap
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(width * scale), int(height * scale))
    surface.set_device_scale(scale, scale)
    cr = cairo.Context(surface)
    _backdrop(cr, width, height)

    def note(text, x, y):
        _note(cr, text, x, y)

    def row(cells, top, lift=0):
        cell = width / len(cells)
        for i, (name, script, at, mic) in enumerate(cells):
            scene, t = _simulate(script, at, mic, lift)
            cr.save()
            cr.translate(i * cell + (cell - ORB_W) / 2, top)
            cr.rectangle(0, 0, ORB_W, lift + ORB_H)
            cr.clip()
            scene.draw_swarm(cr, ORB_W, t, lift)
            cr.restore()
            note(name, i * cell + 8, top - 18)

    row(RENDER_STATES, gap)
    row([(f"listening: {name}", LISTEN, at, _phrase) for name, at in LISTEN_MOMENTS], gap + ORB_H + gap)
    for r, part in enumerate(parts):
        cell = width / RENDER_ROW
        for i, (name, scene, t) in enumerate(part):
            top = gap + 2 * (ORB_H + gap) + r * (ORB_H + gap)
            cr.save()
            cr.translate(i * cell + (cell - ORB_W) / 2, top)
            cr.rectangle(0, 0, ORB_W, ORB_H)
            cr.clip()
            scene.draw_swarm(cr, ORB_W, t)
            cr.restore()
            note(name, i * cell + 8, top - 18)
    row([(f"globe to sphere +{at:.2f} s", TRANSITION, 3.0 + at, _speech) for at in (0.06, 0.16, 0.3, 0.5, 1.1)],
        gap + 3 * (ORB_H + gap) + shift)
    period = [(f"rest loop {k}/5 of a period", REST, REST_SETTLED + k * LOOP_PERIOD / 5, _speech) for k in range(5)]
    row(period + [("one full period after 0/5", REST, REST_SETTLED + LOOP_PERIOD, _speech)],
        gap + 4 * (ORB_H + gap) + shift)
    row([(f"rest to listening +{at:.2f} s", DESCENT, 8.0 + at, _speech) for at in (0.08, 0.2, 0.35, 0.55, 1.0)],
        gap + 5 * (ORB_H + gap) + shift, FALLBACK_LIFT)
    row([(f"cloud to rest +{at:.2f} s", RETURN, 3.5 + at, _speech) for at in (0.1, 0.3, 0.5, 0.8, 1.5)],
        gap + 5 * (ORB_H + gap) + shift + tall + gap, FALLBACK_LIFT)

    # WoW mode: reading the gear card.
    reading_top = gap + 5 * (ORB_H + gap) + shift + 2 * (tall + gap)
    moments = [("leaving the listening orb", 0.04), ("mid-flight", 0.13), ("arriving", 0.3),
               ("framed, orb at the left", 0.45), ("framed, orb at the right", 1.12), ("returning", 1.32)]
    cell_w = width / 3
    centre = (1700.0, 140.0)
    for i, (name, at) in enumerate(moments):
        scene, t = _simulate(READING, 2.5 + at, lift=READ_LIFT, game=READ_GAME)
        x, y = (i % 3) * cell_w, reading_top + (i // 3) * (reading_h + gap)
        cr.save()
        cr.translate(x, y)
        cr.rectangle(0, 0, cell_w, reading_h)
        cr.clip()
        cr.scale(zoom, zoom)
        rx, ry, rw, rh = scene.read_rect
        _card_stand_in(cr, centre[0] + rx, centre[1] + ry, rw, rh)
        scene.draw_swarm(cr, cell_w / zoom, t, centre=centre, zoom=zoom)
        cr.restore()
        note(f"reading +{at:.2f} s: {name}", x + 8, y - 18)


    text = "Night light now starts at nine. It fades in over twenty minutes, so the screen warms up slowly."
    seconds = len(text) * SECONDS_PER_CHAR
    script = [(0.0, {"state": "speaking", "caption": text, "seconds": seconds}),
              (seconds, {"caption": ""}), (seconds, {"state": "result"})]
    moments = [("first words arriving", 0.55), ("mid-sentence", seconds * 0.62),
               ("fading out", seconds + HOLD + 0.45)]
    for i, (name, at) in enumerate(moments):
        scene, t = _simulate(script, at)
        x, y = gap + i * (WIDTH + gap), gap + 5 * (ORB_H + gap) + shift + 2 * (tall + gap) + 2 * (reading_h + gap)
        cr.save()
        cr.translate(x + (WIDTH - ORB_W) / 2, y)
        scene.draw_swarm(cr, ORB_W, t)
        cr.restore()
        cr.save()
        cr.translate(x, y + ORB_H)
        cr.rectangle(0, 0, WIDTH, CAPTION_H)
        cr.clip()
        scene.draw_caption(cr, WIDTH, t)
        cr.restore()
        note(f"caption: {name}", x + 8, y - 18)
    surface.write_to_png(_out(path))

    large = cairo.ImageSurface(cairo.FORMAT_ARGB32, 3 * ORB_W * 4, ORB_H * 4)
    large.set_device_scale(4, 4)
    cr = cairo.Context(large)
    # The cells crop the backdrop of the sheet as it was before the WoW rows, so this picture stays the same.
    sheet_h = gap + 5 * (ORB_H + gap) + 2 * (tall + gap) + ORB_H + CAPTION_H + gap
    for i, sheet_x in enumerate((1000, 1800, 1400)):
        cr.save()
        cr.rectangle(i * ORB_W, 0, ORB_W, ORB_H)
        cr.clip()
        cr.translate(i * ORB_W - sheet_x, 0)
        _backdrop(cr, width, sheet_h)
        cr.restore()
    for i, (script, at) in enumerate(((REST, REST_SETTLED), (TRANSITION, 5.0))):
        scene, t = _simulate(script, at, lift=0)
        cr.save()
        cr.translate(i * ORB_W, 0)
        cr.rectangle(0, 0, ORB_W, ORB_H)
        cr.clip()
        scene.draw_swarm(cr, ORB_W, t)
        cr.restore()
    scene, t = _simulate(LISTEN, LISTEN_MOMENTS[2][1], _phrase, lift=0)
    cr.save()
    cr.translate(2 * ORB_W, 0)
    cr.rectangle(0, 0, ORB_W, ORB_H)
    cr.clip()
    scene.draw_swarm(cr, ORB_W, t)
    cr.restore()
    large.write_to_png(_out(os.path.join(os.path.dirname(path), "orb_large.png")))
    _render_listen_styles(os.path.dirname(path))
    _render_shapes(os.path.dirname(path))
    _render_details(os.path.dirname(path))
    _render_panel(os.path.dirname(path))
    _render_panel_history(os.path.dirname(path))
    _render_compare(os.path.dirname(path))
    _render_wow_placement(os.path.dirname(path))
    _render_diagram(os.path.dirname(path))


def _render_diagram(folder):
    """Write diagram.png showing a settled constellation (quiet and with a node lit) in both themes."""
    doc = {"title": "Web", "graph": "browser > dns:globe > server* > page:file"}
    w, h, lift = 740, 620, 172
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, w * 2, h * 2)
    cr = cairo.Context(out)
    kept = PALETTE
    for r, theme in enumerate(("dark", "light")):
        _use_theme(theme)
        for c, step in enumerate((0, 1)):
            s = Scene(0.0)
            s.lift = lift
            s.handle({"state": "speaking"}, 0.0)
            s.render_command({"diagram": doc}, 0.0)
            t = 0.0
            while t < 2.2:
                s.step(t)
                t += TICK_MS / 1000
            if step:
                s.render_command({"step": 1}, t)
                while t < 3.4:
                    s.step(t)
                    t += TICK_MS / 1000
            cr.save()
            cr.rectangle(c * w, r * h, w, h)
            cr.clip()
            cr.translate(c * w, r * h)
            if theme == "light":
                _backdrop_light(cr, w, h)
            else:
                cr.set_source_rgb(0.075, 0.075, 0.09)
                cr.paint()
            s.draw_swarm(cr, w, t, lift)
            _note(cr, f"{theme}: {'browser lit' if step else 'quiet'}", 10, 8)
            cr.restore()
    _use_theme("light" if kept is THEMES["light"] else "dark")
    out.write_to_png(os.path.join(folder, "diagram.png"))


def _render_wow_placement(folder):
    """wow_placement.png at 1x: WoW mode's placement on a 2560 by 1440 monitor whose game window (1920 by 1080)
    does not fill it. The real _placement places it from fake Hyprland output. The resting loop lands at 5% and
    the working form at 15% of the game window's height; dashed lines mark the window and the overlay surface."""
    mon = {"id": 0, "name": "DP-9", "focused": True, "x": 0, "y": 0, "width": 2560, "height": 1440, "scale": 1}
    game = {"title": GAME_TITLE, "monitor": 0, "at": [320, 200], "size": [1920, 1080]}

    class Display:
        def get_monitors(self):
            return Gio.ListStore()

    real = globals()["_hypr"]
    globals()["_hypr"] = lambda *args: [mon] if args == ("monitors",) else [game] if args == ("clients",) else None
    try:
        _, left, top, lift, height, rest_pad, origin, _ = _placement(Display(), True)
    finally:
        globals()["_hypr"] = real
    gx, gy, gw, gh = 320, 200, 1920, 1080
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 2560, 1440)
    cr = cairo.Context(surface)
    cr.set_source_rgb(0.16, 0.17, 0.19)
    cr.paint()
    cr.save()
    cr.rectangle(gx, gy, gw, gh)
    cr.clip()
    cr.translate(gx, gy)
    kept = PALETTE
    _use_theme("dark")
    _backdrop(cr, gw, gh)
    cr.restore()
    area_x = left + (WIDTH - ORB_W) / 2
    for script, at in ((REST, REST_SETTLED), ([(0.0, {"state": "transcribing"}), (0.5, {"state": "thinking"})], 3.0)):
        scene, t = _simulate(script, at, lift=lift, rest_pad=rest_pad)
        cr.save()
        cr.translate(area_x, top)
        cr.rectangle(0, 0, ORB_W, lift + ORB_H)
        cr.clip()
        scene.draw_swarm(cr, ORB_W, t, lift)
        cr.restore()
    cr.set_line_width(2)
    cr.set_dash([10, 8])
    for y, text in ((gy + gh * REST_SHARE, "5% of the game window: the resting loop's centre"),
                    (gy + gh * TOP_SHARE, "15% of the game window: the working forms' top grains")):
        cr.move_to(gx, y)
        cr.line_to(gx + gw, y)
        cr.set_source_rgba(1, 0.85, 0.4, 0.8)
        cr.stroke()
        _note(cr, text, gx + 12, y + 4)
    cr.rectangle(left, top, WIDTH, lift + ORB_H)
    cr.set_source_rgba(0.5, 0.8, 1, 0.8)
    cr.stroke()
    _note(cr, f"overlay surface: left {left}, top {top}, rest pad {rest_pad}, lift {lift}", left + 8, top + lift + ORB_H + 6)
    cr.rectangle(gx, gy, gw, gh)
    cr.set_source_rgba(1, 1, 1, 0.6)
    cr.stroke()
    _note(cr, f"game window {gw} x {gh} at ({gx}, {gy}) on a 2560 x 1440 monitor; game origin {origin}", gx + 12, gy + gh + 8)
    _use_theme("light" if kept is THEMES["light"] else "dark")
    surface.write_to_png(_out(os.path.join(folder, "wow_placement.png")))


def _render_compare(folder):
    """theme_compare.png at 2x: the dark theme on the dark backdrop, then the light theme on the light one.
    Each row: the resting loop, listening, thinking, speaking with a caption, the prompt shape, and the resting
    loop over pure white and over pure black."""
    text = "Night light now starts at nine. It fades in over twenty minutes, so the screen warms up slowly."
    seconds = len(text) * SECONDS_PER_CHAR
    cells = [("resting loop", REST, REST_SETTLED, _speech, None), ("listening", LISTEN, LISTEN_MOMENTS[2][1], _phrase, None),
             ("thinking", [(0.0, {"state": "transcribing"}), (0.5, {"state": "thinking"})], 3.0, _speech, None),
             ("speaking, mid-sentence", [(0.0, {"state": "speaking", "caption": text, "seconds": seconds})],
              seconds * 0.62, _speech, None),
             ("Bash: prompt", _thinking_on("Bash"), 3.0, _speech, None),
             ("resting loop on white", REST, REST_SETTLED, _speech, (1, 1, 1)),
             ("resting loop on black", REST, REST_SETTLED, _speech, (0, 0, 0))]
    gap, head, cell_h = 16, 26, ORB_H + CAPTION_H
    widths = [WIDTH if name.startswith("speaking") else ORB_W for name, *_ in cells]
    width, height = sum(widths) + gap * (len(cells) + 1), 2 * (head + cell_h + gap)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width * 2, height * 2)
    surface.set_device_scale(2, 2)
    cr = cairo.Context(surface)
    kept = PALETTE
    for r, theme in enumerate(("dark", "light")):
        _use_theme(theme)
        top = r * (head + cell_h + gap)
        cr.save()
        cr.rectangle(0, top, width, head + cell_h + gap)
        cr.clip()
        cr.translate(0, top)
        _backdrop(cr, width, head + cell_h + gap)
        cr.restore()
        x = gap
        for (name, script, at, mic, patch), w in zip(cells, widths):
            scene, t = _simulate(script, at, mic, lift=0)
            y = top + head
            cr.save()
            cr.rectangle(x, y, w, cell_h)
            cr.clip()
            if patch:
                cr.set_source_rgb(*patch)
                cr.paint()
            cr.translate(x + (w - ORB_W) / 2, y)
            scene.draw_swarm(cr, ORB_W, t)
            cr.restore()
            if w == WIDTH:
                cr.save()
                cr.translate(x, y + ORB_H)
                scene.draw_caption(cr, WIDTH, t)
                cr.restore()
            _note(cr, f"{theme}: {name}", x + 4, top + 5)
            x += w + gap
    _use_theme("light" if kept is THEMES["light"] else "dark")
    surface.write_to_png(os.path.join(folder, "theme_compare.png"))


def _render_shapes(folder):
    """shapes_large.png: every activity form with its label at 4x, so the grain detail can be judged."""
    scenes = _activity_scenes()
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, len(scenes) * ORB_W * 4, ORB_H * 4)
    surface.set_device_scale(4, 4)
    cr = cairo.Context(surface)
    _backdrop(cr, len(scenes) * ORB_W, ORB_H)
    for i, (name, scene, t) in enumerate(scenes):
        cr.save()
        cr.translate(i * ORB_W, 0)
        cr.rectangle(0, 0, ORB_W, ORB_H)
        cr.clip()
        scene.draw_swarm(cr, ORB_W, t)
        cr.restore()
        _note(cr, name, i * ORB_W + 8, 6)
    surface.write_to_png(_out(os.path.join(folder, "shapes_large.png")))


def _listen_mic(t):
    """For the listening stills: a quiet floor, a phrase that sets the range, silence, quiet speech,
    then one loud syllable whose crest is at 5.395 s."""
    if 1.5 <= t < 2.7:
        return _speech(t - 1.5)
    if 4.0 <= t < 5.0:
        syllable, at = divmod(t - 4.0, 0.19)
        return 0.002 + 0.008 * (0.6 + 0.4 * abs(math.sin(syllable * 7.3))) * math.sin(math.pi * at / 0.19) ** 2
    if 5.3 <= t < 5.49:
        return 0.002 + 0.087 * math.sin(math.pi * (t - 5.3) / 0.19) ** 2
    return 0.002


LISTEN_CELLS = [("silence", 3.9), ("quiet speech", 4.68), ("loud syllable", 5.42), ("0.5 s after it", 5.92)]


def _render_listen_styles(folder):
    """listen_styles.png: every --listen style in four moments, at 2x. listen_large.png: the loud syllable of
    each waveform style at 4x."""
    chosen = FORM_FOR_STATE["listening"]
    label_w, gap = 70, 24
    width, height = label_w + 4 * ORB_W, gap + len(LISTEN_STYLES) * (ORB_H + gap)
    for scale, styles, cells, out in ((2, list(LISTEN_STYLES), LISTEN_CELLS, "listen_styles.png"),
                                      (4, [s for s in LISTEN_STYLES if s != "orb"], LISTEN_CELLS[2:3],
                                       "listen_large.png")):
        large = scale == 4
        w, h = (len(styles) * ORB_W, ORB_H) if large else (width, height)
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w * scale, h * scale)
        surface.set_device_scale(scale, scale)
        cr = cairo.Context(surface)
        _backdrop(cr, w, h)
        for r, style in enumerate(styles):
            FORM_FOR_STATE["listening"] = LISTEN_STYLES[style]
            for c, (moment, at) in enumerate(cells):
                scene, t = _simulate(LISTEN, at, _listen_mic, lift=0)
                x, y = (r * ORB_W, 0) if large else (label_w + c * ORB_W, gap + r * (ORB_H + gap))
                cr.save()
                cr.translate(x, y)
                cr.rectangle(0, 0, ORB_W, ORB_H)
                cr.clip()
                scene.draw_swarm(cr, ORB_W, t)
                cr.restore()
                if large:
                    _note(cr, f"{style}: {moment}", x + 8, 6)
                else:
                    if r == 0:
                        _note(cr, moment, x + 8, 4)
                    if c == 0:
                        _note(cr, style, 10, y + ORB_H / 2 - 8)
        surface.write_to_png(_out(os.path.join(folder, out)))
    FORM_FOR_STATE["listening"] = chosen


SAMPLE_ANSWER = """Your laptop screen looks large because **Hyprland scales it to 1.6**, while the wide monitor runs at 1. Scale 1.25 gives you more room on the laptop, and Hyprland applies the change as soon as you save the file.

**Why this one:** at 1.25 the 3200 by 2000 panel acts like a 2560 by 1600 screen. Text stays a comfortable size, and two windows fit side by side.

## How to change it
1. Open **monitors.conf** in the Hyprland folder of your config, at `~/.config/hypr/monitors.conf`.
2. Find the line for `eDP-1` and change its last number from 1.6 to 1.25.
   - Leave the `DP-1` line as it is.
   - Keep a copy of the old line, so you can switch back quickly.
3. Save the file. You do not need to log out.

## If something looks wrong
- *Older apps* can look blurry at a fractional scale; restart them once after the change.
- **Firefox** keeps its own zoom, so reset it with Ctrl+0.
- Try 2 if you prefer large text & do not need the extra room.

### Common scales for this panel
| Scale | Acts like | Feels |
|---|---|---|
| 2 | 1600 x 1000 | Large |
| 1.6 | 2000 x 1250 | Current |
| 1.25 | 2560 x 1600 | Roomy |

---

Check the result with `hyprctl monitors` after you save: the scale line should read 1.25. Any scale < 1 makes text tiny, so avoid it.

Sources:
- [Monitors - Hyprland Wiki](https://wiki.hypr.land/Configuring/Monitors/)
- [The Omarchy manual](https://learn.omacom.io/2/the-omarchy-manual)
- [Hyprland variables](https://wiki.hypr.land/Configuring/Variables/)"""


def _paint_window(cr, scene, t, lift):
    """One frame of the overlay window as the live layout places it: the swarm area at the top, the captions
    under it."""
    cr.save()
    cr.translate((WIDTH - ORB_W) / 2, 0)
    scene.draw_swarm(cr, ORB_W, t, lift)
    cr.restore()
    cr.save()
    cr.translate(0, lift + ORB_H)
    scene.draw_caption(cr, WIDTH, t)
    cr.restore()


def _render_details(folder):
    """details.png at 2x: the caption's hover hint (READ MORE) and the resting loop's LAST ANSWER hint, which open the
    last-answer panel (see panel_terminal.png). Everything is drawn by the same functions the live overlay uses."""
    gap, lift = 24, FALLBACK_LIFT
    width, height = 2 * WIDTH + 3 * gap, gap + lift + ORB_H + CAPTION_H + gap
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width * 2, int(height * 2))
    surface.set_device_scale(2, 2)
    cr = cairo.Context(surface)
    _backdrop(cr, width, height)
    spoken = SAMPLE_ANSWER.split("\n\n")[0].replace("**", "")
    speaking = [(0.0, {"state": "speaking", "caption": spoken, "seconds": len(spoken) * SECONDS_PER_CHAR})]
    hinted, t_hint = _simulate(speaking, 2.4)
    hinted.caption_hint, hinted.caption_hint_mix = True, 1.0
    cr.save()
    cr.translate(gap, gap)
    _paint_window(cr, hinted, t_hint, lift)
    cr.restore()
    _note(cr, "pointer over the spoken words", gap + 8, gap - 18)
    loop, t_loop = _simulate(REST, REST_SETTLED)
    loop.rest_hint = True
    for _ in range(45):
        t_loop += TICK_MS / 1000
        loop.step(t_loop)
    cr.save()
    cr.translate(2 * gap + WIDTH, gap)
    _paint_window(cr, loop, t_loop, lift)
    cr.restore()
    _note(cr, "pointer over the resting loop, with a last answer", 2 * gap + WIDTH + 8, gap - 18)
    surface.write_to_png(_out(os.path.join(folder, "details.png")))


PANEL_SAMPLE = """To sign in to GitHub on this machine, run the login command, open the link it prints, and paste the one-time code. Then check that the token works.

## Steps
1. Run the login command in any terminal:
   - It prints a code and a link.
   - The browser step needs your GitHub account.
2. Open the link and paste the code.
3. Run the check below; it should name your account.

```bash
gh auth login -h github.com --git-protocol https --web
```

```bash
$ gh auth status
$ gh api user --jq .login
```

### What each part does
| Flag | Meaning |
|---|---|
| `-h github.com` | The host to sign in to |
| `--git-protocol https` | Git talks HTTPS, not SSH |
| `--web` | Sign in through the browser |

---

If the browser step fails, run `gh auth logout` first, then sign in again. The token lives in your keyring, not in a file.

## If it still fails
- **The code expired.** Codes last about fifteen minutes; run the login command again for a fresh one.
- **The wrong account signed in.** Sign out, then sign in again with the right browser profile open.
- **Git still asks for a password.** Tell Git to use the GitHub CLI for HTTPS:

```bash
gh auth setup-git
git config --global --get-regexp '^credential'
git ls-remote https://github.com/example/rook.git HEAD
```

- **Behind a proxy.** Export it before you sign in:

```bash
export HTTPS_PROXY=http://proxy.example:3128
gh auth login -h github.com --web
```

### Where things live
| Item | Place |
|---|---|
| Token | the keyring, through `gh auth token` |
| Settings | `~/.config/gh/hosts.yml` |
| Git helper | `~/.gitconfig`, under `credential` |

Once `gh auth status` names your account, the sign-in is done and Rook can open pull requests for you."""
PANEL_SHORT = """The token works: you are signed in as **alice**, over HTTPS.

```bash
gh auth status
```"""


def _render_panel(folder):
    """panel_terminal.png at 1x: the render's stand-in for the last-answer panel (the live panel is a GTK text view,
    which cannot be drawn offscreen), with the live panel's fonts, colours, and layout numbers. Rows: the 5120 x 1440
    monitor and the 3200 x 2000 one at scale 1.6 (2000 x 1226 logical below its bar), each over the dark and the
    light backdrop. Columns: a short answer, a long one at the top, and the long one scrolled to its end."""
    monitors = [("5120 x 1440", (0, 0, 5120, 1440), 196), ("3200 x 2000 at 1.6", (0, 0, 2000, 1226), 167)]
    gap, head = 24, 22
    probe = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 4, 4))
    cells, row_h = [], []
    for name, bounds, lift in monitors:
        w, cap = _panel_rect(bounds, 0, 0)[2], _panel_rect(bounds, 0, 0)[4]
        row = []
        for label, text, scrolled in (("short answer", PANEL_SHORT, False), ("long answer, top", PANEL_SAMPLE, False),
                                      ("long answer, scrolled to the end", PANEL_SAMPLE, True)):
            page = Page(text)
            page.lay_out(PangoCairo.create_context(probe), w - 2)
            content = min(page.height, cap - TERM_HEAD_H - 2)
            h = int(TERM_HEAD_H + 2 + content)
            row.append((label, page, w, h, page.height - content if scrolled else 0.0))
        cells.append((name, bounds, cap, row))
        row_h.append(max(c[3] for c in row))
    width = gap + sum(c[2] + gap for c in cells[0][3])
    height = sum(2 * (h + head + gap) for h in row_h) + gap
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, int(height))
    cr = cairo.Context(surface)
    kept = PALETTE
    y = gap
    for (name, bounds, cap, row), rh in zip(cells, row_h):
        for theme in ("dark", "light"):
            _use_theme(theme)
            cr.save()
            cr.rectangle(0, y - gap, width, rh + head + gap)
            cr.clip()
            cr.translate(0, y - gap)
            _backdrop(cr, width, rh + head + gap)
            cr.restore()
            x = gap
            for label, page, w, h, scroll in row:
                cr.save()
                cr.translate(x, y + head)
                _paint_answer_panel(cr, w, h, page, scroll, (10, 10))
                cr.restore()
                _note(cr, f"{name}, {theme} theme: {label} ({w} x {h}, height cap {cap})", x + 4, y + 2)
                x += w + gap
            y += rh + head + gap
    _use_theme("light" if kept is THEMES["light"] else "dark")
    surface.write_to_png(os.path.join(folder, "panel_terminal.png"))


PANEL_LINKS = """I found nine guides for the new season. Each link opens in your browser.

1. [Season overview and dates](https://example.com/season/overview)
2. [Tier set bonuses for every class](https://example.com/season/tier-sets)
3. [Mythic+ dungeon routes](https://example.com/mythic-plus/routes)
4. [Crafting orders, *explained*](https://example.com/crafting/orders)
5. [Raid boss guides, normal to mythic](https://example.com/raid/bosses)
6. [Gearing path for alts](https://example.com/gearing/alts)
7. [Delves and their rewards](https://example.com/delves)
8. [Profession knowledge points](https://example.com/professions/knowledge)
9. [Patch notes in full](https://example.com/patch-notes)

The full schedule is at https://www.example.com/season/schedule, and `example.com` in code stays plain text."""


def _render_panel_history(folder):
    """panel_history.png at 1x: the panel's header with its history arrows, over the dark and the light backdrop.
    Left: the newest answer, a list of links, so the forward arrow is dim. Right: the oldest kept answer, so the back
    arrow is dim. Links show in gold and underlined; a click on one opens it in the browser."""
    gap, head = 24, 22
    probe = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 4, 4))
    w, cap = _panel_rect((0, 0, 2560, 1440), 0, 0)[2], _panel_rect((0, 0, 2560, 1440), 0, 0)[4]
    cells = []
    for label, text, history in (("newest of ten, a list of links", PANEL_LINKS, (10, 10)),
                                 ("oldest of ten", PANEL_SHORT, (1, 10))):
        page = Page(text)
        page.lay_out(PangoCairo.create_context(probe), w - 2)
        cells.append((label, page, int(TERM_HEAD_H + 2 + min(page.height, cap - TERM_HEAD_H - 2)), history))
    rh = max(c[2] for c in cells)
    width, height = gap + len(cells) * (w + gap), 2 * (rh + head + gap) + gap
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    kept = PALETTE
    y = gap
    for theme in ("dark", "light"):
        _use_theme(theme)
        cr.save()
        cr.rectangle(0, y - gap, width, rh + head + gap)
        cr.clip()
        cr.translate(0, y - gap)
        _backdrop(cr, width, rh + head + gap)
        cr.restore()
        x = gap
        for label, page, h, history in cells:
            cr.save()
            cr.translate(x, y + head)
            _paint_answer_panel(cr, w, h, page, 0.0, history)
            cr.restore()
            _note(cr, f"{theme} theme: {label} ({history[0]} / {history[1]})", x + 4, y + 2)
            x += w + gap
        y += rh + head + gap
    _use_theme("light" if kept is THEMES["light"] else "dark")
    surface.write_to_png(os.path.join(folder, "panel_history.png"))


def _note(cr, text, x, y):
    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(_font("Noto Sans", 11))
    layout.set_text(_safe_utf8(text), -1)
    fg, shadow = PALETTE["note"]
    cr.move_to(x + 1, y + 1)
    cr.set_source_rgba(*shadow, 0.6)
    PangoCairo.show_layout(cr, layout)
    cr.move_to(x, y)
    cr.set_source_rgba(*fg, 0.85)
    PangoCairo.show_layout(cr, layout)


def _check_placement():
    """Characterisation check of Hyprland placement, focus following, and start-order behaviour.

    Runs against stand-in Hyprland sockets (.socket.sock and .socket2.sock) and a fake hyprctl binary
    in scratch folders. Opens no window and never touches the real compositor.
    """
    import tempfile

    class _FakeMon:
        def __init__(self, name):
            self._name = name

        def get_connector(self):
            return self._name

    class _FakeMonList:
        def __init__(self, names):
            self._items = [_FakeMon(n) for n in names]
            self.connected = []

        def get_n_items(self):
            return len(self._items)

        def get_item(self, i):
            return self._items[i]

        def connect(self, sig, fn):
            self.connected.append((sig, fn))
            return len(self.connected)

    class _FakeDisplay:
        def __init__(self, names):
            self._list = _FakeMonList(names)

        def get_monitors(self):
            return self._list

    saved_env = {k: os.environ.get(k) for k in ("PATH", "XDG_RUNTIME_DIR", "HYPRLAND_INSTANCE_SIGNATURE")}
    with tempfile.TemporaryDirectory(dir="/tmp", prefix="rko-") as folder:
        base = Path(folder) if "Path" in globals() else __import__("pathlib").Path(folder)
        rt_dir = base / "run"
        rt_dir.mkdir(mode=0o700)
        bin_dir = base / "bin"
        bin_dir.mkdir()
        state_file = base / "hypr.json"
        hypr_state = {"monitors": [], "clients": [], "activewindow": {}, "layers": {}}

        def write_state():
            state_file.write_text(json.dumps(hypr_state))

        write_state()
        fake_hyprctl = bin_dir / "hyprctl"
        fake_hyprctl.write_text(
            f"#!{sys.executable}\n"
            "import json, pathlib, sys\n"
            f"data = json.loads(pathlib.Path({str(state_file)!r}).read_text())\n"
            "cmd = sys.argv[1] if len(sys.argv) > 1 else ''\n"
            "if data.get('_fail'): raise SystemExit(1)\n"
            "print(json.dumps(data.get(cmd, {})))\n"
        )
        fake_hyprctl.chmod(0o755)
        os.environ["PATH"] = str(bin_dir)
        os.environ["XDG_RUNTIME_DIR"] = str(rt_dir)
        os.environ["HYPRLAND_INSTANCE_SIGNATURE"] = "ovl"

        try:
            # 1. One monitor (1920x1080 @ 1.0x): pinned with literal geometry numbers so constant drift fails.
            m1 = {"id": 0, "name": "DP-1", "x": 0, "y": 0, "width": 1920, "height": 1080,
                  "scale": 1.0, "focused": True, "reserved": [0, 0, 0, 0]}
            hypr_state["monitors"] = [m1]
            write_state()
            got = _placement(_FakeDisplay(["DP-1"]))
            assert got[0].get_connector() == "DP-1" and got[1:] == (
                590, 0, 142, 1080.0, 54, None, (0.0, 0.0, 1920.0, 1080.0)
            ), f"one monitor: {got}"

            # 2. Two monitors with focus on each.
            m_a = {"id": 0, "name": "eDP-1", "x": 0, "y": 0, "width": 1920, "height": 1200,
                   "scale": 1.0, "focused": True, "reserved": [0, 0, 0, 0]}
            m_b = {"id": 1, "name": "DP-2", "x": 1920, "y": 0, "width": 3840, "height": 2160,
                   "scale": 2.0, "focused": False, "reserved": [0, 0, 0, 0]}
            hypr_state["monitors"] = [m_a, m_b]
            write_state()
            disp2 = _FakeDisplay(["eDP-1", "DP-2"])
            got_a = _placement(disp2)
            assert got_a[0].get_connector() == "eDP-1" and got_a[1:] == (
                590, 0, 160, 1200.0, 60, None, (0.0, 0.0, 1920.0, 1200.0)
            ), f"two monitors (A): {got_a}"
            m_a["focused"], m_b["focused"] = False, True
            write_state()
            got_b = _placement(disp2)
            assert got_b[0].get_connector() == "DP-2" and got_b[1:] == (
                590, 0, 142, 1080.0, 54, None, (0.0, 0.0, 1920.0, 1080.0)
            ), f"two monitors (B): {got_b}"

            # 3. Monitor added and removed (including missing GDK connector and no focused monitor fallback).
            m_c = {"id": 2, "name": "HDMI-A-1", "x": 3840, "y": 0, "width": 2560, "height": 1440,
                   "scale": 1.0, "focused": True, "reserved": [0, 0, 0, 0]}
            m_b["focused"] = False
            hypr_state["monitors"] = [m_a, m_b, m_c]
            write_state()
            got_add = _placement(_FakeDisplay(["eDP-1", "DP-2", "HDMI-A-1"]))
            assert got_add[0].get_connector() == "HDMI-A-1" and got_add[1:] == (
                910, 0, 196, 1440.0, 72, None, (0.0, 0.0, 2560.0, 1440.0)
            ), f"monitor added: {got_add}"
            # Focused monitor not yet in GDK list -> gdk_mon is None, geometry still from Hyprland.
            got_no_gdk = _placement(_FakeDisplay(["eDP-1", "DP-2"]))
            assert got_no_gdk[0] is None and got_no_gdk[1:] == (
                910, 0, 196, 1440.0, 72, None, (0.0, 0.0, 2560.0, 1440.0)
            ), f"monitor missing from GDK: {got_no_gdk}"
            # Monitor removed -> falls back to remaining focused monitor.
            m_a["focused"] = True
            hypr_state["monitors"] = [m_a]
            write_state()
            got_rem = _placement(_FakeDisplay(["eDP-1"]))
            assert got_rem[0].get_connector() == "eDP-1" and got_rem[1:] == (
                590, 0, 160, 1200.0, 60, None, (0.0, 0.0, 1920.0, 1200.0)
            ), f"monitor removed: {got_rem}"
            # Empty monitors list -> literal fallback tuple.
            hypr_state["monitors"] = []
            write_state()
            fallback = (None, None, 0, 196, None, 120, None, None)
            assert _placement(_FakeDisplay([])) == fallback, "no monitors fallback"

            # Platform seam pin (has_hyprland/has_overlay False via desk._Mac): overlay.py does not
            # consult desk.has_hyprland() yet, so with no compositor available (hyprctl failing/absent)
            # _placement() returns the fallback tuple above.
            import desk as _ov_desk
            saved_platform = _ov_desk.PLATFORM
            _ov_desk.PLATFORM = _ov_desk._Mac()
            try:
                assert not _ov_desk.PLATFORM.supports_hyprland and not _ov_desk.PLATFORM.supports_overlay
                assert not any(_ov_desk.desktop_capabilities().values())
                hypr_state["_fail"] = True
                write_state()
                assert _placement(_FakeDisplay(["DP-1"])) == fallback, "no-hyprland placement fallback"
                hypr_state["_fail"] = False
                write_state()
            finally:
                _ov_desk.PLATFORM = saved_platform

            # 4. Fractional scale (1.6): 2560x1600 / 1.6 = 1600x1000 logical.
            m_frac = {"id": 0, "name": "eDP-1", "x": 0, "y": 0, "width": 2560, "height": 1600,
                      "scale": 1.6, "focused": True, "reserved": [0, 0, 0, 0]}
            hypr_state["monitors"] = [m_frac]
            write_state()
            got_f = _placement(_FakeDisplay(["eDP-1"]))
            assert got_f[0].get_connector() == "eDP-1" and got_f[1:] == (
                430, 0, 130, 1000.0, 50, None, (0.0, 0.0, 1600.0, 1000.0)
            ), f"fractional 1.6: {got_f}"

            # 5. Bar / reserved area (and in-game window inside monitor with top bar).
            # KNOWN FAULT (pinned, not fixed): _placement() trims bounds by reserved [left, top, right, bottom]
            # but does not adjust left or top, so the presence sits offset by a bar's size.
            m_bar = {"id": 0, "name": "DP-1", "x": 0, "y": 0, "width": 1920, "height": 1080,
                     "scale": 1.0, "focused": True, "reserved": [40, 32, 10, 24]}
            hypr_state["monitors"] = [m_bar]
            write_state()
            got_bar = _placement(_FakeDisplay(["DP-1"]))
            assert got_bar[0].get_connector() == "DP-1" and got_bar[1:] == (
                590, 0, 142, 1080.0, 54, None, (0.0, 0.0, 1870.0, 1024.0)
            ), f"reserved bar placement: {got_bar}"
            m_game_mon = {"id": 1, "name": "DP-2", "x": 0, "y": 0, "width": 2560, "height": 1440,
                          "scale": 1.0, "focused": True, "reserved": [0, 32, 0, 0]}
            wow_client = {"title": GAME_TITLE, "monitor": 1, "at": [100, 80], "size": [1600, 900]}
            hypr_state["monitors"] = [m_game_mon]
            hypr_state["clients"] = [wow_client]
            write_state()
            got_game = _placement(_FakeDisplay(["DP-2"]), game=True)
            assert got_game[0].get_connector() == "DP-2" and got_game[1:] == (
                530, 0, 195, 900.0, 125, (100.0, 80.0, 1.0), (100.0, 48.0, 1600.0, 900.0)
            ), f"game window placement: {got_game}"

            # 6 & 7. Follow-the-focused-monitor rule + start-order behaviour (before vs after late sockets).
            # Uses a stubbed Overlay instance and fake GLib/LayerShell hooks: opens no window.
            timers, sec_timers, fd_watches, layer_calls, removed_timers = [], [], [], [], []
            next_tid = [100]

            def fake_timeout_add(ms, fn, *args):
                tid = next_tid[0]
                next_tid[0] += 1
                timers.append([tid, ms, fn, args, True])
                return tid

            def fake_timeout_add_seconds(secs, fn, *args):
                tid = next_tid[0]
                next_tid[0] += 1
                sec_timers.append([tid, secs, fn, args, True])
                return tid

            def fake_source_remove(tid):
                removed_timers.append(tid)
                for entry in timers:
                    if entry[0] == tid:
                        entry[4] = False
                return True

            def fake_unix_fd_add_full(_prio, fd, _cond, fn):
                fd_watches.append((fd, fn))
                return 999

            def make_stub_overlay(display_names):
                ov = Overlay.__new__(Overlay)
                disp = _FakeDisplay(display_names)
                sc = Scene(0.0)
                ov.scene = sc
                ov.demo = False
                ov.theme = "dark"
                ov.wow = False
                ov.game_focused = False
                ov.in_game = False
                ov.monitor = None
                ov.left = ov.top = None
                ov.home_xy = None
                ov.bounds = None
                ov.carry = ov.flight = None
                ov.return_at = None
                ov.answer_open = False
                ov.opacity = 1.0
                ov._mapped_at = 0.0
                ov._replace_pending = None
                ov._focus_sock = None
                ov._focus_buffer = b""
                ov._focus_name = None
                ov._focus_why = ""
                ov._focus_move = None
                ov._region_key = None
                ov._surface = object()
                ov.quitting = False
                ov.dark = False
                ov._held = lambda: False
                ov._away = lambda: False
                ov._should_show = lambda _now: True
                ov._set_theme = lambda _name: None
                ov._theme_now = lambda: "dark"
                ov._stage_context = lambda: None
                ov._apply_state = lambda: None
                ov._close_answer = lambda: None
                ov._build_window = lambda: None
                ov._build_answer = lambda: None
                ov._build_reader = lambda: None
                ov._build_viewer = lambda: None
                ov._watch_theme = lambda: None
                ov.hold = lambda: None
                vis = [True]
                ov.win = types.SimpleNamespace(
                    get_display=lambda: disp,
                    get_mapped=lambda: True,
                    get_visible=lambda: vis[0],
                    set_visible=lambda v: vis.__setitem__(0, v),
                    set_opacity=lambda v: None,
                )
                ov.area = types.SimpleNamespace(set_content_height=lambda h: None)
                return ov

            saved_glib = (GLib.timeout_add, GLib.timeout_add_seconds, GLib.source_remove, GLib.unix_fd_add_full)
            saved_ls = (LayerShell.set_monitor, LayerShell.set_anchor, LayerShell.set_margin)
            saved_gtk_settings = Gtk.Settings.get_default
            GLib.timeout_add = fake_timeout_add
            GLib.timeout_add_seconds = fake_timeout_add_seconds
            GLib.source_remove = fake_source_remove
            GLib.unix_fd_add_full = fake_unix_fd_add_full
            LayerShell.set_monitor = lambda w, m: layer_calls.append(("monitor", m.get_connector()))
            LayerShell.set_anchor = lambda w, e, v: layer_calls.append(("anchor", int(e), v))
            LayerShell.set_margin = lambda w, e, v: layer_calls.append(("margin", int(e), v))
            Gtk.Settings.get_default = staticmethod(lambda: types.SimpleNamespace(
                props=types.SimpleNamespace(gtk_interface_color_scheme=None)
            ))
            try:
                # Start order A: overlay activates BEFORE Hyprland sockets exist (and hyprctl fails).
                # Running do_activate() with window builders stubbed pins that the 10 s _check_screen
                # and 1 s _check_focus timers and items-changed signal are actually scheduled.
                hypr_state["_fail"] = True
                write_state()
                ov_late = make_stub_overlay(["DP-1", "DP-2"])
                timers.clear()
                sec_timers.clear()
                ov_late.do_activate()
                assert ov_late.monitor is None and ov_late.left is None, "start before compositor: monitor must be None"
                assert ov_late._focus_sock is None, "start before socket2: no focus socket"
                assert any(ms == 1000 and fn == ov_late._poll_focus for _, ms, fn, _, _ in timers), (
                    f"start before socket2: expected 1000ms _poll_focus fallback, got {timers}"
                )
                check_screen_entry = next(
                    (e for e in sec_timers if e[1] == 10 and e[2] == ov_late._check_screen), None
                )
                assert check_screen_entry is not None, (
                    f"do_activate must schedule 10s _check_screen timer, got {sec_timers}"
                )
                assert any(secs == 1 and fn == ov_late._check_focus for _, secs, fn, _, _ in sec_timers), (
                    f"do_activate must schedule 1s _check_focus timer, got {sec_timers}"
                )
                assert ("items-changed", ov_late._monitors_changed) in ov_late.win.get_display().get_monitors().connected

                # Now bring up stand-in .socket.sock and .socket2.sock LATE.
                hypr_state["_fail"] = False
                m_d1 = {"id": 0, "name": "DP-1", "x": 0, "y": 0, "width": 1920, "height": 1080,
                        "scale": 1.0, "focused": True, "reserved": [0, 0, 0, 0]}
                m_d2 = {"id": 1, "name": "DP-2", "x": 1920, "y": 0, "width": 2560, "height": 1440,
                        "scale": 1.0, "focused": False, "reserved": [0, 0, 0, 0]}
                hypr_state["monitors"] = [m_d1, m_d2]
                hypr_state["layers"] = {"DP-1": {"levels": {"3": []}}}
                write_state()

                hypr_dir = rt_dir / "hypr" / "ovl"
                hypr_dir.mkdir(parents=True)
                stop_socks = threading.Event()
                cmd_srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                cmd_srv.bind(str(hypr_dir / ".socket.sock"))
                cmd_srv.listen(8)
                cmd_srv.settimeout(0.05)
                evals = []  # The Lua requests Rook sends (see _no_layer_anim), answered as Hyprland 0.56 does.

                def _serve_cmd():
                    while not stop_socks.is_set():
                        try:
                            conn, _ = cmd_srv.accept()
                        except TimeoutError:
                            continue
                        except OSError:
                            break
                        with conn:
                            req = conn.recv(4096).decode(errors="replace").strip()
                            if req.startswith("/eval "):
                                evals.append(req)
                                conn.sendall(b"ok")
                                continue
                            cmd = req.removeprefix("j/")
                            conn.sendall(json.dumps(hypr_state.get(cmd, {})).encode())

                ev_srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                ev_srv.bind(str(hypr_dir / ".socket2.sock"))
                ev_srv.listen(4)
                ev_srv.settimeout(0.05)
                ev_clients = []

                def _serve_ev():
                    while not stop_socks.is_set():
                        try:
                            conn, _ = ev_srv.accept()
                        except TimeoutError:
                            continue
                        except OSError:
                            break
                        ev_clients.append(conn)

                t_cmd = threading.Thread(target=_serve_cmd, daemon=True)
                t_ev = threading.Thread(target=_serve_ev, daemon=True)
                t_cmd.start()
                t_ev.start()
                try:
                    # Late socket now responds to _hypr_socket.
                    assert isinstance(_hypr_socket("j/monitors"), list), "late socket must answer j/monitors"
                    # The no-animation rule: one Lua request, for Rook's namespace only.
                    assert _no_layer_anim("check") is True and evals == [NO_ANIM_RULE], evals
                    assert 'namespace = "^rook-overlay$"' in NO_ANIM_RULE and "no_anim = true" in NO_ANIM_RULE
                    # Characterisation quirk pin: _check_focus requires self.monitor is not None, so after a
                    # compositor-less start it does NOT recover monitor placement by itself.
                    timers.clear()
                    ov_late._check_focus()
                    assert ov_late._focus_move is None and ov_late.monitor is None, (
                        "start-order quirk: _check_focus skips when self.monitor is None"
                    )
                    # Firing the scheduled 10s _check_screen timer recovers placement once mapped >= 2s.
                    ov_late._mapped_at = time.monotonic() - 5.0
                    assert check_screen_entry[2]() is True
                    assert ov_late.monitor is not None and ov_late.monitor.get_connector() == "DP-1", (
                        f"late socket recovery via scheduled _check_screen failed: {ov_late.monitor}"
                    )
                    # Unset HYPRLAND_INSTANCE_SIGNATURE: _hypr_socket returns None even though socket exists under 'ovl'.
                    os.environ.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
                    assert _hypr_socket("j/monitors") is None, "missing signature must yield None from _hypr_socket"
                    # Without Hyprland the rule is skipped, and a socket that does not answer fails quietly.
                    assert _no_layer_anim("check") is False and len(evals) == 1, evals
                    os.environ["HYPRLAND_INSTANCE_SIGNATURE"] = "gone"
                    assert _no_layer_anim("check") is False and len(evals) == 1, evals
                    os.environ["HYPRLAND_INSTANCE_SIGNATURE"] = "ovl"

                    # Follow-the-focused-monitor rule with live .socket2.sock events.
                    ov = make_stub_overlay(["DP-1", "DP-2"])
                    layer_calls.clear()
                    ov._place("Rook started")
                    assert ov.monitor.get_connector() == "DP-1"
                    # At home on the desktop the compositor centres the window, so no margin moves for a fan.
                    assert ov._centred and ("anchor", int(LayerShell.Edge.LEFT), False) in layer_calls, layer_calls
                    timers.clear()
                    fd_watches.clear()
                    ov._watch_focus()
                    assert ov._focus_sock is not None and len(fd_watches) == 1, "expected .socket2.sock watch"
                    deadline = time.monotonic() + 2.0
                    while not ev_clients and time.monotonic() < deadline:
                        time.sleep(0.01)
                    assert ev_clients, "stand-in socket2 did not accept client"
                    # At rest: focusedmon>> schedules FOLLOW_REST_MS (700 ms).
                    ev_clients[-1].sendall(b"focusedmon>>DP-2,2\n")
                    time.sleep(0.02)
                    assert ov._on_focus_events(ov._focus_sock.fileno(), None) is True
                    assert ov._focus_name == "DP-2" and timers[-1][1] == FOLLOW_REST_MS, timers[-1]
                    first_tid = ov._focus_move
                    # During a turn (not home): focusedmonv2>> replaces the pending timer with FOLLOW_SETTLE_MS (600 ms).
                    ov.scene.handle({"state": "thinking"}, 1.0)
                    ev_clients[-1].sendall(b"focusedmonv2>>DP-2,2\n")
                    time.sleep(0.02)
                    assert ov._on_focus_events(ov._focus_sock.fileno(), None) is True
                    assert first_tid in removed_timers and timers[-1][1] == FOLLOW_SETTLE_MS, (removed_timers, timers[-1])
                    # A config reload drops runtime rules: the no-animation rule is set again.
                    ev_clients[-1].sendall(b"configreloaded>>\n")
                    time.sleep(0.02)
                    assert ov._on_focus_events(ov._focus_sock.fileno(), None) is True and len(evals) == 2, evals
                    # Executing _follow_focus during a turn calls _regather -> _place onto DP-2.
                    m_d1["focused"], m_d2["focused"] = False, True
                    write_state()
                    scattered = []
                    orig_scatter = ov.scene.scatter
                    ov.scene.scatter = lambda: scattered.append(1) or orig_scatter()
                    assert ov._follow_focus() is False
                    assert ov.monitor.get_connector() == "DP-2" and scattered == [1], (ov.monitor, scattered)
                    # Back at rest, _check_focus detects focus moved back to DP-1 via .socket.sock.
                    ov.scene = Scene(0.0)
                    m_d1["focused"], m_d2["focused"] = True, False
                    write_state()
                    timers.clear()
                    assert ov._check_focus() is True
                    assert ov._focus_name == "DP-1" and timers[-1][1] == FOLLOW_REST_MS, timers[-1]
                    assert ov._follow_focus() is False
                    assert ov.monitor.get_connector() == "DP-1"
                    # _monitors_changed coalesces bursts into one 300ms timer calling _monitors_settled -> _replace.
                    timers.clear()
                    ov._monitors_changed()
                    ov._monitors_changed()
                    assert len(timers) == 1 and timers[0][1] == 300 and timers[0][2] == ov._monitors_settled, timers
                    # Socket2 EOF falls back to 1000ms _poll_focus.
                    timers.clear()
                    ev_clients[-1].close()
                    time.sleep(0.02)
                    assert ov._on_focus_events(ov._focus_sock.fileno(), None) is False
                    assert any(ms == 1000 and fn == ov._poll_focus for _, ms, fn, _, _ in timers), timers
                finally:
                    stop_socks.set()
                    for c in ev_clients:
                        try:
                            c.close()
                        except OSError:
                            pass
                    cmd_srv.close()
                    ev_srv.close()
                    t_cmd.join(timeout=1.0)
                    t_ev.join(timeout=1.0)
            finally:
                GLib.timeout_add, GLib.timeout_add_seconds, GLib.source_remove, GLib.unix_fd_add_full = saved_glib
                LayerShell.set_monitor, LayerShell.set_anchor, LayerShell.set_margin = saved_ls
                Gtk.Settings.get_default = saved_gtk_settings
        finally:
            for k, v in saved_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    print("placement and focus following (monitors, fractional scale, reserved, follow, start order): ok")


def _check_render():
    """The render tool's diagrams in the engine, on a virtual clock: an old scene gets a refusal, a diagram grows the
    swarm and the swarm shrinks back, steps answer, activity forms do not wipe a diagram, and its life follows the turn."""
    _check_placement()
    scene, clock = Scene(0.0), [0.0]

    def run(seconds):
        end = clock[0] + seconds
        while clock[0] < end:
            scene.step(clock[0])
            clock[0] += TICK_MS / 1000

    # Finding shows the prism, plain thinking never does, and a pack with no find icon thinks instead.
    for tool in ("Grep", "Glob", "find", "waypoint"):
        assert _simulate(_thinking_on(tool), 3.0, lift=0)[0].form == "prism", tool
    assert "prism" not in devs_pack.THINK_OTHERS
    flip = pack_player.FlipbookPresence({"icons": {}, "states": {"thinking": {"rook": "rook"}}})
    flip.set_state("find", 0.0)
    assert flip.state == "thinking"
    # Writing a file shows the Nib, and editing one the Strike (the owner's picks, 2026-11-27).
    for tool, name in (("Edit", "writing2_b"), ("Write", "writing2_a"), ("NotebookEdit", "writing2_b")):
        pen = _simulate(_thinking_on(tool), 3.0, lift=0)[0]
        assert pen.form == name and devs_pack.eval_targets(name, _form(name), pen, 3.0) is not None, tool
    # Reading a file shows the Devs scan ring.
    reader = _simulate(_thinking_on("Read"), 3.0, lift=0)[0]
    assert reader.form == "scan" and devs_pack.eval_targets("scan", _form("scan"), reader, 3.0) is not None
    # The WoW and system tools show their orb-free Devs forms (the owner's picks, 2026-11-27).
    for tool in ("find_npc", "find_quest", "find_item", "find_upgrades", "find_price", "find_object",
                 "Skill", "screenshot", "git", "media", "windows", "service", "background", "Bash", "recall",
                 "t3_thread_read", "WebSearch", "threads"):
        seeker = _simulate(_thinking_on(tool), 1.5, lift=0)[0]  # Before find_upgrades turns to prices.
        names = ACTIVITY_FORMS[tool] if ACTIVITY_FORMS[tool].__class__ is tuple else (ACTIVITY_FORMS[tool],)
        assert seeker.form in names, (tool, seeker.form)
        assert devs_pack.eval_targets(seeker.form, _form(seeker.form), seeker, 1.5) is not None, tool
    # find_price takes coins A and C in rotation: each appearance takes the next form and holds it while it shows.
    coins, shown = ACTIVITY_FORMS["find_price"], []
    for _ in coins:
        seeker, t = _simulate(_thinking_on("find_price"), 1.5, lift=0)
        held = {seeker.form}
        for k in range(1, 126):  # Two more seconds of the same appearance.
            seeker.step(t + k * TICK_MS / 1000)
            held.add(seeker.form)
        assert len(held) == 1 and seeker.form in coins, held
        shown.append(seeker.form)
    assert set(shown) == set(coins), shown

    # Devs listening shows only the helix (the owner, 2026-11-25). The ripples ring stays built as the halo style.
    cycle = devs_pack.STATES["listening"]["cycle"]
    assert [devs_pack.ICONS[n].get("form", n) for n in cycle] == ["helix"], cycle
    assert devs_pack.BUILDERS["halo"] is devs_pack.build_listen_ripples and LISTEN_STYLES["halo"] == "halo"
    # In silence every ripple grain waits dark on the ring, and the core rests as a dim dot at the centre. At full
    # voice ripples light inside and the core grows brighter.
    saved_listen = FORM_FOR_STATE["listening"]
    FORM_FOR_STATE["listening"] = "halo"
    core_ids = [i for i, p in enumerate(_form("halo")) if p[2] == -1]
    rest_core = 0.0
    try:
        for mic, lit_inside in ((lambda t: 0.002, 0), (lambda t: 1.0 if t > 1.0 else 0.002, 80)):
            sc_c, t_c = _simulate(LISTEN, 2.0, mic, lift=0)
            assert sc_c.form == "halo", sc_c.form
            tx, ty, tb, _ = devs_pack.eval_targets("halo", _form("halo"), sc_c, t_c)
            r = [math.hypot(x, y) for x, y in zip(tx, ty)]
            inside = sum(1 for d, b in zip(r, tb) if d < 30 and b > 0.05)
            core = sum(1 for d, b in zip(r, tb) if d < 1.5 * devs_pack.CORE_R and b > 0.05)
            core_tb = sum(tb[i] for i in core_ids) / len(core_ids)
            if lit_inside:
                assert inside >= lit_inside and core >= 20, f"level 1 lit {inside} grains inside, {core} at the core"
                assert core_tb > 2.5 * rest_core, f"the core glows {core_tb:.2f} at level 1, {rest_core:.2f} at rest"
            else:
                rest_core = core_tb
                assert all(0.3 < tb[i] < 0.5 and r[i] < devs_pack.CORE_R for i in core_ids), "the resting core is off"
                assert inside == len(core_ids), f"{inside - len(core_ids)} grains lit inside the ring in silence"
                assert all(abs(d - devs_pack.HALO_RING) < 2.6 for i, d in enumerate(r) if i not in core_ids), \
                    "a quiet grain left the ring"
                # The rim turns in silence: its grains' mean angle advances over 1 s of quiet steps, and still no
                # grain lights inside the ring.
                rim = [i for i, p in enumerate(_form("halo")) if p[2] is None]
                sc_n, t_n = _simulate(LISTEN, 3.0, mic, lift=0)
                tx_n, ty_n, tb_n, _ = devs_pack.eval_targets("halo", _form("halo"), sc_n, t_n)
                turned = sum((math.atan2(ty_n[i], tx_n[i]) - math.atan2(ty[i], tx[i]) + math.pi) % (2 * math.pi)
                             - math.pi for i in rim) / len(rim)
                assert 0.15 < turned < 0.4, f"the quiet rim turned {turned:.3f} rad in 1 s"
                lit = sum(1 for x, y, b in zip(tx_n, ty_n, tb_n) if math.hypot(x, y) < 30 and b > 0.05)
                assert lit == len(core_ids), f"{lit - len(core_ids)} grains lit inside the turning ring in silence"
        # The ripples clear, and the core eases back to rest, as fast at 120 Hz as at 60 Hz, because they run on the
        # real dt. Through the whole run, no grain's place lies beyond the rim's own spread.
        inner = [i for i, p in enumerate(_form("halo")) if p[2] is not None and p[2] >= 0]
        cleared = []
        for hz in (60, 120):
            sc_c, t_c, far = Scene(0.0), 0.0, 0.0
            sc_c.handle({"state": "listening"}, 0.0)
            while t_c < 5.0:
                if t_c < 3.0:
                    sc_c.handle({"level": 1.0 if t_c > 1.0 else 0.002}, t_c)
                sc_c.step(t_c)
                if t_c >= 1.0:
                    tx, ty, tb, _ = devs_pack.eval_targets("halo", _form("halo"), sc_c, t_c)
                    far = max(far, max(map(math.hypot, tx, ty)))
                    if (t_c >= 3.0 and all(tb[i] <= 0.01 for i in inner)
                            and all(tb[i] <= 0.46 for i in core_ids)):
                        break
                t_c += 1 / hz
            assert far < devs_pack.HALO_RING + 2.0, f"a grain's place lay {far:.2f} px out at {hz} Hz"
            cleared.append(t_c - 3.0)
        assert abs(cleared[0] - cleared[1]) <= 1 / 60 and 0.3 < cleared[0] < 0.8, f"ripples cleared in {cleared} s"
    finally:
        FORM_FOR_STATE["listening"] = saved_listen

    web = {"diagram": {"title": "Web", "graph": "browser > dns:globe > server* > page"}}
    scene.handle({"state": "thinking"}, 0.0)
    run(0.5)
    # An old scene request gets a refusal that names show_diagram, and nothing shows.
    gone = scene.render_command({"scene": {"parts": [{"id": "a", "circle": [50, 50, 10]}]}}, clock[0])
    assert gone == {"ok": False, "error": SCENE_GONE} and "show_diagram" in SCENE_GONE and scene.render is None, gone
    assert scene.render_command({"step": 1}, clock[0])["error"].startswith("No scene")
    sizes = list(scene.size)
    assert scene.render_command(web, clock[0])["ok"]
    run(1)
    scene.handle({"state": "thinking", "activity": "WebSearch"}, clock[0])
    run(1)
    assert scene.form == "render", "an activity form of the same turn wiped the diagram"
    scene.handle({"state": "speaking"}, clock[0])
    run(2)
    scene.handle({"state": "result"}, clock[0])
    run(scenes.SCENE_SECONDS - 1)
    assert scene.form == "render", "the diagram left before its time"
    run(2 + RENDER_FADE)
    assert scene.form == "loop" and scene.render is None and len(scene.x) == GRAINS and scene.size == sizes
    scene.render_command(web, clock[0])
    run(1)
    scene.handle({"state": "listening"}, clock[0])
    run(RENDER_FADE + 0.1)
    assert scene.form != "render" and len(scene.x) == len(scene.loose_until) == GRAINS
    assert scene.render_command({"clear": True}, clock[0])["said"] == "Nothing was on screen."
    run(RENDER_FADE + 0.5)
    scene.drop_render(clock[0])
    assert scene.render is None and scene.render_form is None
    # A form that fails as it commits leaves the state clean.
    try:
        scene.render_commit({"steps": [], "nodes": 1}, {"kind": "constellation"}, clock[0])
        assert False, "expected a bad form's commit to fail"
    except KeyError:
        pass
    assert scene.render is None and scene.render_form is None
    run(0.2)
    # A constellation: it grows the swarm to its fixed budget, its names fade in, a step lights a node, a list lights
    # two, the voice's end leaves all known, and the swarm shrinks back once it ends. Too few nodes shows nothing.
    assert not scene.render_command({"diagram": {"graph": "solo"}}, clock[0])["ok"] and scene.render is None
    said = scene.render_command({"diagram": {"title": "Web", "graph": "browser > dns:globe > server* > page"}},
                                clock[0])["said"]
    assert said == "Showing 4 nodes.", said
    run(1.5)
    con = scene.render_form["con"]
    assert len(scene.x) == constellation.BUDGET and scene.size_k == 1.0 and len(scene.diagram_names(clock[0])) == 5
    assert scene.render_reach(clock[0]) <= scene.render_form["size"][1] and scene.render_width_px <= WIDTH
    assert scene.render_command({"step": 2}, clock[0])["ok"] and con.focal == 1
    assert scene.render_command({"step": [3, 4]}, clock[0])["ok"] and con.lit == {2, 3} and 1 in con.known
    assert not scene.render_command({"step": 9}, clock[0])["ok"]
    run(1)
    scene.render_command({"step": 0}, clock[0])
    assert con.focal is None and con.known == {0, 1, 2, 3}
    scene.render_command({"clear": True}, clock[0])
    run(RENDER_FADE + 0.5)
    assert scene.render is None and len(scene.x) == GRAINS and not scene.diagram_names(clock[0])
    # Review 38 offscreen guards: Cairo frame cost (dark, light, flight), light GL support, u_time wrap,
    # broken-pack resilience + stdin watch armor, Nova zero-dust-work, and full Nova tour.
    global PARTICLE_VARIANT
    import tempfile
    assert _DustGL.supports(THEMES["dark"]) and _DustGL.supports(THEMES["light"])
    assert abs(math.sin(1.55 * _TIME_WRAP)) < 1e-9 and abs(math.sin(0.90 * _TIME_WRAP)) < 1e-9

    def _time_cairo(variant, theme_name, state_msg, steps_s, n_frames=20):
        global PARTICLE_VARIANT
        saved_v, saved_p = PARTICLE_VARIANT, PALETTE
        try:
            PARTICLE_VARIANT = variant
            _use_theme(theme_name)
            s = Scene(0.0)
            s.handle(state_msg, 0.0)
            t0 = 0.0
            while t0 < steps_s:
                s.step(t0)
                t0 += TICK_MS / 1000
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(math.ceil(ORB_W * 1.6)), int(math.ceil(ORB_H * 1.6)))
            surf.set_device_scale(1.6, 1.6)
            cr = cairo.Context(surf)
            s.draw_swarm(cr, ORB_W, t0)  # warm
            times = []
            for k in range(n_frames):
                t_a = time.perf_counter()
                s.draw_swarm(cr, ORB_W, t0 + k * 0.016)
                times.append((time.perf_counter() - t_a) * 1000.0)
            times.sort()
            return times[len(times) // 2]
        finally:
            PARTICLE_VARIANT = saved_v
            _use_theme("light" if saved_p is THEMES["light"] else "dark")

    cairo_stats = {}
    for label_k, th_name, msg_k, dur_s in (
        ("dark_rest", "dark", {"state": "ready"}, 0.4),
        ("dark_think", "dark", {"state": "thinking"}, 0.6),
        ("light_think", "light", {"state": "thinking"}, 0.6),
        ("flight", "dark", {"state": "listening", "level": 0.6}, 0.2),
    ):
        base_ms = _time_cairo("baseline", th_name, msg_k, dur_s)
        cur_ms = _time_cairo("C", th_name, msg_k, dur_s)
        cairo_stats[label_k] = (base_ms, cur_ms)
        limit_ms = max(base_ms * 2.5, base_ms + 1.5)
        assert cur_ms <= limit_ms and cur_ms < 4.0, f"Cairo {label_k} too slow: {cur_ms:.2f} ms vs baseline {base_ms:.2f} ms"

    # Lit-area and brightness guard per form: fast Cairo fallback must never drop dim grains / half-draw any form.
    def _lit_stats(buf, dark=True):
        lit = 0
        val_sum = 0.0
        for idx_p in range(0, len(buf), 4):
            b_p, g_p, r_p, a_p = buf[idx_p], buf[idx_p + 1], buf[idx_p + 2], buf[idx_p + 3]
            if dark:
                y_p = 0.2126 * r_p + 0.7152 * g_p + 0.0722 * b_p
                if y_p >= 8.0 or a_p >= 12:
                    lit += 1
                    val_sum += y_p
            elif a_p >= 12:
                lum_p = 0.2126 * r_p + 0.7152 * g_p + 0.0722 * b_p
                lit += 1
                val_sum += max(0.0, a_p - lum_p)
        return lit, (val_sum / lit if lit else 0.0)

    saved_pal_lit = PALETTE
    saved_listen_form = FORM_FOR_STATE.get("listening")
    try:
        for mode_lit in ("dark", "light"):
            _use_theme(mode_lit)
            for fname_lit, msg_lit, dur_lit in (
                ("loop", {"state": "ready"}, 1.2),
                ("sphere", {"state": "speaking", "level": 0.6}, 1.2),
                ("rook", {"state": "thinking"}, 1.2),
                ("lattice", {"state": "thinking"}, 5.2),
                ("helix", {"state": "listening", "level": 0.6}, 1.2),
                ("question", {"state": "permission"}, 1.2),
            ):
                if fname_lit == "helix":
                    FORM_FOR_STATE["listening"] = "helix"
                sc_l = Scene(0.0)
                sc_l.lift = 0.0
                sc_l.rest_pad = 110.0
                sc_l.handle(msg_lit, 0.0)
                t_l = 0.0
                while t_l < dur_lit:
                    sc_l.step(t_l)
                    t_l += TICK_MS / 1000
                wp_l, hp_l = math.ceil(230 * 1.6), math.ceil(220 * 1.6)
                sf_ref = cairo.ImageSurface(cairo.FORMAT_ARGB32, wp_l, hp_l)
                sf_ref.set_device_scale(1.6, 1.6)
                sc_l.draw_swarm(cairo.Context(sf_ref), 230, t_l, top=0.0, centre=(115, 110), label=False, soft=True)
                sf_fast = cairo.ImageSurface(cairo.FORMAT_ARGB32, wp_l, hp_l)
                sf_fast.set_device_scale(1.6, 1.6)
                sc_l.draw_swarm(cairo.Context(sf_fast), 230, t_l, top=0.0, centre=(115, 110), label=False, soft=False)
                ref_a, ref_v = _lit_stats(bytes(sf_ref.get_data()), dark=(mode_lit == "dark"))
                fst_a, fst_v = _lit_stats(bytes(sf_fast.get_data()), dark=(mode_lit == "dark"))
                ratio_a = fst_a / max(1, ref_a)
                ratio_v = fst_v / max(1e-3, ref_v)
                assert 0.75 <= ratio_a <= 1.25, f"Fast Cairo {mode_lit} {fname_lit} area ratio {ratio_a:.2f} out of bounds ({fst_a} vs {ref_a})"
                assert 0.72 <= ratio_v <= 1.28, f"Fast Cairo {mode_lit} {fname_lit} val ratio {ratio_v:.2f} out of bounds ({fst_v:.1f} vs {ref_v:.1f})"
    finally:
        if saved_listen_form is not None:
            FORM_FOR_STATE["listening"] = saved_listen_form
        _use_theme("light" if saved_pal_lit is THEMES["light"] else "dark")

    # Broken-pack resilience: deleted atlas, broken manifest field, unknown theme, and runtime deleted atlas.
    nova_src = os.path.join(pack_player.THEMES_DIR, "nova")
    if os.path.isdir(nova_src):
        with tempfile.TemporaryDirectory(prefix="rook_pack_check_") as tmpdir:
            # 1) Deleted atlas before switch
            p_del = os.path.join(tmpdir, "bad_missing")
            shutil.copytree(nova_src, p_del)
            os.remove(os.path.join(p_del, "baked", "rest.webp"))
            s_bp = Scene(0.0)
            assert not s_bp.set_pack("bad_missing", 0.0, themes_dir=tmpdir)
            assert s_bp.pack_name == "devs" and s_bp.pack_kind == "points"
            # 2) Broken manifest field (fps: 0 and non-dict icons)
            p_bad = os.path.join(tmpdir, "bad_manifest")
            shutil.copytree(nova_src, p_bad)
            mpath = os.path.join(p_bad, "manifest.json")
            with open(mpath, "r", encoding="utf-8") as f:
                mdata = json.load(f)
            mdata["icons"]["rest"]["fps"] = 0
            with open(mpath, "w", encoding="utf-8") as f:
                json.dump(mdata, f)
            assert not s_bp.set_pack("bad_manifest", 0.0, themes_dir=tmpdir)
            assert s_bp.pack_name == "devs" and s_bp.pack_kind == "points"
            mdata["icons"] = []
            with open(mpath, "w", encoding="utf-8") as f:
                json.dump(mdata, f)
            assert not s_bp.set_pack("bad_manifest", 0.0, themes_dir=tmpdir)
            assert s_bp.pack_name == "devs" and s_bp.pack_kind == "points"
            # 3) Unknown theme / pack name via Scene.handle
            s_bp.handle({"pack": "no_such_pack_999"}, 0.1)
            assert s_bp.pack_name == "devs" and s_bp.pack_kind == "points"
            s_bp.handle({"theme": "no_such_pack_999"}, 0.2)
            assert s_bp.pack_name == "devs" and s_bp.pack_kind == "points"
            # 4) Runtime deleted atlas during Cairo draw falls back to Devs without raising
            p_rt = os.path.join(tmpdir, "bad_runtime")
            shutil.copytree(nova_src, p_rt)
            assert s_bp.set_pack("bad_runtime", 0.3, themes_dir=tmpdir)
            assert s_bp.pack_kind == "flipbook"
            os.remove(os.path.join(p_rt, "baked", "rest.webp"))
            surf_rt = cairo.ImageSurface(cairo.FORMAT_ARGB32, 240, 240)
            s_bp.draw_swarm(cairo.Context(surf_rt), 240, 0.4)
            assert s_bp.pack_name == "devs" and s_bp.pack_kind == "points"
            # 4b) AtlasLoader rebake recovery, daemon worker, and ready-cache cleanup on pack switch
            p_rb = os.path.join(tmpdir, "nova_rebake")
            shutil.copytree(nova_src, p_rb)
            rb_rest = os.path.join(p_rb, "baked", "rest.webp")
            rb_orig = open(rb_rest, "rb").read()
            os.remove(rb_rest)
            pack_player.ATLAS_LOADER.reset_for_pack(None)
            pack_player.ATLAS_LOADER.prefetch(rb_rest)
            for _ in range(40):
                if pack_player.ATLAS_LOADER.failure(rb_rest):
                    break
                time.sleep(0.01)
            assert pack_player.ATLAS_LOADER.failure(rb_rest) is not None
            assert pack_player.ATLAS_LOADER._worker is not None and pack_player.ATLAS_LOADER._worker.daemon
            with open(rb_rest, "wb") as f:
                f.write(rb_orig)
            assert s_bp.set_pack("nova_rebake", 0.5, themes_dir=tmpdir)
            assert pack_player.ATLAS_LOADER.failure(rb_rest) is None
            time.sleep(0.05)
            assert s_bp.set_pack("devs", 0.6)
            assert pack_player.ATLAS_LOADER.ready_bytes == 0

        # 5) Stdin watch armor: even a raising handle() never removes the stdin watch.
        class _StdinStub:
            _buffer = b""
            quitting = False
            def handle(self, _msg):
                raise RuntimeError("simulated malformed message failure")

        r_fd, w_fd = os.pipe()
        try:
            os.write(w_fd, b'{"pack":"broken"}\n')
            assert Overlay._on_stdin(_StdinStub(), r_fd, None) is True
        finally:
            os.close(r_fd)
            os.close(w_fd)

        # 6) Nova skips all dust work + full Nova tour across every state and thinking icon.
        s_nv = Scene(0.0)
        assert s_nv.set_pack("nova", 0.0)
        s_nv.spring_gl = True
        x_snap = list(s_nv.x)
        tour_states = [
            ({"state": "ready"}, 0.2),
            ({"state": "listening", "level": 0.6}, 0.6),
            ({"state": "transcribing"}, 0.4),
            ({"state": "thinking"}, 26.0),
            ({"state": "speaking", "level": 0.7}, 0.6),
            ({"state": "thinking", "activity": "handoff"}, 0.4),
            ({"state": "thinking", "activity": "aperture"}, 0.4),
            ({"state": "thinking", "activity": "timer"}, 0.4),
            ({"state": "permission"}, 0.4),
            ({"state": "error"}, 0.4),
            ({"state": "listening", "level": 0.5}, 0.6),
            ({"state": "ready"}, 0.4),
        ]
        t_nv = 0.0
        seen_icons = set()
        worst_step_ms = 0.0
        for msg_t, dur_t in tour_states:
            s_nv.handle(msg_t, t_nv)
            end_t = t_nv + dur_t
            while t_nv < end_t:
                t_a = time.perf_counter()
                s_nv.step(t_nv)
                quads = s_nv.flipbook.draw_list(t_nv, pack_player.state_level_for_scene(s_nv.pack, s_nv.flipbook.state, s_nv))
                worst_step_ms = max(worst_step_ms, (time.perf_counter() - t_a) * 1000.0)
                for q in quads:
                    seen_icons.add(q["icon"])
                assert not s_nv.spring_steps and not s_nv.springs_on_gpu
                t_nv += 0.25
        assert s_nv.x == x_snap, "Nova stepped Devs particle positions"
        for req_icon in ("rest", "listen", "helix", "transcribe", "rook", "lattice", "star", "synapse", "board", "speak", "card", "timer", "error"):
            assert req_icon in seen_icons, f"Nova full tour missed icon {req_icon!r} (saw {sorted(seen_icons)})"
        # The viewer shows an animated picture over Nova and closes: Nova fades back in whole and keeps stepping.
        with tempfile.TemporaryDirectory(prefix="rook_view_nova_") as vtmp:
            gif = os.path.join(vtmp, "two.gif")
            with open(gif, "wb") as fh:  # A 1x1 GIF of two looping frames, black then white.
                fh.write(bytes.fromhex("47494638396101000100800000000000ffffff21ff0b4e45545343415045322e300301000000"
                                       "21f904000a0000002c000000000100010000020244010021f904000a0000002c00000000010001"
                                       "000002024c01003b"))
            _, _, pic = _load_media(gif, (0, 0, 1920, 1080), 1.0)
            assert pic.kind == "animation" and len(pic.frames) == 2, (pic.kind, len(pic.frames))
            s_nv.open_view(t_nv, (-100, -80, 200, 160), (-90, -70, 180, 140))
            for _ in range(40):
                s_nv.step(t_nv)
                t_nv += 0.05
            assert s_nv.swarm_vis == 0.0, s_nv.swarm_vis
            s_nv.close_view(t_nv)
            pic.close()
            assert not pic.frames and not pic.textures
            for _ in range(80):
                s_nv.step(t_nv)
                t_nv += 0.05
            assert s_nv.view is None and s_nv.swarm_vis == 1.0 and _smooth(s_nv.swarm_vis) == 1.0, s_nv.swarm_vis
            assert s_nv.moved_at == s_nv.last, "Nova stopped stepping after the viewer closed"
            quads = s_nv.flipbook.draw_list(t_nv, pack_player.state_level_for_scene(s_nv.pack, s_nv.flipbook.state, s_nv))
            assert quads and max(q["alpha"] for q in quads) > 0.5, "Nova drew nothing after the viewer closed"
        print(f"cairo guard (base -> C ms): " + ", ".join(f"{k}={b:.2f}->{c:.2f}" for k, (b, c) in cairo_stats.items())
              + f"; broken packs & stdin armor: ok; nova tour ({len(seen_icons)} icons, worst step {worst_step_ms:.2f} ms): ok")

    # Multi-thread dispatch offscreen checks: 0 names, 40 names, long name, markup/control chars,
    # outcome updates, replacement mid-flight, laptop/ultrawide/narrow widths, light theme, Nova stand-in.
    sd = Scene(0.0)
    sd.handle({"state": "thinking"}, 0.0)
    # 1) Zero names / whitespace-only -> no active fan
    sd.handle({"send": []}, 0.1)
    assert not sd.dispatch_active(0.1)
    sd.handle({"send": [{"name": "  \x00\t\n  "}]}, 0.15)
    assert not sd.dispatch_active(0.15)
    # 2) Forty names -> capped to 6 rows with "and 35 more" on row 6, alternating right/left
    forty = [{"id": f"k{i}", "name": f"Thread {i}", "outcome": "pending"} for i in range(40)]
    sd.handle({"send": forty}, 0.2)
    assert sd.dispatch_active(0.2) and len(sd.dispatch.rows) == 6
    assert sd.dispatch.rows[5]["more"] and sd.dispatch.rows[5]["name"] == "and 35 more"
    assert [r["side"] for r in sd.dispatch.rows] == [1.0, -1.0, 1.0, -1.0, 1.0, -1.0]
    assert sd.label_text(0.5) == ""
    sd.step(0.6)
    assert sd.form in devs_pack.SEND_FORMS, sd.form
    # 3) Outcome updates in place (pending -> landed / failed -> not-landed / unknown) keep t0,
    #    including folded rows (#7..#40) and unmatched outcome-only settles without ever clearing the fan.
    t0_keep = sd.dispatch.t0
    sd.handle({"send": [{"id": "k0", "outcome": "landed"}, {"id": "k1", "outcome": "failed"}, {"id": "k2", "outcome": "unknown"}]}, 1.1)
    assert sd.dispatch.t0 == t0_keep
    assert sd.dispatch.rows[0]["outcome"] == "landed"
    assert sd.dispatch.rows[1]["outcome"] == "not-landed"
    assert sd.dispatch.rows[2]["outcome"] == "unknown"
    # Folded row #7 (id "k7") settles cleanly without wiping the fan; unmatched outcome-only settle is ignored.
    sd.handle({"send": [{"id": "k7", "outcome": "landed"}]}, 1.15)
    assert sd.dispatch is not None and sd.dispatch.t0 == t0_keep
    assert any(r["id"] == "k7" and r["outcome"] == "landed" for r in sd.dispatch.folded_rows)
    sd.handle({"send": [{"id": "no-such-id", "outcome": "failed"}]}, 1.2)
    assert sd.dispatch is not None and sd.dispatch.t0 == t0_keep
    # Pending fan holds calmly up to DISPATCH_MAX_WAIT (8.0 s) and ends at once if the owner starts listening.
    assert sd.dispatch_active(7.5) and not sd.dispatch_leaving(7.5)
    assert sd.dispatch_leaving(8.25) and not sd.dispatch_active(8.9)
    sd.handle({"send": [{"id": "p1", "name": "Wait test", "outcome": "pending"}]}, 1.22)
    assert sd.dispatch_active(1.22)
    # Same-turn tool activity keeps the fan alive. The owner's turn, a card, hidden or dark end it at once; thinking again
    # mid-turn (as when a spoken line ends) or the turn moving on plays the teardown.
    sd.handle({"activity": "WebSearch"}, 1.23)
    assert sd.dispatch_active(1.23)
    for end_msg in ({"state": "listening"}, {"state": "transcribing"}, {"state": "speaking"},
                    {"state": "permission"}, {"state": "error"}, {"state": "result"},
                    {"state": "ready"}, {"state": "hidden"}, {"dark": True}, {"state": "thinking"}):
        sd.handle({"dark": False, "state": "thinking"}, 1.24)
        sd.handle({"send": [{"id": "p1", "name": "Wait test", "outcome": "pending"}]}, 1.24)
        assert sd.dispatch_active(1.24), end_msg
        sd.step(1.245)
        assert sd.form in devs_pack.SEND_FORMS and sd.dispatch.ports is not None, (end_msg, sd.form)
        sd.handle(end_msg, 1.25)
        if end_msg.get("state") in (*FAN_TEARDOWN_STATES, "thinking"):
            # The turn moved on: the teardown plays once the names have shown for DISPATCH_MIN_SHOW, an outcome
            # then does not bring the fan back, and it ends.
            ds = sd.dispatch
            cut = ds.t0 + ds.end_at
            assert abs(cut - max(1.25, min(ds.t0 + ds.landed_at + DISPATCH_MIN_SHOW, cut))) < 1e-6, end_msg
            assert sd.dispatch_active(1.25) and sd.dispatch_leaving(cut), end_msg
            assert cut <= 1.25 or not sd.dispatch_leaving(cut - 0.01), end_msg
            sd.step(cut + 0.005)
            assert sd.form in devs_pack.SEND_FORMS and sd.send_clock(cut + 0.35)[1] > 0.4, (end_msg, sd.form)
            sd.handle({"send": [{"id": "p1", "outcome": "landed"}]}, cut + 0.05)
            assert sd.dispatch_active(cut + 0.65) and not sd.dispatch_active(cut + DISPATCH_OUT + 0.01), end_msg
            done_at = cut + DISPATCH_OUT + 0.005
        else:
            assert not sd.dispatch_active(1.25) and sd.dispatch is None, f"fan survived {end_msg}"
            done_at = 1.255 + DISPATCH_OUT
        sd.step(done_at)
        assert sd.form not in devs_pack.SEND_FORMS, f"send form survived {end_msg}"
    sd.handle({"dark": False, "state": "speaking"}, 1.255)
    sd.handle({"send": [{"id": "sp1", "name": "Ignored while speaking", "outcome": "pending"}]}, 1.256)
    sd.step(1.258)
    assert sd.dispatch is None and sd.form == "sphere", f"speaking lost to send: {sd.form}"
    sd.handle({"state": "thinking"}, 1.26)
    sd.handle({"send": [{"id": "p2", "name": "Viewer clear", "outcome": "pending"}]}, 1.26)
    sd.open_view(1.27, (-100, -80, 200, 160), (-90, -70, 180, 140))
    assert sd.dispatch is None
    sd.view = None
    # An answer to a thread's question is a send: before its fan it thinks and says so, with no lone form, and arriving
    # during a live fan it never cuts it. Reading a thread's questions shows the reading form, with no fan.
    sa = Scene(0.0)
    sa.handle({"state": "thinking", "activity": "t3_pending_request"}, 0.0)
    sa.step(0.5)
    assert sa.form not in (*devs_pack.SEND_FORMS, "message") and sa.label_text(0.5) == "SENDING TO AGENT", sa.form
    assert {ACTIVITY_LABELS[k] for k in ("t3_thread_send", "handoff", "t3_pending_request")} == {"SENDING TO AGENT"}
    sa.handle({"activity": "t3_thread_send"}, 0.6)
    sa.handle({"send": [{"id": "a", "name": "Opus"}]}, 0.6)
    for k in range(1, 300):
        t = 0.6 + k / 60
        if k == 60:
            sa.handle({"activity": "t3_pending_request"}, t)
            sa.handle({"send": [{"id": "a", "name": "Opus"}, {"id": "answer:t:r", "name": "Neon"}]}, t)
            assert sa.dispatch_active(t) and [r["name"] for r in sa.dispatch.rows] == ["Opus", "Neon"]
        sa.step(t)
        if k >= 60 and sa.dispatch_active(t):
            assert sa.form in devs_pack.SEND_FORMS, (t, sa.form, "the answer cut the fan")
    sa = Scene(0.0)
    sa.handle({"state": "thinking", "activity": "t3_thread_read"}, 0.0)
    sa.step(0.5)
    assert sa.form in ACTIVITY_FORMS["t3_thread_read"] and sa.dispatch is None, sa.form  # A form, or forms in turn.
    sd.handle({"state": "thinking"}, 1.28)
    # 4) Lone surrogates + markup + control chars across dispatch, captions, scene labels, and titles never crash Pango.
    sd.handle({"send": [{"name": "\ud800<b>Urgent\x07\n<span color='red'>&amp;</b> " + "longword " * 40,
                         "project": "rook\ud800\x01", "machine": "oak", "outcome": "landed"}]}, 1.3)
    assert sd.dispatch.t0 == 1.3 and len(sd.dispatch.rows) == 1
    assert "\ud800" not in sd.dispatch.rows[0]["name"] and "\x07" not in sd.dispatch.rows[0]["name"] and "\n" not in sd.dispatch.rows[0]["name"]
    assert len(sd.dispatch.rows[0]["name"]) <= DISPATCH_RAW_CAP
    assert "<b>" in sd.dispatch.rows[0]["name"]  # kept as literal plain text, never stripped/parsed as markup
    assert sd.dispatch.rows[0]["where"] == "ROOK? · OAK"
    _surf_utf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 80)
    _cr_utf = cairo.Context(_surf_utf)
    _s_utf = Sentence("\ud800Hello \udfffworld", [(0, 6, 0.0), (7, 13, 0.2)])
    _s_utf.build(_cr_utf, 1.0)
    _word_sprite(_cr_utf, "\ud800label", 1.0)
    assert "\ud800" not in _fit_title("\ud800Title", 120)
    # Edge-aware side placement: near left edge puts all names on right; near right edge puts all on left.
    ds_edge = DispatchState([{"id": "e1", "name": "One"}, {"id": "e2", "name": "Two"}], 0.0)
    ds_edge.layout_for_canvas(120.0, 1200.0, 2000.0)
    assert all(r["side"] > 0 for r in ds_edge.rows)
    ds_edge.layout_for_canvas(1080.0, 1200.0, 1200.0)
    assert all(r["side"] < 0 for r in ds_edge.rows)
    # Verify GPU-cached row textures build once and reuse across frames with zero new texture allocations.
    snap_chk = Gtk.Snapshot.new()
    ds_edge.append_gl_overlay(snap_chk, 600.0, 100.0, 1200.0, 0.9, 2000.0, 1.6, PALETTE, is_nova=False)
    cache_n = len(ds_edge._tex_cache)
    mark_n = len(ds_edge._mark_cache)
    ds_edge.append_gl_overlay(snap_chk, 600.0, 100.0, 1200.0, 1.2, 2000.0, 1.6, PALETTE, is_nova=False)
    assert len(ds_edge._tex_cache) == cache_n and len(ds_edge._mark_cache) == mark_n
    # 5) Render cleanly across laptop (2000), ultrawide (5120), narrow (900), light theme, and Nova stand-in
    saved_pal = PALETTE
    try:
        for mon_w, th_name, pk_name in ((2000.0, "dark", "devs"), (5120.0, "dark", "devs"),
                                        (900.0, "dark", "devs"), (2000.0, "light", "devs"),
                                        (2000.0, "dark", "nova")):
            _use_theme(th_name)
            sd.set_pack(pk_name, 1.3)
            sd.monitor_width = mon_w
            fw = sd.dispatch_canvas_width()
            assert WIDTH <= fw <= int(mon_w)
            sd.step(4.0)  # The strands leave once the send form has assembled.
            gl_rows = sd.dispatch_gl_rows(4.0)
            assert len(gl_rows) > 0 and len(gl_rows) % 11 == 0
            surf_d = cairo.ImageSurface(cairo.FORMAT_ARGB32, fw, ORB_H)
            sd.draw_swarm(cairo.Context(surf_d), fw, 4.0, top=0.0)
            # Verify middle-cut fit respects room limit
            for _k, (_txt, tw_px, _th_px) in sd.dispatch._fit_cache.items():
                room_lim = min(DISPATCH_MAX_W, max(80.0, mon_w / 2.0 - (DISPATCH_R + DISPATCH_REACH + DISPATCH_GAP) - DISPATCH_EDGE))
                assert tw_px <= room_lim + 2 or _k[1] != int(round(room_lim))
        # 6) Verify Nova CP7: per-icon anchors (no 164 px slide), premultiplied flash, 60 fps changing(),
        # search state (Devs globe + Nova search + fallback to thinking), baked dispatch lifecycle, and user packs.
        s_nv_d = Scene(0.0)
        s_nv_d.lift = 250.0
        s_nv_d.rest_pad = 128.0
        s_nv_d.set_pack("nova", 0.0)
        assert pack_player.has_dispatch_bake(s_nv_d.pack)
        s_nv_d.handle({"state": "ready"}, 0.0)
        s_nv_d.home = True
        s_nv_d.step(0.1)
        assert s_nv_d.flipbook.cur["name"] == "rest"
        assert not s_nv_d.flipbook.changing(0.1)
        # Transition rest -> listening: rest stays at rest_dy while listen and premultiplied flash sit at 0.0 (zero slide).
        rdy = s_nv_d.rest_y_offset()
        assert rdy < -100.0
        s_nv_d.home = False
        s_nv_d.handle({"state": "listening"}, 0.2)
        s_nv_d.step(0.2)
        s_nv_d.step(0.32)
        assert s_nv_d.flipbook.changing(0.32)
        q_tr = s_nv_d.flipbook.draw_list(0.32, 0.4, rest_dy=rdy)
        by_ic = {}
        for q in q_tr:
            by_ic.setdefault(q["icon"], []).append(q)
        assert "rest" in by_ic and all(abs(q["dy"] - rdy) < 1e-6 for q in by_ic["rest"]), by_ic
        assert "listen" in by_ic and all(abs(q["dy"]) < 1e-6 for q in by_ic["listen"]), by_ic
        assert "flash" in by_ic and all(not q["additive"] and abs(q["dy"]) < 1e-6 for q in by_ic["flash"]), by_ic
        s_nv_d.step(0.95)
        assert not s_nv_d.flipbook.changing(0.95)
        # Search state: WebSearch & WebFetch -> Nova 'search' (Devs 'globe'); find -> Nova 'find' (Devs 'prism');
        # write (Edit/Write/NotebookEdit) -> Nova 'quill' (Devs 'quill'); missing state falls back to thinking.
        s_nv_d.handle({"state": "thinking", "activity": "Grep"}, 0.96)
        s_nv_d.step(0.97)
        assert pack_player.map_overlay_state(s_nv_d) == "find" and s_nv_d.flipbook.cur["name"] == "find"
        s_nv_d.handle({"state": "thinking", "activity": "Edit"}, 0.98)
        s_nv_d.step(0.99)
        assert pack_player.map_overlay_state(s_nv_d) == "write" and s_nv_d.flipbook.cur["name"] == "quill"
        s_nv_d.handle({"state": "thinking", "activity": "WebSearch"}, 1.0)
        s_nv_d.step(1.05)
        assert pack_player.map_overlay_state(s_nv_d) == "search" and s_nv_d.flipbook.cur["name"] == "search"
        s_nv_d.handle({"activity": "WebFetch"}, 1.1)
        assert pack_player.map_overlay_state(s_nv_d) == "search"
        sd_web = Scene(0.0)
        sd_web.handle({"state": "thinking", "activity": "WebSearch"}, 0.0)
        sd_web.step(0.1)
        assert sd_web.form in ACTIVITY_FORMS["WebSearch"]
        # Missing state fallback: walk every companion state & activity against a pack holding only rest + thinking icons.
        p_minimal = {
            **s_nv_d.pack,
            "icons": {k: v for k, v in s_nv_d.pack["icons"].items() if k == "rest" or k == "rook" or v.get("think")},
            "states": {"rest": "rest", "thinking": s_nv_d.pack["states"]["thinking"]},
        }
        fp_min = pack_player.FlipbookPresence(p_minimal)
        think_set = {"rook"} | {k for k, v in p_minimal["icons"].items() if v.get("think")}
        s_min = Scene(0.0)
        for idx_m, m_msg in enumerate([
            {"state": "ready"},
            {"state": "listening", "level": 0.4},
            {"state": "transcribing"},
            {"state": "thinking"},
            {"state": "thinking", "activity": "Grep"},
            {"state": "thinking", "activity": "Glob"},
            {"state": "thinking", "activity": "find"},
            {"state": "thinking", "activity": "waypoint"},
            {"state": "thinking", "activity": "Edit"},
            {"state": "thinking", "activity": "Write"},
            {"state": "thinking", "activity": "NotebookEdit"},
            {"state": "thinking", "activity": "WebSearch"},
            {"state": "thinking", "activity": "WebFetch"},
            {"state": "thinking", "activity": "timer"},
            {"state": "thinking", "activity": "show"},
            {"state": "thinking", "activity": "t3_thread_send"},
            {"state": "speaking", "level": 0.7},
            {"state": "permission"},
            {"state": "result"},
            {"state": "error"},
            {"state": "hidden"},
        ]):
            t_m = idx_m * 0.5
            s_min.handle(m_msg, t_m)
            s_min.home = m_msg["state"] in ("ready", "result", "hidden")
            s_min.last = t_m
            mapped = pack_player.map_overlay_state(s_min)
            fp_min.set_state(mapped, t_m)
            got_ic = fp_min.pick(t_m)
            if mapped == "rest":
                assert got_ic == "rest", (m_msg, mapped, got_ic)
            else:
                assert fp_min.state == "thinking" and got_ic in think_set, (m_msg, mapped, fp_min.state, got_ic)
        # CP8 speak speech bubble: level 0 -> flat line (stretch 0.1, glow 0, scale 0.96); high level -> tall bright wave.
        s_nv_d.handle({"state": "speaking", "level": 0.0}, 1.12)
        s_nv_d.step(1.12)
        s_nv_d.step(1.15)
        q_sp0 = s_nv_d.flipbook.draw_list(1.8, 0.0, rest_dy=0.0)
        assert len(q_sp0) == 2 and abs(q_sp0[0]["scale"] - 0.96) < 1e-4 and abs(q_sp0[1]["stretch"] - 0.1) < 1e-4
        assert abs(q_sp0[1]["alpha"] - 0.55) < 1e-4
        q_sp1 = s_nv_d.flipbook.draw_list(1.8, 1.0, rest_dy=0.0)
        assert len(q_sp1) == 3 and all(abs(q["scale"] - 1.05) < 1e-4 for q in q_sp1)
        assert abs(q_sp1[1]["alpha"] - 1.0) < 1e-4 and abs(q_sp1[2]["stretch"] - 1.0) < 1e-4
        # Return to rest, then test baked dispatch lifecycle on an active thinking turn (rest -> dispatch_in -> dispatch).
        s_nv_d.handle({"state": "ready"}, 1.2)
        s_nv_d.home = True
        s_nv_d.step(1.2)
        s_nv_d.step(1.8)
        assert s_nv_d.flipbook.cur["name"] == "rest"
        s_nv_d.handle({"state": "thinking",
                       "send": [{"id": "n1", "name": "Rook build", "outcome": "pending"},
                                {"id": "n2", "name": "Phone collapse", "outcome": "failed"}]}, 2.0)
        s_nv_d.step(2.1)
        assert not s_nv_d.dispatch_nova_standin(2.1)
        assert s_nv_d.flipbook.cur["name"] == "dispatch_in" and not s_nv_d.flipbook.cur["reverse"]
        assert s_nv_d.flipbook.changing(2.1)
        s_nv_d.step(2.5)
        assert s_nv_d.flipbook.cur["name"] == "dispatch"
        tips = s_nv_d.dispatch_tip_levels(2.5)
        assert tips[1] > 0.1 and tips[-1] > 0.1
        nstr = s_nv_d.dispatch.nova_strand_data(2.5, tip_at=s_nv_d.flipbook.dispatch_tip_at())
        assert len(nstr) == 2 and any(st["head_pos"] is not None for st in nstr)
        surf_nv = cairo.ImageSurface(cairo.FORMAT_ARGB32, s_nv_d.dispatch_canvas_width(), ORB_H)
        s_nv_d.draw_swarm(cairo.Context(surf_nv), s_nv_d.dispatch_canvas_width(), 2.5, top=0.0)
        # While n1 is still pending, Nova dispatch holds past 3.0 s; settling n1 at 3.0 schedules leave after the hold.
        s_nv_d.step(3.0)
        assert s_nv_d.dispatch_active(3.0) and not s_nv_d.dispatch_leaving(3.0)
        s_nv_d.handle({"send": [{"id": "n1", "outcome": "landed"}]}, 3.0)
        s_nv_d.step(3.0 + DISPATCH_HOLD + 0.05)
        assert s_nv_d.dispatch_leaving(3.0 + DISPATCH_HOLD + 0.05)
        s_nv_d.step(3.0 + DISPATCH_HOLD + DISPATCH_OUT + 0.05)
        assert not s_nv_d.dispatch_active(3.0 + DISPATCH_HOLD + DISPATCH_OUT + 0.05)
        # While Nova is speaking, an incoming send never overrides the speaking bubble.
        t_sp = 3.0 + DISPATCH_HOLD + DISPATCH_OUT + 0.15
        s_nv_d.handle({"state": "speaking", "level": 0.6}, t_sp)
        s_nv_d.handle({"send": [{"id": "n3", "name": "Late send", "outcome": "pending"}]}, t_sp + 0.05)
        s_nv_d.step(t_sp + 0.1)
        assert s_nv_d.dispatch is None and pack_player.map_overlay_state(s_nv_d) == "speaking"
        # 7) User packs in scratch $XDG_CONFIG_HOME/rook/themes/: valid pack inherits base=nova; broken falls back to devs.
        with tempfile.TemporaryDirectory(prefix="rook_user_pack_") as utmp:
            old_xdg = os.environ.get("XDG_CONFIG_HOME")
            os.environ["XDG_CONFIG_HOME"] = utmp
            try:
                u_good = os.path.join(utmp, "rook", "themes", "nova-custom")
                os.makedirs(os.path.join(u_good, "baked"), exist_ok=True)
                # Copy one real Nova atlas + json as a custom think icon
                nova_dir = os.path.join(pack_player.THEMES_DIR, "nova", "baked")
                shutil.copyfile(os.path.join(nova_dir, "star.webp"), os.path.join(u_good, "baked", "orbit.webp"))
                star_meta = json.loads(open(os.path.join(nova_dir, "star.json")).read())
                star_meta["image"] = "baked/orbit.webp"
                open(os.path.join(u_good, "baked", "orbit.json"), "w").write(json.dumps(star_meta))
                open(os.path.join(u_good, "manifest.json"), "w").write(json.dumps({
                    "name": "nova-custom", "title": "Nova Custom", "format": 1, "kind": "flipbook", "base": "nova",
                    "icons": {"orbit": {"src": "icons/orbit.glsl", "think": True}}, "states": {},
                }))
                assert "nova-custom" in pack_player.list_packs()
                upack = pack_player.validate_pack("nova-custom")
                assert "orbit" in upack["icons"] and upack["icons"]["orbit"]["_image_path"].startswith(u_good)
                assert upack["icons"]["rest"]["_image_path"].startswith(os.path.join(pack_player.THEMES_DIR, "nova"))
                fp_u = pack_player.FlipbookPresence(upack)
                assert "orbit" in fp_u.thinkers
                # Broken user pack (missing atlas) -> refused and Scene falls back to devs
                u_bad = os.path.join(utmp, "rook", "themes", "nova-broken")
                os.makedirs(u_bad, exist_ok=True)
                open(os.path.join(u_bad, "manifest.json"), "w").write(json.dumps({
                    "name": "nova-broken", "format": 1, "kind": "flipbook", "base": "nova",
                    "icons": {"ghost": {"image": "baked/ghost.webp"}}, "states": {},
                }))
                s_ub = Scene(0.0)
                s_ub.set_pack("nova-broken", 0.0)
                assert s_ub.pack_name == "devs" and s_ub.pack_kind == "points"
                # Hostile user packs: absolute image path, symlinked pack folder, escaping atlas symlink, 60000x60000 header bomb.
                u_abs = os.path.join(utmp, "rook", "themes", "nova-abs")
                os.makedirs(u_abs, exist_ok=True)
                open(os.path.join(u_abs, "manifest.json"), "w").write(json.dumps({
                    "name": "nova-abs", "format": 1, "kind": "flipbook", "base": "nova",
                    "icons": {"x": {"image": os.path.join(nova_dir, "star.webp"), "frames": 1, "fps": 12, "grid": [1, 1], "cell": 256}},
                    "states": {},
                }))
                s_ub.set_pack("nova-abs", 0.0)
                assert s_ub.pack_name == "devs"
                ext_dir = os.path.join(utmp, "outside_pack")
                os.makedirs(ext_dir, exist_ok=True)
                open(os.path.join(ext_dir, "manifest.json"), "w").write(json.dumps({
                    "name": "nova-link", "format": 1, "kind": "flipbook", "base": "nova", "icons": {}, "states": {},
                }))
                os.symlink(ext_dir, os.path.join(utmp, "rook", "themes", "nova-link"))
                assert "nova-link" not in pack_player.list_packs()
                s_ub.set_pack("nova-link", 0.0)
                assert s_ub.pack_name == "devs"
                u_sym = os.path.join(utmp, "rook", "themes", "nova-sym-img")
                os.makedirs(os.path.join(u_sym, "baked"), exist_ok=True)
                os.symlink(os.path.join(nova_dir, "star.webp"), os.path.join(u_sym, "baked", "x.webp"))
                open(os.path.join(u_sym, "manifest.json"), "w").write(json.dumps({
                    "name": "nova-sym-img", "format": 1, "kind": "flipbook", "base": "nova",
                    "icons": {"x": {"image": "baked/x.webp", "frames": 1, "fps": 12, "grid": [1, 1], "cell": 256}},
                    "states": {},
                }))
                s_ub.set_pack("nova-sym-img", 0.0)
                assert s_ub.pack_name == "devs"
                u_bomb = os.path.join(utmp, "rook", "themes", "nova-bomb")
                os.makedirs(os.path.join(u_bomb, "baked"), exist_ok=True)
                # Minimal 24-byte PNG IHDR claiming 60000 x 60000 (~14.4 GB uncompressed RGBA) -> refused before decode.
                bomb_hdr = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + (60000).to_bytes(4, "big") + (60000).to_bytes(4, "big") + b"\x08\x06\x00\x00\x00"
                open(os.path.join(u_bomb, "baked", "bomb.png"), "wb").write(bomb_hdr)
                open(os.path.join(u_bomb, "manifest.json"), "w").write(json.dumps({
                    "name": "nova-bomb", "format": 1, "kind": "flipbook", "base": "nova",
                    "icons": {"bomb": {"image": "baked/bomb.png", "frames": 1, "fps": 12, "grid": [1, 1], "cell": 256}},
                    "states": {},
                }))
                s_ub.set_pack("nova-bomb", 0.0)
                assert s_ub.pack_name == "devs"
                # A dust pack's own form comes first in the thinking rotation, after the rook. Each bad file is
                # refused in one sentence, and its icon keeps the built-in forms.
                u_dust = os.path.join(utmp, "rook", "themes", "dust-mine")
                os.makedirs(os.path.join(u_dust, "forms"))
                rows = [[30 * math.cos(k), 40 * math.sin(k / 2), 10.0] for k in range(640)]

                def dust_pack(icons):
                    open(os.path.join(u_dust, "manifest.json"), "w").write(json.dumps({
                        "name": "dust-mine", "format": 1, "kind": "points", "base": "devs", "states": {},
                        "icons": {icon: {"form": form, "think": True} for icon, form in icons.items()}}))
                    return pack_player.pack_forms(pack_player.load_pack("dust-mine", reload=True))

                files = {"good": rows, "few": rows[1:], "wide": rows[1:] + [[0, 63, 0]], "word": rows[1:] + [[0, "x", 0]],
                         "four": rows[1:] + [[0, 0, 0, 1]], "huge": rows[1:] + [[0, 10 ** 400, 0]],
                         "nan": rows[1:] + [[0, float("nan"), 0]], "big": " " * 70000 + "[]",
                         "deep": "[" * 30000 + "]" * 30000, "gone": None}
                for icon, data in files.items():
                    if data is not None:
                        open(os.path.join(u_dust, "forms", f"{icon}.json"), "w").write(
                            data if isinstance(data, str) else json.dumps(data))
                for icon in [*files, "out"]:
                    forms, problems = dust_pack({icon: "../nova-custom/manifest.json" if icon == "out" else
                                                 f"forms/{icon}.json"})
                    assert (list(forms) == ["pack:dust-mine/good"] and not problems if icon == "good" else
                            not forms and len(problems) == 1 and problems[0].count(". ") == 1
                            and problems[0].endswith(".")), (icon, problems)
                # At most MAX_PACK_FORMS forms are read, and the rest get one sentence.
                forms, problems = dust_pack({f"x{k}": "forms/good.json" for k in range(9)})
                assert len(forms) == pack_player.MAX_PACK_FORMS and len(problems) == 1, problems
                # Broken files do not count toward the cap. An icon with no .json form gets one sentence, and a name
                # with control characters is printed safely.
                forms, problems = dust_pack({**{f"bad{k}": "forms/few.json" for k in range(3)},
                                             **{f"x{k}": "forms/good.json" for k in range(5)}})
                assert len(forms) == 4 and len(problems) == 4, problems
                forms, problems = dust_pack({"named": "rook", "evil\x1b[2J": "forms/few.json"})
                assert not forms and len(problems) == 2 and not any("\x1b" in p for p in problems), problems
                # A reload with the same refusals, as on every settings change, does not say them again.
                import contextlib
                said = io.StringIO()
                with contextlib.redirect_stderr(said):
                    s_n = Scene(0.0)
                    assert s_n.set_pack("dust-mine", 0.0) and s_n.set_pack("dust-mine", 1.0)
                assert said.getvalue().count("keeps the built-in forms") == 2, said.getvalue()
                dust_pack({"good": "forms/good.json"})
                s_d, shown = Scene(0.0), None
                assert s_d.set_pack("dust-mine", 0.0) and s_d.pack_name == "dust-mine"
                assert s_d.think_forms == ("pack:dust-mine/good", *devs_pack.THINK_OTHERS)
                s_d.handle({"state": "thinking"}, 0.0)
                for k in range(int(THINK_TURN * 2 * len(s_d.think_forms) * 4) + 4):
                    s_d.step(k / 4)
                    shown = k / 4 if shown is None and s_d.form == "pack:dust-mine/good" else shown
                assert shown == THINK_TURN and s_d.pack_name == "dust-mine", shown
                tx, ty, _ = s_d._form_targets("pack:dust-mine/good", 0.0)
                assert len(tx) == GRAINS and max(map(abs, ty)) > 30, (len(tx), max(map(abs, ty)))
                # A flat form, even one set to spin fast, sways and never turns edge-on: over a whole sway it keeps
                # at least 90% of its settled width.
                SPIN["pack:dust-mine/good"], settled = 2.0, max(tx) - min(tx)
                for k in range(64):
                    tx, _, _ = s_d._form_targets("pack:dust-mine/good", k * math.pi / 64)
                    assert max(tx) - min(tx) >= 0.9 * settled, (k, max(tx) - min(tx), settled)
                # Rook sends the theme again on every settings change: the same pack reads its forms again.
                dust_pack({"good": "forms/good.json", "again": "forms/good.json"})
                assert s_d.set_pack("dust-mine", 30.0)
                assert s_d.think_forms[:2] == ("pack:dust-mine/good", "pack:dust-mine/again"), s_d.think_forms
                # Back on Devs, the pack's forms are dropped, but for one still on screen.
                s_d.set_pack("devs", 30.0)
                assert s_d.think_forms == devs_pack.THINK_OTHERS
                assert set(_DATA_FORMS) <= {s_d.form, s_d.prev}, (set(_DATA_FORMS), s_d.form, s_d.prev)
            finally:
                if old_xdg is None:
                    os.environ.pop("XDG_CONFIG_HOME", None)
                else:
                    os.environ["XDG_CONFIG_HOME"] = old_xdg
        # Verify expiration clears dispatch cleanly back to idle (zero cost)
        assert not sd.dispatch_active(10.0) and sd.dispatch is None
    finally:
        _use_theme("light" if saved_pal is THEMES["light"] else "dark")
    print("dispatch fan & CP7 nova notes (anchors/60fps/search/user-packs): ok")

    # The send forms: each builds with GRAINS grains; sends take them in turn; the strands leave their ports; and a
    # frame of either costs well under 1.5 ms of Python. The whole send: from a thinking form a clean flight into the
    # loop, the staged assembly, the strands with the device until the teardown, the gather into the centre, then the
    # next form, never the loop or a lone device. The device stays on the presence's centre, and nothing jumps.
    assert devs_pack.SEND_LOOP_FLOW == 2 * math.pi / LOOP_PERIOD
    assert set(devs_pack.ICONS["cascade"]["cycle"]) == set(devs_pack.SEND_FORMS) == set(SEND_CYCLE)
    three = [{"id": f"x{i}", "name": name, "outcome": "pending"} for i, name in enumerate(("Lark", "Harbor", "Ferns"))]
    ss, t_s, sent, cost = Scene(0.0), 0.0, [], {}

    def device_centre(form, now):
        """The device's own centre at this pose, from the grains' own records: the mean of every part's place as drawn,
        as if all had arrived."""
        place, _, m = devs_pack._send_device(form, now - ss.form_at, now, math.inf)
        ox, oy = devs_pack._send_centre(form, now - ss.form_at)
        xs, ys = [], []
        for rec in _form(form):
            x, y, z, _ = place(rec)
            q = 1.0 / (1.0 - (m[6] * x + m[7] * y + m[8] * z) / 320.0)
            xs.append((m[0] * x + m[1] * y + m[2] * z) * q)
            ys.append((m[3] * x + m[4] * y + m[5] * z) * q)
        return sum(xs) / GRAINS - ox, sum(ys) / GRAINS - oy

    for n_send in range(4):
        ss.handle({"state": "thinking"}, t_s)
        t_f = t_s
        while t_f < t_s + 1.5:  # A settled thinking form, so the send starts from it.
            t_f += 1 / 60
            ss.step(t_f)
        assert ss.form not in (*devs_pack.SEND_FORMS, "loop"), ss.form
        ss.handle({"state": "thinking", "activity": "t3_thread_send"}, t_f)
        ss.handle({"send": [dict(row, id=f"{row['id']}-{n_send}") for row in three]}, t_f)
        assert {r["side"] for r in ss.dispatch.rows} == {1.0, -1.0}, "The targets do not show on both sides."
        frames, t_go, looped, fired = [], t_f, 0, None
        last_x, last_y, last_t = list(ss.x), list(ss.y), None
        while t_f < t_go + 3.9:
            t_f += 1 / 60
            ss.step(t_f)
            form = ss.form
            assert form in devs_pack.SEND_FORMS, form
            started = time.perf_counter()
            tx_s, ty_s, _ = ss._targets(form, t_f)
            devs_pack.send_ports(form, t_f - ss.form_at)
            frames.append((time.perf_counter() - started) * 1000.0)
            assert len(tx_s) == GRAINS == len(_form(form)) and all(map(math.isfinite, tx_s + ty_s))
            T, y_off = t_f - ss.form_at, ss.dispatch_y_offset()
            if 0.45 < T < devs_pack.SEND_MORPH:  # The loop shows before the assembly: every grain's place is on it.
                looped += 1
                for i, rec in enumerate(_form(form)):
                    a = rec[0] + T * devs_pack.SEND_LOOP_FLOW
                    assert abs(tx_s[i] - 60.0 * math.sin(a)) < 1e-6, (form, "not on the loop before the assembly")
                    assert abs(ty_s[i] - y_off - 52.0 * math.sin(a) * math.cos(a)) < 1e-6, form
            dcx, dcy = device_centre(form, t_f)
            assert math.hypot(dcx, dcy) < 1.0, (form, T, dcx, dcy)  # On the presence's centre, the whole send.
            if T > devs_pack.SEND_LOCK + 0.2:  # Every grain has arrived: what is drawn sits on the centre too.
                assert math.hypot(sum(tx_s) / GRAINS, sum(ty_s) / GRAINS - y_off) < 1.0, (form, T)
            jump = max(math.hypot(ss.x[i] - last_x[i], ss.y[i] - last_y[i]) for i in range(GRAINS))
            assert jump < 16.0, (form, T, jump)  # A spring flight at 60 Hz moves at most about 11 px a frame.
            if last_t is not None:  # No place pops: the assembly moves each target smoothly from frame to frame.
                pop = max(math.hypot(tx_s[i] - last_t[0][i], ty_s[i] - last_t[1][i]) for i in range(GRAINS))
                assert pop < 9.0, (form, T, pop)
            last_x, last_y, last_t = list(ss.x), list(ss.y), (tx_s, ty_s)
            if ss.dispatch_gl_rows(t_f):
                fired = fired or T
            elif fired:
                raise AssertionError(f"{form}: the device showed without its strands at {T:.2f} s")
        assert looped >= 5 and fired, (looped, fired)
        sent.append(form)
        cost.setdefault(form, []).extend(frames)
        # Held: each strand starts at its side's port, and the port is the centre of the drawn nozzle mouth or emitter.
        ports = ss.dispatch.ports
        assert ports == devs_pack.send_ports(form, t_f - ss.form_at)
        for row in ss.dispatch.rows:
            assert ss.dispatch.row_path(row)[:2] == ports[1 if row["side"] > 0 else -1]
        y_off = ss.dispatch_y_offset()
        for side in (1, -1):
            if form == "send_turbine":
                mouth = [i for i, rec in enumerate(_form(form)) if rec[3] == 1 and rec[5] == side * 14.0]
            else:
                mouth = [i for i, rec in enumerate(_form(form)) if rec[3] == 2 and rec[4] == side]
            mx = sum(tx_s[i] for i in mouth) / len(mouth)
            my = sum(ty_s[i] - y_off for i in mouth) / len(mouth)
            assert math.hypot(mx - ports[side][0], my - ports[side][1]) < 1.5, (form, side, mx, my, ports[side])
        # Every send lands and the fan leaves while the turn still thinks on the send activity. The strands draw back
        # into the ports as the ports and the device gather into the centre; then the turn's thinking form follows.
        ss.handle({"send": [{"id": f"{row['id']}-{n_send}", "outcome": "landed"} for row in three]}, t_f)
        held_reach = abs(ports[1][0])
        t_end, pulled_in, after, gathered, repeated = ss.dispatch.t0 + ss.dispatch.total, False, 0, None, False
        while t_f < t_end + 1.5:
            t_f += 1 / 60
            ss.step(t_f)
            if ss.dispatch is not None:
                assert ss.form == form
                if not ss.dispatch_leaving(t_f):
                    assert ss.dispatch_gl_rows(t_f), f"{form}: the strands left before the teardown"
                elif not repeated:  # The same outcome again, mid-teardown, does not reopen the fan.
                    repeated, total = True, ss.dispatch.total
                    ss.handle({"send": [{"id": f"{row['id']}-{n_send}", "outcome": "landed"} for row in three]}, t_f)
                    assert ss.dispatch.total == total and ss.dispatch_leaving(t_f), "a late outcome reopened the fan"
                if ss.send_clock(t_f)[1] > 0.6:
                    pulled_in = pulled_in or abs(ss.dispatch.ports[1][0]) < 0.5 * held_reach
                y_off = ss.dispatch_y_offset()
                gathered = sorted(math.hypot(ss.x[i], ss.y[i] - y_off) for i in range(GRAINS))[GRAINS * 9 // 10]
            else:
                after += 1
                assert ss.form not in (*devs_pack.SEND_FORMS, "loop"), (form, ss.form, "after the fan")
                assert ss.label_text(t_f) == LABELS["thinking"], ss.label_text(t_f)  # The label follows the form.
        # Nine grains in ten lie near the centre as the next form starts (a few always slip loose).
        assert gathered is not None and gathered < 10.0, (form, gathered)
        assert pulled_in and repeated and after > 60 and ss.state == "thinking", (pulled_in, after, ss.form)
        ss.handle({"state": "speaking"}, t_f + 0.1)
        ss.step(t_f + 0.15)
        assert ss.dispatch is None and ss.form not in devs_pack.SEND_FORMS
        t_s = t_f + 1.0
    assert sent[0] != sent[1] and sent[2:] == sent[:2] and set(sent) == set(devs_pack.SEND_FORMS), sent
    # The send tool starts at 2 s and its fan comes at 7 s: no device before the fan, then the whole sequence.
    sl, t_l = Scene(0.0), 0.0
    sl.handle({"state": "thinking"}, 0.0)
    sl.handle({"activity": "t3_thread_send"}, 2.0)
    while t_l < 7.0:
        t_l += 1 / 60
        sl.step(t_l)
        assert sl.form not in devs_pack.SEND_FORMS, (t_l, sl.form, "a lone device before the fan")
    assert sl.label_text(t_l) == ACTIVITY_LABELS["t3_thread_send"]
    sl.handle({"send": [{"id": "late", "name": "Lark", "outcome": "pending"}]}, t_l)
    sl.step(t_l + 1 / 60)
    assert sl.form in devs_pack.SEND_FORMS and sl.form_at == t_l + 1 / 60
    assert sl.dispatch.rows[0]["begin"] >= devs_pack.SEND_FIRE - 0.02  # The strands wait for the assembly.
    for form, frames in cost.items():
        mean = sum(frames) / len(frames)
        print(f"{form}: {GRAINS} grains, {mean:.2f} ms mean, {max(frames):.2f} ms max per frame of Python")
        assert mean < 1.5, (form, mean)  # About 0.5 ms quiet; room for a loaded desktop.
    _check_send_motion()
    # The window grows for a fan and shrinks after it. While GTK still has the old width laid out, the presence keeps
    # its place: its x in the window, less the area's, centred in the window (Overlay._canvas_cx).
    win = types.SimpleNamespace(_dispatch_cx=None, _win_width=WIDTH, _centred=False,
                                column=types.SimpleNamespace(get_width=lambda: 1400))
    assert Overlay._canvas_cx(win, 1400) == WIDTH / 2  # Shrunk, the margin moved, the old wide frame: still in place.
    win.column.get_width = lambda: WIDTH
    win._dispatch_cx = WIDTH / 2  # Growing: the margin waits, so the presence stays at its old x in the window.
    assert Overlay._canvas_cx(win, ORB_W) == ORB_W / 2
    _check_send_window()
    _check_send_window_gl()
    print("send forms (640 grains, cycle, ports, fan ends): ok")
    _check_lettering()
    _check_card()
    # The onboarding guide: it shows, turns into the listening line on the first listen, and clears when that listen
    # ends; null clears it, "seconds" ends it, and dark hides it. Drawn once at home and once in a turn.
    key = {"guide": {"text": "Hold Right Alt to answer", "until": "listening"}}
    g = _simulate([(0.0, {"state": "ready"}), (0.1, key)], 1.0)[0]
    assert g.guide_shown == ("Hold Right Alt to answer", "", True) and g.guide_alpha == 1.0, g.guide_shown
    sheet = cairo.ImageSurface(cairo.FORMAT_ARGB32, WIDTH, 400)
    g.draw_swarm(cairo.Context(sheet), WIDTH, 1.0, g.lift)
    g = _simulate([(0.0, {"state": "ready"}), (0.1, key), (1.0, {"state": "listening"})], 2.0)[0]
    assert g.guide_shown == (GUIDE_LISTENING, "", False), g.guide_shown
    g.draw_guide(cairo.Context(sheet), WIDTH / 2, g.guide_y, False)
    g = _simulate([(0.0, {"state": "ready"}), (0.1, key), (1.0, {"state": "listening"}),
                   (2.0, {"state": "transcribing"}), (2.5, {"state": "ready"})], 3.0)[0]
    assert g.guide is None and g.guide_shown is None and g.guide_key() is None
    g = _simulate([(0.0, {"state": "ready"}), (0.1, key), (1.0, {"guide": None})], 2.0)[0]
    assert g.guide is None and g.guide_shown is None
    code = {"guide": {"code": "482 913", "text": "Open Rook on your phone and enter this code", "seconds": 2}}
    g = _simulate([(0.0, {"state": "ready"}), (0.1, code)], 2.0)[0]
    assert g.guide_shown == ("Open Rook on your phone and enter this code", "482 913", True)
    g = _simulate([(0.0, {"state": "ready"}), (0.1, code)], 2.5)[0]
    assert g.guide is None and g.guide_shown is None
    g = _simulate([(0.0, {"state": "ready"}), (0.1, key), (0.5, {"dark": True})], 1.5)[0]
    assert g.guide is not None and g.guide_shown is None
    # A bool or endless "seconds" sets no end; the text and code are cut to fit; a send fan keeps the guide in the turn.
    for seconds in (True, math.nan, math.inf, "9"):
        g.handle({"guide": {"text": "W" * 200, "code": "WMW MWM WMW MWM", "seconds": seconds}}, 2.0)
        assert g.guide["ends"] == math.inf and len(g.guide["text"]) == 75 and g.guide["code"] == "WMW MWM WMW", seconds
    g.handle({"dark": False}, 2.0)
    g.step(3.0)
    assert g.guide_shown[2] and g.guide_w <= WIDTH - 2 * GUIDE_MARGIN, g.guide_w
    g.dispatch_active = lambda now=None: True
    g._step_guide(3.5, 0.1)
    assert g.guide_shown is not None and not g.guide_shown[2]
    # The worst case in a turn: the widest code (server.py's alphabet) under a two-line caption. The guide sits clear
    # of the caption, fits the width, and stays 24 px above the bottom of the grown caption area.
    words = "Open Rook on your phone, then type the six letters and numbers you see under me."
    widest = {"guide": {"code": "WMW MWM", "text": "Open Rook on your phone and enter this code", "seconds": 600}}
    g = _simulate([(0.0, {"state": "ready"}), (0.1, widest), (0.5, {"state": "speaking", "caption": words,
                                                                     "seconds": 3})], 3.9)[0]

    def ink(paint):  # The first and last rows and columns that paint draws, in an area as tall as the grown one.
        area = cairo.ImageSurface(cairo.FORMAT_ARGB32, WIDTH, CAPTION_H + GUIDE_ROOM)
        paint(cairo.Context(area))
        data, stride = bytes(area.get_data()), area.get_stride()
        rows = [y for y in range(area.get_height()) if any(data[y * stride + 3:(y + 1) * stride:4])]
        cols = [x for x in range(WIDTH) if any(data[x * 4 + 3::stride])]
        return rows[0], rows[-1], cols[0], cols[-1]

    caption = ink(lambda cr: g.draw_caption(cr, WIDTH, 3.9))
    assert g.guide_y == GUIDE_BELOW and caption[1] - caption[0] > 50, caption  # Both caption lines are drawn.
    guide = ink(lambda cr: g.draw_guide(cr, WIDTH / 2, g.guide_y, False))
    assert caption[1] + 8 < guide[0] and guide[1] < CAPTION_H + GUIDE_ROOM - 24 and 0 < guide[2] < guide[3] < WIDTH - 1, (
        caption, guide)
    print("onboarding guide (shows, listens, clears, expires, dark, caps, send fan, worst case): ok")
    global REST_LOOK
    default_look, REST_LOOK = REST_LOOK, "today"  # The comet checks below are today's look; the rest looks follow.
    # A quiet turn: Rook stays at rest with no label, form, or send fan, and only a comet lights the loop. Speaking
    # pulls it down, hidden leaves it at rest, a steer (quiet false) drops it down, and dark shows nothing.
    ready, quiet = (0.0, {"state": "ready"}), (0.5, {"state": "thinking", "quiet": True})
    plain = _simulate([ready], 2.0)[0]
    work = [ready, quiet, (0.6, {"activity": "WebSearch"}), (1.0, {"send": [{"id": "k1", "name": "Rook build"}]})]
    q = _simulate(work, 2.0)[0]
    assert q.home and q.form == "loop" and q.label_text(2.0) == "" and q.dispatch is None and q.quiet_mix == 1.0
    assert (q.x, q.y) == (plain.x, plain.y), "a quiet turn moved the grains"
    lit = [b / a for a, b in zip(plain.depth, q.depth)]
    top = max(range(GRAINS), key=lit.__getitem__)
    gap = (_form("loop")[top][0] + 2.0 * 2 * math.pi / LOOP_PERIOD - 2.0 * 2 * math.pi / QUIET_LAP + math.pi) % (
        2 * math.pi) - math.pi
    assert min(lit) > 1.07 and lit[top] > 1.75 and abs(gap) < 0.1, (min(lit), lit[top], gap)
    for end, home in (({"state": "speaking"}, False), ({"state": "hidden"}, True),
                      ({"state": "thinking", "quiet": False}, False)):
        q, ref = _simulate(work, 2.0)[0], _simulate([ready], 2.0)[0]  # ref: the same end with no quiet turn before.
        q.handle(end, 2.0)
        ref.handle(end, 2.0)
        for t in (2.1, 2.2, 2.3, 2.35, 2.6):
            was = q.quiet_mix
            q.step(t)
            ref.step(t)
            assert q.quiet_mix < was or t == 2.6, (end, t, q.quiet_mix)  # A fade, not a snap.
        assert q.quiet_mix == 0.0 and q.home == home and (q.form == "loop") == home, (end, q.form)
        assert not home or (q.x, q.y) == (ref.x, ref.y), "a pass moved the grains"
    q = _simulate([ready, (0.5, {"state": "thinking", "quiet": False})], 2.0)[0]
    assert not q.home and q.form != "loop" and q.label_text(2.0) == "THINKING" and q.quiet_mix == 0.0
    q = _simulate([ready, (0.2, {"dark": True}), quiet], 2.0)[0]
    assert q.home and q.quiet_mix == 0.0  # At rest while dark, so the window shows nothing (see _should_show).
    print("quiet turn (parked, comet, no label, activity or fan; speaking, pass, steer, normal, dark): ok")
    # The resting loop's look: "today" never dims. Every other look dims the rest with flecks at today's light, lifts a
    # quiet turn to its level under a glare lap, falls back to rest when it ends, and lights fully for a turn at once.
    # It changes brightness only, never a grain's place.
    saved, work = default_look, [ready, (5.0, {"state": "thinking", "quiet": True})]
    try:
        REST_LOOK = "today"
        today, calm = {t: _simulate(work, t)[0] for t in (4.9, 8.0)}, _simulate([ready], 8.0)[0]
        assert all(s.rest_dim == s.glare_mix == 0.0 for s in today.values())
        for name, look in REST_LOOKS.items():
            if not look:
                continue
            REST_LOOK = name
            rest, quiet = _simulate(work, 4.9)[0], _simulate(work, 8.0)[0]
            for s, ref in ((rest, today[4.9]), (quiet, today[8.0])):
                assert (s.x, s.y) == (ref.x, ref.y), (name, "a look moved the grains")
            assert rest.rest_dim == 1.0 and rest.glare_mix == 0.0 and quiet.glare_mix == 1.0, name
            flecks = [i for i in range(GRAINS) if (i * 2654435761 & 0xFFFFFFFF) % 100 < look["flecks"]]
            plain = [i for i in range(GRAINS) if (i * 2654435761 & 0xFFFFFFFF) % 100 >= max(12, look["flecks"])]
            assert all(abs(rest.depth[i] / today[4.9].depth[i] - look["dim"]) < 1e-6 for i in plain), name
            assert min(rest.depth[i] / today[4.9].depth[i] for i in flecks) > 0.44, name
            lit = max(range(GRAINS), key=lambda i: quiet.depth[i] / calm.depth[i])  # Over the loop with no comet.
            gap = (_form("loop")[lit][0] + 8.0 * 2 * math.pi / LOOP_PERIOD - 8.0 * 2 * math.pi / look["lap"]
                   + math.pi) % (2 * math.pi) - math.pi
            assert abs(gap) < look["band"] / 2, (name, gap)  # The brightest grain is at the band's centre.
            done = _simulate(work + [(8.0, {"state": "ready"})], 8.0 + REST_FALL + 0.1)[0]
            assert done.glare_mix == 0.0 and done.rest_dim == 1.0, name
            turn = _simulate(work, 6.0)[0]
            turn.handle({"state": "speaking"}, 6.0)
            for t in (6.1, 6.2, 6.25):  # REST_OUT is 0.2 s.
                turn.step(t)
            assert turn.rest_dim == turn.glare_mix == 0.0, name
    finally:
        REST_LOOK = saved
    print(f"resting looks ({', '.join(n for n in REST_LOOKS if n != 'today')}: brightness only, "
          "flecks, glare, fall back, wake): ok")
    print("render scenes in the engine: ok")


def _check_send_window():
    """A send frame by frame, for one and three targets. Each strand's head fades as it lands, and only then does its
    name's reveal play, in full, with grains. The device never shows without its strands from the fire to the teardown.
    By the window model (Overlay._size_canvas and _canvas_cx, GTK's layout, and the compositor placing the layer in the
    commit GTK draws), the presence never moves more than 1 px between frames or leaves its area: in the window the
    compositor centres with GTK's layout on time or a frame late, and in a left-anchored one with it on time."""
    saved_pal, saved_margin = PALETTE, LayerShell.set_margin
    _use_theme("dark")
    lit_map = bytes(1 if b > 40 else 0 for b in range(256))
    try:
        for n in (1, 3):
            sent = [{"id": f"w{k}", "name": name} for k, name in enumerate(("Opus", "Harbor", "Lark")[:n])]
            sc, t = Scene(0.0), 0.0
            script = [(0.0, {"state": "thinking"}), (2.0, {"activity": "t3_thread_send"}), (2.0, {"send": sent}),
                      (4.6, {"send": [{"id": row["id"], "outcome": "landed"} for row in sent]})]
            cx, cy, surf = 626.0, 60.0, cairo.ImageSurface(cairo.FORMAT_ARGB32, 1252, 120)
            seen = [{"head": [], "dark": True, "landed": None, "grains": [], "lit": []} for _ in sent]
            while t < 7.0:
                while script and script[0][0] <= t:
                    sc.handle(script.pop(0)[1], t)
                sc.step(t)
                ds = sc.dispatch if sc.dispatch_active(t) else None
                assert sc.form not in devs_pack.SEND_FORMS or ds is not None, (n, t, "the device without its fan")
                if ds is None or ds.leaving(t):
                    t += 1 / 60
                    continue
                strands = ds.eval_gl_rows(t, 0.0)
                if t - ds.t0 >= ds.rows[0]["begin"]:
                    assert sc.form in devs_pack.SEND_FORMS and strands, (n, t, "the device or its strands missing")
                cr = cairo.Context(surf)
                cr.set_operator(cairo.OPERATOR_CLEAR)
                cr.paint()
                ds.draw_overlay(cr, cx, cy, t, 5120.0, PALETTE)  # Letters the names too, as a draw does.
                surf.flush()
                data, stride, grains = bytes(surf.get_data()), surf.get_stride(), ds.reveal_rows(t, 0.0)
                for row, got in zip(ds.rows, seen):
                    side, ex, ry = row["side"], cx + row["ex"], cy + row["y_off"]
                    head = ds._row_timing(row, t - ds.t0)[0]
                    if head < 1.0:  # In flight: its head (radius 14) is where the path puts it, and its name is dark.
                        hx, hy = ds._at3(ds.row_path(row), head)
                        got["head"] += [strands[i + 2] for i in range(0, len(strands), 11) if strands[i + 6] > 8.0
                                        and abs(strands[i] - hx) < 0.01 and abs(strands[i + 1] - hy) < 0.01]
                    elif got["landed"] is None:
                        got["landed"] = t
                    x0 = int(ex + DISPATCH_GAP - 3) if side > 0 else int(ex - DISPATCH_GAP - 200)
                    lit = sum(sum(data[y * stride + x0 * 4 + 3:y * stride + (x0 + 203) * 4:4].translate(lit_map))
                              for y in range(int(ry - 12), int(ry + 12)))
                    mine = sum(1 for i in range(0, len(grains), 11) if (grains[i] > 0) == (side > 0)
                               and abs(grains[i + 1] - row["y_off"]) < 12.0)
                    if got["landed"] is None:
                        got["dark"] = got["dark"] and lit == 0 and mine == 0
                    else:
                        got["grains"].append((t - got["landed"], mine))
                        got["lit"].append((t - got["landed"], lit))
                t += 1 / 60
            for k, got in enumerate(seen):
                assert got["dark"] and got["landed"] is not None, (n, k, "a name showed before its strand landed")
                assert got["head"] and got["head"][-1] < 0.05, (n, k, "the strand's head popped", got["head"][-3:])
                assert all(m > 0 for dt, m in got["grains"] if dt < 0.3), (n, k, "the reveal has no grains")
                assert not [m for dt, m in got["grains"] if dt > REVEAL_SECONDS + 0.02 and m], (n, k, "grains stay")
                full = max(lit for dt, lit in got["lit"] if dt > REVEAL_SECONDS)
                assert got["lit"][0][1] < 0.25 * full, (n, k, "the name appeared at once", got["lit"][:3], full)

        # One strand on its own: tied to its port all through the flight, and no jump, dimming or stop as it lands.
        cx, cy = 626.0, 60.0
        ds = DispatchState([{"id": "s", "name": "Opus", "outcome": "landed"}], 0.0)
        row = ds.rows[0]
        path, land = ds.row_path(row), row["begin"] + DISPATCH_TRAVEL
        span = path[6] - path[0]

        def strand(t):  # Each grain's x as a share of the strand's length, and its alpha.
            r = ds.eval_gl_rows(t, 0.0)
            return [((r[i] - path[0]) / span, r[i + 2]) for i in range(0, len(r), 11) if r[i + 6] < 8.0]
        t = row["begin"]
        while t < land:
            head = ds._row_timing(row, t)[0]
            if head >= 0.40:
                us, hx = [u for u, _ in strand(t)], (ds._at3(path, head)[0] - path[0]) / span
                assert min(us) < 0.25 and max(us) > hx - 0.1, (t, head, min(us), max(us), "a strand left its port")
            t += 1 / 60
        before, after = strand(land - 1 / 60), strand(land + 1 / 60)
        mid = [sum(u for u, _ in g) / len(g) for g in (before, after)]
        glow = [sum(a for _, a in g) / len(g) for g in (before, after)]
        assert abs(mid[1] - mid[0]) < 0.10 and 0.65 < glow[1] / glow[0] < 1.55, (mid, glow, "the strand jumped")
        assert 0.8 < len(after) / len(before) < 1.25, (len(before), len(after), "the strand's grains jumped")
        # The name's first reveal frame has grains before any draw has lettered it.
        assert LETTERING and ds.reveal_rows(land + 1 / 60, 0.0), "no grains on the reveal's first frame"

        assert _glint(0.0) == 0.0, "the glint shows before the strand lands"

        class _Snap:  # Keeps the alpha stops of each mask append_gl_overlay builds, and counts its sprites.
            def __init__(self):
                self.masks, self.sprites = [], 0

            def append_linear_gradient(self, _rect, _start, _end, stops):
                self.masks.append([stop.color.alpha for stop in stops])

            def append_texture(self, *_args):
                self.sprites += 1

            def __getattr__(self, _name):
                return lambda *_args: None

        def masks(state, times):
            seen = []
            for t in times:
                snap = _Snap()
                state.append_gl_overlay(snap, cx, cy, 1252.0, t, 5120.0, 1.0, PALETTE)
                assert len(snap.masks) == 1, (t, "no reveal mask")
                m = snap.masks[0]
                assert all(a >= b - 1e-9 for a, b in zip(m, m[1:])), (t, m, "the mask runs the wrong way")
                seen.append(sum(m) / len(m))
            return seen
        shown = masks(ds, [land + dt for dt in (0.1, 0.2, 0.3)])
        assert shown[0] < shown[1] < shown[2], ("the name does not reveal", shown)
        gone = masks(ds, [ds.end_at + DISPATCH_OUT * k for k in (0.20, 0.30, 0.40, 0.55)])
        assert all(a > b for a, b in zip(gone, gone[1:])) and gone[-1] < 0.5 * gone[0], ("no reverse mask", gone)
        # A narrower room letters the name anew, for the reveal's grains and the sprite alike.
        long_row = DispatchState([{"id": "l", "name": "Harbor lights on the north pier"}], 0.0)
        lr = long_row.rows[0]
        long_row._rooms = (DISPATCH_MAX_W, DISPATCH_MAX_W)
        wide = long_row._row_geometry(lr, DISPATCH_MAX_W)
        long_row._rooms = (90.0, 90.0)
        t_l = lr["begin"] + DISPATCH_TRAVEL + 0.1
        narrow = long_row._lettered_name(lr, 90.0, 1.0)[1]
        assert narrow is long_row._row_geometry(lr, 90.0) and narrow is not wide, "stale name geometry"
        assert long_row.reveal_rows(t_l, 0.0) == _reveal_rows(narrow, long_row._reveal_at(lr, t_l), "left",
                                                              *_name_spot(lr, narrow, lr["ex"], lr["y_off"]))

        # A teardown asked for before the strand lands waits until the name has landed and shown for
        # DISPATCH_MIN_SHOW (the owner, 2026-11-25: stay on screen a beat longer), so the name always gets its reveal.
        early = DispatchState([{"id": "e", "name": "Opus", "project": "rook", "machine": "desk",
                                "outcome": "landed"}], 0.0)
        er = early.rows[0]
        early.leave(er["begin"] + DISPATCH_TRAVEL - 0.1)
        assert abs(early.end_at - (early.landed_at + DISPATCH_MIN_SHOW)) < 1e-6, (early.end_at, early.landed_at)
        assert early._reveal_at(er, early.landed_at + 0.3) >= 0.0, "the name never revealed before the teardown"
        # A teardown asked for mid-reveal waits out the show time, then the reveal only runs back from full.
        mid_r = DispatchState([{"id": "m", "name": "Opus", "outcome": "landed"}], 0.0)
        mr = mid_r.rows[0]
        mid_r.leave(mr["begin"] + DISPATCH_TRAVEL + 0.2)
        back = [min(REVEAL_SECONDS, mid_r._reveal_at(mr, mid_r.end_at + k / 60))
                for k in range(int(DISPATCH_OUT * 60) + 1)]
        assert all(a >= b - 1e-9 for a, b in zip(back, back[1:])), ("the reveal ran on", back[:4])

        # The window: one send on a 2000 px free area, its fan, the teardown and the next form. In the last two runs
        # Rook says thinking again mid-hold, as when a spoken line ends: the teardown still plays, never an instant end.
        free = 2000
        for centred, lag, again in ((True, 0, False), (True, 1, False), (False, 0, False), (True, 1, True),
                                    (False, 0, True)):
            sc, t = Scene(0.0), 0.0
            sc.monitor_width = float(free)
            script = [(0.0, {"state": "thinking"}), (1.0, {"activity": "t3_thread_send"}),
                      (1.0, {"send": [{"id": "w", "name": "Opus"}]}),
                      (2.0, {"send": [{"id": "w", "outcome": "landed"}]})]
            script += [(2.6, {"state": "thinking"})] if again else []
            requests, laid, margin, content = [WIDTH], [WIDTH], [(free - WIDTH) // 2], [ORB_W, 0]
            ov = types.SimpleNamespace(carry=None, flight=None, scene=sc, _centred=centred, _widen_to=None,
                                       _dispatch_cx=None, _win_width=WIDTH, left=margin[0], top=0,
                                       home_xy=(margin[0], 0), bounds=(0, 0, free, 1440), win=None)
            ov.column = types.SimpleNamespace(set_size_request=lambda w, _h: requests.append(w),
                                              get_width=lambda: laid[0])
            ov.area = types.SimpleNamespace(get_content_width=lambda: content[0], get_content_height=lambda: content[1],
                                            set_content_width=lambda w: content.__setitem__(0, w),
                                            set_content_height=lambda h: content.__setitem__(1, h))
            LayerShell.set_margin = lambda _w, _e, v: margin.__setitem__(0, v)
            xs, widths, grains, phases = [], set(), [], []
            while t < 7.5:  # Long enough for the hold, the teardown and the next form.
                while script and script[0][0] <= t:
                    sc.handle(script.pop(0)[1], t)
                sc.step(t)
                Overlay._size_canvas(ov, t)
                laid[0] = requests[-1] if lag == 0 else requests[-2] if len(requests) > 1 else requests[-1]
                requests.append(requests[-1])  # The width GTK has asked for as this frame ends.
                area_w = content[0]
                where = Overlay._canvas_cx(ov, area_w)
                layer = (free - laid[0]) / 2 if centred else margin[0]
                assert 0 <= where <= area_w, (centred, lag, t, where, area_w, "the presence left its area")
                xs.append(layer + (laid[0] - area_w) / 2 + where)
                # The viewer's box, captions and dust hang from _centre(): it stays on the presence as the margin moves.
                assert Overlay._centre(ov)[0] == xs[-1], (centred, t, Overlay._centre(ov), xs[-1])
                grains.append((laid[0], [xs[-1] + sc.x[i] for i in sc.idx]))  # Each grain's x on the screen.
                widths.add(laid[0])
                phases.append(None if not sc.dispatch_active(t) else "leaving" if sc.dispatch_leaving(t) else "on")
                t += 1 / 60
            assert len(widths) == 2 and xs[0] == free / 2, (centred, lag, widths, xs[0])
            step = max(abs(b - a) for a, b in zip(xs, xs[1:]))
            assert step <= 1.0, (centred, lag, "the presence stepped", step)
            # No grain jumps on the screen when the window changes width: across a widen or a narrow each grain moves
            # no further than its springs move it in an ordinary frame.
            moves = [(a[0] != b[0], max(abs(q - p) for p, q in zip(a[1], b[1])))
                     for a, b in zip(grains, grains[1:]) if len(a[1]) == len(b[1])]
            ordinary = max(m for changed, m in moves if not changed)
            assert any(c for c, _ in moves) and max(m for c, m in moves if c) <= ordinary, (
                centred, lag, again, "a grain jumped as the width changed", ordinary)
            end = phases.index(None, phases.index("on"))
            assert phases[end - 1] == "leaving", (centred, lag, again, "the fan ended with no teardown")

        # A drag during a fan: the wide, centred window goes to the left margin with Rook and the fan where they were,
        # and Rook then follows the pointer exactly.
        saved_anchor, wide = LayerShell.set_anchor, Scene(0.0).dispatch_canvas_width()
        anchors, margins = [], {}
        LayerShell.set_anchor = lambda _w, e, v: anchors.append((int(e), v))
        LayerShell.set_margin = lambda _w, e, v: margins.__setitem__(int(e), v)
        try:
            ov = types.SimpleNamespace(_centred=True, _win_width=wide, _dispatch_cx=None, left=(free - WIDTH) // 2,
                                       top=0, in_game=False, bounds=(0, 0, free, 1440), answer_open=False, win=None,
                                       return_at=None, flight=None, scene=Scene(0.0),
                                       column=types.SimpleNamespace(get_width=lambda: wide))
            ov.carry = [None, (ov.left, ov.top), (0, 0), False]
            ov._move_window = lambda x, y: Overlay._move_window(ov, x, y)
            before = (free - wide) / 2 + wide / 2  # The compositor centres the wide window.
            Overlay._carry_update(ov, None, 40.0, 0.0)
            after = margins[int(LayerShell.Edge.LEFT)] + Overlay._canvas_cx(ov, wide)
            assert not ov._centred and (int(LayerShell.Edge.LEFT), True) in anchors, anchors
            assert after == before + 40.0 and Overlay._canvas_cx(ov, wide) == wide / 2, (before, after)
        finally:
            LayerShell.set_anchor = saved_anchor
    finally:
        LayerShell.set_margin = saved_margin
        _use_theme("light" if saved_pal is THEMES["light"] else "dark")
    print("send window (names reveal as their strands land, one and three; presence holds still, widen and narrow): ok")


def _check_send_window_gl():
    """_check_send_window_gl_one with each send form, so the check never depends on whose turn the cycle is on."""
    saved = SEND_CYCLE[:]
    try:
        for form in saved:
            others = [f for f in saved if f != form]
            SEND_CYCLE[:] = [others[0], form, *others[1:]]  # A new send rotates the cycle once, so form comes first.
            _check_send_window_gl_one()
    finally:
        SEND_CYCLE[:] = saved


def _check_send_window_gl_one():
    """The same send drawn by the chip (_DustGL, its springs on the chip) in a GL context with no window: across the
    widen and the narrow, the lit dust's mean x on the screen never jumps, and no frame is blank. Skipped where this
    machine has no surfaceless EGL."""
    try:
        egl = ctypes.CDLL("libEGL.so.1")
    except OSError:
        egl = None
    if egl is None:
        print("send window on the chip: skipped, no libEGL")
        return
    egl.eglGetPlatformDisplay.restype = egl.eglCreateContext.restype = ctypes.c_void_p
    egl.eglGetPlatformDisplay.argtypes = [ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    egl.eglInitialize.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    egl.eglChooseConfig.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    egl.eglCreateContext.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    egl.eglMakeCurrent.argtypes = [ctypes.c_void_p] * 4
    dpy = egl.eglGetPlatformDisplay(0x31DD, None, None)  # EGL_PLATFORM_SURFACELESS_MESA
    cfg, n = ctypes.c_void_p(), ctypes.c_int()
    if not (dpy and egl.eglInitialize(dpy, None, None) and egl.eglBindAPI(0x30A2) and egl.eglChooseConfig(
            dpy, (ctypes.c_int * 5)(0x3040, 8, 0x3033, 0, 0x3038), ctypes.byref(cfg), 1, ctypes.byref(n)) and n.value):
        print("send window on the chip: skipped, no surfaceless EGL")
        return
    context = egl.eglCreateContext(dpy, cfg, None, (ctypes.c_int * 7)(0x3098, 4, 0x30FB, 4, 0x30FD, 1, 0x3038))
    if not context:
        print("send window on the chip: skipped, no GL 4.4 context")
        return
    ctx = types.SimpleNamespace(make_current=lambda: egl.eglMakeCurrent(dpy, None, None, context),
                                clear_current=lambda: egl.eglMakeCurrent(dpy, None, None, None))
    saved_pal = PALETTE
    _use_theme("dark")
    try:
        ctx.make_current()
        gl, read = _DustGL(None, ctx), ctypes.CDLL("libOpenGL.so.0").glReadPixels
        frame = []

        def build(tex, sync, w, h):  # In place of a GDK texture: the frame's pixels, and the texture back for reuse.
            gl.gl.BindFramebuffer(0x8D40, gl.out_fbo)
            pixels = (ctypes.c_ubyte * (w * h * 4))()
            read(0, 0, w, h, 0x1908, 0x1401, pixels)  # GL_RGBA, GL_UNSIGNED_BYTE
            gl.free.append((tex, sync, (w, h)))
            frame[:] = [w, bytes(pixels)]
        gl._build = build
        free, sc, t = 2000, Scene(0.0), 0.0
        sc.monitor_width, sc.spring_back = float(free), lambda: gl.read_springs(sc)
        wide = sc.dispatch_canvas_width()
        script = [(0.0, {"state": "thinking"}), (1.0, {"activity": "t3_thread_send"}),
                  (1.0, {"send": [{"id": "w", "name": "Opus"}]}), (2.0, {"send": [{"id": "w", "outcome": "landed"}]}),
                  (2.6, {"state": "thinking"})]
        xs = []
        while t < 4.5:
            while script and script[0][0] <= t:
                sc.handle(script.pop(0)[1], t)
            sc.spring_gl = True
            if sc.springs_on_gpu:
                gl.follow(sc)
            sc.step(t)
            area_w = wide if sc.dispatch_active(t) else ORB_W
            gl.draw_main(sc, area_w, sc.lift + ORB_H, (area_w / 2.0, sc.lift + ORB / 2), 1.0, None)
            w, pixels = frame
            lit = [(k // 4) % w for k in range(3, len(pixels), 12) if pixels[k] > 24]  # Every third pixel's alpha.
            assert lit, (t, area_w, "a blank frame")
            # Only the presence's own dust counts: a name or strand appearing to one side is not a jump.
            lit = [x for x in lit if abs(x - area_w / 2.0) <= ORB_W / 2.0] or lit
            xs.append((area_w, (free - area_w) / 2 + sum(lit) / len(lit)))  # The centred window, the area in it.
            t += 1 / 60
        assert sc.springs_on_gpu and len({w for w, _ in xs}) == 2, "the chip did not run the springs, or no resize"
        steps = [(a[0] != b[0], abs(b[1] - a[1])) for a, b in zip(xs, xs[1:])]
        # A resize must not move the dust. Between resizes the lit mean moves with the form itself: the array's
        # one-sided wings gather 6 px a frame in its teardown, which is motion, so only a teleport fails there.
        assert max((m for r, m in steps if r), default=0.0) <= 4.0, ("the dust jumped at a resize", steps)
        assert max(m for _, m in steps) <= 10.0, ("the dust jumped on the screen", max(steps, key=lambda s: s[1]))
    finally:
        ctx.clear_current()
        _use_theme("light" if saved_pal is THEMES["light"] else "dark")
    print(f"send window on the chip, {SEND_CYCLE[0]} (widen and narrow, the lit dust's screen x steady, no blank frame): ok")


def _send_turns():
    """Whole turns around a send, as (case, [(time, message)], end): one thread, two threads, send then speak then
    rest, send then straight to rest, and a send while a diagram shows."""
    def names(n):
        return [{"id": f"m{k}", "name": name, "outcome": "pending"} for k, name in enumerate(("Lark", "Harbor")[:n])]

    def landed(n):
        return {"send": [{"id": f"m{k}", "outcome": "landed"} for k in range(n)]}

    go = {"state": "thinking", "activity": "t3_thread_send"}
    diagram = {"diagram": {"graph": "a > b"}}
    return [
        ("one", [(0.0, {"state": "thinking"}), (2.0, go), (2.0, {"send": names(1)}), (3.6, landed(1)),
                 (9.0, {"state": "speaking"}), (11.0, {"state": "ready"})], 14.0),
        ("two", [(0.0, {"state": "thinking"}), (2.0, go), (2.0, {"send": names(2)}), (3.6, landed(2)),
                 (9.0, {"state": "speaking"}), (11.0, {"state": "ready"})], 14.0),
        ("speak-rest", [(0.0, {"state": "thinking"}), (2.0, go), (2.0, {"send": names(1)}), (3.6, landed(1)),
                        (5.0, {"state": "speaking"}), (8.0, {"state": "ready"})], 11.0),
        ("silent-rest", [(0.0, {"state": "thinking"}), (2.0, go), (2.0, {"send": names(1)}), (3.6, landed(1)),
                         (5.0, {"state": "ready"})], 8.0),
        ("diagram", [(0.0, {"state": "thinking"}), (0.5, {"render": diagram}), (2.0, go), (2.0, {"send": names(1)}),
                     (3.6, landed(1)), (9.0, {"state": "speaking"}), (11.0, {"state": "ready"})], 14.0),
    ]


def _send_motion(script, end, varied):
    """A turn on a frame clock: each frame's time, mean grain speed (px/s), mean distance to the targets (px), mean
    target speed (px/s) and form."""
    scene, t, n, trace, last = Scene(0.0), 0.0, 0, [], None
    rng = random.Random(7)
    while t < end:
        while n < len(script) and script[n][0] <= t:
            msg = script[n][1]
            if "render" in msg:
                assert scene.render_command(msg["render"], t)["ok"]
            else:
                scene.handle(msg, t)
            n += 1
        x0, y0 = list(scene.x), list(scene.y)
        dt = rng.choice((1 / 144, 1 / 90, 1 / 60, 1 / 45, 1 / 30)) if varied else 1 / 60
        t += dt
        scene.step(t)
        idx = [i for i in scene.idx if i < min(len(x0), len(scene.x))]
        tx, ty, _ = scene._targets(scene.form, t)
        speed = sum(math.hypot(scene.x[i] - x0[i], scene.y[i] - y0[i]) for i in idx) / len(idx) / dt
        far = sum(math.hypot(scene.x[i] - tx[i], scene.y[i] - ty[i]) for i in idx) / len(idx)
        aim = 0.0 if last is None or last[2] != scene.form else sum(
            math.hypot(tx[i] - last[0][i], ty[i] - last[1][i]) for i in idx) / len(idx) / dt
        last = (tx, ty, scene.form)
        trace.append((t, speed, far, aim, scene.form, scene.dispatch is not None))
    return trace


def _send_stalls(trace):
    """Runs of more than three frames with near-zero grain motion while the targets are still far or still moving."""
    runs, run = [], []
    for t, speed, far, aim, *_ in trace:
        if speed < 4.0 and (far > 4.0 or aim > 8.0):
            run.append(t)
        else:
            if len(run) > 3:
                runs.append((run[0], run[-1], len(run)))
            run = []
    if len(run) > 3:
        runs.append((run[0], run[-1], len(run)))
    return runs


def _check_send_motion():
    """No send turn holds a still cluster: at a steady and a varied frame time, the grains never stop while they
    still have somewhere to go or the device shows."""
    for case, script, end in _send_turns():
        for varied in (False, True):
            trace = _send_motion(script, end, varied)
            stalls = _send_stalls(trace)
            assert not stalls, (case, "varied" if varied else "60 Hz", stalls)
            # Once the fan has gone, no send form holds on: not the device, and not the loop it used to sit on.
            gone = next(k for k in range(1, len(trace)) if trace[k - 1][5] and not trace[k][5])
            assert all(r[4] not in devs_pack.SEND_FORMS for r in trace[gone:]), (case, "a send form after the fan")
    print("send turns (one, two, speak then rest, silent rest, diagram; 60 Hz and varied frames): no stalls")


def _check_lettering():
    """A pack's lettering: Devs sets its serif, a pack's own font file loads, a bad one falls back to today's
    lettering, Nova keeps today's lettering, the reveal leaves no grains, and long thread names follow the length
    rule."""
    import tempfile
    saved_pal = PALETTE
    _use_theme("dark")
    try:
        devs = Scene(0.0)
        assert LETTERING is not None and LABEL_FONT.get_family() == "Noto Serif", "the Devs lettering did not load"
        fonts = PangoCairo.FontMap.get_default()
        loaded = fonts.load_font(fonts.create_context(), LABEL_FONT).describe()
        assert loaded.get_family() == "Noto Serif" and loaded.get_weight() == Pango.Weight.HEAVY, loaded.to_string()
        _use_theme("light")
        assert LETTERING is None and LABEL_FONT.to_string() == _DEFAULT_FONTS[2].to_string()
        _use_theme("dark")
        assert LETTERING is not None

        # A built-in pack's own font file loads. A missing, symlinked, oversized or user-pack font keeps today's
        # lettering, with no exception.
        good_font = subprocess.run(["fc-match", "-f", "%{file}", "Noto Serif:black"], capture_output=True,
                                   text=True, check=True).stdout
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(pack_player.THEMES_DIR, "devs")
            # So does a value out of range in the block, with a good font: NaN, a huge size, a negative outline.
            for name, setup in (("good", "good"), ("gone", None), ("linked", "link"), ("huge", "huge"),
                                ("nan", "nan"), ("giant", "giant"), ("inkless", "inkless")):
                pdir = os.path.join(tmp, name)
                os.makedirs(os.path.join(pdir, "fonts"))
                manifest = json.load(open(os.path.join(source, "manifest.json")))
                manifest["name"] = name
                manifest["text"]["font"] = "fonts/own.ttf"
                if setup in ("nan", "giant", "inkless"):
                    manifest["text"]["label"]["size"] = {"nan": math.nan, "giant": 1e9}.get(setup, 11)
                    manifest["text"]["outline"]["width"] = -1 if setup == "inkless" else 0.6
                json.dump(manifest, open(os.path.join(pdir, "manifest.json"), "w"))
                font = os.path.join(pdir, "fonts", "own.ttf")
                if setup == "link":
                    os.symlink(good_font, font)
                elif setup == "huge":
                    with open(font, "wb") as f:
                        f.truncate(pack_player.MAX_FONT_FILE_BYTES + 1)
                elif setup:
                    shutil.copyfile(good_font, font)
                assert devs.set_pack(name, 0.0, themes_dir=tmp) and devs.pack_name == name, name
                if setup == "good":
                    assert LETTERING is not None and font in _FONT_FILES, name
                    continue
                assert LETTERING is None and devs.pack["_lettering"] is None, name
                assert CAPTION_FONT.to_string() == _DEFAULT_FONTS[0].to_string(), name
                devs._label_sprite(cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 4, 4)), "LISTENING")
            assert pack_player.pack_font_file({"text": {"font": "fonts/x.ttf"}, "_dir": tmp, "_user": True}) is None
            # A user pack cannot set the loader's own keys: "_lettering", "_user" and "_dir" are dropped on load.
            user = os.path.join(tmp, "config", "rook", "themes", "sneaky")
            os.makedirs(user)
            json.dump({"name": "sneaky", "format": 1, "kind": "points", "base": "devs", "icons": {}, "states": {},
                       "_lettering": {"label": 1}, "_user": False, "_dir": source},
                      open(os.path.join(user, "manifest.json"), "w"))
            old_xdg = os.environ.get("XDG_CONFIG_HOME")
            os.environ["XDG_CONFIG_HOME"] = os.path.join(tmp, "config")
            try:
                assert devs.set_pack("sneaky", 0.0) and devs.pack_name == "sneaky"
                assert devs.pack["_user"] is True and devs.pack["_dir"] != source
                assert LETTERING is not None and LETTERING is devs.pack["_lettering"]  # Its base's block, by family.
            finally:
                if old_xdg is None:
                    os.environ.pop("XDG_CONFIG_HOME", None)
                else:
                    os.environ["XDG_CONFIG_HOME"] = old_xdg
        devs.set_pack("devs", 0.0)
        assert LETTERING is not None

        # Nova has no text block: its labels, names and captions keep today's lettering, pixel for pixel.
        nova = Scene(0.0)
        assert nova.set_pack("nova", 0.0) and LETTERING is None
        assert (LABEL_FONT.to_string(), CAPTION_FONT.to_string(), LABEL_SPACING, CAPTION_SPACING) == (
            _DEFAULT_FONTS[2].to_string(), _DEFAULT_FONTS[0].to_string(), _DEFAULT_FONTS[3], 0.0)
        probe = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 4, 4))
        old = _word_sprite(probe, "LISTENING", 1.0, LABEL_FONT, PALETTE["label"], LABEL_SPACING, PALETTE["label_halos"],
                           PALETTE["label_halo"], PALETTE["label_outline"])[0]
        assert bytes(nova._label_sprite(probe, "LISTENING")[0].get_data()) == bytes(old.get_data())
        assert nova.dispatch_gl_rows(1.0) == []

        # The reveal: a new label spreads in and leaves no grains; the same text again does not replay it.
        scene, t = _simulate(LISTEN, 0.2, lift=0)
        assert scene.label == "LISTENING" and 0.0 <= t - scene.label_at < REVEAL_SECONDS
        assert 0 < len(scene.dispatch_gl_rows(t)) // 11 <= REVEAL_GRAINS[0] * len("LISTENING")
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(ORB_W * 1.6), int(ORB_H * 1.6))
        surf.set_device_scale(1.6, 1.6)
        scene.draw_swarm(cairo.Context(surf), ORB_W, t)
        assert scene.dispatch_gl_rows(scene.label_at + REVEAL_SECONDS) == []
        shown_at = scene.label_at
        scene.handle({"state": "hidden"}, 1.0)
        for k in range(30):
            scene.step(1.0 + k * 0.02)
        scene.handle({"state": "listening"}, 2.0)
        for k in range(30):
            scene.step(2.0 + k * 0.02)
        assert scene.label == "LISTENING" and scene.label_at == shown_at, "the same label replayed its reveal"
        sd, _ = _simulate([(0.0, {"state": "thinking"}), (0.4, {"send": [{"id": "a", "name": "Fable"}]})], 3.5,
                          lift=0)
        t0 = sd.dispatch.t0 + sd.dispatch.rows[0]["begin"] + DISPATCH_TRAVEL  # When the name starts to show.
        sd.draw_swarm(cairo.Context(surf), ORB_W, t0 + 0.2)  # Letters the name, on the Cairo path.
        for dt in (0.03, 0.2, 0.4):
            assert 0 < len(sd.dispatch.reveal_rows(t0 + dt, 0.0)) // 11 <= REVEAL_GRAINS[0] * len("FABLE"), dt
        assert sd.dispatch.reveal_rows(t0 + REVEAL_SECONDS, 0.0) == []
        # A long name has one ellipsis: the 22-character cut, or on a narrow screen the middle cut alone.
        long_name = "Harbor lights on the north pier and the old ferry slip"
        assert _lettered_text(long_name, False, 380.0) == "HARBOR LIGHTS ON THE…"
        assert _lettered_text(long_name, False, 120.0).count("…") == 1

        # The long-name rule: the words before a colon, else whole words up to 22 characters and an ellipsis.
        assert _short_name("Rook on the phone: the web app, first release") == "Rook on the phone"
        assert _short_name("Harbor lights on the north pier") == "Harbor lights on the…"
        assert _short_name("Ab: a much longer second part of it") == "Ab: a much longer…"
        assert all(len(_short_name(n)) <= 22 for n in ("A" * 60, "word " * 20, "Fable"))
    finally:
        _use_theme("light" if saved_pal is THEMES["light"] else "dark")
    print("lettering (Devs font, fallback, Nova unchanged, reveal, long names): ok")


def _check_card():
    """The Devs permission card: its headline rules, Allow and Decline live at once, the queue mark with two cards,
    its drawing cost, and Nova and the light theme keeping the plain card."""
    import inspect
    saved_pal = PALETTE
    _use_theme("dark")
    try:
        Scene(0.0)  # The Devs pack, with its lettering.
        assert LETTERING is not None

        def words(tool, data):
            return _card_words(tool, json.dumps(data, indent=2))
        # The headline is the tool's own summary; without one, a short plain line from the tool and its main input.
        assert words("Bash", {"command": "make tidy", "description": "Tidy the build folder"}) == (
            "Tidy the build folder", "make tidy")
        assert words("Bash", {"command": "make tidy"}) == ("Run a shell command", "make tidy")
        assert words("Edit", {"file_path": "/srv/app/desktop/overlay.py", "old_string": "a", "new_string": "b\nc"}) == (
            "Edit desktop/overlay.py", "/srv/app/desktop/overlay.py\nReplaces 1 line with 2 lines\n\n- a\n+ b\n+ c")
        assert words("Write", {"file_path": "/srv/notes/notes.md", "content": "one\ntwo"}) == (
            "Write notes/notes.md", "/srv/notes/notes.md\n2 lines\n\none\ntwo")
        assert words("Read", {"file_path": "/srv/app/main.py", "limit": 40}) == (
            "Read app/main.py", "/srv/app/main.py\n\nlimit: 40")
        assert words("mcp__harbor-maps__find_pier", {"pier": "north", "depth": 4}) == (
            "Find pier", "pier: north\ndepth: 4")
        assert _card_tag("Claude", "mcp__harbor-maps__find_pier") == "Claude · harbor-maps"
        assert words("WebFetch", {"url": "https://example.com/tide", "prompt": "The times"})[0] == "Fetch example.com"
        assert words("NotebookEdit", {})[0] == "Use NotebookEdit"
        assert _card_words("Bash", "not json") == ("Use Bash", "not json")
        # Nothing that runs is hidden: a key the clean form does not show is listed under it.
        head, body = words("Bash", {"command": "make", "description": "Build", "dangerouslyDisableSandbox": True})
        assert head == "Build" and body == "make\n\ndangerouslyDisableSandbox: true", body
        # A long summary keeps two lines and ends in an ellipsis.
        lines = _card_headline_lines("Run the tide tests, then ship the fix to the harbour branch " * 4)
        assert len(lines) == 2 and lines[1].endswith("…"), lines

        # Allow and Decline are both live at once: each answers the card on show at once, with no gate or wait.
        sent = []
        desk = types.SimpleNamespace(card_id="c1", answer_fields=[], _emit=sent.append)
        Overlay._permission(desk, True)
        Overlay._permission(desk, False)
        assert sent == [{"event": "permission", "allow": True, "card": "c1"},
                        {"event": "permission", "allow": False, "card": "c1"}], sent
        assert "set_sensitive" not in "".join(inspect.getsource(f) for f in (
            _CardFace, Overlay._show_permission, Overlay._apply_state, Overlay._permission))

        # The queue mark shows with two cards, in its own gap of the top edge; with one card the edge runs on.
        bash = json.dumps({"command": "git push", "description": "Push the finished branch"})
        one, two = _CardFace("Bash", "Claude", bash, 1), _CardFace("Bash", "Claude", bash, 2)
        assert one.tag == "CLAUDE · BASH" and one.queue is None and two.queue == "CARD 1 OF 2"
        h = CARD_FALL + 22 + CARD_LINE + 2 + 8 + two.req_h + 18 + 25 + 16
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(CARD_W * 1.6), int(h * 1.6))
        surf.set_device_scale(1.6, 1.6)
        cr = cairo.Context(surf)
        right = CARD_W - CARD_PAD - 10  # Inside the queue mark's gap.
        for face, gap in ((one, False), (two, True)):
            face.draw_panel(cr, CARD_W, h, None, 1.0)
            top = [g for g in face.frame[1] if abs(g["at"][1] - CARD_INSET) < 3 and abs(g["at"][0] - right) < 4]
            assert bool(top) != gap, (face.queue, len(top))
        # Its cost: the frame at rest, a few times a second, and a whole entrance frame of every part.
        cost = {"rest": [], "entrance": []}
        for n in range(30):
            t0 = time.perf_counter()
            two.draw_panel(cr, CARD_W, h, None, n / CARD_REST_FPS)
            cost["rest"].append((time.perf_counter() - t0) * 1000)
            t = n * CARD_ENTRANCE / 30
            t0 = time.perf_counter()
            two.draw_panel(cr, CARD_W, h, t, t)
            two.draw_headline(cr, t)
            two.draw_request(cr, t)
            two.draw_button(cr, False, t)
            two.draw_button(cr, True, t)
            cost["entrance"].append((time.perf_counter() - t0) * 1000)
        for kind, frames in cost.items():
            print(f"Devs card {kind}: {len(two.frame[1])} grains, {sum(frames) / len(frames):.2f} ms mean, "
                  f"{max(frames):.2f} ms max per frame")
        assert sum(cost["rest"]) / 30 < 8.0, cost["rest"]
        # A 3000-line request draws only the lines in view, from a layout made once: no freeze while it arrives.
        many = "\n".join(f"echo harbour line {n}" for n in range(3000))
        t0 = time.perf_counter()
        big = _CardFace("Bash", "Claude", json.dumps({"command": many, "description": "Print the harbour log"}))
        print(f"Devs card 3000-line request: laid out once in {(time.perf_counter() - t0) * 1000:.0f} ms")
        frames = []
        for n in range(30):
            t0 = time.perf_counter()
            big.draw_request(cr, n * CARD_ENTRANCE / 30, 0.0, 320.0)
            frames.append((time.perf_counter() - t0) * 1000)
        print(f"Devs card 3000-line request: {sum(frames) / 30:.2f} ms mean, {max(frames):.2f} ms max per frame")
        assert max(frames) < 5.0, frames

        # A failure never leaves the card before's face under a new card: building or drawing the Devs card falls
        # back to the plain card, which answers the card on show. A new card's request starts at its top.
        class View:
            def __init__(self):
                self.value = 0.0

            def get_vadjustment(self):
                return self

            def set_value(self, value):
                self.value = value

        def desk_stub():
            d = types.SimpleNamespace(card_id=None, face=None, card_at=0.0, card_details="", answer_fields=[],
                                      scene=types.SimpleNamespace(state="permission", err=0.0), request_view=View(),
                                      devs_request_view=View(), shown=[], redraws=[], sent=[])
            d.card_panel = types.SimpleNamespace(queue_draw=lambda: d.redraws.append(1))
            d._show_permission = lambda questions: d.shown.append((d.card_id, d.face))
            d._emit, d._apply_state = d.sent.append, lambda: None
            for name in ("_open_card", "_devs_card", "_card_t", "_devs_draw", "_permission", "_draw_panel"):
                setattr(d, name, types.MethodType(getattr(Overlay, name), d))
            return d

        def open_card(desk, card, details):
            desk.card_details = details  # As handle sets it from the same message.
            desk._open_card({"state": "permission", "card": card, "tool": "Bash", "who": "Claude", "details": details})

        def failing(*_args, **_kw):
            raise RuntimeError("a test failure")

        def near(rgb, colour, alpha):
            return all(abs(v - c * alpha * 255) <= 1 for v, c in zip(rgb, colour))

        def plain_panel(desk):
            image = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 120)
            desk._draw_panel(None, cairo.Context(image), 200, 120)
            b, g, r, _a = bytes(image.get_data())[(80 * 200 + 100) * 4:][:4]
            return near((r, g, b), TERM_BG, 0.97)
        push = json.dumps({"command": "git push", "description": "Push the finished branch"})
        tidy = json.dumps({"command": "make tidy", "description": "Tidy the build folder"})
        desk = desk_stub()
        open_card(desk, "A", push)
        assert desk._devs_card() and desk.face.headline == "Push the finished branch"
        desk.request_view.value = desk.devs_request_view.value = 300.0  # Card A scrolled to its end.
        open_card(desk, "A", push)
        assert desk.devs_request_view.value == 300.0, "the same card again lost its scroll"
        real = _CardFace.__init__
        _CardFace.__init__ = failing
        try:
            open_card(desk, "B", tidy)
        finally:
            _CardFace.__init__ = real
        assert desk.face is None and desk.card_id == "B" and desk.shown[-1] == ("B", None) and not desk._devs_card()
        assert desk.request_view.value == desk.devs_request_view.value == 0.0, "card B opened at card A's scroll"
        assert desk.card_details == tidy and plain_panel(desk)
        desk._permission(True)
        assert desk.sent[-1] == {"event": "permission", "allow": True, "card": "B"}, desk.sent
        for part in ("draw_headline", "draw_panel"):
            open_card(desk, f"C-{part}", tidy)
            assert desk._devs_card() and desk.face.headline == "Tidy the build folder"
            real = getattr(_CardFace, part)
            setattr(_CardFace, part, failing)
            try:
                drawn = (desk._devs_draw(_CardFace.draw_headline, cr, None) if part == "draw_headline"
                         else not plain_panel(desk))  # The panel falls back in the same frame.
            finally:
                setattr(_CardFace, part, real)
            assert not drawn and desk.face is None and desk.redraws and not desk._devs_card(), part
            assert plain_panel(desk) and desk.card_id == f"C-{part}", part

        # The panel: the Devs plate under the Devs lettering; Nova and the light theme keep the plain card's surface.
        def centre(pack, theme):
            _use_theme(theme)
            stub = types.SimpleNamespace(face=two, card_at=0.0, scene=Scene(0.0))
            if pack:
                assert stub.scene.set_pack(pack, 0.0)
            stub.scene.state = "permission"
            for name in ("_devs_card", "_card_t", "_devs_draw"):
                setattr(stub, name, types.MethodType(getattr(Overlay, name), stub))
            image = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 120)
            Overlay._draw_panel(stub, None, cairo.Context(image), 200, 120)
            b, g, r, _a = bytes(image.get_data())[(80 * 200 + 100) * 4:][:4]
            return stub._devs_card(), (r, g, b)
        devs, rgb = centre(None, "dark")
        assert devs and near(rgb, CARD_PLATE, 0.96), rgb
        for pack, theme in (("nova", "dark"), (None, "light")):
            devs, rgb = centre(pack, theme)
            assert not devs and near(rgb, TERM_BG, 0.97), (pack, theme, rgb)
    finally:
        _use_theme("light" if saved_pal is THEMES["light"] else "dark")
        Scene(0.0)  # The Devs pack again.
    print("Devs permission card (headlines, both buttons live, queue mark, cost, fallback, scroll reset, Nova and "
          "light unchanged): ok")


def main():
    args = sys.argv[1:]
    if "--listen" in args:
        at = args.index("--listen") + 1
        styles = (args[at] if at < len(args) else "").split(",")
        if not all(style in LISTEN_STYLES for style in styles):
            print(f"--listen takes one or more of: {', '.join(LISTEN_STYLES)}", file=sys.stderr)
            return 2
        FORM_FOR_STATE["listening"] = LISTEN_STYLES[styles[0]]
        if len(styles) > 1:
            LISTEN_CYCLE[:] = styles[-1:] + styles[:-1]  # The first turn rotates to the first style.
    theme = None
    if "--theme" in args:
        at = args.index("--theme") + 1
        theme = args[at] if at < len(args) else ""
        if theme not in THEMES:
            print("--theme takes light or dark", file=sys.stderr)
            return 2
        _use_theme(theme)
    if "--font" in args:
        at = args.index("--font") + 1
        name = args[at] if at < len(args) else ""
        if name not in FONTS:
            print(f"--font takes one of: {', '.join(FONTS)}", file=sys.stderr)
            return 2
        _use_font(FONTS[name])
    pack = None
    if "--pack" in args:
        at = args.index("--pack") + 1
        pack = args[at] if at < len(args) else ""
        packs = pack_player.list_packs()
        if pack not in packs:
            print(f"--pack takes one of: {', '.join(packs)}", file=sys.stderr)
            return 2
    if "--render" in args:
        global _OFFSCREEN_SOFT
        _OFFSCREEN_SOFT = True
        try:
            render(args[args.index("--render") + 1])
        finally:
            _OFFSCREEN_SOFT = False
        return 0
    if "--check-placement" in args:
        _check_placement()
        return 0
    if "--check-render" in args:
        _check_render()
        return 0
    if "--check-viewer" in args:
        _check_viewer()
        return 0
    return Overlay(demo="--demo" in args, theme=theme, wow="--wow" in args, pack=pack).run(None)


if __name__ == "__main__":
    raise SystemExit(main())
