// Thinking: a crystal lattice. Nova's take on Devs' cube: an inked crystal cube with tinted faces turns a quarter turn per loop round
// an octahedron turning the other way, with a hot core between them.

vec3 spinPt(vec3 v, float ay, float ax) {
  v.xz = rot(ay) * v.xz;
  v.yz = rot(ax) * v.yz;
  return v;
}

// Draws one pass of edges: only edges whose mid depth is on the asked side (front > 0.5 means z > 0). Ink first,
// then plasma, so crossing edges look the same whatever order they come in; the loop needs that.
vec4 edges(vec2 p, float t, float front, vec4 col) {
  float ay = TAU / 4.0 * t + 0.55, ax = -0.5;
  float de = 1e9, dn = 1e9;
  for (int i = 0; i < 12; i++) {
    // Cube edges: pick the axis the edge runs along, and the signs of the other two.
    int axis = i / 4, k = i % 4;
    vec3 a = vec3(-1.0), b = vec3(1.0);
    float s1 = (k & 1) == 0 ? -1.0 : 1.0, s2 = (k & 2) == 0 ? -1.0 : 1.0;
    if (axis == 0) { a = vec3(-1, s1, s2); b = vec3(1, s1, s2); }
    if (axis == 1) { a = vec3(s1, -1, s2); b = vec3(s1, 1, s2); }
    if (axis == 2) { a = vec3(s1, s2, -1); b = vec3(s1, s2, 1); }
    vec3 A = spinPt(a * 0.42, ay, ax), B = spinPt(b * 0.42, ay, ax);
    if ((A.z + B.z > 0.0) != (front > 0.5)) continue;
    de = min(de, sdSeg(p, A.xy, B.xy));
    dn = min(dn, min(length(p - A.xy), length(p - B.xy)));
  }
  float h = front > 0.5 ? 0.75 : 0.35;
  col = over(paint(INK, fill(de - 0.038)), col);
  col = over(paint(plasma(h + 0.2 * snap(t, 2.0, 6.0)), fill(de - 0.022)), col);
  return over(paint(front > 0.5 ? CORE : VIOLET, fill(dn - 0.04)), col);
}

// The cube's front faces as tinted crystal: each face lit in cel bands by its turn toward the light, with a hard
// glint band across it. Back faces are left clear, so the gem inside shows through.
vec4 faces(vec2 p, float t) {
  float ay = TAU / 4.0 * t + 0.55, ax = -0.5;
  vec3 L = normalize(vec3(-0.6, 0.6, 0.55));
  vec4 col = vec4(0.0);
  for (int f = 0; f < 6; f++) {
    int axis = f / 2;
    float sg = (f & 1) == 0 ? -1.0 : 1.0;
    vec3 nrm = vec3(0.0); nrm[axis] = sg;
    vec3 n = spinPt(nrm, ay, ax);
    if (n.z <= 0.0) continue;
    // The face's corners: walk the other two axes round the square.
    int u = (axis + 1) % 3, v = (axis + 2) % 3;
    vec2 q[4];
    for (int k = 0; k < 4; k++) {
      vec3 c = nrm;
      c[u] = (k == 0 || k == 3) ? -1.0 : 1.0;
      c[v] = (k < 2) ? -1.0 : 1.0;
      q[k] = spinPt(c * 0.42, ay, ax).xy;
    }
    // Inside a convex quad: the same side of all four edges.
    float sgn = 0.0; bool inside = true;
    for (int k = 0; k < 4; k++) {
      vec2 a = q[k], b = q[(k + 1) % 4];
      float cr = (b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x);
      if (sgn == 0.0) sgn = sign(cr); else if (sign(cr) != sgn) inside = false;
    }
    if (!inside) continue;
    float lit = dot(n, L) * 0.5 + 0.5;
    vec3 c = mix(DEEP, VIOLET, cel(lit, 0.55));
    // A glint band runs diagonally across the face that faces the light most.
    vec2 g = p - 0.5 * (q[0] + q[2]);
    float glint = cel(lit, 0.75) * (1.0 - cel(abs(g.x + g.y * 0.8 - 0.05), 0.035));
    col = over(paint(mix(c, CORE, glint), 0.28 + 0.5 * glint), col);
  }
  return col;
}

vec4 icon(vec2 p, float t, int layer) {
  vec4 col = glow(VIOLET, 0.4 * exp(-pow(length(p) / 0.36, 2.0)));
  col = edges(p, t, 0.0, col);
  // The octahedron inside, counter-turning, drawn thin in cyan.
  float ay = -TAU / 4.0 * t, ax = 0.4;
  vec3 V[6] = vec3[6](vec3(1, 0, 0), vec3(-1, 0, 0), vec3(0, 1, 0), vec3(0, -1, 0), vec3(0, 0, 1), vec3(0, 0, -1));
  float dOct = 1e9;
  for (int i = 0; i < 6; i++) for (int j = i + 1; j < 6; j++) {
    if (dot(V[i], V[j]) < -0.5) continue;
    dOct = min(dOct, sdSeg(p, spinPt(V[i] * 0.28, ay, ax).xy, spinPt(V[j] * 0.28, ay, ax).xy));
  }
  col = over(paint(CYAN, fill(dOct - 0.012)), over(paint(INK, fill(dOct - 0.022)), col));
  col = over(orb(p, 0.085 + 0.015 * snap(t, 2.0, 6.0), t, 0.3), col);
  col = over(faces(p, t), col);
  return edges(p, t, 1.0, col);
}
