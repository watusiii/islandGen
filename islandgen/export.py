"""Writers. The only place that knows about file formats."""
import json
from .mesh import _normal

COLORS = {"grass": (0.68, 0.68, 0.68), "rock": (0.6, 0.6, 0.6),
          "top": (0.0, 0.0, 0.0), "filler": (0.6, 0.6, 0.6), "sand": (0.85, 0.85, 0.85)}  # monochrome; "top" = walkable, "rock" = sides + underside


def write_obj(mesh: dict, path: str, name: str = "island"):
    """OBJ with one face normal per triangle = flat low-poly shading."""
    mtl_path = path[:-4] + ".mtl"
    mtl_name = mtl_path.replace("\\", "/").split("/")[-1]
    with open(mtl_path, "w") as m:
        for mat, (r, g, b) in COLORS.items():
            m.write(f"newmtl {mat}\nKd {r:.3f} {g:.3f} {b:.3f}\n\n")

    V = mesh["vertices"]
    with open(path, "w") as f:
        f.write(f"# islandGen\nmtllib {mtl_name}\no {name}\n")
        for (x, y, z) in V:
            f.write(f"v {x:.4f} {y:.4f} {z:.4f}\n")
        for face in mesh["faces"]:
            nx, ny, nz = _normal(*(V[i] for i in face["v"]))
            f.write(f"vn {nx:.4f} {ny:.4f} {nz:.4f}\n")
        current = None
        for n, face in enumerate(mesh["faces"], start=1):
            if face["material"] != current:
                current = face["material"]
                f.write(f"usemtl {current}\n")
            a, b, c = (i + 1 for i in face["v"])
            f.write(f"f {a}//{n} {b}//{n} {c}//{n}\n")


def write_chunked_obj(verts, faces, chunks, path):
    """One OBJ object per chunk, each with its own vertices, so an importer makes one mesh each
    (needed where an engine caps triangles per mesh). Flat normals, one material per chunk."""
    mtl_path = path[:-4] + ".mtl"
    mtl_name = mtl_path.replace("\\", "/").split("/")[-1]
    with open(mtl_path, "w") as m:
        for mat, (r, g, b) in COLORS.items():
            m.write(f"newmtl {mat}\nKd {r:.3f} {g:.3f} {b:.3f}\n\n")
    with open(path, "w") as f:
        f.write(f"# islandGen chunked\nmtllib {mtl_name}\n")
        base_v, base_n = 0, 0
        for c in chunks:
            fs = faces[c["faces"]]
            used, inv = __import__("numpy").unique(fs, return_inverse=True)
            inv = inv.reshape(fs.shape)
            f.write(f"o {c['name']}\nusemtl {c['material']}\n")
            for (x, y, z) in verts[used].tolist():
                f.write(f"v {x:.4f} {y:.4f} {z:.4f}\n")
            for a, b, cc in fs.tolist():
                nx, ny, nz = _normal(verts[a], verts[b], verts[cc])
                f.write(f"vn {nx:.4f} {ny:.4f} {nz:.4f}\n")
            for n, (a, b, cc) in enumerate(inv.tolist(), start=1):
                vn = base_n + n
                f.write(f"f {base_v + a + 1}//{vn} {base_v + b + 1}//{vn} {base_v + cc + 1}//{vn}\n")
            base_v += len(used)
            base_n += len(fs)


