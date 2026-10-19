import os
import io
import re
import base64
import time
import json
import shutil
import pathlib
import tempfile
import urllib.request
import urllib.parse
import webbrowser
import subprocess
import threading
import psutil
import pyperclip
import pyautogui
import pygetwindow as gw
from PIL import ImageGrab
from ctypes import byref, cast, c_ulong, POINTER, windll
import comtypes
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from google import genai
from google.genai import types
from config import key_rotator, MODEL_ROUTER
from roblox_automation import (
    generate_roblox_script,
    play_roblox_studio,
    roblox_automation_control,
)
from blender_automation import (
    blender_render_background,
    generate_blender_script,
)
from blender_project_edit import edit_blender_project
from tool_registry import build_tool_registry

# Configuração de segurança do PyAutoGUI
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.25

current_mode = "PADRAO"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

real_cpu_usage = 0.0
real_cpu_cores = [0.0] * 6
psutil.cpu_percent(interval=None)

def _cpu_sampler():
    global real_cpu_usage, real_cpu_cores
    while True:
        try:
            val = psutil.cpu_percent(interval=0.8)
            if val > 0.0:
                real_cpu_usage = val
            cores = psutil.cpu_percent(percpu=True, interval=None)
            real_cpu_cores = cores[:6] if len(cores) >= 6 else cores
        except Exception:
            time.sleep(1.0)

threading.Thread(target=_cpu_sampler, daemon=True).start()

last_weather_fetch = 0
cached_weather = {
    "cidade": "CURITIBA (SANTA CÂNDIDA), PR",
    "temperatura": "--",
    "condicao": "Sincronizando...",
    "umidade": "--"
}

last_net_time = time.time()
last_net_bytes = psutil.net_io_counters()

def _find_executable(app_type: str) -> str:
    if app_type == "blender":
        caminhos = [
            r"C:\Program Files\Blender Foundation",
            r"C:\Program Files (x86)\Blender Foundation",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Blender Foundation")
        ]
        for base in caminhos:
            if os.path.exists(base):
                for root, dirs, files in os.walk(base):
                    if "blender.exe" in files:
                        return os.path.join(root, "blender.exe")
        return "blender"

    elif app_type == "roblox_studio":
        caminhos = [
            os.path.expandvars(r"%LOCALAPPDATA%\Roblox\Versions"),
            r"C:\Program Files (x86)\Roblox\Versions"
        ]
        for base in caminhos:
            if os.path.exists(base):
                for root, dirs, files in os.walk(base):
                    if "RobloxStudioBeta.exe" in files:
                        return os.path.join(root, "RobloxStudioBeta.exe")
        return "RobloxStudioBeta.exe"
        
    elif app_type == "sketchup":
        caminhos = [
            r"C:\Program Files\SketchUp",
            r"C:\Program Files (x86)\SketchUp"
        ]
        for base in caminhos:
            if os.path.exists(base):
                for root, dirs, files in os.walk(base):
                    if "SketchUp.exe" in files:
                        return os.path.join(root, "SketchUp.exe")
        return "sketchup"

    return app_type

# ==========================================================
# 3. CONTROLES DE ÁUDIO E NOTIFICAÇÕES
# ==========================================================
def set_volume(level: int) -> str:
    try:
        comtypes.CoInitialize()
        val = max(0, min(100, int(level)))
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(val / 100.0, None)
        return f"Volume ajustado para {val}%."
    except Exception as e:
        return f"Falha ao regular volume: {str(e)}"
    finally:
        try:
            comtypes.CoUninitialize()
        except:
            pass

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_VOLUME_MUTE = 0xAD

def _send_media_key(code: int):
    windll.user32.keybd_event(code, 0, 0, 0)
    time.sleep(0.05)
    windll.user32.keybd_event(code, 0, 2, 0)

def media_control(acao: str) -> str:
    act = acao.lower().strip()
    try:
        if act in ["play", "pause", "play_pause", "pausar", "tocar", "continuar"]:
            _send_media_key(VK_MEDIA_PLAY_PAUSE)
            return "Comando de reprodução/pausa executado."
        elif act in ["next", "proxima", "avancar", "pular"]:
            _send_media_key(VK_MEDIA_NEXT_TRACK)
            return "Avançado para a próxima faixa."
        elif act in ["previous", "anterior", "voltar"]:
            _send_media_key(VK_MEDIA_PREV_TRACK)
            return "Retornado para a faixa anterior."
        elif act in ["mute", "mutar", "desmutar"]:
            _send_media_key(VK_VOLUME_MUTE)
            return "Alternância de mudo executada."
        return f"Ação '{acao}' não reconhecida."
    except Exception as e:
        return f"Erro de mídia: {str(e)}"

