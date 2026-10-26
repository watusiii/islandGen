"""Tower layout: floating pads winding up a helix, joined by ribbon paths and hop stones.

Every pad is its own flat layer with its own small 2D metaball field, so pads can stack
over each other (a real tower), which the single top-down grid of meta.py can't do.

  pads      flat metaball clusters on a tapering helix; pad 0 is the round base at the centre
  links     between consecutive pads, one of:
              ramp    a grassy ribbon that curves up between them (gentle climbs)
              stairs  a ribbon of stone treads (steeper climbs)
              hop     a few floating stepping stones: the platforming bits
  dressing  per pad: a sand patch with rocks, a lantern, a tree spot; a torii on the top pad
  level     spawn (base), goal (top), route, dust spots with height01, and collision boxes

Engine-agnostic, meters, Y up. Returns the same result contract as meta.generate (verts, faces,
material per face, stats) plus a ready `level` dict, so the exporters and the GUI just work.
"""
import math
import random
import time

import numpy as np

from .pads import _Mesh, _polygons, _ring_normals, _triangulate, _belly

MAT_TOP, MAT_ROCK, MAT_STONE, MAT_SAND = 0, 1, 2, 3
THRESHOLD = 0.5
VIS = math.sqrt(1 - THRESHOLD ** (1 / 3))


# ---------------------------------------------------------------- layout
def _layout(rng, s):
    n = int(s["pads"])
    a0 = rng.uniform(0, math.tau)
    # uneven climbs: some pads close in height (ramps), some far (stairs / hops)
    # pad 1 stays low so the way in from the base is an easy stair; the rest share the climb
    first = min(1.2, s["climb"] * 0.2)
    w = [rng.uniform(0.5, 1.5) for _ in range(n - 2)]
    hs = [0.0, first]
    for x in w:
        hs.append(hs[-1] + (s["climb"] - first) * x / max(sum(w), 1e-6))
    unit = max(s["stair_rise"] * 2, 0.1)
    snap = lambda y: round(y / unit) * unit
    pads = [{"i": 0, "x": 0.0, "z": 0.0, "h": 0.0, "r": s["base_r"], "angle": a0, "R": 0.0, "base": True}]
    for i in range(1, n):
        t = (i - 1) / max(n - 2, 1)
        a = a0 + s["turns"] * math.tau * t
        R = s["radius"] * (1 - s["taper"] * t)
        r = s["pad_size"] * (1 + rng.uniform(-1, 1) * s["size_var"] * 0.5)
        if i == n - 1:
            r *= 1.25                                              # the top pad is a little stage
        pads.append({"i": i, "x": math.cos(a) * R, "z": math.sin(a) * R, "h": snap(hs[i]),
                     "r": r, "angle": a, "R": R, "base": False})
    # keep stacked pads apart: anything overlapping in plan must clear head room + belly
    for _ in range(20):
        moved = False
        for j in range(1, n):
            for k in range(j):
                p, q = pads[k], pads[j]
                d = math.hypot(q["x"] - p["x"], q["z"] - p["z"])
                need_h = s["player_height"] + 1.2 + s["belly"] * (p["r"] + q["r"]) + s["thickness"]
                gap_need = 1.0 if j == k + 1 else 0.6                   # neighbours always get a real gap
                if d < p["r"] + q["r"] + gap_need and (j == k + 1 or abs(q["h"] - p["h"]) < need_h):
                    # push the later pad outward along its own spoke
                    q["R"] += 0.8
                    q["x"], q["z"] = math.cos(q["angle"]) * q["R"], math.sin(q["angle"]) * q["R"]
                    moved = True
        if not moved:
            break
    return pads


def _pad_balls(rng, p, s):
    if p["base"]:
        return [{"x": p["x"], "z": p["z"], "r": p["r"], "h": p["h"]}]
    balls = [{"x": p["x"], "z": p["z"], "r": p["r"], "h": p["h"]}]
    for _ in range(rng.randint(1, 3)):
        sa = rng.uniform(0, math.tau)
        d = p["r"] * rng.uniform(0.45, 0.8)
        balls.append({"x": p["x"] + math.cos(sa) * d, "z": p["z"] + math.sin(sa) * d,
                      "r": p["r"] * rng.uniform(0.45, 0.75), "h": p["h"]})
    return balls


