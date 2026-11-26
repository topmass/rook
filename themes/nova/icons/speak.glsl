// Speaking: a speech bubble of plasma with a sound wave inside, the sign for talking that reads with the sound off.
// Layer "main" is the bubble: inflated, cel-lit from the upper left, with an ink rim and a cyan rim light, like the
// rook. Layer "wave" is a standing sound wave travelling through it, baked at full height: the player stretches it
// from a flat line at silence to its full swing at full voice. Layer "glow" is the bubble's inner light, which the
// player fades up with the level, so a loud syllable visibly brightens the whole icon.

float sdRoundBox(vec2 p, vec2 b, float r) { return sdBox(p, b - r) - r; }
float bubble(vec2 p) {
  float body = sdRoundBox(p - vec2(0.0, 0.08), vec2(0.62, 0.44), 0.26);
  float tail = sdTaper(p, vec2(-0.2, -0.26), vec2(-0.44, -0.64), 0.15, 0.0);
  return min(body, tail);
}

vec4 icon(vec2 p, float t, int layer) {
  float d = bubble(p);
  if (layer == 2) {
    vec2 q = p - vec2(0.0, 0.08);
    float env = pow(max(0.0, 1.0 - pow(q.x / 0.47, 2.0)), 1.2);
    float amp = 0.25 * env * (0.72 + 0.28 * sin(q.x * 5.0 + TAU * t));
    float y = amp * sin(q.x * 14.0 - TAU * 2.0 * t);
    float slope = 14.0 * amp;
    float w = 0.034 * (0.35 + env);
    float dw = max(abs(q.y - y) / sqrt(1.0 + 0.5 * slope * slope) - w, abs(q.x) - 0.49);
    float core = max(abs(q.y - y) / sqrt(1.0 + 0.5 * slope * slope) - w * 0.38, abs(q.x) - 0.47);
    vec4 c = over(paint(CORE, fill(core)), paint(PINK, fill(dw)));
    c = over(c, paint(INK, stroke(dw, INKW * 0.8)));
    return over(c, glow(PINK, 0.55 * exp(-pow(max(dw, 0.0) / 0.06, 2.0)) * fill(d)));
  }
  if (layer == 1) {
    // The inner light: brightest in the middle of the bubble, kept inside its edge.
    float h = clamp(-d / 0.3, 0.0, 1.0);
    return over(paint(mix(VIOLET, PINK, 0.55), fill(d + 0.05) * (0.25 + 0.55 * h)), glow(PINK, 0.35 * exp(-pow(max(d, 0.0) / 0.1, 2.0))));
  }
  // The bubble, inflated: depth rises from the edge, and the edge's normal sets the light.
  vec2 e = vec2(0.004, 0.0);
  vec2 n2 = normalize(vec2(bubble(p + e.xy) - bubble(p - e.xy), bubble(p + e.yx) - bubble(p - e.yx)) + 1e-6);
  float depth = smoothstep(0.0, 0.16, -d);
  vec3 n = normalize(vec3(n2 * (1.0 - depth), 0.35 + depth));
  float diff = dot(n, normalize(vec3(-0.55, 0.6, 0.6))) * 0.5 + 0.5;
  vec3 c = mix(INK * 1.7, DEEP, cel(diff, 0.38));
  c = mix(c, VIOLET, cel(diff, 0.6));
  c = mix(c, mix(VIOLET, CORE, 0.5), cel(diff, 0.82) * (1.0 - depth));
  c = mix(c, CYAN, cel(1.0 - n.z, 0.55) * (1.0 - cel(diff, 0.5)) * 0.9);
  vec4 body = paint(c, fill(d));
  return over(over(body, paint(INK, stroke(d, INKW))), glow(VIOLET, 0.45 * exp(-pow(max(d, 0.0) / 0.08, 2.0))));
}
