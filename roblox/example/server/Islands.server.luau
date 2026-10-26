-- Example: build the level and put a glowing orb on every collectible spot.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local IslandGen = require(ReplicatedStorage.IslandGen)
local options = require(ReplicatedStorage.IslandOptions)

local level = IslandGen.build(ReplicatedStorage.Levels.tower1, options)
print(("[Islands] built %s: %d boxes, %d spots"):format(level.model.Name, #level.walk:GetChildren(), #level.spots))

-- collectibles: rarer (warmer) the higher they are
for _, spot in level.spots do
	local orb = Instance.new("Part")
	orb.Shape = Enum.PartType.Ball
	orb.Size = Vector3.new(1.5, 1.5, 1.5)
	orb.Anchored = true
	orb.CanCollide = false
	orb.Material = Enum.Material.Neon
	orb.Color = Color3.fromHSV(0.55 - 0.45 * spot.height01, 0.7, 1)
	orb.Position = spot.position + Vector3.new(0, 1.5, 0)
	orb.Parent = level.model
	local pp = Instance.new("ProximityPrompt")
	pp.ActionText = "Collect"
	pp.Parent = orb
	pp.Triggered:Connect(function(player)
		print(player.Name, "collected a spot at height", spot.height01)
		orb:Destroy()
	end)
end

-- start players on the base pad
Players.PlayerAdded:Connect(function(player)
	player.CharacterAdded:Connect(function(char)
		task.wait()
		char:PivotTo(level.spawn)
	end)
end)
