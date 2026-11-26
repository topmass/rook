// The forge's shared helpers. Every icon shader gets this file, then its theme's common.glsl, then its own source.
// An icon defines: vec4 icon(vec2 p, float t, int layer)
//   p: the icon's square, from -1 to 1 on both axes, y up.
//   t: the loop's phase, from 0 up to 1. At t = 1 the loop is back at t = 0.
//   layer: which layer to draw, by its index in the icon's "layers" list.
// It returns premultiplied colour. The forge clamps rgb to alpha.
precision highp float;
uniform vec2 u_res;
uniform float u_t;
uniform int u_layer;
out vec4 forge_out;

#define PI 3.14159265
#define TAU 6.28318531
float AA;  // One pixel, in icon units. Use it to keep cel edges crisp but not jagged.

// A small integer hash, after the pcg3d idea of Jarzynski and Olano (2020), written here from scratch.
uvec3 forge_pcg(uvec3 v) {
  v = v * 1664525u + 1013904223u;
  v.x += v.y * v.z; v.y += v.z * v.x; v.z += v.x * v.y;
  v ^= v >> 16u;
  v.x += v.y * v.z; v.y += v.z * v.x; v.z += v.x * v.y;
  return v;
}
float hash1(vec3 c) { return float(forge_pcg(uvec3(ivec3(c) + 4096)).x & 0xffffffu) / 16777215.0; }
vec3 hash3(vec3 c) { return vec3(forge_pcg(uvec3(ivec3(c) + 4096)) & 0xffffffu) / 16777215.0; }
float hash1(float c) { return hash1(vec3(c, 7.0, 13.0)); }

// Gradient noise that repeats every `per` cells on each axis. Use whole-number periods.
// Seamless loops: scroll an axis by a whole number of periods over t, or use (z = t * per.z).
float pnoise(vec3 p, vec3 per) {
  vec3 i = floor(p), f = p - i;
  vec3 u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
  float r[8];
  for (int k = 0; k < 8; k++) {
    vec3 o = vec3(k & 1, (k >> 1) & 1, (k >> 2) & 1);
    vec3 g = hash3(mod(i + o, per)) * 2.0 - 1.0;
    r[k] = dot(normalize(g + 1e-4), f - o);
  }
  return mix(mix(mix(r[0], r[1], u.x), mix(r[2], r[3], u.x), u.y),
             mix(mix(r[4], r[5], u.x), mix(r[6], r[7], u.x), u.y), u.z) * 1.4;
}
// Fractal sum of pnoise; each octave doubles the frequency and the period, so it stays seamless.
float pfbm(vec3 p, vec3 per, int oct) {
  float s = 0.0, a = 0.5;
  for (int k = 0; k < 6; k++) {
    if (k >= oct) break;
    s += a * pnoise(p, per);
    p *= 2.0; per *= 2.0; a *= 0.5;
  }
  return s;
}

// Loop helpers. ph(t, n) is t * n * TAU, for n whole turns per loop.
float ph(float t, float n) { return t * n * TAU; }
// A pulse that rises fast and falls slowly, with peaks at phase 0 of each of n beats.
float snap(float t, float n, float sharp) { return exp(-sharp * fract(t * n)); }

// Cel helpers.
float cel(float x, float edge) { return smoothstep(edge - AA, edge + AA, x); }
float fill(float d) { return clamp(0.5 - d / AA, 0.0, 1.0); }      // Inside an SDF, anti-aliased.
float stroke(float d, float w) { return fill(abs(d) - w); }       // A line of half-width w along an SDF edge.
float bands(float x, float n) { return floor(clamp(x, 0.0, 0.9999) * n) / (n - 1.0); }

// Premultiplied compositing.
vec4 over(vec4 top, vec4 bot) { return top + bot * (1.0 - top.a); }
vec4 paint(vec3 c, float a) { return vec4(c * a, a); }
// A glow that reads on dark and on light: its alpha follows its brightest channel.
vec4 glow(vec3 c, float g) { vec3 rgb = c * g; return vec4(rgb, max(max(rgb.r, rgb.g), rgb.b)); }

// 2D shapes.
mat2 rot(float a) { float c = cos(a), s = sin(a); return mat2(c, s, -s, c); }
float sdCircle(vec2 p, float r) { return length(p) - r; }
float sdBox(vec2 p, vec2 b) { vec2 d = abs(p) - b; return length(max(d, 0.0)) + min(max(d.x, d.y), 0.0); }
float sdSeg(vec2 p, vec2 a, vec2 b) {
  vec2 pa = p - a, ba = b - a;
  return length(pa - ba * clamp(dot(pa, ba) / max(dot(ba, ba), 1e-8), 0.0, 1.0));
}
// A segment that tapers from width wa at a to wb at b: good for streaks and flame tongues.
float sdTaper(vec2 p, vec2 a, vec2 b, float wa, float wb) {
  vec2 pa = p - a, ba = b - a;
  float h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-8), 0.0, 1.0);
  return length(pa - ba * h) - mix(wa, wb, h);
}
float sdRing(vec2 p, float r, float w) { return abs(length(p) - r) - w; }
// An arc of the circle of radius r, centred on angle a0 with half-span hs.
float sdArc(vec2 p, float r, float a0, float hs, float w) {
  p = rot(-a0) * p;
  float a = atan(p.y, p.x);
  if (abs(a) < hs) return abs(length(p) - r) - w;
  vec2 e = r * vec2(cos(hs), sin(hs) * sign(a));
  return length(p - e) - w;
}
