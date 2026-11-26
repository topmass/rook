// The rest tube braiding itself into the dispatch braid, played once (and backwards when the send is over). Its first
// frame is the rest tube without its comet; its last is the dispatch loop's first frame, exactly.

vec4 icon(vec2 p, float t, int layer) {
  float morph = smoothstep(0.0, 1.0, t);
  float nearD, frontZ;
  vec4 col = novaLoop(p, -1.0, morph, 0.0, nearD, frontZ);
  return over(col, glow(VIOLET, 0.3 * exp(-pow(max(nearD, 0.0) / 0.06, 2.0))));
}