def _outline(balls, facet, res):
    """Metaball cluster (one height) -> simplified polygon(s), plus the mask grid for bellies."""
    lo_x = min(b["x"] - b["r"] / VIS for b in balls) - 2 * res
    hi_x = max(b["x"] + b["r"] / VIS for b in balls) + 2 * res
    lo_z = min(b["z"] - b["r"] / VIS for b in balls) - 2 * res
    hi_z = max(b["z"] + b["r"] / VIS for b in balls) + 2 * res
    ax = np.arange(lo_x, hi_x + res, res)
    az = np.arange(lo_z, hi_z + res, res)
    X, Z = np.meshgrid(ax, az, indexing="ij")
    field = np.zeros(X.shape, np.float32)
    for b in balls:
        fr = b["r"] / VIS
        q = ((X - b["x"]) ** 2 + (Z - b["z"]) ** 2) / fr ** 2
        field += np.clip(1 - q, 0, None) ** 3
    mask = field > THRESHOLD
    polys = _polygons(mask, (lo_x, lo_z), res, facet, 0.0)
    return polys, mask, (lo_x, lo_z)


# ---------------------------------------------------------------- solids
def _slab(mesh, poly, top, mat_top, s, mask, lo, res, rng, belly=True, thickness=None):
    """Flat cap + lip + wall all round (open air), and optionally the rock belly underneath."""
    from scipy import ndimage
    th = s["thickness"] if thickness is None else thickness
    lip = min(s["lip"], th)
    rings = [np.asarray(poly.exterior.coords)[:-1]] + [np.asarray(h.coords)[:-1] for h in poly.interiors]
    verts, tris = _triangulate(rings)
    for a, b, c in tris:
        mesh.tri(*[(verts[k][0], top, verts[k][1]) for k in (a, b, c)], mat_top, np.array([0, 1.0, 0]))
    for ring in rings:
        en, _ = _ring_normals(ring)
        n = len(ring)
        for i in range(n):
            p, q = ring[i], ring[(i + 1) % n]
            out = np.array([en[i][0], 0, en[i][1]])
            P = lambda xz, y: (xz[0], y, xz[1])
            mesh.quad(P(p, top), P(q, top), P(q, top - lip), P(p, top - lip), mat_top, out)
            mesh.quad(P(p, top - lip), P(q, top - lip), P(q, top - th), P(p, top - th), MAT_ROCK, out)
    if belly:
        edt = ndimage.distance_transform_edt(np.pad(mask, 1))[1:-1, 1:-1]
        _belly(mesh, poly, lambda p: top - th, s, edt, lo, res, rng)
    else:
        verts, tris = _triangulate(rings)
        for a, b, c in tris:
            mesh.tri(*[(verts[k][0], top - th, verts[k][1]) for k in (a, b, c)], MAT_ROCK, np.array([0, -1.0, 0]))


def _flat_patch(mesh, poly, y, mat):
    """A thin coloured patch lying on a top (sand), raised a hair to avoid flicker."""
    rings = [np.asarray(poly.exterior.coords)[:-1]] + [np.asarray(h.coords)[:-1] for h in poly.interiors]
    verts, tris = _triangulate(rings)
    for a, b, c in tris:
        mesh.tri(*[(verts[k][0], y, verts[k][1]) for k in (a, b, c)], mat, np.array([0, 1.0, 0]))
    for ring in rings:
        en, _ = _ring_normals(ring)
        for i in range(len(ring)):
            p, q = ring[i], ring[(i + 1) % len(ring)]
            mesh.quad((p[0], y, p[1]), (q[0], y, q[1]), (q[0], y - 0.04, q[1]), (p[0], y - 0.04, p[1]),
                      mat, np.array([en[i][0], 0, en[i][1]]))


# ---------------------------------------------------------------- collision boxes
def _obox(center, size, right, up):
    c = [round(float(x), 4) for x in center]
    return c + [round(float(x), 4) for x in size] + [round(float(x), 5) for x in right] + [round(float(x), 5) for x in up]


