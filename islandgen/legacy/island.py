"""One floating island, as plain data.

Picture it as a stack of rings (closed loops of points):
  ring 0      = the flat grass top
  ring 1      = bottom of the grass rim (a short vertical wall)
  ring 2..n   = rocky body, shrinking and wobbling as it goes down
  tip         = one point at the very bottom

Faces connect each ring to the next. That's the whole mesh.
"""
import math
import random

# name: (default, min, max, step, help)  -- the GUI builds its sliders from this
PARAMS = {
    "radius":       (20.0, 4.0, 60.0, 0.5, "size of the top, in studs"),
    "points":       (18, 5, 48, 1, "points around the outline (low = more low-poly)"),
    "wobble":       (0.28, 0.0, 0.8, 0.01, "how blobby the top outline is (0 = circle)"),
    "wobble_knots": (4, 1, 12, 1, "number of big bumps around the edge"),
    "rim":          (2.0, 0.2, 8.0, 0.1, "thickness of the grass layer"),
    "depth":        (0.8, 0.2, 2.5, 0.05, "body depth as a multiple of radius"),
    "layers":       (4, 1, 10, 1, "rings in the rocky body"),
    "taper":        (2.2, 0.3, 5.0, 0.05, "higher = fatter body, lower = pointier cone"),
    "jitter":       (0.12, 0.0, 0.5, 0.01, "per-point randomness on body rings"),
    "drift":        (0.15, 0.0, 0.6, 0.01, "how much the tip wanders off-center"),
}
DEFAULTS = {k: v[0] for k, v in PARAMS.items()}


def generate_island(seed: int = 1, **overrides) -> dict:
    s = {**DEFAULTS, **overrides}
    rng = random.Random(seed)
    from ..noise import layered_loop_noise

    n = int(s["points"])
    R = s["radius"]
    edge = layered_loop_noise(rng, int(s["wobble_knots"]), 2)

    # 1. Top outline: a circle with each point pushed in/out by noise.
    outline = []
    for i in range(n):
        t = i / n
        a = t * math.tau
        r = R * (1 + s["wobble"] * edge(t))
        outline.append((math.cos(a) * r, math.sin(a) * r))

    rings = []
    rings.append({"y": 0.0, "points": outline, "role": "top"})
    rings.append({"y": -s["rim"], "points": outline, "role": "rim"})

    # 2. Rocky body: shrink the outline step by step going down.
    depth = R * s["depth"]
    drift_x = rng.uniform(-1, 1) * R * s["drift"]
    drift_z = rng.uniform(-1, 1) * R * s["drift"]
    L = int(s["layers"])
    for k in range(1, L + 1):
        f = k / (L + 1)                      # 0 -> 1 going down
        scale = (1 - f) ** (1 / max(s["taper"], 0.05))
        y = -s["rim"] - depth * f
        pts = []
        for (x, z) in outline:
            j = 1 + rng.uniform(-1, 1) * s["jitter"]
            pts.append((x * scale * j + drift_x * f, z * scale * j + drift_z * f))
        rings.append({"y": y, "points": pts, "role": "body"})

    tip = (drift_x, -s["rim"] - depth, drift_z)

    return {
        "seed": seed,
        "settings": s,
        "rings": rings,
        "tip": tip,
        "top_outline": outline,
        "top_y": 0.0,
        "bottom_y": tip[1],
    }
