// The head of a send's strand: a small comet travelling along +x, which the player turns to the strand's tangent.
// A white-hot core with a four-point glint, and a tapered pink-to-violet tail with an ink edge.

vec4 icon(vec2 p, float t, int layer) {
  float fl = 0.85 + 0.15 * sin(TAU * 2.0 * t);
  vec2 head = vec2(0.32, 0.0);
  float tail = sdTaper(p, head, vec2(-0.75, 0.0), 0.16, 0.0);
  float h = clamp((p.x + 0.75) / 1.07, 0.0, 1.0);
  vec4 c = paint(mix(DEEP, mix(VIOLET, PINK, h), cel(h, 0.25)), fill(tail));
  c = over(paint(mix(PINK, CORE, cel(h, 0.85)), fill(sdTaper(p, head, vec2(-0.35, 0.0), 0.09, 0.0))), c);
  c = over(c, paint(INK, stroke(tail, 0.06) * 0.8));
  vec2 s = p - head;
  float star = max(1.0 - length(s * vec2(1.0, 5.0)) / (0.5 * fl), 1.0 - length(s * vec2(5.0, 1.0)) / (0.5 * fl));
  c = over(paint(CORE, smoothstep(0.0, 0.1, star)), c);
  return over(c, glow(PINK, 0.7 * fl * exp(-pow(length(s) / 0.3, 2.0))));
}
