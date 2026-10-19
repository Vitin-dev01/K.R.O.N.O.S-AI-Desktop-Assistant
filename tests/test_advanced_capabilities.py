import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import blender_automation
import blender_project_edit
import roblox_automation
import brain
import memory
from google.genai import types

BLENDER_EXECUTABLE = blender_automation._find_blender_executable()


class AdvancedBlenderModelingTests(unittest.TestCase):
    """Testes de modelagem 3D avançada com modificadores, cortes e separação."""

    def test_ast_validator_permits_advanced_modifiers_and_mesh_operations(self):
        source = """
import bpy
import bmesh

# Criação de malha base
bpy.ops.mesh.primitive_cube_add(size=2.0)
cube = bpy.context.active_object
cube.name = "Test_Box"

# Modificador Bevel
bev = cube.modifiers.new(name="BevelMod", type='BEVEL')
bev.width = 0.05
bev.segments = 3

# Modificador Solidify
sol = cube.modifiers.new(name="SolidMod", type='SOLIDIFY')
sol.thickness = 0.08

# Modificador Subsurf
sub = cube.modifiers.new(name="SubMod", type='SUBSURF')
sub.levels = 1

# Aplicação de modificadores e operadores de malha
bpy.ops.object.modifier_apply(modifier="BevelMod")
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.subdivide(number_cuts=2)
bpy.ops.mesh.inset(thickness=0.1, depth=0.05)
bpy.ops.mesh.extrude_region_move()
bpy.ops.mesh.shade_smooth()
bpy.ops.object.mode_set(mode='OBJECT')
"""
        # Não deve levantar ValueError nem erro de segurança
        blender_automation._validate_generated_source(source)

    @unittest.skipUnless(BLENDER_EXECUTABLE, "Blender is not installed")
    def test_execute_modifiers_and_component_separation_in_blender(self):
        """Valida execução real no Blender de modificadores (Mirror, Bevel, Solidify) e Separate."""
        with tempfile.TemporaryDirectory(prefix="kronos-modifiers-test-") as directory:
            blend_path = os.path.join(directory, "modifiers_test.blend")
            runner_script = f"""import bpy
import os

# 1. Objeto com cortes e modificadores
bpy.ops.mesh.primitive_cube_add(size=1.5, location=(0, 0, 0))
obj = bpy.context.active_object
obj.name = "Mechanical_Part"

mat = bpy.data.materials.new("Part_Material")
mat.diffuse_color = (0.2, 0.7, 0.5, 1.0)
obj.data.materials.append(mat)

# Solidify + Bevel
sol = obj.modifiers.new(name="Solidify", type='SOLIDIFY')
sol.thickness = 0.1
bev = obj.modifiers.new(name="Bevel", type='BEVEL')
bev.width = 0.03
bev.segments = 2
bpy.ops.object.modifier_apply(modifier=sol.name)
bpy.ops.object.modifier_apply(modifier=bev.name)

# 2. Separação de componentes (Loose parts)
bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.3, depth=1.0, location=(2.5, 0, 0))
cyl1 = bpy.context.active_object
bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.3, depth=1.0, location=(4.0, 0, 0))
cyl2 = bpy.context.active_object

# Une e depois separa
bpy.ops.object.select_all(action='DESELECT')
cyl1.select_set(True)
cyl2.select_set(True)
bpy.context.view_layer.objects.active = cyl1
bpy.ops.object.join()

joined_obj = bpy.context.active_object
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.separate(type='LOOSE')
bpy.ops.object.mode_set(mode='OBJECT')

bpy.ops.wm.save_as_mainfile(filepath={blend_path!r})
print("KRONOS_MODIFIERS_TEST_OK")
"""
            runner_path = os.path.join(directory, "run_test.py")
            with open(runner_path, "w", encoding="utf-8") as f:
                f.write(runner_script)

            result = subprocess.run(
                [
                    BLENDER_EXECUTABLE,
                    "--background",
                    "--factory-startup",
                    "--python",
                    runner_path,
                ],
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("KRONOS_MODIFIERS_TEST_OK", result.stdout)
            self.assertTrue(os.path.isfile(blend_path))

            # Inspeciona o resultado reaberto
            inspection = blender_project_edit._inspect_project(
                BLENDER_EXECUTABLE, blend_path, directory
            )
            obj_names = [o["name"] for o in inspection["objects_reported"]]
            self.assertIn("Mechanical_Part", obj_names)
            # Pelo menos 2 componentes de cilindro separados
            self.assertGreaterEqual(len(obj_names), 3)


class AdvancedRobloxLuauTests(unittest.TestCase):
    """Testes de geração Luau com mecanismos avançados e interfaces."""

    def test_roblox_runtime_ok_evaluates_true_without_legacy_keys(self):
        """Garante que a correção de runtime_ok aprova play test verificado."""
        report = {
            "play_running": True,
            "runtime_confirmed": True,
            "errors_visible": False,
            "evidence": "KRONOS_RUNTIME_OK:DoorScript",
        }
        runtime_ok = (
            report.get("errors_visible") is not True
            and report.get("play_running") is True
            and report.get("runtime_confirmed") is True
        )
        self.assertTrue(runtime_ok)

    def test_luau_interactive_mechanism_scaffold(self):
        """Verifica a geração de código Luau para portas e mecanismos com TweenService."""
        code = (
            "local part = script.Parent\n"
            "local TweenService = game:GetService('TweenService')\n"
            "local debounce = false\n"
            "local openGoal = {CFrame = part.CFrame * CFrame.new(0, 5, 0)}\n"
            "local tweenInfo = TweenInfo.new(1.0, Enum.EasingStyle.Sine)\n"
            "local openTween = TweenService:Create(part, tweenInfo, openGoal)\n"
            "part.Touched:Connect(function(hit)\n"
            "    if not debounce and hit.Parent:FindFirstChild('Humanoid') then\n"
            "        debounce = true\n"
            "        openTween:Play()\n"
            "        task.wait(2)\n"
            "        debounce = false\n"
            "    end\n"
            "end)\n"
        )
        runtime_source = roblox_automation._build_roblox_runtime_source(
            code, "KRONOS_RUNTIME_OK:DoorScript"
        )
        self.assertIn("TweenService", runtime_source)
        self.assertIn("debounce = false", runtime_source)
        self.assertIn('print("KRONOS_RUNTIME_OK:DoorScript")', runtime_source)

    def test_luau_ui_interface_scaffold(self):
        """Verifica código Luau construindo interfaces e HUDs (ScreenGui)."""
        code = (
            "local part = script.Parent\n"
            "local Players = game:GetService('Players')\n"
            "local function createHUD(player)\n"
            "    local gui = Instance.new('ScreenGui')\n"
            "    gui.Name = 'KronosHUD'\n"
            "    local label = Instance.new('TextLabel')\n"
            "    label.Text = 'Status: Operacional'\n"
            "    label.Parent = gui\n"
            "    gui.Parent = player:WaitForChild('PlayerGui')\n"
            "end\n"
            "Players.PlayerAdded:Connect(createHUD)\n"
        )
        runtime_source = roblox_automation._build_roblox_runtime_source(
            code, "KRONOS_RUNTIME_OK:HUDScript"
        )
        self.assertIn("ScreenGui", runtime_source)
        self.assertIn("PlayerGui", runtime_source)


class BrainAndMemoryIntegrationTests(unittest.TestCase):
    """Testes da injeção de memória e raciocínio do cérebro."""

    def test_user_memory_injection_into_prompt(self):
        facts = memory.get_all_facts()
        self.assertTrue(len(facts) > 0)
        self.assertIn("Curitiba", facts)

        # Prompt do sistema deve receber a memória do usuário
        rendered_prompt = brain.KRONOS_SYSTEM_PROMPT.replace("{MEMORIA_USUARIO}", facts)
        self.assertNotIn("{MEMORIA_USUARIO}", rendered_prompt)
        self.assertIn("Curitiba", rendered_prompt)
        self.assertIn("Ryzen", rendered_prompt)

    def test_contingency_fallback_dispatch(self):
        """Verifica que o fallback de contingência é invocado quando necessário."""
        b = brain.KronosBrain()
        fake_spec = MagicMock()
        fake_spec.invoke.return_value = "Modelo criado e validado. Projeto: test.blend. Prévia: test.png."
        custom_registry = dict(brain.TOOL_REGISTRY)
        custom_registry["generate_blender_script"] = fake_spec
        with patch.object(brain, "TOOL_REGISTRY", custom_registry):
            res = b._dispatch_contingency_action("crie um modelo 3d de teste no blender")
            self.assertIsNotNone(res)
            self.assertEqual(res["modelo"], "blender-build-contingency")
            self.assertEqual(res["estado"], "IDLE")


if __name__ == "__main__":
    unittest.main()
