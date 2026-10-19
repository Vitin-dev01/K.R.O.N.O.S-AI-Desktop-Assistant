--!strict

local part = script.Parent

local kronos = workspace:FindFirstChild("KRONOS", true)

if kronos and kronos:IsA("BasePart") then
	local existingScript = kronos:FindFirstChild("ColorCyclerScript")
	if not existingScript then
		local newScript = Instance.new("Script")
		newScript.Name = "ColorCyclerScript"
		newScript.Source = [[
--!strict
local p = script.Parent :: BasePart
while true do
	p.Color = Color3.fromRGB(math.random(0, 255), math.random(0, 255), math.random(0, 255))
	task.wait(2)
end
]]
		newScript.Parent = kronos
	end
end

local success, plugin = pcall(function()
	return game:GetService("ChangeHistoryService")
end)

local function startPlayTest()
	local runService = game:GetService("RunService")
	if not runService:IsRunning() then
		local successStudio, studio = pcall(function()
			return (settings():GetService("StudioService") :: any)
		end)
		if successStudio and studio then
			-- Simula o start do play test se estiver em ambiente de plugin/studio
		end
	end
end

startPlayTest()