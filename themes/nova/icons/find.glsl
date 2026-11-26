// Finding: Nova's crystal pylon, after the Devs prism the owner chose. A square bipyramid of plasma glass turns a quarter
// turn per loop (it has four-fold symmetry, so the loop closes), cel-lit with ink on every edge and a glowing inner
// seam and cross showing through. A sonar ping sweeps out over the ground twice a loop, the tip flares, and a short
// beam rises from it, as a waypoint marker does: Rook is looking for something. Made through the forge; STYLE 1 (a
// searchlight sweeping the ground) and STYLE 2 (facets lighting in turn) were the sketches it beat.
const int STYLE = 0;
const float PH = 0.5, PR = 0.33, TILT = 0.32, GY = -0.64;

vec3 pv(int k, float spin) {
  vec3 v = k == 0 ? vec3(0.0, PH, 0.0) : k == 1 ? vec3(0.0, -PH, 0.0)
         : vec3(PR * cos(spin + float(k - 2) * PI * 0.5), 0.0, PR * sin(spin + float(k - 2) * PI * 0.5));
  v.y += 0.06;
  return vec3(v.x, v.y * cos(TILT) - v.z * sin(TILT), v.y * sin(TILT) + v.z * cos(TILT));
}
float edgeSide(vec2 p, vec2 a, vec2 b) { return (b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x); }

vec4 icon(vec2 p, float t, int layer) {
  float spin = PI * 0.5 * t + 0.3;
  vec3 L = normalize(vec3(-0.55, 0.65, 0.55));
  float ping = fract(t * 2.0);
  // Ground: an ellipse under the pylon, with the effect of each style on it.
  vec2 g = vec2(p.x, (p.y - GY) / 0.24);
  float gr = length(g);
  vec4 ground = paint(mix(INK * 1.6, DEEP, 0.5), fill((gr - 0.62) * 0.24) * 0.55);
  ground = over(paint(INK, stroke((gr - 0.62) * 0.24, INKW * 0.6) * 0.6), ground);
  if (STYLE == 0) {
    for (int i = 0; i < 2; i++) {
      float f = fract(t * 2.0 + float(i) * 0.5);
      float d = abs(gr - (0.12 + 0.62 * f)) * 0.24 - 0.012 * (1.0 - f);
      ground = over(paint(mix(CORE, CYAN, f), fill(d) * (1.0 - f) * smoothstep(0.0, 0.1, f)), ground);
    }
  } else if (STYLE == 1) {
    float ang = atan(g.y, g.x) - TAU * t;
    float sweep = fract(ang / TAU);
    float beam = (1.0 - smoothstep(0.0, 0.25, sweep)) * fill((gr - 0.62) * 0.24);
    ground = over(paint(mix(CYAN, CORE, 1.0 - sweep / 0.25), beam * 0.75), ground);
  }
  // The pylon's faces, front ones only, nearest last.
  vec4 col = vec4(0.0);
  float edgeD = 1e9;
  int lit = int(mod(floor(t * 8.0), 8.0));
  for (int f = 0; f < 8; f++) {
    int e = f % 4;
    vec3 a = pv(f < 4 ? 0 : 1, spin), b = pv(2 + e, spin), c = pv(2 + (e + 1) % 4, spin);
    if (f >= 4) { vec3 tmp = b; b = c; c = tmp; }
    vec3 n = normalize(cross(b - a, c - a));
    if (n.z <= 0.0) continue;
    float s1 = edgeSide(p, a.xy, b.xy), s2 = edgeSide(p, b.xy, c.xy), s3 = edgeSide(p, c.xy, a.xy);
    bool inside = (s1 >= 0.0 && s2 >= 0.0 && s3 >= 0.0) || (s1 <= 0.0 && s2 <= 0.0 && s3 <= 0.0);
    edgeD = min(edgeD, min(sdSeg(p, a.xy, b.xy), min(sdSeg(p, b.xy, c.xy), sdSeg(p, c.xy, a.xy))));
    if (!inside) continue;
    float diff = dot(n, L) * 0.5 + 0.5;
    vec3 fc = mix(DEEP, VIOLET, cel(diff, 0.55));
    fc = mix(fc, mix(VIOLET, PINK, 0.6), cel(diff, 0.8));
    if (STYLE == 2 && f == lit) fc = mix(fc, mix(PINK, CORE, 0.5), 0.75);
    float flare = STYLE == 0 ? exp(-8.0 * ping) : 0.0;
    fc = mix(fc, CORE, flare * 0.35 * smoothstep(0.0, 0.3, p.y));
    col = paint(fc, 0.86);
  }
  // The inner seam and cross, glowing through the glass.
  vec3 top = pv(0, spin), bot = pv(1, spin);
  float seam = sdSeg(p, top.xy, bot.xy) - 0.012;
  float cross_ = abs(p.y - 0.06 * cos(TILT)) - 0.008;
  cross_ = max(cross_, abs(p.x) - PR * 0.8);
  float inner = min(seam, cross_);
  vec4 core = over(paint(mix(PINK, CORE, 0.6), fill(inner)), glow(PINK, 0.6 * exp(-pow(max(inner, 0.0) / 0.05, 2.0))));
  vec4 body = col.a > 0.0 ? over(col, core) : vec4(0.0);
  if (col.a > 0.0) body = over(paint(CORE, fill(inner) * 0.45), body);
  // Edges: thin ink inside, a full rim at the silhouette.
  vec4 ink = paint(INK, fill(edgeD - INKW * 0.7));
  vec4 tipGlow;
  tipGlow = glow(STYLE == 0 ? CORE : PINK, (0.35 + 0.5 * (STYLE == 0 ? exp(-8.0 * ping) : 0.0)) * exp(-pow(length(p - top.xy) / 0.07, 2.0)));
  vec4 halo = glow(VIOLET, 0.4 * exp(-pow(length((p - vec2(0.0, 0.04)) * vec2(1.4, 1.1)) / 0.4, 2.0)));
  // On each ping a short beam of light rises from the tip, as a waypoint marker does.
  float beamF = STYLE == 0 ? exp(-6.0 * ping) : 0.0;
  float beamD = max(abs(p.x) - 0.012 * (1.0 - (p.y - top.y) / 0.24), max(top.y + 0.02 - p.y, p.y - top.y - 0.24));
  tipGlow = over(paint(mix(CORE, PINK, (p.y - top.y) / 0.24), fill(beamD) * beamF), tipGlow);
  return over(tipGlow, over(ink, over(body, over(ground, halo))));
}
