import bpy
import json
import math
import os
import runpy
import time
import traceback
from mathutils import Vector

source_path = 'C:\\Users\\Usuario\\Documents\\K.R.O.N.O.S\\scripts_blender\\Blender_d718b2049b.py'
blend_path = 'C:\\Users\\Usuario\\Documents\\Blender_d718b2049b_project.blend'
render_path = 'C:\\Users\\Usuario\\Documents\\Blender_d718b2049b_preview.png'
export_path = 'C:\\Users\\Usuario\\Documents\\Blender_d718b2049b.fbx'
status_path = 'C:\\Users\\Usuario\\Documents\\K.R.O.N.O.S\\scripts_blender\\Blender_d718b2049b_status.json'
visible = True

def write_status(status):
    temporary_path = status_path + ".tmp"
    with open(temporary_path, "w", encoding="utf-8") as status_file:
        json.dump(status, status_file)
    os.replace(temporary_path, status_path)

def configure_scene():
    scene = bpy.context.scene
    geometry_objects = [
        obj for obj in scene.objects
        if obj.type in {"MESH", "CURVE", "SURFACE", "FONT", "META"}
    ]
    if not geometry_objects:
        raise RuntimeError("O script terminou sem criar geometria 3D renderizável.")

    corners = [
        obj.matrix_world @ Vector(corner)
        for obj in geometry_objects
        for corner in obj.bound_box
    ]
    minimum = Vector(tuple(min(point[i] for point in corners) for i in range(3)))
    maximum = Vector(tuple(max(point[i] for point in corners) for i in range(3)))
    center = (minimum + maximum) * 0.5
    radius = max((maximum - minimum).length * 0.5, 1.0)

    camera_data = bpy.data.cameras.new("KRONOS_Camera")
    camera = bpy.data.objects.new("KRONOS_Camera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = center + Vector((1.8, -2.4, 1.5)).normalized() * radius * 3.2
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.lens = 50
    scene.camera = camera

    def add_area_light(name, offset, energy, size):
        data = bpy.data.lights.new(name, type="AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        light = bpy.data.objects.new(name, data)
        scene.collection.objects.link(light)
        light.location = center + Vector(offset).normalized() * radius * 2.5
        light.rotation_euler = (center - light.location).to_track_quat("-Z", "Y").to_euler()

    add_area_light("KRONOS_Key_Light", (1.0, -1.5, 2.0), 1800, radius * 1.5)
    add_area_light("KRONOS_Fill_Light", (-1.5, -0.5, 0.8), 1000, radius * 1.8)
    add_area_light("KRONOS_Rim_Light", (0.2, 1.5, 1.5), 2200, radius * 1.2)

    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("KRONOS_World")
        scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background:
        background.inputs["Color"].default_value = (0.12, 0.14, 0.18, 1)
        background.inputs["Strength"].default_value = 0.35

    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 1024
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = render_path
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.view_transform = "AgX"
    scene.camera.data.dof.use_dof = False
    if visible:
        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type == "VIEW_3D":
                    region = area.spaces.active.region_3d
                    region.view_location = center
                    region.view_distance = radius * 1.8
                    region.view_rotation = camera.rotation_euler.to_quaternion()
                    region.view_perspective = "PERSP"
                    area.spaces.active.overlay.show_extras = False
                    area.spaces.active.overlay.show_floor = False
                    area.spaces.active.overlay.show_axis_x = False
                    area.spaces.active.overlay.show_axis_y = False
                    area.spaces.active.shading.color_type = "MATERIAL"
                    area.spaces.active.shading.light = "STUDIO"

def export_model():
    extension = export_path.lower().rsplit(".", 1)[-1]
    if extension == "blend":
        return

    geometry = [
        obj for obj in bpy.context.scene.objects
        if obj.type in {"MESH", "CURVE", "SURFACE", "FONT", "META"}
    ]
    bpy.ops.object.select_all(action="DESELECT")
    for obj in geometry:
        obj.select_set(True)
    if geometry:
        bpy.context.view_layer.objects.active = geometry[0]

    if extension == "fbx":
        bpy.ops.export_scene.fbx(
            filepath=export_path,
            use_selection=True,
            object_types={"MESH", "EMPTY", "ARMATURE", "OTHER"},
        )
    elif extension == "glb":
        bpy.ops.export_scene.gltf(
            filepath=export_path,
            export_format="GLB",
            use_selection=True,
        )
    elif extension == "obj":
        bpy.ops.wm.obj_export(
            filepath=export_path,
            export_selected_objects=True,
        )
    else:
        raise RuntimeError("Formato de exportação não suportado: ." + extension)

def optimize_model_objects():
    mesh_objects = [
        obj for obj in bpy.context.scene.objects
        if obj.type == "MESH" and obj.parent is None
    ]
    if len(mesh_objects) <= 100:
        return
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in mesh_objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = mesh_objects[0]
    result = bpy.ops.object.join()
    if "FINISHED" not in result:
        raise RuntimeError(
            "Não foi possível otimizar o modelo: há mais de 100 malhas "
            "independentes e o Blender não conseguiu combiná-las."
        )
    print(
        "KRONOS_BLENDER_STEP Otimizando "
        + str(len(mesh_objects))
        + " malhas low-poly",
        flush=True,
    )

def _kronos_progress(label="Montando o modelo"):
    print("KRONOS_BLENDER_STEP " + str(label), flush=True)
    if bpy.app.background:
        return
    geometry_objects = [
        obj for obj in bpy.context.scene.objects
        if obj.type in {"MESH", "CURVE", "SURFACE", "FONT", "META"}
    ]
    if geometry_objects:
        corners = [
            obj.matrix_world @ Vector(corner)
            for obj in geometry_objects
            for corner in obj.bound_box
        ]
        minimum = Vector(tuple(min(point[i] for point in corners) for i in range(3)))
        maximum = Vector(tuple(max(point[i] for point in corners) for i in range(3)))
        center = (minimum + maximum) * 0.5
        radius = max((maximum - minimum).length * 0.5, 1.0)
        view_rotation = Vector((1.8, -2.4, 1.5)).to_track_quat("Z", "Y")
        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type == "VIEW_3D":
                    region = area.spaces.active.region_3d
                    region.view_location = center
                    region.view_distance = radius * 1.8
                    region.view_rotation = view_rotation
                    region.view_perspective = "PERSP"
                    area.header_text_set("KRONOS | " + str(label)[:100])
    bpy.context.view_layer.update()
    bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=2)
    time.sleep(0.15)

try:
    print("KRONOS_BLENDER_STEP Preparando a cena", flush=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    runpy.run_path(
        source_path,
        run_name="__main__",
        init_globals={"_kronos_progress": _kronos_progress},
    )
    optimize_model_objects()
    _kronos_progress("Modelo pronto; preparando luz e enquadramento")
    configure_scene()
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.header_text_set(None)
    print("KRONOS_BLENDER_STEP Salvando o projeto", flush=True)
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print("KRONOS_BLENDER_STEP Exportando e renderizando a prévia", flush=True)
    export_model()
    bpy.ops.render.render(write_still=True)
    write_status({"status": "done"})
    print("KRONOS_BLENDER_DONE")
except Exception as error:
    error_details = traceback.format_exc()
    print(error_details)
    write_status({"status": "error", "error": error_details})
    if bpy.app.background:
        raise
    bpy.ops.wm.quit_blender()
