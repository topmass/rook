// Thinking: the board. A small chessboard floats at an angle; a spark of thought leaps across it in knight's moves,
// four hops round a closed tour each loop, lighting each square it lands on with a ring.

const float SX = 0.17, SY = 0.095, OY = -0.05, TH = 0.06;
// The tour: (0,0) -> (1,2) -> (3,3) -> (2,1) -> back, every hop a knight's move.
const vec2 TOUR[4] = vec2[4](vec2(0, 0), vec2(1, 2), vec2(3, 3), vec2(2, 1));

vec2 toScreen(vec2 b) { b -= 1.5; return vec2((b.x - b.y) * SX, (b.x + b.y) * SY + OY); }
vec2 toBoard(vec2 p) { float a = p.x / SX, c = (p.y - OY) / SY; return vec2(0.5 * (a + c), 0.5 * (c - a)) + 1.5; }

// A small chess rook in profile: base, tapered body, collar, and a crown with two notches.
float rookPiece(vec2 rq) {
  float rk = sdBox(rq - vec2(0.0, 0.018), vec2(0.06, 0.018)) - 0.006;
  rk = min(rk, sdTaper(rq, vec2(0.0, 0.03), vec2(0.0, 0.13), 0.046, 0.034));
  rk = min(rk, sdBox(rq - vec2(0.0, 0.138), vec2(0.048, 0.011)) - 0.004);
  float crown = sdBox(rq - vec2(0.0, 0.178), vec2(0.05, 0.03)) - 0.004;
  crown = max(crown, -sdBox(vec2(abs(rq.x) - 0.019, rq.y - 0.2), vec2(0.009, 0.016)));
  return min(rk, crown);
}

