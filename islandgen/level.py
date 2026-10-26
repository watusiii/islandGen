"""Level layer: what a game needs to PLAY the land, not just look at it.

Engine-agnostic. Everything is meters, Y up, same as the rest of islandGen.
Reads the 2D grid from meta.generate() (land mask + owning ball per cell) and returns:

  terraces   flat areas: connected land cells with the same top height
  walk       boxes that cover the flat tops exactly (simple, exact collision for any engine)
  links      which terraces connect: "walk" (touching, step <= jump) or "hop" (gap <= reach)
  spawn      the start: middle of the biggest terrace on the biggest piece
  goal       the highest terrace you can reach
  route      the shortest chain of terraces from spawn to goal (the main climb)
  checkpoints  every few terraces along the route
  spots      evenly spread points on flat tops, away from edges (collectibles, props).
             Each has a height01 (0 = lowest land, 1 = highest) so a game can weight by height.
  chunks     the mesh split into pieces of at most `max_tris` triangles, one material each
"""
import heapq
import math

import numpy as np

from .meta import THRESHOLD

SPOT_SPACING = 6.0      # m between collectible spots
SPOT_EDGE = 1.5         # cells: spots stay at least this far from any edge or step
CHECKPOINT_EVERY = 4    # route terraces between checkpoints


def _grid(res):
    f = res["f2d"]
    balls = res["balls"]
    land, owner = f["land"], f["owner"]
    h = np.array([b["h"] for b in balls] + [0.0])
    top = np.where(land, h[owner], np.nan)
    return land, owner, top, f["lo"], res["settings"]["voxel"]


def _terraces(land, top):
    from scipy import ndimage
    labels = np.zeros(land.shape, np.int32)
    n = 0
    for lvl in np.unique(top[land]):
        lab, k = ndimage.label(land & (top == lvl))
        labels[lab > 0] = lab[lab > 0] + n
        n += k
    return labels, n                                   # 0 = no land, 1..n = terrace


def _interior_distance(labels):
    """Cells from the nearest edge or step (0 on the border of its terrace)."""
    from scipy import ndimage
    L = np.pad(labels, 1)
    c = L[1:-1, 1:-1]
    inner = (c > 0) & (L[:-2, 1:-1] == c) & (L[2:, 1:-1] == c) & (L[1:-1, :-2] == c) & (L[1:-1, 2:] == c)
    return ndimage.distance_transform_edt(inner)


def _walk_boxes(labels, top, lo, v, thickness):
    """Greedy rectangles over each terrace. Each box: [x0, z0, x1, z1, top_y, bottom_y] in m."""
    nx, nz = labels.shape
    used = np.zeros(labels.shape, bool)
    boxes = []
    for i in range(nx):
        for k in range(nz):
            t = labels[i, k]
            if t == 0 or used[i, k]:
                continue
            k1 = k
            while k1 + 1 < nz and labels[i, k1 + 1] == t and not used[i, k1 + 1]:
                k1 += 1
            i1 = i
            while i1 + 1 < nx and (labels[i1 + 1, k:k1 + 1] == t).all() and not used[i1 + 1, k:k1 + 1].any():
                i1 += 1
            used[i:i1 + 1, k:k1 + 1] = True
            y = float(top[i, k])
            boxes.append([round(lo[0] + (i - 0.5) * v, 3), round(lo[1] + (k - 0.5) * v, 3),
                          round(lo[0] + (i1 + 0.5) * v, 3), round(lo[1] + (k1 + 0.5) * v, 3),
                          round(y, 3), round(y - thickness, 3)])
    return boxes


