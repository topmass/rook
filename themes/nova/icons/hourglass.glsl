// A timer: an hourglass of curved glass in a violet frame, running amber plasma, Nova's one warm colour for time.
// The sand drops onto the neck, runs for most of the loop, then the glass flips with a snap. Shapes are
// point-symmetric and all light is worked out in screen space, so the flipped glass is exactly the first frame.

const float H = 0.5;     // Half the glass's height.

float bulbW(float y) {
  float a = clamp(abs(y) / H, 0.0, 1.0);
  return 0.035 + 0.3 * smoothstep(0.0, 0.7, a) * (1.0 - 0.22 * smoothstep(0.72, 1.0, a));
}
float sdRoundBox(vec2 p, vec2 b, float r) { return sdBox(p, b - r) - r; }
// The frame in local coordinates: two caps and two posts.
float frameSDF(vec2 q) {
  float caps = min(sdRoundBox(q - vec2(0.0, H + 0.05), vec2(0.4, 0.045), 0.03),
                   sdRoundBox(q + vec2(0.0, H + 0.05), vec2(0.4, 0.045), 0.03));
  float posts = sdRoundBox(vec2(abs(q.x) - 0.36, q.y), vec2(0.022, H + 0.02), 0.02);
  return min(caps, posts);
}

vec4 icon(vec2 p, float t, int layer) {
  float flip = smoothstep(0.82, 1.0, t);
  float ang = PI * (flip * flip * (3.0 - 2.0 * flip));
  vec2 q = rot(-ang) * p;
  float drop = smoothstep(0.0, 0.06, t);
  float s = clamp((t - 0.06) / 0.74, 0.0, 1.0);
  float hw = bulbW(q.y);
  float glass = max(abs(q.x) - hw, abs(q.y) - H);
  float inside = max(abs(q.x) - (hw - 0.025), abs(q.y) - (H - 0.02));
  // Sand: the top heap drops onto the neck, then sinks; the bottom heap rises with a mound that settles flat.
  float floorY = mix(H * 0.15, 0.0, drop);
  float topY = floorY + H * 0.85 * sqrt(1.0 - s);
  float botY = -H + H * 0.85 * (1.0 - sqrt(1.0 - s));
  float sandTop = max(inside, max(q.y - topY, floorY - q.y));
  float mound = q.y - (botY + 0.06 * sin(PI * s) * (1.0 - abs(q.x) / 0.3));
  float sandBot = max(inside, max(mound, -q.y - H));
  float stream = max(abs(q.x) - 0.012, max(q.y, botY - q.y)) + (drop < 1.0 ? 1.0 : 0.0);
  float sand = min(min(sandTop, sandBot), s < 1.0 ? stream : 1e9);
  float grain = pnoise(vec3(p * 14.0, t * 4.0), vec3(64.0, 64.0, 4.0));
  // Rose-gold shadow, so the sand's one warm colour sits with the violet instead of clashing with it.
  vec3 sc = mix(mix(AMBER, PINK, 0.4) * 0.82, AMBER, cel(0.5 - p.x * 1.4 + 0.12 * grain, 0.42));
  sc = mix(sc, mix(AMBER, CORE, 0.7), cel(grain * 0.6 - p.x * 0.8, 0.42));
  // Behind the glass: a faint violet fill, then the sand.
  vec4 col = paint(mix(DEEP, VIOLET, 0.25), fill(inside) * 0.3);
  col = over(paint(sc, fill(sand)), col);
  // The glass: a curved cyan glint on the screen-left of each bulb, an ink outline.
  float glint = abs(abs(q.x) - (hw - 0.06)) - 0.012;
  col = over(paint(CYAN, fill(glint) * step(p.x, 0.0) * step(0.12, abs(q.y)) * step(abs(q.y), H - 0.08) * 0.85), col);
  col = over(paint(INK, stroke(glass, INKW)), col);
  // The frame: violet with a bevel lit from the screen's upper left.
  float fd = frameSDF(q);
  vec2 e = vec2(0.004, 0.0);
  vec2 gq = vec2(frameSDF(q + e.xy) - frameSDF(q - e.xy), frameSDF(q + e.yx) - frameSDF(q - e.yx));
  vec2 n = rot(ang) * normalize(gq + 1e-6);          // The frame's edge normal, turned to screen space.
  float bevel = 1.0 - cel(-fd, 0.018);                 // The rim band just inside the edge.
  float lit = dot(n, normalize(vec2(-0.6, 0.8)));
  vec3 fc = mix(DEEP, VIOLET, 0.35);
  fc = mix(fc, mix(VIOLET, CORE, cel(lit, 0.7) * 0.6), bevel * cel(lit, 0.1));
  fc = mix(fc, INK * 1.6, bevel * (1.0 - cel(lit, -0.3)));
  col = over(over(paint(fc, fill(fd)), paint(INK, stroke(fd, INKW))), col);
  vec4 g = glow(AMBER, 0.3 * exp(-pow(length(p * vec2(1.3, 0.9)) / 0.4, 2.0)));
  return over(col, g);
}
