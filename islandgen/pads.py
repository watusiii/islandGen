"""Pad mesher: flat terraces as clean low-poly slabs, instead of marching cubes.

The tops are dead flat, so the land is really 2D outlines with heights. Per terrace:
  1. outline   trace the terrace's edge on the grid at sub-cell accuracy (contour of a softened mask)
  2. simplify  cut the outline down to a few corners -> the faceted low-poly edge (`facet`, meters)
  3. build     top cap (filled polygon, holes kept), a lip wall straight down, then a rock belly:
               rings that step inward and down, deepest where the pad is widest, closed underneath.
Every terrace is its own closed solid. Neighbours overlap a little; the hidden parts sit inside
each other, so there are never cracks between steps.

Engine-agnostic: returns vertices (meters, Y up), triangles, and a material id per triangle
(0 top, 1 rock, 2 filler) - the same contract as the marching-cubes path.
"""
import math

import numpy as np

MAT_TOP, MAT_ROCK, MAT_FILLER = 0, 1, 2


# ---------------------------------------------------------------- outlines
def _polygons(mask, lo, v, facet, grow):
    """Boolean grid mask -> list of shapely Polygons (holes kept), in meters."""
    from scipy.ndimage import gaussian_filter
    from shapely.geometry import Polygon
    from shapely.geometry.polygon import orient
    from skimage.measure import find_contours

    m = gaussian_filter(np.pad(mask.astype(np.float32), 2), 0.7)
    rings = []
    for c in find_contours(m, 0.5):
        if len(c) < 4:
            continue
        xz = np.stack([lo[0] + (c[:, 0] - 2) * v, lo[1] + (c[:, 1] - 2) * v], 1)
        p = Polygon(xz)
        if not p.is_valid:
            p = p.buffer(0)
        if p.is_empty or p.area < (0.25 * v) ** 2:
            continue
        rings.append(p)
    # biggest first; a ring inside an earlier shell is a hole in it
    rings.sort(key=lambda p: -p.area)
    shells = []
    for p in rings:
        for sh in shells:
            if sh["poly"].contains(p.representative_point()):
                sh["holes"].append(p)
                break
        else:
            shells.append({"poly": p, "holes": []})
    out = []
    for sh in shells:
        poly = sh["poly"]
        for h in sh["holes"]:
            poly = poly.difference(h)
        poly = poly.buffer(grow, join_style=2)                     # overlap neighbours: no cracks
        simple = poly.simplify(facet, preserve_topology=True)
        poly = simple if (not simple.is_empty and simple.area > 0.5 * poly.area) else poly
        for g in getattr(poly, "geoms", [poly]):
            if g.area > 1e-3:
                out.append(orient(g, 1.0))                         # exterior CCW in (x, z)
    return out


# ---------------------------------------------------------------- geometry helpers
class _Mesh:
    def __init__(self):
        self.v, self.f, self.m = [], [], []

    def tri(self, a, b, c, mat, want=None):
        """Add a triangle; if `want` (a direction) is given, wind it to face that way."""
        a, b, c = np.asarray(a, float), np.asarray(b, float), np.asarray(c, float)
        n = np.cross(b - a, c - a)
        if np.dot(n, n) < 1e-14:
            return
        if want is not None and np.dot(n, want) < 0:
            b, c = c, b
        i = len(self.v)
        self.v += [a, b, c]
        self.f.append((i, i + 1, i + 2))
        self.m.append(mat)

    def quad(self, a, b, c, d, mat, want):
        self.tri(a, b, c, mat, want)
        self.tri(a, c, d, mat, want)


def _ring_normals(ring):
    """Per-vertex outward normals of a closed ring (CCW exterior / CW hole -> points off the solid)."""
    p = np.asarray(ring)
    nxt = np.roll(p, -1, 0)
    e = nxt - p
    en = np.stack([e[:, 1], -e[:, 0]], 1)                         # right-hand normal = outward for CCW
    en /= np.linalg.norm(en, axis=1, keepdims=True) + 1e-12
    vn = en + np.roll(en, 1, 0)
    vn /= np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12
    return en, vn