def _poly_boxes(poly, top, th, cell=0.25):
    """Rasterise a polygon into axis-aligned boxes (greedy rectangles on a fine grid)."""
    import shapely
    x0, z0, x1, z1 = poly.bounds
    ax = np.arange(x0 + cell / 2, x1, cell)
    az = np.arange(z0 + cell / 2, z1, cell)
    if not len(ax) or not len(az):
        return []
    X, Z = np.meshgrid(ax, az, indexing="ij")
    inside = shapely.contains_xy(poly, X, Z)
    used = np.zeros_like(inside)
    out = []
    nx, nz = inside.shape
    for i in range(nx):
        for k in range(nz):
            if not inside[i, k] or used[i, k]:
                continue
            k1 = k
            while k1 + 1 < nz and inside[i, k1 + 1] and not used[i, k1 + 1]:
                k1 += 1
            i1 = i
            while i1 + 1 < nx and inside[i1 + 1, k:k1 + 1].all() and not used[i1 + 1, k:k1 + 1].any():
                i1 += 1
            used[i:i1 + 1, k:k1 + 1] = True
            cx = (ax[i] + ax[i1]) / 2
            cz = (az[k] + az[k1]) / 2
            out.append(_obox((cx, top - th / 2, cz), ((i1 - i + 1) * cell, th, (k1 - k + 1) * cell),
                             (1, 0, 0), (0, 1, 0)))
    return out


# ---------------------------------------------------------------- links
def _curve(p, q, rng):
    """Smooth plan-view curve from pad p to pad q, bowing along the helix."""
    P0 = np.array([p["x"], p["z"]])
    P2 = np.array([q["x"], q["z"]])
    mid = (P0 + P2) / 2
    if p["base"] or q["base"]:
        side = np.array([-(P2 - P0)[1], (P2 - P0)[0]])
        side /= np.linalg.norm(side) + 1e-9
        ctrl = mid + side * np.linalg.norm(P2 - P0) * rng.uniform(0.15, 0.3)
    else:
        am = (p["angle"] + q["angle"]) / 2
        Rm = (p["R"] + q["R"]) / 2 * 1.08
        ctrl = np.array([math.cos(am) * Rm, math.sin(am) * Rm])
    ts = np.linspace(0, 1, 400)[:, None]
    return (1 - ts) ** 2 * P0 + 2 * (1 - ts) * ts * ctrl + ts ** 2 * P2


def _span(curve, poly_a, poly_b, overlap):
    """The part of the curve outside both pads, extended `overlap` m into each."""
    import shapely
    ina = shapely.contains_xy(poly_a, curve[:, 0], curve[:, 1])
    inb = shapely.contains_xy(poly_b, curve[:, 0], curve[:, 1])
    out = np.nonzero(~ina & ~inb)[0]
    if not len(out):
        return None
    i0, i1 = int(out[0]), int(out[-1])
    seg = np.linalg.norm(np.diff(curve, axis=0), axis=1)
    acc = np.concatenate([[0], np.cumsum(seg)])
    a = np.searchsorted(acc, acc[i0] - overlap)
    b = np.searchsorted(acc, acc[i1] + overlap)
    return max(a, 0), min(b, len(curve) - 1), acc[i1] - acc[i0]


def _resample(pts, step):
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    acc = np.concatenate([[0], np.cumsum(seg)])
    L = acc[-1]
    n = max(2, int(math.ceil(L / step)) + 1)
    d = np.linspace(0, L, n)
    x = np.interp(d, acc, pts[:, 0])
    z = np.interp(d, acc, pts[:, 1])
    return np.stack([x, z], 1), d