def play_music(busca: str, plataforma: str = "youtube") -> str:
    query = busca.strip()
    plat = plataforma.lower().strip()
    try:
        if "spotify" in plat:
            webbrowser.open_new_tab(f"spotify:search:{urllib.parse.quote(query)}")
            return f"Reprodução de '{query}' iniciada no Spotify."
        else:
            search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
            req = urllib.request.Request(search_url, headers={"User-Agent": "Mozilla/5.0"})
            try:
                with urllib.request.urlopen(req, timeout=3) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                    video_ids = re.findall(r"/watch\?v=([a-zA-Z0-9_-]{11})", html)
                    if video_ids:
                        first_id = video_ids[0]
                        webbrowser.open_new_tab(f"https://www.youtube.com/watch?v={first_id}")
                        return f"Reproduzindo a faixa '{query}' diretamente no YouTube."
            except:
                pass
            webbrowser.open_new_tab(search_url)
            return f"Tocando '{query}' no YouTube."
    except Exception as e:
        return f"Erro ao tocar música: {str(e)}"

def send_notification(titulo: str, mensagem: str) -> str:
    try:
        encoded_title = base64.b64encode(titulo.encode("utf-8")).decode("ascii")
        encoded_message = base64.b64encode(mensagem.encode("utf-8")).decode("ascii")
        aumid = "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe"
        ps_cmd = f"""
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
        $textNodes = $template.GetElementsByTagName("text")
        $title = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("{encoded_title}"))
        $message = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("{encoded_message}"))
        $textNodes.Item(0).AppendChild($template.CreateTextNode($title)) | Out-Null
        $textNodes.Item(1).AppendChild($template.CreateTextNode($message)) | Out-Null
        $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
        $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{aumid}")
        $notifier.Show($toast)
        """
        subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps_cmd,
            ],
            creationflags=0x08000000,
        )
        return f"Notificação emitida no Windows 11: {titulo}"
    except Exception as e:
        return f"Falha ao emitir notificação: {str(e)}"

def read_clipboard() -> str:
    try:
        conteudo = pyperclip.paste()
        return f"Conteúdo da Área de Transferência:\n{conteudo[:3000]}" if conteudo and conteudo.strip() else "Área de transferência vazia."
    except Exception as e:
        return f"Erro ao ler clipboard: {str(e)}"

def copy_to_clipboard(texto: str) -> str:
    try:
        pyperclip.copy(texto)
        return "Conteúdo copiado com sucesso para a área de transferência."
    except Exception as e:
        return f"Erro ao copiar para clipboard: {str(e)}"

# ==========================================================
# 4. GESTÃO DE APLICATIVOS E SITES
# ==========================================================
def open_website(url_ou_nome: str) -> str:
    site = url_ou_nome.lower().strip()
    redes_sociais = {
        "youtube": "https://www.youtube.com", "instagram": "https://www.instagram.com",
        "twitter": "https://www.x.com", "x": "https://www.x.com", "tiktok": "https://www.tiktok.com",
        "reddit": "https://www.reddit.com", "whatsapp": "https://web.whatsapp.com",
        "discord": "https://discord.com/app", "twitch": "https://www.twitch.tv",
        "github": "https://www.github.com", "google": "https://www.google.com"
    }
    alvo = redes_sociais.get(site, site)
    if not alvo.startswith("http"):
        alvo = f"https://www.{alvo}.com" if "." not in alvo else f"https://{alvo}"
    try:
        webbrowser.open_new_tab(alvo)
        return f"Página '{alvo}' aberta."
    except Exception as e:
        return f"Falha ao abrir: {str(e)}"

