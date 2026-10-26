"""Metaball land, top-down. The main system.

Fundamentals:
  ball      = a 2D circle seen from above (x, z, radius) that also carries a height.
  field     = add every ball's field together on a flat grid. Close balls melt together.
  silhouette= wherever the total is over THRESHOLD is land. That's the top-down outline.
  height    = at each spot, the ball contributing the most decides the top height.
              Neighbouring balls with different heights -> a step you jump up.
  slab      = the top is dead flat; the rock underneath hangs deeper where the field
              is stronger (middle of the land) and thins out at the edges.

  rings     = balls are laid along irregular, broken rings around a center.
              Where rings wobble close together, they merge into natural bridges.

The balls are the engine-agnostic data. The mesh is just one way to use them.
"""
import math
import random
import time

import numpy as np

from .noise import layered_loop_noise

THRESHOLD = 0.5
# A lone ball's visible edge sits at this fraction of its field radius
VIS = math.sqrt(1 - THRESHOLD ** (1 / 3))

# ALL DISTANCES ARE METERS, Y UP (same as glTF). Exporters convert per engine.
# name: (default, min, max, step, help)
PARAMS = {
    "tower": {
        "layout":      (1, 0, 1, 1, "0 = rings, 1 = tower: pads winding up a helix, joined by ribbons, stairs and hops"),
        "pads":        (9, 2, 30, 1, "tower: how many pads (incl. the round base)"),
        "turns":       (1.75, 0.25, 4.0, 0.05, "tower: how many times the climb goes round"),
        "radius":      (7.0, 1.0, 40.0, 0.25, "tower: how far pads sit from the centre at the bottom (m)"),
        "taper":       (0.35, 0.0, 0.9, 0.01, "tower: how much tighter it winds at the top"),
        "climb":       (20.0, 2.0, 150.0, 0.5, "tower: height from the base to the top pad (m)"),
        "pad_size":    (2.1, 0.8, 10.0, 0.05, "tower: pad radius (m)"),
        "base_r":      (1.6, 0.5, 10.0, 0.05, "tower: radius of the round base pad (m)"),
        "paths":       (0.75, 0.0, 1.0, 0.01, "tower: chance two pads get a path (ramp / stairs); else hop stones"),
        "ribbon":      (1.5, 0.6, 5.0, 0.05, "tower: path width (m)"),
        "ramp_slope":  (0.45, 0.05, 1.0, 0.01, "tower: paths steeper than this become stone stairs"),
        "stair_rise":  (0.3, 0.1, 1.0, 0.01, "tower: height of one stair step (m)"),
        "slab":        (0.6, 0.15, 3.0, 0.05, "tower: pad edge thickness before the rock belly starts (m)"),
        "tower_belly": (0.6, 0.0, 3.0, 0.05, "tower: how deep the rock hangs under pads (x pad size)"),
    },
    "rings": {
        "rings":       (11, 1, 14, 1, "number of rings"),
        "first":       (3.9, 0.0, 25.0, 0.1, "radius of the innermost ring (m)"),
        "gap":         (4.2, 1.5, 25.0, 0.1, "distance between rings (m)"),
        "wobble":      (0.6, 0.0, 1.0, 0.01, "how irregular each ring is"),
        "completion":  (0.34, 0.1, 1.0, 0.01, "how much of each ring exists"),
        "pieces":      (3, 1, 6, 1, "how many pieces each ring breaks into"),
        "drift":       (0.08, 0.0, 1.0, 0.01, "rings slide off-center"),
        "shuffle":     (1.0, 0.0, 1.0, 0.01, "break the small-to-big order: rings swap, cross and overlap"),
    },
    "balls": {
        "size":        (1.8, 0.5, 9.0, 0.05, "ball radius = land half-width (m)"),
        "size_var":    (0.77, 0.0, 0.9, 0.01, "random ball sizes"),
        "beads":       (0.75, 0.3, 2.0, 0.05, "spacing between balls (high = beady / gaps)"),
        "blobs":       (0.32, 0.0, 1.0, 0.01, "chance of a fat ball bulging off a ring"),
    },
    "height": {
        "tier":        (11.5, -20.0, 20.0, 0.1, "steady height change per ring (m, + = inner rings higher)"),
        "lift":        (0.0, 0.0, 90.0, 0.5, "random height per ring, +/- m"),
        "piece_lift":  (0.6, 0.0, 45.0, 0.1, "random height per broken piece, +/- m"),
        "step":        (2.4, 0.0, 6.0, 0.05, "terrace step height (m); all heights snap to it"),
        "terrace":     (32.0, 1.5, 45.0, 0.5, "length of a terrace along the ring (m)"),
        "thickness":   (1.8, 0.15, 5.0, 0.05, "slab thickness at the edges (m)"),
        "belly":       (0.4, 0.0, 6.0, 0.05, "how deep the rock hangs in the middle (x ball size)"),
        "voxel":       (1.25, 0.25, 2.0, 0.05, "grid cell size (m). bigger = faster + chunkier"),
        "spiral":      (0.0, -40.0, 40.0, 0.5, "height gained per full turn around the centre (m): a climbing spiral"),
    },
    "look": {
        "mesher":      (1, 0, 1, 1, "1 = clean low-poly pads (flat tops, faceted rock), 0 = marching cubes"),
        "facet":       (0.6, 0.05, 3.0, 0.05, "how chunky pad outlines are (m): bigger = fewer, longer edges"),
        "lip":         (0.25, 0.0, 1.0, 0.05, "top-coloured band down the pad edge (m)"),
        "belly_rings": (3, 1, 6, 1, "rock facets under each pad"),
    },
    "player": {
        "player_height": (1.4, 0.5, 3.0, 0.05, "character height (m). Roblox default ~1.4"),
        "jump":          (2.0, 0.2, 10.0, 0.05, "jump height (m). Roblox default ~2.0. steps above this get flagged"),
        "resolve":       (1, 0, 1, 1, "1 = re-solve heights so every touching step is jumpable (layout from above stays the same)"),
        "reach":         (4.0, 0.5, 15.0, 0.1, "how far the player can jump across a gap (m). Roblox default ~4.5"),
    },
    "filler": {
        "filler":        (1, 0, 1, 1, "1 = add stepping stones so every piece can be reached"),
        "stone":         (0.9, 0.3, 4.0, 0.05, "stepping stone radius (m)"),
        "stone_gap":     (0.7, 0.2, 1.0, 0.01, "how much of a full jump each stone hop uses (lower = easier)"),
    },
}
FLAT = {k: v for g in PARAMS.values() for k, v in g.items()}