def write_json(data: dict, path: str):
    """The engine-agnostic contract. Any engine loader reads this."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def write_scene(scene: dict, folder: str) -> str:
    """One OBJ per island (each becomes its own part in an engine) + scene.json."""
    import os
    os.makedirs(folder, exist_ok=True)
    entries = []
    for isl in scene["islands"]:
        write_obj(isl["mesh"], os.path.join(folder, isl["id"] + ".obj"), isl["id"])
        d = isl["island"]
        entries.append({
            "id": isl["id"],
            "seed": d["seed"],
            "position": [round(v, 4) for v in isl["position"]],
            "mesh": isl["id"] + ".obj",
            "top_y": d["top_y"],
            "bottom_y": d["bottom_y"],
            "top_outline": [[round(x, 4), round(z, 4)] for x, z in d["top_outline"]],
        })
    write_json({
        "format": "islandgen/1",
        "units": "studs",
        "up": "y",
        "seed": scene["seed"],
        "settings": scene["settings"],
        "islands": entries,
    }, os.path.join(folder, "scene.json"))
    return folder


def face_materials(res):
    """0 = top (walkable land), 1 = rock (sides + underside), 2 = filler (stepping-stone tops), 3 = sand."""
    import numpy as np
    if "mat" in res:
        return np.asarray(res["mat"])
    mat = np.where(res["top"], 0, 1)
    mat = np.where(res.get("filler_face", np.zeros_like(res["top"])), 2, mat)
    return mat


MAT_NAMES = ["top", "rock", "filler", "sand"]


def write_glb(verts, faces, mat, path):
    """Binary glTF. Meters, Y up by spec, so every engine's importer converts it correctly.
    Two primitives sharing one vertex buffer: material 0 "top" (walkable), 1 "rock"."""
    import struct
    import numpy as np
    pos = np.asarray(verts, dtype=np.float32)
    f = np.asarray(faces, dtype=np.uint32)
    mat = np.asarray(mat)
    parts = [f[mat == i].ravel() for i in range(len(MAT_NAMES))]
    blobs, views, accs = [], [], []
    off = 0

    def add(data, target):
        nonlocal off
        b = data.tobytes()
        b += b"\0" * ((4 - len(b) % 4) % 4)
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(data.tobytes()), "target": target})
        blobs.append(b)
        off += len(b)
        return len(views) - 1

    v_pos = add(pos, 34962)
    accs.append({"bufferView": v_pos, "componentType": 5126, "count": len(pos), "type": "VEC3",
                 "min": pos.min(0).tolist(), "max": pos.max(0).tolist()})
    prims = []
    for mat, idx in enumerate(parts):
        if not len(idx):
            continue
        v = add(idx, 34963)
        accs.append({"bufferView": v, "componentType": 5125, "count": len(idx), "type": "SCALAR"})
        prims.append({"attributes": {"POSITION": 0}, "indices": len(accs) - 1, "material": mat})
    gltf = {
        "asset": {"version": "2.0", "generator": "islandGen"},
        "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0, "name": "land"}],
        "meshes": [{"name": "land", "primitives": prims}],
        "materials": [{"name": n, "pbrMetallicRoughness": {"baseColorFactor": [*COLORS[n], 1],
                       "metallicFactor": 0, "roughnessFactor": 1}} for n in MAT_NAMES],
        "accessors": accs, "bufferViews": views, "buffers": [{"byteLength": off}],
    }
    j = json.dumps(gltf, separators=(",", ":")).encode()
    j += b" " * ((4 - len(j) % 4) % 4)
    binary = b"".join(blobs)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(j) + 8 + len(binary)))
        fh.write(struct.pack("<II", len(j), 0x4E4F534A) + j)
        fh.write(struct.pack("<II", len(binary), 0x004E4942) + binary)


def write_meta(res: dict, folder: str, target: str = "unity") -> str:
    """Writes, all from the same data:
      land.glb          meters, Y up (glTF spec) -- best for every engine
      land_<target>.obj OBJ with that engine's scale baked in
      scene.json        balls, rings, grid, settings, player check -- in meters
      level.json        the level layer (see level.py): walk boxes, spawn, route, spots, chunks
    """
    import os
    import numpy as np
    from .units import TARGETS, STUD
    os.makedirs(folder, exist_ok=True)
    verts, faces = res["verts"], res["faces"]
    mat = face_materials(res)
    write_glb(verts, faces, mat, os.path.join(folder, "land.glb"))
    k = TARGETS[target]["scale"]
    mesh = {
        "vertices": [tuple(v) for v in (verts * k).tolist()],
        "faces": [{"v": tuple(f), "material": MAT_NAMES[m]}
                  for f, m in sorted(zip(faces.tolist(), mat.tolist()), key=lambda p: p[1])],
    }
    max_tris = TARGETS[target].get("max_tris")
    if max_tris:
        # engine caps triangles per mesh: level layer splits the mesh into chunks, one object each
        from .level import build_level, _chunks
        if "level" in res:                       # the tower layout brings its own level
            level = dict(res["level"])
            level["chunks"] = _chunks(res["verts"], res["faces"], np.asarray(mat), list(MAT_NAMES), max_tris)
        else:
            level = build_level(res, max_tris=max_tris, mat=mat, mat_names=MAT_NAMES)
        write_chunked_obj(verts * k, faces, level["chunks"], os.path.join(folder, f"land_{target}.obj"))
        os.makedirs(os.path.join(folder, "chunks"), exist_ok=True)
        for c in level["chunks"]:
            del c["faces"]
            with open(os.path.join(folder, "chunks", c["name"] + ".txt"), "w") as fh:
                fh.write(c.pop("data"))            # base64 geometry, see level._encode
            c["file"] = "chunks/" + c["name"] + ".txt"
    else:
        from .level import build_level
        level = dict(res["level"]) if "level" in res else build_level(res)
        write_obj(mesh, os.path.join(folder, f"land_{target}.obj"), "land")
    write_json(level, os.path.join(folder, "level.json"))
    write_json({
        "format": "islandgen-meta/2",
        "units": "meters",
        "up": "y",
        "handedness": "right",
        "conversions": {**{t: {"multiply_by": v["scale"], "unit": v["unit"]} for t, v in TARGETS.items()},
                        "note": f"1 Roblox stud = {STUD} m"},
        "seed": res["seed"],
        "settings": res["settings"],
        "threshold": 0.5,
        "kernel": "2D top-down: field = sum (1 - q)^3, q = ((x-bx)^2 + (z-bz)^2) / fr^2; land where field > threshold; top height = height of the strongest ball at that spot",
        "grid": res["grid"],
        "rings": res["rings"],
        "balls": [{**{k2: round(b[k2], 4) for k2 in ("x", "z", "r", "h", "fr")},
                   "kind": b.get("kind", "land")} for b in res["balls"]],
        "jump_check": res["jump"],
        "materials": {"top": "walkable flat tops", "rock": "sides + underside",
                      "filler": "tops of stepping stones added so every piece is reachable"},
        "files": {"glb": "land.glb", "obj": f"land_{target}.obj", "level": "level.json"},
        "stats": res["stats"],
    }, os.path.join(folder, "scene.json"))
    return folder
