-- Client side: rebuilds the land mesh from islandGen chunks with EditableMesh.
--
-- Chunk format (islandgen/level.py _encode): base64 of little-endian uint16s.
--   verts: x,y,z quantized over the chunk box (meters = origin + q * step)
--   then triangles: 3 vertex indices each
-- Each triangle gets its own vertices = flat, faceted shading.

local AssetService = game:GetService("AssetService")

local Base64 = require(script.Parent.Base64)

local View = {}

local keep = {} -- EditableMeshes stay referenced while their MeshParts live

local function buildChunk(chunk, text: string, o, parent: Instance): MeshPart
	local K = 1 / o.studM
	local buf = Base64.decode(text)
	local origin = Vector3.new(chunk.origin[1], chunk.origin[2], chunk.origin[3])
	local step = Vector3.new(chunk.step[1], chunk.step[2], chunk.step[3])
	local center = Vector3.new(chunk.center[1], chunk.center[2], chunk.center[3])

	local P = table.create(chunk.verts)
	for i = 0, chunk.verts - 1 do
		local q = Vector3.new(buffer.readu16(buf, i * 6), buffer.readu16(buf, i * 6 + 2), buffer.readu16(buf, i * 6 + 4))
		P[i] = (origin + q * step - center) * K
	end

	local em = AssetService:CreateEditableMesh({})
	local triStart = chunk.verts * 6
	for t = 0, chunk.tris - 1 do
		local at = triStart + t * 6
		local i1, i2, i3 = buffer.readu16(buf, at), buffer.readu16(buf, at + 2), buffer.readu16(buf, at + 4)
		if o.flipWinding then
			i2, i3 = i3, i2
		end
		em:AddTriangle(em:AddVertex(P[i1]), em:AddVertex(P[i2]), em:AddVertex(P[i3]))
	end

	local part = AssetService:CreateMeshPartAsync(Content.fromObject(em))
	table.insert(keep, em)
	part.Name = chunk.name
	part.Anchored = true
	part.CanCollide = false
	part.CanTouch = false
	part.CanQuery = false
	part.CFrame = CFrame.new(o.origin + center * K)
	local look = o.look[chunk.material] or o.look.rock
	part.Color = look.color
	part.Material = look.material
	part.Parent = parent
	return part
end

local function showBoxes(model: Instance)
	local walk = model:FindFirstChild("Walk")
	if walk then
		for _, p in walk:GetChildren() do
			if p:IsA("BasePart") then
				p.Transparency = 0
				p.CastShadow = true
			end
		end
	end
end

function View.build(data, chunks: Instance?, o): (boolean, string?)
	local model = o.parent:WaitForChild(o.name, 60)
	if not model then
		return false, "no level model '" .. o.name .. "' (did the server call IslandGen.build?)"
	end
	if not data.chunks or not chunks then
		showBoxes(model)
		return false, "level has no mesh chunks (export with a target that chunks, e.g. roblox)"
	end
	local land = Instance.new("Model")
	land.Name = "Land"
	land.Parent = model
	for _, chunk in data.chunks do
		local value = chunks:WaitForChild(chunk.name, 10) :: StringValue?
		local ok, err = pcall(function()
			assert(value, "missing chunk " .. chunk.name)
			buildChunk(chunk, value.Value, o, land)
		end)
		if not ok then
			land:Destroy()
			showBoxes(model)
			return false, tostring(err) .. " (EditableMesh needs Game Settings > Security > Allow Mesh / Image APIs)"
		end
		task.wait()
	end
	return true
end

return View
