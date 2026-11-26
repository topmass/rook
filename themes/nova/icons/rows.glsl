// Transcribing: sound becomes words. Voice bars on the left bob in plasma and throw sparks to a writing head, which
// lays down a line of word-shaped strokes; the block scrolls up one line per loop, and lines cool as they age. Every
// line has the same words, so the scroll lands each one exactly where the one above began, and the loop closes.

const float GAP = 0.2;
const float X0 = -0.12, X1 = 0.7;
const float BASE = -0.3;   // The line being written.

// Distance to the words of a line written up to xe.
float words(vec2 p, float y, float xe) {
  float d = 1e9;
  // Words with gaps wider than their rounded caps (0.03 each side), so each word stands apart.
  float starts[4] = float[4](0.0, 0.25, 0.43, 0.7);
  float lens[4] = float[4](0.13, 0.08, 0.17, 0.12);
  for (int k = 0; k < 4; k++) {
    float a = X0 + starts[k], b = min(X0 + starts[k] + lens[k], xe);
    if (b <= a) break;
    d = min(d, sdSeg(p, vec2(a, y), vec2(b, y)) - 0.03);
  }
  return d;
}

vec4 icon(vec2 p, float t, int layer) {
  vec4 col = vec4(0.0);
  float w = smoothstep(0.0, 0.85, t);
  float xe = mix(X0, X1 + 0.02, w);
  for (int j = 0; j < 4; j++) {
    float y = BASE + (float(j) + t) * GAP;
    float show = 1.0 - smoothstep(0.32, 0.46, y);
    float d = words(p, y, j == 0 ? xe : X1 + 0.1);
    float age = (float(j) + t) / 4.0;
    col = over(over(paint(plasma(0.9 - 0.62 * age), fill(d) * show), paint(INK, stroke(d, INKW) * show)), col);
  }
  // The writing head.
  vec2 head = vec2(xe, BASE);
  // The head fades in as a line starts and out as it ends, so it never jumps back across the loop.
  float headA = smoothstep(0.0, 0.05, t) * (1.0 - smoothstep(0.8, 0.86, t));
  {
    vec2 s = p - head;
    float star = max(1.0 - length(s * vec2(1.0, 5.0)) / 0.1, 1.0 - length(s * vec2(5.0, 1.0)) / 0.1);
    col = over(over(paint(CORE, smoothstep(0.0, 0.12, star)), glow(PINK, 0.8 * exp(-pow(length(s) / 0.06, 2.0)))) * headA, col);
  }
  // The voice: seven bars that bob on whole beats per loop.
  float bd = 1e9, bh = 0.0;
  for (int i = 0; i < 7; i++) {
    float x = -0.72 + float(i) * 0.075;
    float env = sin(PI * (float(i) + 0.5) / 7.0);
    float h = 0.05 + 0.2 * env * (0.5 + 0.5 * sin(TAU * (t * float(1 + i % 3) + hash1(float(i) + 3.0))));
    float d = sdSeg(p, vec2(x, -h), vec2(x, h)) - 0.024;
    if (d < bd) { bd = d; bh = h; }
  }
  col = over(over(paint(mix(VIOLET, CYAN, cel(bh, 0.15)), fill(bd)), paint(INK, fill(bd - INKW))), col);
  // Sparks fly from the bars to the head, three lives per loop each.
  for (int i = 0; i < 5; i++) {
    float life = fract(t * 3.0 + float(i) / 5.0);
    vec2 a = vec2(-0.3, 0.12 * sin(float(i) * 2.3));
    vec2 b = head;
    vec2 pt = mix(a, b, life) + vec2(0.0, 0.12 * sin(PI * life));
    vec2 pt2 = mix(a, b, max(life - 0.1, 0.0)) + vec2(0.0, 0.12 * sin(PI * max(life - 0.1, 0.0)));
    col = over(streak(p, pt2, pt, 0.014 * (1.0 - life * 0.6), CYAN) * (1.0 - smoothstep(0.85, 1.0, life)) * headA, col);
  }
  return over(col, glow(VIOLET, 0.25 * exp(-pow(length(p * vec2(0.75, 1.4)) / 0.36, 2.0))));
}
