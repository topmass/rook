// Writing: a fountain pen of plasma writes a looping line. Its nib circles as cursive loops leave it, and the paper
// carries the line away to the left, hot at the nib and cooling as it goes. Nova's version of the Devs pen. The line
// moves two loops a cycle and is the same shape at every loop, so the loop closes. Made through the forge.

const vec2 NIB = vec2(-0.02, -0.2);
const float STEP = 0.155, LOOPR = 0.092;   // Loop spacing and loop radius of the cursive line.

// The cursive line in paper coordinates: a prolate cycloid, which draws loops like a run of "l".
vec2 script(float u) { return vec2(STEP * u - LOOPR * sin(TAU * u), LOOPR * cos(TAU * u)); }

vec4 icon(vec2 p, float t, int layer) {
  float uh = 2.0 * t;                                   // The nib's place on the line.
  vec2 head = script(uh);
  vec2 off = NIB - vec2(STEP * uh, 0.0);               // The paper moves so the nib's average place stays put.
  vec2 nib = head + off;
  // The written line, from the nib back four loops, cooling and fading with distance.
  float best = 1e9, age = 1.0;
  vec2 prev = nib;
  for (int i = 1; i <= 90; i++) {
    float u = uh - float(i) * 0.045;
    vec2 cur = script(u) + off;
    float d = sdSeg(p, prev, cur);
    if (d < best) { best = d; age = float(i) / 90.0; }
    prev = cur;
  }
  float w = 0.026 * (1.0 - 0.45 * age);
  float fade = 1.0 - smoothstep(0.55, 1.0, age);
  float dl = best - w;
  vec4 line = over(paint(plasma(0.95 - 0.7 * age), fill(dl) * fade), paint(INK, stroke(dl, INKW * 0.8) * fade));
  line = over(line, glow(PINK, 0.4 * fade * exp(-pow(max(dl, 0.0) / 0.04, 2.0))));
  // The pen: from the nib up to the right, with a slight sway as it writes.
  float ang = radians(52.0) + 0.06 * sin(TAU * uh);
  vec2 dir = vec2(cos(ang), sin(ang)), nrm = vec2(-dir.y, dir.x);
  vec2 q = p - nib;
  float along = dot(q, dir), across = dot(q, nrm);
  // Nib (metal): a pointed blade from the tip to the grip, with its slit and breather hole.
  float nibD = sdTaper(q, vec2(0.0), dir * 0.24, 0.005, 0.066);
  float slit = max(abs(across) - 0.005, max(along - 0.16, 0.012 - along));
  float hole = length(q - dir * 0.16) - 0.015;
  // Grip, barrel and cap band, a turned cylinder.
  float grip = sdTaper(q, dir * 0.23, dir * 0.38, 0.066, 0.082);
  float barrel = sdTaper(q, dir * 0.37, dir * 0.9, 0.088, 0.078);
  float band = max(abs(along - 0.56) - 0.028, abs(across) - 0.092);
  float body = min(grip, barrel);
  // Cylinder light across the barrel: lit along one side, a hard highlight stripe, a cyan rim on the shadow side.
  float cx = clamp(across / 0.088, -1.0, 1.0);
  float lit = 0.5 + 0.5 * dot(normalize(vec2(cx, sqrt(max(0.0, 1.0 - cx * cx)))), normalize(vec2(0.6, 0.8)));
  vec3 bc = mix(INK * 1.7, DEEP, cel(lit, 0.35));
  bc = mix(bc, VIOLET, cel(lit, 0.62));
  bc = mix(bc, mix(VIOLET, CORE, 0.6), cel(lit, 0.9));
  bc = mix(bc, CYAN, cel(-cx, 0.8) * 0.85);
  vec3 gc = mix(bc, mix(INK * 1.7, DEEP, 0.6), 0.55);            // The grip is darker.
  vec4 pen = paint(along < 0.37 ? gc : bc, fill(body));
  pen = over(paint(mix(PINK, CORE, cel(lit, 0.6) * 0.6), fill(band) * fill(barrel)), pen);
  vec3 metal = mix(mix(VIOLET, CORE, 0.35), CORE, cel(0.5 + 0.5 * cx, 0.6));
  vec4 nibC = over(paint(INK, max(fill(slit), fill(hole)) * fill(nibD)), paint(metal, fill(nibD)));
  pen = over(nibC, pen);
  float outline = min(body, nibD);
  pen = over(paint(INK, stroke(outline, INKW)), pen);
  // A drop of light where the nib meets the paper.
  vec4 drop = glow(CORE, 0.8 * exp(-pow(length(p - nib) / 0.045, 2.0)));
  vec4 halo = glow(VIOLET, 0.35 * exp(-pow(length(p - vec2(0.0, 0.02)) / 0.36, 2.0)));
  return over(pen, over(drop, over(line, halo)));
}
