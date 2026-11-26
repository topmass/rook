// Rook's presence: the desktop's gold dust on a canvas, in the desktop's own forms (phone/forms.json, made by
// phone/forms.py from desktop/overlay.py and desktop/devs_pack.py). The motion follows the overlay's Scene: each grain
// on its own spring with its own delay, a slight curl in flight, a shimmer, and a few grains slipping loose once a form
// has settled. It draws as the desktop's Devs look does, in WebGL 2 (see DustGL below), and as plain squares on a 2D
// canvas where WebGL 2 is missing. It draws only while something moves. At rest the loop flows at a low frame rate,
// then holds still.
"use strict";

const RookPresence = (() => {
  const REST_FPS = 20;
  const REST_FLOW_SECONDS = 45;  // After this long at rest with nothing new, the loop holds still until something happens.
  const REST_Y = -6;  // The resting loop's height in the canvas, a little above the working forms' centre.
  // The checks' quiet presence: the 2D canvas at one pixel to a form unit and ten frames a second, so a headless check
  // tests the page's logic without rendering the dust in software. Only a browser driven over DevTools can turn it
  // on, by defining window.rookCheckPresence before the page's scripts run (phone/check.py does). The app never sets
  // it, the server serves the same files, and the content-security policy runs no script but the app's own.
  const QUIET = window.rookCheckPresence === "quiet";
  const QUIET_FPS = 10;
  // The desktop's send cycle: a send steps it as its form starts, so the first send is the turbine.
  const SEND_CYCLE = ["send_array", "send_turbine"];
  const KIND_FORMS = {
    reading: "page", searching: "magnifier", running: "prompt", editing: "quill",
    waiting: "spinner", showing: "film", drawing: "eye", timing: "hourglass", game: "sword", tool: "cog",
    speaking: "sphere",
  };

  let data = null;
  let N = 0;
  let canvas = null;
  let ctx = null;
  let dust = null;  // The WebGL renderer, or null on the 2D canvas.
  let width = 0;
  let height = 0;
  let scale = 1;
  let zoom = 1;  // The presence-only view scales the canvas up; the canvas draws this much sharper to match.
  const forms = {};
  let g = null;  // Each grain's constants.
  let x, y, vx, vy, depth, loose, tx, ty, tb, ox, oy, ob, zn, tz, oz;  // z: each grain's depth, -1 far to 1 near.
  let restIdx = [];
  let allIdx = [];

  const view = {
    form: "loop", prev: "loop", formAt: -Infinity, mood: "resting", kind: null, thinkingSince: null, sendTurn: 0,
    loosen: 0, pace: 1, intensity: 0.85, share: 0.035, extra: 0, level: 0, heard: new Array(32).fill(0),
    voice: 0, dim: 0, err: 0, changedAt: 0, clock: 0, last: null, timer: null, frame: null, reduce: false,
    listenTurn: -1,  // Listening takes the halo and the helix in turn, one per listening, as the desktop does.
    // Rook's voice while it speaks: the newest level and when it came, the envelope, and a wave for each syllable.
    said: 0, saidAt: -Infinity, env: 0, envWas: 0, trough: 0, armed: false, waves: [],
  };
  // The desktop's speaking globe (overlay.py): each syllable sends a ring over the globe from EAR_POLE to the far side.
  const EAR_POLE = [0.26, -0.22, 0.94];
  const SPEAK_RIPPLE = 0.3;
  const WAVE_RISE = 0.1;
  const WAVE_GAP = 0.15;
  const WAVE_SECONDS = 1.1;
  const WAVE_WIDTH = 0.7;
  const WAVE_MAX = 6;
  const stats = { frames: 0, running: false, gl: false };  // gl: the Devs look draws, not the 2D fallback.

  function decode(b64, k) {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const ints = new Int16Array(bytes.buffer);
    const out = new Float32Array(ints.length);
    for (let i = 0; i < ints.length; i++) out[i] = ints[i] / k;
    return out;
  }

  async function load(target) {
    canvas = target;
    const res = await fetch("/forms.json", { cache: "force-cache" });
    data = await res.json();
    dust = QUIET ? null : DustGL(canvas, data.look);
    stats.gl = Boolean(dust);
    if (!dust) {  // A canvas that once gave a WebGL context gives no 2D one: draw on a fresh one.
      const fresh = canvas.cloneNode();
      canvas.replaceWith(fresh);
      canvas = fresh;
      ctx = canvas.getContext("2d");
    }
    canvas.addEventListener("webglcontextlost", (e) => e.preventDefault());  // A phone may take the chip back for a while.
    canvas.addEventListener("webglcontextrestored", () => {
      dust = DustGL(canvas, data.look);
      draw();
    });
    N = data.grains;
    const gr = data.grain;
    g = {
      omega: decode(gr.omega, 1000), delay: decode(gr.delay, 1000), curl: decode(gr.curl, 1000),
      freq: decode(gr.freq, 1000), phase: decode(gr.phase, 1000), base: decode(gr.base, 1000),
      size: decode(gr.size, 1000), tone: decode(gr.tone, 1), blue: decode(gr.blue, 1000),
    };
    for (const [name, f] of Object.entries(data.forms)) {
      if (f.type === "loop2") forms[name] = { type: f.type, along: decode(f.along, 1000), off: decode(f.off, 1000) };
      else if (f.type === "halo2") forms[name] = { type: f.type, a: decode(f.a, 1000), echo: decode(f.echo, 1), off: decode(f.off, 1000) };
      else if (f.type === "loop3") forms[name] = { type: f.type, along: decode(f.along, 1000), spread: decode(f.spread, 1000), thick: decode(f.thick, 1000) };
      else if (f.type === "halo3") forms[name] = { type: f.type, kind: decode(f.kind, 1), a: decode(f.a, 1000), pa: decode(f.pa, 1000), pb: decode(f.pb, 1000) };
      else if (f.type === "helix3") forms[name] = { type: f.type, u: decode(f.u, 10000), turn: decode(f.turn, 1), rung: decode(f.rung, 1), v: decode(f.v, 1000), oy: decode(f.oy, 1000), oz: decode(f.oz, 1000) };
      else if (f.type === "spin") forms[name] = { type: "spin", spin: f.spin, fit: f.fit, x: decode(f.x, 10), y: decode(f.y, 10), z: decode(f.z, 10) };
      else forms[name] = { type: "still", x: decode(f.x, 10), y: decode(f.y, 10), b: decode(f.b, 1000) };
    }
    [x, y, vx, vy, depth, loose, tx, ty, tb, ox, oy, ob, zn, tz, oz] = Array.from({ length: 15 }, () => new Float32Array(N));
    allIdx = Array.from({ length: N }, (_, i) => i);
    restIdx = allIdx.filter((i) => i % data.restEvery === 0);
    view.reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    fit();
    targets("loop", 0, tx, ty, tb, tz);
    x.set(tx);
    y.set(ty);
    depth.set(tb);
    zn.set(tz);
    view.formAt = -10;
    new ResizeObserver(fit).observe(canvas);
    document.addEventListener("visibilitychange", () => (document.hidden ? halt() : wake()));
    wake();
  }

  function fit() {
    const box = canvas.getBoundingClientRect();
    // WebGL draws at most four pixels to a form unit: enough for the soft grains, and a bound on the cost.
    const dpr = QUIET ? 1 : Math.min(dust ? 4 : 3 * zoom, (window.devicePixelRatio || 1) * zoom);
    width = box.width;
    height = box.height;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    scale = dpr;
    if (data) draw();
  }

  // Where each grain belongs in a form at time t, as the overlay's _form_targets has it.
  function targets(name, t, ox_, oy_, ob_, oz_) {
    const f = forms[name] ?? forms.loop;
    const { sin, cos } = Math;
    oz_.fill(0);
    if (f.type === "loop2") {
      const flow = (t * 2 * Math.PI) / data.loopPeriod;
      for (let i = 0; i < N; i++) {
        const a = f.along[i] + flow;
        const sa = sin(a);
        const ca = cos(a);
        ox_[i] = 60 * sa;
        oy_[i] = REST_Y + 52 * sa * ca + f.off[i];
        ob_[i] = 0.55 + 0.225 * (ca + 1);
      }
    } else if (f.type === "halo2") {
      const heard = view.heard;
      const held = heard.reduce((s, v) => s + v, 0) / heard.length;
      const breath = sin((t * 2 * Math.PI) / 5.5);
      const spin = t * 0.12;
      const radius = 40 + 1.5 * breath + 7 * held;
      const p1 = t * 3.0;
      const p2 = t * 4.7;
      for (let i = 0; i < N; i++) {
        const th = f.a[i] + spin;
        const echo = f.echo[i] !== 0;
        const m = Math.abs((((th - Math.PI / 2) % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI) - Math.PI);
        const lv = echo ? heard[6] : heard[0];
        const wave = 0.65 * sin(12 * m + p1) + 0.35 * sin(20 * m - p2);
        const d = 16 * (lv + 0.04) * (0.4 + 0.6 * sin(th) * sin(th)) * wave;
        const r = (echo ? 31 + 4 * held : radius) + f.off[i] + d;
        ox_[i] = r * cos(th);
        oy_[i] = r * sin(th);
        ob_[i] = (echo ? 0.65 : 1.0) + 0.02 * Math.abs(d);
      }
    } else if (f.type === "loop3" || f.type === "halo3" || f.type === "helix3") {
      devsTargets(f, t, ox_, oy_, ob_, oz_);
    } else if (f.type === "spin") {
      const a = t * f.spin;
      const ca = cos(a);
      const sa = sin(a);
      const ct = cos(data.tilt);
      const st = sin(data.tilt);
      const [k, dx, dy] = f.fit;
      // Each wave is a ring: its angle from the pole and its strength. It fades in over its first 0.12 s and fades
      // out as it nears the far side.
      const rings = name !== "sphere" ? [] : view.waves.map(([start, loud]) => {
        const p = Math.max(0, (t - start) / WAVE_SECONDS);
        return [Math.PI * p, 0.5 * loud * smooth(p / 0.12) * cos((Math.PI / 2) * p)];
      });
      const [ex, ey, ez] = EAR_POLE;
      for (let i = 0; i < N; i++) {
        const px = f.x[i];
        const py = f.y[i];
        const pz = f.z[i];
        let x1 = px * ca + pz * sa;
        const z1 = pz * ca - px * sa;
        let y2 = py * ct - z1 * st;
        let z2 = py * st + z1 * ct;
        if (rings.length) {  // A raised cosine across each ring, so the swell has no hard edge.
          const away = Math.acos(Math.max(-1, Math.min(1, (x1 * ex + y2 * ey + z2 * ez) / 46)));
          let wave = 0;
          for (const [at, strength] of rings) {
            const u = away - at;
            if (u > -WAVE_WIDTH && u < WAVE_WIDTH) wave += strength * (1 + cos((u * Math.PI) / WAVE_WIDTH));
          }
          if (wave) {
            const swell = 1 + SPEAK_RIPPLE * wave;
            x1 *= swell;
            y2 *= swell;
            z2 = z2 * swell + 30 * wave;
          }
        }
        ox_[i] = x1 * k + dx;
        oy_[i] = y2 * k + dy;
        ob_[i] = shade(z2, 46, oz_, i);
      }
    } else {
      ox_.set(f.x);
      oy_.set(f.y);
      ob_.set(f.b);
    }
  }

  // The desktop's depth shading (devs_pack._depth_shade): far grains at 0.30, near ones up to 1.38. Writes z.
  function shade(z2, span, oz_, i) {
    const z = Math.max(-1, Math.min(1, z2 / span));
    oz_[i] = z;
    return 0.30 + 1.08 * (0.5 + 0.5 * z) ** 1.25;
  }

  // The forms the desktop rebuilt in 3D, as devs_pack.eval_targets has them: the loop, the halo with its rays, the
  // helix. Each turns in space with perspective.
  function devsTargets(f, t, ox_, oy_, ob_, oz_) {
    const { sin, cos, abs, PI } = Math;
    const heard = view.heard;
    const held = heard.reduce((s, v) => s + v, 0) / heard.length;
    const meta = data.meta[f.type === "loop3" ? "loop" : f.type === "halo3" ? "halo" : "helix"];
    let yaw;
    let pitch;
    if (f.type === "loop3") {
      yaw = meta.yaw_amp * sin(t * 0.35);
      pitch = 0.08 + meta.pitch_amp * cos(t * 0.35);
    } else if (f.type === "halo3") {
      const prec = t * meta.prec_rate;
      yaw = meta.yaw_amp * cos(prec);
      pitch = meta.pitch_amp * sin(prec);
    } else {
      yaw = meta.yaw_base + 0.10 * sin(t * 0.28);
      pitch = meta.pitch;
    }
    const cy = cos(yaw);
    const sy = sin(yaw);
    const cp = cos(pitch);
    const sp = sin(pitch);
    const persp = meta.persp;
    const put = (i, px, py, pz, lift, span, boost) => {
      const x1 = px * cy + pz * sy;
      const z1 = pz * cy - px * sy;
      const y2 = py * cp - z1 * sp;
      const z2 = py * sp + z1 * cp;
      const p = 1 / (1 - z2 / persp);
      ox_[i] = x1 * p;
      oy_[i] = lift + y2 * p;
      ob_[i] = shade(z2, span, oz_, i) * boost;
    };
    if (f.type === "loop3") {
      const flow = (t * 2 * PI) / meta.period;
      for (let i = 0; i < N; i++) {
        const a = f.along[i] + flow;
        const sa = sin(a);
        const ca = cos(a);
        put(i, 60 * sa, 54 * sa * ca + f.spread[i], 24 * ca + f.thick[i], REST_Y, 34, 1);
      }
    } else if (f.type === "halo3") {
      const breath = sin((t * 2 * PI) / 5.5);
      const spin = t * 0.24;
      const p1 = t * 3.2;
      const p2 = t * 5.0;
      for (let i = 0; i < N; i++) {
        const a = f.a[i];
        const th = a + spin;
        const c = cos(th);
        const s = sin(th);
        const pa = f.pa[i];
        const pb = f.pb[i];
        if (f.kind[i] === 0) {  // The inner rim, which never dissolves.
          const r = 33 + 1.4 * breath + 4.5 * held + pa;
          put(i, r * c, r * s, 0, 0, 42, 1.12);
        } else if (f.kind[i] === 1) {  // Two tilted bands crossing in depth.
          const r = 41 + 1.5 * breath + 5.5 * held + pb;
          const tilt = 0.36 * pa;
          put(i, r * c, r * s * cos(tilt), r * s * sin(tilt) + 3 * heard[2] * sin(4 * th + p1), 0, 42, 1.02);
        } else {  // The rays, which reach out with the voice.
          const lv = heard[Math.round(pb) % 6];
          const wave = 0.58 + 0.42 * abs(sin(6 * a + p1) * 0.65 + cos(10 * a - p2) * 0.35);
          const r = 41.5 + 5 * held + pa * (10 + 26 * lv) * wave;
          put(i, r * c, r * s, 5 * pa * sin(3 * a + p1) * (0.4 + lv), 0, 42, (0.78 + 0.45 * lv) * (1 - 0.32 * pa));
        }
      }
    } else {
      const spin = t * meta.spin;
      const twist = 0.048 * (1 + 0.12 * held);
      for (let i = 0; i < N; i++) {
        const u = f.u[i];
        const px = 68 * u;
        const lv = heard[Math.floor(abs(u) * 8)];
        const r = 22.5 * (1 - 0.28 * u ** 4) * (1 + 0.36 * lv * (0.45 + 0.55 * (1 - u * u)));
        const ph = twist * px + spin + (f.turn[i] ? PI : 0);
        const s = sin(ph);
        const c = cos(ph);
        if (f.rung[i]) put(i, px, f.v[i] * r * s, f.v[i] * r * c, 0, 28, 0.68 + 0.34 * lv);
        else put(i, px, r * s + f.oy[i], r * c + f.oz[i], 0, 28, 1.04 + 0.28 * lv);
      }
    }
  }

  // The helix's two glowing strands, as devs_pack.eval_helix_strands has them: per strand, (x, y, z, brightness,
  // level, fade) at 64 points. They fade while the grains fly to another form.
  function helixStrands(t) {
    const fade = Math.max(0, Math.min(1, 1 - view.loosen));
    if (view.form !== "helix" || fade <= 0.01) return [];
    const { sin, cos, abs, PI } = Math;
    const meta = data.meta.helix;
    const heard = view.heard;
    const held = heard.reduce((s, v) => s + v, 0) / heard.length;
    const spin = t * meta.spin;
    const yaw = meta.yaw_base + 0.10 * sin(t * 0.28);
    const cy = cos(yaw);
    const sy = sin(yaw);
    const cp = cos(meta.pitch);
    const sp = sin(meta.pitch);
    const twist = 0.048 * (1 + 0.12 * held);
    return [0, PI].map((turn) => Array.from({ length: 64 }, (_, k) => {
      const u = -1 + (2 * k) / 63;
      const px = 68 * u;
      const lv = heard[Math.min(heard.length - 1, Math.floor(abs(u) * 8))];
      const r = 22.5 * (1 - 0.28 * u ** 4) * (1 + 0.36 * lv * (0.45 + 0.55 * (1 - u * u)));
      const ph = twist * px + spin + turn;
      const py = r * sin(ph);
      const pz = r * cos(ph);
      const x1 = px * cy + pz * sy;
      const z1 = pz * cy - px * sy;
      const y2 = py * cp - z1 * sp;
      const z2 = py * sp + z1 * cp;
      const p = 1 / (1 - z2 / meta.persp);
      const z = Math.max(-1, Math.min(1, z2 / 28));
      return [x1 * p, y2 * p, z, 0.30 + 1.08 * (0.5 + 0.5 * z) ** 1.25, lv, fade * Math.min(1, (1 - abs(u)) / 0.10)];
    }));
  }

  // Which form a mood takes, as the overlay's Scene.step chooses it.
  function chooseForm(t) {
    const m = view.mood;
    if (m === "resting" || m === "dark" || m === "away") return "loop";
    if (m === "listening") return view.listenTurn % 2 ? "helix" : "halo";
    if (m === "transcribing") return "rows";
    if (m === "speaking") return "sphere";
    if (m === "waiting") return "question";
    if (m === "error") return "sink";
    if (m === "thinking" && view.kind && view.kind !== "thinking") {
      if (view.kind === "sending" || view.kind === "launching") {
        // A send form keeps showing; a new send takes the next one (enterForm steps the cycle).
        return SEND_CYCLE.includes(view.form) ? view.form : SEND_CYCLE[(view.sendTurn + 1) % SEND_CYCLE.length];
      }
      return KIND_FORMS[view.kind] ?? "cog";
    }
    if (view.thinkingSince === null) view.thinkingSince = t;
    return ["lattice", "rook"][Math.floor((t - view.thinkingSince) / data.thinkTurn) % 2];
  }

  function glide(dt, tau) {
    return 1 - Math.exp(-dt / tau);
  }

  function smooth(v) {
    const x = Math.max(0, Math.min(1, v));
    return x * x * (3 - 2 * x);
  }

  // A stand-in for Rook's voice when no level reaches the phone, as while the desk speaks: about four syllables a
  // second, each with its own loudness, and a short breath now and then.
  function syllables(t) {
    const s = t * 4.2 + 0.8 * Math.sin(t * 1.3);
    const ph = s % 1;
    const loud = 0.45 + 0.55 * Math.sin(Math.floor(s) * 12.9898) ** 2;
    return Math.sin(t * 0.7) < -0.85 || ph > 0.62 ? 0 : 0.6 * loud * Math.sin((Math.PI * ph) / 0.62);
  }

  // The desktop's voice envelope and syllable waves (overlay.Scene.step): the envelope rises in 0.04 s and falls in
  // 0.12 s, and a syllable starts when it rises WAVE_RISE from its last dip.
  function speech(t, dt) {
    const on = view.mood === "speaking";
    const raw = !on ? 0 : t - view.saidAt < 0.3 ? view.said : syllables(t);
    const said = Math.min(1, raw) ** 0.55;
    view.env += (said - view.env) * glide(dt, said > view.env ? 0.04 : 0.12);
    if (view.env < view.envWas && !view.armed) {
      view.armed = true;
      view.trough = view.env;
    }
    view.trough = Math.min(view.trough, view.env);
    if (view.armed && view.env - view.trough > WAVE_RISE && t - (view.waves.at(-1)?.[0] ?? -Infinity) >= WAVE_GAP) {
      view.waves = [...view.waves, [t, view.env]].slice(-WAVE_MAX);
      view.armed = false;
    }
    view.envWas = view.env;
    view.waves = view.waves.filter((w) => t - w[0] < WAVE_SECONDS);
    for (const w of view.waves) if (t - w[0] < 0.2) w[1] = Math.max(w[1], view.env);
    return said;
  }

  function step(t, dt) {
    const home = view.form === "loop";
    const m = view.mood;
    const level = view.level;
    view.heard.unshift(level);
    view.heard.pop();
    view.voice += (speech(t, dt) - view.voice) * glide(dt, 0.1);
    const goal = home ? 0.85 : m === "listening" ? 0.8 + 0.4 * level : m === "speaking" ? 0.9 + 0.3 * view.voice
      : m === "error" ? 0.45 : 0.9;
    view.intensity += (goal - view.intensity) * glide(dt, 0.25);
    const share = m === "thinking" && view.kind ? 0.09 : m === "thinking" ? 0.06 : 0.035;
    view.share += (share - view.share) * glide(dt, 0.8);
    view.dim += ((m === "away" || m === "dark" ? 1 : 0) - view.dim) * glide(dt, 0.4);
    view.err += ((m === "error" ? 1 : 0) - view.err) * glide(dt, 0.8);
    const form = chooseForm(t);
    if (form !== "lattice" && form !== "rook") view.thinkingSince = null;
    if (form !== view.form) {
      enterForm(form);
      view.formAt = t;
      view.pace = 1;
      view.loosen = 1;
      loose.fill(-Infinity);
    }
    view.loosen *= Math.exp(-dt / 0.35);
    if ((form === "halo" || form === "helix" || form === "sphere") && t - view.formAt > 0.9) {
      // Once formed, the listening forms' and the speaking globe's grains answer the voice within a frame or two.
      view.pace += ((form === "sphere" ? 1.5 : 2.2) - view.pace) * glide(dt, 0.2);
    }
    const resting = view.form === "loop";
    view.extra += ((resting ? 0 : 1) - view.extra) * glide(dt, resting ? 0.35 : 0.15);
    const idx = resting && view.extra < 0.01 ? restIdx : allIdx;
    if (!resting && t - view.formAt > 1) carryLoose(t, dt);

    targets(view.form, t, tx, ty, tb, tz);
    const moving = t - view.formAt < 0.3 + 0.3;
    if (moving) targets(view.prev, t, ox, oy, ob, oz);
    const steps = dt <= 0.034 ? 1 : Math.ceil(dt / 0.034);
    const h = dt / steps;
    const pace = view.pace;
    const jitter = (35 + 900 * view.loosen) * pace * pace;
    const { sin, cos } = Math;
    for (const i of idx) {
      const since = t - view.formAt - g.delay[i];
      let gx;
      let gy;
      if (moving && since < 0) {
        gx = ox[i];
        gy = oy[i];
        depth[i] = ob[i];
        zn[i] = oz[i];
      } else {
        gx = tx[i];
        gy = ty[i];
        depth[i] = tb[i];
        zn[i] = tz[i];
      }
      const w = g.omega[i] * (view.err ? 1 - 0.6 * view.err : 1) * pace;
      const k = w * w * (loose[i] > t ? 0.03 : 1);
      const bend = since > 0 && since < 0.5 / pace ? g.curl[i] * k * 0.5 * (1 - since * 2 * pace) : 0;
      const p = t * g.freq[i] + g.phase[i];
      const jx = jitter * sin(p);
      const jy = jitter * cos(p * 2);
      for (let s = 0; s < steps; s++) {
        const dx = gx - x[i];
        const dy = gy - y[i];
        let ax = k * dx - 1.1 * w * vx[i] + jx;
        let ay = k * dy - 1.1 * w * vy[i] + jy;
        if (bend) {
          ax -= bend * dy;
          ay += bend * dx;
        }
        vx[i] += ax * h;
        vy[i] += ay * h;
        x[i] += vx[i] * h;
        y[i] += vy[i] * h;
      }
    }
    return idx;
  }

  function carryLoose(t, dt) {
    view.carry = (view.carry ?? 0) + N * 0.025 * dt;
    while (view.carry >= 1) {
      view.carry -= 1;
      const i = Math.floor(Math.random() * N);
      loose[i] = t + 0.8 + Math.random() * 0.8;
      vx[i] += (Math.random() * 2 - 1) * 14;
      vy[i] += (Math.random() * 2 - 1) * 14;
    }
  }

  // The overlay's grain model for the dark theme: additive squares, bucketed by tone and by one of seven levels.
  const buckets = Array.from({ length: 32 }, () => []);
  function draw(idx = view.form === "loop" && view.extra < 0.01 ? restIdx : allIdx) {
    if (dust) {
      if (data) dust.draw({ N, x, y, vx, vy, depth, zn, g, idx, width, height, scale, t: view.clock,
                            intensity: view.intensity * (1 - 0.55 * view.dim), share: view.share, err: view.err,
                            strands: helixStrands(view.clock) });
      stats.frames += 1;
      return;
    }
    if (!ctx) return;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.setTransform(scale, 0, 0, scale, width / 2 * scale, height / 2 * scale);
    ctx.globalCompositeOperation = "lighter";
    for (const b of buckets) b.length = 0;
    const sparks = [];
    const intensity = view.intensity * 7 * (1 - 0.55 * view.dim);
    for (const i of idx) {
      const level = Math.floor(g.base[i] * depth[i] * intensity * (i % data.restEvery === 0 ? 1 : view.extra));
      if (level <= 0) continue;
      const colour = g.blue[i] < view.share ? 3 : g.tone[i];
      buckets[colour * 8 + Math.min(7, level)].push(i);
      if (g.base[i] > 0.85) sparks.push(i);
    }
    const tones = [...data.tones, data.blueTone];
    const grey = view.dim * 0.6;
    for (let c = 0; c < 4; c++) {
      let [r, gg, b] = tones[c].map((v, k) => v + (data.ember[k] - v) * view.err);
      const mean = (r + gg + b) / 3;
      [r, gg, b] = [r, gg, b].map((v) => v + (mean - v) * grey);
      for (let level = 1; level < 8; level++) {
        const bucket = buckets[c * 8 + level];
        if (!bucket.length) continue;
        ctx.fillStyle = `rgba(${Math.round(r * 255)},${Math.round(gg * 255)},${Math.round(b * 255)},${level / 7})`;
        ctx.beginPath();
        for (const i of bucket) {
          const s = g.size[i];
          ctx.rect(x[i] - s / 2, y[i] - s / 2, s, s);
        }
        ctx.fill();
      }
    }
    const [sr, sg, sb] = data.spark;
    ctx.fillStyle = `rgba(${Math.round(sr * 255)},${Math.round(sg * 255)},${Math.round(sb * 255)},${data.sparkAlpha * view.intensity * (1 - view.dim)})`;
    ctx.beginPath();
    for (const i of sparks) ctx.rect(x[i] - 1.8, y[i] - 1.8, 3.6, 3.6);
    ctx.fill();
    ctx.globalCompositeOperation = "source-over";
    stats.frames += 1;
  }

  // The frame loop: every vsync while grains fly or a form moves; a low rate while the loop flows at rest; nothing
  // while the page is hidden, nothing once the rest has held still, and nothing at all with reduced motion.
  function settled(t) {
    return view.form === "loop" && t - view.formAt > 3 && view.extra < 0.01;
  }

  function tick(stamp) {
    view.frame = null;
    view.timer = null;
    const now = stamp / 1000;
    const dt = view.last === null ? 1 / 60 : Math.min(0.1, Math.max(0, now - view.last));
    view.last = now;
    view.clock += dt;
    const t = view.clock;
    draw(step(t, dt));
    if (document.hidden) return halt();
    if (settled(t) && t - view.changedAt > REST_FLOW_SECONDS) return halt();
    const fps = QUIET ? QUIET_FPS : settled(t) ? REST_FPS : 0;
    if (fps) view.timer = setTimeout(() => { view.frame = requestAnimationFrame(tick); }, 1000 / fps);
    else view.frame = requestAnimationFrame(tick);
  }

  function halt() {
    if (view.frame !== null) cancelAnimationFrame(view.frame);
    clearTimeout(view.timer);
    view.frame = null;
    view.timer = null;
    view.last = null;
    stats.running = false;
  }

  function wake() {
    if (!data || document.hidden) return;
    view.changedAt = view.clock;
    if (view.reduce) {
      // No flight: the grains take their places at once, drawn once.
      const form = chooseForm(view.clock);
      if (form !== view.form) enterForm(form);
      view.extra = view.form === "loop" ? 0 : 1;
      view.intensity = 0.85;
      targets(view.form, 0, tx, ty, tb, tz);
      x.set(tx);
      y.set(ty);
      depth.set(tb);
      zn.set(tz);
      draw();
      return;
    }
    if (view.frame === null && view.timer === null) {
      stats.running = true;
      view.frame = requestAnimationFrame(tick);
    }
  }

  // The swarm takes a new form. Entering a send form from another form steps the send cycle, as on the desktop.
  function enterForm(form) {
    if (SEND_CYCLE.includes(form) && !SEND_CYCLE.includes(view.form)) view.sendTurn += 1;
    view.prev = view.form;
    view.form = form;
  }

  // mood: resting, listening, transcribing, thinking, speaking, waiting, error, dark or away. kind: the newest
  // activity's kind while thinking.
  function set(mood, kind = null) {
    if (mood === view.mood && kind === view.kind) return;
    if (mood === "listening" && view.mood !== "listening") view.listenTurn += 1;
    view.mood = mood;
    view.kind = kind;
    wake();
  }

  function setLevel(value) {
    view.level = Math.max(0, Math.min(1, value));
  }

  // Rook's own speech level as it plays on this phone, 0 to 1, about every 50 ms.
  function setSpeech(value) {
    view.said = Math.max(0, Math.min(1, value));
    view.saidAt = view.clock;
  }

  function setZoom(value) {
    zoom = value;
    if (canvas) fit();
  }

  function form() {
    return view.reduce || !data ? view.form : chooseForm(view.clock);
  }

  return { load, set, setLevel, setSpeech, setZoom, form, stats, wake, halt, waves: () => view.waves.length,
           forms: () => Object.keys(forms) };
})();

// The Devs look in WebGL 2, after the desktop's _DustGL (desktop/overlay.py): each grain a soft round sprite added into
// a half-float buffer, brighter and larger near, smaller and dimmer far; about a tenth of the grains hot sparkles that
// twinkle, each with a wider faint halo; a glint where a grain faces the light; a streak on fast grains. A small glow
// (a two-level Kawase blur of the brightest parts only) goes on top, and a warm tone curve brings it to the screen,
// bold and gold, never clipped to white. Returns null where WebGL 2 or a half-float buffer is missing.
function DustGL(canvas, look) {
  const gl = canvas.getContext("webgl2", { alpha: true, premultipliedAlpha: true, antialias: false, depth: false,
                                           stencil: false, powerPreference: "low-power" });
  if (!gl || !gl.getExtension("EXT_color_buffer_float")) return null;
  const f = (v) => Number(v).toFixed(4);
  const v3 = (v) => `vec3(${f(v[0])}, ${f(v[1])}, ${f(v[2])})`;
  const dk = look.dark;
  const [t0, t1, t2] = dk.tones_lin;
  const sparkCut = Math.round(look.sparkle_fraction * 100);

  const GRAIN_VERT = `#version 300 es
layout(location = 0) in vec4 a0;  // x, y, depth brightness, z
layout(location = 1) in vec2 a1;  // vx, vy
layout(location = 2) in vec3 a2;  // base, tone, blue rank
uniform int spark;
uniform float intensity, share, scale, err, u_time;
uniform vec2 origin, size_px;
out vec2 v_uv;
flat out vec3 v_col;
void main() {
  float b = a2.x;
  float d_val = a0.z;
  uint gid = uint(gl_InstanceID);
  bool is_spark = ((gid * 2654435761u) % 100u) < ${sparkCut}u;
  if (d_val <= 0.002 || (spark == 1 && !is_spark)) {
    gl_Position = vec4(-2.0, -2.0, 0.0, 1.0);
    v_uv = vec2(0.0);
    v_col = vec3(0.0);
    return;
  }
  float zi = clamp(a0.w, -1.0, 1.0);
  float tw = is_spark ? (0.68 + 0.56 * (0.5 + 0.5 * sin(u_time * ${f(look.twinkle_rate)} + float(gid) * 1.6180339887))) : 1.0;
  float rad;
  vec3 col;
  vec3 ember = ${v3(dk.ember_lin)};
  vec3 sp_col = mix(${v3(dk.spark_lin)}, ember, err);
  float stretch = 0.0;
  vec2 vdir = vec2(1.0, 0.0);
  if (spark == 1) {
    rad = ${f(look.spark_radius_px)} * scale;
    col = sp_col * (0.28 * tw * d_val * intensity);
  } else {
    float d_nom = (${f(look.sprite_base_px)} + ${f(look.sprite_span_px)} * b) * (is_spark ? 1.08 : 1.0);
    float d_floor = zi < -0.15 ? ${f(look.sprite_far_floor_px)} : ${f(look.sprite_floor_px)};
    rad = 0.5 * max(d_floor, d_nom * (1.0 + ${f(look.depth_size_gain)} * zi)) * scale;
    float norm_b = clamp((b - 0.18) / 0.82, 0.0, 1.0);
    int t = 0;
    if (is_spark) {
      col = sp_col * ((0.72 + 0.28 * norm_b) * ${f(look.sparkle_boost)} * tw * d_val * intensity * ${f(look.energy_gain)});
    } else {
      t = a2.z < min(share, ${f(look.blue_max_share)}) ? 3 : int(a2.y);
      col = t == 3 ? ${v3(dk.accent_lin)} : t == 0 ? ${v3(t0)} : t == 1 ? ${v3(t1)} : ${v3(t2)};
      col = mix(col, ember, err);
      if (t < 3 && zi != 0.0) {
        col.g = clamp(col.g * (1.0 + 0.12 * zi), 0.34, 0.95);
        col.b = clamp(col.b * (1.0 + 0.28 * zi), 0.03, 0.60);
      }
      col *= (0.38 + 0.50 * norm_b) * d_val * intensity * ${f(look.energy_gain)};
    }
    if (is_spark || t < 3) {
      float h1 = float((gid * 1597334677u) & 65535u) / 32768.0 - 1.0;
      float h2 = float((gid * 3812015801u) & 65535u) / 32768.0 - 1.0;
      vec3 nrm = normalize(vec3(a0.x / 52.0 + 0.55 * h1, a0.y / 52.0 + 0.55 * h2,
                                max(0.05, 0.65 + 0.55 * zi) + 0.25 * sin(u_time * 0.9 + float(gid) * 0.73)));
      float ndh = dot(nrm, vec3(-0.30, -0.42, 0.856));
      if (ndh > 0.55) col += mix(vec3(1.0, 0.84, 0.44), ember, err)
        * (pow(ndh, 20.0) * 1.45 * ${f(look.glint_strength)} * d_val * intensity * ${f(look.energy_gain)});
    }
    float spd = length(a1);
    if (spd > 18.0) {
      stretch = min(1.35, ((spd - 18.0) / 145.0) * ${f(look.streak_strength)});
      vdir = a1 / spd;
    }
  }
  vec2 corner = vec2(gl_VertexID & 1, gl_VertexID >> 1) * 2.0 - 1.0;
  vec2 centre = origin + a0.xy * scale;
  float r_maj = rad * (1.0 + stretch);
  float r_min = rad / sqrt(1.0 + 0.50 * stretch);
  vec2 offs = vdir * (corner.x * (r_maj + 0.5)) + vec2(-vdir.y, vdir.x) * (corner.y * (r_min + 0.5));
  vec2 p = (centre + offs) / size_px * 2.0 - 1.0;
  gl_Position = vec4(p.x, -p.y, 0.0, 1.0);
  v_uv = vec2(corner.x * ((r_maj + 0.5) / r_maj), corner.y * ((r_min + 0.5) / r_min));
  v_col = col;
}`;
  const GRAIN_FRAG = `#version 300 es
precision highp float;
precision highp int;
in vec2 v_uv;
flat in vec3 v_col;
uniform int spark;
out vec4 result;
void main() {
  float u2 = dot(v_uv, v_uv);
  if (u2 >= 1.0) discard;
  float w = exp((spark == 1 ? -${f(look.spark_k)} : -${f(look.gaussian_k)}) * u2) * (1.0 - u2);
  result = vec4(v_col * w, 0.0);
}`;
  const STRAND_VERT = `#version 300 es
layout(location = 0) in vec3 a_pos;  // x, y in pixels, across from -1 to 1
layout(location = 1) in vec3 a_col;
uniform vec2 size_px;
out float v_across;
out vec3 v_col;
void main() {
  vec2 p = a_pos.xy / size_px * 2.0 - 1.0;
  gl_Position = vec4(p.x, -p.y, 0.0, 1.0);
  v_across = a_pos.z;
  v_col = a_col;
}`;
  const STRAND_FRAG = `#version 300 es
precision highp float;
precision highp int;
in float v_across;
in vec3 v_col;
out vec4 result;
void main() {
  float u2 = v_across * v_across;
  if (u2 >= 1.0) discard;
  result = vec4(v_col * exp(-4.0 * u2) * (1.0 - u2), 0.0);
}`;
  const FULL_VERT = `#version 300 es
void main() { gl_Position = vec4(vec2(gl_VertexID & 1, gl_VertexID >> 1) * 4.0 - 1.0, 0.0, 1.0); }`;
  const DOWN_FRAG = `#version 300 es
precision highp float;
precision highp int;
uniform sampler2D src_tex;
uniform vec2 half_px;
uniform int soft_knee;
out vec4 result;
void main() {
  vec2 uv = gl_FragCoord.xy / vec2(textureSize(src_tex, 0)) * 2.0;
  vec3 c = texture(src_tex, uv).rgb * 4.0 + texture(src_tex, uv - half_px).rgb + texture(src_tex, uv + half_px).rgb
         + texture(src_tex, uv + vec2(half_px.x, -half_px.y)).rgb + texture(src_tex, uv + vec2(-half_px.x, half_px.y)).rgb;
  c *= 0.125;
  if (soft_knee == 1) {
    float ex = max(0.0, dot(c, vec3(0.2126, 0.7152, 0.0722)) - ${f(look.bloom_threshold)});
    c *= ex > 0.0 ? ex / (ex + ${f(look.bloom_knee)}) : 0.0;
  }
  result = vec4(c, 1.0);
}`;
  const UP_FRAG = `#version 300 es
precision highp float;
precision highp int;
uniform sampler2D src_tex, tap_tex;
uniform vec2 half_px;
out vec4 result;
void main() {
  vec2 uv = gl_FragCoord.xy * half_px;
  vec3 c = texture(src_tex, uv + vec2(-half_px.x * 2.0, 0.0)).rgb + texture(src_tex, uv + vec2(half_px.x * 2.0, 0.0)).rgb
         + texture(src_tex, uv + vec2(0.0, -half_px.y * 2.0)).rgb + texture(src_tex, uv + vec2(0.0, half_px.y * 2.0)).rgb
         + (texture(src_tex, uv - half_px).rgb + texture(src_tex, uv + half_px).rgb
          + texture(src_tex, uv + vec2(half_px.x, -half_px.y)).rgb + texture(src_tex, uv + vec2(-half_px.x, half_px.y)).rgb) * 2.0;
  result = vec4(mix(c / 12.0, texture(tap_tex, uv).rgb, 0.28), 1.0);
}`;
  const TONE_FRAG = `#version 300 es
precision highp float;
precision highp int;
uniform sampler2D hdr_tex, bloom_tex;
out vec4 result;
float srgb(float c) {
  c = clamp(c, 0.0, 1.0);
  return c <= 0.0031308 ? 12.92 * c : 1.055 * pow(c, 1.0 / 2.4) - 0.055;
}
void main() {
  vec2 uv = gl_FragCoord.xy / vec2(textureSize(hdr_tex, 0));
  vec3 rgb = texelFetch(hdr_tex, ivec2(gl_FragCoord.xy), 0).rgb
           + ${f(look.bloom_strength)} * ${v3(look.bloom_tint)} * texture(bloom_tex, uv).rgb;
  float y = dot(rgb, vec3(0.2126, 0.7152, 0.0722));
  if (y <= 1e-5) { result = vec4(0.0); return; }
  float y_tm = 1.0 - exp(-${f(look.tonemap_exposure)} * y);
  float t_hot = y / (y + ${f(look.highlight_knee)});
  float hot = min(${f(look.highlight_cap)}, t_hot * t_hot * 0.88);
  vec3 lin = rgb * (y_tm / y) * (1.0 - hot) + ${v3(look.highlight_target)} * (y_tm * hot);
  vec3 sr = vec3(srgb(lin.r), srgb(lin.g), srgb(lin.b));
  float tri = fract(52.9829189 * fract(dot(floor(gl_FragCoord.xy), vec2(0.06711056, 0.00583715)))) * 2.0 - 1.0;
  sr = clamp(sr + vec3(sign(tri) * (1.0 - sqrt(1.0 - abs(tri))) * (0.5 / 255.0) * ${f(look.dither_strength)}), 0.0, 1.0);
  result = vec4(sr, max(sr.r, max(sr.g, sr.b)));
}`;

  function program(vs, fs) {
    const p = gl.createProgram();
    for (const [type, src] of [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]]) {
      const s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
      gl.attachShader(p, s);
    }
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    const u = {};
    for (let k = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS); k--;) {
      const name = gl.getActiveUniform(p, k).name;
      u[name] = gl.getUniformLocation(p, name);
    }
    return { p, u };
  }

  let progs;
  try {
    progs = { grain: program(GRAIN_VERT, GRAIN_FRAG), strand: program(STRAND_VERT, STRAND_FRAG),
              down: program(FULL_VERT, DOWN_FRAG), up: program(FULL_VERT, UP_FRAG), tone: program(FULL_VERT, TONE_FRAG) };
  } catch {
    return null;
  }
  const fbo = gl.createFramebuffer();
  const empty = gl.createVertexArray();
  const grains = gl.createVertexArray();
  const live = gl.createBuffer();
  const still = gl.createBuffer();
  const strandVao = gl.createVertexArray();
  const strandBuf = gl.createBuffer();
  gl.bindVertexArray(grains);
  gl.bindBuffer(gl.ARRAY_BUFFER, live);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 4, gl.FLOAT, false, 24, 0);
  gl.vertexAttribDivisor(0, 1);
  gl.enableVertexAttribArray(1);
  gl.vertexAttribPointer(1, 2, gl.FLOAT, false, 24, 16);
  gl.vertexAttribDivisor(1, 1);
  gl.bindBuffer(gl.ARRAY_BUFFER, still);
  gl.enableVertexAttribArray(2);
  gl.vertexAttribPointer(2, 3, gl.FLOAT, false, 0, 0);
  gl.vertexAttribDivisor(2, 1);
  gl.bindVertexArray(strandVao);
  gl.bindBuffer(gl.ARRAY_BUFFER, strandBuf);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 24, 0);
  gl.enableVertexAttribArray(1);
  gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 24, 12);
  gl.bindVertexArray(null);

  let rows = null;
  let stillFor = null;
  let size = [0, 0];
  let tex = [];  // The full buffer, then each blur level down by half, then the way back up.
  let dims = [];

  function texture(w, h) {
    const t = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texStorage2D(gl.TEXTURE_2D, 1, gl.RGBA16F, w, h);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    return t;
  }

  function target(t, w, h) {
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t, 0);
    gl.viewport(0, 0, w, h);
  }

  function draw(s) {
    const W = canvas.width;
    const H = canvas.height;
    if (!W || !H || gl.isContextLost()) return;
    // The desktop blurs two levels down at about two pixels to a form unit. A phone draws finer, so it goes one level
    // further, for a glow of the same reach on the form.
    const levels = s.scale >= 3 ? 3 : 2;
    if (size[0] !== W || size[1] !== H || dims.length !== levels + 1) {
      for (const t of tex) gl.deleteTexture(t);
      dims = [[W, H]];
      for (let k = 0; k < levels; k++) dims.push(dims[k].map((v) => Math.ceil(v / 2)));
      tex = dims.map(([w, h]) => texture(w, h));
      tex.push(texture(...dims[levels - 1]));  // The way back up, at the level above the smallest.
      size = [W, H];
    }
    if (stillFor !== s.g) {  // Each grain's constants: its brightness, tone and blue rank.
      const data = new Float32Array(s.N * 3);
      for (let i = 0; i < s.N; i++) data.set([s.g.base[i], s.g.tone[i], s.g.blue[i]], i * 3);
      gl.bindBuffer(gl.ARRAY_BUFFER, still);
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
      stillFor = s.g;
      rows = new Float32Array(s.N * 6);
    }
    rows.fill(0);
    for (const i of s.idx) {
      const k = i * 6;
      rows[k] = s.x[i];
      rows[k + 1] = s.y[i];
      rows[k + 2] = s.depth[i];
      rows[k + 3] = s.zn[i];
      rows[k + 4] = s.vx[i];
      rows[k + 5] = s.vy[i];
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, live);
    gl.bufferData(gl.ARRAY_BUFFER, rows, gl.STREAM_DRAW);

    // The grains, added in light.
    const origin = [W / 2, H / 2];
    target(tex[0], W, H);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);
    if (s.strands.length) drawStrands(s, origin, W, H);
    const { p, u } = progs.grain;
    gl.useProgram(p);
    gl.uniform1f(u.intensity, s.intensity);
    gl.uniform1f(u.share, s.share);
    gl.uniform1f(u.scale, s.scale);
    gl.uniform1f(u.err, s.err);
    gl.uniform1f(u.u_time, s.t % 3600);
    gl.uniform2f(u.origin, origin[0], origin[1]);
    gl.uniform2f(u.size_px, W, H);
    gl.bindVertexArray(grains);
    for (const spark of [0, 1]) {
      gl.uniform1i(u.spark, spark);
      gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, s.N);
    }
    gl.disable(gl.BLEND);

    // The glow: the brightest parts only, blurred down to a quarter and back up to a half.
    gl.bindVertexArray(empty);
    gl.activeTexture(gl.TEXTURE0);
    const down = progs.down;
    gl.useProgram(down.p);
    gl.uniform1i(down.u.src_tex, 0);
    for (let k = 1; k <= levels; k++) {  // The first step down keeps only the brightest parts.
      target(tex[k], ...dims[k]);
      gl.bindTexture(gl.TEXTURE_2D, tex[k - 1]);
      gl.uniform2f(down.u.half_px, 1 / dims[k - 1][0], 1 / dims[k - 1][1]);
      gl.uniform1i(down.u.soft_knee, k === 1 ? 1 : 0);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }
    const up = progs.up;
    const [uw, uh] = dims[levels - 1];
    gl.useProgram(up.p);
    target(tex[levels + 1], uw, uh);
    gl.bindTexture(gl.TEXTURE_2D, tex[levels]);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, tex[levels - 1]);
    gl.uniform1i(up.u.src_tex, 0);
    gl.uniform1i(up.u.tap_tex, 1);
    gl.uniform2f(up.u.half_px, 1 / uw, 1 / uh);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);

    // The tone curve, onto the page.
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, W, H);
    const tone = progs.tone;
    gl.useProgram(tone.p);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, tex[0]);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, tex[levels + 1]);
    gl.uniform1i(tone.u.hdr_tex, 0);
    gl.uniform1i(tone.u.bloom_tex, 1);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    gl.activeTexture(gl.TEXTURE0);
  }

  // The helix's two strands, as mitred ribbons of light, under its grains.
  function drawStrands(s, origin, W, H) {
    const e1 = 1 - s.err;
    const [er, eg, eb] = dk.ember_lin;
    const { p, u } = progs.strand;
    gl.useProgram(p);
    gl.uniform2f(u.size_px, W, H);
    gl.bindVertexArray(strandVao);
    gl.bindBuffer(gl.ARRAY_BUFFER, strandBuf);
    for (const strand of s.strands) {
      const n = strand.length;
      const verts = new Float32Array(n * 12);
      strand.forEach(([sx, sy, zn, bd, lv, fade], k) => {
        const a = strand[Math.max(0, k - 1)];
        const b = strand[Math.min(n - 1, k + 1)];
        const tx = (b[0] - a[0]) * s.scale;
        const ty = (b[1] - a[1]) * s.scale;
        const tl = Math.hypot(tx, ty) || 1;
        const nx = -ty / tl;
        const ny = tx / tl;
        const hw = (2.15 + 0.65 * zn + 0.55 * lv) * s.scale;
        const en = 0.56 * bd * (0.85 + 0.35 * lv) * s.intensity * fade * look.energy_gain;
        const col = [(e1 + er * s.err) * en, ((0.66 + 0.14 * zn) * e1 + eg * s.err) * en,
                     ((0.14 + 0.12 * Math.max(0, zn)) * e1 + eb * s.err) * en];
        const px = origin[0] + sx * s.scale;
        const py = origin[1] + sy * s.scale;
        verts.set([px - nx * hw, py - ny * hw, -1, ...col, px + nx * hw, py + ny * hw, 1, ...col], k * 12);
      });
      gl.bufferData(gl.ARRAY_BUFFER, verts, gl.STREAM_DRAW);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, n * 2);
    }
  }

  return { draw };
}
