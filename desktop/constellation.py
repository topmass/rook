"""Constellation: a diagram that the model writes as one short line in its answer, drawn as filament lines that
Rook's own grains build, light and carry home (see filament.py).

The model writes {diagram TITLE | GRAPH} at the start of its answer, for example
    {diagram How a web page loads | browser > dns:globe > server* > data:database > page:file}
and may add a third section that draws a node's own shape as SVG path data on the icon grid (filament.shape):
    {diagram Launch | pad > rocket* | rocket: M0-10C4-6 4 2 3 6H-3C-4 2-4-6 0-10ZM-4 1-7 7H-3M4 1 7 7H3}
parse() reads the line and never refuses. layout() places the nodes as a star, a ring, a chain or layers, with threads
whose ends keep an even gap from each glyph and names that keep off every thread. build() gives a fixed budget of grain
records, and Constellation turns them into the presence path's targets each frame. Pure Python, with no GTK: the
overlay draws it as the scene form "constellation" (see Scene.diagram_form in overlay.py).

Self-check: /usr/bin/python desktop/constellation.py
"""

import math
import random
import re

import filament  # The look: line icons, the texture the overlay draws, and the Cairo fallback. Stdlib only at import.

BUDGET = 1600  # Grains while a constellation shows, whatever its size.
# Of the budget: the grains that build the icons, and those that run along the threads; the rest are the sparks that
# gather on the lit node. Once a line has drawn on, its grains go dark: the line itself is the filament layer.
GLYPH_SHARE, THREAD_SHARE = 0.88, 0.07
NODES_MAX, LINKS_MAX, LABEL_MAX, TITLE_MAX = 8, 12, 16, 60
SHAPES_MAX = 4  # Drawn shapes a diagram may give its nodes: a few keep the mark short and the first speech soon.
GAP = 13.0  # px from a glyph's circle to its thread's end, the same at every end.
MIN_THREAD = 56.0  # px: the shortest thread.
WIDTH_MAX = 700.0  # px: the widest layout, names included.
PAD = 20.0  # px of canvas round the layout.
BOW = 0.08  # A thread's control point sits this share of its length off the straight line.
QUIET, LEAD, KNOWN, LIT = 0.42, 0.55, 0.58, 1.4  # A node's light: unlit, the lead unlit, lit before, lit now.
RAMP, RUN = 0.35, 0.6  # s: a node's light ramp, and its incoming thread's light run from source to head.
STAGGER, LAND = 0.07, 0.55  # s: between nodes leaving Rook, and each node's flight.
NAME_FADE = 0.45  # s
DUST_FADE, HANDBACK = 0.45, 0.25  # s: a node's grains fade as its line draws on, and come back at the exit.
SPARKS = 34  # Spark records per constellation; they stay dark (the lit node glows in its filament line).

ICONS = frozenset(filament.ICONS) - {"dot"}  # Only icons the filament set draws; any other name is a ring.
SYNONYMS = {
    "db": "database", "data": "database", "sql": "database", "storage": "database", "store": "database",
    "postgres": "database", "table": "database", "api": "server", "backend": "server", "service": "server",
    "host": "server", "worker": "server", "you": "user", "me": "user", "person": "user", "owner": "user",
    "customer": "user", "people": "user", "cache": "chip", "memory": "chip", "cpu": "chip", "gpu": "chip",
    "web": "globe", "internet": "globe", "dns": "globe", "network": "globe", "world": "globe", "docs": "file",
    "doc": "file", "page": "file", "document": "file", "report": "file", "list": "file", "note": "file",
    "app": "browser", "ui": "browser", "frontend": "browser", "website": "browser", "site": "browser",
    "email": "mail", "inbox": "mail", "mailbox": "mail", "chat": "message", "sms": "message", "reply": "message",
    "shell": "terminal", "cli": "terminal", "thread": "terminal", "command": "terminal", "agent": "rook",
    "ai": "robot", "bot": "robot", "model": "robot", "llm": "robot", "mobile": "phone", "timer": "clock",
    "schedule": "clock", "cron": "clock", "time": "clock", "auth": "lock", "login": "lock", "password": "key",
    "secret": "key", "token": "key", "jobs": "queue", "job": "queue", "task": "queue", "script": "code",
    "repo": "code", "git": "code", "computer": "laptop", "desktop": "laptop", "pc": "laptop", "dir": "folder",
    "router": "wifi", "idea": "bulb", "search": "magnifier", "find": "magnifier", "settings": "gear",
    "config": "gear", "voice": "mic", "audio": "speaker", "sound": "speaker", "money": "coins", "cost": "coins",
    "home": "house", "power": "bolt", "energy": "bolt", "light": "bulb", "fire": "flame", "water": "drop",
}
ARROW = re.compile(r"(\s*(?:-+>|=+>|→|⟶|>)\s*|\s+(?:-{1,2}|—|–)\s+|\s*(?:--|—|–)\s*)")
MARK = re.compile(r"\{\s*diagram\b([^{}]*)\}", re.IGNORECASE)


def _singular(word):
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def guess_icon(label):
    """A stencil for a node's name: an exact icon name, then a synonym, last word first. None means an orb."""
    words = re.findall(r"[a-z0-9]+", label.lower())
    for word in reversed(words):
        for w in (word, _singular(word)):
            if w in ICONS:
                return w
            if SYNONYMS.get(w) in ICONS:
                return SYNONYMS[w]
    return None


def _clean(label):
    return " ".join(label.split()).strip(" '\"`.<>()[]")


