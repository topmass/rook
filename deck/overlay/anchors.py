"""Where Rook's overlay sits on the screen: one of five anchors, each a window rectangle for a given screen size.

Every anchor keeps two rules: nothing in the top 10 px (a WoW add-on draws a 1024 x 6 px data strip at the top
centre) and nothing in the middle third of the screen either way (the centre of the game).

The default is middle-right: below where WoW's minimap, zone name and coordinates end (Rook's wow skill reads the
coordinates there), over the quest tracker, which matters less. Middle-left is free outside a group, but WoW's
party frames sit there in a group, and party chat is what the Deck's chat replies are for.
"""

ANCHORS = ("middle-right", "middle-left", "top-right", "top-left", "bottom-center")
DEFAULT = "middle-right"


def normalise(anchor):
    a = str(anchor or "").strip().lower().replace("_", "-").replace(" ", "-")
    a = {"bottom-centre": "bottom-center", "right": "middle-right", "left": "middle-left"}.get(a, a)
    return a if a in ANCHORS else DEFAULT


def geometry(anchor, sw, sh):
    """(x, y, w, h) of the overlay window for this anchor on an sw x sh screen."""
    a = normalise(anchor)
    w = min(430, max(300, int(sw * 0.34)))
    if a in ("top-right", "top-left"):
        h = min(560, int(sh * 0.7))
        return (sw - w if a == "top-right" else 0), 10, w, h
    if a in ("middle-right", "middle-left"):
        y = max(int(sh * 0.33), 250)  # Below the minimap, its zone name and the coordinates beneath it.
        h = max(160, min(440, sh - y - 100))  # Above the bottom action bars.
        return (sw - w if a == "middle-right" else 0), y, w, h
    # bottom-center: a low strip above the main action bars, below the screen's middle third.
    w = min(520, int(sw * 0.42))
    h = 190
    y = max(int(sh * 2 / 3) + 4, sh - 95 - h)
    return (sw - w) // 2, y, w, min(h, sh - y)
