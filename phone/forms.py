"""Export the desktop swarm's forms for the phone, from desktop/overlay.py itself.

    scripts/capped env -u WAYLAND_DISPLAY -u DISPLAY /usr/bin/python phone/forms.py            writes phone/forms.json
    scripts/capped env -u WAYLAND_DISPLAY -u DISPLAY /usr/bin/python phone/forms.py --desktop DIR
                                                                    also draws the desktop's own swarm per state

It imports the overlay as a module and never runs it, so no window opens and nothing plays. The overlay needs the
system Python (PyGObject, cairo). The phone's canvas reads forms.json: each grain's own constants (its spring, delay,
shimmer, brightness, size and tone), and each form's points in the desktop's coordinates. Numbers are packed as
little-endian int16 in base64, at a fixed scale per field, to keep the file small.

The Devs look (the soft gold grains, their sparkles and glow) and the forms it rebuilt in 3D (the loop, the halo with
its rays, the helix) come from desktop/devs_pack.py and themes/devs/manifest.json. Until those are merged, they are
read from the branch DEVS_REF with git show, into a temporary folder, without touching the checkout.
"""

import base64
import json
import math
import random
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "desktop"))
import overlay  # noqa: E402

DEVS_REF = "engine/round1-particles"


def devs_pack():
    """desktop/devs_pack.py with its manifest, from the checkout once merged, else from DEVS_REF."""
    if (HERE.parent / "desktop" / "devs_pack.py").exists():
        import devs_pack as pack
        return pack
    root = Path(tempfile.mkdtemp(prefix="rook-devs-"))
    for path in ("desktop/devs_pack.py", "themes/devs/manifest.json"):
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_bytes(subprocess.run(["git", "-C", str(HERE.parent), "show", f"{DEVS_REF}:{path}"],
                                                 check=True, capture_output=True).stdout)
    sys.path.insert(0, str(root / "desktop"))
    sys.dont_write_bytecode = True
    import devs_pack as pack
    for path in ("desktop/devs_pack.py", "themes/devs/manifest.json"):
        (root / path).unlink()
    for folder in ("themes/devs", "themes", "desktop", ""):
        (root / folder).rmdir()
    return pack


def devs_forms(pack, n):
    """The forms exported dynamically for the phone: restored flat loop, organic halo, and 3D helix."""
    seed = lambda name: random.Random(sum(map(ord, name)))
    loop_pts = overlay._form("loop")
    halo_pts = overlay._form("halo")
    helix = pack.build_helix_3d(n, seed("helix"))
    return {
        "loop": {"type": "loop2", "along": pack_(p[0] for p in loop_pts), "off": pack_(p[1] for p in loop_pts)},
        # The Devs halo's ring grains carry None in p[2] and their radial offset in p[4]; its ripple and core grains
        # draw as the phone's inner echo ring.
        "halo": {"type": "halo2", "a": pack_(math.atan2(p[1], p[0]) for p in halo_pts),
                 "echo": pack_((p[2] is not None for p in halo_pts), 1),
                 "off": pack_((p[4] if p[2] is None else 0 for p in halo_pts))},
        "helix": {"type": "helix3", "u": pack_((p[2] for p in helix), 10000), "turn": pack_((p[3] > 0 for p in helix), 1),
                  "rung": pack_((p[4] is not None for p in helix), 1), "v": pack_((p[4] or 0 for p in helix)),
                  "oy": pack_(p[5] for p in helix), "oz": pack_(p[6] for p in helix)},
    }


def pack_(values, scale=1000):
    return pack(list(values), scale)

# The phone's forms: its thinking pair, the sphere it speaks with (the loop, halo and helix come from devs_forms),
# and the form each kind of activity takes on the desktop (ACTIVITY_FORMS), by the tool that kind stands for.
SPIN_FORMS = ["lattice", "rook", "sphere", "globe"]
STILL_FORMS = ["rows", "question", "sink", "page", "magnifier", "prompt", "quill", "send_turbine", "send_array",
               "hourglass", "spinner", "film", "cog", "sword", "eye", "overlook", "message"]


def pack(values, scale):
    return base64.b64encode(struct.pack(f"<{len(values)}h", *(max(-32767, min(32767, round(v * scale)))
                                                                 for v in values))).decode()


