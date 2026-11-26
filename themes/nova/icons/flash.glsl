// The transition flash: a third-of-a-second impact burst that covers the change from one icon to the next, as an
// anime hit frame does. Tapered white-hot spikes shoot out and retract, a shock ring spreads, and a core blooms.
// Ink edges keep it visible on a light desktop. It plays once.

vec4 icon(vec2 p, float t, int layer) {
  float r = length(p), a = atan(p.y, p.x);
  float out_ = sin(PI * clamp(t * 1.15, 0.0, 1.0));             // Rises fast, falls back.
  // Spikes: twelve, alternating long and short, each a little off its slot so the burst feels drawn.
  float spikes = 1e9;
  for (int k = 0; k < 12; k++) {
    float ak = TAU * (float(k) + 0.3 * (hash1(float(k) + 4.0) - 0.5)) / 12.0;
    float len = (k % 2 == 0 ? 0.62 : 0.38) * (0.8 + 0.4 * hash1(float(k) + 9.0)) * out_;
    vec2 dir = vec2(cos(ak), sin(ak));
    float inner = 0.1 + 0.25 * t;
    spikes = min(spikes, sdTaper(p, dir * inner, dir * (inner + len), 0.045 * out_, 0.0));
  }
  float h = 1.0 - clamp(r / 0.7, 0.0, 1.0);
  vec4 col = over(paint(mix(PINK, CORE, cel(h, 0.45)), fill(spikes)), paint(INK, fill(spikes - 0.014) * out_));
  // The shock ring.
  float ring = abs(r - (0.12 + 0.62 * t)) - 0.03 * (1.0 - t);
  float ra = smoothstep(0.05, 0.25, t) * (1.0 - t);
  col = over(over(paint(mix(CORE, VIOLET, t), fill(ring) * ra), paint(INK, fill(ring - 0.012) * ra * 0.8)), col);
  // The core bloom.
  float core = r - 0.16 * out_;
  col = over(over(paint(CORE, fill(core)), paint(INK, stroke(core, 0.01) * out_)), col);
  return over(col, glow(VIOLET, 0.6 * out_ * exp(-pow(r / 0.32, 2.0))));
}
