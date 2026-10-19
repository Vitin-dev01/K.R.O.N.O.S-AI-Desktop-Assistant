import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import blender_automation
import blender_project_edit


BLENDER_EXECUTABLE = blender_automation._find_blender_executable()


@unittest.skipUnless(BLENDER_EXECUTABLE, "Blender is not installed")
class BlenderProjectEditIntegrationTests(unittest.TestCase):
    def test_edits_a_copy_of_an_existing_project_and_reopens_it(self):
        with tempfile.TemporaryDirectory(
            prefix="kronos-edit-integration-",
            dir=blender_automation.BASE_DIR,
        ) as directory:
            source_path = os.path.join(directory, "source.blend")
            output_path = os.path.join(directory, "edited.blend")
            create_source = (
                "import bpy; "
                f"bpy.ops.wm.save_as_mainfile(filepath={source_path!r})"
            )
            creation = subprocess.run(
                [
                    BLENDER_EXECUTABLE,
                    "--background",
                    "--factory-startup",
                    "--python-expr",
                    create_source,
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            self.assertEqual(creation.returncode, 0, creation.stderr[-3000:])
            original_size = os.path.getsize(source_path)
            edit_script = '''import bpy

obj = bpy.data.objects.get("Cube")
if obj is None:
    raise RuntimeError("Expected startup Cube was not found")
obj.name = "QA_Edited_Cube"
obj.scale.x = 1.4
material = bpy.data.materials.new(name="QA_Edit_Material")
material.diffuse_color = (0.2, 0.45, 0.8, 1.0)
obj.data.materials.append(material)
_kronos_progress("Edited cube name, scale, and material")
'''

            with (
                patch.object(
                    blender_project_edit,
                    "_choose_project_to_edit",
                    return_value=source_path,
                ),
                patch.object(
                    blender_project_edit,
                    "_choose_edited_project_path",
                    return_value=output_path,
                ),
                patch.object(
                    blender_project_edit,
                    "_generate_source",
                    return_value=edit_script,
                ),
            ):
                result = blender_project_edit.edit_blender_project(
                    "Rename the cube, widen it, and give it a blue material."
                )

            self.assertTrue(
                result.startswith("Projeto editado e reaberto com validação:"),
                result,
            )
            self.assertTrue(os.path.isfile(output_path))
            self.assertEqual(os.path.getsize(source_path), original_size)

            report = blender_project_edit._inspect_project(
                BLENDER_EXECUTABLE,
                output_path,
                directory,
            )
            objects = {obj["name"]: obj for obj in report["objects_reported"]}
            self.assertIn("QA_Edited_Cube", objects)
            self.assertIn("QA_Edit_Material", objects["QA_Edited_Cube"]["materials"])
            self.assertGreater(objects["QA_Edited_Cube"]["dimensions"][0], 2.0)
            self.assertTrue(any(name.endswith("_render0001.png") for name in os.listdir(directory)))

    def test_edits_existing_mesh_with_applied_boolean_and_bevel_modifiers(self):
        with tempfile.TemporaryDirectory(
            prefix="kronos-edit-boolean-",
            dir=blender_automation.BASE_DIR,
        ) as directory:
            source_path = os.path.join(directory, "source.blend")
            output_path = os.path.join(directory, "edited_boolean.blend")
            creation = subprocess.run(
                [
                    BLENDER_EXECUTABLE,
                    "--background",
                    "--factory-startup",
                    "--python-expr",
                    f"import bpy; bpy.ops.wm.save_as_mainfile(filepath={source_path!r})",
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            self.assertEqual(creation.returncode, 0, creation.stderr[-3000:])
            original_size = os.path.getsize(source_path)
            edit_script = '''import bpy
import bmesh

obj = bpy.data.objects.get("Cube")
if obj is None:
    raise RuntimeError("Existing Cube is missing")
obj.name = "QA_Boolean_Cut_Cube"
material = bpy.data.materials.new(name="QA_Cut_Material")
material.diffuse_color = (0.18, 0.38, 0.7, 1.0)
obj.data.materials.clear()
obj.data.materials.append(material)

bpy.ops.mesh.primitive_cylinder_add(
    vertices=12,
    radius=0.42,
    depth=3.0,
    location=(0.82, 0.0, 0.0),
)
cutter = bpy.context.object
cutter.name = "QA_Temporary_Cutter"
cutter.data.materials.append(material)

bpy.ops.object.select_all(action="DESELECT")
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
boolean = obj.modifiers.new(name="QA_Boolean_Difference", type="BOOLEAN")
boolean.operation = "DIFFERENCE"
boolean.object = cutter
bpy.ops.object.modifier_apply(modifier=boolean.name)
volume_check = bmesh.new()
volume_check.from_mesh(obj.data)
cut_volume = abs(volume_check.calc_volume(signed=True))
volume_check.free()
if not 0.1 < cut_volume < 7.8:
    raise RuntimeError("Boolean difference did not cut a valid volume")
bpy.data.objects.remove(cutter, do_unlink=True)

bevel = obj.modifiers.new(name="QA_Applied_Bevel", type="BEVEL")
bevel.width = 0.04
bevel.segments = 2
bpy.ops.object.modifier_apply(modifier=bevel.name)
_kronos_progress("Applied boolean cut and bevel to the existing cube")
'''

            with (
                patch.object(
                    blender_project_edit,
                    "_choose_project_to_edit",
                    return_value=source_path,
                ),
                patch.object(
                    blender_project_edit,
                    "_choose_edited_project_path",
                    return_value=output_path,
                ),
                patch.object(
                    blender_project_edit,
                    "_generate_source",
                    return_value=edit_script,
                ),
            ):
                result = blender_project_edit.edit_blender_project(
                    "Cut a side recess into the existing cube and apply a small bevel."
                )

            self.assertTrue(
                result.startswith("Projeto editado e reaberto com validação:"),
                result,
            )
            self.assertEqual(os.path.getsize(source_path), original_size)
            report = blender_project_edit._inspect_project(
                BLENDER_EXECUTABLE,
                output_path,
                directory,
            )
            objects = {obj["name"]: obj for obj in report["objects_reported"]}
            edited = objects["QA_Boolean_Cut_Cube"]
            self.assertGreater(edited["faces"], 6)
            self.assertEqual(edited["modifiers"], [])
            self.assertEqual(edited["materials"], ["QA_Cut_Material"])
            self.assertNotIn("QA_Temporary_Cutter", objects)


if __name__ == "__main__":
    unittest.main()