def open_app(app_name: str) -> str:
    nome = app_name.lower().strip()
    if any(s in nome for s in ["youtube", "instagram", "twitter", "reddit", "tiktok", "whatsapp"]):
        return open_website(nome)

    if "blender" in nome:
        alvo = _find_executable("blender")
    elif "roblox studio" in nome:
        alvo = _find_executable("roblox_studio")
    elif "sketchup" in nome:
        alvo = _find_executable("sketchup")
    else:
        atalhos = {
            "bloco de notas": "notepad", "calculadora": "calc", "chrome": "chrome",
            "discord": "discord", "roblox": "robloxplayerbeta", "gerenciador de tarefas": "taskmgr", "explorer": "explorer"
        }
        alvo = atalhos.get(nome, "")
        if not alvo:
            candidate = pathlib.Path(app_name.strip().strip('"')).expanduser()
            if candidate.is_absolute():
                if candidate.suffix.casefold() != ".exe" or not candidate.is_file():
                    return "Falha: informe um executável .exe existente."
                alvo = str(candidate.resolve())
            else:
                alvo = shutil.which(app_name.strip()) or ""
        if not alvo:
            return (
                f"Falha: '{app_name}' não é um aplicativo compatível nem um "
                "executável encontrado no PATH."
            )

    try:
        subprocess.Popen([alvo], shell=False)
        return f"Aplicativo '{app_name}' iniciado."
    except Exception as e:
        return f"Falha ao abrir '{app_name}': {str(e)}"

def close_app(app_name: str) -> str:
    nome_alvo = app_name.lower().replace(".exe", "").strip()
    alias = {
        "bloco de notas": "notepad", "calculadora": "calculator", "chrome": "chrome", 
        "discord": "discord", "blender": "blender", "sketchup": "sketchup"
    }
    alvo = alias.get(nome_alvo, nome_alvo)
    if not re.fullmatch(r"[a-z0-9_.-]+", alvo):
        return "Falha: nome de processo inválido."

    matches = []
    for proc in psutil.process_iter(['name']):
        try:
            process_name = (proc.info.get('name') or '').casefold()
            if process_name == alvo or process_name == f"{alvo}.exe":
                matches.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if not matches:
        return f"Processo '{app_name}' não encontrado."
    if len(matches) > 1:
        return (
            f"Encontrei {len(matches)} processos com o nome '{app_name}'. "
            "Nenhum foi encerrado para evitar fechar sessões ou projetos não salvos."
        )
    try:
        matches[0].terminate()
        matches[0].wait(timeout=5)
        return f"Processo '{app_name}' encerrado."
    except psutil.TimeoutExpired:
        return (
            f"Falha: o processo '{app_name}' não encerrou após a solicitação. "
            "Ele permanece ativo."
        )
    except (psutil.NoSuchProcess, psutil.AccessDenied) as error:
        return f"Falha ao encerrar '{app_name}': {error}"

def search_google(pesquisa: str) -> str:
    try:
        url = f"https://www.google.com/search?q={urllib.parse.quote(pesquisa)}"
        webbrowser.open_new_tab(url)
        return f"Pesquisa por '{pesquisa}' realizada."
    except Exception as e:
        return f"Erro na pesquisa: {str(e)}"

