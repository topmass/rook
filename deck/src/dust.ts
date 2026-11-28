// A small Rook presence for the Quick Access panel: gold grains on their own springs that gather into one form per
// mood, after Rook's desktop dust (phone/presence.js has the full WebGL version, which the in-game overlay uses).
// This one is a light 2D canvas, about 90 grains at 30 frames a second, and it runs only while the panel shows.

export type Mood = "resting" | "listening" | "transcribing" | "thinking" | "speaking" | "waiting" | "error";

const { sin, cos } = Math;
const N = 96;
const TONES = ["#f2b347", "#f8cf7d", "#fde9b2"];  // amber, gold, pale gold (the desktop's AMBER .. PALE_GOLD)
const EMBER = "#c0563a";

interface Grain { omega: number; delay: number; phase: number; freq: number; size: number; tone: number; base: number }

function seeded(seed: number) {
  let s = seed;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}

export function moodFor(state: string | undefined): Mood {
  switch (state) {
    case "listening": return "listening";
    case "transcribing": return "transcribing";
    case "thinking": return "thinking";
    case "speaking": return "speaking";
    case "waiting": return "waiting";
    case "error": return "error";
    default: return "resting";
  }
}

export class Dust {
  private ctx: CanvasRenderingContext2D | null;
  private grains: Grain[] = [];
  private x = new Float32Array(N);
  private y = new Float32Array(N);
  private vx = new Float32Array(N);
  private vy = new Float32Array(N);
  private b = new Float32Array(N);
  private mood: Mood = "resting";
  private formAt = 0;
  private clock = 0;
  private last: number | null = null;
  private frame = 0;
  private alive = false;
  private w = 0;
  private h = 0;

  constructor(private canvas: HTMLCanvasElement) {
    this.ctx = canvas.getContext("2d");
    const rnd = seeded(7919);
    for (let i = 0; i < N; i++) {
      this.grains.push({
        omega: 3.2 + rnd() * 2.6, delay: rnd() * 0.35, phase: rnd() * Math.PI * 2, freq: 0.6 + rnd() * 1.4,
        size: 0.9 + rnd() * 1.5, tone: i % 3, base: 0.45 + rnd() * 0.55,
      });
    }
    this.fit();
    for (let i = 0; i < N; i++) {
      const [tx, ty] = this.target(i, 0);
      this.x[i] = tx;
      this.y[i] = ty;
    }
  }

  set(mood: Mood) {
    if (mood === this.mood) return;
    this.mood = mood;
    this.formAt = this.clock;
  }

  start() {
    if (this.alive) return;
    this.alive = true;
    this.last = null;
    const tick = (stamp: number) => {
      if (!this.alive) return;
      const now = stamp / 1000;
      const dt = this.last === null ? 1 / 30 : Math.min(0.1, now - this.last);
      if (this.last === null || dt >= 1 / 32) {
        this.last = now;
        this.step(dt);
        this.draw();
      }
      this.frame = requestAnimationFrame(tick);
    };
    this.frame = requestAnimationFrame(tick);
  }

  stop() {
    this.alive = false;
    cancelAnimationFrame(this.frame);
  }

