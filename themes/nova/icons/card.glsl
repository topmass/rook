// Waiting on the owner: a card held up to them. A thick bevelled card rocks gently in three dimensions. Its face has an
// inset frame with corner diamonds, a raised plasma question mark that casts a shadow on the face, a glint that
// sweeps as it turns, and two sparks circling the mark: the card is waiting, and alive.

float sdRound(vec2 p, vec2 b, float r) { return sdBox(p, b - r) - r; }
float sdDiamond(vec2 p, float r) { return (abs(p.x) + abs(p.y) - r) * 0.7071; }

const vec2 CARD = vec2(0.37, 0.52);
const float THICK = 0.07;

// The question mark on the card's face, in face coordinates.
float markSDF(vec2 g) {
  float hook = sdArc(g - vec2(0.0, 0.12), 0.14, PI * 0.25, PI * 0.72, 0.042);
  float stem = sdSeg(g, vec2(0.0, -0.02), vec2(0.0, -0.1)) - 0.042;
  return min(min(hook, stem), length(g - vec2(0.0, -0.22)) - 0.05);
}

vec4 icon(vec2 p, float t, int layer) {
  float a = 0.4 * sin(TAU * t);                  // The rock about the vertical axis.
  vec2 q = rot(-0.07) * (p - vec2(0.0, 0.025 * sin(TAU * 2.0 * t)));
  float ca = cos(a), sa = sin(a);
  // Face coordinates undo the turn (orthographic, so x shrinks by cos a); the back face sits one thickness behind.
  vec2 f = vec2(q.x / ca, q.y);
  float d = sdRound(f, CARD, 0.08) * ca;
  vec2 b = vec2((q.x + THICK * sa) / ca, q.y);
  float db = sdRound(b, CARD, 0.08) * ca;
  // The edge: a violet slab, lit on one side, with an ink outline.
  vec4 slab = over(paint(mix(DEEP, VIOLET, 0.25 + 0.3 * step(0.0, sa)), fill(db)), paint(INK, fill(db - INKW)));
  // The face: lit by its turn toward the light, darker toward the bottom, a glint band sweeping across.
  float lit = 0.5 + 0.5 * dot(normalize(vec3(sa, 0.0, ca)), normalize(vec3(-0.5, 0.4, 0.75)));
  vec3 fc = mix(INK * 1.7, DEEP, cel(lit + f.y * 0.35, 0.62));
  float glint = 1.0 - cel(abs(f.x + f.y * 0.5 + a * 1.8) - 0.06, 0.0);
  fc = mix(fc, mix(fc, VIOLET, 0.55), glint);
  vec4 face = paint(fc, fill(d));
  // The inset frame: a thin plasma line, with diamonds at its corners.
  float frame = sdRound(f, CARD - 0.06, 0.05);
  float frameLine = abs(frame) - 0.008;
  vec2 cq = abs(f) - (CARD - 0.06 - 0.03);
  float dia = sdDiamond(cq, 0.035);
  float orn = min(frameLine, dia) * ca;
  vec4 ornament = paint(mix(VIOLET, PINK, 0.35 + 0.3 * glint), fill(orn));
  // The question mark: a shadow cast down and away from the light, then the raised mark with a lit top edge.
  vec2 g = f - vec2(0.0, 0.05);
  float shadow = markSDF(g + vec2(0.025, 0.03)) * ca;
  float mark = markSDF(g) * ca;
  float topEdge = markSDF(g - vec2(0.008, -0.012)) * ca;
  float pulse = 0.5 + 0.5 * cos(TAU * t);
  vec3 mc = plasma(0.55 + 0.25 * pulse);
  mc = mix(mc, CORE, (1.0 - fill(topEdge)) * fill(mark));      // The rim that catches the light.
  vec4 m = over(paint(mc, fill(mark)), paint(INK, fill(mark - INKW * 0.8)));
  m = over(m, paint(INK * 0.6, fill(shadow) * 0.7));
  // Two sparks circle the mark, half a loop apart.
  vec4 motes = vec4(0.0);
  for (int i = 0; i < 2; i++) {
    float ang = TAU * (t + float(i) * 0.5);
    vec2 c = vec2(0.0, 0.02) + vec2(cos(ang) * 0.24, sin(ang) * 0.3);
    vec2 c2 = vec2(0.0, 0.02) + vec2(cos(ang - 0.35) * 0.24, sin(ang - 0.35) * 0.3);
    vec2 sc = vec2(c.x * ca, c.y), sc2 = vec2(c2.x * ca, c2.y);
    motes = over(streak(q, sc2, sc, 0.018, i == 0 ? CYAN : PINK), motes);
  }
  // The card's front edge: a plasma line inside the ink.
  vec4 edge = paint(mix(VIOLET, CORE, glint * 0.6), stroke(d + 0.016, 0.008));
  vec4 ink = paint(INK, stroke(d, INKW));
  vec4 halo = glow(VIOLET, 0.42 * exp(-pow(max(min(d, db), 0.0) / 0.08, 2.0)));
  vec4 markGlow = glow(PINK, (0.25 + 0.25 * pulse) * exp(-pow(max(mark, 0.0) / 0.07, 2.0)) * fill(d));
  return over(motes, over(edge, over(ink, over(m, over(markGlow, over(ornament, over(face, over(slab, halo))))))));
}