def set_operational_mode(mode_name: str) -> str:
    global current_mode
    requested_mode = mode_name.upper().strip()
    plans = {
        "GAMER": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
        "PADRAO": "381b4222-f694-41f0-9685-ff5bb260df2e",
    }
    if requested_mode not in plans:
        return "Falha: modo não suportado. Use GAMER ou PADRAO."
    try:
        result = subprocess.run(
            ["powercfg", "/setactive", plans[requested_mode]],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"Falha ao alterar o modo de energia: {error}"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return f"Falha ao alterar o modo de energia: {detail or result.returncode}"
    current_mode = requested_mode
    return f"Modo {current_mode} ativado."

# ==========================================================
# 5. ARQUIVOS, VISÃO E TELEMETRIA
# ==========================================================
def analyze_screen(pergunta: str = "O que você vê na tela?") -> str:
    try:
        screenshot = ImageGrab.grab()
        if screenshot.mode in ("RGBA", "P"): screenshot = screenshot.convert("RGB")
        screenshot.thumbnail((1280, 720))
        buf = io.BytesIO()
        screenshot.save(buf, format="JPEG", quality=80)
        img_bytes = buf.getvalue()

        for vision_model in MODEL_ROUTER["vision"]:
            for _ in range(2):
                try:
                    client = genai.Client(api_key=key_rotator.current_key)
                    response = client.models.generate_content(
                        model=vision_model,
                        contents=[types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"), f"Inspecione a tela: {pergunta}"]
                    )
                    if response.text: return response.text
                except Exception:
                    key_rotator.rotate("Visão")
                    time.sleep(0.4)
        return "Captura visual realizada."
    except Exception as e:
        return f"Falha na captura: {str(e)}"

PROTECTED_DIRS = {".git", ".venv", "__pycache__"}
PROTECTED_FILES = {
    "kronos_memory.db",
    "config.py",
    "brain.py",
    "tools.py",
    "tool_registry.py",
    "memory.py",
    "roblox_automation.py",
    "blender_automation.py",
}
PROTECTED_SUFFIXES = {".pem", ".key", ".pfx", ".kdbx"}

# Pastas liberadas SOMENTE para leitura/listagem (escrita continua só no workspace)
READ_ONLY_FOLDERS = {
    "documents": ["Documents", "OneDrive/Documents", "Documentos", "OneDrive/Documentos"],
    "downloads": ["Downloads", "OneDrive/Downloads"],
    "desktop": ["Desktop", "OneDrive/Desktop", "Área de Trabalho", "OneDrive/Área de Trabalho"],
}
READ_ONLY_ALIASES = {
    "documents": "documents", "documentos": "documents",
    "downloads": "downloads",
    "desktop": "desktop", "area de trabalho": "desktop", "área de trabalho": "desktop",
}


def _check_protected(resolved: pathlib.Path) -> None:
    if any(part.casefold() in PROTECTED_DIRS for part in resolved.parts):
        raise PermissionError("Acesso negado a diretórios internos/protegidos.")
    name = resolved.name.casefold()
    if (
        name in PROTECTED_FILES
        or name.startswith(".env")
        or resolved.suffix.casefold() in PROTECTED_SUFFIXES
    ):
        raise PermissionError(
            "Acesso negado: esse arquivo contém segredos ou infraestrutura central."
        )


def _resolve_workspace_path(nome_arquivo: str) -> pathlib.Path:
    """Caminho para ESCRITA: só dentro do workspace do KRONOS."""
    root = pathlib.Path(BASE_DIR).resolve()
    requested = pathlib.Path(nome_arquivo)
    if not requested.is_absolute():
        requested = root / requested
    resolved = requested.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise PermissionError(
            "Acesso negado: ferramentas de escrita só podem acessar "
            "o workspace do KRONOS."
        ) from error
    _check_protected(resolved)
    return resolved


def _read_only_roots() -> dict:
    home = pathlib.Path.home()
    roots = {}
    for key, options in READ_ONLY_FOLDERS.items():
        for option in options:
            candidate = home / option
            if candidate.is_dir():
                roots[key] = candidate.resolve()
                break
    return roots


def _resolve_readable_path(nome: str) -> pathlib.Path:
    """Caminho para LEITURA: workspace + Documentos/Downloads/Área de Trabalho."""
    root = pathlib.Path(BASE_DIR).resolve()
    roots = _read_only_roots()
    texto = (nome or ".").strip().strip('"')
    caminho = pathlib.Path(texto).expanduser()

    if not caminho.is_absolute():
        partes = [p for p in re.split(r"[\\/]+", texto) if p and p != "~"]
        chave = READ_ONLY_ALIASES.get(partes[0].casefold()) if partes else None
        if chave and chave in roots:
            caminho = roots[chave].joinpath(*partes[1:])

    resolved = (caminho if caminho.is_absolute() else root / caminho).resolve(strict=False)

    for base in [root, *roots.values()]:
        try:
            resolved.relative_to(base)
            break
        except ValueError:
            continue
    else:
        raise PermissionError(
            "Acesso negado: leitura permitida apenas no workspace do KRONOS "
            "e nas pastas Documentos, Downloads e Área de Trabalho."
        )
    _check_protected(resolved)
    return resolved

def write_file(nome_arquivo: str, conteudo: str) -> str:
    temporary_path = None
    try:
        destination = _resolve_workspace_path(nome_arquivo)
        destination.parent.mkdir(parents=True, exist_ok=True)
        backup_path = None
        if destination.exists():
            suffix = 1
            backup_path = pathlib.Path(str(destination) + ".bak")
            while backup_path.exists():
                suffix += 1
                backup_path = pathlib.Path(f"{destination}.bak.{suffix}")
            shutil.copy2(destination, backup_path)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary_path = output.name
            output.write(conteudo)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, destination)
        relative_path = destination.relative_to(pathlib.Path(BASE_DIR).resolve())
        backup_message = (
            f" Backup: {backup_path.relative_to(pathlib.Path(BASE_DIR).resolve())}."
            if backup_path
            else ""
        )
        return f"Arquivo '{relative_path}' salvo.{backup_message}"
    except (OSError, PermissionError, ValueError) as error:
        return f"Falha ao escrever arquivo: {error}"
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)