# Settings each layout actually reads (the GUI shows only these).
TOWER_KEYS = set(PARAMS["tower"]) | {"size_var", "stone", "facet", "lip", "belly_rings",
                                     "jump", "reach", "player_height", "voxel"}
RINGS_KEYS = (set(FLAT) - set(PARAMS["tower"])) | {"layout"}
USED_BY = {"1": sorted(TOWER_KEYS), "0": sorted(RINGS_KEYS)}
DEFAULTS = {k: v[0] for k, v in FLAT.items()}


# ---------------------------------------------------------------- 1. place balls
def generate_balls(seed: int, s: dict) -> dict:
    rng = random.Random(seed)
    balls, rings = [], []
    n_rings = int(s["rings"])
    for k in range(n_rings):
        R = max(0.0, s["first"] + k * s["gap"] + rng.uniform(-1, 1) * s["gap"] * 1.5 * s["shuffle"])
        wob = layered_loop_noise(rng, 3, 2)
        cx = rng.uniform(-1, 1) * s["drift"] * s["gap"] * 0.5
        cz = rng.uniform(-1, 1) * s["drift"] * s["gap"] * 0.5
        base = (n_rings - 1 - k) * s["tier"] + rng.uniform(-1, 1) * s["lift"]

        # which parts of the ring exist: `pieces` arcs covering `completion`
        pieces = int(s["pieces"])
        total = s["completion"] * math.tau
        weights = [rng.uniform(0.5, 1.5) for _ in range(pieces)]
        gap_total = math.tau - total
        start = rng.uniform(0, math.tau)
        if s["spiral"] and k > 0:
            start = prev_end + gap_total / pieces      # spiral: each ring picks up where the last one ended
        arcs = []
        for w in weights:
            length = total * w / sum(weights)
            arcs.append((start, start + length))
            start += length + gap_total / pieces

        prev_end = arcs[-1][1] if arcs else start
        rings.append({"index": k, "radius": R, "center": [cx, cz], "arcs": arcs})
        if R <= 0.01:  # center disc
            balls.append({"x": cx, "z": cz, "r": s["size"] * 1.5, "h": base})
            continue

        snap = (lambda y: round(y / s["step"]) * s["step"]) if s["step"] > 0 else (lambda y: y)
        a_start = arcs[0][0] if arcs else 0.0
        for a0, a1 in arcs:
            h = snap(base + rng.uniform(-1, 1) * s["piece_lift"])
            walked = 0.0
            next_terrace = s["terrace"] * rng.uniform(0.5, 1.5)
            a = a0
            while a < a1:
                r = s["size"] * (1 + rng.uniform(-1, 1) * s["size_var"])
                rad = R * (1 + s["wobble"] * wob((a / math.tau) % 1))
                x, z = cx + math.cos(a) * rad, cz + math.sin(a) * rad
                if walked >= next_terrace:          # new terrace: step up, down or stay
                    h += rng.choice((-1, 1, 1)) * s["step"]
                    walked = 0.0
                    next_terrace = s["terrace"] * rng.uniform(0.5, 1.5)
                hb = snap(h + s["spiral"] * (a - a_start) / math.tau)   # spiral: climbs as it goes round
                balls.append({"x": x, "z": z, "r": r, "h": hb})
                if rng.random() < s["blobs"] * 0.3:  # a fat bulge off the ring
                    off = rng.choice((-1, 1)) * r * 0.9
                    balls.append({"x": x + math.cos(a) * off, "z": z + math.sin(a) * off,
                                  "r": r * rng.uniform(1.2, 1.8), "h": hb})
                arc_step = max(r * s["beads"], 0.5)
                a += arc_step / max(rad, 1.0)
                walked += arc_step
    for b in balls:
        b["fr"] = b["r"] / VIS                       # field radius
    return {"rings": rings, "balls": balls}


