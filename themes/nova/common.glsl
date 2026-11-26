// Nova's palette and plasma, shared by its icons. See DIRECTION.md.
const vec3 INK = vec3(0.082, 0.043, 0.200);
const vec3 DEEP = vec3(0.294, 0.122, 0.722);
const vec3 VIOLET = vec3(0.541, 0.271, 1.000);
const vec3 PINK = vec3(1.000, 0.357, 0.847);
const vec3 CORE = vec3(1.000, 0.957, 1.000);
const vec3 CYAN = vec3(0.275, 0.902, 1.000);
const vec3 AMBER = vec3(1.000, 0.710, 0.278);
const vec3 ROSE = vec3(1.000, 0.239, 0.416);
// One outline weight for the whole family: an object's ink edge is this half-width (about 2.5 px at 1.6x).
const float INKW = 0.014;

// Plasma heat to colour, in hard cel bands: deep, violet, pink, white.
vec3 plasma(float h) {
  vec3 c = DEEP;
  c = mix(c, VIOLET, cel(h, 0.3));
  c = mix(c, PINK, cel(h, 0.58));
  c = mix(c, CORE, cel(h, 0.8));
  return c;
}
// The same bands in water: deep, cyan, white.
vec3 water(float h) {
  vec3 c = DEEP;
  c = mix(c, mix(VIOLET, CYAN, 0.55), cel(h, 0.28));
  c = mix(c, CYAN, cel(h, 0.52));
  c = mix(c, CORE, cel(h, 0.8));
  return c;
}
// A plasma shape from an SDF and its heat: ink edge, banded body, soft violet glow outside.
vec4 plasmaShape(float d, float heat, float edge, vec3 glowCol, float glowR) {
  vec4 body = paint(plasma(heat), fill(d));
  vec4 ink = paint(INK, fill(d - edge) * (1.0 - fill(d)));
  vec4 g = glow(glowCol, 0.55 * exp(-max(d, 0.0) / glowR) * (1.0 - fill(d - edge)));
  return over(body, over(ink, g));
}
// A streak spark: a tapered line from tail to head, white at the head.
vec4 streak(vec2 p, vec2 tail, vec2 head, float w, vec3 col) {
  float d = sdTaper(p, head, tail, w, 0.0);
  float h = clamp(dot(p - tail, head - tail) / max(dot(head - tail, head - tail), 1e-8), 0.0, 1.0);
  return paint(mix(col, CORE, cel(h, 0.6)), fill(d));
}

// Nova's orb, shared by listening and speaking: a sphere of plasma with a swirl inside, lit from the upper left,
// a cyan rim on its shadow side, and an ink edge. `heat` lifts it (speaking runs hotter).
vec4 orb(vec2 p, float r, float t, float heat) {
  float d = length(p) - r;
  vec2 q = p / r;
  vec3 n = vec3(q, sqrt(max(0.0, 1.0 - dot(q, q))));
  float diff = dot(n, normalize(vec3(-0.5, 0.6, 0.62))) * 0.5 + 0.5;
  float swirl = pnoise(vec3(q * 2.2 + 9.0, t * 2.0), vec3(64.0, 64.0, 2.0));
  float core = pow(max(0.0, 1.0 - length(q - vec2(-0.12, 0.14))), 2.0);
  float h = diff * 0.58 + 0.14 * swirl + 0.22 * core + heat;
  vec3 c = plasma(h);
  c = mix(c, CYAN, cel(1.0 - n.z, 0.72) * (1.0 - cel(diff, 0.55)));
  vec4 body = paint(c, fill(d));
  vec4 ink = paint(INK, stroke(d - 0.004, INKW));
  vec4 g = glow(VIOLET, 0.6 * exp(-pow(max(d, 0.0) / 0.08, 2.0)));
  return over(ink, over(body, g));
}

// Nova's loop, shared by rest and dispatch. At morph 0 it is the rest tube: one lit plasma tube in a figure of
// eight. At morph 1 it is the braid: three thinner strands wound round the same path, three twists a lap, which
// `slide` (radians) moves along the loop. Rest and dispatch both draw it here, so they match exactly.
// trailT >= 0 adds the rest comet's hot trail behind the point at loop phase trailT. Returns the body and its ink;
// nearD is the distance to the nearest strand edge (for glows), frontZ the depth drawn here (-1e9 where empty).
const int LOOP_N = 72;
const float BRAID_A = 0.043;
vec3 loopLem(float s) {
  float d = 1.0 + sin(s) * sin(s);
  return vec3(0.62 * cos(s) / d, 0.62 * sin(s) * cos(s) / d, 0.3 * sin(s));
}
vec3 loopStrand(float u, int k, float morph, float slide) {
  float ph = 3.0 * (u - slide) + TAU * float(k) / 3.0;
  return loopLem(u) + morph * BRAID_A * vec3(0.0, sin(ph), cos(ph));
}
float loopW(float z, float morph) { return mix(0.042, 0.023, morph) * (0.8 + 0.45 * z); }

