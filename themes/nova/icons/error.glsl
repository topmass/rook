// An error: a ring of rose plasma, cracked open at the top right, its broken ends sparking at each other, with a bold
// inked "!" at its centre. On each beat the ring jolts and a glitch slides a band sideways. Rose is Nova's colour for
// trouble.

vec3 roseRamp(float h) {
  vec3 c = mix(vec3(0.3, 0.03, 0.14), vec3(0.62, 0.08, 0.28), cel(h, 0.3));
  c = mix(c, ROSE, cel(h, 0.55));
  return mix(c, CORE, cel(h, 0.86));
}

const float RR = 0.46, RW = 0.075;   // The ring's radius and half-thickness.
const float GAPA = 0.75;              // The crack's angle (top right), and its half-width in radians below.

vec4 icon(vec2 p, float t, int layer) {
  float k = floor(fract(t) * 12.0);
  float beat = snap(t, 2.0, 7.0);
  // Glitch: on some steps, a band slides sideways.
  float band = floor(p.y * 7.0);
  if (hash1(vec3(k, 2.0, 0.0)) > 0.6 && hash1(vec3(k, band, 5.0)) > 0.7) p.x += (hash1(vec3(k, band, 9.0)) - 0.5) * 0.12;
  vec2 q = p + vec2(0.018 * beat * sin(TAU * 7.0 * t), 0.0);
  float r = length(q), a = atan(q.y, q.x);
  // The ring as a tube, cut by the crack; its ends jitter apart on the beat.
  float gapHalf = 0.16 + 0.06 * beat;
  float da = abs(mod(a - GAPA + PI, TAU) - PI);
  float tube = abs(r - RR) - RW;
  float cut = (gapHalf - da) * r;             // > 0 inside the crack.
  float ring = max(tube, cut);
  float u = clamp(abs(r - RR) / RW, 0.0, 1.0);
  float lit = dot(normalize(vec3(q / max(r, 1e-3) * (r - RR) / RW, 0.8)), normalize(vec3(-0.5, 0.6, 0.6)));
  vec3 rc = roseRamp(0.2 + 0.4 * lit + 0.2 * (1.0 - u * u) + 0.2 * beat);
  // A dark glass disc inside the ring, so the mark reads on any desktop.
  float disc = r - (RR - RW + 0.005);
  vec4 col = paint(mix(INK * 1.5, vec3(0.3, 0.03, 0.14), cel(-q.y * 0.5 + 0.2 - r * 0.5, 0.2)), fill(disc));
  col = over(over(paint(rc, fill(ring)), paint(INK, fill(ring - INKW))), col);
  // Sparks arc across the crack between the two broken ends.
  vec2 e0 = RR * vec2(cos(GAPA - gapHalf), sin(GAPA - gapHalf)), e1 = RR * vec2(cos(GAPA + gapHalf), sin(GAPA + gapHalf));
  vec2 dir = e1 - e0, nrm = normalize(vec2(-dir.y, dir.x));
  float bd = 1e9;
  vec2 prev = e0;
  for (int i = 1; i <= 5; i++) {
    float f = float(i) / 5.0;
    vec2 cur = i == 5 ? e1 : e0 + dir * f + nrm * (hash1(vec3(k, float(i), 7.0)) - 0.5) * 0.12 * sin(PI * f);
    bd = min(bd, sdSeg(q, prev, cur));
    prev = cur;
  }
  col = over(over(paint(CORE, fill(bd - 0.008)), paint(ROSE, fill(bd - 0.018))), col);
  col = over(col, glow(ROSE, 0.5 * exp(-pow(bd / 0.05, 2.0))));
  // The "!": a tapered bar and a dot, white-hot in an ink edge.
  float bar = sdTaper(q, vec2(0.0, 0.21), vec2(0.0, -0.05), 0.06, 0.038);
  float dot_ = length(q - vec2(0.0, -0.18)) - 0.055;
  float mark = min(bar, dot_);
  col = over(over(paint(mix(CORE, ROSE, 0.25 * (1.0 - beat)), fill(mark)), paint(INK, fill(mark - INKW))), col);
  // Embers drip from the crack.
  for (int i = 0; i < 6; i++) {
    float hs = hash1(float(i) + 51.0), life = fract(t * 2.0 + hs);
    vec2 o = mix(e0, e1, hs) + vec2(0.0, -0.02);
    vec2 head = o + vec2(0.06 * (hs - 0.5), -0.55 * life * life);
    col = over(streak(q, head + vec2(0.0, 0.07), head, 0.013 * (1.0 - life), ROSE), col);
  }
  vec4 g = glow(ROSE, (0.35 + 0.25 * beat) * exp(-pow(abs(r - RR) / 0.16, 2.0)) * (1.0 - smoothstep(0.62, 0.75, r)));
  return over(col, g);
}
