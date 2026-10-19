import os
import re
import shutil
import subprocess
import threading
import time
from contextlib import contextmanager
from ctypes import byref, c_ulong, windll

import pyautogui
import pygetwindow as gw
import pyperclip
import psutil
from google import genai
from google.genai import types

from config import MODEL_ROUTER, key_rotator

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.25
_roblox_control_context = threading.local()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROBLOX_DIR = os.path.join(BASE_DIR, 'scripts_roblox')
os.makedirs(ROBLOX_DIR, exist_ok=True)
MAX_AUTOMATION_ATTEMPTS = 5


def _find_roblox_executable():
    paths = [
        os.path.expandvars(r'%LOCALAPPDATA%\Roblox\Versions'),
        r'C:\Program Files (x86)\Roblox\Versions',
    ]
    for base in paths:
        if os.path.exists(base):
            for root, _dirs, files in os.walk(base):
                if 'RobloxStudioBeta.exe' in files:
                    return os.path.join(root, 'RobloxStudioBeta.exe')
    return 'RobloxStudioBeta.exe'


# ==========================================================
# 1. ARSENAL DO ROBLOX (GERADOR PROCEDURAL E PLAY AUTOMÁTICO)
# ==========================================================
def _roblox_studio_windows():
    studio_windows = []
    for window in gw.getWindowsWithTitle("Roblox Studio"):
        try:
            hwnd = int(window._hWnd)
            if not windll.user32.IsWindow(hwnd):
                continue
            process_id = c_ulong()
            if not windll.user32.GetWindowThreadProcessId(
                hwnd, byref(process_id)
            ) or not process_id.value:
                continue
        except Exception as error:
            _roblox_log("STUDIO", f"Ignorando referência de janela inválida: {error}", "AVISO")
            continue
        try:
            process_name = psutil.Process(process_id.value).name().lower()
        except psutil.Error:
            continue
        if process_name == "robloxstudiobeta.exe":
            studio_windows.append(window)
    return studio_windows


def _is_roblox_place_window(window):
    try:
        if not windll.user32.IsWindow(int(window._hWnd)):
            return False
        title = window.title.strip().lower()
        return title != "roblox studio" and "start page" not in title
    except Exception as error:
        _roblox_log("STUDIO", f"Não foi possível validar a janela: {error}", "AVISO")
        return False


def _activate_roblox_studio():
    studio_windows = _roblox_studio_windows()
    if not studio_windows:
        executable = _find_roblox_executable()
        try:
            subprocess.Popen([executable])
        except OSError as e:
            return None, f"Não foi possível abrir o Roblox Studio: {e}"

        deadline = time.time() + 45
        while time.time() < deadline:
            studio_windows = _roblox_studio_windows()
            if studio_windows:
                break
            time.sleep(0.5)
        if not studio_windows:
            return None, "Roblox Studio foi iniciado, mas sua janela não apareceu."

    place_windows = [candidate for candidate in studio_windows if _is_roblox_place_window(candidate)]
    candidates = place_windows or studio_windows
    foreground = windll.user32.GetForegroundWindow()
    win = next(
        (candidate for candidate in candidates if int(candidate._hWnd) == foreground),
        candidates[-1],
    )
    if not windll.user32.IsWindow(int(win._hWnd)):
        return None, "A janela do Roblox Studio foi fechada ou recriada. Tente novamente."
    if not _is_roblox_place_window(win):
        return None, "Roblox Studio está aberto, mas nenhuma place está carregada."

    try:
        if win.isMinimized:
            win.restore()
    except Exception as error:
        _roblox_log("STUDIO", f"Janela desatualizada; procurando novamente: {error}", "ERRO")
        refreshed_windows = _roblox_studio_windows()
        win = next((candidate for candidate in refreshed_windows if _is_roblox_place_window(candidate)), None)
        if not win:
            return None, "Não foi possível localizar novamente a janela da place."
    for _ in range(3):
        if not windll.user32.IsWindow(int(win._hWnd)):
            return None, "A janela do Roblox Studio foi fechada ou recriada. Tente novamente."
        try:
            win.activate()
        except Exception as error:
            if not windll.user32.IsWindow(int(win._hWnd)):
                refreshed_windows = _roblox_studio_windows()
                win = next(
                    (candidate for candidate in refreshed_windows if _is_roblox_place_window(candidate)),
                    None,
                )
                if not win:
                    return None, f"A janela do Roblox Studio não está mais válida: {error}"
        deadline = time.time() + 1.0
        while time.time() < deadline:
            if windll.user32.GetForegroundWindow() == int(win._hWnd):
                return win, None
            time.sleep(0.1)
    return None, "Não foi possível trazer a janela da place do Roblox Studio para frente."


