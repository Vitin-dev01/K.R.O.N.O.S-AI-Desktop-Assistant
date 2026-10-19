import bpy
import math
import runpy
import traceback
from mathutils import Vector

source_path = 'C:\\Users\\Usuario\\Documents\\K.R.O.N.O.S\\scripts_blender\\Blender_0835407098_2.py'
blend_path = 'C:\\Users\\Usuario\\Documents\\K.R.O.N.O.S\\scripts_blender\\Blender_0835407098_2.blend'
render_path = 'C:\\Users\\Usuario\\Documents\\K.R.O.N.O.S\\scripts_blender\\Blender_0835407098_2_preview.png'

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

try:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    runpy.run_path(source_path, run_name="__main__")
    configure_scene()
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    bpy.ops.render.render(write_still=True)
    print("KRONOS_BLENDER_DONE")
except Exception:
    traceback.print_exc()
    raise
