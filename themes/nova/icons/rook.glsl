// Nova's rook. Devs' rook profile (ROOK_PROFILE in desktop/overlay.py), turned in dark plasma glass with an ink
// outline, cel-banded light, a cyan rim, glowing seams, and a star burning in the crown. It makes one full, slow turn per
// loop, like Devs' turning rook.

const float RS = 1.0 / 87.0;  // Devs units to icon units: the rook and its glow fit inside the cell's safe area.
const float RY = -0.026;      // Places the rook so its base and the crown's flame both stay inside the cell.
const float TILT = 0.22;      // The camera looks down a little, so the base reads as an ellipse.
const float SPAN = TAU / 5.0;
const int NP = 17;
// (radius, y down) in Devs units, from the base's centre round the outline to the crown floor's centre.
const vec2 PROF[NP] = vec2[NP](vec2(0, 58), vec2(40, 58), vec2(40, 51), vec2(36, 51), vec2(36, 45), vec2(34, 44),
  vec2(30, 40), vec2(25, 36), vec2(19, -14), vec2(26, -18), vec2(26, -24), vec2(21, -27), vec2(31, -44),
  vec2(31, -64), vec2(21, -64), vec2(21, -50), vec2(0, -50));

float sdProfile(vec2 q) {
  float d = 1e9, s = 1.0;
  for (int i = 0; i < NP; i++) {
    vec2 a = PROF[i], b = PROF[(i + 1) % NP];
    d = min(d, sdSeg(q, a, b));
    // Even-odd crossing test for the sign.
    if ((a.y > q.y) != (b.y > q.y) && q.x < a.x + (q.y - a.y) * (b.x - a.x) / (b.y - a.y)) s = -s;
  }
  return s * d;
}

// The rook's SDF in icon units; also returns its Devs height and angle for shading.
float rookSDF(vec3 p, float spin, out vec2 info) {
  p.xz = rot(spin) * p.xz;
  float r = length(p.xz) / RS, yd = -(p.y - RY) / RS;
  float d = sdProfile(vec2(r, yd));
  float a = atan(p.z, p.x);
  // Crenels: slots with parallel sides, so every merlon is the same clean block. A merlon spans the first half of
  // each fifth of the turn; the slot is centred on the second half, and the nearer of two slots is the one that cuts.
  float gc = (floor(a / SPAN) + 0.75) * SPAN;
  vec2 l0 = rot(-gc) * p.xz, l1 = rot(-gc + SPAN) * p.xz;
  float slot = min(max(abs(l0.y) / RS - 9.5, -l0.x), max(abs(l1.y) / RS - 9.5, -l1.x));
  float gap = max(slot, yd + 50.0);
  d = max(d, -gap);
  info = vec2(yd, a);
  return d * RS;
}

vec4 crownFlame(vec2 p, float t) {
  vec2 q = p - vec2(0.0, 0.6);
  float y = q.y;
  float up = y > 0.0 ? 0.2 : 0.08;
  float F = 1.0 - length(vec2(q.x / 0.11, y / up));
  float n = pfbm(vec3(q.x * 5.0, y * 4.0 - t * 4.0, t * 2.0), vec3(64.0, 4.0, 2.0), 3);
  F += 1.0 * n * clamp(0.2 + y * 2.4, 0.0, 1.0);
  F -= 3.0 * smoothstep(0.79, 0.85, p.y);   // The tip stays inside the top of the cell.
  float a = smoothstep(0.0, 0.04, F);
  vec4 c = paint(plasma(F * 1.6 + 0.18), a);

  vec4 g = glow(VIOLET, 0.6 * exp(-max(-F, 0.0) * 4.0) * (1.0 - a));
  // Sparks rise out of the crown, two lives per loop each.
  for (int i = 0; i < 9; i++) {
    float h = hash1(float(i) + 3.0);
    float life = fract(t * 2.0 + h);
    float x0 = (hash1(float(i) + 11.0) - 0.5) * 0.3;
    vec2 head = vec2(x0 + 0.05 * sin(life * 5.0 + h * 9.0), 0.6 + life * 0.2);
    vec2 tail = head - vec2(0.03 * cos(life * 5.0 + h * 9.0), 0.08);
    c = over(streak(p, tail, head, 0.014 * (1.0 - life), mix(PINK, CYAN, step(0.5, h))), c);
  }
  return over(c, g);
}