vec4 novaLoop(vec2 p, float trailT, float morph, float slide, out float nearD, out float frontZ) {
  int strands = morph > 0.0 ? 3 : 1;
  int n = morph > 0.0 ? 120 : LOOP_N;   // The braid's twists need finer segments; rest keeps its own count.
  float bestZ = -1e9, bestD = 1e9, bestS = 0.0, inkZ = -1e9;
  int bestK = -1;
  nearD = 1e9;
  // Two stages: each strand's own body here (its nearest covering segment, or the front pass where it crosses
  // itself), then one strand among the three: the frontmost, or, at nearly equal depth (while they are still
  // splitting), the one that covers this pixel most centrally. Choosing per strand first keeps the choice steady.
  for (int k = 0; k < 3; k++) {
    if (k >= strands) break;
    float kz = -1e9, kd = 1e9, ks = 0.0;
    for (int i = 0; i < n; i++) {
      float s0 = TAU * float(i) / float(n), s1 = TAU * float(i + 1) / float(n);
      vec3 a = loopStrand(s0, k, morph, slide), b = loopStrand(s1, k, morph, slide);
      float sm = 0.5 * (s0 + s1);
      float z = 0.5 * (a.z + b.z);
      float d = sdSeg(p, a.xy, b.xy) - loopW(z, morph);
      nearD = min(nearD, d);
      if (d < 0.0 && (z > kz + 0.1 || (z > kz - 0.1 && d < kd))) { kz = z; kd = d; ks = sm; }
    }
    if (kz < -1e8) continue;
    float tol = 0.03 * (1.0 - morph) + 0.004;
    if (bestK < 0 || kz > bestZ + tol || (kz > bestZ - tol && kd < bestD)) { bestZ = kz; bestD = kd; bestS = ks; bestK = k; }
  }
  // Ink where an edge in front lies over the body here: another strand, or the other pass of the same strand.
  if (bestK >= 0) {
    for (int k = 0; k < 3; k++) {
      if (k >= strands) break;
      for (int i = 0; i < n; i++) {
        float s0 = TAU * float(i) / float(n), s1 = TAU * float(i + 1) / float(n);
        float sm = 0.5 * (s0 + s1);
        if (k == bestK && abs(mod(sm - bestS + PI, TAU) - PI) < 0.6) continue;
        vec3 a = loopStrand(s0, k, morph, slide), b = loopStrand(s1, k, morph, slide);
        float z = 0.5 * (a.z + b.z);
        // Between braid strands the ink is thinner, so at real size the braid stays plasma, not a dark knot.
        // It fades in only as the strands separate, so the braiding never turns inky halfway.
        float iw = k == bestK ? INKW : INKW * 0.5 * smoothstep(0.55, 1.0, morph);
        // Another strand inks only where it is clearly in front, by the same tolerance that chose the body here.
        float ztol = k == bestK ? 0.0 : 0.03 * (1.0 - morph) + 0.004;
        if (sdSeg(p, a.xy, b.xy) - loopW(z, morph) < iw && z > bestZ + ztol) inkZ = 1.0;
      }
    }
  }
  frontZ = bestZ;
  vec4 col = vec4(0.0);
  if (bestK >= 0) {
    float trail = 0.0;
    if (trailT >= 0.0) {
      float behind = fract(trailT - bestS / TAU);
      trail = behind < 0.4 ? pow(1.0 - behind / 0.4, 1.6) : 0.0;
    }
    // Across the tube: 0 at its centre line, 1 at its edge; the light runs along the middle.
    float w = loopW(bestZ, morph);
    float u = clamp(1.0 + bestD / w, 0.0, 1.0);
    float face = 1.0 - u * u;
    // On the braid, beads of heat ride each strand with the twist (three a lap, in step with it, so the loop closes).
    float bead = morph * pow(0.5 + 0.5 * cos(3.0 * (bestS - slide) + TAU * float(bestK) / 3.0 + PI), 8.0);
    // The braid runs hotter than the rest tube: it is Rook at work, and its thin strands need the light.
    float h = 0.26 + 0.14 * morph + 0.36 * face + 0.12 * bestZ + 0.72 * trail + 0.55 * bead;
    vec3 c = mix(INK * 1.6, DEEP, cel(h, 0.22));
    c = mix(c, VIOLET, cel(h, 0.45));
    c = mix(c, PINK, cel(h, 0.72));
    c = mix(c, CORE, cel(h, 0.9));
    c = mix(c, CYAN, (1.0 - cel(u, 0.12)) * cel(bestZ, 0.0) * (1.0 - cel(trail, 0.15)) * 0.85);
    // The three strands differ a little in hue, so the braid reads as three: violet, rose, and cyan-lit.
    if (bestK == 1) c = mix(c, PINK, 0.18 * morph * cel(h, 0.4));
    if (bestK == 2) c = mix(c, CYAN, 0.22 * morph * cel(h, 0.4));
    col = paint(c, 1.0);
  }
  bool inkFront = inkZ > 0.0 || bestK < 0;
  float inkA = inkFront ? clamp(0.5 - (nearD - INKW) / AA, 0.0, 1.0) : 0.0;
  if (bestK < 0) col = paint(INK, inkA);
  else if (inkFront) col = paint(INK, 1.0);
  return col;
}
