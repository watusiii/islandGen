-- Server side: collision boxes + props from an islandGen level, and a handle for game code.
-- Collision never uses the mesh: flat tops, ramps and stairs are rebuilt as invisible boxes.

local Props = require(script.Parent.Props)

local Loader = {}

local function box(parent: Instance, size: Vector3, cf: CFrame, color: Color3, material: Enum.Material)
	local p = Instance.new("Part")
	p.Name = "Walk"
	p.Size = size
	p.CFrame = cf
	p.Color = color
	p.Material = material
	p.Anchored = true
	p.CastShadow = false
	p.Transparency = 1 -- the client's View shows these if the mesh can't be built
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	p.Parent = parent
	return p
end

function Loader.build(data, o)
	local K = 1 / o.studM
	local function world(p): Vector3
		return o.origin + Vector3.new(p[1], p[2], p[3]) * K
	end

	local old = o.parent:FindFirstChild(o.name)
	if old then
		old:Destroy()
	end
	local model = Instance.new("Model")
	model.Name = o.name
	model:SetAttribute("IslandGen", data.format)
	model:SetAttribute("Origin", o.origin)
	model:SetAttribute("StudM", o.studM)

	-- collision
	local walk = Instance.new("Folder")
	walk.Name = "Walk"
	walk.Parent = model
	local look = o.look.top
	if data.walk.format == "obox" then
		-- {cx,cy,cz, sx,sy,sz, rx,ry,rz, ux,uy,uz}: centre + size (m), right + up vectors
		for _, b in data.walk.boxes do
			local cf = CFrame.fromMatrix(world({ b[1], b[2], b[3] }), Vector3.new(b[7], b[8], b[9]), Vector3.new(b[10], b[11], b[12]))
			box(walk, Vector3.new(b[4], b[5], b[6]) * K, cf, look.color, look.material)
		end
	else
		-- level v1: {x0, z0, x1, z1, top_y, bottom_y}, axis-aligned
		for _, b in data.walk.boxes do
			local x0, z0, x1, z1, top, bottom = b[1], b[2], b[3], b[4], b[5], b[6]
			local cf = CFrame.new(world({ (x0 + x1) / 2, (top + bottom) / 2, (z0 + z1) / 2 }))
			box(walk, Vector3.new(x1 - x0, top - bottom, z1 - z0) * K, cf, look.color, look.material)
		end
	end

	-- props
	if o.props and data.props then
		local folder = Instance.new("Folder")
		folder.Name = "Props"
		folder.Parent = model
		for _, pr in data.props do
			local at = world(pr.at)
			if o.onProp and o.onProp(pr.kind, at, pr, folder) then
				continue
			end
			if pr.kind == "lantern" then
				Props.lantern(folder, at)
			elseif pr.kind == "rocks" then
				Props.rocks(folder, at, (pr.size or 0.5) * K)
			elseif pr.kind == "torii" then
				Props.torii(folder, at, Vector3.new(pr.face[1], pr.face[2], pr.face[3]))
			end
		end
	end
	model.Parent = o.parent

	-- handle for game code: everything in world space
	local spots = {}
	for i, sp in data.spots or {} do
		spots[i] = { position = world({ sp.x, sp.y, sp.z }), height01 = sp.height01, pad = sp.pad or sp.terrace }
	end
	local route = {}
	for i, r in data.route or {} do
		route[i] = world(r.at)
	end
	return {
		model = model,
		data = data,
		world = world, -- level meters {x, y, z} -> world Vector3
		spawn = data.spawn and CFrame.new(world(data.spawn.at) + Vector3.new(0, 4, 0)) or nil,
		goal = data.goal and world(data.goal.at) or nil,
		route = route,
		spots = spots,
		walk = walk,
	}
end

return Loader
