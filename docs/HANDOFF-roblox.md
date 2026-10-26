# islandGen → Roblox handoff

**From:** the islandGen chat (Law). **To:** the main Roblox dev chat.
**Repo:** `D:\Game Dev\Watusi Tools\islandGen` (its own repo; engine-agnostic, no Roblox code inside).

## What it is
A procedural generator for floating land for a **3D platformer**, made from top-down metaballs. You jump
between pieces; there are no ramps or stairs.
- Each ball is a circle seen from above (x, z, radius) that also carries a height. Close balls melt
  together; the merged outline is the land seen from above.
- Height at any spot = the height of the strongest ball there, so merged land steps up in flat terraces.
  Tops are dead flat. Rock hangs underneath.
- Balls sit along irregular, broken, overlapping rings. Bridges form wherever rings pass close.
- **Height resolve:** heights are re-solved so no two touching surfaces differ by more than one jump.
- **Filler:** stepping stones are added so every piece can be reached from the biggest one
  (gap ≤ reach sideways, ≤ one jump up).

## Run it
    pip install -r requirements.txt        # numpy, scikit-image (scipy comes with it)
    python gui/server.py                   # http://127.0.0.1:8765, sliders + live 3D view
Pick an engine and press Export. Output goes to `out/meta_<seed>_<engine>/`.

## Units (important)
- Inside the generator everything is **meters, Y up, right-handed** (the glTF convention).
- Roblox: **1 stud = 0.28 m**. The Roblox export bakes this in.
- Player profile (Roblox defaults, in m): `player_height` 1.4 (≈5 studs), `jump` 2.0 (≈7.2 studs),
  `reach` 4.0 (≈14 studs). If the game changes JumpPower, WalkSpeed or gravity, update these
  and regenerate; the solver re-fits heights and stones to them.

## Export files
| File | What |
|---|---|
| `land_roblox.obj` + `.mtl` | Mesh in **studs**, Y up. Materials: `top`, `rock`, `filler`. |
| `land.glb` | Same mesh in **meters** (glTF spec). Three materials. Passes the glTF validator. |
| `scene.json` | Data: every ball, rings, grid, settings, stats, jump check, unit conversion table. |

**Materials** (one face list each):
- `top`: walkable flat land tops
- `rock`: sides and underside
- `filler`: tops of the stepping stones

**`scene.json` → `balls[]`:** `{x, z, r, h, fr, kind}`, in meters. `kind` is `land` or `filler`.
`r` is the visible radius, `fr` the field radius, `h` the top height.
These balls are the true source: any engine can rebuild the land from them.

## Current state (Law's defaults, seed 3)
- About 21k triangles, 601 balls, 31 height levels.
- Biggest step 2.0 m; 0 m of edges too tall to jump; 12 pieces; 80 stones; 0 unreachable.
- Ground covers about 110 × 110 m and rises about 100 m.
- Generating takes about 0.5–2 s; the stone placement is the slow part (optimization is open).
- Look: monochrome, gray and black only. Exported colors are placeholders.

## Roblox loader (packaged, 2026-10-25)
- Lives in this repo: `roblox/` (Rojo-ready module `IslandGen` + an example place). See `roblox/README.md`.
- Server: `IslandGen.build(levelFolder, options)` -> invisible collision boxes (flat tops, tilted ramp boxes,
  stair treads) + props (lanterns, rock groups, torii), and a handle with spawn / goal / route / spots.
- Client: `IslandGen.view(levelFolder, options)` -> mesh from `chunks/` via EditableMesh
  (Game Settings > Security > Allow Mesh / Image APIs). Falls back to showing the boxes.
- Game-specific things (collectibles, dust piles) stay in the game: it reads `level.spots`.
- Rub a Mud Ball still has its own copy of this loader (src/server/Level.luau + src/client/LevelView.luau).

## Layouts
- `layout = 1` tower: layered pads (they can stack), ramps / stone stairs / hop stones, dressing spots.
  This is what Rub a Mud Ball uses (tower rising out of the garden pond).
- `layout = 0` rings: one big top-down field, flat terraces, stepping stones. Works with the same loader.
- Reach: a default character clears ~2.4 m flat. Tower hops are spaced inside that; for rings use `reach` ≈ 3.4.

## Decisions already made (don't relitigate)
- Engine-agnostic core. Roblox code lives only in `roblox/`, outside `islandgen/`.
- Top-down 2D metaballs with flat tops. Not 3D blobs, not a spiral ribbon, not stairs.
- Platformer: every height step must be jumpable, and every piece reachable.
- Meters inside; each engine's conversion happens at export.

Full history: `DEVLOG.md` in the repo.
