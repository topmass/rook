// Thinking: a synapse. A hub orb sits among three nodes, joined by inked plasma links that carry pulses inward. In
// turn, lightning leaps from the hub to each node, which flares with a ring. The bolts are redrawn every other
// frame, as hand-drawn lightning is, and the pattern repeats each loop.

vec2 node(int i) { float a = TAU * float(i) / 3.0 + PI / 2.0; return vec2(cos(a), sin(a) * 0.9 - 0.02) * 0.56; }

// Distance to a jagged bolt from a to b, its kinks chosen by seed.
float bolt(vec2 p, vec2 a, vec2 b, float seed, float amp) {
  vec2 dir = b - a, nrm = normalize(vec2(-dir.y, dir.x));
  float d = 1e9;
  vec2 prev = a;
  for (int k = 1; k <= 7; k++) {
    float f = float(k) / 7.0;
    vec2 cur = k == 7 ? b : a + dir * f + nrm * (hash1(vec3(seed, float(k), 3.0)) - 0.5) * amp * sin(PI * f);
    d = min(d, sdSeg(p, prev, cur));
    prev = cur;
  }
  return d;
}

vec4 icon(vec2 p, float t, int layer) {
  float step12 = floor(fract(t) * 12.0);
  int live = int(mod(floor(t * 3.0), 3.0));
  float beat = fract(t * 3.0);
  float hit = exp(-7.0 * beat);
  vec2 hub = vec2(0.0, 0.03);
  vec4 col = glow(VIOLET, 0.35 * exp(-pow(length(p) / 0.38, 2.0)));
  // The outer ring: a thin inked line joining the nodes.
  float ringD = 1e9;
  for (int i = 0; i < 3; i++) ringD = min(ringD, sdSeg(p, node(i), node((i + 1) % 3)));
  col = over(paint(DEEP, fill(ringD - 0.008)), over(paint(INK, fill(ringD - 0.016) * 0.8), col));
  // The links: plasma tubes from each node to the hub, with three pulses per loop running inward.
  float linkD = 1e9, pulseH = 0.0;
  for (int i = 0; i < 3; i++) {
    vec2 a = node(i);
    float d = sdTaper(p, a, hub, 0.02, 0.03);
    float along = clamp(dot(p - a, hub - a) / dot(hub - a, hub - a), 0.0, 1.0);
    float pul = exp(-pow((fract(along - t * 3.0 + float(i) * 0.33) - 0.5) / 0.08, 2.0));
    if (d < linkD) { linkD = d; pulseH = pul; }
  }
  vec4 link = paint(mix(mix(DEEP, VIOLET, 0.6), CORE, cel(pulseH, 0.5)), fill(linkD));
  col = over(link, over(paint(INK, fill(linkD - 0.014)), col));
  // The live bolt: hub to node, white core in cyan, with a fork.
  vec2 tgt = node(live);
  float seed = step12 * 7.0 + float(live) * 31.0;
  float d = bolt(p, hub, tgt, seed, 0.3);
  vec2 mid = mix(hub, tgt, 0.45);
  float br = bolt(p, mid, mid + rot(1.0 * (hash1(vec3(seed, 2.0, 9.0)) - 0.5) + 0.9) * (tgt - hub) * 0.4, seed + 55.0, 0.15);
  float fade = 1.0 - smoothstep(0.55, 0.9, beat);
  col = over(glow(CYAN, 0.7 * fade * exp(-pow(min(d, br) / 0.06, 2.0))), col);
  col = over(paint(INK, fill(d - 0.03) * fade), col);
  col = over(paint(CYAN, max(fill(d - 0.02), fill(br - 0.011)) * fade), col);
  col = over(paint(CORE, max(fill(d - 0.009), fill(br - 0.004)) * fade), col);
  // The struck node's ring flares outward.
  float rr = 0.12 + 0.13 * beat;
  col = over(paint(mix(CORE, CYAN, beat), stroke(length(p - tgt) - rr, 0.014 * (1.0 - beat))), col);
  for (int i = 0; i < 3; i++) {
    float hot = i == live ? hit : 0.0;
    col = over(orb(p - node(i), 0.105 + 0.025 * hot, t + float(i) * 0.33, -0.02 + 0.32 * hot), col);
  }
  return over(orb(p - hub, 0.14 + 0.015 * hit, t, -0.06 + 0.2 * hit), col);
}
