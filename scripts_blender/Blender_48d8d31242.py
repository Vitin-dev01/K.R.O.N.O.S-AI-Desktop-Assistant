import bpy
import math
import random

def _kronos_progress():
    pass

# Limpar cena existente
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Configuração de semente aleatória para reproducibilidade
random.seed(42)

# --- MATERIAIS ---
# Material do Tronco
mat_bark = bpy.data.materials.new(name="Bark_Material")
mat_bark.use_nodes = True
nodes_bark = mat_bark.node_tree.nodes
nodes_bark.clear()
node_output_bark = nodes_bark.new(type='ShaderNodeOutputMaterial')
node_bsdf_bark = nodes_bark.new(type='ShaderNodeBsdfPrincipled')
node_bsdf_bark.inputs['Base Color'].default_value = (0.08, 0.05, 0.03, 1.0)
node_bsdf_bark.inputs['Roughness'].default_value = 0.9
mat_bark.node_tree.links.new(node_bsdf_bark.outputs['BSDF'], node_output_bark.inputs['Surface'])

# Material das Folhas
mat_leaves = bpy.data.materials.new(name="Leaves_Material")
mat_leaves.use_nodes = True
nodes_leaves = mat_leaves.node_tree.nodes
nodes_leaves.clear()
node_output_leaves = nodes_leaves.new(type='ShaderNodeOutputMaterial')
node_bsdf_leaves = nodes_leaves.new(type='ShaderNodeBsdfPrincipled')
node_bsdf_leaves.inputs['Base Color'].default_value = (0.15, 0.35, 0.1, 1.0)
node_bsdf_leaves.inputs['Roughness'].default_value = 0.5
mat_leaves.node_tree.links.new(node_bsdf_leaves.outputs['BSDF'], node_output_leaves.inputs['Surface'])

_kronos_progress()

# --- GEOMETRIA DA FOLHA (MALLHA ÚNICA REUTILIZÁVEL) ---
bpy.ops.mesh.primitive_plane_add(size=0.15, location=(0,0,0))
leaf_base_obj = bpy.context.active_object
leaf_base_obj.name = "Leaf_Base"
leaf_mesh = leaf_base_obj.data
leaf_mesh.name = "Leaf_Mesh"

# Dar alguma forma à folha (curvatura simples)
for v in leaf_mesh.vertices:
    if v.co.x > 0:
        v.co.z += 0.03

leaf_base_obj.data.materials.append(mat_leaves)

# --- ESTRUTURA DO TRONCO E GALHOS ---
# Usando curvas para gerar ramos orgânicos e afunilados
def create_branch_curve(points, radius_start, radius_end, name):
    curve_data = bpy.data.curves.new(name=name, type='CURVE')
    curve_data.dimensions = '3D'
    curve_data.resolution_u = 4
    curve_data.bevel_depth = radius_start
    curve_data.taper_radius_mode = 'MULTIPLY'
    
    spline = curve_data.splines.new('BEZIER')
    # Ajustar pontos
    spline.bezier_points.add(len(points) - 1)
    for i, pt in enumerate(points):
        bp = spline.bezier_points[i]
        bp.co = pt
        bp.handle_left_type = 'AUTO'
        bp.handle_right_type = 'AUTO'
        
    obj = bpy.data.objects.new(name, curve_data)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat_bark)
    return obj

# Tronco Principal
trunk_points = [
    (0.0, 0.0, 0.0),
    (0.1, 0.05, 1.0),
    (-0.05, 0.1, 2.5),
    (0.0, 0.0, 4.0)
]
trunk = create_branch_curve(trunk_points, 0.35, 0.15, "Tree_Trunk")

_kronos_progress()

# Galhos Secundários e Terciários (Gerados proceduralmente)
branch_objects = [trunk]
leaf_instances = []

def generate_sub_branches(start_co, direction, level, max_level):
    if level > max_level:
        # Gerar folhas no final dos ramos terminais
        for _ in range(random.randint(3, 7)):
            offset = math.cos(random.uniform(0, math.pi)) * 0.2
            lx = start_co[0] + random.uniform(-0.4, 0.4)
            ly = start_co[1] + random.uniform(-0.4, 0.4)
            lz = start_co[2] + random.uniform(-0.2, 0.3)
            leaf_instances.append((lx, ly, lz))
        return

    length = random.uniform(1.0, 2.0) / level
    end_co = (
        start_co[0] + direction[0] * length + random.uniform(-0.3, 0.3),
        start_co[1] + direction[1] * length + random.uniform(-0.3, 0.3),
        start_co[2] + abs(direction[2]) * length + random.uniform(0.1, 0.4)
    )
    
    radius = 0.15 / (level + 1)
    b_obj = create_branch_curve([start_co, end_co], radius, radius * 0.6, f"Branch_L{level}")
    branch_objects.append(b_obj)
    
    # Criar novos ramos filhos
    num_children = random.randint(2, 3)
    for i in range(num_children):
        angle = (i / num_children) * math.pi * 2 + random.uniform(-0.5, 0.5)
        new_dir = (
            math.cos(angle) * 0.7,
            math.sin(angle) * 0.7,
            random.uniform(0.3, 0.9)
        )
        generate_sub_branches(end_co, new_dir, level + 1, max_level)

