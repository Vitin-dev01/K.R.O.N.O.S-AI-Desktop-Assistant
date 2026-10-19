import os
import tempfile
import unittest

from google.genai import types

import brain
import tools


def response_with_tool(name: str, arguments: dict | None = None, text: str = ""):
    call = types.FunctionCall(name=name, args=arguments or {})
    content = types.Content(role="model", parts=[types.Part(function_call=call)])
    candidate = types.Candidate(content=content)
    return type("ModelResponse", (), {"candidates": [candidate], "text": text})()


class ToolRegistryTests(unittest.TestCase):
    def test_every_tool_has_model_facing_operational_metadata(self):
        self.assertEqual(set(tools.TOOL_REGISTRY), set(tools.TOOLS_MAP))
        for name, specification in tools.TOOL_REGISTRY.items():
            with self.subTest(tool=name):
                self.assertTrue(specification.metadata.purpose)
                self.assertTrue(specification.metadata.effects)
                self.assertTrue(specification.metadata.validation)
                self.assertTrue(specification.metadata.recovery)
                self.assertTrue(specification.function.__doc__)

    def test_registry_rejects_invalid_arguments_before_invoking_tool(self):
        specification = tools.TOOL_REGISTRY["set_volume"]
        with self.assertRaises(TypeError):
            specification.invoke({"unknown_parameter": 25})


class WorkspaceFileToolTests(unittest.TestCase):
    def test_file_tools_confine_paths_and_protect_core_files(self):
        outside = os.path.join(tools.BASE_DIR, "..", "outside.txt")
        with self.assertRaises(PermissionError):
            tools._resolve_workspace_path(outside)
        with self.assertRaises(PermissionError):
            tools._resolve_workspace_path(os.path.join(tools.BASE_DIR, ".env"))
        with self.assertRaises(PermissionError):
            tools._resolve_workspace_path(os.path.join(tools.BASE_DIR, "brain.py"))

    def test_overwrites_create_backup_and_replace_atomically(self):
        with tempfile.TemporaryDirectory(
            prefix="kronos-tool-test-",
            dir=tools.BASE_DIR,
        ) as directory:
            path = os.path.join(directory, "data.txt")
            with open(path, "w", encoding="utf-8") as original:
                original.write("before")

            result = tools.write_file(path, "after")

            self.assertIn("Backup:", result)
            with open(path, encoding="utf-8") as updated:
                self.assertEqual(updated.read(), "after")
            with open(path + ".bak", encoding="utf-8") as backup:
                self.assertEqual(backup.read(), "before")


class ToolPlanningLoopTests(unittest.TestCase):
    def test_registered_tools_compose_a_new_write_then_verify_workflow(self):
        with tempfile.TemporaryDirectory(
            prefix="kronos-new-workflow-",
            dir=tools.BASE_DIR,
        ) as directory:
            path = os.path.join(directory, "project_plan.txt")
            first_response = response_with_tool(
                "write_file",
                {
                    "nome_arquivo": path,
                    "conteudo": "Create geometry, save project, verify the render.",
                },
            )
            second_response = response_with_tool(
                "read_file",
                {"nome_arquivo": path},
            )

            class FakeChat:
                def __init__(self):
                    self.responses = [
                        second_response,
                        type("FinalResponse", (), {
                            "candidates": [],
                            "text": "Plan written and read back.",
                        })(),
                    ]
                    self.sent_parts = []

                def send_message(self, parts):
                    self.sent_parts.append(parts)
                    return self.responses.pop(0)

            chat = FakeChat()
            result = brain.KronosBrain()._handle_parallel_tools(
                first_response,
                chat,
            )

            self.assertEqual(result, "Plan written and read back.")
            self.assertEqual(len(chat.sent_parts), 2)
            write_result = chat.sent_parts[0][0].function_response.response
            read_result = chat.sent_parts[1][0].function_response.response
            self.assertTrue(write_result["executed"])
            self.assertTrue(read_result["executed"])
            self.assertEqual(read_result["result"], "Create geometry, save project, verify the render.")

    def test_tool_calls_continue_across_multiple_model_rounds(self):
        first_call = response_with_tool("unregistered_first_tool")
        second_call = response_with_tool("unregistered_second_tool", text="All steps reported.")

        class FakeChat:
            def __init__(self):
                self.responses = [second_call, type("FinalResponse", (), {
                    "candidates": [],
                    "text": "Task finished.",
                })()]
                self.sent_parts = []

            def send_message(self, parts):
                self.sent_parts.append(parts)
                return self.responses.pop(0)

        chat = FakeChat()
        result = brain.KronosBrain()._handle_parallel_tools(first_call, chat)

        self.assertEqual(result, "Task finished.")
        self.assertEqual(len(chat.sent_parts), 2)
        first_response = chat.sent_parts[0][0].function_response.response
        second_response = chat.sent_parts[1][0].function_response.response
        self.assertFalse(first_response["executed"])
        self.assertFalse(second_response["executed"])

    def test_tool_call_limit_is_enforced(self):
        calls = [
            types.Part(function_call=types.FunctionCall(name="unknown", args={}))
            for _ in range(brain.MAX_TOOL_CALLS_PER_TURN + 1)
        ]
        content = types.Content(role="model", parts=calls)
        response = type("ModelResponse", (), {
            "candidates": [types.Candidate(content=content)],
            "text": "",
        })()

        class FakeChat:
            def __init__(self):
                self.responses = [type("FinalResponse", (), {
                    "candidates": [],
                    "text": "Budget reached.",
                })()]
                self.sent_parts = []

            def send_message(self, parts):
                self.sent_parts.append(parts)
                return self.responses.pop(0)

        chat = FakeChat()
        result = brain.KronosBrain()._handle_parallel_tools(response, chat)

        self.assertEqual(result, "Budget reached.")
        responses = [
            part.function_response.response
            for part in chat.sent_parts[0]
        ]
        self.assertEqual(len(responses), brain.MAX_TOOL_CALLS_PER_TURN + 1)
        self.assertEqual(
            sum(bool(item["executed"]) for item in responses),
            0,
        )


if __name__ == "__main__":
    unittest.main()