vec4 icon(vec2 p, float t, int layer) {
  float hopT = t * 4.0;
  int hop = int(floor(hopT));
  float f = fract(hopT);
  vec2 from = TOUR[hop % 4], to = TOUR[(hop + 1) % 4];
  // The board's top: squares in two tones, the landed square lit and cooling.
  vec2 b = toBoard(p);
  vec4 col = vec4(0.0);
  float inBoard = step(-0.5, b.x) * step(b.x, 3.5) * step(-0.5, b.y) * step(b.y, 3.5);
  vec2 cell = floor(b + 0.5);
  float dark = mod(cell.x + cell.y, 2.0);
  vec2 lb = toBoard(p + vec2(0.0, TH));                  // The slab's sides: the top shape, moved down.
  float inSide = step(-0.5, lb.x) * step(lb.x, 3.5) * step(-0.5, lb.y) * step(lb.y, 3.5) * (1.0 - inBoard);
  if (inSide > 0.5) {
    vec3 side = lb.y < lb.x ? mix(DEEP, VIOLET, 0.45) : INK * 1.8;   // Right front face lit, left front face in shadow.
    col = paint(side, 1.0);
  }
  if (inBoard > 0.5) {
    vec3 sq = dark > 0.5 ? INK * 1.9 : mix(DEEP, VIOLET, 0.75);
    // The square just landed on glows pink, cooling over the hop; the one before it holds a faint violet.
    float glowLand = (1.0 - f) * float(cell == from);
    sq = mix(sq, mix(VIOLET, PINK, glowLand), cel(glowLand, 0.15));
    sq = mix(sq, CORE, cel(glowLand, 0.8));
    // Grid lines between squares.
    vec2 g = 0.5 - abs(fract(b + 0.5) - 0.5);           // 0 on the lines between squares.
    sq = mix(sq, INK, (1.0 - cel(min(g.x, g.y), 0.04)) * 0.6);
    // A lit bevel along each light square's upper-left edge gives the squares a little height.
    vec2 fb = fract(b + 0.5);
    sq = mix(sq, mix(VIOLET, CORE, 0.35), (1.0 - dark) * cel(fb.y, 0.84) * cel(1.0 - fb.y, 0.04) * (1.0 - glowLand));
    col = paint(sq, 1.0);
  }
  // The board's ink outline, top and sides together.
  vec2 corner[4] = vec2[4](toScreen(vec2(-0.5, -0.5)), toScreen(vec2(3.5, -0.5)), toScreen(vec2(3.5, 3.5)), toScreen(vec2(-0.5, 3.5)));
  // Corners: 0 bottom, 1 right, 2 top, 3 left. Only the front faces' edges show: the top's four edges, the front
  // two edges' lower copies, and the three front corners' uprights.
  float outl = 1e9;
  vec2 dn = vec2(0.0, TH);
  for (int k = 0; k < 4; k++) outl = min(outl, sdSeg(p, corner[k], corner[(k + 1) % 4]));
  outl = min(outl, min(sdSeg(p, corner[3] - dn, corner[0] - dn), sdSeg(p, corner[0] - dn, corner[1] - dn)));
  outl = min(outl, min(sdSeg(p, corner[3], corner[3] - dn), min(sdSeg(p, corner[0], corner[0] - dn), sdSeg(p, corner[1], corner[1] - dn))));
  // A cyan rim light along the two back edges of the top.
  float rim = min(sdSeg(p, corner[1], corner[2]), sdSeg(p, corner[2], corner[3]));
  col = over(paint(CYAN, fill(rim - 0.011)), col);
  col = over(paint(INK, fill(outl - 0.009)), col);
  // The landing ring spreads over the board plane.
  vec2 lr = (b - from);
  float ring = abs(length(lr) - (0.2 + 1.3 * f)) - 0.06 * (1.0 - f);
  col = over(paint(mix(CORE, CYAN, f), fill(ring * SY * 1.4) * (1.0 - f) * inBoard), col);
  // A small rook stands on the free corner square, watching the move: the board is Rook's own.
  vec2 rp = toScreen(vec2(3.0, 0.0)) + vec2(0.0, -0.01);
  const float RK = 1.3;
  vec2 rq = (p - rp) / RK;
  float rk = rookPiece(rq) * RK;
  float rkLeft = rookPiece(rq + vec2(0.014, 0.0)) * RK;       // The silhouette moved left: its right rim is the gap.
  vec2 sh2 = (rq - vec2(0.03, 0.0)) / vec2(0.09, 0.03);
  col = over(paint(INK, (1.0 - smoothstep(0.6, 1.0, length(sh2))) * 0.55), col);
  vec3 rkc = rq.x < -0.014 ? mix(VIOLET, CORE, 0.3) : (rq.x < 0.02 ? VIOLET : mix(DEEP, VIOLET, 0.3));
  rkc = mix(rkc, CYAN, (1.0 - fill(rkLeft)) * step(0.0, rq.x));
  col = over(over(paint(rkc, fill(rk)), paint(INK, fill(rk - INKW))), col);
  // The spark: an arc from square to square, rising and falling, with a trail.
  float hopF = smoothstep(0.1, 0.75, f);
  vec2 A = toScreen(from), B = toScreen(to);
  vec2 sp = mix(A, B, hopF) + vec2(0.0, 0.32 * sin(PI * hopF));
  float hopF2 = smoothstep(0.1, 0.75, max(f - 0.06, 0.0));
  vec2 sp2 = mix(A, B, hopF2) + vec2(0.0, 0.32 * sin(PI * hopF2));
  vec2 s = p - sp;
  float tw = 0.11 + 0.04 * sin(PI * hopF);
  float star = max(1.0 - length(s * vec2(1.0, 5.0)) / tw, 1.0 - length(s * vec2(5.0, 1.0)) / tw);
  vec4 spark = over(paint(CORE, smoothstep(0.0, 0.12, star)), streak(p, sp2, sp, 0.03, PINK));
  spark = over(spark, glow(PINK, 0.8 * exp(-pow(length(s) / 0.07, 2.0))));
  // Its shadow on the board, a dark ellipse under it.
  vec2 sh = (p - mix(A, B, hopF)) / vec2(0.08, 0.035);
  col = over(paint(INK, (1.0 - smoothstep(0.7, 1.0, length(sh))) * 0.5 * inBoard * (1.0 - 0.5 * sin(PI * hopF))), col);
  return over(spark, over(col, glow(VIOLET, 0.3 * exp(-pow(length(p - vec2(0.0, OY)) / 0.4, 2.0)))));
}
