local part = script.Parent
part.Transparency = 1
part.CanCollide = false
part.Anchored = true

local function createPart(size, color, material, position, parent)
	local p = Instance.new("Part")
	p.Size = size
	p.Color = color
	p.Material = material
	p.Position = position
	p.Anchored = true
	p.Parent = parent
	return p
end

local treeModel = Instance.new("Model")
treeModel.Name = "ProceduralTree"
treeModel.Parent = workspace

local basePos = part.Position

local trunkSize = Vector3.new(2, 10, 2)
local trunkPos = basePos + Vector3.new(0, trunkSize.Y / 2, 0)
local trunk = createPart(trunkSize, Color3.fromRGB(90, 60, 40), Enum.Material.Wood, trunkPos, treeModel)

local foliageCount = 5
local foliageBaseSize = Vector3.new(8, 4, 8)
local startHeight = basePos.Y + trunkSize.Y

for i = 1, foliageCount do
	local factor = 1 - ((i - 1) / foliageCount)
	local size = foliageBaseSize * factor
	local height = startHeight + (i - 2) * 2
	local pos = basePos + Vector3.new(0, height, 0)
	createPart(size, Color3.fromRGB(34, 139, 34), Enum.Material.LeafyGrass, pos, treeModel)
end