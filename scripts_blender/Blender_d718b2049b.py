import bpy
import bmesh
import math
import random

def _kronos_progress(msg):
    print(f"KRONOS_PROGRESS: {msg}")

for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
for mesh in list(bpy.data.meshes):
    bpy.data.meshes.remove(mesh)
for mat in list(bpy.data.materials):
    bpy.data.materials.remove(mat)

_kronos_progress("Configurando paleta de cores Low-Poly")
mat_trunk = bpy.data.materials.new(name="LowPoly_Trunk")
mat_trunk.use_nodes = True
mat_trunk.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.28, 0.16, 0.08, 1.0)
mat_trunk.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9

mat_leaves_dark = bpy.data.materials.new(name="LowPoly_LeavesDark")
mat_leaves_dark.use_nodes = True
mat_leaves_dark.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.12, 0.32, 0.12, 1.0)
mat_leaves_dark.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9

mat_leaves_mid = bpy.data.materials.new(name="LowPoly_LeavesMid")
mat_leaves_mid.use_nodes = True
mat_leaves_mid.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.18, 0.48, 0.18, 1.0)
mat_leaves_mid.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9

mat_leaves_light = bpy.data.materials.new(name="LowPoly_LeavesLight")
mat_leaves_light.use_nodes = True
mat_leaves_light.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.26, 0.62, 0.22, 1.0)
mat_leaves_light.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9

mat_pot = bpy.data.materials.new(name="LowPoly_Pot")
mat_pot.use_nodes = True
mat_pot.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.65, 0.32, 0.20, 1.0)
mat_pot.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.8

mat_soil = bpy.data.materials.new(name="LowPoly_Soil")
mat_soil.use_nodes = True
mat_soil.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.15, 0.10, 0.06, 1.0)
mat_soil.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 1.0

_kronos_progress("Construindo o vaso low-poly")
bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=1.2, depth=2.0, location=(0, 0, 1.0))
pot_obj = bpy.context.active_object
pot_obj.name = "Plant_Pot"

# Ajustar escala dos vértices superiores para criar o formato de vaso (cônico)
bm = bmesh.new()
bm.from_mesh(pot_obj.data)
for v in bm.verts:
    if v.co.z > 0.5:
        v.co.x *= 0.66
        v.co.y *= 0.66
bm.to_mesh(pot_obj.data)
bm.free()

pot_obj.data.materials.append(mat_pot)
for poly in pot_obj.data.polygons:
    poly.use_smooth = False

_kronos_progress("Adicionando a terra do vaso")
bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=1.15, depth=0.2, location=(0, 0, 1.9))
soil_obj = bpy.context.active_object
soil_obj.name = "Plant_Soil"
soil_obj.data.materials.append(mat_soil)
for poly in soil_obj.data.polygons:
    poly.use_smooth = False

_kronos_progress("Construindo o tronco principal e galhos")
bpy.ops.mesh.primitive_cone_add(vertices=5, radius1=0.3, radius2=0.15, depth=2.5, location=(0, 0, 2.75))
trunk_obj = bpy.context.active_object
trunk_obj.name = "Tree_Trunk"
trunk_obj.data.materials.append(mat_trunk)
for poly in trunk_obj.data.polygons:
    poly.use_smooth = False

branch_configs = [
    (0.8, 2.8, 0, 0.7, 0.3, 0.4),
    (-0.7, 3.2, 0.5, -0.6, 0.2, 0.5),
    (0.0, 3.6, -0.7, 0.0, -0.5, 0.6)
]

branch_objects = [trunk_obj]
for loc_x, loc_z_pos, rot_y, scale_x, scale_y, scale_z in branch_configs:
    bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=0.15, radius2=0.08, depth=1.5, location=(loc_x, 0, loc_z_pos))
    b_obj = bpy.context.active_object
    b_obj.rotation_euler = (0, rot_y, loc_x * 1.5)
    b_obj.scale = (scale_x, scale_y, scale_z)
    b_obj.data.materials.append(mat_trunk)
    for poly in b_obj.data.polygons:
        poly.use_smooth = False
    branch_objects.append(b_obj)

_kronos_progress("Criando agrupamentos de folhas facetadas")
leaf_materials = [mat_leaves_dark, mat_leaves_mid, mat_leaves_light]

leaf_cluster_data = [
    (0, 0, 4.2, 1.2, 1.2, 1.2, 0),
    (0.8, 2.5, 3.8, 0.8, 0.8, 0.8, 1),
    (-0.9, 2.9, 4.0, 0.9, 0.9, 0.9, 2),
    (0.5, -0.5, 3.5, 0.7, 0.7, 0.7, 0),
    (-0.5, -0.4, 3.7, 0.8, 0.8, 0.8, 1),
    (0.0, 0.8, 4.6, 0.6, 0.6, 0.6, 2)
]

leaf_objects = []
for lx, ly, lz, sx, sy, sz, mat_idx in leaf_cluster_data:
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=1.0, location=(lx, ly, lz))
    l_obj = bpy.context.active_object
    l_obj.scale = (sx, sy, sz)
    l_obj.rotation_euler = (random.uniform(0, 3), random.uniform(0, 3), random.uniform(0, 3))
    l_obj.data.materials.append(leaf_materials[mat_idx])
    for poly in l_obj.data.polygons:
        poly.use_smooth = False
    leaf_objects.append(l_obj)

_kronos_progress("Combinando e organizando malhas low-poly")
bpy.ops.object.select_all(action='DESELECT')

pot_obj.select_set(True)
soil_obj.select_set(True)
for b in branch_objects:
    b.select_set(True)
for l in leaf_objects:
    l.select_set(True)

bpy.context.view_layer.objects.active = pot_obj
bpy.ops.object.join()

final_plant = bpy.context.active_object
final_plant.name = "LowPoly_Potted_Plant"

_kronos_progress("Finalizando planta low-poly")
bpy.ops.object.select_all(action='DESELECT')
final_plant.select_set(True)
bpy.context.view_layer.objects.active = final_plant

_kronos_progress("Concluído com sucesso")
