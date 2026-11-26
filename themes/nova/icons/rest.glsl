// At rest: Devs' resting loop as a ribbon of plasma in three dimensions. The figure of eight passes over and under
// itself at the crossing as a lit plasma tube, and a comet runs one calm lap per loop, leaving a hot trail
// that cools back into the ribbon. Seen most of the day, so it stays quiet: no flares, one slow lap.

// The loop itself is novaLoop in common.glsl, shared with dispatch, so the two match exactly.
vec3 lem3(float s) { return loopLem(s); }

vec4 icon(vec2 p, float t, int layer) {
  float nearD, bestZ;
  vec4 col = novaLoop(p, t, 0.0, 0.0, nearD, bestZ);
  // The comet's head: a white core, a small four-point star, and a soft pink glow.
  vec3 hp = lem3(TAU * t);
  vec2 s = p - hp.xy;
  float tw = 0.8 + 0.2 * cos(TAU * 2.0 * t);
  float star = max(1.0 - length(s * vec2(1.0, 5.5)) / (0.13 * tw), 1.0 - length(s * vec2(5.5, 1.0)) / (0.13 * tw));
  vec4 head = over(paint(CORE, smoothstep(0.0, 0.12, star)), paint(CORE, fill(length(s) - 0.03)));
  head = over(head, glow(PINK, 0.75 * exp(-pow(length(s) / 0.08, 2.0))));
  // Embers drift off the head and fade, three at a time.
  for (int i = 0; i < 3; i++) {
    float life = fract(t * 3.0 + float(i) / 3.0);
    vec3 at = lem3(TAU * (t - life / 3.0));
    vec2 e = at.xy + vec2(0.0, 0.09 * life) + 0.03 * vec2(cos(float(i) * 2.1), sin(float(i) * 2.1)) * life;
    col = over(paint(mix(PINK, VIOLET, life), fill(length(p - e) - 0.012 * (1.0 - life))), col);
  }
  vec4 g = glow(VIOLET, 0.3 * exp(-pow(max(nearD, 0.0) / 0.06, 2.0)));
  // The head sits in front when it is on the near half of the loop, behind the ribbon when on the far half.
  if (hp.z > bestZ - 0.02 || bestZ < -1e8) return over(head, over(col, g));
  return over(col, over(head, g));
}
