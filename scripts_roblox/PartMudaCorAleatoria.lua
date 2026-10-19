--!strict

local Workspace = game:GetService("Workspace")
local RunService = game:GetService("RunService")

local part = Instance.new("Part")
part.Size = Vector3.new(4, 1, 2)
part.Position = Vector3.new(0, 5, 0)
part.Anchored = false
part.Parent = Workspace

local timeElapsed = 0.0
local interval = 1.0

RunService.Stepped:Connect(function(time: number, dt: number)
	timeElapsed += dt
	if timeElapsed >= interval then
		timeElapsed = 0.0
		part.BrickColor = BrickColor.random()
	end
end)