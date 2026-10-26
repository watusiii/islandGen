--[[
	IslandGen for Roblox: loads islandGen exports (level.json + chunks/) into a place.

	Data (put the exported folder somewhere both sides can see, e.g. ReplicatedStorage.Levels.<name>):
		<name>/level        ModuleScript  (level.json, Rojo turns .json into a ModuleScript)
		<name>/chunks/<x>   StringValue   (chunks/*.txt, base64 geometry)

	Server:
		local level = IslandGen.build(levelFolder, options)
		-> invisible collision boxes + props, and a handle with spawn / goal / route / spots in world space

	Client (every client, because EditableMesh doesn't replicate):
		IslandGen.view(levelFolder, options)
		-> builds the land mesh from the chunks. If mesh APIs are off, shows the collision boxes instead.

	The mesh needs: Game Settings > Security > "Allow Mesh / Image APIs".

	options (pass the same table on both sides; every field is optional):
		origin      Vector3   where the level's (0,0,0) goes, in studs          (default 0,0,0)
		studM       number    meters per stud                                    (default 0.28)
		name        string    name of the Model in workspace                     (default levelFolder.Name)
		parent      Instance  where to put it                                    (default workspace)
		look        table     { top = {color, material}, rock = ..., filler = ..., sand = ... }
		props       boolean   build lanterns / rocks / torii from the data        (default true)
		onProp      function(kind, position, prop, parent) -> true if you placed it yourself
		            (use it for "tree" spots, or to swap in your own lantern/rock assets)
		flipWinding boolean   if the mesh renders inside-out                      (default false)
]]

local Loader = require(script.Loader)
local View = require(script.View)

local IslandGen = {}

IslandGen.DEFAULT_LOOK = {
	top = { color = Color3.fromRGB(127, 176, 78), material = Enum.Material.SmoothPlastic },
	rock = { color = Color3.fromRGB(201, 162, 107), material = Enum.Material.SmoothPlastic },
	filler = { color = Color3.fromRGB(176, 170, 158), material = Enum.Material.SmoothPlastic },
	sand = { color = Color3.fromRGB(233, 224, 204), material = Enum.Material.SmoothPlastic },
}

local function resolve(levelFolder: Instance, options)
	options = options or {}
	local look = table.clone(IslandGen.DEFAULT_LOOK)
	for k, v in options.look or {} do
		look[k] = v
	end
	return {
		origin = options.origin or Vector3.zero,
		studM = options.studM or 0.28,
		name = options.name or levelFolder.Name,
		parent = options.parent or workspace,
		look = look,
		props = options.props ~= false,
		onProp = options.onProp,
		flipWinding = options.flipWinding == true,
	}
end

-- Reads the level data table (the level.json module).
function IslandGen.data(levelFolder: Instance)
	local module = levelFolder:WaitForChild("level", 10)
	assert(module and module:IsA("ModuleScript"), "IslandGen: no 'level' ModuleScript in " .. levelFolder:GetFullName())
	return require(module)
end

-- Server: collision + props. Returns a level handle (see Loader.build).
function IslandGen.build(levelFolder: Instance, options)
	return Loader.build(IslandGen.data(levelFolder), resolve(levelFolder, options))
end

-- Client: the land mesh. Returns true when the mesh is up, false (+ reason) when it fell back to boxes.
function IslandGen.view(levelFolder: Instance, options)
	local o = resolve(levelFolder, options)
	return View.build(IslandGen.data(levelFolder), levelFolder:WaitForChild("chunks", 10), o)
end

return IslandGen
