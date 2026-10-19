import unittest
from types import SimpleNamespace
from unittest.mock import patch

import roblox_automation


class RobloxRuntimeEvidenceTests(unittest.TestCase):
    def test_runtime_marker_is_emitted_only_after_generated_source(self):
        runtime_source = roblox_automation._build_roblox_runtime_source(
            "local part = script.Parent\npart:SetAttribute('Ready', true)",
            "KRONOS_RUNTIME_OK:Test_Script",
        )

        self.assertLess(
            runtime_source.index("part:SetAttribute('Ready', true)"),
            runtime_source.index('print("KRONOS_RUNTIME_OK:Test_Script")'),
        )
        self.assertEqual(runtime_source.count("local part = script.Parent"), 1)

    @patch("roblox_automation.time.sleep")
    @patch("roblox_automation._roblox_hotkey")
    @patch("roblox_automation._roblox_click")
    @patch("roblox_automation._roblox_press")
    @patch("roblox_automation._roblox_checkpoint")
    @patch("roblox_automation._capture_roblox_output")
    def test_play_is_confirmed_only_by_runtime_marker(
        self,
        capture_output,
        _checkpoint,
        _press,
        _click,
        _hotkey,
        _sleep,
    ):
        capture_output.side_effect = [
            "existing output",
            "existing output\nKRONOS_RUNTIME_OK:Test_Script",
        ]

        report, evidence = roblox_automation._start_roblox_play(
            SimpleNamespace(left=0, top=0, width=1200, height=800),
            "Test_Script",
            "KRONOS_RUNTIME_OK:Test_Script",
        )

        self.assertTrue(report["runtime_confirmed"])
        self.assertTrue(report["play_running"])
        self.assertFalse(report["errors_visible"])
        self.assertEqual(evidence, "KRONOS_RUNTIME_OK:Test_Script")
        self.assertNotIn("part_visible", report)
        self.assertNotIn("script_visible", report)
        capture_output.assert_called()
        _checkpoint.assert_called()
        _press.assert_called_once_with(
            SimpleNamespace(left=0, top=0, width=1200, height=800), "esc"
        )
        _click.assert_called_once()
        _hotkey.assert_called_once()
        _sleep.assert_has_calls([unittest.mock.call(0.3), unittest.mock.call(5.0)])

    @patch("roblox_automation.time.sleep")
    @patch("roblox_automation._roblox_hotkey")
    @patch("roblox_automation._roblox_click")
    @patch("roblox_automation._roblox_press")
    @patch("roblox_automation._roblox_checkpoint")
    @patch("roblox_automation._capture_roblox_output")
    def test_play_without_runtime_marker_is_not_reported_as_success(
        self,
        capture_output,
        _checkpoint,
        _press,
        _click,
        _hotkey,
        _sleep,
    ):
        capture_output.side_effect = ["existing output", "existing output"]

        report, evidence = roblox_automation._start_roblox_play(
            SimpleNamespace(left=0, top=0, width=1200, height=800),
            "Test_Script",
            "KRONOS_RUNTIME_OK:Test_Script",
        )

        self.assertFalse(report["runtime_confirmed"])
        self.assertFalse(report["play_running"])
        self.assertTrue(report["errors_visible"])
        self.assertIn("Nenhuma saída nova", evidence)
        self.assertEqual(capture_output.call_count, 2)
        _checkpoint.assert_called()
        _press.assert_called_once()
        _click.assert_called_once()
        _hotkey.assert_called_once()
        _sleep.assert_has_calls([unittest.mock.call(0.3), unittest.mock.call(5.0)])


if __name__ == "__main__":
    unittest.main()
