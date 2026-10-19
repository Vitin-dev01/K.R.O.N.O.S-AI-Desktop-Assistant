--!strict

local parte = Instance.new("Part")
parte.Name = "BlocoMagico"
parte.Size = Vector3.new(4, 1, 2)
parte.Position = Vector3.new(0, 5, 0)
parte.Anchored = true
parte.Parent = workspace

local scriptFilho = Instance.new("Script")
scriptFilho.Name = "MudancaDeCor"
scriptFilho.Source = [[
--!strict
local part = script.Parent :: Part

while true do
	part.Color = Color3.fromRGB(math.random(0, 255), math.random(0, 255), math.random(0, 255))
	task.wait(0.5)
end
]]
scriptFilho.Parent = parte