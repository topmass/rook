// Listening: the orb, with a spark on a tilted orbit (layer "main"), and a corona of flares that answers the voice
// (layer "voice"). The player sets the voice layer's opacity and scale from the voice level each frame, so one
// baked loop reacts to sound with no re-render.

vec4 icon(vec2 p, float t, int layer) {
  if (layer == 1) {
    // The corona: sixteen flares round the orb, each breathing on its own beat, whole beats per loop.
    float a = atan(p.y, p.x), r = length(p);
    float k = floor(a / TAU * 16.0 + 0.5);
    float ac = k / 16.0 * TAU;
    float beat = 0.5 + 0.5 * sin(TAU * (t * (1.0 + mod(k, 3.0)) + hash1(k + 5.0)));
    vec2 dir = vec2(cos(ac), sin(ac));
    float len = 0.08 + 0.22 * beat;
    float d = sdTaper(p, dir * 0.36, dir * (0.36 + len), 0.03, 0.0);
    float h = 1.0 - clamp((dot(p, dir) - 0.36) / len, 0.0, 1.0);
    vec4 fl = over(paint(plasma(0.35 + 0.6 * h), fill(d)), paint(INK, fill(d - 0.01) * (1.0 - fill(d))));
    vec4 ring = paint(CYAN, stroke(r - 0.7 - 0.03 * sin(TAU * 2.0 * t), 0.006));
    return over(fl, over(ring, glow(VIOLET, 0.35 * exp(-pow((r - 0.45) / 0.16, 2.0)))));
  }
  vec4 col = orb(p, 0.32, t, 0.0);
  // A spark on a tilted orbit: in front of the orb on the near half, behind it on the far half.
  float s = TAU * t;
  vec2 sp = vec2(cos(s) * 0.52, sin(s) * 0.14);
  sp = rot(0.35) * sp;
  vec2 sp2 = rot(0.35) * vec2(cos(s - 0.5) * 0.52, sin(s - 0.5) * 0.14);
  vec4 spark = over(streak(p, sp2, sp, 0.03, CYAN), glow(CYAN, 0.6 * exp(-length(p - sp) / 0.04)));
  vec2 oq = rot(-0.35) * p;
  float orbit = abs(length(oq / vec2(0.52, 0.14)) - 1.0) * 0.14;
  vec4 path = paint(DEEP, stroke(orbit, 0.004) * 0.8);
  bool front = sin(s) < 0.0;
  if (front) return over(spark, over(col, path));
  return over(col, over(spark, path));
}
