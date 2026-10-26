# IslandGen for Roblox

Loads islandGen exports into a place. No manual mesh import: the client builds the mesh from the
exported data with EditableMesh, and the server builds invisible collision boxes.

## 1. Turn on mesh APIs (once per place)

Game Settings → Security → **Allow Mesh / Image APIs**. Without it you still get a playable level,
just with plain boxes instead of the mesh.

## 2. Bring the module into your project

**With Rojo:** copy `roblox/src` into your project (or point at it), and map it:

```json
"ReplicatedStorage": {
  "IslandGen": { "$path": "path/to/islandGen/roblox/src" },
  "Levels":    { "$path": "levels" }
}
```

**Without Rojo:** `rojo build roblox/default.project.json -o IslandGen.rbxm` and insert the model into
ReplicatedStorage.

## 3. Export a level and add it

```
python -m islandgen --seed 1 --layout 1 --target roblox --name tower1
```

Copy `out/tower1/level.json` and the `out/tower1/chunks/` folder into your project's `levels/tower1/`.
Rojo turns `level.json` into a ModuleScript and each chunk `.txt` into a StringValue:

```
ReplicatedStorage.Levels.tower1.level        (ModuleScript)
ReplicatedStorage.Levels.tower1.chunks.*     (StringValues)
```

(Only `level.json` and `chunks/` are needed. The `.glb` / `.obj` are for other engines or for looking at.)

## 4. Build it

Server script:

```lua
local IslandGen = require(ReplicatedStorage.IslandGen)
local options = { origin = Vector3.new(0, 1, 0) }          -- share this table with the client

local level = IslandGen.build(ReplicatedStorage.Levels.tower1, options)
-- level.spawn  CFrame on the base pad
-- level.goal   Vector3 on the top pad
-- level.route  { Vector3 } pad by pad, bottom to top
-- level.spots  { { position = Vector3, height01 = 0..1, pad = n } }  -> put your collectibles here
-- level.world({x, y, z})  level meters -> world position
```

Client script (every client):

```lua
local ok, why = IslandGen.view(ReplicatedStorage.Levels.tower1, options)
if not ok then warn(why) end
```

Use the **same options table on both sides** (a shared ModuleScript works well), or the mesh won't line
up with the collision.

### Options

| Option | Default | |
|---|---|---|
| `origin` | `0,0,0` | Where the level's (0,0,0) goes, in studs. The tower's base pad centre sits here. |
| `studM` | `0.28` | Meters per stud. |
| `name` / `parent` | folder name / `workspace` | Where the level Model goes. |
| `look` | green / tan / stone / sand | `{ top = {color=, material=}, rock = …, filler = …, sand = … }` |
| `props` | `true` | Build lanterns, rock groups and the torii from the data. |
| `onProp` | none | `function(kind, position, prop, parent)`: return `true` if you placed it yourself. Use it for `"tree"` spots (no default tree) or to swap in your own assets. |
| `flipWinding` | `false` | If the mesh ever renders inside-out. |

## Example place

`roblox/example` is a tiny standalone place: a ground plane, the tower, glowing orbs on the spots.

```
cd roblox/example
rojo serve        # then connect from Studio, or:  rojo build -o IslandGenExample.rbxl
```

## Notes

- Collision is boxes, never the mesh: flat tops, tilted boxes on ramps, one box per stair tread.
- The mesh is client-only (EditableMesh doesn't replicate), so it never collides and costs the server nothing.
- Levels were solved for a default character (WalkSpeed 16, jump about 7.2 studs). If your character
  jumps lower, regenerate with a smaller `--jump` / `--reach`.
