# islandGen dev journal

## 2026-10-24 / 25 — project start

**Goal:** an engine-agnostic procedural floating-land generator. First target: a 3D Roblox platformer.
Reference: a low-poly "Japanese zen garden" floating-garden concept piece.

**Ground rules**
- The generator never knows about any engine. It outputs data + files; engines only read files.
- Python is the source of truth. The GUI only draws what Python returns.
- Optimized from the start: live stats (tris, cells, ms) in the GUI; `voxel` is the main cost dial.

**How we got here (what didn't work)**
1. Single noisy blob islands (circle + noise, stacked shrinking rings underneath). Fine, but just blobs.
2. Blobs placed along a spiral. Read as a scattered cluster.
3. One continuous spiral "ribbon" land bridge. Wrong: the reference isn't a literal spiral.
4. Full 3D metaballs (platforms + chains of balls as bridges). Wrong: read as old islands tied together
   with rope, and it was a stairway, not a platformer.

**What the system is now: top-down metaballs** (`islandgen/meta.py`)
- Each ball is a 2D circle seen from above (x, z, radius) that also carries a height.
- Fields add up on a flat grid; land is wherever the total > 0.5. That's the top-down silhouette.
- Height at each spot = the height of the strongest ball there. Merged land with different heights
  makes clean terrace steps you jump up. Tops are dead flat.
- Rock hangs underneath, deeper in the middle, thin at the edges.
- Balls are laid along irregular, broken, concentric-ish rings. Where rings pass close they merge into
  natural bridges. `shuffle` breaks the small-to-big ring order so rings cross and overlap.
- Mesh: the 2D field + top/bottom heights become a 3D volume, then marching cubes (scikit-image).

**GUI** (`python gui/server.py`)
- Strictly two colors: gray + black. Unlit.
- Materials shown as data: top (walkable) = solid black, rock (sides + underside) = gray with black edges.
  Legend shows triangle count per material.
- Sliders are generated from `PARAMS` in `meta.py`.

**Exports** (`out/meta_<seed>/`)
- `land.obj` + `.mtl`: one mesh, two materials (top / rock).
- `scene.json`: every ball (x, z, r, h), the rings, the grid, settings and stats.
  The ball list is the engine-agnostic source; any engine can rebuild the land from it.

**Defaults locked in by Law (2026-10-25)**
rings 11 · first 14 · gap 15 · wobble 0.6 · completion 0.34 · pieces 3 · drift 0.08 · shuffle 1 ·
size 6.5 · size_var 0.77 · beads 0.75 · blobs 0.32 · tier 41 · lift 0 · piece_lift 2 · step 8.5 ·
terrace 114 · thickness 6.5 · belly 0.4 · voxel 4.5
(seed 3: ~19.6k tris, ~0.5 s per rebuild)

## 2026-10-25 — units for every engine

**Why:** Law wants to use islandGen in Blender, Unity, Unreal and Roblox. They disagree on scale and up axis:
Blender m / Z-up · Unity m / Y-up · Unreal cm / Z-up · Roblox stud (0.28 m) / Y-up.

**Decision:** the generator works in **meters, Y up, right-handed** (the glTF convention). Engines only
differ at export. Defaults converted from studs (x0.28).

**Exports** (`out/meta_<seed>_<engine>/`)
- `land.glb`: meters, Y up by spec; every engine's glTF importer converts it. Two materials: top, rock.
  Passes the glTF validator with no errors or warnings.
- `land_<engine>.obj`: same mesh with that engine's scale baked in (Unreal x100, Roblox /0.28).
- `scene.json`: meters, plus a conversion table per engine.
- `islandgen/units.py` holds the table.

**Player profile** (new slider group): `player_height` (1.4 m) and `jump` (2.0 m), Roblox defaults.
The generator walks the top heightmap and reports: number of levels, biggest step, and meters of edge
taller than the jump. A black box at player height sits in the view for scale.
With the current defaults (seed 3): 18 levels, biggest step 38.4 m, ~541 m of unjumpable edges.

## 2026-10-25 — resolve heights to the jump

**Goal:** keep Law's look exactly as seen from above, but make heights jumpable for the current player profile.

**How** (`resolve` in the Player group, on by default; `resolve_heights` in meta.py)
- Read the exact contacts off the grid: neighbouring land cells owned by different balls = touching balls.
  (A first try guessed contacts from ball distance; it missed many and made things worse.)
- Heights count in whole steps; step is capped at the jump (2.4 m step > 2.0 m jump, so it snaps to 2.0).
- Grow two envelopes over the contact graph: highest-allowed and lowest-allowed. Each is jumpable
  everywhere; their average is too, and it keeps the original ups and downs.
- Seed 3: 0 m of unjumpable edges (was 541 m), biggest step 2.0 m, heights 0-104 m (was 0-115 m),
  31 levels. Runs in ~30 ms.

**What it doesn't do yet:** pieces that don't touch keep their own heights, so separate floating pieces can
sit far above/below each other. Crossing gaps sideways (horizontal jump distance) is the next check.

## 2026-10-25 — filler: stepping stones

**Goal:** every piece of land reachable by jumping, without touching Law's layout.

**How** (`filler` group; `add_filler` + `reach_check` in meta.py)
- New player value `reach`: how far you can jump across a gap (default 4.0 m; Roblox ~4.5).
- Label separate pieces of land. For each pair, find the closest edge points.
- Start from the biggest piece; repeatedly connect the cheapest unreached piece with a straight line of
  small stones. Enough hops that none is longer than reach x `stone_gap` or taller than one jump.
- Stone-to-stone hops are fed into the height resolver as constraints, so resolving can't break them.
  (Without that, seed 3 still had 9 unreachable pieces.) Repeats up to 6 times.
- Final check walks the pieces (gap <= reach, height <= jump) from the biggest piece.
- Seeds 3, 7, 11, 21, 42, 99: 0 unreachable, 0 m unjumpable edges.

**Data:** new material **filler** (stone tops). In glb/obj/scene.json; balls carry `kind: land|filler`.
GUI shows filler tops hatched (gray fill + every edge drawn), still two colors.

**Side effect:** resolving the hop links pulls connected pieces' heights toward each other, so the whole
thing gets more compact vertically than without filler.

**Open / not decided**
- Roblox side: imported mesh vs writing the field into Roblox Terrain. Not decided.
- Stairs: parked.
- Jumpability: current defaults are far over a 2 m jump (see jump check). Needs a design pass.
- OBJ axis import in Unreal untested; prefer land.glb there.
- Older code (island.py, ribbon.py, layout.py, scene.py, tools/preview.py) is unused by the GUI.

## 2026-10-25 — Level layer + straight into Roblox
- New `islandgen/level.py` (engine-agnostic, meters): `level.json` on every export with terraces, walk boxes
  (flat tops as rectangles = cheap exact collision), links (walk/hop), spawn, goal (highest reachable),
  main route, checkpoints, spots (flat, off edges, `height01`), mesh chunks.
- Targets with `max_tris` (Roblox 10k) split the mesh: one chunk per material, halved until it fits.
  Each chunk also written as compact geometry `chunks/<name>.txt` (base64 uint16: quantized verts + tris),
  so an engine can BUILD the mesh from data. Roblox does that with EditableMesh — no manual import.
- Loader lives in RubAMudBall (`src/server/Level.luau` + `src/client/LevelView.luau`), outside islandgen/.
- Reach: default Roblox character clears ~2.4 m flat; `reach` is measured edge cell to edge cell (~1 voxel
  slack), so ~3.4. Seed 5 at reach 3.4 → `out/meta_5_roblox_play/` (stones bridge it into one piece, 0 unreachable).
- Mesh vs Terrain: decided — mesh for looks, walk boxes for collision.

## 2026-10-25 — Pad mesher + tower layout
- New `islandgen/pads.py` (look → `mesher` = 1, default): no marching cubes. Per flat terrace: trace its outline
  (contour of the softened mask), simplify to a few corners (`facet`, m) = faceted low-poly edge, then a flat cap,
  a top-coloured `lip`, and walls that drop only as far as the ground beside them (a step meets the lower top;
  open air gets the full `thickness` slab). Each terrace hangs one faceted rock belly (`belly_rings` facets),
  inset toward its middle and deepest where it's widest. ~3x fewer triangles than marching cubes, no grid stairs.
- New `tower` layout (`layout` = 1): `pads` up a tapering helix (`turns`, `radius`, `taper`, `climb`, `pad_size`),
  each pad a cluster of fat balls on one level, joined by stair paths (`paths` chance) stepping by `step`.
- `spiral` (rings layout): height climbs as you go round; rings continue where the last one ended.
- Limit found: top-down 2D can't stack land over land. A helix over ~1 turn overlaps itself in plan view, the
  pads merge and the solver flattens the climb. Real stacking needs layers (separate 2D grids per height band).
- Needs `pip install shapely mapbox_earcut` (added to requirements).

## 2026-10-25 — Tower layout (layered), ramps/stairs/hops, level v2
- `islandgen/tower.py` (`layout = 1`): each pad is its own flat layer with its own small metaball field, so pads
  stack over each other (fixes the 2D limit for towers). Links between consecutive pads: grass ramp (gentle),
  stone stairs (slope ≤ 1), or hop stones (spaced within reach/jump). Neighbours always keep a gap; the first pad
  stays low so the way in from the base is easy. Heights snap to 2 × `stair_rise`.
- Look: thin `slab` + `tower_belly` rock per pad, sand patches (material 3 "sand"), dressing spots
  (rocks / lantern / tree / torii on the top pad). Climb check: 0 unreachable over 40 seeds.
- Writes `level.json` v2 directly: spawn (base), goal (top), route, links, spots, props, collision as oriented
  boxes `{cx,cy,cz, sx,sy,sz, rx,ry,rz, ux,uy,uz}`. GUI shows sand as gray.
- Note: this mode deliberately adds paths and stairs (agreed with Law), unlike the ring layout.

## 2026-10-25 — Packaged for GitHub
- `roblox/`: the Roblox loader as a reusable module (`IslandGen.build` server, `IslandGen.view` client), Rojo-ready,
  plus `roblox/example/` (standalone place with the tower and orbs on the spots). Both Rojo projects build.
- CLI is the real generator now: `python -m islandgen --seed 1 --layout 1 --target roblox [--name x] [--list]`.
  Public API: `from islandgen import generate, write_meta, PARAMS`.
- Old generator moved to `islandgen/legacy/` (incl. the old preview). `pyproject.toml` (`pip install -e .`),
  requirements now list scipy explicitly, README rewritten for a teammate.
- GUI opens on the tower now (`layout` default 1) and only shows the sliders the current layout reads
  (`meta.USED_BY`, served at `/used`); switching layout rebuilds the sliders and reframes the camera.
  Tower stats line: pads, ramps, stairs, hops, unreachable.
