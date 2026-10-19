--!strict

local Players = game:GetService("Players")
local TweenService = game:GetService("TweenService")

local part = script.Parent :: Part

local function getRandomColor(): Color3
	return Color3.fromRGB(math.random(0, 255), math.random(0, 255), math.random(0, 255))
end

task.spawn(function()
	while true do
		local goal = {
			Color = getRandomColor()
		}
		
		local tweenInfo = TweenInfo.new(
			1, -- Duração da transição
			Enum.EasingStyle.Sine,
			Enum.EasingDirection.InOut
		)
		
		local tween = TweenService:Create(part, tweenInfo, goal)
		tween:Play()
		
		task.wait(2)
	end
end)