def _inner_room(points, vn, edt, lo, v):
    """How far each vertex can move inward before reaching the middle of the pad (meters)."""
    out = np.zeros(len(points))
    nx, nz = edt.shape
    for i, (p, n) in enumerate(zip(points, vn)):
        best, t = 0.0, 0.0
        while t < 40 * v:
            q = p - n * t
            ci, ck = int(round((q[0] - lo[0]) / v)), int(round((q[1] - lo[1]) / v))
            if not (0 <= ci < nx and 0 <= ck < nz):
                break
            d = edt[ci, ck] * v
            if d + 0.25 * v < best:                               # past the ridge
                break
            best = max(best, d)
            t += 0.5 * v
        out[i] = max(min(best, t), 0.2 * v)
    return out


def _triangulate(rings_xz):
    """Earcut a polygon given as [exterior, hole, hole...] (each Nx2). Returns index triples."""
    import mapbox_earcut as earcut
    verts = np.concatenate(rings_xz).astype(np.float64)
    ends = np.cumsum([len(r) for r in rings_xz]).astype(np.uint32)
    idx = earcut.triangulate_float64(verts, ends)
    return verts, np.asarray(idx).reshape(-1, 3)


# ---------------------------------------------------------------- one terrace: cap + walls
def _wall_depth(s):
    return max(s["thickness"], s["jump"] + 0.2)                   # always reaches the step below


def _prism(mesh, poly, top, mat_top, s, grid):
    """Flat cap + lip + walls. Each wall edge drops only as far as the ground beside it:
    to the lower terrace's top at a step, the full slab `thickness` over open air."""
    land, tops, lo, v = grid
    lip = min(s["lip"], s["thickness"])
    rings = [np.asarray(poly.exterior.coords)[:-1]] + [np.asarray(h.coords)[:-1] for h in poly.interiors]
    verts, tris = _triangulate(rings)
    for a, b, c in tris:
        mesh.tri(*[(verts[k][0], top, verts[k][1]) for k in (a, b, c)], mat_top, np.array([0, 1.0, 0]))
    nx, nz = land.shape
    for ring in rings:
        en, _ = _ring_normals(ring)
        n = len(ring)
        for i in range(n):
            p, q = ring[i], ring[(i + 1) % n]
            m = (p + q) / 2 + en[i] * 0.7 * v
            ci, ck = int(round((m[0] - lo[0]) / v)), int(round((m[1] - lo[1]) / v))
            bottom = top - s["thickness"]                       # open air: full slab
            if 0 <= ci < nx and 0 <= ck < nz and land[ci, ck]:
                other = tops[ci, ck]
                if other < top - 1e-3:
                    bottom = max(other - 0.05, top - s["thickness"] - s["jump"])   # step down: meet its top
                else:
                    bottom = top - lip - 0.05                   # same level or higher: hidden, keep short
            out = np.array([en[i][0], 0, en[i][1]])
            P = lambda xz, y: (xz[0], y, xz[1])
            mesh.quad(P(p, top), P(q, top), P(q, top - lip), P(p, top - lip), mat_top, out)
            if bottom < top - lip:
                mesh.quad(P(p, top - lip), P(q, top - lip), P(q, bottom), P(p, bottom), MAT_ROCK, out)


# ---------------------------------------------------------------- one island: the rock belly
def _belly(mesh, poly, y0_of, s, edt, lo, v, rng):
    """One belly under a whole island. Ring 0 is the island outline, each vertex at the bottom of
    the wall above it (y0_of); rings step inward toward the middle and down, deeper where wider."""
    rings = [np.asarray(poly.exterior.coords)[:-1]] + [np.asarray(h.coords)[:-1] for h in poly.interiors]
    K = int(s["belly_rings"])
    inner = []
    for ring in rings:
        en, vn = _ring_normals(ring)
        n = len(ring)
        y0 = np.array([y0_of(p) for p in ring])
        room = _inner_room(ring, vn, edt, lo, v)
        deep = s["thickness"] * 0.3 + s["belly"] * float(np.max(room)) * 2.0     # one depth per island
        layers = [np.column_stack([ring[:, 0], y0, ring[:, 1]])]
        for k in range(1, K + 1):
            t = k / K
            jitter = 1 + rng.uniform(-0.12, 0.12, n)
            inset = np.minimum(room * 0.94, room * (t ** 0.6) * jitter)
            # deeper toward the middle of the island: depth follows how far in this ring point is
            local = 0.35 + 0.65 * (inset / max(float(np.max(room)), 1e-6))
            depth = deep * (t ** 1.2) * local * (1 + rng.uniform(-0.08, 0.08, n))
            xz = ring - vn * inset[:, None]
            layers.append(np.column_stack([xz[:, 0], y0 - depth, xz[:, 1]]))
        for k in range(K):
            A, B = layers[k], layers[k + 1]
            for i in range(n):
                j = (i + 1) % n
                out = np.array([en[i][0], -0.6, en[i][1]])
                mesh.quad(A[i], A[j], B[j], B[i], MAT_ROCK, out)
        inner.append(layers[-1])
    try:
        verts, tris = _triangulate([r[:, [0, 2]] for r in inner])
        ys = np.concatenate([r[:, 1] for r in inner])
        for a, b, c in tris:
            mesh.tri((verts[a][0], ys[a], verts[a][1]), (verts[b][0], ys[b], verts[b][1]),
                     (verts[c][0], ys[c], verts[c][1]), MAT_ROCK, np.array([0, -1.0, 0]))
    except Exception:
        pass


