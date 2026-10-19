import bpy
import bmesh
import math
from mathutils import Vector

# Limpa a cena
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# Coleção
collection = bpy.data.collections.new("KRONOS | Mecanica")
bpy.context.scene.collection.children.link(collection)

# Materiais
mat_metal = bpy.data.materials.new("Metal_Polido")
mat_metal.use_nodes = True
bsdf = mat_metal.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.2, 0.25, 0.35, 1.0)
    bsdf.inputs["Metallic"].default_value = 0.85
    bsdf.inputs["Roughness"].default_value = 0.25

mat_gold = bpy.data.materials.new("Ouro_Acabamento")
mat_gold.use_nodes = True
bsdf_gold = mat_gold.node_tree.nodes.get("Principled BSDF")
if bsdf_gold:
    bsdf_gold.inputs["Base Color"].default_value = (0.85, 0.65, 0.15, 1.0)
    bsdf_gold.inputs["Metallic"].default_value = 0.95
    bsdf_gold.inputs["Roughness"].default_value = 0.18

# 1. Base principal facetada
bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=1.6, depth=0.8, location=(0, 0, 0.4))
base = bpy.context.active_object
base.name = "Peca_Base"
base.data.materials.append(mat_metal)

# 2. Núcleo com Bevel
bev = base.modifiers.new("Bevel_Borda", 'BEVEL')
bev.width = 0.08
bev.segments = 3
bpy.ops.object.modifier_apply(modifier=bev.name)

# 3. Anel superior com Solidify e Array
bpy.ops.mesh.primitive_torus_add(major_radius=1.2, minor_radius=0.15, location=(0, 0, 1.1))
ring = bpy.context.active_object
ring.name = "Anel_Superior"
ring.data.materials.append(mat_gold)

sol = ring.modifiers.new("Solidify", 'SOLIDIFY')
sol.thickness = 0.05
bpy.ops.object.modifier_apply(modifier=sol.name)

# 4. Corte booleano central
bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.65, depth=3.0, location=(0, 0, 0.5))
cutter = bpy.context.active_object
cutter.name = "Cutter_Centro"

bpy.ops.object.select_all(action='DESELECT')
base.select_set(True)
bpy.context.view_layer.objects.active = base

bool_mod = base.modifiers.new("Corte_Central", 'BOOLEAN')
bool_mod.operation = 'DIFFERENCE'
bool_mod.object = cutter
bpy.ops.object.modifier_apply(modifier=bool_mod.name)

bpy.data.objects.remove(cutter, do_unlink=True)

# Câmera e luz para renderização de inspeção
cam_data = bpy.data.cameras.new("KRONOS_Cam")
cam = bpy.data.objects.new("KRONOS_Cam", cam_data)
bpy.context.scene.collection.objects.link(cam)
cam.location = (4.0, -4.5, 3.5)
cam.rotation_euler = (math.radians(60), 0, math.radians(45))
bpy.context.scene.camera = cam

light_data = bpy.data.lights.new("KRONOS_Light", type='AREA')
light_data.energy = 800
light_data.size = 3.0
light = bpy.data.objects.new("KRONOS_Light", light_data)
bpy.context.scene.collection.objects.link(light)
light.location = (3.0, -3.0, 5.0)

# Render settings
bpy.context.scene.render.resolution_x = 1024
bpy.context.scene.render.resolution_y = 1024
bpy.context.scene.render.filepath = 'C:\\Users\\Usuario\\Documents\\K.R.O.N.O.S\\scripts_blender\\objeto_mecanico_modificadores_preview.png'
bpy.ops.render.render(write_still=True)

bpy.ops.wm.save_as_mainfile(filepath='C:\\Users\\Usuario\\Documents\\K.R.O.N.O.S\\scripts_blender\\objeto_mecanico_modificadores.blend')
print("KRONOS_MODIFIERS_ASSET_SAVED")