def _ribbon(mesh, xz, ys, width, mat_top, s, boxes):
    """A strip following xz (Nx2) at heights ys: top, lip/earth sides, keeled underside."""
    th = 0.45
    tan = np.gradient(xz, axis=0)
    tan /= np.linalg.norm(tan, axis=1, keepdims=True) + 1e-9
    nrm = np.stack([-tan[:, 1], tan[:, 0]], 1)
    L = xz + nrm * width / 2
    R = xz - nrm * width / 2
    lip = min(s["lip"], th)
    keel = th + 0.3 * width
    for i in range(len(xz) - 1):
        a, b = i, i + 1
        tl = lambda k, y=0: (L[k][0], ys[k] - y, L[k][1])
        tr = lambda k, y=0: (R[k][0], ys[k] - y, R[k][1])
        kc = lambda k: (xz[k][0], ys[k] - keel, xz[k][1])
        up = np.array([0, 1.0, 0])
        mesh.quad(tl(a), tl(b), tr(b), tr(a), mat_top, up)
        sl = np.array([nrm[a][0], 0, nrm[a][1]])
        mesh.quad(tl(a), tl(b), tl(b, lip), tl(a, lip), mat_top, sl)
        mesh.quad(tl(a, lip), tl(b, lip), tl(b, th), tl(a, th), MAT_ROCK, sl)
        mesh.quad(tr(a), tr(b), tr(b, lip), tr(a, lip), mat_top, -sl)
        mesh.quad(tr(a, lip), tr(b, lip), tr(b, th), tr(a, th), MAT_ROCK, -sl)
        mesh.quad(tl(a, th), tl(b, th), kc(b), kc(a), MAT_ROCK, sl + np.array([0, -1.0, 0]))
        mesh.quad(tr(a, th), tr(b, th), kc(b), kc(a), MAT_ROCK, -sl + np.array([0, -1.0, 0]))
        # collision: one tilted box per segment, its top on the strip
        p0 = np.array([xz[a][0], ys[a], xz[a][1]])
        p1 = np.array([xz[b][0], ys[b], xz[b][1]])
        fwd = p1 - p0
        ln = np.linalg.norm(fwd)
        if ln < 1e-6:
            continue
        fwd /= ln
        right = np.array([-nrm[a][0], 0.0, -nrm[a][1]])
        right -= fwd * np.dot(right, fwd)
        right /= np.linalg.norm(right) + 1e-9
        upv = np.cross(right, fwd)
        if upv[1] < 0:
            right, upv = -right, -upv
        c = (p0 + p1) / 2 - upv * 0.2
        boxes.append(_obox(c, (width, 0.4, ln + 0.05), right, upv))