vec4 icon(vec2 p, float t, int layer) {
  float spin = -fract(t) * TAU + 0.3;  // One full turn per loop. fract: t = 1 is exactly t = 0, to the last bit.
  vec3 right = vec3(1, 0, 0), up = vec3(0, cos(TILT), -sin(TILT)), fwd = vec3(0, -sin(TILT), -cos(TILT));
  vec3 ro = right * p.x + up * p.y - fwd * 3.0, rd = fwd;
  float dist = 0.0, minD = 1e9, d = 1e9;
  vec2 info;
  bool hit = false;
  if (abs(p.x) < 0.66) {
    for (int i = 0; i < 110; i++) {
      d = rookSDF(ro + rd * dist, spin, info);
      minD = min(minD, d);
      if (d < 0.0006) { hit = true; break; }
      dist += d * 0.85;
      if (dist > 6.0) break;
    }
  }
  vec4 col = vec4(0.0);
  // The crown's star burns inside the crown: in front of the crown's back wall and floor, behind its front wall.
  vec4 flame = crownFlame(p, t);
  vec4 back = vec4(0.0);
  vec2 g = vec2(p.x, (p.y + 0.63) / 0.22);
  float ring = 0.6 + 0.2 * fract(t);  // Spreads only to the edge of the base glow, well inside the cell.
  float shock = stroke(length(g) - ring, 0.018 / 0.22 * (1.0 - fract(t))) * (1.0 - fract(t));
  back = over(back, paint(mix(CYAN, VIOLET, fract(t)), shock * 0.9));
  back = over(back, glow(VIOLET, 0.35 * exp(-pow(max(length(g) - 0.5, 0.0) / 0.17, 2.0))));
  if (hit) {
    vec3 pos = ro + rd * dist;
    vec2 e = vec2(0.0015, 0.0);
    vec2 tmp;
    vec3 n = normalize(vec3(rookSDF(pos + e.xyy, spin, tmp) - rookSDF(pos - e.xyy, spin, tmp),
                            rookSDF(pos + e.yxy, spin, tmp) - rookSDF(pos - e.yxy, spin, tmp),
                            rookSDF(pos + e.yyx, spin, tmp) - rookSDF(pos - e.yyx, spin, tmp)));
    float yd = info.x;
    vec3 L = normalize(vec3(-0.8, 0.5, 0.32));
    float diff = dot(n, L) * 0.5 + 0.5;
    float spec = pow(max(dot(n, normalize(L - rd)), 0.0), 16.0);
    float fres = 1.0 - abs(dot(n, rd));
    // Heat: the body's light, a pulse that climbs the rook once per loop, and the seams at its steps.
    float pulse = exp(-abs(yd - mix(120.0, -125.0, t)) / 7.0);
    float seams = 0.0;
    for (int i = 0; i < 4; i++) {
      float ys = float[4](51.0, 44.0, -21.0, -44.0)[i];
      seams = max(seams, 1.0 - smoothstep(0.6, 1.6, abs(yd - ys)));
    }
    // Plasma currents in the glass, fixed to it and different all the way round, so the eye reads the turn.
    float vein = abs(pnoise(vec3((info.y / TAU + 0.5) * 5.0, yd / 26.0, 0.5), vec3(5.0, 5.0, 9.0)));
    vein = (1.0 - cel(vein, 0.075)) * (1.0 - cel(abs(n.y), 0.55));
    // Volume, as an anime painter shades a turned piece: a lit side, a dark core shadow at the terminator, bounce
    // light on the far side, a cyan rim at the silhouette, and a hard highlight stripe down the lit side.
    float top = cel(n.y, 0.75);                          // Flat tops: the merlons and the steps.
    float shade = diff + 0.18 * top;
    vec3 body = mix(INK * 1.7, DEEP, cel(shade, 0.36));
    body = mix(body, VIOLET, cel(shade, 0.6));
    body = mix(body, mix(DEEP, VIOLET, 0.35), cel(fres, 0.5) * (1.0 - cel(shade, 0.5)) * (1.0 - top));
    body = mix(body, CYAN, cel(fres, 0.78) * (1.0 - cel(shade, 0.55)) * 0.9);
    // Heat on top: the climbing pulse, the seams and the veins glow pink to white.
    body = mix(body, mix(body, PINK, 0.55), vein);
    float heat = pulse * 0.6 + seams * (0.6 + 0.4 * pulse) + vein * 0.6 * pulse;
    body = mix(body, PINK, cel(heat, 0.4));
    body = mix(body, CORE, max(cel(heat, 0.85), cel(spec, 0.55) * (1.0 - top)));
    // The crown, crisp and closed: the inside walls and floor sit in shadow, warmed a little by the ember; the merlon
    // tops catch the light as a clean rim; and an ink line marks every edge where a merlon's top meets its sides.
    float rr = length(pos.xz) / RS;
    if (rr < 21.8 && yd < -48.5) body = mix(mix(INK * 1.5, DEEP, 0.45), PINK, 0.18 * (1.0 - smoothstep(-64.0, -50.0, yd)));
    if (top > 0.5 && yd < -62.0) body = mix(VIOLET, CORE, 0.5);
    if (yd < -55.0 && n.y > 0.2 && n.y < 0.7) body = INK;
    col = paint(body, 1.0);
    float crownDepth = dot(vec3(0.0, RY + 50.0 * RS, 0.0), fwd);
    if (info.x < -44.0 && dot(pos, fwd) > crownDepth - 0.02) col = over(flame, col);
  } else if (minD < INKW) {
    col = paint(INK, 1.0);
  } else {
    col = glow(VIOLET, 0.45 * exp(-pow((minD - INKW) / 0.04, 2.0)) * step(minD, 1e8));
  }
  // The outline closes around the hit edge too: blend the ink ring's soft edge.
  if (!hit && minD < INKW + AA) col = mix(col, paint(INK, 1.0), 1.0 - smoothstep(INKW, INKW + AA, minD));
  // A four-point sparkle above the crown flares twice per loop.
  float tw = snap(t + 0.1, 2.0, 4.0);
  vec2 s = p - vec2(0.24, 0.69);
  float star = max(1.0 - length(s * vec2(1.0, 8.0)) / (0.11 * tw), 1.0 - length(s * vec2(8.0, 1.0)) / (0.11 * tw));
  vec4 spark = over(paint(CORE, smoothstep(0.0, 0.1, star)), glow(PINK, 0.5 * tw * exp(-pow(length(s) / 0.06, 2.0))));
  if (!hit) back = over(flame, back);
  return over(spark, over(col, back));
}
