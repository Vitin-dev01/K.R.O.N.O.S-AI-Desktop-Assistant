import os
import tempfile
import unittest
from unittest.mock import patch

import blender_automation

BLENDER_EXECUTABLE = blender_automation._find_blender_executable()


@unittest.skipUnless(BLENDER_EXECUTABLE, "Blender is not installed")
class RealModelsGenerationTests(unittest.TestCase):
    """Gera modelos reais no Blender: planta em vaso, árvore e pedra estilizada."""

    def test_generate_stylized_potted_plant(self):
        with tempfile.TemporaryDirectory(prefix="kronos-real-plant-", dir=blender_automation.BASE_DIR) as directory:
            blend_target = os.path.join(directory, "planta_vaso.blend")
            with (
                patch.object(blender_automation, "_choose_save_path", return_value=blend_target),
                patch.object(blender_automation, "_should_show_blender", return_value=False),
            ):
                result = blender_automation.generate_blender_script(
                    "QA_Planta_Vaso",
                    "Uma planta estilizada em vaso com caules e folhas verdes bem definidas",
                )
            self.assertTrue(result.startswith("Modelo criado e validado."), result)
            self.assertTrue(os.path.isfile(blend_target))
            preview_png = os.path.splitext(blend_target)[0] + "_preview.png"
            self.assertTrue(os.path.isfile(preview_png))
            render_qa = blender_automation._inspect_render(preview_png)
            self.assertIsNotNone(render_qa)
            self.assertGreater(render_qa["foreground_ratio"], 0.005)

    def test_generate_stylized_rock(self):
        with tempfile.TemporaryDirectory(prefix="kronos-real-rock-", dir=blender_automation.BASE_DIR) as directory:
            blend_target = os.path.join(directory, "pedra_estilizada.blend")
            with (
                patch.object(blender_automation, "_choose_save_path", return_value=blend_target),
                patch.object(blender_automation, "_should_show_blender", return_value=False),
            ):
                result = blender_automation.generate_blender_script(
                    "QA_Pedra_Estilizada",
                    "Uma pedra estilizada facetada com chanfros e volume angular",
                )
            self.assertTrue(result.startswith("Modelo criado e validado."), result)
            self.assertTrue(os.path.isfile(blend_target))
            preview_png = os.path.splitext(blend_target)[0] + "_preview.png"
            self.assertTrue(os.path.isfile(preview_png))
            render_qa = blender_automation._inspect_render(preview_png)
            self.assertIsNotNone(render_qa)
            self.assertGreater(render_qa["foreground_ratio"], 0.005)


if __name__ == "__main__":
    unittest.main()