# ---------------------------------------------------------------- 2. 2D field -> 3D volume
def build_field(balls: list, s: dict):
    """2D pass: total field + which ball owns each cell (the strongest one). Heights not needed."""
    v = s["voxel"]
    pad = 2 * v
    lo_x = min(b["x"] - b["fr"] for b in balls) - pad
    hi_x = max(b["x"] + b["fr"] for b in balls) + pad
    lo_z = min(b["z"] - b["fr"] for b in balls) - pad
    hi_z = max(b["z"] + b["fr"] for b in balls) + pad
    nx = int(math.ceil((hi_x - lo_x) / v)) + 1
    nz = int(math.ceil((hi_z - lo_z) / v)) + 1
    ax = lo_x + np.arange(nx) * v
    az = lo_z + np.arange(nz) * v

    field = np.zeros((nx, nz), np.float32)
    best = np.zeros((nx, nz), np.float32)
    owner = np.full((nx, nz), -1, np.int32)
    for n, b in enumerate(balls):
        i0 = max(0, int((b["x"] - b["fr"] - lo_x) / v)); i1 = min(nx, int((b["x"] + b["fr"] - lo_x) / v) + 2)
        k0 = max(0, int((b["z"] - b["fr"] - lo_z) / v)); k1 = min(nz, int((b["z"] + b["fr"] - lo_z) / v) + 2)
        dx = (ax[i0:i1] - b["x"]) / b["fr"]
        dz = (az[k0:k1] - b["z"]) / b["fr"]
        f = np.clip(1 - (dx[:, None] ** 2 + dz[None, :] ** 2), 0, None) ** 3
        field[i0:i1, k0:k1] += f
        win = f > best[i0:i1, k0:k1]
        best[i0:i1, k0:k1] = np.where(win, f, best[i0:i1, k0:k1])
        owner[i0:i1, k0:k1] = np.where(win, n, owner[i0:i1, k0:k1])
    land = field > THRESHOLD
    return {"field": field, "owner": owner, "land": land, "lo": (lo_x, lo_z), "dims": (nx, nz)}


def touching_pairs(f2d) -> np.ndarray:
    """Exact contacts: neighbouring land cells owned by different balls."""
    land, owner = f2d["land"], f2d["owner"]
    pairs = []
    for a, b, la, lb in ((owner[:-1], owner[1:], land[:-1], land[1:]),
                         (owner[:, :-1], owner[:, 1:], land[:, :-1], land[:, 1:])):
        m = la & lb & (a != b)
        p = np.stack([a[m], b[m]], 1)
        pairs.append(np.sort(p, 1))
    p = np.concatenate(pairs) if pairs else np.zeros((0, 2), int)
    return np.unique(p, axis=0)


