-- Shared by server and client: both sides must place the level the same way.
return {
	origin = Vector3.new(0, 1, 0), -- the tower's base pad sits just above the ground
	-- look = { top = { color = Color3.fromRGB(127, 176, 78), material = Enum.Material.SmoothPlastic } },
	-- onProp = function(kind, position, prop, parent) ... return true end, -- e.g. your own tree asset for "tree"
}
