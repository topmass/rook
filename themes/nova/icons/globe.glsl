// Searching the web: Nova's globe, after the Devs globe the owner loves. A dark glass sphere with inked plasma latitude and
// longitude lines turns slowly; the far side's lines show faintly through it. A scan line sweeps the meridians, a
// dashed ring turns round it, and a spark orbits it. It turns one meridian gap (30 degrees) per loop, so it loops.

const float R = 0.47;
const float TILT = 0.38;

// Distance, in degrees of arc turned to icon units, from a surface normal to the nearest grid line.
// Returns (nearest line distance, 1 if that line is the equator).
vec2 grid(vec3 n, float spin) {
  n.yz = rot(TILT) * n.yz;
  n.xz = rot(spin) * n.xz;
  float lat = asin(clamp(n.y, -1.0, 1.0)), lon = atan(n.z, n.x);
  float step_ = PI / 6.0;
  float dLat = abs(lat - (floor(lat / step_ + 0.5)) * step_);
  float dLon = abs(lon - (floor(lon / step_ + 0.5)) * step_) * cos(lat);
  float eq = step(abs(lat), step_ * 0.5);
  return vec2(min(dLat, dLon) * R, eq * step(dLat, dLon));
}

vec4 icon(vec2 p, float t, int layer) {
  float r = length(p);
  float spin = TAU / 12.0 * t + 0.2;
  float inside = fill(r - R);
  vec3 nF = vec3(p / R, sqrt(max(0.0, 1.0 - dot(p, p) / (R * R))));
  vec3 nB = vec3(nF.xy, -nF.z);
  vec2 gF = grid(nF, spin), gB = grid(nB, spin);
  float w = 0.011;
  // The glass body: cel-lit, dark at the terminator, with a cyan rim and a hard highlight.
  float diff = dot(nF, normalize(vec3(-0.6, 0.55, 0.6))) * 0.5 + 0.5;
  float fres = 1.0 - nF.z;
  vec3 body = mix(INK * 1.6, DEEP, cel(diff, 0.45));
  body = mix(body, mix(DEEP, VIOLET, 0.5), cel(diff, 0.7));
  body = mix(body, CYAN, cel(fres, 0.8) * (1.0 - cel(diff, 0.5)) * 0.9);
  // Far-side lines through the glass, dim; then the near lines in plasma, the equator in pink.
  body = mix(body, mix(body, VIOLET, 0.55), fill(gB.x - w * 0.8));
  vec3 lineC = mix(mix(VIOLET, PINK, 0.35), PINK, gF.y);
  lineC = mix(lineC, CORE, cel(diff, 0.82) * 0.7);
  body = mix(body, INK, fill(gF.x - w - 0.007));
  body = mix(body, lineC, fill(gF.x - w));
  float hl = 1.0 - cel(length(nF.xy - vec2(-0.42, 0.45)), 0.16);
  body = mix(body, CORE, hl * 0.9);
  vec4 c = paint(body, inside);
  c = over(c, paint(INK, stroke(r - R, 0.014)));
  // Searching: a scan line sweeps down across the meridians once a loop, lighting them as it passes.
  float scanY = mix(R * 0.95, -R * 0.95, t);
  float scan = exp(-pow((p.y - scanY) / 0.03, 2.0)) * sin(PI * t) * inside;
  c = over(paint(mix(CYAN, CORE, 0.4), scan * 0.55 * fill(gF.x - w * 1.4)), c);
  c = over(paint(CYAN, scan * 0.22), c);
  // A dashed ring turns round it: twelve dashes, one dash a loop, so the loop closes.
  float ra = atan(p.y, p.x) - TAU / 12.0 * t;
  float dash = cel(cos(ra * 12.0), 0.1);
  float ringD = abs(r - R - 0.075) - 0.011;
  vec4 ringC = over(paint(mix(VIOLET, CYAN, 0.55), fill(ringD) * dash), paint(INK, stroke(ringD, INKW * 0.7) * dash * 0.8));
  // A spark orbits on a tilted path, in front of the globe on the near half and behind it on the far half.
  float oa = TAU * t;
  vec2 o = rot(-0.45) * vec2(cos(oa) * (R + 0.13), sin(oa) * 0.18);
  vec2 o2 = rot(-0.45) * vec2(cos(oa - 0.35) * (R + 0.13), sin(oa - 0.35) * 0.18);
  vec4 spark = over(streak(p, o2, o, 0.022, PINK), glow(PINK, 0.6 * exp(-pow(length(p - o) / 0.05, 2.0))));
  vec4 g = glow(VIOLET, 0.45 * exp(-pow(max(r - R, 0.0) / 0.07, 2.0)));
  if (sin(oa) < 0.0) return over(spark, over(ringC, over(c, g)));
  return over(ringC, over(c, over(spark, g)));
}