  private fit() {
    const r = this.canvas.getBoundingClientRect();
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    this.w = Math.max(1, r.width || this.canvas.width);
    this.h = Math.max(1, r.height || this.canvas.height);
    this.canvas.width = Math.round(this.w * dpr);
    this.canvas.height = Math.round(this.h * dpr);
    this.ctx?.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  // Where grain i belongs at time t, in units: the form spans about -1..1 across and -0.5..0.5 down.
  private target(i: number, t: number): [number, number, number] {
    const { sin, cos, PI } = Math;
    const g = this.grains[i];
    const u = i / N;
    const a = u * PI * 2;
    switch (this.mood) {
      case "listening": {  // The halo, breathing, its rim stirred.
        const r = 0.42 + 0.02 * sin(t * 1.1) + 0.05 * sin(a * 9 + t * 3.0) * sin(t * 2.3 + g.phase);
        const th = a + t * 0.2;
        return [r * cos(th), r * sin(th), 1];
      }
      case "transcribing": {  // Three rows of text being set.
        const row = i % 3;
        const k = Math.floor(i / 3) / (N / 3);
        const len = [0.9, 0.75, 0.5][row];
        const x = -0.9 + ((k * 2 + t * 0.25) % 2) * len;
        return [x, -0.28 + row * 0.28, 0.6 + 0.4 * sin(t * 4 + k * 9)];
      }
      case "thinking": {  // The lattice: a hexagon turning in space, with its spokes.
        const spoke = i % 4 === 0;
        const side = Math.floor(u * 6);
        const f = (u * 6) % 1;
        const p0 = (side * PI) / 3 + PI / 6;
        const p1 = ((side + 1) * PI) / 3 + PI / 6;
        let x = spoke ? f * cos(p0) : cos(p0) + (cos(p1) - cos(p0)) * f;
        let y = spoke ? f * sin(p0) : sin(p0) + (sin(p1) - sin(p0)) * f;
        x *= 0.46; y *= 0.46;
        const yaw = t * 0.9;
        const z = x * sin(yaw);
        x = x * cos(yaw);
        return [x, y, 0.65 + 0.45 * (z / 0.46 + 1) / 2];
      }
      case "speaking": {  // The globe, turning, a ripple running over it.
        const yy = 1 - 2 * ((i + 0.5) / N);
        const rr = Math.sqrt(1 - yy * yy);
        const ph = i * 2.399963 + t * 0.8;
        const swell = 1 + 0.06 * sin(t * 6 - yy * 4);
        const x = rr * cos(ph) * 0.42 * swell;
        const z = rr * sin(ph);
        return [x, yy * 0.42 * swell, 0.45 + 0.55 * (z + 1) / 2];
      }
      case "waiting": {  // An open ring, slowly turning: Rook waits on you.
        const th = -PI / 2 + u * PI * 1.6 + t * 0.6;
        const r = 0.4;
        return [r * cos(th), r * sin(th), u < 0.2 ? 1.2 : 0.8];
      }
      case "error": {  // The grains sink and dim.
        const x = (u * 2 - 1) * 0.8;
        return [x, 0.35 + 0.06 * sin(x * 7 + t), 0.5];
      }
      default: {  // At rest, the loop: a figure of eight that flows slowly.
        const f = a + (t * 2 * PI) / 10.5;
        const sa = sin(f);
        const ca = cos(f);
        return [0.78 * sa, 0.62 * sa * ca + 0.02 * sin(g.phase), 0.55 + 0.22 * (ca + 1)];
      }
    }
  }

  private step(dt: number) {
    this.clock += dt;
    const t = this.clock;
    const since = t - this.formAt;
    const jitter = since < 0.6 ? 1.2 : 0.06;
    for (let i = 0; i < N; i++) {
      const g = this.grains[i];
      if (since < g.delay) continue;
      const [tx, ty, tb] = this.target(i, t);
      const k = g.omega * g.omega;
      const ax = k * (tx - this.x[i]) - 1.4 * g.omega * this.vx[i] + jitter * sin(t * g.freq * 6 + g.phase);
      const ay = k * (ty - this.y[i]) - 1.4 * g.omega * this.vy[i] + jitter * cos(t * g.freq * 7 + g.phase);
      this.vx[i] += ax * dt;
      this.vy[i] += ay * dt;
      this.x[i] += this.vx[i] * dt;
      this.y[i] += this.vy[i] * dt;
      this.b[i] = tb;
    }
  }

  private draw() {
    const ctx = this.ctx;
    if (!ctx) return;
    const r = this.canvas.getBoundingClientRect();
    if (Math.abs(r.width - this.w) > 1 || Math.abs(r.height - this.h) > 1) this.fit();
    const { w, h } = this;
    ctx.clearRect(0, 0, w, h);
    const unit = Math.min(w / 2.2, h * 0.95);
    const cx = w / 2;
    const cy = h / 2;
    ctx.globalCompositeOperation = "lighter";
    const err = this.mood === "error";
    for (let i = 0; i < N; i++) {
      const g = this.grains[i];
      const alpha = Math.max(0, Math.min(1, g.base * this.b[i] * 0.85));
      if (alpha <= 0.02) continue;
      ctx.globalAlpha = alpha;
      ctx.fillStyle = err ? EMBER : TONES[g.tone];
      const s = g.size * (0.8 + 0.3 * this.b[i]);
      ctx.fillRect(cx + this.x[i] * unit - s / 2, cy + this.y[i] * unit - s / 2, s, s);
    }
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
  }
}