@contextmanager
def roblox_automation_control(cancel_event):
    previous_event = getattr(_roblox_control_context, "cancel_event", None)
    previous_window = getattr(_roblox_control_context, "window_handle", None)
    _roblox_control_context.cancel_event = cancel_event
    _roblox_control_context.window_handle = None
    try:
        yield
    finally:
        _roblox_control_context.cancel_event = previous_event
        _roblox_control_context.window_handle = previous_window


def _roblox_checkpoint(win=None):
    cancel_event = getattr(_roblox_control_context, "cancel_event", None)
    target_handle = int(win._hWnd) if win else getattr(
        _roblox_control_context, "window_handle", None
    )
    if target_handle:
        _roblox_control_context.window_handle = target_handle

    pause_logged = False
    while True:
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("Automação Roblox cancelada pelo usuário.")
        if target_handle and not windll.user32.IsWindow(target_handle):
            raise RuntimeError(
                "Janela do Roblox Studio fechada durante a automação; operação interrompida."
            )
        if not target_handle or windll.user32.GetForegroundWindow() == target_handle:
            if pause_logged:
                _roblox_log("AUTOMACAO", "Studio em primeiro plano; automação retomada.", "OK")
            return
        if not pause_logged:
            _roblox_log(
                "AUTOMACAO",
                "Studio perdeu o foco. Automação pausada; volte ao Studio para continuar.",
                "AVISO",
            )
            pause_logged = True
        time.sleep(0.2)


def _roblox_click(win, x, y):
    _roblox_checkpoint(win)
    pyautogui.click(x, y)


def _roblox_press(win, key):
    _roblox_checkpoint(win)
    pyautogui.press(key)


def _roblox_hotkey(win, *keys):
    _roblox_checkpoint(win)
    pyautogui.hotkey(*keys)


def _command_bar_is_visible(win) -> bool:
    _roblox_checkpoint(win)
    screenshot = pyautogui.screenshot()
    top = max(0, int(win.top + win.height - 81))
    bottom = min(screenshot.height, int(win.top + win.height - 41))
    left = max(0, int(win.left + win.width - 110))
    right = min(screenshot.width, int(win.left + win.width - 10))
    if bottom <= top or right <= left:
        return False

    run_button_pixels = sum(
        1
        for y in range(top, bottom)
        for x in range(left, right)
        if max(screenshot.getpixel((x, y))[:3]) > 180
    )
    return run_button_pixels > 20


def _ensure_roblox_command_bar(win):
    _roblox_checkpoint(win)
    if _command_bar_is_visible(win):
        return

    _roblox_click(win, int(win.left + win.width * 0.5), int(win.top + 70))
    time.sleep(0.3)
    for _ in range(3):
        _roblox_click(win, int(win.left + 410), int(win.top + 108))
        time.sleep(0.8)
        if _command_bar_is_visible(win):
            return
    if not _command_bar_is_visible(win):
        raise RuntimeError("Não foi possível abrir a Command Bar do Roblox Studio.")


def _output_panel_is_visible(win) -> bool:
    _roblox_checkpoint(win)
    screenshot = pyautogui.screenshot()
    sample_y = int(win.top + win.height - 195)
    sample_start = max(0, int(win.left + 300))
    sample_end = min(screenshot.width, int(win.left + win.width - 300))
    if sample_y < 0 or sample_y >= screenshot.height or sample_end <= sample_start:
        return False

    pixels = [
        screenshot.getpixel((x, sample_y))[:3]
        for x in range(sample_start, sample_end, 12)
    ]
    dark_pixels = sum(1 for pixel in pixels if max(pixel) < 55)
    return (
        bool(pixels)
        and dark_pixels / len(pixels) > 0.8
        and len(set(pixels)) < 20
    )