def parse(line, shapes=None):
    """Return (title, nodes, links, repairs) for a mark's inside or a whole mark. nodes are dicts with label, icon and
    lead, in the order the line first names them. links are (a, b, arrow) index triples. A third section after a
    second "|", "name: PATH; name: PATH", and shapes, a {name: PATH} dict, give nodes shapes drawn as SVG path data
    (filament.shape), at most SHAPES_MAX. It never refuses: what it cannot read is dropped or guessed, and each repair
    is a sentence for the builders' log, never for the model."""
    repairs = []
    text = (line or "")[:2000].strip()  # The arrow pattern backtracks on long runs of spaces: keep it short.
    whole = MARK.fullmatch(text)
    if whole:
        text = whole[1]
    title, graph = text.split("|", 1) if "|" in text else ("", text)
    graph, drawn = graph.split("|", 1) if "|" in graph else (graph, "")
    title = " ".join(title.split())
    if len(title) > TITLE_MAX:
        title = title[:TITLE_MAX].rstrip()
        repairs.append("title cut")
    nodes, index, links, seen = [], {}, [], set()

    def node(token):
        lead = "*" in token
        label, _, icon = token.replace("*", "").partition(":")
        label = _clean(label)
        if not label:
            if token.strip():
                repairs.append(f"dropped {token.strip()!r}")
            return None
        if len(label) > LABEL_MAX:
            repairs.append(f"cut {label!r}")
            label = label[:LABEL_MAX].rstrip()
        key = label.casefold()
        if key in index:
            nodes[index[key]]["lead"] |= lead
            return index[key]
        if len(nodes) >= NODES_MAX:
            repairs.append(f"dropped node {label!r}")
            return None
        icon = icon.strip().lower()
        if icon and icon not in ICONS:
            repairs.append(f"unknown icon {icon!r}")
            icon = ""
        index[key] = len(nodes)
        nodes.append({"label": label, "icon": icon or guess_icon(label), "lead": lead})
        return index[key]

    for chain in re.split(r"[;\n]", graph):
        hops = ARROW.split(chain)
        prev, arrow = None, True
        for j, hop in enumerate(hops):
            if j % 2:
                arrow = ">" in hop or "→" in hop or "⟶" in hop
                continue
            group = [k for k in (node(t) for t in hop.split(",")) if k is not None]
            for a in prev or ():
                for b in group:
                    pair = frozenset((a, b))
                    if a == b or pair in seen:
                        continue
                    if len(links) >= LINKS_MAX:
                        repairs.append("dropped a link past twelve")
                        continue
                    seen.add(pair)
                    links.append((a, b, arrow))
            prev = group or prev
    if len(nodes) < 2:
        if nodes or graph.strip():
            repairs.append("fewer than two nodes: nothing drawn")
        return title, [], [], repairs[:20]
    wanted = [entry.partition(":")[::2] for entry in drawn.split(";") if entry.strip()]
    if isinstance(shapes, dict):
        wanted += [(str(k), str(v)) for _, (k, v) in zip(range(NODES_MAX), shapes.items())]
    given = 0
    for name, path in wanted:
        k = index.get(_clean(name.replace("*", ""))[:LABEL_MAX].rstrip().casefold())
        if k is None:
            repairs.append(f"a shape for no node {name.strip()[:LABEL_MAX]!r}")
        elif given >= SHAPES_MAX:
            repairs.append(f"dropped a shape past {SHAPES_MAX}")
        else:
            icon, notes = filament.shape(path)
            repairs += [f"shape {nodes[k]['label']!r}: {note}" for note in notes]
            if icon:  # A path that draws nothing leaves the node its icon or ring.
                nodes[k]["icon"], given = icon, given + 1
    return title, nodes, links, repairs[:20]


# ---- layout ----

def _estimate(text):
    """A name's ink size in px without Pango: the overlay passes the real one."""
    return 9.0 * len(text) + 2.0, 12.0


def _qpt(c, u):
    (x0, y0), (x1, y1), (x2, y2) = c
    v = 1.0 - u
    return v * v * x0 + 2 * v * u * x1 + u * u * x2, v * v * y0 + 2 * v * u * y1 + u * u * y2


def _kind(n, links):
    """star, ring, chain or layers, and for a star its hub, for a chain its order."""
    adj = [set() for _ in range(n)]
    for a, b, _ in links:
        adj[a].add(b)
        adj[b].add(a)
    if n >= 4:
        hub = max(range(n), key=lambda k: len(adj[k]))
        if len(adj[hub]) == n - 1:
            return "star", hub
    degrees = [len(s) for s in adj]
    connected = _connected(adj)
    if n >= 3 and len(links) == n and connected and all(d == 2 for d in degrees):
        return "ring", None
    if len(links) == n - 1 and connected and max(degrees) <= 2:
        ends = [k for k in range(n) if degrees[k] == 1]
        heads = {b for _, b, arrow in links if arrow}
        start = min(ends, key=lambda k: (k in heads, k))  # The end no arrow points to, else the one named first.
        order, prev = [start], None
        while len(order) < n:
            nxt = next(k for k in adj[order[-1]] if k != prev)
            prev = order[-1]
            order.append(nxt)
        return "chain", order
    return "layers", None


def _connected(adj):
    seen, todo = {0}, [0]
    while todo:
        for k in adj[todo.pop()]:
            if k not in seen:
                seen.add(k)
                todo.append(k)
    return len(seen) == len(adj)


