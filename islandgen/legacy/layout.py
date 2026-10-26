"""Where islands go. Pure data: positions and sizes, no meshes."""
import math
import random

# name: (default, min, max, step, help)
PARAMS = {
    "count":         (10, 1, 40, 1, "number of islands"),
    "turns":         (1.75, 0.0, 5.0, 0.05, "how many times the spiral wraps around"),
    "spiral_radius": (34.0, 0.0, 150.0, 1.0, "distance from the center axis"),
    "rise":          (80.0, 0.0, 300.0, 1.0, "total height from lowest to highest island"),
    "size_min":      (0.35, 0.1, 2.0, 0.05, "smallest island, as a multiple of radius"),
    "size_max":      (0.8, 0.1, 3.0, 0.05, "biggest island, as a multiple of radius"),
    "scatter":       (0.25, 0.0, 1.0, 0.01, "randomness of position along the spiral"),
    "spacing":       (1.05, 0.5, 2.0, 0.05, "how hard islands push apart (1 = just touching)"),
}
DEFAULTS = {k: v[0] for k, v in PARAMS.items()}


def generate_layout(seed: int, base_radius: float, spine=None, ribbon_width=0.0, **overrides) -> list:
    """Returns [{"seed", "position": [x,y,z], "radius"}], bottom to top.

    With a spine (the ribbon's curve), pads hug the bridge edges instead.
    """
    s = {**DEFAULTS, **overrides}
    rng = random.Random(seed * 7919 + 1)
    n = int(s["count"])
    out = []
    if spine is not None:
        for i in range(n):
            t = (i + 0.5) / n + rng.uniform(-0.5, 0.5) * s["scatter"] / n
            t = min(max(t, 0.01), 0.99)
            x, y, z = spine(t)
            a2, b2 = spine(max(t - 0.01, 0)), spine(min(t + 0.01, 1))
            tx, tz = b2[0] - a2[0], b2[2] - a2[2]
            l = math.hypot(tx, tz) or 1.0
            side = rng.choice((-1, 1))
            size = rng.uniform(s["size_min"], max(s["size_min"], s["size_max"]))
            r = base_radius * size
            off = side * (ribbon_width + r * 0.55)
            out.append({
                "seed": rng.randrange(1, 10**9),
                "position": [x - tz / l * off, y - rng.uniform(0.0, 3.0), z + tx / l * off],
                "radius": r,
            })
        return out
    for i in range(n):
        f = i / max(n - 1, 1)
        a = f * s["turns"] * math.tau + rng.uniform(-1, 1) * s["scatter"] * 0.8
        d = s["spiral_radius"] * (1 + rng.uniform(-1, 1) * s["scatter"])
        y = f * s["rise"] + rng.uniform(-1, 1) * s["scatter"] * s["rise"] / max(n, 1)
        size = rng.uniform(s["size_min"], max(s["size_min"], s["size_max"]))
        out.append({
            "seed": rng.randrange(1, 10**9),
            "position": [math.cos(a) * d, y, math.sin(a) * d],
            "radius": base_radius * size,
        })
    if n == 1:
        out[0]["position"] = [0.0, 0.0, 0.0]

    # push apart islands that overlap (only sideways, keep heights)
    for _ in range(40):
        moved = False
        for i in range(n):
            for j in range(i + 1, n):
                A, B = out[i], out[j]
                dy = abs(A["position"][1] - B["position"][1])
                if dy > (A["radius"] + B["radius"]) * 0.6:
                    continue  # far enough apart vertically
                dx = B["position"][0] - A["position"][0]
                dz = B["position"][2] - A["position"][2]
                dist = math.hypot(dx, dz) or 0.01
                want = (A["radius"] + B["radius"]) * s["spacing"]
                if dist < want:
                    push = (want - dist) / 2 / dist
                    A["position"][0] -= dx * push; A["position"][2] -= dz * push
                    B["position"][0] += dx * push; B["position"][2] += dz * push
                    moved = True
        if not moved:
            break
    return out