def build_volume(balls: list, s: dict, f2d: dict):
    v = s["voxel"]
    pad = 2 * v
    field, owner, land = f2d["field"], f2d["owner"], f2d["land"]
    lo_x, lo_z = f2d["lo"]
    nx, nz = f2d["dims"]
    heights = np.array([b["h"] for b in balls], np.float32)
    top = np.where(owner >= 0, heights[np.maximum(owner, 0)], 0).astype(np.float32)

    # belly: deeper where the field is strong (middle), thin at the silhouette edge
    strength = np.sqrt(np.clip(field - THRESHOLD, 0, None))
    bottom = top - s["thickness"] - s["belly"] * s["size"] * strength

    y_lo = float(bottom[land].min()) - pad if land.any() else -1.0
    y_hi = float(top[land].max()) + pad if land.any() else 1.0
    ny = int(math.ceil((y_hi - y_lo) / v)) + 1
    ay = y_lo + np.arange(ny) * v

    # signed volume: >0 inside. inside = in the silhouette AND between bottom and top.
    edge = (field - THRESHOLD) * s["size"] * 4         # roughly studs from the edge
    Y = ay[None, :, None]
    g = np.minimum(np.minimum(edge[:, None, :], top[:, None, :] - Y), Y - bottom[:, None, :])
    return g.astype(np.float32), np.array([lo_x, y_lo, lo_z]), (nx, ny, nz), land, top


# ---------------------------------------------------------------- 3. mesh
def build_mesh(g, lo, voxel):
    from skimage.measure import marching_cubes
    if g.max() <= 0:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=int), np.zeros(0, dtype=bool)
    verts, faces, _, _ = marching_cubes(g, 0.0, spacing=(voxel, voxel, voxel))
    verts += lo
    faces = faces[:, ::-1]                                # outward-facing winding
    a, b, c = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    nrm = np.cross(b - a, c - a)
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-9
    top = nrm[:, 1] > 0.7                                 # walkable faces
    return verts, faces, top


def resolve_heights(balls: list, s: dict, pairs: np.ndarray) -> dict:
    """Keep every ball where it is (the look from above); change only heights so that
    any two touching balls differ by at most one jump.

    Heights are counted in whole steps. Two "envelopes" are grown across the contact graph:
      low  = lowest you can be:  max over others of (their height - m steps per hop)
      high = highest you can be: min over others of (their height + m steps per hop)
    Each envelope alone is jumpable everywhere; so is their average. The average keeps
    the original ups and downs, squeezed just enough to fit.
    """
    if not len(balls) or not len(pairs):
        return {"moved": 0}
    unit = min(s["step"], s["jump"]) if s["step"] > 0 else s["jump"] / 4
    m = max(1, int(s["jump"] / unit + 1e-6))
    k = np.array([round(b["h"] / unit) for b in balls], dtype=np.int64)
    i, j = pairs[:, 0], pairs[:, 1]
    hi, lo = k.copy(), k.copy()
    for _ in range(len(balls)):
        nh, nl = hi.copy(), lo.copy()
        np.minimum.at(nh, i, hi[j] + m); np.minimum.at(nh, j, hi[i] + m)
        np.maximum.at(nl, i, lo[j] - m); np.maximum.at(nl, j, lo[i] - m)
        if (nh == hi).all() and (nl == lo).all():
            break
        hi, lo = nh, nl
    new = (hi + lo) // 2                                  # floor keeps neighbours within m
    for b, kk in zip(balls, new):
        b["h"] = float(kk * unit)
    return {"moved": int((new != k).sum()), "unit": unit, "steps_per_jump": m}


def jump_check(land, top, voxel, jump):
    """Walk the top heightmap: neighbouring land cells whose heights differ by more than
    the player's jump are walls you can't get up. Reports their total length in meters."""
    bad = 0
    biggest = 0.0
    for axis in (0, 1):
        a = np.take(land, range(land.shape[axis] - 1), axis=axis) & np.take(land, range(1, land.shape[axis]), axis=axis)
        d = np.abs(np.diff(top, axis=axis))
        d = np.where(a, d, 0)
        bad += int((d > jump + 1e-4).sum())
        biggest = max(biggest, float(d.max()) if d.size else 0.0)
    levels = sorted(set(np.round(top[land], 3).tolist()))
    return {"unjumpable_m": round(bad * voxel, 1), "max_step_m": round(biggest, 2), "levels": len(levels)}


