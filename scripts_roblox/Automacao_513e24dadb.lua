local part = script.Parent

local function getRandomColor()
	return Color3.fromRGB(math.random(0, 255), math.random(0, 255), math.random(0, 255))
end

task.spawn(function()
	while true do
		part.BrickColor = BrickColor.random()
		-- Alternativamente, usando Color3:
		-- part.Color = getRandomColor()
		task.wait(1)
	end
end)