def _layers(n, links):
    """Columns by longest path, at most four nodes a column, each ordered by the mean of its neighbours."""
    out = [[] for _ in range(n)]
    for a, b, _ in links:
        out[a].append(b)
    state, order = [0] * n, []

    def visit(k):  # Depth first; an edge back into the path is ignored, so a cycle still lays out.
        state[k] = 1
        for m in out[k]:
            if state[m] == 0:
                visit(m)
        state[k] = 2
        order.append(k)

    for k in range(n):
        if state[k] == 0:
            visit(k)
    order.reverse()
    rank = {k: j for j, k in enumerate(order)}
    layer = [0] * n
    for k in order:
        for m in out[k]:
            if rank[m] > rank[k]:
                layer[m] = max(layer[m], layer[k] + 1)
    cols = [[] for _ in range(max(layer) + 1)]
    for k in range(n):
        cols[layer[k]].append(k)
    j = 0
    while j < len(cols):  # At most four a column: the rest move one column right.
        if len(cols[j]) > 4:
            if j + 1 == len(cols):
                cols.append([])
            cols[j + 1] = cols[j][4:] + cols[j + 1]
            cols[j] = cols[j][:4]
        j += 1
    nbr = [set() for _ in range(n)]
    for a, b, _ in links:
        nbr[a].add(b)
        nbr[b].add(a)
    for sweep in (range(1, len(cols)), range(len(cols) - 2, -1, -1)):
        for j in sweep:
            ref = cols[j - 1] if sweep.step > 0 else cols[j + 1]
            place = {k: i for i, k in enumerate(ref)}
            cols[j].sort(key=lambda k: (sum(place[m] for m in nbr[k] if m in place)
                                        / max(1, sum(1 for m in nbr[k] if m in place)))
                         if any(m in place for m in nbr[k]) else 99)
    return [c for c in cols if c]


def _need(r, a, b):
    return r[a] + r[b] + 2 * GAP + MIN_THREAD


def _place(kind, extra, n, links, r, s):
    """Node centres for kind at spread s (1 is comfortable; smaller packs it tighter, never under the shortest thread)."""
    pos = [(0.0, 0.0)] * n
    if kind == "star":
        hub = extra
        spokes = [k for k in range(n) if k != hub]
        ry = max(_need(r, hub, k) for k in spokes) + 24
        rx = max(ry, ry * 1.4 * s)
        for j, k in enumerate(spokes):
            a = -math.pi / 2 + 2 * math.pi * j / len(spokes)
            pos[k] = (rx * math.cos(a), ry * math.sin(a))
    elif kind == "ring":
        angles = [-math.pi / 2 + 2 * math.pi * j / n for j in range(n)]
        unit = [(1.4 * s * math.cos(a), math.sin(a)) for a in angles]
        chord = min(math.dist(unit[j], unit[(j + 1) % n]) for j in range(n))
        ry = (max(_need(r, j, (j + 1) % n) for j in range(n)) + 30) / chord
        pos = [(ry * x, ry * y) for x, y in unit]
    elif kind == "chain":
        order = extra
        if n <= 6:
            dx = min(190.0, 610.0 / (n - 1)) * s
            amp = 40.0
            for j in range(n - 1):
                need = _need(r, order[j], order[j + 1])
                amp = max(amp, math.sqrt(max(0.0, need * need - dx * dx)) / 2)
            for j, k in enumerate(order):
                pos[k] = ((j - (n - 1) / 2) * dx, amp if j % 2 == 0 else -amp)
        else:  # A snake: the first half left to right, the rest right to left beneath it.
            top = (n + 1) // 2
            dx = min(190.0, 610.0 / (top - 1)) * s
            half = max(_need(r, order[top - 1], order[top]), 150.0) / 2 + 10  # The rows wave 10 px.
            for j, k in enumerate(order):
                col = j if j < top else top - 1 - (j - top) - (0 if n % 2 == 0 else 0.5)
                y = -half if j < top else half
                pos[k] = ((col - (top - 1) / 2) * dx, y + (10.0 if j % 2 else -10.0))
    else:
        cols = _layers(n, links)
        dx = min(210.0, 620.0 / max(1, len(cols) - 1)) * s
        for j, col in enumerate(cols):
            dy = max(140.0, max((r[a] + r[b] + 2 * GAP + 40 for a, b in zip(col, col[1:])), default=0))
            for i, k in enumerate(col):
                pos[k] = ((j - (len(cols) - 1) / 2) * dx, (i - (len(col) - 1) / 2) * dy)
    return pos


def _curve(pa, pb, ra, rb, bow):
    """A thread from a to b: each end exactly r + GAP from its node's centre, bowed bow px to the right of travel."""
    (ax, ay), (bx, by) = pa, pb
    d = math.hypot(bx - ax, by - ay) or 1.0
    ux, uy = (bx - ax) / d, (by - ay) / d
    p0 = (ax + ux * (ra + GAP), ay + uy * (ra + GAP))
    p2 = (bx - ux * (rb + GAP), by - uy * (rb + GAP))
    mx, my = (p0[0] + p2[0]) / 2, (p0[1] + p2[1]) / 2
    return p0, (mx - uy * bow, my + ux * bow), p2


def _threads(pos, r, links):
    """Each thread bowed BOW of its length; one that passes a third node's circle bows harder, away from it."""
    curves = []
    for a, b, _ in links:
        length = math.dist(pos[a], pos[b]) - r[a] - r[b] - 2 * GAP
        bow = BOW * length
        c = _curve(pos[a], pos[b], r[a], r[b], bow)
        for k in range(len(pos)):
            if k in (a, b):
                continue
            for _ in range(8):
                if min(math.dist(_qpt(c, u / 12), pos[k]) for u in range(13)) >= r[k] + GAP:
                    break
                (ax, ay), (bx, by) = pos[a], pos[b]
                side = (bx - ax) * (pos[k][1] - ay) - (by - ay) * (pos[k][0] - ax)  # > 0: k is to the right.
                bow = -math.copysign(abs(bow) + 0.08 * length, side)
                c = _curve(pos[a], pos[b], r[a], r[b], bow)
        curves.append(c)
    return curves


