// Listening: a helix. Two plasma strands, one violet and one cyan, twist round a glowing spine and pass in front of
// each other, joined by rungs. Layer "main" is the spine; layer "voice" is the strands, which the player stretches
// tall with the incoming voice level (manifest: states.listening.voice). The twist turns once per loop.

const float HALF = 0.78;   // Half the helix's length.
const float AMP = 0.3;     // The strands' full height, before the player's stretch.
const float TURNS = 2.5;

float env(float x) { return pow(max(0.0, 1.0 - pow(x / HALF, 2.0)), 0.6); }

// Strand i at x: its height, its depth (z > 0 nearer), and its slope.
vec3 strand(float x, int i, float t) {
  float a = x / HALF * PI * TURNS - TAU * t + float(i) * PI;
  float e = env(x) * AMP;
  float de = (env(x + 0.002) - env(x - 0.002)) / 0.004 * AMP;
  return vec3(e * sin(a), cos(a), de * sin(a) + e * cos(a) * PI * TURNS / HALF);
}

vec4 icon(vec2 p, float t, int layer) {
  if (abs(p.x) > HALF + 0.06) return vec4(0.0);
  if (layer == 0) {
    // The spine: a thin bright line with a soft glow and two motes running along it.
    float d = abs(p.y) - 0.008 * (0.3 + env(p.x));
    vec4 c = over(paint(mix(VIOLET, CORE, 0.6), fill(d) * cel(env(p.x), 0.02)), glow(VIOLET, 0.45 * env(p.x) * exp(-pow(p.y / 0.06, 2.0))));
    for (int k = 0; k < 2; k++) {
      float x = -HALF + 2.0 * HALF * fract(t + float(k) * 0.5);
      c = over(glow(CYAN, 0.7 * env(x) * exp(-pow(length(p - vec2(x, 0.0)) / 0.04, 2.0))), c);
    }
    return c;
  }
  // The strands: for each, the distance across the tube, its depth, and its shading.
  float dS[2], zS[2];
  for (int i = 0; i < 2; i++) {
    vec3 s = strand(p.x, i, t);
    float w = 0.034 * (0.75 + 0.35 * s.y) * (0.35 + 0.65 * env(p.x));
    dS[i] = abs(p.y - s.x) / sqrt(1.0 + s.z * s.z) - w;
    zS[i] = s.y;
  }
  // Rungs: thin bars between the strands every so often, at the depth between them.
  float rx = (floor(p.x / 0.11) + 0.5) * 0.11;
  vec3 r0 = strand(rx, 0, t), r1 = strand(rx, 1, t);
  float rung = max(abs(p.x - rx) - 0.008, (abs(p.y - 0.5 * (r0.x + r1.x)) - 0.5 * abs(r0.x - r1.x)));
  vec4 col = over(paint(DEEP, fill(rung) * cel(env(rx), 0.1)), paint(INK, fill(rung - 0.01) * cel(env(rx), 0.1) * 0.8));
  // Draw the far strand, then the near one, each with ink and tube shading.
  int nearI = zS[0] > zS[1] ? 0 : 1;
  for (int k = 0; k < 2; k++) {
    int i = k == 0 ? 1 - nearI : nearI;
    vec3 s = strand(p.x, i, t);
    float w = 0.034 * (0.75 + 0.35 * s.y) * (0.35 + 0.65 * env(p.x));
    float u = clamp(1.0 + dS[i] / max(w, 1e-3), 0.0, 1.0);
    float h = 0.3 + 0.35 * (1.0 - u * u) + 0.25 * s.y;
    vec3 c = i == 0 ? plasma(h) : water(h);
    c = mix(c, mix(INK * 1.6, DEEP, 0.5), cel(-s.y, 0.55) * 0.5);   // The far side of the twist sinks into shadow.
    col = over(paint(c, fill(dS[i])), over(paint(INK, fill(dS[i] - INKW)), col));
  }
  return over(col, glow(VIOLET, 0.35 * exp(-pow(max(min(dS[0], dS[1]), 0.0) / 0.05, 2.0))));
}
