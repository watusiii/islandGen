"""The ribbon: one long curved land bridge that spirals upward.

Fundamentals:
  spine    = a curve. A point moving around a circle while climbing (a helix),
             with flat terraces and short ramps instead of a constant slope.
  section  = a 2D slice: flat grass top, grass rim, rocky V hanging underneath.
  ribbon   = place that slice at every spine point, facing along the curve,
             and connect neighbouring slices with triangles (a "loft").
"""
import math
import random
from ..noise import layered_loop_noise

# name: (default, min, max, step, help)
PARAMS = {
    "ribbon":        (1, 0, 1, 1, "1 = build the spiral land bridge, 0 = pads only"),
    "width":         (7.0, 1.0, 30.0, 0.5, "half-width of the bridge, in studs"),
    "width_var":     (0.45, 0.0, 0.9, 0.01, "how much the width swells and pinches"),
    "terraces":      (4, 1, 12, 1, "flat levels the bridge climbs through"),
    "ramp":          (0.35, 0.05, 1.0, 0.01, "share of each level spent ramping up (low = steep steps)"),
    "segments":      (64, 12, 240, 1, "slices along the bridge (low = more low-poly)"),
    "belly":         (1.4, 0.2, 4.0, 0.05, "rock depth under the bridge, as a multiple of width"),
    "wander":        (0.18, 0.0, 0.6, 0.01, "how much the curve drifts in and out"),
}
DEFAULTS = {k: v[0] for k, v in PARAMS.items()}


def make_spine(seed: int, layout: dict, rib: dict):
    """Returns spine(t) -> (x, y, z) for t in [0, 1]. Shared with the pad layout."""
    rng = random.Random(seed * 31 + 5)
    wander = layered_loop_noise(rng, 3, 2)
    steps = max(int(rib["terraces"]), 1)
    ramp = rib["ramp"]

    def height(t):
        k = t * steps
        i = min(int(k), steps - 1)
        frac = k - i
        u = min(max((frac - (1 - ramp)) / ramp, 0.0), 1.0)
        u = u * u * (3 - 2 * u)                  # smoothstep
        return layout["rise"] * (i + u) / steps

    def spine(t):
        a = t * layout["turns"] * math.tau
        r = layout["spiral_radius"] * (1 + rib["wander"] * wander(t * 0.999))
        return (math.cos(a) * r, height(t), math.sin(a) * r)

    return spine


def build_ribbon(seed: int, layout: dict, rib: dict, rim: float, jitter: float) -> dict:
    """Mesh in the same format as mesh.build_mesh: {"vertices", "faces"}."""
    from ..mesh import _normal, _dot
    rng = random.Random(seed * 131 + 9)
    spine = make_spine(seed, layout, rib)
    widthn = layered_loop_noise(rng, 5, 2)
    n = int(rib["segments"])
    W = rib["width"]

    # 1. slice positions along the curve
    pts = [spine(i / n) for i in range(n + 1)]
    verts, faces, sections = [], [], []

    def add(p):
        verts.append(p)
        return len(verts) - 1

    for i, (x, y, z) in enumerate(pts):
        a, b = pts[max(i - 1, 0)], pts[min(i + 1, n)]
        tx, tz = b[0] - a[0], b[2] - a[2]
        l = math.hypot(tx, tz) or 1.0
        nx, nz = -tz / l, tx / l               # sideways direction
        t = i / n
        w = W * (1 + rib["width_var"] * widthn(t))
        end = min(t, 1 - t) * n                # taper the two tips
        if end < 2:
            w *= 0.55 + 0.225 * end
        d = w * rib["belly"]
        j = lambda: 1 + rng.uniform(-1, 1) * jitter
        # 2. the slice, as (sideways offset, height offset), going around
        prof = [
            (-w, 0), (w, 0),                                   # grass top
            (w, -rim), (w * 0.75 * j(), -rim - d * 0.35 * j()),  # right side
            (w * 0.15 * j(), -rim - d * j()),                  # bottom point
            (-w * 0.75 * j(), -rim - d * 0.35 * j()), (-w, -rim),  # left side
        ]
        ring = [add((x + nx * s, y + h, z + nz * s)) for s, h in prof]
        sections.append({"ring": ring, "center": (x, y - rim - d * 0.4, z)})

    MAT = ["grass", "grass", "rock", "rock", "rock", "rock", "grass"]  # per edge

    def tri(i, j, k, mat, ref):
        A, B, C = verts[i], verts[j], verts[k]
        mid = tuple((A[q] + B[q] + C[q]) / 3 for q in range(3))
        out = tuple(mid[q] - ref[q] for q in range(3))
        if _dot(_normal(A, B, C), out) < 0:
            j, k = k, j
        faces.append({"v": (i, j, k), "material": mat})

    # 3. loft: connect each slice to the next
    m = len(sections[0]["ring"])
    for s0, s1 in zip(sections, sections[1:]):
        A, B = s0["ring"], s1["ring"]
        ref = tuple((s0["center"][q] + s1["center"][q]) / 2 for q in range(3))
        for e in range(m):
            e2 = (e + 1) % m
            if e == 0:  # top face: reference is straight below
                ref_top = (verts[A[0]][0], verts[A[0]][1] - 100, verts[A[0]][2])
                tri(A[e], A[e2], B[e], MAT[e], ref_top)
                tri(A[e2], B[e2], B[e], MAT[e], ref_top)
                continue
            tri(A[e], A[e2], B[e], MAT[e], ref)
            tri(A[e2], B[e2], B[e], MAT[e], ref)

    # 4. caps at both ends
    for sec, nb in ((sections[0], sections[1]), (sections[-1], sections[-2])):
        ring = sec["ring"]
        c = tuple(sum(verts[v][q] for v in ring) / m for q in range(3))
        ci = add(c)
        inward = nb["center"]
        for e in range(m):
            tri(ring[e], ring[(e + 1) % m], ci, "rock", inward)

    return {"vertices": verts, "faces": faces}