def _links(labels, top, lo, v, jump, reach):
    """Terrace graph. walk = touching cells, step <= jump. hop = edge cells within reach, step <= jump."""
    from scipy.spatial import cKDTree
    eps = 1e-4
    best = {}

    def add(a, b, d, kind, pa, pb):
        key = (min(a, b), max(a, b))
        if key not in best or d < best[key][0]:
            best[key] = (d, kind, pa, pb) if a < b else (d, kind, pb, pa)

    for sl_a, sl_b in (((slice(None, -1), slice(None)), (slice(1, None), slice(None))),
                       ((slice(None), slice(None, -1)), (slice(None), slice(1, None)))):
        a, b = labels[sl_a], labels[sl_b]
        m = (a > 0) & (b > 0) & (a != b) & (np.abs(top[sl_a] - top[sl_b]) <= jump + eps)
        for x, y in set(zip(a[m].tolist(), b[m].tolist())):
            add(x, y, 0.0, "walk", None, None)

    land = labels > 0
    L = np.pad(land, 1)
    edge = land & ~(L[:-2, 1:-1] & L[2:, 1:-1] & L[1:-1, :-2] & L[1:-1, 2:])
    ii, kk = np.nonzero(edge)
    xz = np.stack([lo[0] + ii * v, lo[1] + kk * v], 1)
    lab = labels[ii, kk]
    hh = top[ii, kk]
    pairs = cKDTree(xz).query_pairs(reach, output_type="ndarray")
    if len(pairs):
        p, q = pairs[:, 0], pairs[:, 1]
        ok = (lab[p] != lab[q]) & (np.abs(hh[p] - hh[q]) <= jump + eps)
        p, q = p[ok], q[ok]
        d = np.linalg.norm(xz[p] - xz[q], axis=1)
        order = np.argsort(d)
        for n in order:
            a, b = int(lab[p[n]]), int(lab[q[n]])
            key = (min(a, b), max(a, b))
            if key in best:
                continue
            add(a, b, float(d[n]), "hop", xz[p[n]], xz[q[n]])
    return best


def _route(n, links, centers, start, goal):
    adj = {t: [] for t in range(1, n + 1)}
    for (a, b), (d, kind, _, _) in links.items():
        w = float(np.linalg.norm(np.subtract(centers[a], centers[b]))) + (2.0 if kind == "hop" else 0.0)
        adj[a].append((b, w))
        adj[b].append((a, w))
    dist = {start: 0.0}
    prev = {}
    pq = [(0.0, start)]
    while pq:
        d, t = heapq.heappop(pq)
        if t == goal:
            break
        if d > dist.get(t, math.inf):
            continue
        for u, w in adj[t]:
            nd = d + w
            if nd < dist.get(u, math.inf):
                dist[u] = nd
                prev[u] = t
                heapq.heappush(pq, (nd, u))
    reach = set(dist)
    if goal is None or goal not in dist:
        return [start], reach
    path = [goal]
    while path[-1] != start:
        path.append(prev[path[-1]])
    return path[::-1], reach


def _spots(labels, top, dist, lo, v, seed, ymin, ymax):
    rng = np.random.default_rng(seed + 1009)
    ii, kk = np.nonzero(dist >= SPOT_EDGE)
    order = rng.permutation(len(ii))
    taken = []
    out = []
    span = max(ymax - ymin, 1e-6)
    from scipy.spatial import cKDTree
    for n in order:
        x, z = lo[0] + ii[n] * v, lo[1] + kk[n] * v
        if taken and cKDTree(np.array(taken)).query([x, z])[0] < SPOT_SPACING:
            continue
        taken.append((x, z))
        y = float(top[ii[n], kk[n]])
        out.append({"x": round(x, 3), "y": round(y, 3), "z": round(z, 3),
                    "terrace": int(labels[ii[n], kk[n]]), "height01": round((y - ymin) / span, 4)})
    return out


def _encode(verts, tri, a, b):
    """Compact geometry any engine can rebuild: base64 of little-endian uint16s.
    vertices: x,y,z quantized over the chunk's box (pos = origin + q * step, meters);
    then triangles: 3 vertex indices each (counter-clockwise seen from outside)."""
    import base64
    used, inv = np.unique(tri, return_inverse=True)
    step = np.maximum(b - a, 1e-6) / 65535.0
    q = np.round((verts[used] - a) / step).astype("<u2")
    blob = q.tobytes() + inv.reshape(-1, 3).astype("<u2").tobytes()
    return {"verts": int(len(used)), "origin": a.round(6).tolist(), "step": step.tolist(),
            "data": base64.b64encode(blob).decode("ascii")}