def _box_hits(box, pos, r, curves, boxes, own):
    x0, y0, x1, y1 = box[0] - 4, box[1] - 3, box[0] + box[2] + 4, box[1] + box[3] + 3
    for c in curves:
        for u in range(25):
            x, y = _qpt(c, u / 24)
            if x0 <= x <= x1 and y0 <= y <= y1:
                return True
    for k, (px, py) in enumerate(pos):
        if k != own and math.hypot(max(x0 - px, 0, px - x1), max(y0 - py, 0, py - y1)) < r[k] + 2:
            return True
    return any(x0 < b[0] + b[2] and b[0] < x1 and y0 < b[1] + b[3] and b[1] < y1 for b in boxes)


def _names(kind, pos, r, curves, sizes, hub):
    """Each name's ink box (x, y, w, h): below for chains and layers, outward for stars and rings, else the next of
    four sides that no thread, glyph or other name touches."""
    boxes = []
    for k, ((px, py), (w, h)) in enumerate(zip(pos, sizes)):
        rr = r[k] * 1.08
        low = high = None
        if kind == "chain":  # A row's names share one line: under its lowest glyph, or over its highest.
            row = [j for j in range(len(pos)) if abs(pos[j][1] - py) < 25]
            low, high = max(pos[j][1] + r[j] * 1.08 for j in row), min(pos[j][1] - r[j] * 1.08 for j in row)
        sides = {"below": (px - w / 2, (py + rr if low is None else low) + 8),
                 "above": (px - w / 2, (py - rr if high is None else high) - 8 - h),
                 "right": (px + rr + 16, py - h / 2), "left": (px - rr - 16 - w, py - h / 2)}
        order = ["below", "right", "left", "above"]
        if kind in ("star", "ring") and k != hub:
            ux, uy = px / (math.hypot(px, py) or 1.0), py / (math.hypot(px, py) or 1.0)
            first = ("right" if ux > 0 else "left") if abs(ux) > 0.75 else "below" if uy > 0 else "above"
            order = [first] + [s for s in ("below", "right", "left", "above") if s != first]
        pick = None
        for side in order:
            box = (*sides[side], w, h)
            if not _box_hits(box, pos, r, curves, boxes, k):
                pick = box
                break
        boxes.append(pick or (*sides[order[0]], w, h))
    return boxes


def layout(nodes, links, measure=_estimate):
    """Place parsed nodes and links. measure(text) gives a name's ink width and height in px. Returns a plan: kind,
    node centres pos and glyph radii r, thread curves, name and title boxes, and the canvas size; (0, 0) is the
    centre of the canvas, so the overlay centres it on Rook."""
    n = len(nodes)
    kind, extra = _kind(n, links)
    labels = [nd["label"].upper() for nd in nodes]
    sizes = [measure(t) for t in labels]
    for shrink in (1.0, 0.9, 0.8):  # Smaller glyphs only when the spokes cannot pack any tighter.
        base = (44.0 if n <= 6 else 36.0) * shrink
        r = [round(base * 1.3) if nd["lead"] else base for nd in nodes]
        s, last = 1.0, None
        for _ in range(10):  # Pack it tighter until it fits WIDTH_MAX, but never under the shortest thread.
            pos = _place(kind, extra, n, links, r, s)
            curves = _threads(pos, r, links)
            if last and any(math.dist(c[0], c[2]) < MIN_THREAD for c in curves):
                pos, curves, names, x0, x1 = last
                break
            names = _names(kind, pos, r, curves, sizes, extra if kind == "star" else None)
            x0 = min(min(p[0] - 1.25 * rr for p, rr in zip(pos, r)), min(b[0] for b in names))
            x1 = max(max(p[0] + 1.25 * rr for p, rr in zip(pos, r)), max(b[0] + b[2] for b in names))
            if x1 - x0 <= WIDTH_MAX:
                break
            last, s = (pos, curves, names, x0, x1), s * 0.93
        if x1 - x0 <= WIDTH_MAX:
            break
    cx = (x0 + x1) / 2
    pos = [(x - cx, y) for x, y in pos]
    curves = [tuple((x - cx, y) for x, y in c) for c in curves]
    names = [(b[0] - cx, b[1], b[2], b[3]) for b in names]
    y0 = min(min(p[1] - 1.25 * rr for p, rr in zip(pos, r)), min(b[1] for b in names))
    y1 = max(max(p[1] + 1.25 * rr for p, rr in zip(pos, r)), max(b[1] + b[3] for b in names))
    return {"kind": kind, "labels": labels, "pos": pos, "r": r, "links": links, "curves": curves, "names": names,
            "ink": (x0 - cx, y0, x1 - cx, y1)}


def finish(plan, title, measure=_estimate):
    """Put the title under the drawing and centre everything on (0, 0). measure gives the title's ink size in its own
    lettering. Returns the plan with its title box and canvas size."""
    x0, y0, x1, y1 = plan["ink"]
    tbox = None
    if title:
        w, h = measure(title.upper())
        tbox = (-w / 2, y1 + 30, w, h)  # Far enough under the names that it never reads as one.
        y1 = tbox[1] + h
        x0, x1 = min(x0, -w / 2), max(x1, w / 2)
    half_w = max(-x0, x1)
    cy = (y0 + y1) / 2
    shift = lambda p: (p[0], p[1] - cy)  # noqa: E731
    plan.update(pos=[shift(p) for p in plan["pos"]], curves=[tuple(shift(p) for p in c) for c in plan["curves"]],
                names=[(b[0], b[1] - cy, b[2], b[3]) for b in plan["names"]],
                title=title, title_box=None if tbox is None else (tbox[0], tbox[1] - cy, tbox[2], tbox[3]),
                size=(2 * math.ceil(half_w + PAD), 2 * math.ceil((y1 - y0) / 2 + PAD)))
    return plan


