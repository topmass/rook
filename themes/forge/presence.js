// Theme presence: plays a forge-baked theme pack (flipbook kind) on a 2D canvas. No framework, no network beyond the
// pack's own files, which it loads from `base` (same origin, so it fits the phone app's CSP).
//
//   ThemePresence.loadPack(base)            -> {pack, icons}       base like "/themes/nova/" or "../nova/"
//   new ThemePresence.Presence(pack, icons)  .setState(state, now) .level .label .draw(ctx, x, y, size, now)
//   ThemePresence.phone({base})              -> the phone app's RookPresence interface:
//                                              load(canvas), set(mood, kind, sendLine), setLevel(v), form(), stats,
//                                              wake(), halt(), forms()
"use strict";

const ThemePresence = (() => {
  // Ease in and out, so a change starts and ends gently and the middle carries it.
  const ease = (x) => { x = Math.min(Math.max(x, 0), 1); return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; };
  const lerp = (a, b, f) => a + (b - a) * f;

  function loadScript(src) {
    return new Promise((ok, fail) => {
      const s = document.createElement("script");
      s.src = src;
      s.onload = ok;
      s.onerror = () => fail(new Error("cannot load " + src));
      document.head.append(s);
    });
  }

  // One baked icon. Its atlas loads on first use, so a phone holds only the icons it has shown.
  class Flipbook {
    constructor(name, spec, base) {
      Object.assign(this, spec);
      this.name = name;
      this.src = base + spec.image;
      this.img = null;
      this.loading = null;
    }
    ready() {
      if (this.img) return true;
      if (!this.loading) {
        this.loading = new Promise((ok) => {
          const i = new Image();
          i.onload = () => { this.img = i; ok(); };
          i.onerror = () => ok();
          i.src = this.src;
        });
      }
      return false;
    }
    frameAt(seconds) {
      const f = Math.floor(seconds * this.fps);
      return this.loop === false ? Math.max(0, Math.min(f, this.frames - 1)) : ((f % this.frames) + this.frames) % this.frames;
    }
    duration() { return this.frames / this.fps; }
    // Draws frame `seconds` of `layer`, `size` pixels across, centred on (x, y). `stretch` scales height only.
    draw(ctx, x, y, size, seconds, layer = 0, alpha = 1, scale = 1, stretch = 1, angle = 0) {
      if (alpha <= 0.002 || !this.ready()) return;
      const k = layer * this.frames + this.frameAt(seconds), cols = this.grid[0], c = this.cell;
      const w = size * scale, h = w * stretch;
      ctx.save();
      ctx.globalAlpha *= alpha;
      ctx.translate(x, y);
      if (angle) ctx.rotate(angle);
      ctx.drawImage(this.img, (k % cols) * c, Math.floor(k / cols) * c, c, c, -w / 2, -h / 2, w, h);
      ctx.restore();
    }
  }

  async function loadPack(base) {
    const name = base.replace(/\/$/, "").split("/").pop();
    if (!window.FORGE_PACKS?.[name]) await loadScript(base + "pack.js");
    const pack = window.FORGE_PACKS[name];
    const icons = {};
    for (const [n, s] of Object.entries(pack.icons)) if (s.image) icons[n] = new Flipbook(n, s, base);
    // Warm the icons a presence needs first.
    for (const n of ["rest", pack.states.thinking?.rook, pack.transition?.flash, "dispatch", "dispatch_in", "strand_head"]) if (icons[n]) icons[n].ready();
    await Promise.all(Object.values(icons).map((i) => i.loading).filter(Boolean));
    return { pack, icons };
  }

  const smooth01 = (x) => { x = Math.min(Math.max(x, 0), 1); return x * x * (3 - 2 * x); };
  const easeOut3 = (x) => 1 - Math.pow(1 - Math.min(Math.max(x, 0), 1), 3);
  const bez = (a, b, c, d, u) => {
    const v = 1 - u;
    return [v * v * v * a[0] + 3 * v * v * u * b[0] + 3 * v * u * u * c[0] + u * u * u * d[0],
            v * v * v * a[1] + 3 * v * v * u * b[1] + 3 * v * u * u * c[1] + u * u * u * d[1]];
  };
  // The dispatch's timing, in seconds (stage/dispatch.md).
  const Dispatch = { timing: { intro: 0.3, gap: 0.09, travel: 0.56, hold: 1.2, out: 0.45 } };
  // Nova's name colour: core mixed 45% with pink. Its quiet colour, for marks and "and N more".
  const NAME = "#ffafed", QUIET = "#a08ce0";

  // A send's strand from u0 to u1 of its curve, in Nova's material: an ink underlay (it carries the line on a light
  // desktop), a violet-to-pink plasma line, and white beads marching toward the name, one pass every 2.4 s.
  function drawStrand(ctx, curve, u0, u1, k, now, alpha, P) {
    const pts = [];
    for (let i = 0; i <= 40; i++) pts.push(curve(u0 + (u1 - u0) * i / 40));
    const path = () => { ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1]); for (const q of pts) ctx.lineTo(q[0], q[1]); };
    ctx.save();
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.globalAlpha = alpha;
    path(); ctx.strokeStyle = P.pink; ctx.globalAlpha = alpha * 0.16; ctx.lineWidth = 7 * k; ctx.stroke();
    path(); ctx.strokeStyle = P.ink; ctx.globalAlpha = alpha * 0.55; ctx.lineWidth = 3.4 * k; ctx.stroke();
    const g = ctx.createLinearGradient(pts[0][0], pts[0][1], pts[pts.length - 1][0], pts[pts.length - 1][1]);
    g.addColorStop(0, P.violet); g.addColorStop(1, P.pink);
    path(); ctx.strokeStyle = g; ctx.globalAlpha = alpha; ctx.lineWidth = 1.8 * k; ctx.stroke();
    let len = 0;
    for (let i = 1; i < pts.length; i++) len += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
    path(); ctx.setLineDash([2.2 * k, 9 * k]); ctx.lineDashOffset = -((now / 2.4) % 1) * 11.2 * k * Math.max(1, Math.round(len / (11.2 * k)));
    ctx.strokeStyle = P.core; ctx.globalAlpha = alpha * 0.9; ctx.lineWidth = 1.1 * k; ctx.stroke();
    ctx.restore();
  }

  // The outcome mark at a strand's end. All quiet: a breathing violet dot (no answer), a pink dot with one glint (landed), an
  // empty ring (did not land), three grains (cannot tell). Each has a thin ink rim so it holds on a light desktop.
  function drawMark(ctx, x, y, side, k, it, t, alpha, P) {
    if (it.more) return;
    const o = it.outcome, v = o?.value, ot = o ? t - o.at : 0;
    ctx.save();
    ctx.globalAlpha = alpha;
    const dot = (cx, cy, d, col) => {
      ctx.beginPath(); ctx.arc(cx, cy, d / 2 + 0.6 * k, 0, Math.PI * 2); ctx.fillStyle = P.ink; ctx.globalAlpha = alpha * 0.6; ctx.fill();
      ctx.beginPath(); ctx.arc(cx, cy, d / 2, 0, Math.PI * 2); ctx.fillStyle = col; ctx.globalAlpha = alpha; ctx.fill();
    };
    if (!v) {
      ctx.globalAlpha = alpha * (0.45 + 0.35 * (0.5 + 0.5 * Math.sin(t * 4)));
      dot(x, y, 2.1 * k, P.violet);
    } else if (v === "landed") {
      dot(x, y, 2.6 * k, P.pink);   // Filled pink, so on a light desktop it never reads as the empty ring.
      const g = 1 - Math.min(1, ot / 0.5);
      if (g > 0) {
        const r = 7 * k * (0.6 + 0.4 * g);
        ctx.globalAlpha = alpha * g;
        ctx.beginPath();
        ctx.moveTo(x - r, y); ctx.quadraticCurveTo(x, y, x, y - r); ctx.quadraticCurveTo(x, y, x + r, y);
        ctx.quadraticCurveTo(x, y, x, y + r); ctx.quadraticCurveTo(x, y, x - r, y);
        ctx.fillStyle = P.core; ctx.shadowColor = P.pink; ctx.shadowBlur = 6 * k; ctx.fill();
      }
    } else if (v === "not-landed") {
      ctx.beginPath(); ctx.arc(x, y, 1.7 * k, 0, Math.PI * 2);
      ctx.strokeStyle = P.ink; ctx.globalAlpha = alpha * 0.5; ctx.lineWidth = 2.6 * k; ctx.stroke();
      ctx.strokeStyle = QUIET; ctx.globalAlpha = alpha; ctx.lineWidth = 1.3 * k; ctx.stroke();
    } else {
      for (let n = -1; n <= 1; n++) dot(x - side * (n + 1) * 5 * k, y, 1.6 * k, QUIET);
    }
    ctx.restore();
  }

  // Cuts a name to fit `max` pixels in the middle: 40% of the kept text from the start, then an end that starts on
  // a whole word.
  function cutMiddle(ctx, name, max) {
    if (ctx.measureText(name).width <= max) return name;
    for (let keep = name.length - 1; keep > 4; keep--) {
      const a = name.slice(0, Math.round(keep * 0.4));
      let b = name.slice(name.length - (keep - a.length));
      const sp = b.indexOf(" ");
      if (sp > 0 && sp < b.length - 1 && !/\s/.test(name[name.length - b.length - 1] ?? " ")) b = b.slice(sp + 1);
      const text = a.trimEnd() + "…" + b;
      if (ctx.measureText(text).width <= max) return text;
    }
    return name.slice(0, 4) + "…";
  }

  // A thread's name, facing the presence: left-aligned on the right, right-aligned on the left, in Nova's caption
  // type with a soft shade behind it; under a single send, project · machine in the small label type.
  function drawName(ctx, x, y, side, k, it, single, alpha, P, canvasW) {
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.textAlign = side > 0 ? "left" : "right";
    ctx.textBaseline = "middle";
    ctx.font = `${it.more ? 400 : 600} ${21 * k}px "IBM Plex Sans", system-ui, sans-serif`;
    const room = side > 0 ? canvasW - 24 * k - x : x - 24 * k;
    const text = cutMiddle(ctx, it.name, Math.min(380 * k, room));
    ctx.shadowColor = "rgba(11, 6, 26, 0.5)";
    ctx.shadowBlur = 4 * k;
    ctx.lineJoin = "round";
    ctx.lineWidth = 1.7 * k;
    ctx.strokeStyle = P.ink;
    ctx.strokeText(text, x, y);
    ctx.shadowBlur = 0;
    ctx.fillStyle = it.more ? QUIET : NAME;
    ctx.fillText(text, x, y);
    if (single && it.sub) {
      ctx.font = `600 ${11 * k}px "IBM Plex Sans", system-ui, sans-serif`;
      ctx.letterSpacing = `${1.4 * k}px`;
      ctx.lineWidth = 2.4 * k;
      ctx.strokeText(it.sub.toUpperCase(), x, y + 19 * k);
      ctx.fillStyle = QUIET;
      ctx.fillText(it.sub.toUpperCase(), x, y + 19 * k);
    }
    ctx.restore();
  }

  // The presence: plays a pack's states, alternates thinking, follows the voice, and never pops between icons.
  class Presence {
    constructor(pack, icons) {
      this.pack = pack;
      this.icons = icons;
      this.level = 0;     // 0..1: the voice level for states with "level" (listening: the owner's voice; speaking: Rook's).
      this.label = "";    // Text for an icon with a "label" place, such as the thread a send goes to.
      this.alpha = 1;     // Dimming for dark or away.
      // Anchors: a host that seats the resting loop higher than the working icons (the desktop overlay does) sets
      // restDy, the rest anchor's offset in pixels. The rest icon, and anything braided from it (an icon whose intro
      // comes from rest, and that intro), sit there; every other icon sits at the centre. Each icon fades where it
      // is, so nothing slides between the two. legacyJump reproduces the old desktop rule (every icon moved with the
      // state), for before-and-after previews only.
      this.restDy = 0;
      this.legacyJump = false;
      const restIcon = typeof pack.states.rest === "string" ? pack.states.rest : "rest";
      this.restSet = new Set([restIcon]);
      for (const [n, spec] of Object.entries(pack.icons)) {
        if (spec.intro?.from === restIcon) { this.restSet.add(n); this.restSet.add(spec.intro.icon); }
      }
      const th = pack.states.thinking || {};
      this.rook = th.rook || "rook";
      this.thinkers = Object.keys(pack.icons).filter((n) => pack.icons[n].think && n !== this.rook);
      this.cur = null;
      this.prev = null;
      this.state = null;
      this.turns = {};    // How many times each cycling state has begun, to take the next icon in its cycle.
    }
    setState(state, now) {
      if (state === this.state) return;
      this.state = state;
      this.stateAt = now;
      this.turns[state] = (this.turns[state] ?? -1) + 1;
    }
    // Which icon a state shows at time `now`. Thinking goes rook, other, rook, next other, and so on.
    pick(now) {
      if (this.dispatch && !this.dispatch.leaving) return this.pack.states.send ?? "dispatch";
      const st = this.pack.states[this.state] ?? this.state;
      if (this.state === "thinking") {
        const turn = Math.floor((now - this.stateAt) / (st.turn || 4));
        if (turn % 2 === 0 || !this.thinkers.length) return this.rook;
        return this.thinkers[Math.floor(turn / 2) % this.thinkers.length];
      }
      if (typeof st === "string") return st;
      if (st.cycle) return st.cycle[this.turns[this.state] % st.cycle.length];
      return st.icon;
    }
    busy(now) { return !this.cur || !!this.dispatch || (this.prev && now - this.cur.at < 0.5) || !!this.pack.states[this.state]?.level; }
    // Starts the change toward icon `want`. An icon with an `intro` ({icon, from}) is reached from `from` through its
    // intro, played once; leaving it back to `from` plays the intro backwards. Intros fade in quickly, with no flash.
    change(want, now) {
      const wi = this.icons[want]?.intro, ci = this.cur && this.icons[this.cur.target]?.intro;
      this.prev = this.cur;
      if (wi && this.icons[wi.icon] && this.cur?.target === wi.from) this.cur = { name: wi.icon, at: now, target: want, fade: 0.12, quiet: true };
      else if (ci && this.icons[ci.icon] && want === ci.from) this.cur = { name: ci.icon, at: now, target: want, fade: 0.15, quiet: true, reverse: true };
      else this.cur = { name: want, at: now, target: want };
    }
    draw(ctx, x, y, size, now) {
      let want = this.pick(now);
      // Keep the current icon until the next one's atlas has loaded, so nothing blinks.
      if (this.icons[want] && !this.icons[want].ready() && this.cur) want = this.cur.target;
      if (!this.cur) this.cur = { name: want, at: now, target: want };
      else if (want !== this.cur.target) this.change(want, now);
      // An intro that has finished hands over: forwards, exactly onto the loop's first frame; backwards, by a short fade.
      const ic = this.icons[this.cur.name];
      if (this.cur.name !== this.cur.target && ic && now - this.cur.at >= ic.duration()) {
        const back = this.cur.reverse;
        this.prev = back ? this.cur : null;
        this.cur = { name: this.cur.target, at: now, target: this.cur.target, fade: back ? 0.15 : 0, quiet: true };
      }
      const tr = this.pack.transition || { seconds: 0.28, from_scale: 0.85, to_scale: 0.92 };
      const quiet = this.cur.quiet, span = this.cur.fade ?? tr.seconds;
      const f = this.prev && span > 0 ? ease((now - this.cur.at) / span) : 1;
      const fromS = quiet ? 1 : tr.from_scale, toS = quiet ? 1 : tr.to_scale;
      const c = this.icons[this.cur.name], p = this.prev && f < 1 && this.icons[this.prev.name];
      const at = (name) => y + (this.legacyJump ? (this.state === "rest" ? this.restDy : 0) : (this.restSet.has(name) ? this.restDy : 0));
      const yc = at(this.cur.name), yp = this.prev ? at(this.prev.name) : y;
      if (quiet) {
        // An intro handoff joins two frames of the same shape: the new one sits at full strength under the old one
        // as it fades, so the presence never dips the way two half-transparent copies would.
        if (c) this.drawIcon(ctx, c, x, yc, size, this.clock(this.cur, now), this.alpha, 1);
        if (p) this.drawIcon(ctx, p, x, yp, size, this.clock(this.prev, now), (1 - f) * this.alpha, 1);
      } else {
        if (p) this.drawIcon(ctx, p, x, yp, size, this.clock(this.prev, now), (1 - f) * this.alpha, lerp(1, fromS, f));
        if (c) this.drawIcon(ctx, c, x, yc, size, this.clock(this.cur, now), f * this.alpha, lerp(toS, 1, f));
      }
      // A flash covers the seam: a one-shot icon, played from the change.
      // The flash starts `flash_at` seconds into the change, so its peak lands on the crossfade's middle.
      const flash = tr.flash && this.icons[tr.flash], ft = now - this.cur.at - (tr.flash_at ?? 0);
      if (!quiet && flash && this.prev && ft >= 0 && ft < flash.duration()) flash.draw(ctx, x, yc, size, ft, 0, this.alpha, tr.flash_scale ?? 1);
      if (this.dispatch) this.drawDispatch(ctx, x, yc, size, now);
    }
    // ---- Dispatch: sending work to threads (stage/dispatch.md). All sizes are the spec's logical pixels for a
    // presence drawn 140 px across; they scale with the drawn size, so 1.6x is exact.
    // threads: [{name, sub}] (sub: "project · machine", shown with a single send). Returns nothing; it plays itself.
    send(threads, now) {
      const T = Dispatch.timing, n = threads.length;
      const shown = n > 6 ? [...threads.slice(0, 5), { name: `and ${n - 5} more`, more: true }] : threads;
      const items = shown.map((th, i) => ({ ...th, i, side: i % 2 === 0 ? 1 : -1, leave: T.intro + T.gap * i, outcome: null }));
      const last = Math.max(...items.map((it) => it.leave + T.travel));
      this.dispatch = { at: now, items, single: n === 1, end: last + T.hold, leaving: false };
    }
    // value: "landed", "not-landed" or "unknown" (null: no answer yet).
    sendOutcome(i, value, now) {
      const it = this.dispatch?.items[i];
      if (it && !it.more) it.outcome = { value, at: now - this.dispatch.at };
    }
    drawDispatch(ctx, cx, cy, size, now) {
      const D = this.dispatch, T = Dispatch.timing, k = size / 140, t = now - D.at;
      const P = this.pack.palette, icon = this.icons.dispatch;
      if (t >= D.end && !D.leaving) D.leaving = true;          // The braid flies back to the loop as the names leave.
      const out = Math.max(0, (t - D.end) / T.out);
      if (out >= 1) { this.dispatch = null; this.tipLevel = null; return; }
      const outE = ease(out);
      // Which sides are sending: a tip reaches out from just before its first strand leaves until it has arrived.
      const tips = { 1: 0, "-1": 0 };
      for (const it of D.items) {
        const a = smooth01((t - it.leave + 0.12) / 0.12) * (1 - smooth01((t - it.leave - T.travel - 0.25) / 0.35));
        tips[it.side] = Math.max(tips[it.side], a);
      }
      this.tipLevel = tips;
      const rowsOn = { 1: 0, "-1": 0 };
      for (const it of D.items) rowsOn[it.side]++;
      const tipAt = { 1: icon?.tips?.tip_r?.at ?? [0.83, 0.5], "-1": icon?.tips?.tip_l?.at ?? [0.17, 0.5] };
      ctx.save();
      for (const it of D.items) {
        const side = it.side, j = Math.floor(it.i / 2), rows = rowsOn[side];
        const ta = tipAt[side];
        const S = [cx + (ta[0] - 0.5) * size, cy + (ta[1] - 0.5) * size];
        const E = [cx + side * (60 + 150) * k, cy + (j - (rows - 1) / 2) * 34 * k];
        const C1 = [S[0] + side * 75 * k, S[1]], C2 = [E[0] - side * 67.5 * k, E[1]];
        const curve = (u) => bez(S, C1, C2, E, u);
        const tl = t - it.leave;
        if (tl < 0) continue;
        const head = easeOut3(Math.min(1, tl / T.travel));
        const arrived = tl >= T.travel;
        // A strand that did not land drains back into the presence; every strand fades on the way out.
        const o = it.outcome, ot = o ? t - o.at : 0;
        const drain = o?.value === "not-landed" ? smooth01(ot / 0.7) : 0;
        const fade = 1 - outE;
        const from = 0, to = head * (1 - drain);
        if (to > from + 0.005) drawStrand(ctx, curve, from, to, k, now, fade * (arrived ? 0.85 : 1), P);
        // The comet head while it travels.
        if (!arrived && this.icons.strand_head) {
          const p0 = curve(head), p1 = curve(Math.max(0, head - 0.02));
          const ang = Math.atan2(p0[1] - p1[1], p0[0] - p1[0]);
          this.icons.strand_head.draw(ctx, p0[0], p0[1], 30 * k, tl, 0, 1, 1, 1, ang);
        }
        // The name rides in from 220 ms before its strand arrives, over 260 ms, sliding 14 px out from the presence.
        const ride = smooth01((tl - (T.travel - 0.22)) / 0.26);
        if (ride <= 0) continue;
        const nameA = ride * fade * (o?.value === "not-landed" ? 1 - 0.45 * smooth01(ot / 0.4) : o?.value === "unknown" ? 0.8 : 1);
        const slide = (1 - ride) * -14 * k + outE * 10 * k;
        drawMark(ctx, E[0] + side * 4 * k, E[1], side, k, it, t, nameA, P);
        drawName(ctx, E[0] + side * (12 * k + slide), E[1], side, k, it, D.single, nameA, P, ctx.canvas.width);
      }
      ctx.restore();
    }

    // An icon's own clock: seconds since it began, or counting down for an intro played backwards.
    clock(entry, now) {
      const t = now - entry.at;
      return entry.reverse ? this.icons[entry.name].duration() - t - 1e-3 : t;
    }
    drawIcon(ctx, icon, x, y, size, seconds, alpha, scale) {
      const voiced = !!this.pack.states[this.state]?.level;
      (icon.layers || ["main"]).forEach((layer, i) => {
        const tip = icon.tips?.[layer];
        if (tip) return icon.draw(ctx, x, y, size, seconds, i, alpha * (this.tipLevel?.[tip.side] ?? 0), scale);
        const r = voiced && icon.voice?.[layer];
        if (!r) return icon.draw(ctx, x, y, size, seconds, i, alpha, scale);
        const lv = this.level;
        icon.draw(ctx, x, y, size, seconds, i, alpha * lerp(r.opacity[0], r.opacity[1], lv),
                  scale * lerp(r.scale?.[0] ?? 1, r.scale?.[1] ?? 1, lv), lerp(r.stretch?.[0] ?? 1, r.stretch?.[1] ?? 1, lv));
      });
      // The label, where the icon has a place for one: ink-edged text, so it reads on dark and on light.
      if (icon.label && this.label) {
        const [ax, ay] = icon.label.at, px = Math.max(10, icon.label.size * size);
        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.font = `600 ${px}px system-ui, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.lineJoin = "round";
        ctx.lineWidth = px * 0.28;
        ctx.strokeStyle = this.pack.palette.ink;
        const tx = x + (ax - 0.5) * size * scale, ty = y + (ay - 0.5) * size * scale;
        const text = this.label.length > 22 ? this.label.slice(0, 21) + "…" : this.label;
        ctx.strokeText(text, tx, ty);
        ctx.fillStyle = this.pack.palette.core;
        ctx.fillText(text, tx, ty);
        ctx.restore();
      }
    }
  }

  // The phone app's interface (phone/presence.js's RookPresence), so the app can swap this in. Moods and kinds map
  // to the pack's states; the app keeps the tap target and feeds the level.
  function phone({ base }) {
    const KIND_STATES = { sending: "send", launching: "send", showing: "open", timing: "timer", waiting: "waiting" };
    let canvas = null, ctx = null, presence = null, dpr = 1, frame = null, mood = "resting", kind = null;
    const stats = { frames: 0, running: false };
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const clock = () => performance.now() / 1000;

    function stateFor(m, k) {
      if (m === "thinking" && KIND_STATES[k]) return KIND_STATES[k];
      return { resting: "rest", dark: "rest", away: "rest" }[m] ?? m;
    }
    function fit() {
      const box = canvas.getBoundingClientRect();
      dpr = Math.min(3, window.devicePixelRatio || 1);
      canvas.width = Math.round(box.width * dpr);
      canvas.height = Math.round(box.height * dpr);
    }
    function draw() {
      const now = reduce ? 0 : clock();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const size = Math.min(canvas.width, canvas.height);
      presence.draw(ctx, canvas.width / 2, canvas.height / 2, size, now);
      stats.frames++;
    }
    function tick() {
      frame = null;
      if (document.hidden || !presence) return halt();
      draw();
      // Icons play at 12 to 24 frames a second; draw at 30 while something changes or the voice drives the
      // icon, and at the icon's own rate otherwise.
      const busy = presence.busy(clock());
      frame = busy ? requestAnimationFrame(tick) : setTimeout(() => { frame = requestAnimationFrame(tick); }, 1000 / 24);
    }
    function wake() {
      if (frame === null && presence && !document.hidden) { stats.running = true; frame = requestAnimationFrame(tick); }
    }
    function halt() {
      if (frame !== null) { cancelAnimationFrame(frame); clearTimeout(frame); frame = null; }
      stats.running = false;
    }
    async function load(target) {
      canvas = target;
      ctx = canvas.getContext("2d");
      const { pack, icons } = await loadPack(base);
      presence = new Presence(pack, icons);
      presence.setState("rest", clock());
      fit();
      new ResizeObserver(() => { fit(); draw(); }).observe(canvas);
      document.addEventListener("visibilitychange", () => (document.hidden ? halt() : wake()));
      wake();
    }
    function set(m, k = null, sendLine = null) {
      mood = m;
      kind = k;
      if (!presence) return;
      if (sendLine) presence.label = String(sendLine);
      presence.alpha = m === "dark" || m === "away" ? 0.4 : 1;
      presence.setState(stateFor(m, k), clock());
      wake();
    }
    function setLevel(v) { if (presence) presence.level = Math.max(0, Math.min(1, v)); }
    function form() { return presence ? presence.pick(clock()) : "rest"; }
    return { load, set, setLevel, form, stats, wake, halt, forms: () => (presence ? Object.keys(presence.icons) : []) };
  }

  return { loadPack, Presence, Flipbook, phone };
})();
