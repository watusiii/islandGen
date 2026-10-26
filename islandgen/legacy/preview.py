"""Old ring/ribbon generator preview: python -m islandgen.legacy.preview 1 2 3 4"""
import sys, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from islandgen.legacy.island import generate_island
from islandgen.mesh import build_mesh, _normal
from islandgen.export import COLORS

seeds = [int(s) for s in sys.argv[1:]] or [1, 2, 3, 4]
fig = plt.figure(figsize=(4 * len(seeds), 4.5), facecolor="#efece6")
light = (0.4, 0.8, 0.3)
for n, seed in enumerate(seeds):
    mesh = build_mesh(generate_island(seed))
    V = mesh["vertices"]
    polys, cols = [], []
    for f in mesh["faces"]:
        tri = [V[i] for i in f["v"]]
        nx, ny, nz = _normal(*tri)
        lit = 0.45 + 0.55 * max(0, nx*light[0] + ny*light[1] + nz*light[2])
        r, g, b = COLORS[f["material"]]
        polys.append([(x, z, y) for (x, y, z) in tri])  # matplotlib is z-up
        cols.append((r*lit, g*lit, b*lit))
    ax = fig.add_subplot(1, len(seeds), n + 1, projection="3d")
    ax.add_collection3d(Poly3DCollection(polys, facecolors=cols, edgecolor=cols))
    ax.set_xlim(-28, 28); ax.set_ylim(-28, 28); ax.set_zlim(-40, 8)
    ax.set_box_aspect((1, 1, 0.86)); ax.view_init(22, 35); ax.axis("off")
    ax.set_title(f"seed {seed}")
os.makedirs("out", exist_ok=True)
plt.savefig("out/preview.png", dpi=90, bbox_inches="tight")
print("out/preview.png")
