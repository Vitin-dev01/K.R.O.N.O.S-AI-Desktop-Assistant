local part = script.Parent

local function criarCubo(parent, tamanho, posicao, cor, material)
	local p = Instance.new("Part")
	p.Size = tamanho
	p.Position = posicao
	p.Color = cor
	p.Material = material or Enum.Material.SmoothPlastic
	p.Anchored = true
	p.Parent = parent
	return p
end

local function criarArvore3D(centro)
	local modelo = Instance.new("Model")
	modelo.Name = "Arvore3D"
	modelo.Parent = workspace

	local alturaTronco = 4
	local larguraTronco = 1.2
	local posTronco = centro + Vector3.new(0, alturaTronco / 2, 0)
	
	local tronco = criarCubo(
		modelo, 
		Vector3.new(larguraTronco, alturaTronco, larguraTronco), 
		posTronco, 
		Color3.fromRGB(100, 65, 30), 
		Enum.Material.Wood
	)
	tronco.Name = "Tronco"

	local camadas = 5
	local larguraInicial = 6
	local alturaCamada = 1.2
	local yBase = centro.Y + alturaTronco

	for i = 1, camadas do
		local fator = 1 - ((i - 1) / camadas)
		local larguraAtual = larguraInicial * fator
		if larguraAtual < 1.5 then larguraAtual = 1.5 end
		
		local yPos = yBase + (i - 1) * (alturaCamada * 0.7) + (alturaCamada / 2)
		local tamanhoCamada = Vector3.new(larguraAtual, alturaCamada, larguraAtual)
		local posCamada = Vector3.new(centro.X, yPos, centro.Z)

		local folhas = criarCubo(
			modelo,
			tamanhoCamada,
			posCamada,
			Color3.fromRGB(34, 139, 34),
			Enum.Material.Grass
		)
		folhas.Name = "Folhagem_" .. i
	end

	return modelo
end

if part and part:IsA("BasePart") then
	local centroArvore = part.Position + Vector3.new(0, 0, 0)
	criarArvore3D(centroArvore)
end