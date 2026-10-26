"""Turn island ring data into triangles. Still engine-agnostic: just numbers."""


def _sub(a, b): return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def _cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def _dot(a, b): return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]


def _normal(a, b, c):
    n = _cross(_sub(b, a), _sub(c, a))
    l = _dot(n, n) ** 0.5 or 1.0
    return (n[0]/l, n[1]/l, n[2]/l)


def build_mesh(island: dict) -> dict:
    """Returns {"vertices": [(x,y,z)], "faces": [{"v": (i,j,k), "material": str}]}.

    Materials: "grass" (top + rim) and "rock" (body).
    """
    verts, faces = [], []

    def add(p):
        verts.append(p)
        return len(verts) - 1

    rings = island["rings"]
    ring_idx = [[add((x, r["y"], z)) for (x, z) in r["points"]] for r in rings]
    n = len(ring_idx[0])

    def tri(i, j, k, mat, outward):
        a, b, c = verts[i], verts[j], verts[k]
        if _dot(_normal(a, b, c), outward) < 0:
            j, k = k, j
        faces.append({"v": (i, j, k), "material": mat})

    # top cap: fan from the center
    cx = sum(p[0] for p in island["top_outline"]) / n
    cz = sum(p[1] for p in island["top_outline"]) / n
    center = add((cx, island["top_y"], cz))
    for i in range(n):
        tri(center, ring_idx[0][i], ring_idx[0][(i+1) % n], "grass", (0, 1, 0))

    # walls between rings
    for r in range(len(ring_idx) - 1):
        mat = "grass" if rings[r]["role"] == "top" else "rock"
        A, B = ring_idx[r], ring_idx[r+1]
        for i in range(n):
            i2 = (i+1) % n
            mid = verts[A[i]]
            out = (mid[0]-cx, 0, mid[2]-cz)
            tri(A[i], A[i2], B[i], mat, out)
            tri(A[i2], B[i2], B[i], mat, out)

    # close the bottom to the tip
    tip = add(tuple(island["tip"]))
    last = ring_idx[-1]
    for i in range(n):
        p = verts[last[i]]
        out = (p[0]-island["tip"][0], -0.5, p[2]-island["tip"][2])
        tri(last[i], last[(i+1) % n], tip, "rock", out)

    return {"vertices": verts, "faces": faces}
