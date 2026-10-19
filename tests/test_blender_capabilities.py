import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import blender_automation


BLENDER_EXECUTABLE = blender_automation._find_blender_executable()


class BlenderProcessLifecycleTests(unittest.TestCase):
    class ActiveProcess:
        pid = 12345
        returncode = None

        def poll(self):
            return None

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("blender", timeout)

    class ExitedProcess:
        pid = 12345
        returncode = 1

        def poll(self):
            return self.returncode

    def test_terminal_done_is_success_even_if_visible_process_stays_open(self):
        with tempfile.TemporaryDirectory(prefix="kronos-blender-status-") as directory:
            status_path = os.path.join(directory, "status.json")
            with open(status_path, "w", encoding="utf-8") as status_file:
                json.dump({"status": "done", "quality": {"faces": 1000}}, status_file)

            with patch.object(
                blender_automation,
                "_stop_process_tree",
                return_value=True,
            ) as stop_process:
                status, diagnostic, forced = (
                    blender_automation._monitor_blender_process(
                        self.ActiveProcess(),
                        status_path,
                        os.path.join(directory, "progress.json"),
                        1,
                    )
                )

            self.assertEqual(status["status"], "done")
            self.assertEqual(diagnostic, "")
            self.assertTrue(forced)
            stop_process.assert_called_once()

    def test_error_status_is_terminal_and_preserves_blender_diagnostic(self):
        with tempfile.TemporaryDirectory(prefix="kronos-blender-status-") as directory:
            status_path = os.path.join(directory, "status.json")
            with open(status_path, "w", encoding="utf-8") as status_file:
                json.dump({"status": "error", "error": "invalid mesh"}, status_file)

            status, diagnostic, forced = blender_automation._monitor_blender_process(
                self.ExitedProcess(),
                status_path,
                os.path.join(directory, "progress.json"),
                1,
            )

            self.assertEqual(status["status"], "error")
            self.assertEqual(diagnostic, "")
            self.assertFalse(forced)

    def test_timeout_cleans_up_and_does_not_report_a_success_state(self):
        with tempfile.TemporaryDirectory(prefix="kronos-blender-status-") as directory:
            process = self.ActiveProcess()
            with patch.object(
                blender_automation,
                "_stop_process_tree",
                return_value=True,
            ) as stop_process:
                status, diagnostic, forced = (
                    blender_automation._monitor_blender_process(
                        process,
                        os.path.join(directory, "status.json"),
                        os.path.join(directory, "progress.json"),
                        0,
                    )
                )

            self.assertIsNone(status)
            self.assertIn("excedeu o limite", diagnostic)
            self.assertTrue(forced)
            stop_process.assert_called_once_with(process)

    def test_malformed_status_is_not_treated_as_success(self):
        with tempfile.TemporaryDirectory(prefix="kronos-blender-status-") as directory:
            status_path = os.path.join(directory, "status.json")
            with open(status_path, "w", encoding="utf-8") as status_file:
                status_file.write("{invalid")

            with self.assertRaises(json.JSONDecodeError):
                blender_automation._monitor_blender_process(
                    self.ActiveProcess(),
                    status_path,
                    os.path.join(directory, "progress.json"),
                    1,
                )