def pieces(f2d, balls, s):
    """Label separate pieces of land and find, for each pair, the closest edge cells."""
    from scipy import ndimage
    from scipy.spatial import cKDTree
    land, owner = f2d["land"], f2d["owner"]
    labels, n = ndimage.label(land)
    v = s["voxel"]
    lo_x, lo_z = f2d["lo"]
    h = np.array([b["h"] for b in balls])
    edge = land & ~ndimage.binary_erosion(land)
    info = []
    for c in range(1, n + 1):
        ii, kk = np.nonzero(edge & (labels == c))
        xz = np.stack([lo_x + ii * v, lo_z + kk * v], 1)
        info.append({"id": c, "area": int((labels == c).sum()), "xz": xz,
                     "h": h[owner[ii, kk]], "own": owner[ii, kk], "tree": cKDTree(xz)})
    return labels, info


def add_filler(f2d, balls, s):
    """Connect every piece to the biggest one with stepping stones.

    Two pieces are linked when their closest edges are within `reach` sideways and one
    jump up/down. Starting from the biggest piece, repeatedly take the cheapest unreached
    piece and lay stones on the straight line between the closest edge points:
    enough hops that no hop is longer than reach*stone_gap or taller than one jump.
    """
    labels, info = pieces(f2d, balls, s)
    links = []                                   # (ball, ball) pairs a hop apart: must stay jumpable
    if len(info) < 2:
        return 0, 0, links
    unit = min(s["step"], s["jump"]) if s["step"] > 0 else s["jump"] / 4
    m = max(1, int(s["jump"] / unit + 1e-6))
    up = m * unit
    hop = max(s["reach"] * s["stone_gap"], 0.3)
    # closest edge points between every pair of pieces
    best = {}
    for a in range(len(info)):
        for b in range(a + 1, len(info)):
            A, B = info[a], info[b]
            d, j = B["tree"].query(A["xz"])
            i = int(np.argmin(d))
            best[(a, b)] = (float(d[i]), A["xz"][i], B["xz"][j[i]], float(A["h"][i]), float(B["h"][j[i]]),
                            int(A["own"][i]), int(B["own"][j[i]]))

    def pair(a, b):
        return best[(a, b)] if a < b else (lambda t: (t[0], t[2], t[1], t[4], t[3], t[6], t[5]))(best[(b, a)])

    reached = {max(range(len(info)), key=lambda c: info[c]["area"])}
    stones = 0
    while len(reached) < len(info):
        cand = []
        for a in reached:
            for b in range(len(info)):
                if b in reached:
                    continue
                d, pa, pb, ha, hb, _, _ = pair(a, b)
                hops = max(1, math.ceil(d / hop), math.ceil(abs(hb - ha) / up))
                cand.append((hops, d, a, b))
        hops, d, a, b = min(cand)
        _, pa, pb, ha, hb, oa, ob = pair(a, b)
        prev = oa
        if hops > 1 or d > s["reach"] or abs(hb - ha) > up:
            hops = max(2, hops)
            ka = round(ha / unit)
            dk = round(hb / unit) - ka
            for t in range(1, hops):
                f = t / hops
                x = pa[0] + (pb[0] - pa[0]) * f
                z = pa[1] + (pb[1] - pa[1]) * f
                k = ka + math.floor(dk * f)
                r = s["stone"]
                balls.append({"x": float(x), "z": float(z), "r": r, "h": float(k * unit),
                              "fr": r / VIS, "kind": "filler"})
                links.append((prev, len(balls) - 1))
                prev = len(balls) - 1
                stones += 1
        links.append((prev, ob))
        reached.add(b)
    return stones, len(info), links


def reach_check(f2d, balls, s):
    """How many pieces can't be reached from the biggest one (jumping sideways <= reach,
    up/down <= jump between closest edges)."""
    labels, info = pieces(f2d, balls, s)
    if len(info) < 2:
        return 0, len(info)
    links = {c: set() for c in range(len(info))}
    for a in range(len(info)):
        for b in range(a + 1, len(info)):
            d, j = info[b]["tree"].query(info[a]["xz"], distance_upper_bound=s["reach"] + s["voxel"])
            ok = np.isfinite(d)
            if ok.any():
                i = np.nonzero(ok)[0]
                dh = np.abs(info[a]["h"][i] - info[b]["h"][j[i]])
                if (dh <= s["jump"] + 1e-4).any():
                    links[a].add(b); links[b].add(a)
    start = max(range(len(info)), key=lambda c: info[c]["area"])
    seen, todo = {start}, [start]
    while todo:
        for nb in links[todo.pop()]:
            if nb not in seen:
                seen.add(nb); todo.append(nb)
    return len(info) - len(seen), len(info)