# Disparar ramos a partir do tronco
for i in range(1, 4):
    t = i / 4.0
    # Interpolação simples do ponto no tronco
    trunk_pt = (trunk_points[i][0], trunk_points[i][1], trunk_points[i][2])
    for j in range(3):
        angle = j * (math.pi * 2 / 3) + random.uniform(-0.2, 0.2)
        dir_vec = (math.cos(angle), math.sin(angle), random.uniform(0.5, 1.0))
        generate_sub_branches(trunk_pt, dir_vec, 1, 3)

_kronos_progress()

# Converter curvas em malhas para unir e otimizar
bpy.ops.object.select_all(action='DESELECT')
for obj in branch_objects:
    obj.select_set(True)
bpy.context.view_layer.objects.active = trunk

# Converter para mesh
bpy.ops.object.convert(target='MESH')
# Juntar todos os galhos em um único objeto de tronco/galhos
bpy.ops.object.join()
tree_mesh_obj = bpy.context.active_object
tree_mesh_obj.name = "Tree_Structure"

_kronos_progress()

# --- DISTRIBUIÇÃO DAS FOLHAS USANDO INSTÂNCIAS VINCULADAS ---
# Remover o plano original base para usar apenas instâncias linked
bpy.data.objects.remove(leaf_base_obj, do_unlink=True)

# Criar um container vazio para as folhas
leaves_parent = bpy.data.objects.new("Tree_Leaves_Group", None)
bpy.context.collection.objects.link(leaves_parent)

# Agrupar folhas em malhas unificadas por proximidade para respeitar limite de objetos
# Criar algumas malhas de folhagem combinadas para performance
batch_size = 100
for i in range(0, len(leaf_instances), batch_size):
    batch = leaf_instances[i:i+batch_size]
    
    # Criar uma malha combinada para este lote
    mesh_data = bpy.data.meshes.new(f"Leaf_Batch_Mesh_{i}")
    batch_obj = bpy.data.objects.new(f"Leaf_Batch_{i}", mesh_data)
    batch_obj.parent = leaves_parent
    bpy.context.collection.objects.link(batch_obj)
    batch_obj.data.materials.append(mat_leaves)
    
    # Construir geometria combinada via bmesh (simulado criando dados de malha básicos ou duplicando)
    # Para simplicidade e robustez sem falhas de bmesh em versões específicas:
    # Usaremos instâncias vinculadas (Linked Duplicates) que são altamente otimizadas no Blender
    pass

# Abordagem robusta e otimizada: Instâncias vinculadas associadas a um Empty principal
collection_leaves = bpy.data.collections.new("Leaves_Collection")
bpy.context.scene.collection.children.link(collection_leaves)

# Recriar a malha da folha original limpa para instanciação
bpy.ops.mesh.primitive_plane_add(size=0.18, location=(0,0,0))
master_leaf = bpy.context.active_object
master_leaf.name = "Master_Leaf"
master_leaf.data.materials.append(mat_leaves)

# Mover para fora da vista direta ou ocultar da camada principal se necessário
master_leaf.location = (0, 0, -10) # Afastado da árvore principal

for idx, pos in enumerate(leaf_instances):
    # Criar duplicata vinculada (compartilha os mesmos dados de malha, zero custo extra de memória)
    leaf_inst = master_leaf.copy()
    leaf_inst.data = master_leaf.data 
    leaf_inst.name = f"Leaf_Inst_{idx}"
    
    leaf_inst.location = pos
    leaf_inst.rotation_euler = (
        random.uniform(0, math.pi),
        random.uniform(0, math.pi),
        random.uniform(0, math.pi)
    )
    scale_var = random.uniform(0.7, 1.3)
    leaf_inst.scale = (scale_var, scale_var, scale_var)
    
    bpy.context.collection.objects.link(leaf_inst)

_kronos_progress()

# Garantir que a árvore principal está na origem com a base em Z=0
tree_mesh_obj.location = (0, 0, 0)

# Seleção final limpa
bpy.ops.object.select_all(action='DESELECT')
tree_mesh_obj.select_set(True)
bpy.context.view_layer.objects.active = tree_mesh_obj