def _chunks(verts, faces, mat, names, max_tris):
    """Split by material, then halve along the longest axis until every chunk fits."""
    out = []
    cen_all = verts[faces].mean(1)
    for m, name in enumerate(names):
        idx = np.nonzero(mat == m)[0]
        todo = [idx] if len(idx) else []
        parts = []
        while todo:
            f = todo.pop()
            if len(f) <= max_tris:
                parts.append(f)
                continue
            c = cen_all[f]
            ax = int(np.argmax(np.ptp(c[:, [0, 2]], 0))) * 2       # split along x or z
            cut = np.median(c[:, ax])
            left = f[c[:, ax] <= cut]
            right = f[c[:, ax] > cut]
            if not len(left) or not len(right):
                left, right = f[: len(f) // 2], f[len(f) // 2:]
            todo += [left, right]
        parts.sort(key=lambda f: (cen_all[f][:, 0].mean(), cen_all[f][:, 2].mean()))
        for n, f in enumerate(parts):
            used = verts[np.unique(faces[f])]
            a, b = used.min(0), used.max(0)
            out.append({"name": f"land_{name}_{n:02d}", "material": name, "faces": f,
                        "tris": int(len(f)), "center": ((a + b) / 2).round(4).tolist(),
                        "size": (b - a).round(4).tolist(), **_encode(verts, faces[f], a, b)})
    return out


def build_level(res: dict, max_tris: int = 10000, mat=None, mat_names=("top", "rock", "filler")) -> dict:
    s = res["settings"]
    land, owner, top, lo, v = _grid(res)
    labels, n = _terraces(land, top)
    dist = _interior_distance(labels)
    from scipy import ndimage
    piece_lab, n_pieces = ndimage.label(land)

    # one record per terrace
    terraces = []
    centers = {}
    for t in range(1, n + 1):
        m = labels == t
        area = int(m.sum())
        d = np.where(m, dist, -1)
        i, k = np.unravel_index(int(np.argmax(d)), d.shape)
        c = (float(lo[0] + i * v), float(lo[1] + k * v))
        centers[t] = c
        terraces.append({"id": t, "y": round(float(top[i, k]), 3), "area_m2": round(area * v * v, 2),
                         "center": [round(c[0], 3), round(float(top[i, k]), 3), round(c[1], 3)],
                         "piece": int(piece_lab[i, k]),
                         "stone": bool(res["balls"][owner[i, k]].get("kind") == "filler"),
                         "room": round(float(d[i, k]) * v, 2)})
    byid = {t["id"]: t for t in terraces}

    links = _links(labels, top, lo, v, s["jump"], s["reach"])

    # spawn: roomiest spot on the biggest terrace of the biggest piece
    sizes = np.bincount(piece_lab.ravel())[1:]
    big_piece = int(np.argmax(sizes)) + 1
    spawn_t = max((t for t in terraces if t["piece"] == big_piece), key=lambda t: t["area_m2"])["id"]
    _, reachable = _route(n, links, centers, spawn_t, None)
    # goal: highest reachable terrace (biggest one if several share the top)
    goal_t = max((t for t in terraces if t["id"] in reachable), key=lambda t: (t["y"], t["area_m2"]))["id"]
    path, _ = _route(n, links, centers, spawn_t, goal_t)
    checkpoints = [path[i] for i in range(CHECKPOINT_EVERY, len(path) - 1, CHECKPOINT_EVERY)
                   if not byid[path[i]]["stone"]]

    ymin, ymax = float(np.nanmin(top)), float(np.nanmax(top))
    spots = _spots(labels, top, dist, lo, v, res["seed"], ymin, ymax)
    on_route = set(path)
    for sp in spots:
        sp["on_route"] = sp["terrace"] in on_route

    level = {
        "format": "islandgen-level/1",
        "units": "meters",
        "up": "y",
        "seed": res["seed"],
        "player": {"height": s["player_height"], "jump": s["jump"], "reach": s["reach"]},
        "bounds": {"top_min": round(ymin, 3), "top_max": round(ymax, 3),
                   "lowest": round(float(res["verts"][:, 1].min()), 3) if len(res["verts"]) else 0.0},
        "spawn": {"terrace": spawn_t, "at": byid[spawn_t]["center"]},
        "goal": {"terrace": goal_t, "at": byid[goal_t]["center"]},
        "route": [{"terrace": t, "at": byid[t]["center"]} for t in path],
        "checkpoints": [{"terrace": t, "at": byid[t]["center"]} for t in checkpoints],
        "terraces": terraces,
        "links": [{"a": a, "b": b, "kind": kind, "gap_m": round(d, 3)}
                  for (a, b), (d, kind, _, _) in sorted(links.items())],
        "spots": spots,
        "walk": {"columns": ["x0", "z0", "x1", "z1", "top_y", "bottom_y"],
                 "boxes": _walk_boxes(labels, top, lo, v, s["thickness"])},
        "stats": {"terraces": n, "pieces": int(n_pieces), "links": len(links), "route_len": len(path),
                  "spots": len(spots), "unreachable_terraces": n - len(reachable)},
    }
    if mat is not None and len(res["faces"]):
        level["chunks"] = _chunks(res["verts"], res["faces"], np.asarray(mat), list(mat_names), max_tris)
    return level
