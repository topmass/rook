// Thinking: the nova itself. A white-hot star draws in, bursts with long rays and a shockwave, then settles, once a
// loop. The rays turn a quarter turn per loop; with four long and four short rays, that is seamless.

vec4 icon(vec2 p, float t, int layer) {
  // 0 to 0.3: it draws in. At 0.3 it bursts. Then it settles back.
  float burst = t < 0.3 ? 0.0 : exp(-(t - 0.3) * 7.0) * (1.0 - smoothstep(0.8, 1.0, t));
  float draw = t < 0.3 ? smoothstep(0.0, 0.3, t) : 0.0;
  float rc = 0.15 - 0.045 * draw + 0.07 * burst;
  float a = atan(p.y, p.x) - TAU / 4.0 * t, r = length(p);
  // Rays: tapered spikes whose length breathes with the burst.
  // Each ray is a four-sided pyramid seen from the front: the face toward the light is lit, the other in shadow,
  // split along a bright ridge, as an anime star is drawn.
  float rays = 1e9, side = 0.0, along = 0.0;
  vec2 q = rot(TAU / 4.0 * t) * p;
  vec2 Lq = rot(TAU / 4.0 * t) * normalize(vec2(-0.6, 0.8));
  for (int k = 0; k < 8; k++) {
    float ak = TAU * float(k) / 8.0;
    float len = (k % 2 == 0 ? 0.38 : 0.22) * (1.0 - 0.5 * draw) + (k % 2 == 0 ? 0.22 : 0.13) * burst;
    vec2 dir = vec2(cos(ak), sin(ak));
    float d = sdTaper(q, dir * rc * 0.6, dir * (rc + len), 0.055 + 0.03 * burst, 0.0);
    if (d < rays) {
      rays = d;
      vec2 nrm = vec2(-dir.y, dir.x);
      side = sign(dot(q, nrm)) * sign(dot(nrm, Lq) + 1e-3);   // +1 on the face toward the light.
      along = clamp(dot(q, dir) / (rc + len), 0.0, 1.0);
    }
  }
  vec3 lit = mix(PINK, CORE, 0.25 + 0.5 * burst), dark = mix(DEEP, VIOLET, 0.55);
  vec3 rc3 = side > 0.0 ? lit : dark;
  vec4 col = over(paint(mix(rc3, CORE, cel(1.0 - along, 0.78) * 0.6), fill(rays)), paint(INK, fill(rays - INKW) * (1.0 - fill(rays))));
  // The shockwave ring.
  float f = clamp((t - 0.3) / 0.7, 0.0, 1.0);
  float sw = abs(r - (0.2 + 0.68 * pow(f, 0.6))) - 0.03 * (1.0 - f);
  if (t >= 0.3) col = over(paint(mix(CORE, CYAN, f), fill(sw) * (1.0 - f)), col);
  // Inward motes while it draws in.
  for (int k = 0; k < 10; k++) {
    float h = hash1(float(k) + 21.0);
    float ang = TAU * h, life = draw;
    vec2 dir = vec2(cos(ang), sin(ang));
    float s0 = mix(0.85, rc, life), s1 = mix(0.85, rc, max(life - 0.12, 0.0));
    if (t < 0.3) col = over(streak(p, dir * s1, dir * s0, 0.012, CYAN) * smoothstep(0.02, 0.1, t), col);
  }
  vec4 g = glow(PINK, (0.5 + 0.5 * burst) * exp(-pow(max(r - rc, 0.0) / (0.1 + 0.12 * burst), 2.0)));
  return over(orb(p, rc, t, 0.3 + 0.4 * burst), over(col, g));
}