# ---- grains ----

def glyph_points(icon, count):
    """count points (x, y) for a node, spaced evenly along its filament icon's strokes, as shares of its radius."""
    return [(x * filament.GRID, y * filament.GRID) for x, y in filament.sample(filament.icon_name(icon), count)]


G, T, M = 0, 1, 3  # Record kinds: glyph, thread, spark.


def build(plan, nodes, budget=BUDGET, seed=0):
    """Grain records, exactly budget of them: glyphs share GLYPH_SHARE (the lead 1.3 times a share), threads
    THREAD_SHARE, sparks the rest. Each record is (kind, owner, a, b, c, ph): for a glyph grain its place about its
    node (a, b) and its brightness (c); for a thread grain its share along the thread (a); for a spark the angle (a)
    and reach (b) it gathers from, and the share of the icon's strokes it lands on (c)."""
    rng = random.Random(seed)
    links = plan["links"]
    sparks = budget - round(budget * (GLYPH_SHARE + THREAD_SHARE))
    thread_total = round(budget * THREAD_SHARE) if links else 0
    glyph_total = budget - sparks - thread_total
    weights = [1.3 if nd["lead"] else 1.0 for nd in nodes]
    counts = [int(glyph_total * w / sum(weights)) for w in weights]
    for k in range(glyph_total - sum(counts)):
        counts[k % len(counts)] += 1
    recs = []
    for k, (nd, count) in enumerate(zip(nodes, counts)):
        rr = plan["r"][k]
        for x, y in glyph_points(nd["icon"], count):
            recs.append((G, k, x * rr, y * rr, 0.92 + 0.16 * rng.random(), rng.random()))
    per = [thread_total // len(links) + (1 if e < thread_total % len(links) else 0) for e in range(len(links))] \
        if links else []
    for e, count in enumerate(per):
        for j in range(count):
            recs.append((T, e, (j + rng.random()) / count, 0.0, 0.0, rng.random()))
    for j in range(sparks):
        recs.append((M, 0, rng.uniform(0, 2 * math.pi), rng.uniform(1.35, 2.1), j / max(1, SPARKS) + rng.uniform(0, 0.02),
                     rng.random()))
    return recs


def _smooth(p):
    p = min(1.0, max(0.0, p))
    return p * p * (3 - 2 * p)


def _mix(a, b, k):
    return tuple(x + (y - x) * k for x, y in zip(a, b))


def _on(pts, u):
    """The point at share u of a polyline of evenly spaced parameter steps."""
    n = len(pts) - 1
    a = min(n - 1e-6, max(0.0, u * n))
    j = int(a)
    f = a - j
    return pts[j][0] + (pts[j + 1][0] - pts[j][0]) * f, pts[j][1] + (pts[j + 1][1] - pts[j][1]) * f


class Constellation:
    """One laid-out constellation: its light state, the grains' per-frame targets, and the filament layer's state.

    The drawing is the filament layer (lines()). The grains only move: they fly out from Rook and land on each icon's
    strokes, go dark as its line draws on, and light again to carry the drawing home at the exit (end()). Lighting a
    node is the lines' work alone: no loose grain flutters over them. targets() recomputes only what moves, so a settled
    constellation costs a few grains a frame."""

    def __init__(self, plan, nodes, recs):
        self.plan, self.nodes, self.recs = plan, nodes, recs
        self.n = len(nodes)
        n = len(recs)
        self.tx, self.ty, self.tb, self.tz = [0.0] * n, [0.0] * n, [0.0] * n, [0.0] * n
        self.by_node = [[] for _ in range(self.n)]
        self.by_link = [[] for _ in plan["links"]]
        self.sparks = []
        for i, rec in enumerate(recs):
            (self.by_node[rec[1]] if rec[0] == G else self.sparks if rec[0] == M else self.by_link[rec[1]]).append(i)
        self.curves = [[_qpt(c, j / 40) for j in range(41)] for c in plan["curves"]]
        self.lengths = [sum(math.dist(a, b) for a, b in zip(p, p[1:])) or 1.0 for p in self.curves]
        self.icons = [filament.icon_name(nd["icon"]) for nd in nodes]
        self.elements = filament.elements(plan, nodes)  # The filament layer's strokes: nodes, then threads.
        self.state = [0.0] * (12 * len(self.elements))
        self.level = [(LEAD if nd["lead"] else QUIET,) * 2 + (-math.inf,) for nd in nodes]  # (from, to, since)
        self.lit, self.known, self.focal, self.lit_at = set(), set(), None, -math.inf
        self.ending = None  # When the exit began: the lines hand the drawing back to the grains.
        self.drawn = {}  # What each node, thread and the sparks were last computed for.
        self.dy = None

    def light(self, step, now):
        """Light the nodes a step names, 1 for the first node: an int or a list. 0 lights none and leaves every node
        known, as at the end of the voice."""
        steps = step if isinstance(step, list) else [step]
        valid = [s - 1 for s in steps if isinstance(s, int) and not isinstance(s, bool) and 0 < s <= self.n]
        lit = set(valid)
        self.known |= self.lit - lit
        if not valid:
            self.known |= set(range(self.n))
        self.lit = lit
        for k in range(self.n):
            to = LIT if k in lit else KNOWN if k in self.known else LEAD if self.nodes[k]["lead"] else QUIET
            if to != self.level[k][1]:
                self.level[k] = (self._level(k, now), to, now)
        if lit:
            self.lit_at = now
        self.focal = valid[-1] if valid else None

    def end(self, now):
        """The exit: the lines fade as the grains light on them again, so the grains can carry the drawing home."""
        if self.ending is None:
            self.ending = now

    def _level(self, k, now):
        a, b, since = self.level[k]
        return a + (b - a) * _smooth((now - since) / RAMP)

    def _glow(self, k, now):
        """A node's light from 0 (quiet) to 1 (lit now); a known node sits near 0.5. A node lit through a thread
        brightens as the thread's light reaches it, not at the step."""
        fed = k == self.focal and any(b == k for _, b, _ in self.plan["links"])
        lv = self._level(k, now - 0.42 if fed else now)
        for (a, x), (b, y) in zip(((QUIET, 0.0), (LEAD, 0.18), (KNOWN, 0.5)), ((LEAD, 0.18), (KNOWN, 0.5), (LIT, 1.0))):
            if lv <= b:
                return x + (y - x) * max(0.0, (lv - a) / (b - a))
        return 1.0

    def _link(self, e, now):
        """A thread's light: the node it lights (or None), whether its node is known, and how far the light has run."""
        a, b, arrow = self.plan["links"][e]
        hot = b if b in self.lit else a if not arrow and a in self.lit else None
        warm = b in self.known or (not arrow and a in self.known)
        return hot, warm, min(1.0, (now - self.lit_at) / RUN) if hot is not None else 1.0

    def _out(self, now):
        return 1.0 if self.ending is None else 1.0 - _smooth((now - self.ending) / (1.2 * HANDBACK))

    def name_alpha(self, k, t, now):
        """A node's name: it fades in once its glyph has formed, never before, and its strength follows its light."""
        appear = _smooth((t - STAGGER * k - LAND - 0.25) / NAME_FADE)
        lvl = self._level(k, now)
        return appear * (0.72 + 0.28 * min(1.0, max(0.0, (lvl - QUIET) / (LIT - QUIET))) ** 0.6)

    def title_alpha(self, t):
        return 0.68 * _smooth((t - STAGGER * (self.n - 1) - LAND - 0.25) / NAME_FADE)  # With the last name.

    def lines(self, t, now, light=False):
        """The filament layer's state, t seconds after the reveal: 12 floats per element (filament.elements order),
        colour r, g, b and alpha; draw-on share, lit run share (or -1), runs back (0 or 1), glow; exit fade, pen tip
        (0 or 1), the lit run's alpha and glow. The list is reused: callers must not change it."""
        st, out = self.state, self._out(now)
        gold, champ, hot_rgb = ((filament.LIGHT[c] for c in (filament.GOLD, filament.CHAMP, filament.HOT)) if light
                                else (filament.GOLD, filament.CHAMP, filament.HOT))
        for k, nd in enumerate(self.nodes):
            p = _smooth((t - (STAGGER * k + 0.12 + LAND) + 0.22) / 0.55)
            lv = self._glow(k, now)
            lead = 0.08 if nd["lead"] else 0.0
            rgb = _mix(_mix(gold, champ, 0.2 + lead), hot_rgb, _smooth((lv - 0.45) / 0.55))
            st[12 * k:12 * k + 12] = (*rgb, (0.50 + lead + 0.50 * lv) * out, p, -1.0, 0.0,
                                      (0.08 + 0.75 * lv ** 1.5) * out, out, 1.0 if 0.0 < p < 1.0 else 0.0,
                                      0.9 * out, 0.6 * out)
        for e, (a, _, arrow) in enumerate(self.plan["links"]):
            shown = _smooth((t - (STAGGER * a + 0.12 + LAND * 0.8) - 0.18) / 0.5)
            hot, warm, run = self._link(e, now)
            j = 12 * (self.n + e)
            st[j:j + 12] = (*_mix(gold, champ, 0.3 if warm else 0.0), (0.50 if warm else 0.30) * out, shown,
                            run if hot is not None else -1.0, 1.0 if hot is not None and hot == a and not arrow else 0.0,
                            0.10 * out, out, 0.0, 0.95 * out, 0.55 * out)
        return st

    def targets(self, t, now, dy=0.0):
        """tx, ty, tb, tz for every record, t seconds after the reveal; the drawing sits dy below Rook's centre. The
        lists are reused: callers must not change them."""
        if dy != self.dy:
            self.dy, self.drawn = dy, {}
        tx, ty, tb, tz = self.tx, self.ty, self.tb, self.tz
        recs, pos = self.recs, self.plan["pos"]
        back = 0.0 if self.ending is None else _smooth((now - self.ending) / HANDBACK)
        for k in range(self.n):
            end = STAGGER * k + 0.12 + LAND
            px, py = pos[k][0], pos[k][1] + dy
            if t < end:  # In flight from Rook's centre: each grain leaves at its own moment, lands in LAND s.
                self.drawn.pop(("n", k), None)
                level = 0.9 * self._level(k, now)
                for i in self.by_node[k]:
                    _, _, ox, oy, w, _ = recs[i]
                    p = min(1.0, max(0.0, (t - STAGGER * k - 0.12 * (i * 0.618 % 1.0)) / LAND))
                    f = 1 - (1 - p) ** 3  # Out fast and slow to land, so the springs arrive with their targets.
                    tx[i], ty[i], tb[i], tz[i] = (px + ox) * f, (py + oy) * f, level * w * (0.25 + 0.75 * p), 0.0
                continue
            # Landed: the grains sit on the strokes and fade as the line draws on, and light again at the exit.
            gain = max(1.0 - _smooth((t - end + 0.05) / DUST_FADE), back)
            key = (round(gain, 3), round(self._level(k, now), 3) if gain > 0 else 0.0)
            if self.drawn.get(("n", k)) == key:
                continue
            self.drawn[("n", k)] = key
            level = 0.9 * key[1] * gain
            for i in self.by_node[k]:
                _, _, ox, oy, w, _ = recs[i]
                tx[i], ty[i], tb[i], tz[i] = px + ox, py + oy, level * w, 0.0
        for e in range(len(self.plan["links"])):  # The threads' grains wait dark on them: the lines carry the light.
            if self.drawn.get(("l", e)):
                continue
            self.drawn[("l", e)] = True
            for i in self.by_link[e]:
                x, y = _on(self.curves[e], recs[i][2])
                tx[i], ty[i], tb[i], tz[i] = x, y + dy, 0.0, 0.0
        if not self.drawn.get("s"):  # So do the sparks: a lit node glows in its own line, never in loose grains.
            self.drawn["s"] = True
            for i in self.sparks:
                tb[i] = 0.0
        return tx, ty, tb, tz


def make(line, measure=_estimate, budget=BUDGET, measure_title=None, shapes=None):
    """parse, layout, finish and build in one: (title, nodes, Constellation or None, repairs)."""
    title, nodes, links, repairs = parse(line, shapes)
    if not nodes:
        return title, nodes, None, repairs
    plan = finish(layout(nodes, links, measure), title, measure_title or measure)
    return title, nodes, Constellation(plan, nodes, build(plan, nodes, budget)), repairs


def _check():
    t, n, links, rep = parse("How a web page loads | browser > dns:globe > server* > data:database > cache:chip > "
                             "page:file")
    assert t == "How a web page loads" and [x["label"] for x in n] == ["browser", "dns", "server", "data", "cache",
                                                                       "page"]
    assert [x["icon"] for x in n] == ["browser", "globe", "server", "database", "chip", "file"] and n[2]["lead"]
    assert links == [(0, 1, True), (1, 2, True), (2, 3, True), (3, 4, True), (4, 5, True)] and not rep
    t, n, links, rep = parse("{diagram agent:rook* > threads:terminal, mailbox:mail, work list:file, phone, timers:clock}")
    assert t == "" and len(n) == 6 and len(links) == 5 and n[3]["label"] == "work list" and n[4]["icon"] == "phone"
    assert parse("a, b > c")[2] == [(0, 2, True), (1, 2, True)]
    assert parse("a > b > c; b - d")[2] == [(0, 1, True), (1, 2, True), (1, 3, False)]
    assert parse("a > b; b > a; a > a")[2] == [(0, 1, True)]  # A repeated link is drawn once; a self link never.
    t, n, links, rep = parse("x | " + " > ".join(f"n{k}" for k in range(11)))
    assert len(n) == 8 and len(links) == 7 and sum("dropped node" in r for r in rep) == 3
    t, n, links, rep = parse("solo")
    assert n == [] and rep  # Fewer than two nodes draws nothing, and says so to the log.
    assert parse("")[1] == [] and parse("|")[1] == [] and parse(">>,,;")[1] == []
    t, n, links, rep = parse("a:nosuchicon > database server > you > ,, > b")
    assert n[0]["icon"] is None and n[1]["icon"] == "server" and n[2]["icon"] == "user" and rep
    assert len(links) == 3  # ",, >" drops the empty hop and keeps the chain.
    assert parse("e-mail > web-site")[1][0]["label"] == "e-mail"  # A hyphen inside a word is no line.
    for junk in ("{diagram}", "{{{", "a > > > b", "*:* > :x", "a" * 99 + " > b", "→→", "a—b"):
        parse(junk)
    import time
    started = time.perf_counter()  # Long runs of spaces stay fast, and the repairs stay few.
    t, n, links, rep = parse("a" + " " * 200_000 + "b > c")
    assert time.perf_counter() - started < 0.5 and len(parse(", ".join(f"x{k}:bad" for k in range(99)))[3]) <= 20
    # Drawn shapes: the third section binds each path to its node by name, and the graph parses as before.
    heart = "M0 9C-6 4-10 0-10-4A5 5 0 0 1 0-6A5 5 0 0 1 10-4C10 0 6 4 0 9Z"
    plain = parse("Love | you > Heart* > page:file")
    t, n, links, rep = parse(f"Love | you > Heart* > page:file | heart: {heart}; PAGE: M-5-8H5V8H-5Z; ghost: M0 0L1 1")
    assert (t, [x["label"] for x in n], links) == (plain[0], [x["label"] for x in plain[1]], plain[2])
    assert n[0]["icon"] == "user" and n[1]["lead"]
    assert n[1]["icon"] == filament.shape(heart)[0] and n[2]["icon"].startswith("~") and len(rep) == 1, rep
    assert parse(f"{{diagram x | a > b | b: {heart}}}")[1][1]["icon"].startswith("~")  # A whole mark too.
    assert parse("x | a > b", {"a": heart, "b": "M0 0L4 4"})[1][0]["icon"] == filament.shape(heart)[0]
    t, n, _, rep = parse("x | a > b | a: nonsense; b: M5 5")  # A path that draws nothing keeps the icon or ring.
    assert [x["icon"] for x in n] == [None, None] and rep
    many = "; ".join(f"n{k}: M0 0L{k} 6" for k in range(6))
    t, n, _, rep = parse("x | " + " > ".join(f"n{k}" for k in range(6)) + " | " + many)
    assert sum(x["icon"].startswith("~") for x in n if x["icon"]) == SHAPES_MAX and any("past" in r for r in rep)
    assert parse("x | a > b | ")[1] == parse("x | a > b")[1]
    con = make(f"x | a > b | a: {heart}")[2]
    assert con.icons[0].startswith("~") and len(glyph_points(con.nodes[0]["icon"], 50)) == 50

    def check(line, kind):
        title, nodes, con, _ = make(line)
        plan = con.plan
        assert plan["kind"] == kind, (line, plan["kind"])
        pos, r = plan["pos"], plan["r"]
        for (a, b, _), c in zip(plan["links"], plan["curves"]):  # The even gap, and every thread long enough.
            assert abs(math.dist(c[0], pos[a]) - r[a] - GAP) < 1e-6 and abs(math.dist(c[2], pos[b]) - r[b] - GAP) < 1e-6
            assert math.dist(c[0], c[2]) >= MIN_THREAD - 1e-6, (line, math.dist(c[0], c[2]))
            for k in range(len(pos)):  # No thread runs through a third node.
                if k not in (a, b):
                    assert min(math.dist(_qpt(c, u / 40), pos[k]) for u in range(41)) >= r[k] + GAP - 3, (line, k)
        for k, box in enumerate(plan["names"]):  # No name over a thread.
            assert not _box_hits((box[0] + 3, box[1] + 2, box[2] - 6, box[3] - 4), pos, r, plan["curves"], [], k), \
                (line, plan["labels"][k])
        assert plan["size"][0] <= WIDTH_MAX + 2 * PAD + 2, (line, plan["size"])
        # An arrowhead's tip keeps the gap from its glyph, and the rest of the head lies further out.
        for (a, b, arrow), strokes in zip(plan["links"], con.elements[len(nodes):]):
            for pts, _, _ in strokes[1:] if arrow else ():
                assert min(math.dist(p, pos[b]) for p in pts) >= r[b] + GAP - 0.5, line
        if kind == "chain":  # Names under one row share one line. A name a thread moves aside does not count.
            rows = {}
            for (x, y), box in zip(pos, plan["names"]):
                if box[1] > y:
                    rows.setdefault(round(y / 25), set()).add(round(box[1], 3))
            assert all(len(ys) == 1 for ys in rows.values()), (line, rows)
        assert len(con.recs) == BUDGET
        tx, ty, tb, tz = con.targets(5.0, 5.0)
        assert len(tx) == BUDGET and all(math.isfinite(v) for v in tx + ty + tb + tz)
        st = con.lines(5.0, 5.0)
        assert len(st) == 12 * (len(nodes) + len(plan["links"])) and all(math.isfinite(v) for v in st)
        assert all(st[12 * k + 4] == 1.0 for k in range(len(nodes) + len(plan["links"])))  # Drawn on by 5 s.
        assert max(tb[i] for idx in con.by_node for i in idx) == 0.0  # Once drawn, the grains have gone dark.
        return con

    check("browser > dns:globe > server* > data:database > cache:chip > page:file", "chain")
    check("agent:rook* > threads:terminal, mailbox:mail, work list:file, phone, timers:clock", "star")
    check("plan > build > test > ship > plan", "ring")
    check("a > b > c", "chain")
    check("a > b", "chain")
    check("one > two > three > four > five > six > seven > eight", "chain")
    check("one > two > three > four > five > six > seven", "chain")
    check("you > app > api > db; api > cache; api > queue > worker", "layers")
    check("a > b, c, d; b > e; c > e; d > e; e > f", "layers")
    check("hub - a, b, c; a - b", "star")
    for size in range(2, 9):  # The budget holds for every size.
        con = check(" > ".join(f"node {k}" for k in range(size)), "chain")
        assert sum(1 for rec in con.recs if rec[0] == G) >= 0.6 * BUDGET
    # Light: a step lights its node, the one before stays known, and 0 leaves all known with no focal node.
    _, _, con, _ = make("a > b > c")
    con.targets(3.0, 3.0)
    con.light(2, 3.0)
    con.targets(4.0, 4.0)
    st = con.lines(4.0, 4.0)
    assert con.focal == 1 and st[12 + 3] > st[24 + 3] + 0.3  # Lit, and white-hot:
    assert all(abs(a - b) < 1e-6 for a, b in zip(st[12:15], filament.HOT))
    assert st[12 * 3 + 5] == 1.0 and st[12 * 4 + 5] == -1.0  # The thread into b has run its light; b to c has none.
    lit = [i for i in con.sparks + [i for e in con.by_link for i in e] if con.tb[i] > 0]
    assert not lit, lit  # Lighting b lights no loose grain: the lines alone carry the light.
    con.light(3, 5.0)
    con.light([1, 2], 6.0)
    assert con.lit == {0, 1} and con.focal == 1 and 2 in con.known
    con.light(0, 7.0)
    assert con.focal is None and con.known == {0, 1, 2}
    # A settled frame recomputes nothing: every node, thread and spark keeps what it had.
    con.targets(20.0, 20.0)
    before = dict(con.drawn)
    con.targets(20.0 + 1 / 60, 20.0 + 1 / 60)
    assert con.drawn == before
    # The exit: the lines fade and the grains light on the strokes again, ready to fly home.
    con.end(21.0)
    con.targets(21.5, 21.5)
    assert con.lines(21.5, 21.5)[3] == 0.0 and min(con.tb[i] for i in con.by_node[0]) > 0.2
    print("constellation: ok")


if __name__ == "__main__":
    _check()
