--!strict

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local part = script.Parent :: BasePart

task.spawn(function()
	while true do
		part.BrickColor = BrickColor.random()
		task.wait(1)
	end
end)