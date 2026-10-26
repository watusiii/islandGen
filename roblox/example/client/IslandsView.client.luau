-- Example: build the land mesh on this client.
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local IslandGen = require(ReplicatedStorage:WaitForChild("IslandGen"))
local options = require(ReplicatedStorage:WaitForChild("IslandOptions"))

local ok, why = IslandGen.view(ReplicatedStorage:WaitForChild("Levels"):WaitForChild("tower1"), options)
if ok then
	print("[IslandsView] mesh ON")
else
	warn("[IslandsView] mesh OFF, showing boxes: " .. tostring(why))
end
