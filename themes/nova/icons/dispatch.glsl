// Sending work to threads: Rook's rest loop braided from three strands (novaLoop at morph 1, in common.glsl). The
// strands slide a third of a lap per loop, which brings the braid back to itself. Layers "tip_r" and "tip_l" are
// each lobe tip reaching out and flaring; the player fades in the tip of each side that is sending, and draws the
// strands to the threads' names from the tip points in the manifest (icons.dispatch.tips).

// A lobe tip as a strand leaves it: a glint where the three strands gather, and a short hot streak pulling out
// along the send's direction, with a glow. side is +1 (right) or -1 (left).
vec4 tip(vec2 p, float t, float side) {
  vec2 q = vec2(p.x * side, p.y);
  vec2 at = vec2(0.66, 0.0);
  float flick = 0.85 + 0.15 * sin(TAU * 3.0 * t + side);
  float d = sdTaper(q, at + vec2(0.1, 0.0), at - vec2(0.02, 0.0), 0.0, 0.03);
  float h = clamp((q.x - at.x + 0.02) / 0.12, 0.0, 1.0);
  vec4 c = over(paint(mix(CORE, PINK, h), fill(d)), paint(INK, stroke(d, INKW * 0.8) * 0.9));
  vec2 s = q - at;
  float star = max(1.0 - length(s * vec2(1.0, 5.0)) / (0.09 * flick), 1.0 - length(s * vec2(5.0, 1.0)) / (0.09 * flick));
  c = over(paint(CORE, smoothstep(0.0, 0.12, star)), c);
  return over(c, glow(PINK, 0.6 * flick * exp(-pow(length(s - vec2(0.03, 0.0)) / 0.08, 2.0))));
}

vec4 icon(vec2 p, float t, int layer) {
  if (layer == 1) return tip(p, t, 1.0);
  if (layer == 2) return tip(p, t, -1.0);
  float nearD, frontZ;
  vec4 col = novaLoop(p, -1.0, 1.0, TAU / 3.0 * t, nearD, frontZ);
  return over(col, glow(VIOLET, 0.3 * exp(-pow(max(nearD, 0.0) / 0.06, 2.0))));
}