# ---------------------------------------------------------------- all terraces
def build_pads(res: dict):
    """Mesh every terrace of a meta.generate() result. Returns verts (N,3), faces (M,3), mat (M,)."""
    from scipy import ndimage
    from .level import _terraces
    s = res["settings"]
    f = res["f2d"]
    land, owner = f["land"], f["owner"]
    lo, v = f["lo"], s["voxel"]
    h = np.array([b["h"] for b in res["balls"]] + [0.0])
    filler = np.array([b.get("kind") == "filler" for b in res["balls"]] + [False])
    top = np.where(land, h[owner], np.nan)
    labels, n = _terraces(land, top)
    pieces = labels                                                 # one belly per flat terrace (a pad, or a stair step)
    rng = np.random.default_rng(res["seed"] + 77)
    mesh = _Mesh()
    grow = 0.2 * v
    wall = s["thickness"]                                           # outline edges hang the full slab

    def window(sl, shape):
        i0, i1 = max(sl[0].start - 3, 0), min(sl[0].stop + 3, shape[0])
        k0, k1 = max(sl[1].start - 3, 0), min(sl[1].stop + 3, shape[1])
        return i0, i1, k0, k1

    # terraces: flat cap + lip + wall
    for t, sl in enumerate(ndimage.find_objects(labels), start=1):
        if sl is None:
            continue
        i0, i1, k0, k1 = window(sl, land.shape)
        mask = labels[i0:i1, k0:k1] == t
        wlo = (lo[0] + i0 * v, lo[1] + k0 * v)
        ii, kk = np.nonzero(mask)
        y = float(top[i0 + ii[0], k0 + kk[0]])
        is_stone = bool(filler[owner[i0 + ii[0], k0 + kk[0]]])
        for poly in _polygons(mask, wlo, v, s["facet"], grow):
            _prism(mesh, poly, y, MAT_FILLER if is_stone else MAT_TOP, s, (land, top, lo, v))

    # islands: one rock belly each, hanging from the wall bottoms along the outline
    for pc, sl in enumerate(ndimage.find_objects(pieces), start=1):
        if sl is None:
            continue
        i0, i1, k0, k1 = window(sl, land.shape)
        mask = pieces[i0:i1, k0:k1] == pc
        wlo = (lo[0] + i0 * v, lo[1] + k0 * v)
        tops = np.where(mask, top[i0:i1, k0:k1], -np.inf)
        edt = ndimage.distance_transform_edt(np.pad(mask, 1))[1:-1, 1:-1]

        def y0_of(p, tops=tops, wlo=wlo):
            # highest top within ~1.5 cells of this outline point, minus the wall
            ci, ck = (p[0] - wlo[0]) / v, (p[1] - wlo[1]) / v
            a0, a1 = max(int(ci - 1.5), 0), min(int(ci + 2.5), tops.shape[0])
            b0, b1 = max(int(ck - 1.5), 0), min(int(ck + 2.5), tops.shape[1])
            w = tops[a0:a1, b0:b1]
            hmax = float(w.max()) if w.size and np.isfinite(w.max()) else float(np.nanmax(np.where(np.isfinite(tops), tops, np.nan)))
            return hmax - wall
        for poly in _polygons(mask, wlo, v, s["facet"], grow):
            _belly(mesh, poly, y0_of, s, edt, wlo, v, rng)

    if not mesh.f:
        return np.zeros((0, 3)), np.zeros((0, 3), int), np.zeros(0, int)
    return np.array(mesh.v), np.array(mesh.f, dtype=np.int64), np.array(mesh.m, dtype=np.int64)
