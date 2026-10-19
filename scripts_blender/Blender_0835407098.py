import bpy
import math
import random
import bmesh

def cleanup_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)
    for block in bpy.data.materials:
        if block.users == 0:
            bpy.data.materials.remove(block)
    for block in bpy.data.textures:
        if block.users == 0:
            bpy.data.textures.remove(block)

def create_tree():
    cleanup_scene()
    
    bark_mat = bpy.data.materials.new(name="Tree_Bark")
    bark_mat.use_nodes = True
    bsdf_bark = bark_mat.node_tree.nodes.get("Principled BSDF")
    if bsdf_bark:
        bsdf_bark.inputs['Base Color'].default_value = (0.08, 0.05, 0.03, 1.0)
        bsdf_bark.inputs['Roughness'].default_value = 0.9

    leaf_mat = bpy.data.materials.new(name="Tree_Leaves")
    leaf_mat.use_nodes = True
    bsdf_leaf = leaf_mat.node_tree.nodes.get("Principled BSDF")
    if bsdf_leaf:
        bsdf_leaf.inputs['Base Color'].default_value = (0.1, 0.35, 0.08, 1.0)
        bsdf_leaf.inputs['Roughness'].default_value = 0.6

    trunk_mesh = bpy.data.meshes.new("Trunk_Mesh")
    trunk_obj = bpy.data.objects.new("Tree_Trunk", trunk_mesh)
    bpy.context.collection.objects.link(trunk_obj)
    
    bm_trunk = bmesh.new()
    
    height = 4.0
    segments = 6
    rings = 10
    
    random.seed(101)
    rings_verts_list = []
    for r in range(rings):
        z_frac = r / (rings - 1)
        z = z_frac * height
        radius = 0.35 * (1.0 - z_frac * 0.7)
        
        offset_x = math.sin(z_frac * math.pi * 2) * 0.15 * z_frac
        offset_y = math.cos(z_frac * math.pi * 1.5) * 0.15 * z_frac
        
        ring_verts = []
        for s in range(segments):
            angle = (s / segments) * math.pi * 2.0
            r_var = radius * (1.0 + 0.15 * math.sin(angle * 3.0 + z_frac * 5.0))
            vx = offset_x + math.cos(angle) * r_var
            vy = offset_y + math.sin(angle) * r_var
            vz = z
            ring_verts.append(bm_trunk.verts.new((vx, vy, vz)))
            
        if r > 0:
            prev_ring = rings_verts_list[r-1]
            for s in range(segments):
                v1 = prev_ring[s]
                v2 = prev_ring[(s + 1) % segments]
                v3 = ring_verts[(s + 1) % segments]
                v4 = ring_verts[s]
                bmesh.ops.contextual_create(bm_trunk, geom=[v1, v2, v3, v4])
                
        rings_verts_list.append(ring_verts)

    bmesh.ops.recalc_face_normals(bm_trunk, faces=bm_trunk.faces)
    bm_trunk.to_mesh(trunk_mesh)
    bm_trunk.free()
    
    trunk_obj.data.materials.append(bark_mat)

    leaves_mesh = bpy.data.meshes.new("Leaves_Mesh")
    leaves_obj = bpy.data.objects.new("Tree_Leaves", leaves_mesh)
    bpy.context.collection.objects.link(leaves_obj)

    bm_leaves = bmesh.new()
    
    random.seed(42)
    for _ in range(100):
        theta = random.uniform(0, 2 * math.pi)
        phi = random.uniform(0, math.pi * 0.7)
        r = random.uniform(0.6, 2.0)
        
        lx = r * math.sin(phi) * math.cos(theta)
        ly = r * math.sin(phi) * math.sin(theta)
        lz = r * math.cos(phi) + 3.2
        
        scale = random.uniform(0.3, 0.7)
        
        raft = bmesh.new()
        bmesh.ops.create_icosphere(raft, subdivisions=1, radius=scale)
        
        for v in raft.verts:
            v.co.x += lx
            v.co.y += ly
            v.co.z += lz
            
        bm_leaves.verts.ensure_lookup_table()
        vert_offset = len(bm_leaves.verts)
        
        for v in raft.verts:
            bm_leaves.verts.new(v.co)
        bm_leaves.verts.ensure_lookup_table()
        
        for f in raft.faces:
            try:
                indices = [v.index for v in f.verts]
                new_verts = [bm_leaves.verts[vert_offset + idx] for idx in indices]
                bm_leaves.faces.new(new_verts)
            except ValueError:
                pass
                
        raft.free()

    bmesh.ops.recalc_face_normals(bm_leaves, faces=bm_leaves.faces)
    bm_leaves.to_mesh(leaves_mesh)
    bm_leaves.free()
    
    leaves_obj.data.materials.append(leaf_mat)
    
    trunk_obj.location = (0, 0, 0)
    leaves_obj.location = (0, 0, 0)
    
    bpy.ops.object.select_all(action='DESELECT')

create_tree()
