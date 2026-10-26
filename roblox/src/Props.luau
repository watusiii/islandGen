-- Simple part-built dressing for islandGen prop spots: lantern, rocks, torii.
-- "tree" has no default (prim trees look bad): pass options.onProp to place your own asset.
local Props = {}

local C = {
	stone = Color3.fromRGB(150, 146, 138),
	rock = Color3.fromRGB(128, 124, 118),
	moss = Color3.fromRGB(96, 128, 70),
	paper = Color3.fromRGB(244, 236, 214),
	vermilion = Color3.fromRGB(200, 69, 44),
	darkWood = Color3.fromRGB(84, 60, 42),
}

local function part(parent: Instance, name: string, size: Vector3, cf: CFrame, color: Color3, material: Enum.Material, collide: boolean): Part
	local p = Instance.new("Part")
	p.Name = name
	p.Size = size
	p.CFrame = cf
	p.Color = color
	p.Material = material
	p.Anchored = true
	p.CanCollide = collide
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	p.Parent = parent
	return p
end

function Props.lantern(parent: Instance, at: Vector3, scale: number?)
	local s = scale or 0.8
	local function p(name, size, y, color, material)
		return part(parent, name, size * s, CFrame.new(at + Vector3.new(0, y * s, 0)), color, material, false)
	end
	p("LanternBase", Vector3.new(1.6, 0.6, 1.6), 0.3, C.stone, Enum.Material.Slate)
	p("LanternPost", Vector3.new(0.7, 2.4, 0.7), 1.8, C.stone, Enum.Material.Slate)
	local box = p("LanternLight", Vector3.new(1.3, 1.1, 1.3), 3.55, C.paper, Enum.Material.SmoothPlastic)
	box.Transparency = 0.15
	local light = Instance.new("PointLight")
	light.Color = Color3.fromRGB(255, 214, 160)
	light.Range = 14
	light.Brightness = 1.2
	light.Parent = box
	p("LanternCap", Vector3.new(2, 0.4, 2), 4.3, C.stone, Enum.Material.Slate)
end

function Props.rocks(parent: Instance, at: Vector3, size: number)
	local rng = Random.new(math.floor(at.X * 13 + at.Z * 7))
	for i = 1, 3 do
		local h = size * rng:NextNumber(0.6, 1.1) * (i == 1 and 1.5 or 0.8)
		local w = size * rng:NextNumber(0.6, 1)
		local off = Vector3.new(rng:NextNumber(-0.8, 0.8) * size * (i - 1), h / 2 - 0.2, rng:NextNumber(-0.8, 0.8) * size * (i - 1))
		local cf = CFrame.new(at + off) * CFrame.Angles(math.rad(rng:NextNumber(-12, 12)), rng:NextNumber(0, math.pi), math.rad(rng:NextNumber(-12, 12)))
		local r = part(parent, "Rock", Vector3.new(w, h, w * 0.8), cf, C.rock, Enum.Material.Slate, i == 1)
		part(parent, "Moss", Vector3.new(w * 0.9, 0.25, w * 0.7), r.CFrame * CFrame.new(0, h / 2, 0), C.moss, Enum.Material.Grass, false)
	end
end

function Props.torii(parent: Instance, at: Vector3, face: Vector3)
	local f = CFrame.lookAt(at, at + Vector3.new(face.X, 0, face.Z))
	for _, dx in { -3, 3 } do
		part(parent, "ToriiPost", Vector3.new(0.8, 7, 0.8), f * CFrame.new(dx, 3.5, 0), C.vermilion, Enum.Material.SmoothPlastic, true)
	end
	part(parent, "ToriiTop", Vector3.new(9, 0.6, 1.1), f * CFrame.new(0, 7.3, 0), C.darkWood, Enum.Material.Wood, true)
	part(parent, "ToriiBeam", Vector3.new(7.4, 0.45, 0.6), f * CFrame.new(0, 6, 0), C.vermilion, Enum.Material.SmoothPlastic, false)
end

return Props