def _ensure_roblox_output_panel(win):
    if _output_panel_is_visible(win):
        return

    _roblox_click(win, int(win.left + win.width * 0.5), int(win.top + 70))
    time.sleep(0.3)
    _roblox_click(win, int(win.left + 465), int(win.top + 108))
    time.sleep(0.8)
    if not _output_panel_is_visible(win):
        raise RuntimeError("Não foi possível abrir o painel Output do Roblox Studio.")


def _lua_string_literal(text: str) -> str:
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _build_roblox_runtime_source(source: str, runtime_marker: str) -> str:
    body = re.sub(
        r"^\s*local\s+part\s*=\s*script\.Parent\s*\n?",
        "",
        source,
        count=1,
    ).rstrip()
    return (
        "local part = script.Parent\n"
        f"part:SetAttribute({_lua_string_literal('KRONOS_RuntimeStarted')}, true)\n"
        f"{body}\n"
        f"print({_lua_string_literal(runtime_marker)})\n"
    )


def _roblox_log(stage: str, message: str, level: str = "INFO"):
    print(f"[ROBLOX][{level}][{stage}] {message}", flush=True)


def _capture_roblox_output(win) -> str:
    _roblox_checkpoint(win)
    previous_clipboard = pyperclip.paste()
    try:
        _roblox_click(
            win,
            int(win.left + win.width * 0.35),
            int(win.top + win.height - 145),
        )
        _roblox_hotkey(win, "ctrl", "a")
        _roblox_hotkey(win, "ctrl", "c")
        time.sleep(0.2)
        output = pyperclip.paste()
        if not isinstance(output, str):
            raise RuntimeError("O Output do Studio não foi copiado como texto.")
        return output
    finally:
        pyperclip.copy(previous_clipboard)


def _new_roblox_output(before: str, after: str) -> str:
    if after.startswith(before):
        return after[len(before):].strip()
    return after.strip()


def _output_has_error(output: str, script_name: str | None = None) -> bool:
    output_lines = [
        line
        for line in output.splitlines()
        if not re.match(
            r"^\s*(?:\d{1,2}:\d{2}:\d{2}(?:\.\d+)?\s*)?>\s*",
            line,
        )
    ]
    error_pattern = re.compile(
        r"\bscript error\b|\bcommand error\b|\btraceback\b|"
        r"\bsyntax error\b|\bstack begin\b|\battempt to\b|"
        r"\bexpected\b.{0,60}\bgot\b|\bunknown global\b|"
        r"\berror occurred\b|\berror\b|\bfailed\b",
        re.IGNORECASE,
    )
    if not script_name:
        return any(error_pattern.search(line) for line in output_lines)

    script_pattern = re.compile(re.escape(script_name), re.IGNORECASE)
    for index, line in enumerate(output_lines):
        if script_pattern.search(line) and error_pattern.search(line):
            return True
        if re.search(r"\bstack begin\b", line, re.IGNORECASE):
            stack_lines = []
            for stack_line in output_lines[index:index + 30]:
                stack_lines.append(stack_line)
                if re.search(r"\bstack end\b", stack_line, re.IGNORECASE):
                    break
            stack = "\n".join(stack_lines)
            if script_pattern.search(stack) and error_pattern.search(stack):
                return True
    return False


