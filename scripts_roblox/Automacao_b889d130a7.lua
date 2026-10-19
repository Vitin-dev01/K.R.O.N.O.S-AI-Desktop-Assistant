local part = script.Parent

local colors = {
    Color3.fromRGB(255, 0, 0),
    Color3.fromRGB(0, 255, 0),
    Color3.fromRGB(0, 0, 255),
    Color3.fromRGB(255, 255, 0),
    Color3.fromRGB(255, 0, 255),
    Color3.fromRGB(0, 255, 255),
    Color3.fromRGB(255, 255, 255)
}

task.spawn(function()
    local index = 1
    while true do
        part.Color = colors[index]
        index = index % #colors + 1
        task.wait(2)
    end
end)