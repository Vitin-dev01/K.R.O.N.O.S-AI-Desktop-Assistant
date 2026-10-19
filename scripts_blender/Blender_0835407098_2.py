import bpy
import bmesh
import random
import math
import mathutils

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

for block in bpy.data.meshes:
    if block.users == 0:
        bpy.data.meshes.remove(block)
for block in bpy.data.materials:
    if block.users == 0:
        bpy.data.materials.remove(block)

bark_mat = bpy.data.materials.new(name="Bark_Material")
bark_mat.use_nodes = True
nodes = bark_mat.node_tree.nodes
nodes.clear()
node_output = nodes.new(type='ShaderNodeOutputMaterial')
node_principled = nodes.new(type='ShaderNodeBsdfPrincipled')
node_principled.inputs['Base Color'].default_value = (0.08, 0.05, 0.02, 1.0)
node_principled.inputs['Roughness'].default_value = 0.9
bark_mat.node_tree.links.new(node_principled.outputs['BSDF'], node_output.inputs['Surface'])

leaf_mat = bpy.data.materials.new(name="Leaf_Material")
leaf_mat.use_nodes = True
nodes = leaf_mat.node_tree.nodes
nodes.clear()
node_output = nodes.new(type='ShaderNodeOutputMaterial')
node_principled = nodes.new(type='ShaderNodeBsdfPrincipled')
node_principled.inputs['Base Color'].default_value = (0.05, 0.25, 0.05, 1.0)
node_principled.inputs['Roughness'].default_value = 0.4
leaf_mat.node_tree.links.new(node_principled.outputs['BSDF'], node_output.inputs['Surface'])

def create_branch_mesh(name, radius_base, radius_top, length, segments=6, rings=8):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    
    for r in range(rings):
        frac = r / (rings - 1)
        z = frac * length
        current_radius = radius_base * (1.0 - frac) + radius_top * frac
        
        for s in range(segments):
            angle = (s / segments) * math.pi * 2.0
            x = math.cos(angle) * current_radius
            y = math.sin(angle) * current_radius
            bm.verts.new((x, y, z))
            
    bm.verts.ensure_lookup_table()
    
    for r in range(rings - 1):
        for s in range(segments):
            next_s = (s + 1) % segments
            v1 = r * segments + s
            v2 = r * segments + next_s
            v3 = (r + 1) * segments + next_s
            v4 = (r + 1) * segments + s
            try:
                bm.faces.new((bm.verts[v1], bm.verts[v2], bm.verts[v3], bm.verts[v4]))
            except:
                pass
                
    bm.to_mesh(mesh)
    bm.free()
    return mesh

def build_tree_recursive(bm, matrix, radius, length, level, max_level):
    if level > max_level:
        return

    sub_mesh = create_branch_mesh("TempBranch", radius, radius * 0.6, length, segments=5, rings=5)
    
    sub_bm = bmesh.new()
    sub_bm.from_mesh(sub_mesh)
    bmesh.ops.transform(sub_bm, matrix=matrix, verts=sub_bm.verts)
    sub_bm.to_mesh(sub_mesh)
    sub_bm.free()
    
    bm.from_mesh(sub_mesh)
    bpy.data.meshes.remove(sub_mesh)

    if level < max_level:
        num_children = random.randint(2, 4)
        for i in range(num_children):
            rot_angle = (i / num_children) * math.pi * 2.0 + random.uniform(-0.5, 0.5)
            tilt = random.uniform(0.3, 0.8)
            
            child_matrix = matrix @ mathutils.Matrix.Translation((0, 0, length * 0.8)) @ mathutils.Matrix.Rotation(rot_angle, 4, 'Z') @ mathutils.Matrix.Rotation(tilt, 4, 'Y')
            build_tree_recursive(bm, child_matrix, radius * 0.6, length * 0.7, level + 1, max_level)

tree_mesh = bpy.data.meshes.new("TreeTrunk_Mesh")
tree_bm = bmesh.new()

base_mesh = create_branch_mesh("Base", 0.4, 0.25, 3.0, segments=8, rings=10)
tree_bm.from_mesh(base_mesh)
bpy.data.meshes.remove(base_mesh)

mat1 = mathutils.Matrix.Translation((0, 0, 2.5)) @ mathutils.Matrix.Rotation(0.3, 4, 'Y')
build_tree_recursive(tree_bm, mat1, 0.2, 2.0, 1, 3)

mat2 = mathutils.Matrix.Translation((0, 0, 2.0)) @ mathutils.Matrix.Rotation(-0.4, 4, 'X')
build_tree_recursive(tree_bm, mat2, 0.18, 1.8, 1, 3)

tree_bm.to_mesh(tree_mesh)
tree_bm.free()

tree_obj = bpy.data.objects.new("TreeTrunk", tree_mesh)
tree_obj.data.materials.append(bark_mat)
bpy.context.collection.objects.link(tree_obj)

leaf_mesh = bpy.data.meshes.new("LeafCluster_Mesh")
leaf_bm = bmesh.new()
bmesh.ops.create_uvsphere(leaf_bm, u_segments=6, v_segments=6, radius=0.4)
leaf_bm.to_mesh(leaf_mesh)
leaf_bm.free()

leaf_collection = bpy.data.collections.new("Leaves")
bpy.context.scene.collection.children.link(leaf_collection)

random.seed(42)
for i in range(120):
    leaf_obj = bpy.data.objects.new(f"Leaf_{i}", leaf_mesh)
    leaf_obj.data.materials.append(leaf_mat)
    
    rx = random.uniform(-1.5, 1.5)
    ry = random.uniform(-1.5, 1.5)
    rz = random.uniform(2.0, 5.5)
    
    leaf_obj.location = (rx, ry, rz)
    scale_var = random.uniform(0.5, 1.5)
    leaf_obj.scale = (scale_var, scale_var, scale_var)
    leaf_obj.rotation_euler = (random.uniform(0, 3.14), random.uniform(0, 3.14), random.uniform(0, 3.14))
    
    leaf_collection.objects.link(leaf_obj)

bpy.context.view_layer.update()
