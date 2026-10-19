--!strict

local parte = script.Parent :: Part

while true do
	local corAleatoria = Color3.fromRGB(math.random(0, 255), math.random(0, 255), math.random(0, 255))
	parte.Color = corAleatoria
	task.wait(1)
end