@unittest.skipUnless(BLENDER_EXECUTABLE, "Blender is not installed")
class BlenderCapabilityIntegrationTests(unittest.TestCase):
    def test_botanical_intent_does_not_treat_negated_tree_as_tree(self):
        self.assertEqual(
            blender_automation._detect_botanical_kind(
                "stylized botanical houseplant, not a tree"
            ),
            "plant",
        )
        self.assertEqual(
            blender_automation._detect_botanical_kind("low-poly oak tree"),
            "tree",
        )

    def test_asset_kind_distinguishes_single_rocks_from_collections(self):
        self.assertEqual(
            blender_automation._detect_asset_kind("one stylized low-poly rock"),
            "rock",
        )
        self.assertEqual(
            blender_automation._detect_asset_kind("uma pedra estilizada"),
            "rock",
        )
        self.assertEqual(
            blender_automation._detect_asset_kind("a pile of rocks"),
            "generic",
        )

    def test_generated_source_rejects_known_invalid_bmesh_operator_names(self):
        invalid_source = (
            "import bmesh\n"
            "bm = bmesh.new()\n"
            "bmesh.ops.create_ico_sphere(bm, subdivisions=1, radius=0.5)\n"
        )
        with self.assertRaisesRegex(
            ValueError,
            "Operador BMesh inexistente.*create_icosphere",
        ):
            blender_automation._validate_generated_source(invalid_source)

        valid_source = (
            "import bmesh\n"
            "bm = bmesh.new()\n"
            "bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.5)\n"
        )
        blender_automation._validate_generated_source(valid_source)

        with self.assertRaisesRegex(
            ValueError,
            "bmesh.ops.dupe_mesh.*mesh.from_pydata",
        ):
            blender_automation._validate_generated_source(
                "import bmesh\n"
                "bm = bmesh.new()\n"
                "bmesh.ops.dupe_mesh(bm, bm=other)\n"
            )

        invalid_cylinder_source = (
            "import bpy\n"
            "bpy.ops.mesh.primitive_cylinder_add(radius1=0.5, radius2=1.0)\n"
        )
        with self.assertRaisesRegex(
            ValueError,
            "primitive_cylinder_add não aceita radius1/radius2",
        ):
            blender_automation._validate_generated_source(
                invalid_cylinder_source
            )

    def test_runner_writes_terminal_status_and_closes_visible_blender(self):
        runner = blender_automation._build_runner(
            "source.py",
            "project.blend",
            "preview.png",
            "project.blend",
            "status.json",
            "progress.json",
            True,
            "tree",
        )

        self.assertIn('"status": "done"', runner)
        self.assertIn("for attempt in range(20)", runner)
        self.assertIn("bpy.ops.wm.quit_blender()", runner)
        self.assertIn('"process_id": os.getpid()', runner)
        compile(runner, "generated_blender_runner.py", "exec")
        saved_validator = blender_automation._build_saved_project_validator(
            "rock",
            "project.blend",
            "",
            "",
        )
        compile(saved_validator, "generated_saved_validator.py", "exec")

    def _run_model_pipeline(self, kind, description, export_extension):
        with tempfile.TemporaryDirectory(
            prefix=f"kronos-{kind}-{export_extension[1:]}-",
            dir=blender_automation.BASE_DIR,
        ) as directory:
            selected_path = os.path.join(directory, f"{kind}{export_extension}")
            generated_source = blender_automation._build_botanical_source(
                kind,
                description,
            )

            with (
                patch.object(
                    blender_automation,
                    "_choose_save_path",
                    return_value=selected_path,
                ),
                patch.object(
                    blender_automation,
                    "_should_show_blender",
                    return_value=False,
                ),
                patch.object(
                    blender_automation,
                    "_generate_source",
                    return_value=generated_source,
                ),
            ):
                result = blender_automation.generate_blender_script(
                    f"QA_{kind}", description
                )

            self.assertTrue(result.startswith("Modelo criado e validado.") or
                            result.startswith("Modelo exportado e reimportado:"), result)
            blend_path = (
                selected_path
                if export_extension == ".blend"
                else os.path.splitext(selected_path)[0] + "_project.blend"
            )
            render_path = os.path.splitext(selected_path)[0] + "_preview.png"
            self.assertTrue(os.path.isfile(blend_path))
            self.assertGreater(os.path.getsize(blend_path), 0)
            self.assertTrue(os.path.isfile(render_path))
            render_report = blender_automation._inspect_render(render_path)
            self.assertIsNotNone(render_report)
            self.assertGreater(render_report["foreground_ratio"], 0.003)
            self.assertTrue(os.path.isfile(selected_path))
            if export_extension != ".blend":
                self.assertGreater(os.path.getsize(selected_path), 0)

            reopened = blender_automation._validate_saved_project(
                BLENDER_EXECUTABLE,
                blend_path,
                selected_path if export_extension != ".blend" else "",
                export_extension if export_extension != ".blend" else "",
                kind,
                directory,
            )
            self.assertTrue(reopened["reopened"])
            self.assertGreater(reopened["faces"], 0)
            self.assertGreater(reopened["leaf_objects"], 0)
            if kind == "plant":
                self.assertGreaterEqual(reopened["leaf_objects"], 15)
            else:
                self.assertTrue(
                    reopened["separated_leaf_parts"] >= 5
                    or reopened["leaves_are_separate"]
                )
            if export_extension != ".blend":
                self.assertGreater(reopened["roundtrip_imported_meshes"], 0)
            return reopened, render_report

    def test_stylized_plant_has_individual_leaf_meshes_and_valid_render(self):
        reopened, render = self._run_model_pipeline(
            "plant",
            "stylized plant with its own stems and distributed individual leaves",
            ".blend",
        )

        self.assertGreaterEqual(reopened["leaf_objects"], 15)
        self.assertGreater(render["width"], 128)
        self.assertGreater(render["height"], 128)

    def test_potted_plant_keeps_most_leaves_visible_above_the_container(self):
        reopened, _render = self._run_model_pipeline(
            "plant",
            "stylized houseplant in a pot with distributed individual leaves",
            ".blend",
        )
        self.assertGreaterEqual(reopened["leaf_objects"], 15)

    def test_low_poly_tree_separates_leaves_and_roundtrips_supported_exports(self):
        for extension in (".glb", ".fbx", ".obj"):
            with self.subTest(export_format=extension):
                reopened, render = self._run_model_pipeline(
                    "tree",
                    "low-poly tree with trunk, branches, a layered canopy, and real leaves",
                    extension,
                )
                self.assertGreaterEqual(reopened["separated_leaf_parts"], 5)
                self.assertGreater(reopened["roundtrip_imported_meshes"], 0)
                self.assertGreater(render["foreground_ratio"], 0.003)

    def test_generic_tree_uses_explicit_fallback_after_ai_generation_fails(self):
        with tempfile.TemporaryDirectory(
            prefix="kronos-tree-fallback-",
            dir=blender_automation.BASE_DIR,
        ) as directory:
            selected_path = os.path.join(directory, "fallback-tree.blend")
            with (
                patch.object(
                    blender_automation,
                    "_choose_save_path",
                    return_value=selected_path,
                ),
                patch.object(
                    blender_automation,
                    "_should_show_blender",
                    return_value=False,
                ),
                patch.object(
                    blender_automation,
                    "_generate_source",
                    side_effect=RuntimeError("simulated AI source failures"),
                ) as generate_source,
            ):
                result = blender_automation.generate_blender_script(
                    "KRONOS_Fallback_Tree",
                    "Create a generic stylized low-poly tree with trunk, branches, and leaves",
                )

            self.assertTrue(
                result.startswith(
                    "Modelo criado e validado com composição procedural de segurança"
                ),
                result,
            )
            self.assertEqual(
                generate_source.call_count,
                blender_automation.MAX_SCRIPT_CORRECTIONS + 1,
            )
            self.assertTrue(os.path.isfile(selected_path))
            preview_path = os.path.splitext(selected_path)[0] + "_preview.png"
            self.assertTrue(os.path.isfile(preview_path))


if __name__ == "__main__":
    unittest.main()