def _stairs(mesh, xz, d, h0, h1, width, s, boxes):
    """Stone treads along the curve, rising evenly from h0 to h1 (each tread its own slab)."""
    rise_max = s["stair_rise"]
    n = max(1, int(math.ceil(abs(h1 - h0) / rise_max)))
    L = d[-1]
    tread = L / (n + 1)
    for k in range(1, n + 1):
        y = h0 + (h1 - h0) * k / n
        a, b = tread * (k - 0.1), tread * (k + 1.1)
        sel = (d >= a) & (d <= b)
        pts = xz[sel]
        if len(pts) < 2:
            continue
        mid = pts[len(pts) // 2]
        fwd2 = pts[-1] - pts[0]
        fwd2 /= np.linalg.norm(fwd2) + 1e-9
        side = np.array([-fwd2[1], fwd2[0]])
        half = np.linalg.norm(pts[-1] - pts[0]) / 2
        corners = [mid + fwd2 * half + side * width / 2, mid - fwd2 * half + side * width / 2,
                   mid - fwd2 * half - side * width / 2, mid + fwd2 * half - side * width / 2]
        from shapely.geometry import Polygon
        from shapely.geometry.polygon import orient
        poly = orient(Polygon(corners), 1.0)
        th = 0.35 + (y - h0 if h1 > h0 else h0 - y) * 0.0
        rings = [np.asarray(poly.exterior.coords)[:-1]]
        verts, tris = _triangulate(rings)
        for t in tris:
            mesh.tri(*[(verts[j][0], y, verts[j][1]) for j in t], MAT_STONE, np.array([0, 1.0, 0]))
            mesh.tri(*[(verts[j][0], y - th, verts[j][1]) for j in t], MAT_STONE, np.array([0, -1.0, 0]))
        ring = rings[0]
        en, _ = _ring_normals(ring)
        for i in range(4):
            p, q = ring[i], ring[(i + 1) % 4]
            mesh.quad((p[0], y, p[1]), (q[0], y, q[1]), (q[0], y - th, q[1]), (p[0], y - th, p[1]),
                      MAT_STONE, np.array([en[i][0], 0, en[i][1]]))
        right = np.array([side[0], 0, side[1]])
        boxes.append(_obox((mid[0], y - th / 2, mid[1]), (width, th, 2 * half),
                           -right if np.cross(right, [fwd2[0], 0, fwd2[1]])[1] < 0 else right, (0, 1, 0)))


# ---------------------------------------------------------------- dressing
def _dress(rng, pad, poly, landings, s, top_pad):
    """Pick what stands on a pad. Returns (props, sand polygon or None, dust spots)."""
    from shapely.geometry import Point
    props, spots = [], []
    inner = poly.buffer(-0.7)
    if inner.is_empty:
        return props, None, spots
    keep_clear = [Point(p).buffer(1.6) for p in landings]
    free = inner
    for k in keep_clear:
        free = free.difference(k)
    sand = None

    def pick(area, tries=40):
        if area.is_empty:
            return None
        x0, z0, x1, z1 = area.bounds
        for _ in range(tries):
            pt = Point(rng.uniform(x0, x1), rng.uniform(z0, z1))
            if area.contains(pt):
                return pt
        return None

    if top_pad:
        # torii at the far edge from where you arrive, facing the arrival
        arrive = np.mean(landings, axis=0) if landings else np.array([pad["x"], pad["z"]])
        c = np.array([pad["x"], pad["z"]])
        away = c - arrive
        away = away / (np.linalg.norm(away) + 1e-9)
        spot = c + away * pad["r"] * 0.45
        props.append({"kind": "torii", "at": [round(spot[0], 3), pad["h"], round(spot[1], 3)],
                      "face": [round(-away[0], 4), 0, round(-away[1], 4)]})
        sand = poly.buffer(-0.9).intersection(Point(c).buffer(pad["r"] * 0.55))
    elif not pad["base"]:
        feature = rng.choice(["rockgarden", "rockgarden", "lantern", "tree"])
        if feature == "rockgarden":
            centre = pick(free.buffer(-0.6)) or pick(free)
            if centre is not None:
                sand = inner.intersection(centre.buffer(pad["r"] * rng.uniform(0.45, 0.65)))
                for _ in range(rng.randint(1, 3)):
                    rp = pick(sand.buffer(-0.3)) if not sand.is_empty else None
                    if rp is not None:
                        props.append({"kind": "rocks", "at": [round(rp.x, 3), pad["h"], round(rp.y, 3)],
                                      "size": round(rng.uniform(0.35, 0.7), 3)})
        else:
            pt = pick(free)
            if pt is not None:
                props.append({"kind": feature, "at": [round(pt.x, 3), pad["h"], round(pt.y, 3)]})
    # dust spots: away from edges, landings and props
    taken = [Point(p["at"][0], p["at"][2]).buffer(1.2) for p in props]
    area = free
    for t in taken:
        area = area.difference(t)
    for _ in range(0 if pad["base"] else rng.randint(1, 2)):
        pt = pick(area)
        if pt is not None:
            spots.append((pt.x, pt.y))
            area = area.difference(pt.buffer(1.5))
    if sand is not None:
        sand = sand.simplify(s["facet"] * 0.6)
        if sand.is_empty or sand.geom_type != "Polygon" or sand.area < 0.8:
            sand = None
    return props, sand, spots


# ---------------------------------------------------------------- main
def generate(seed: int, s: dict) -> dict:
    t0 = time.perf_counter()
    s = {**s, "thickness": s["slab"], "belly": s["tower_belly"]}   # tower look: thin slab, deep rock
    rng = random.Random(seed)
    nrng = np.random.default_rng(seed + 77)
    res = min(s["voxel"], 0.2)
    pads = _layout(rng, s)
    mesh = _Mesh()
    boxes = []
    balls_out = []
    shapes = []
    for p in pads:
        balls = _pad_balls(rng, p, s)
        for b in balls:
            balls_out.append({**b, "fr": b["r"] / VIS, "kind": "land"})
        polys, mask, lo = _outline(balls, s["facet"], res)
        poly = max(polys, key=lambda g: g.area) if polys else None
        shapes.append((poly, mask, lo))

    # links between consecutive pads
    links = []
    hop_checks = []
    landings = {p["i"]: [] for p in pads}
    for p, q in zip(pads, pads[1:]):
        pa, pb = shapes[p["i"]][0], shapes[q["i"]][0]
        curve = _curve(p, q, rng)
        sp = _span(curve, pa, pb, 0.6)
        dh = q["h"] - p["h"]
        if sp is None:                                          # pads touch
            if abs(dh) <= s["jump"] * 0.9:
                links.append({"a": p["i"], "b": q["i"], "kind": "touch", "rise_m": round(dh, 3)})
                continue
            # too tall to jump: stone steps over the lower pad, along the middle of the curve
            seg = np.linalg.norm(np.diff(curve, axis=0), axis=1)
            acc = np.concatenate([[0], np.cumsum(seg)])
            i0 = int(np.searchsorted(acc, acc[-1] * 0.3))
            i1 = int(np.searchsorted(acc, acc[-1] * 0.7))
            sp = (i0, i1, acc[i1] - acc[i0])
        i0, i1, gap = sp
        xz, d = _resample(curve[i0:i1 + 1], 0.35)
        slope = abs(dh) / max(gap, 1e-6)
        kind = "ramp" if slope <= s["ramp_slope"] else "stairs"
        if p["base"]:
            kind = "ramp" if slope <= s["ramp_slope"] else "stairs"
        elif rng.random() > s["paths"] or slope > 1.0:
            kind = "hop"
        landings[p["i"]].append(tuple(xz[0]))
        landings[q["i"]].append(tuple(xz[-1]))
        if kind == "ramp":
            u = np.clip((d - 0.6) / max(d[-1] - 1.2, 1e-6), 0, 1)
            ys = p["h"] + dh * (u * u * (3 - 2 * u))
            _ribbon(mesh, xz, ys, s["ribbon"], MAT_TOP, s, boxes)
        elif kind == "stairs":
            _ribbon_ends = 0
            _stairs(mesh, xz, d, p["h"], q["h"], s["ribbon"], s, boxes)
        else:
            # hop: stepping stones spaced within reach and jump
            L = d[-1]
            k = max(1, int(math.ceil(max(L / (s["reach"] * 0.75), abs(dh) / (s["jump"] * 0.7)))) - 1)
            hop_checks.append({"link": (p["i"], q["i"]), "stride_m": L / (k + 1), "rise_m": abs(dh) / (k + 1)})
            for j in range(1, k + 1):
                f = j / (k + 1)
                c = np.array([np.interp(f * L, d, xz[:, 0]), np.interp(f * L, d, xz[:, 1])])
                h = p["h"] + dh * f
                sb = [{"x": c[0], "z": c[1], "r": s["stone"], "h": h}]
                sb.append({"x": c[0] + rng.uniform(-0.3, 0.3), "z": c[1] + rng.uniform(-0.3, 0.3),
                           "r": s["stone"] * 0.7, "h": h})
                for b in sb:
                    balls_out.append({**b, "fr": b["r"] / VIS, "kind": "filler"})
                polys, mask, lo = _outline(sb, s["facet"] * 0.6, res)
                for g in polys:
                    _slab(mesh, g, h, MAT_STONE, s, mask, lo, res, nrng, belly=True, thickness=0.5)
                    boxes += _poly_boxes(g, h, 0.5)
        links.append({"a": p["i"], "b": q["i"], "kind": kind, "gap_m": round(float(gap), 3), "rise_m": round(float(dh), 3)})

    # pads: slabs, dressing, sand, collision
    props, spots, pad_rows = [], [], []
    top_i = pads[-1]["i"]
    for p, (poly, mask, lo) in zip(pads, shapes):
        if poly is None:
            continue
        _slab(mesh, poly, p["h"], MAT_TOP, s, mask, lo, res, nrng)
        boxes += _poly_boxes(poly, p["h"], s["thickness"])
        pr, sand, sp = _dress(rng, p, poly, landings[p["i"]], s, p["i"] == top_i)
        props += pr
        if sand is not None:
            _flat_patch(mesh, sand, p["h"] + 0.03, MAT_SAND)
        for (x, z) in sp:
            spots.append({"x": round(x, 3), "y": p["h"], "z": round(z, 3), "pad": p["i"],
                          "height01": round(p["h"] / max(s["climb"], 1e-6), 4)})
        c = poly.representative_point() if p["base"] else poly.centroid
        if not poly.contains(c):
            c = poly.representative_point()
        pad_rows.append({"id": p["i"], "y": p["h"], "center": [round(c.x, 3), p["h"], round(c.y, 3)],
                         "r": round(p["r"], 3), "area_m2": round(poly.area, 2)})

    verts = np.array(mesh.v) if mesh.v else np.zeros((0, 3))
    faces = np.array(mesh.f, dtype=np.int64) if mesh.f else np.zeros((0, 3), np.int64)
    mat = np.array(mesh.m, dtype=np.int64) if mesh.m else np.zeros(0, np.int64)
    t1 = time.perf_counter()

    byid = {r["id"]: r for r in pad_rows}
    route = [{"terrace": r["id"], "at": r["center"]} for r in pad_rows]
    max_step = max([h["rise_m"] for h in hop_checks] or [0])
    # a hop stride is centre to centre; the air gap is about one stone diameter less
    bad = [h for h in hop_checks if h["stride_m"] - 1.4 * s["stone"] > s["reach"] or h["rise_m"] > s["jump"]]
    bad += [l for l in links if l["kind"] == "touch" and abs(l.get("rise_m", 0)) > s["jump"]]
    level = {
        "format": "islandgen-level/2",
        "units": "meters",
        "up": "y",
        "seed": seed,
        "layout": "tower",
        "player": {"height": s["player_height"], "jump": s["jump"], "reach": s["reach"]},
        "bounds": {"top_min": 0.0, "top_max": round(pads[-1]["h"], 3),
                   "lowest": round(float(verts[:, 1].min()), 3) if len(verts) else 0.0},
        "spawn": {"terrace": 0, "at": byid[0]["center"]},
        "goal": {"terrace": top_i, "at": byid[top_i]["center"]},
        "route": route,
        "checkpoints": [route[i] for i in range(2, len(route) - 1, 2)],
        "terraces": pad_rows,
        "links": links,
        "spots": spots,
        "props": props,
        "walk": {"format": "obox", "columns": ["cx", "cy", "cz", "sx", "sy", "sz", "rx", "ry", "rz", "ux", "uy", "uz"],
                 "boxes": boxes},
        "stats": {"pads": len(pads), "links": len(links), "route_len": len(route), "spots": len(spots),
                  "props": len(props), "boxes": len(boxes)},
    }
    stats = {
        "unjumpable_m": 0.0, "max_step_m": round(max_step, 2), "levels": len({round(p["h"], 3) for p in pads}),
        "pads": len(pads), "pieces": len(pads), "unreachable": len(bad), "stones": sum(1 for b in balls_out if b["kind"] == "filler"),
        "balls": len(balls_out), "tris": int(len(faces)), "verts": int(len(verts)), "cells": 0,
        "links": {k: sum(1 for l in links if l["kind"] == k) for k in ("ramp", "stairs", "hop", "touch")},
        "ms_balls": 0.0, "ms_field": 0.0, "ms_mesh": round((t1 - t0) * 1000, 1),
    }
    return {
        "seed": seed, "settings": s,
        "rings": [{"index": p["i"], "center": [p["x"], p["z"]], "h": p["h"], "radius": p["R"]} for p in pads],
        "balls": balls_out,
        "grid": {"origin": [0, 0, 0], "dims": [0, 0, 0], "voxel": res},
        "verts": verts, "faces": faces, "mat": mat,
        "top": (mat == MAT_TOP) | (mat == MAT_STONE) | (mat == MAT_SAND), "filler_face": mat == MAT_STONE,
        "jump": {"unjumpable_m": 0.0, "max_step_m": stats["max_step_m"], "levels": stats["levels"]},
        "stats": stats,
        "level": level,
    }
