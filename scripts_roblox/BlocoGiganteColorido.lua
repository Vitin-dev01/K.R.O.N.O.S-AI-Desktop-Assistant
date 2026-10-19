--!strict

local workspace = game:GetService("Workspace")

local giantBlock = Instance.new("Part")
giantBlock.Name = "GiantFloatingBlock"
giantBlock.Size = Vector3.new(50, 50, 50)
giantBlock.Position = Vector3.new(0, 100, 0)
giantBlock.Anchored = true
giantBlock.Material = Enum.Material.Neon
giantBlock.Parent = workspace

task.spawn(function()
	while true do
		giantBlock.Color = Color3.new(math.random(), math.random(), math.random())
		task.wait(1)
	end
end)