def read_file(nome_arquivo: str) -> str:
    try:
        caminho_final = _resolve_readable_path(nome_arquivo)
        if not caminho_final.is_file():
            return f"Falha ao ler arquivo: '{nome_arquivo}' não é um arquivo existente."
        with open(caminho_final, "r", encoding="utf-8", errors="replace") as f:
            return f.read(15000)
    except (OSError, PermissionError, ValueError) as error:
        return f"Falha ao ler arquivo: {error}"


def list_directory(pasta: str = ".") -> str:
    try:
        alvo = _resolve_readable_path(pasta)
        if not alvo.is_dir():
            return f"Falha ao listar diretório: '{pasta}' não é uma pasta existente."
        itens = []
        entradas = sorted(alvo.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
        for entrada in entradas:
            if entrada.name.casefold() in PROTECTED_DIRS:
                continue
            itens.append(entrada.name + ("/" if entrada.is_dir() else ""))
        if not itens:
            return "(pasta vazia)"
        texto = "\n".join(itens[:200])
        if len(itens) > 200:
            texto += f"\n... e mais {len(itens) - 200} itens"
        return texto
    except (OSError, PermissionError, ValueError) as error:
        return f"Falha ao listar diretório: {error}"

def get_weather_data() -> dict:
    global last_weather_fetch, cached_weather
    now = time.time()
    if now - last_weather_fetch < 600 and cached_weather["temperatura"] != "--":
        return cached_weather
    try:
        url = "https://wttr.in/Curitiba?format=j1&lang=pt"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            current = data["current_condition"][0]
            cached_weather = {
                "cidade": "CURITIBA (SANTA CÂNDIDA), PR",
                "temperatura": f"{current.get('temp_C', '0')}°C",
                "condicao": current.get("lang_pt", [{}])[0].get("value") or "Tempo Estável",
                "umidade": f"{current.get('humidity', '0')}%"
            }
            last_weather_fetch = now
    except Exception: pass
    return cached_weather

def get_full_telemetry() -> dict:
    global real_cpu_usage, real_cpu_cores, last_net_time, last_net_bytes
    cpu_val = real_cpu_usage if real_cpu_usage > 0.0 else psutil.cpu_percent(interval=0.05)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("C:")
    now = time.time()
    current_net = psutil.net_io_counters()
    time_delta = max(0.1, now - last_net_time)
    down_kbs = round(((current_net.bytes_recv - last_net_bytes.bytes_recv) / 1024) / time_delta, 1)
    up_kbs = round(((current_net.bytes_sent - last_net_bytes.bytes_sent) / 1024) / time_delta, 1)
    last_net_time = now
    last_net_bytes = current_net
    return {
        "cpu_percent": round(cpu_val, 1),
        "cpu_cores": real_cpu_cores,
        "ram_percent": ram.percent,
        "ram_used_gb": round(ram.used / (1024**3), 2),
        "ram_total_gb": round(ram.total / (1024**3), 2),
        "disk_percent": disk.percent,
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "net_down_kbs": down_kbs,
        "net_up_kbs": up_kbs,
        "active_mode": current_mode,
        "weather": get_weather_data()
    }

TOOLS_MAP = {
    "generate_roblox_script": generate_roblox_script,
    "play_roblox_studio": play_roblox_studio,
    "blender_render_background": blender_render_background,
    "generate_blender_script": generate_blender_script,
    "edit_blender_project": edit_blender_project,
    "set_volume": set_volume,
    "send_notification": send_notification,
    "play_music": play_music,
    "media_control": media_control,
    "read_clipboard": read_clipboard,
    "copy_to_clipboard": copy_to_clipboard,
    "get_full_telemetry": get_full_telemetry,
    "analyze_screen": analyze_screen,
    "write_file": write_file,
    "read_file": read_file,
    "open_website": open_website,
    "open_app": open_app,
    "close_app": close_app,
    "search_google": search_google,
    "list_directory": list_directory,
    "set_operational_mode": set_operational_mode
}

TOOL_REGISTRY = build_tool_registry(TOOLS_MAP)
TOOLS_DEFINITIONS = [
    specification.function
    for specification in TOOL_REGISTRY.values()
]