def generate(seed: int, settings: dict = None) -> dict:
    s = {**DEFAULTS, **(settings or {})}
    if int(s["layout"]) == 1:                    # tower: its own layered generator
        from .tower import generate as tower_generate
        return tower_generate(seed, s)
    t0 = time.perf_counter()
    layout = generate_balls(seed, s)
    f2d = build_field(layout["balls"], s)
    solve = resolve_heights(layout["balls"], s, touching_pairs(f2d)) if int(s["resolve"]) else {"moved": 0}
    stones, n_pieces = 0, 0
    hops = []
    if int(s["filler"]):
        for _ in range(6):                       # stones can create new contacts: re-check
            added, n_pieces, links = add_filler(f2d, layout["balls"], s)
            stones += added
            hops += links
            f2d = build_field(layout["balls"], s)
            if int(s["resolve"]):
                # touching balls AND stone-to-stone hops both have to stay within one jump
                extra = np.array(hops, dtype=np.int64).reshape(-1, 2)
                resolve_heights(layout["balls"], s, np.concatenate([touching_pairs(f2d), extra]))
                f2d = build_field(layout["balls"], s)
            if not added:
                break
    unreachable, n_final = reach_check(f2d, layout["balls"], s)
    t1 = time.perf_counter()
    if int(s["mesher"]):
        # pads: no 3D volume needed; the 2D grid is the whole story
        land = f2d["land"]
        hts = np.array([b["h"] for b in layout["balls"]] + [0.0], np.float32)
        top_h = np.where(f2d["owner"] >= 0, hts[np.maximum(f2d["owner"], 0)], 0).astype(np.float32)
        lo = np.array([f2d["lo"][0], float(top_h[land].min()) if land.any() else 0.0, f2d["lo"][1]])
        dims = (f2d["dims"][0], 1, f2d["dims"][1])
    else:
        g, lo, dims, land, top_h = build_volume(layout["balls"], s, f2d)
    jump = jump_check(land, top_h, s["voxel"], s["jump"])
    t2 = time.perf_counter()
    is_filler = np.array([b.get("kind") == "filler" for b in layout["balls"]] + [False])
    if int(s["mesher"]):
        from .pads import build_pads
        verts, faces, mat = build_pads({"settings": s, "f2d": f2d, "balls": layout["balls"], "seed": seed})
        top = mat != 1
        filler_face = mat == 2
    else:
        verts, faces, top = build_mesh(g, lo, s["voxel"])
    # which top faces sit on a filler stone (data: material 2)
    if int(s["mesher"]):
        pass
    elif len(faces):
        cen = verts[faces].mean(1)
        ci = np.clip(np.round((cen[:, 0] - f2d["lo"][0]) / s["voxel"]).astype(int), 0, f2d["dims"][0] - 1)
        ck = np.clip(np.round((cen[:, 2] - f2d["lo"][1]) / s["voxel"]).astype(int), 0, f2d["dims"][1] - 1)
        filler_face = top & is_filler[f2d["owner"][ci, ck]]
    else:
        filler_face = np.zeros(0, bool)
    t3 = time.perf_counter()
    return {
        "seed": seed,
        "settings": s,
        **layout,
        "grid": {"origin": lo.tolist(), "dims": list(dims), "voxel": s["voxel"]},
        "f2d": f2d,                              # 2D grid (land, owner, field) for the level layer
        "verts": verts,
        "faces": faces,
        "top": top,
        "filler_face": filler_face,
        "jump": jump,
        "stats": {
            **jump,
            "resolved_balls": solve["moved"],
            "stones": stones,
            "pieces": n_final,
            "unreachable": unreachable,
            "balls": len(layout["balls"]),
            "tris": int(len(faces)),
            "verts": int(len(verts)),
            "cells": int(np.prod(dims)),
            "ms_balls": round((t1 - t0) * 1000, 1),
            "ms_field": round((t2 - t1) * 1000, 1),
            "ms_mesh": round((t3 - t2) * 1000, 1),
        },
    }
