// Sending work to a thread: a cascade. Water made of light pours from a plasma portal, falls in streaky cel-shaded
// sheets that split into three streams, and crashes into a pool with a foam crown, spray, and ripples. The fall scrolls two whole noise periods per
// loop, so the loop is seamless.

const vec2 LIP = vec2(0.0, 0.6);    // The portal's centre.
const vec2 LIPR = vec2(0.4, 0.095);  // Its radii.
const float POOL = -0.6;            // The pool's centre height.

vec4 icon(vec2 p, float t, int layer) {
  p.y -= 0.1;  // Lifted, to leave the bottom of the cell for the thread's name (manifest: icons.cascade.label).
  // The pool: a tilted ellipse of water with two ripples spreading per loop.
  vec2 pq = (p - vec2(0.0, POOL)) / vec2(0.74, 0.15);
  float pr = length(pq);
  vec4 pool = paint(mix(DEEP, VIOLET, cel(0.75 - pr, 0.25)), fill((pr - 1.0) * 0.08));
  pool = over(paint(INK, stroke((pr - 1.0) * 0.08, 0.006)), pool);
  for (int i = 0; i < 2; i++) {
    float f = fract(t * 2.0 + float(i) * 0.5);
    float rr = 0.35 + 0.6 * f;
    pool = over(paint(mix(CORE, CYAN, f), stroke((pr - rr) * 0.08, 0.006 * (1.0 - f)) * (1.0 - f)), pool);
  }

  // The falling sheet: from the portal's front edge to the pool, widening a little, its edges ragged.
  float top = LIP.y - LIPR.y * 0.4, bot = POOL + 0.05;
  float y01 = clamp((top - p.y) / (top - bot), 0.0, 1.0);
  float w = mix(0.25, 0.4, y01 * y01) + 0.03 * pnoise(vec3(p.y * 6.0 + t * 8.0, 1.5, 0.5), vec3(8.0, 4.0, 4.0));
  float dEdge = abs(p.x) - w;
  float d = max(dEdge, max(p.y - top, bot - p.y));
  float flow = pfbm(vec3(p.x * 7.0, p.y * 1.6 + t * 4.0, 0.5), vec3(64.0, 4.0, 4.0), 3);
  float streaks = pnoise(vec3(p.x * 22.0, p.y * 0.8 + t * 2.0, 1.5), vec3(128.0, 2.0, 4.0));
  // Ribbons: the sheet splits into falling strands, with white speed lines on them.
  float ribbon = 0.5 + 0.5 * cos(p.x / mix(1.0, 1.5, y01) * 24.0 + 3.0 * flow);
  float heat = 0.22 + 0.32 * ribbon + 0.55 * flow + 0.3 * (1.0 - smoothstep(0.0, 0.06, -dEdge)) + 0.35 * y01 * y01;
  // Gaps open in the sheet where the flow thins, so it reads as falling water, not a wall.
  // Lower down the fall splits into three streams: three threads, for sending work to a thread.
  float split = smoothstep(0.35, 0.85, y01);
  float gaps = abs(abs(p.x) - w * 0.34) - 0.07 * split;
  if (split > 0.01) d = max(d, -gaps);
  float body = fill(d) * cel(heat, 0.24);
  vec3 wc = mix(water(heat), CORE, cel(streaks, 0.42) * cel(heat, 0.45));
  vec4 sheet = paint(wc, body);
  sheet = over(sheet, paint(INK, fill(d - INKW) * (1.0 - body) * step(p.y, top)));

  // The foam crown where it lands.
  vec2 fq = (p - vec2(0.0, POOL + 0.05)) / vec2(0.5, 0.15);
  float F = 1.0 - length(fq) + 0.8 * pfbm(vec3(p.x * 9.0, p.y * 7.0 - t * 8.0, t * 2.0), vec3(64.0, 8.0, 2.0), 3);
  F = p.y < POOL - 0.04 ? -1.0 : F;
  vec4 foam = paint(water(0.45 + F * 1.4), smoothstep(0.0, 0.05, F));
  foam = over(foam, paint(INK, smoothstep(-0.06, -0.03, F) * (1.0 - smoothstep(0.0, 0.05, F))));

  // Spray: droplets thrown up and out, two lives per loop each.
  vec4 spray = vec4(0.0);
  for (int i = 0; i < 22; i++) {
    float h = hash1(float(i) + 70.0);
    float life = fract(t * 2.0 + h);
    float side = hash1(float(i) + 90.0) * 2.0 - 1.0;
    vec2 v0 = vec2(side * 0.72, 1.0 + 0.7 * hash1(float(i) + 110.0));
    vec2 o = vec2(side * 0.3, POOL + 0.08);
    float s = life * 0.55, s2 = max(life - 0.05, 0.0) * 0.55;
    vec2 head = o + v0 * s + vec2(0.0, -2.6) * s * s;
    vec2 tail = o + v0 * s2 + vec2(0.0, -2.6) * s2 * s2;
    spray = over(streak(p, tail, head, 0.016 * (1.0 - life), mix(CYAN, CORE, step(0.7, h))), spray);
  }

  // The portal: an inked plasma ring with a dark inside. Its back half sits behind the sheet, its front half before.
  vec2 lq = (p - LIP) / LIPR;
  float lr = length(lq);
  float ringD = (lr - 1.0) * LIPR.y;
  float swirl = 0.5 + 0.5 * cos(atan(lq.y, lq.x) * 3.0 - TAU * 2.0 * t);
  float inner = pnoise(vec3(lq * vec2(1.2, 0.5) + 5.0, t * 2.0), vec3(64.0, 64.0, 2.0));
  vec4 hole = paint(water(0.25 + 0.6 * lr + 0.4 * inner), fill(ringD));
  vec4 ring = over(paint(plasma(0.3 + 0.55 * swirl), stroke(ringD, 0.012)), paint(INK, stroke(ringD, 0.02)));
  bool front = lq.y < 0.0;

  vec4 g = glow(CYAN, 0.6 * exp(-pow(length((p - vec2(0.0, POOL + 0.08)) / vec2(0.7, 0.3)) * 1.9, 2.0)));
  g = over(glow(VIOLET, 0.4 * exp(-pow(max(lr - 1.0, 0.0) / 0.3, 2.0))), g);
  vec4 col = over(foam, over(spray, over(sheet, over(pool, g))));
  if (front) return over(ring, over(col, hole));
  return over(col, over(ring, hole));
}