def export():
    scene = overlay.Scene(0.0)
    n = overlay.GRAINS
    forms = {}
    for name in SPIN_FORMS:
        points = overlay._form(name)
        k, dx, dy = overlay.FORM_FIT.get(name, (1.0, 0.0, 0.0))
        forms[name] = {"type": "spin", "spin": overlay.SPIN[name], "fit": [k, dx, dy],
                       "x": pack([p[0] for p in points], 10), "y": pack([p[1] for p in points], 10),
                       "z": pack([p[2] for p in points], 10)}
    for name in STILL_FORMS:
        # The desktop's own targets, settled: a flowing send or the hourglass is taken five seconds in, mid-flow.
        scene.state, scene.state_at, scene.form, scene.form_at = "transcribing", -99.0, name, 0.0
        tx, ty, tb = scene._targets(name, 5.0)
        forms[name] = {"type": "still", "x": pack(tx, 10), "y": pack(ty, 10), "b": pack(tb, 1000)}
    devs = devs_pack()
    forms.update(devs_forms(devs, n))
    fresh = overlay.Scene(0.0)
    grains = {"omega": pack(fresh.omega, 1000), "delay": pack(fresh.delay, 1000), "curl": pack(fresh.curl, 1000),
              "freq": pack(fresh.freq, 1000), "phase": pack(fresh.phase, 1000), "base": pack(fresh.base, 1000),
              "size": pack(fresh.size, 1000), "tone": pack(fresh.tone, 1), "blue": pack(fresh.blue_rank, 1000)}
    dark = overlay.THEMES["dark"]
    data = {
        "grains": n, "restEvery": 1,  # The Devs look draws every grain at rest, as the desktop now does.
        "loopPeriod": overlay.LOOP_PERIOD, "tilt": overlay.TILT,
        "thinkTurn": overlay.THINK_TURN, "depthFloor": dark["depth_floor"],
        "tones": [list(t) for t in dark["tones"]], "blueTone": list(dark["blue"]), "spark": list(dark["spark"]),
        "sparkAlpha": dark["spark_alpha"], "ember": list(dark["ember"]),
        "labels": {**overlay.LABELS}, "grain": grains, "forms": forms,
        "look": devs.LOOK, "meta": {"helix": devs.FORMS_META["helix"]},
    }
    out = HERE / "forms.json"
    out.write_text(json.dumps(data, separators=(",", ":")) + "\n")
    print(f"Wrote {out} ({out.stat().st_size // 1024} KiB, {len(forms)} forms).")


# The desktop's own swarm for each phone state, drawn offscreen on black for the side-by-side comparison.
DESKTOP_STATES = [
    ("resting", [(0.0, {"state": "ready"})], 12.0),
    ("listening", [(0.0, {"state": "ready"}), (0.5, {"state": "listening"})], 2.6),
    ("transcribing", [(0.0, {"state": "listening"}), (1.0, {"state": "transcribing"})], 2.6),
    ("thinking", [(0.0, {"state": "transcribing"}), (0.5, {"state": "thinking"})], 3.0),
    ("thinking-rook", [(0.0, {"state": "transcribing"}), (0.5, {"state": "thinking"})], 6.5),
    ("speaking", [(0.0, {"state": "thinking"}), (0.5, {"state": "speaking"})], 3.0),
    ("sending", [(0.0, {"state": "thinking"}), (0.3, {"state": "thinking", "activity": "t3_thread_send"})], 3.0),
    ("running", [(0.0, {"state": "thinking"}), (0.3, {"state": "thinking", "activity": "Bash"})], 3.0),
]


def desktop(out, scale=3):
    import cairo
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    overlay.FORM_FOR_STATE["listening"] = "halo"  # The ring the owner calls "the circular thing that says listening".
    for name, script, at in DESKTOP_STATES:
        scene, t = overlay._simulate(script, at, overlay._phrase if name == "listening" else overlay._speech, 0)
        w, h = overlay.ORB_W, overlay.ORB_H
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w * scale, h * scale)
        surface.set_device_scale(scale, scale)
        cr = cairo.Context(surface)
        cr.set_source_rgb(0.043, 0.047, 0.059)  # The phone's background, TERM_BG.
        cr.paint()
        scene.draw_swarm(cr, w, t)
        surface.write_to_png(str(out / f"desktop-{name}.png"))
    print(f"Desktop forms drawn in {out}.")


if __name__ == "__main__":
    export()
    if "--desktop" in sys.argv:
        desktop(sys.argv[sys.argv.index("--desktop") + 1])
