"""Central metadata and validated dispatch for KRONOS tools."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class ToolMetadata:
    purpose: str
    environment: str
    preconditions: str
    effects: str
    validation: str
    recovery: str
    authorization: str
    parameters: Mapping[str, str]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    function: Callable[..., Any]
    metadata: ToolMetadata
    signature: inspect.Signature

    def invoke(self, arguments: Mapping[str, Any]) -> Any:
        if not isinstance(arguments, Mapping):
            raise TypeError("Tool arguments must be an object.")
        bound = self.signature.bind(**dict(arguments))
        bound.apply_defaults()
        return self.function(*bound.args, **bound.kwargs)

    def model_description(self) -> str:
        parameters = "\n".join(
            f"  {name}: {description}"
            for name, description in self.metadata.parameters.items()
        )
        return (
            f"{self.metadata.purpose}\n"
            f"Environment: {self.metadata.environment}\n"
            f"Preconditions: {self.metadata.preconditions}\n"
            f"Effects: {self.metadata.effects}\n"
            f"Validation: {self.metadata.validation}\n"
            f"Recovery: {self.metadata.recovery}\n"
            f"Authorization: {self.metadata.authorization}\n"
            f"Arguments:\n{parameters or '  none'}"
        )


_METADATA: dict[str, ToolMetadata] = {
    "generate_roblox_script": ToolMetadata(
        "Implement a task-specific Luau feature in the open Roblox Studio place, install it, save, and run a play test.",
        "Roblox Studio on Windows.",
        "A Roblox Studio place must be open; the user request must describe the intended behavior.",
        "May add or update Studio objects/scripts, save the place, and start a play test.",
        "Checks script installation and play-test evidence from Studio.",
        "Uses bounded correction attempts based on captured Studio errors; reports failure if verification does not pass.",
        "Requires an explicit user request to create or change the place.",
        {
            "nome_script": "Readable name for the task script/artifact.",
            "descricao_mecanica": "Complete requested behavior, constraints, and relevant existing-project context.",
        },
    ),
    "play_roblox_studio": ToolMetadata(
        "Start a play test in the currently open Roblox Studio place.",
        "Roblox Studio on Windows.",
        "A place must be open in Roblox Studio.",
        "Changes Studio focus and starts Play; it does not create project content.",
        "Confirms that the Studio window was found and the Play input was sent.",
        "Reports the window or activation error; does not silently create a place.",
        "Requires an explicit user request to start play testing.",
        {},
    ),
    "blender_render_background": ToolMetadata(
        "Render an existing .blend file without opening a visible Blender window.",
        "Installed Blender on Windows.",
        "The requested .blend file must exist and be readable.",
        "Creates a render output adjacent to the project.",
        "Checks Blender's completion result and render output.",
        "Returns Blender diagnostics on failure; source project is not intentionally edited.",
        "Requires a user request to render the named project.",
        {"arquivo_blend": "Path to the existing Blender project to render."},
    ),
    "generate_blender_script": ToolMetadata(
        "Generate and run task-specific Blender Python, then validate and save the resulting model.",
        "Installed Blender; compatibility is checked against the installed executable.",
        "Requires a clear modeling task and user-selected save destination.",
        "Creates a new scene, project, and preview; it does not edit an existing .blend in place.",
        "Checks geometry, materials, dimensions, saved-project reopening, and the rendered preview.",
        "Uses bounded code-correction attempts and reports the last specific error.",
        "Requires an explicit user request to create a model.",
        {
            "nome_script": "Short, readable artifact name.",
            "descricao_tarefa": "Full modeling requirements, object type, style, parts, and constraints.",
        },
    ),
    "edit_blender_project": ToolMetadata(
        "Inspect an existing Blender project and apply a task-specific edit to a separate copy.",
        "Installed Blender; uses only the saved state of the selected .blend file.",
        "Requires an existing .blend and user-selected output path.",
        "Opens the source read-only and saves an edited copy; if the chosen output exists, preserves a backup before replacement.",
        "Compares scene state before/after, validates mesh coordinates, reopens the result, and attempts a preview render.",
        "Uses bounded code-correction attempts; failed edits leave the selected source file unchanged.",
        "Requires an explicit user request and user selection of source and output project.",
        {"descricao_tarefa": "Exact requested edit and constraints; the tool supplies a verified inventory of the selected saved scene."},
    ),
    "set_volume": ToolMetadata(
        "Set the Windows master volume.",
        "Windows audio endpoint.",
        "An active audio output device must be available.",
        "Changes system-wide master volume.",
        "Returns the applied volume or the device/API error.",
        "Reports device/API failure; no retry is performed.",
        "Requires an explicit user request to change volume.",
        {"level": "Target volume percentage from 0 to 100."},
    ),
    "send_notification": ToolMetadata(
        "Show a Windows toast notification.",
        "Windows 11 notification service.",
        "Notification service must be available.",
        "Displays a desktop notification.",
        "Returns process-launch status; Windows delivery is not independently acknowledged.",
        "Reports launch errors; no retry is performed.",
        "Requires a user request to display a notification.",
        {"titulo": "Short notification title.", "mensagem": "Notification body."},
    ),
    "play_music": ToolMetadata(
        "Search for and open a requested music track in YouTube or Spotify.",
        "Configured web browser and network access.",
        "A non-empty search query is required.",
        "Opens a browser tab or music application search.",
        "Confirms a result URL/tab was opened, not audio playback.",
        "Falls back to a search page when direct lookup fails.",
        "Requires a user request to open music.",
        {"busca": "Artist, track, or query.", "plataforma": "YouTube or Spotify; defaults to YouTube."},
    ),
    "media_control": ToolMetadata(
        "Send a system media key for play, pause, next, previous, or mute.",
        "Windows media-key handling.",
        "A compatible media application may be open.",
        "Controls the active media session or system mute.",
        "Confirms that the key event was sent, not the application's resulting state.",
        "Reports input errors; no retry is performed.",
        "Requires an explicit user request for the media action.",
        {"acao": "play, pause, next, previous, or mute."},
    ),
    "read_clipboard": ToolMetadata(
        "Read the current clipboard text.",
        "Windows clipboard.",
        "Clipboard access must be available.",
        "Reads potentially sensitive user clipboard data.",
        "Returns clipboard text truncated to a bounded length.",
        "Reports clipboard access errors.",
        "Requires an explicit user request to read clipboard contents.",
        {},
    ),
    "copy_to_clipboard": ToolMetadata(
        "Copy text to the Windows clipboard.",
        "Windows clipboard.",
        "Clipboard access must be available.",
        "Replaces current clipboard contents.",
        "Reports whether the clipboard write succeeded.",
        "Reports clipboard access errors.",
        "Requires an explicit user request to replace clipboard contents.",
        {"texto": "Exact text to place on the clipboard."},
    ),
    "get_full_telemetry": ToolMetadata(
        "Read system resource and network telemetry.",
        "Windows system APIs.",
        "Telemetry counters must be available.",
        "Reads CPU, memory, disk, network, and cached weather data.",
        "Returns measured values and their units.",
        "Reports underlying API errors to the caller.",
        "Requires a user request to inspect system telemetry.",
        {},
    ),
    "analyze_screen": ToolMetadata(
        "Capture and analyze the current desktop screen.",
        "Windows desktop capture and configured vision model.",
        "Desktop capture and network access must be available.",
        "Captures visible screen contents and sends the image to the vision model.",
        "Returns the model's screen analysis or a capture/model error.",
        "Uses bounded model/key retries; reports failure rather than claiming an inspection.",
        "Requires a user request to inspect the screen.",
        {"pergunta": "Specific question about the current screen."},
    ),
    "write_file": ToolMetadata(
        "Write a text file inside the KRONOS workspace.",
        "KRONOS workspace filesystem.",
        "Destination must be inside the workspace and not a protected secret/configuration file.",
        "Creates or replaces the requested file; existing content is backed up.",
        "Checks that the write completes and returns the workspace-relative path.",
        "Reports path, permission, or filesystem errors; restores from backup is manual.",
        "Requires an explicit user request naming the file to write.",
        {"nome_arquivo": "Workspace-relative destination path.", "conteudo": "Complete UTF-8 text to write."},
    ),
    "read_file": ToolMetadata(
        "Read a bounded amount of text from a workspace file.",
        "KRONOS workspace filesystem.",
        "File must be inside the workspace and not a protected secret file.",
        "Reads text only; output is limited to 15,000 characters.",
        "Returns file text or an explicit read error.",
        "Reports missing files, encoding, and permission errors.",
        "Requires a user request to inspect the named file.",
        {"nome_arquivo": "Workspace-relative file path."},
    ),
    "open_website": ToolMetadata(
        "Open a requested website in the default browser.",
        "Windows default browser.",
        "A recognized site name or URL is required.",
        "Opens a browser tab.",
        "Returns browser launch status; page content is not inspected.",
        "Reports browser errors.",
        "Requires a user request to open the site.",
        {"url_ou_nome": "Website URL or recognized site name."},
    ),
    "open_app": ToolMetadata(
        "Launch a supported installed desktop application.",
        "Windows.",
        "Application must be on the supported alias list or resolve to an executable.",
        "Starts a desktop process.",
        "Checks that the process launch request succeeds.",
        "Reports missing executables or launch errors.",
        "Requires an explicit user request to launch the application.",
        {"app_name": "Installed application name or supported alias."},
    ),
    "close_app": ToolMetadata(
        "Close a named desktop application process.",
        "Windows process APIs.",
        "An exact supported process name must be available.",
        "Terminates the named process and may close unsaved work.",
        "Reports the number of matching processes terminated.",
        "Reports process access errors; unsaved data recovery is not guaranteed.",
        "Requires an explicit user request to close the application.",
        {"app_name": "Exact application name or supported alias."},
    ),
    "search_google": ToolMetadata(
        "Open a browser search for the requested query.",
        "Windows default browser and network access.",
        "A non-empty search query is required.",
        "Opens a browser tab.",
        "Returns browser launch status; search results are not independently read.",
        "Reports browser errors.",
        "Requires a user request to search the web.",
        {"pesquisa": "Search terms."},
    ),
    "list_directory": ToolMetadata(
        "List entries in a directory inside the KRONOS workspace.",
        "KRONOS workspace filesystem.",
        "Directory must resolve inside the workspace.",
        "Reads directory names only.",
        "Returns directory entries or an explicit filesystem error.",
        "Reports missing directories and access errors.",
        "Requires a user request to inspect the workspace directory.",
        {"pasta": "Workspace-relative directory, defaults to workspace root."},
    ),
    "set_operational_mode": ToolMetadata(
        "Switch the Windows power plan to a supported KRONOS mode.",
        "Windows power configuration.",
        "Mode must be one of the supported KRONOS modes.",
        "Changes the system power plan.",
        "Reports the requested plan; currently does not verify the active GUID.",
        "Reports command errors; manual power-plan restoration may be needed.",
        "Requires an explicit user request to change power mode.",
        {"mode_name": "Supported operational mode such as PADRAO ou GAMER."},
    ),
}


def build_tool_registry(
    tools: Mapping[str, Callable[..., Any]],
) -> Mapping[str, ToolSpec]:
    if set(tools) != set(_METADATA):
        missing = sorted(set(_METADATA) - set(tools))
        undocumented = sorted(set(tools) - set(_METADATA))
        raise ValueError(
            f"Tool metadata mismatch; missing={missing}, undocumented={undocumented}"
        )

    registry: dict[str, ToolSpec] = {}
    for name, function in tools.items():
        signature = inspect.signature(function)
        parameter_names = set(signature.parameters)
        documented_names = set(_METADATA[name].parameters)
        if parameter_names != documented_names:
            raise ValueError(
                f"Tool parameter metadata mismatch for {name}: "
                f"expected {sorted(parameter_names)}, got {sorted(documented_names)}"
            )
        spec = ToolSpec(name, function, _METADATA[name], signature)
        function.__doc__ = spec.model_description()
        registry[name] = spec
    return MappingProxyType(registry)