def _run_luau_compiler(file_path: str) -> tuple[bool | None, str]:
    compiler = shutil.which("luau-compile") or shutil.which("luau-compile.exe")
    if not compiler:
        message = "luau-compile não está instalado; teste local de sintaxe indisponível."
        _roblox_log("TESTE LOCAL", message, "AVISO")
        return None, message

    result = subprocess.run(
        [compiler, "--text", file_path],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    output = "\n".join(
        part.strip() for part in (result.stdout, result.stderr) if part.strip()
    )
    if result.returncode:
        return False, output or f"luau-compile encerrou com código {result.returncode}."
    return True, "Compilação Luau local concluída sem erros."


def _start_roblox_play(
    win,
    script_name: str,
    runtime_marker: str,
) -> tuple[dict, str]:
    output_before = _capture_roblox_output(win)
    _roblox_checkpoint(win)
    _roblox_press(win, "esc")
    _roblox_click(
        win,
        int(win.left + win.width * 0.3),
        int(win.top + win.height * 0.35),
    )
    time.sleep(0.3)
    _roblox_log("PLAY", "Enviando F5 para iniciar o teste.")
    _roblox_hotkey(win, "f5")
    time.sleep(5.0)
    output = _new_roblox_output(
        output_before, _capture_roblox_output(win)
    )
    runtime_confirmed = runtime_marker in output
    errors_visible = (
        _output_has_error(output, script_name) or not runtime_confirmed
    )
    evidence = output or "Nenhuma saída nova foi copiada do Output do Studio."
    _roblox_log("TERMINAL", evidence[:5000], "ERRO" if errors_visible else "INFO")
    report = {
        "play_running": runtime_confirmed,
        "runtime_confirmed": runtime_confirmed,
        "errors_visible": errors_visible,
        "evidence": evidence,
    }
    if runtime_confirmed:
        _roblox_log("PLAY", "Marcador de execução encontrado no Output.", "OK")
    elif errors_visible:
        _roblox_log("PLAY", "Erro Luau encontrado no Output.", "ERRO")
    else:
        _roblox_log(
            "PLAY",
            "F5 foi enviado, mas o Output não confirmou a execução.",
            "ERRO",
        )
    return report, evidence


def generate_roblox_script(nome_script: str, descricao_mecanica: str) -> str:
    """Creates or reuses a Part, installs its Script, requests saving, and tests the place."""
    try:
        _roblox_checkpoint()
        clean_name = re.sub(
            r"[^A-Za-z0-9_]", "_", nome_script.replace(".lua", "").strip()
        ) or "KronosScript"
        if len(clean_name) > 80:
            clean_name = clean_name[:80]
        part_name = f"KRONOS_{clean_name}"
        script_name = f"{clean_name}_Script"
        def generate_source(
            correction: str = "",
            previous_source: str = "",
        ) -> str:
            correction_prompt = (
                f"\n\nO código anterior foi:\n{previous_source}\n"
                f"O Roblox Studio mostrou este erro durante o teste: {correction}\n"
                "Corrija o código anterior e retorne uma versão completa."
                if correction
                else ""
            )
            prompt = f"""Você é um programador especialista sênior de Roblox (Luau). Gere o código-fonte executável do corpo de um Script de servidor persistente que será filho direto da Part `{part_name}` e atenderá à solicitação:
{descricao_mecanica}

Diretrizes de Arquitetura Luau:
- A primeira linha do código deve ser obrigatoriamente: `local part = script.Parent`
- Adquira os serviços necessários com `game:GetService(...)` (ex: `TweenService`, `Players`, `Debris`, `RunService`, `StarterGui`).
- Se a tarefa envolver portas, elevadores, botões ou plataformas móveis, utilize `TweenService:Create()` com `TweenInfo.new()` para movimento suave e realista, ou ajuste de CFrame com debounce.
- Em mecânicas com gatilhos (`Touched`), sempre use variável de controle de debounce (`local debounce = false`) para evitar acionamentos múltiplos descontrolados e verifique se o contato possui `Humanoid`.
- Se a mecânica for de interação de proximidade, crie um `Instance.new("ProximityPrompt")` configurado como filho da Part.
- Se for uma interface de usuário (HUD, placar, botão na tela), crie um `ScreenGui` bem estruturado adicionado ao `StarterGui` ou clonado nos jogadores ao entrar.
- Se a mecânica envolver efeitos visuais ou iluminação, configure instâncias adequadas (`ParticleEmitter`, `PointLight`, `Highlight`).
- Todas as Parts adicionais necessárias devem ser criadas via `Instance.new("Part")`, configuradas com `Anchored`, `CanCollide`, `Size`, `Position`, `Color` ou `Material`, e parentadas a `workspace`.
- Retorne apenas o código Luau do corpo do Script, sem Markdown nem comentários desnecessários.{correction_prompt}"""
            errors = []
            models = MODEL_ROUTER["tools"]
            for round_number in range(1, 3):
                for model in models:
                    _roblox_checkpoint()
                    try:
                        client = genai.Client(
                            api_key=key_rotator.current_key,
                            http_options=types.HttpOptions(
                                timeout=60000,
                                retry_options=types.HttpRetryOptions(attempts=1),
                            ),
                        )
                        response = client.models.generate_content(
                            model=model,
                            contents=prompt,
                        )
                        source = re.sub(
                            r"```(?:lua|luau)?", "", response.text or ""
                        ).replace("```", "").strip()
                        if not source:
                            raise RuntimeError("o modelo retornou código Luau vazio")
                        if not re.match(
                            r"local\s+part\s*=\s*script\.Parent\b", source
                        ):
                            source = "local part = script.Parent\n" + source
                        return source
                    except Exception as error:
                        errors.append(f"{model}: {error}")
                        _roblox_log(
                            "GERACAO",
                            f"Modelo {model} falhou: {error}.",
                            "AVISO",
                        )
                        key_rotator.rotate("Geração de Script Roblox")
                if round_number < 2:
                    _roblox_log(
                        "GERACAO",
                        "Todos os modelos falharam nesta rodada; aguardando 2 segundos e tentando novamente.",
                        "AVISO",
                    )
                    time.sleep(2)
            raise RuntimeError(
                "Todos os modelos de geração falharam: " + " | ".join(errors)
            )

        runtime_marker = f"KRONOS_RUNTIME_OK:{script_name}"
        file_path = os.path.join(ROBLOX_DIR, f"{clean_name}.lua")
        try:
            _roblox_checkpoint()
            _roblox_log("STUDIO", "Localizando e ativando a place carregada.")
            win, error = _activate_roblox_studio()
            if error:
                _roblox_log("STUDIO", error, "ERRO")
                return f"Não foi possível instalar o Script no Roblox Studio: {error}"

            _roblox_log("OUTPUT", "Abrindo o painel Output para verificar cada etapa.")
            _ensure_roblox_output_panel(win)
            _roblox_hotkey(win, "shift", "f5")
            time.sleep(0.5)

            def run_command(command: str):
                output_before = _capture_roblox_output(win)
                _ensure_roblox_command_bar(win)
                _roblox_press(win, "esc")
                _roblox_click(win, int(win.left + 500), int(win.top + win.height - 60))
                _roblox_hotkey(win, "ctrl", "a")
                previous_clipboard = pyperclip.paste()
                try:
                    pyperclip.copy(command)
                    _roblox_hotkey(win, "ctrl", "v")
                    _roblox_click(
                        win,
                        int(win.left + win.width - 55),
                        int(win.top + win.height - 60),
                    )
                    time.sleep(max(1.5, min(8.0, len(command) / 2000)))
                finally:
                    pyperclip.copy(previous_clipboard)
                output_after = _capture_roblox_output(win)
                return _new_roblox_output(output_before, output_after)

            def create_part() -> tuple[bool, str]:
                part_command = (
                    f"local part = workspace:FindFirstChild({_lua_string_literal(part_name)}, true); "
                    "if part and not part:IsA('BasePart') then error('Objeto com o nome reservado da Part não é BasePart') end; "
                    "if not part then part = Instance.new('Part'); "
                    f"part.Name = {_lua_string_literal(part_name)}; "
                    "part.Size = Vector3.new(4, 1, 4); part.Position = Vector3.new(0, 5, 0); "
                    "part.Anchored = true; part.Parent = workspace end; "
                    "if not part:IsDescendantOf(workspace) or not part:IsA('BasePart') then error('Part não está corretamente instalada na Workspace') end; "
                    "game:GetService('Selection'):Set({part}); "
                    f"print({_lua_string_literal('KRONOS_PART_OK:' + part_name)})"
                )
                output = run_command(part_command)
                marker = "KRONOS_PART_OK:" + part_name
                if marker in output and not _output_has_error(output):
                    return True, marker
                return False, output or "O Studio não confirmou a Part."

            def create_script() -> tuple[bool, str]:
                script_command = (
                    f"local part = workspace:FindFirstChild({_lua_string_literal(part_name)}, true); "
                    "if not part or not part:IsA('BasePart') then error('Part não encontrada para receber o Script') end; "
                    f"local serverScript = part:FindFirstChild({_lua_string_literal(script_name)}); "
                    "if serverScript and not serverScript:IsA('Script') then error('Objeto com o nome reservado do Script não é Script') end; "
                    "if not serverScript then serverScript = Instance.new('Script'); "
                    f"serverScript.Name = {_lua_string_literal(script_name)}; "
                    "serverScript.Disabled = true; serverScript.Parent = part end; "
                    "game:GetService('Selection'):Set({serverScript}); "
                    f"print({_lua_string_literal('KRONOS_SCAFFOLD_OK:' + script_name)})"
                )
                output = run_command(script_command)
                marker = "KRONOS_SCAFFOLD_OK:" + script_name
                if marker in output and not _output_has_error(output):
                    return True, marker
                return False, output or "O Studio não confirmou o Script."

            def build_installer(source: str) -> str:
                full_source = _build_roblox_runtime_source(
                    source, runtime_marker
                )

                return (
                    f"local part = workspace:FindFirstChild({_lua_string_literal(part_name)}, true); "
                    "if part and not part:IsA('BasePart') then error('Objeto com o nome reservado da Part não é BasePart') end; "
                    "if not part then error('Part não encontrada para receber o Script') end; "
                    f"local serverScript = part:FindFirstChild({_lua_string_literal(script_name)}); "
                    "if serverScript and not serverScript:IsA('Script') then error('Objeto com o nome reservado do Script não é Script') end; "
                    "if not serverScript then serverScript = Instance.new('Script'); "
                    f"serverScript.Name = {_lua_string_literal(script_name)} end; "
                    "serverScript.Disabled = true; "
                    f"serverScript.Source = {_lua_string_literal(full_source)}; "
                    "serverScript.Parent = part; "
                    "serverScript.Disabled = false; "
                    f"if serverScript.Parent ~= part or serverScript.Source ~= {_lua_string_literal(full_source)} or serverScript.Disabled then error('Script não permaneceu instalado e habilitado na Part') end; "
                    "game:GetService('Selection'):Set({serverScript}); "
                    f"print({_lua_string_literal('KRONOS_INSTALL_OK:' + part_name)})"
                )

            def install_script(source: str) -> tuple[bool, str]:
                installer_code = build_installer(source)
                output = run_command(installer_code)
                marker = "KRONOS_INSTALL_OK:" + part_name
                confirmed = marker in output and not _output_has_error(output)
                for stage, label in (
                    ("PART", part_name),
                    ("SCRIPT", script_name),
                    ("OUTPUT", "marcador de instalação"),
                ):
                    _roblox_log(
                        stage,
                        f"{label}: {'confirmado' if confirmed else 'não confirmado'}.",
                        "OK" if confirmed else "ERRO",
                    )
                evidence = output or "O Output do Studio não confirmou a instalação."
                return confirmed, evidence

            part_created = False
            for attempt in range(1, MAX_AUTOMATION_ATTEMPTS + 1):
                _roblox_log(
                    "PART",
                    f"Tentativa {attempt}/{MAX_AUTOMATION_ATTEMPTS}: criando ou reutilizando a Part.",
                )
                try:
                    part_created, evidence = create_part()
                except Exception as error:
                    evidence = str(error)
                    _roblox_log("PART", evidence, "ERRO")
                if part_created:
                    break
                if attempt < MAX_AUTOMATION_ATTEMPTS:
                    _roblox_log(
                        "CORRECAO",
                        f"Part não confirmada: {evidence}. Repetindo o comando.",
                        "AVISO",
                    )
            if not part_created:
                return (
                    f"Falha: a Part não foi confirmada após {MAX_AUTOMATION_ATTEMPTS} "
                    f"tentativas. Evidência: {evidence}"
                )

            _roblox_log(
                "SCRIPT",
                f"Part confirmada; criando o Script vazio {script_name} antes de gerar o código.",
            )
            clean_code = ""
            for scaffold_attempt in range(1, MAX_AUTOMATION_ATTEMPTS + 1):
                try:
                    scaffold_created, evidence = create_script()
                except Exception as error:
                    scaffold_created, evidence = False, str(error)
                if scaffold_created:
                    _roblox_log(
                        "SCRIPT",
                        f"Script vazio {script_name} criado dentro da Part.",
                        "OK",
                    )
                    break
                _roblox_log(
                    "SCRIPT",
                    f"Criação do Script ainda não confirmada ({scaffold_attempt}/{MAX_AUTOMATION_ATTEMPTS}): {evidence}",
                    "ERRO",
                )
            else:
                return (
                    f"Falha: não foi possível criar o Script {script_name} após "
                    f"{MAX_AUTOMATION_ATTEMPTS} tentativas. {evidence}"
                )

            _roblox_log(
                "GERACAO",
                f"Part e Script existem na place; iniciando a programação de {script_name}.",
            )
            for source_attempt in range(1, MAX_AUTOMATION_ATTEMPTS + 1):
                clean_code = generate_source(
                    evidence if source_attempt > 1 else "",
                    clean_code,
                )
                with open(file_path, "w", encoding="utf-8") as script_file:
                    script_file.write(clean_code)
                _roblox_log(
                    "ARQUIVO",
                    f"Fonte salva para teste local: {file_path}.",
                    "OK",
                )
                try:
                    syntax_ok, syntax_output = _run_luau_compiler(file_path)
                except Exception as error:
                    syntax_ok, syntax_output = False, str(error)
                if syntax_ok is not False:
                    if syntax_ok is True:
                        _roblox_log("TESTE LOCAL", syntax_output, "OK")
                    break
                evidence = syntax_output
                _roblox_log(
                    "TESTE LOCAL",
                    f"Erro de sintaxe Luau: {syntax_output}",
                    "ERRO",
                )
                if source_attempt < MAX_AUTOMATION_ATTEMPTS:
                    _roblox_log(
                        "CORRECAO",
                        "Enviando o erro do compilador para gerar uma correção.",
                        "AVISO",
                    )
            else:
                return (
                    "Falha: compilação local do Luau continuou apresentando erros "
                    f"após {MAX_AUTOMATION_ATTEMPTS} correções. {evidence}"
                )

            script_installed = False
            for attempt in range(1, MAX_AUTOMATION_ATTEMPTS + 1):
                _roblox_log(
                    "SCRIPT",
                    f"Tentativa {attempt}/{MAX_AUTOMATION_ATTEMPTS}: instalando o Script dentro da Part.",
                )
                try:
                    script_installed, evidence = install_script(clean_code)
                except Exception as error:
                    evidence = str(error)
                    _roblox_log("SCRIPT", evidence, "ERRO")
                if script_installed:
                    break
                if attempt < MAX_AUTOMATION_ATTEMPTS:
                    _roblox_log(
                        "CORRECAO",
                        f"Instalação não confirmada: {evidence}. Corrigindo e tentando novamente.",
                        "AVISO",
                    )
                    clean_code = generate_source(evidence, clean_code)
                    with open(file_path, "w", encoding="utf-8") as script_file:
                        script_file.write(clean_code)
            if not script_installed:
                return (
                    f"Falha: a Part foi criada, mas o Script não foi confirmado após "
                    f"{MAX_AUTOMATION_ATTEMPTS} tentativas. Evidência: {evidence}"
                )

            def save_place() -> None:
                _roblox_log("SALVAMENTO", "Solicitando salvamento da place (Ctrl+S).")
                _roblox_hotkey(win, "ctrl", "s")
                time.sleep(1.0)
                _roblox_checkpoint(win)
                _roblox_log("SALVAMENTO", "Ctrl+S enviado.", "OK")

            save_place()
            for test_attempt in range(1, MAX_AUTOMATION_ATTEMPTS + 1):
                _roblox_log(
                    "PLAY",
                    f"Teste {test_attempt}/{MAX_AUTOMATION_ATTEMPTS}: executando com F5.",
                )
                try:
                    report, evidence = _start_roblox_play(
                        win, script_name, runtime_marker
                    )
                except Exception as error:
                    if "cancelada pelo usuário" in str(error).lower():
                        raise
                    report, evidence = {}, str(error)
                    _roblox_log("PLAY", evidence, "ERRO")

                runtime_ok = (
                    report.get("errors_visible") is not True
                    and report.get("play_running") is True
                    and report.get("runtime_confirmed") is True
                )
                if runtime_ok:
                    _roblox_log("PLAY", evidence, "OK")
                    return (
                        f"Part e Script instalados; Play Test confirmado após "
                        f"{test_attempt} teste(s), sem erros Luau associados. "
                        "Salvamento solicitado pelo Ctrl+S; a confirmação de gravação "
                        "não está disponível pela automação."
                    )

                _roblox_log(
                    "PLAY",
                    f"Teste não confirmado: {evidence}",
                    "ERRO",
                )
                if test_attempt == MAX_AUTOMATION_ATTEMPTS:
                    break

                _roblox_log(
                    "PLAY",
                    "Garantindo que o teste foi interrompido com Shift+F5 antes da correção.",
                )
                _roblox_hotkey(win, "shift", "f5")
                time.sleep(0.5)
                _roblox_checkpoint(win)

                if report.get("errors_visible") is True or report.get("play_running") is True:
                    correction = evidence
                    _roblox_log(
                        "CORRECAO",
                        f"Erro encontrado; gerando correção {test_attempt}/{MAX_AUTOMATION_ATTEMPTS - 1}.",
                        "AVISO",
                    )
                    clean_code = generate_source(correction, clean_code)
                    _roblox_log("CORRECAO", "Nova fonte Luau gerada.", "OK")
                else:
                    _roblox_log(
                        "PLAY",
                        "Erro de inicialização/verificação; mantendo a fonte e repetindo o teste.",
                        "AVISO",
                    )

                with open(file_path, "w", encoding="utf-8") as script_file:
                    script_file.write(clean_code)
                _roblox_log("ARQUIVO", f"Fonte atualizada salva em {file_path}.", "OK")

                installed = False
                install_evidence = "instalação não confirmada"
                for install_attempt in range(
                    1, MAX_AUTOMATION_ATTEMPTS + 1
                ):
                    try:
                        installed, install_evidence = install_script(clean_code)
                    except Exception as error:
                        if "cancelada pelo usuário" in str(error).lower():
                            raise
                        install_evidence = str(error)
                        _roblox_log("INSTALACAO", install_evidence, "ERRO")
                    if installed:
                        break
                    if install_attempt < MAX_AUTOMATION_ATTEMPTS:
                        _roblox_log(
                            "CORRECAO",
                            f"Correção não foi instalada: {install_evidence}. Tentando novamente.",
                            "AVISO",
                        )
                        clean_code = generate_source(
                            install_evidence, clean_code
                        )
                        with open(file_path, "w", encoding="utf-8") as script_file:
                            script_file.write(clean_code)
                if not installed:
                    return (
                        "Não foi possível instalar a correção após "
                        f"{MAX_AUTOMATION_ATTEMPTS} tentativas: {install_evidence}"
                    )
                save_place()

            _roblox_log("PLAY", evidence, "ERRO")
            return (
                f"Falha: automação interrompida após {MAX_AUTOMATION_ATTEMPTS} testes sem "
                f"confirmação de sucesso. Última evidência: {evidence}"
            )
        except Exception as auto_err:
            if "cancelada pelo usuário" in str(auto_err).lower():
                _roblox_log("AUTOMACAO", str(auto_err), "AVISO")
                return "Automação Roblox cancelada; o Studio permanece aberto."
            _roblox_log("AUTOMACAO", str(auto_err), "ERRO")
            return f"Falha na automação do Roblox Studio: {auto_err}"

    except Exception as e:
        if "cancelada pelo usuário" in str(e).lower():
            _roblox_log("AUTOMACAO", str(e), "AVISO")
            return "Automação Roblox cancelada; o Studio permanece aberto."
        _roblox_log("GERACAO", str(e), "ERRO")
        return f"Falha ao gerar script de Roblox: {str(e)}"

def play_roblox_studio() -> str:
    """Força o foco no Roblox Studio e aperta F5 para dar Play Test automaticamente."""
    try:
        win, error = _activate_roblox_studio()
        if error:
            _roblox_log("PLAY", error, "ERRO")
            return error
        _roblox_log("PLAY", "Iniciando Play Test solicitado.")
        _roblox_press(win, "f5")
        return "Teste de jogo (F5) iniciado automaticamente no Roblox Studio."
    except Exception as e:
        return f"Erro ao iniciar play test: {str(e)}"