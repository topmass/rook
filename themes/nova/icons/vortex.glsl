// Opening media or a panel: a black hole that spins open. Three inked plasma arms spiral into an ink-black hole on a
// slightly tilted disk; the photon ring flares, and debris streaks in and is swallowed. The arms turn a third of a
// turn per loop, which with three arms is seamless. Craft ideas (hotter, faster inner rings, a gulp, debris that
// stretches as it falls) come from pixelfx's black-hole effect (MIT); see ../SOURCES.md. The code is Nova's own.

const float RS = 0.19;     // The hole's shadow.
const float SI = 0.62;     // How open the tilted disk is (1 is face on).
const float TILT = -0.18;  // The disk's screen angle.

vec4 icon(vec2 p, float t, int layer) {
  vec2 c = p;
  float ct = cos(TILT), st = sin(TILT);
  vec2 P = vec2(c.x * ct + c.y * st, (-c.x * st + c.y * ct) / SI);
  float rho = length(P), ph = atan(P.y, P.x), r = length(c);
  float pulse = pow(max(0.0, cos(TAU * 2.0 * t)), 10.0);  // A gulp, twice a loop.

  // Heat: three arms that wind inward, hotter near the hole, broken up by noise that turns with them.
  float arm = cos(3.0 * ph + 6.5 * log(rho) - TAU * t);
  float n = pnoise(vec3((ph / TAU) * 9.0 - 3.0 * t, log(rho) * 5.0 - t * 4.0, 0.3), vec3(3.0, 4.0, 7.0));
  float env = smoothstep(RS, RS + 0.05, rho) * (1.0 - smoothstep(0.55, 0.86, rho));
  float h = env * ((0.5 + 0.5 * arm) * 0.8 + 0.25 * n + 0.1) * pow(0.3 / rho, 0.75) * (1.0 + 0.3 * pulse);
  vec3 pc = plasma(h);
  pc = mix(pc, CYAN, cel(h, 0.62) * (1.0 - cel(h, 0.8)) * smoothstep(0.0, 0.6, -P.x / rho));
  vec4 swirl = paint(pc, cel(h, 0.17));
  vec4 inked = paint(INK, cel(h, 0.12) * (1.0 - cel(h, 0.17)));

  // The shadow and its photon ring, with bright lobes turning round it.
  float a = atan(c.y, c.x);
  float lobes = 0.5 + 0.5 * cos(3.0 * a - TAU * 2.0 * t) + pulse * 0.6;
  vec4 ring = paint(mix(PINK, CORE, cel(lobes, 0.5)), stroke(r - RS - 0.012, 0.014 + 0.01 * pulse));
  vec4 hole = paint(INK * 0.2, fill(r - RS));
  vec4 rim = glow(CORE, 0.8 * exp(-max(r - RS, 0.0) / 0.025));

  // Debris spirals in, stretched into hot streaks near the hole, and is gone at the ring.
  vec4 deb = vec4(0.0);
  for (int i = 0; i < 12; i++) {
    float hsh = hash1(float(i) * 1.7 + 2.0);
    float ph0 = hash1(float(i) + 40.0) * TAU;
    vec2 pts[2];
    for (int j = 0; j < 2; j++) {
      float life = max(fract(t * 2.0 + hsh) - float(j) * 0.1, 0.0);
      float q = pow(life, 1.7);
      float rr = mix(0.78, RS + 0.02, q), aa = ph0 + 2.4 * q;
      vec2 d = vec2(cos(aa) * rr, sin(aa) * rr * SI);
      pts[j] = vec2(d.x * ct - d.y * st, d.x * st + d.y * ct);
    }
    float life = fract(t * 2.0 + hsh);
    deb = over(streak(c, pts[1], pts[0], 0.009 * (0.5 + life), mix(PINK, CYAN, step(0.55, hsh))), deb);
  }
  vec4 halo = glow(VIOLET, (0.5 + 0.35 * pulse) * exp(-max(rho - RS, 0.0) / 0.1));
  vec4 far = glow(DEEP, 0.3 * exp(-pow(r / 0.3, 2.0)));
  return over(ring, over(hole, over(rim, over(deb, over(swirl, over(inked, over(halo, far)))))));
}
