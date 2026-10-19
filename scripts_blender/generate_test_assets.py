import os
import sys
import json
import subprocess
from unittest.mock import patch

# Garante import do kronos
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import blender_automation
import blender_project_edit

SCRIPTS_BLENDER_DIR = os.path.join(BASE_DIR, "scripts_blender")
os.makedirs(SCRIPTS_BLENDER_DIR, exist_ok=True)

BLENDER_EXECUTABLE = blender_automation._find_blender_executable()
print(f"[TESTE REAL] Executável do Blender detectado: {BLENDER_EXECUTABLE}")

def generate_asset(name: str, description: str, filename: str):
    target_path = os.path.join(SCRIPTS_BLENDER_DIR, filename)
    print(f"\n=======================================================")
    print(f"[GERANDO] {name}")
    print(f"[ARQUIVO] {target_path}")
    print(f"[DESCRICAO] {description}")
    print(f"=======================================================")
    
    with (
        patch.object(blender_automation, "_choose_save_path", return_value=target_path),
        patch.object(blender_automation, "_should_show_blender", return_value=False),
    ):
        result = blender_automation.generate_blender_script(name, description)
    
    print(f"[RESULTADO] {result}")
    preview_path = os.path.splitext(target_path)[0] + "_preview.png"
    
    blend_exists = os.path.isfile(target_path)
    preview_exists = os.path.isfile(preview_path)
    
    print(f"[STATUS] Blend existe? {blend_exists} ({os.path.getsize(target_path) if blend_exists else 0} bytes)")
    print(f"[STATUS] Preview existe? {preview_exists} ({os.path.getsize(preview_path) if preview_exists else 0} bytes)")
    
    if preview_exists:
        qa = blender_automation._inspect_render(preview_path)
        print(f"[QA RENDER] {json.dumps(qa)}")
    
    return blend_exists and preview_exists

def generate_modifiers_asset(filename: str):
    """Cria um modelo mecânico sofisticado com Bevel, Solidify, cortes e materiais."""
    blend_path = os.path.join(SCRIPTS_BLENDER_DIR, filename)
    render_path = os.path.splitext(blend_path)[0] + "_preview.png"
    print(f"\n=======================================================")
    print(f"[GERANDO] Objeto com Cortes e Modificadores")
    print(f"[ARQUIVO] {blend_path}")
    print(f"=======================================================")

    runner_script = f"""import bpy
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
bpy.context.scene.render.filepath = {render_path!r}
bpy.ops.render.render(write_still=True)

bpy.ops.wm.save_as_mainfile(filepath={blend_path!r})
print("KRONOS_MODIFIERS_ASSET_SAVED")
"""
    runner_file = os.path.join(SCRIPTS_BLENDER_DIR, "run_modifiers_asset.py")
    with open(runner_file, "w", encoding="utf-8") as f:
        f.write(runner_script)
    
    subprocess.run(
        [BLENDER_EXECUTABLE, "--background", "--factory-startup", "--python", runner_file],
        capture_output=True,
        text=True,
        timeout=120,
        check=True
    )
    blend_exists = os.path.isfile(blend_path)
    preview_exists = os.path.isfile(render_path)
    print(f"[STATUS] Blend existe? {blend_exists} ({os.path.getsize(blend_path) if blend_exists else 0} bytes)")
    print(f"[STATUS] Preview existe? {preview_exists} ({os.path.getsize(render_path) if preview_exists else 0} bytes)")
    if preview_exists:
        qa = blender_automation._inspect_render(render_path)
        print(f"[QA RENDER] {json.dumps(qa)}")
    return blend_exists and preview_exists

if __name__ == "__main__":
    ok_plant = generate_asset(
        "Planta_Estilizada_Vaso",
        "Uma planta estilizada em vaso com folhagem verde larga e caule bem definido",
        "planta_estilizada_vaso.blend"
    )
    ok_tree = generate_asset(
        "Arvore_Estilizada_Decidual",
        "Uma arvore estilizada com tronco afunilado, galhos volumetricos e copa de folhagem organica",
        "arvore_estilizada.blend"
    )
    ok_modifiers = generate_modifiers_asset("objeto_mecanico_modificadores.blend")
    
    print("\n=======================================================")
    print(f"RESULTADOS FINAIS:")
    print(f"Planta em vaso: {'SUCESSO' if ok_plant else 'FALHA'}")
    print(f"Árvore estilizada: {'SUCESSO' if ok_tree else 'FALHA'}")
    print(f"Objeto com modificadores e cortes: {'SUCESSO' if ok_modifiers else 'FALHA'}")
    print("=======================================================")
