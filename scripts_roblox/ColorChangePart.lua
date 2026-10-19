--!strict

local part = script.Parent

task.spawn(function()
	while true do
		part.Color = Color3.fromRGB(math.random(0, 255), math.random(0, 255), math.random(0, 255))
		task.wait(1)
	end
end)

game:GetService("RunService"):Run()