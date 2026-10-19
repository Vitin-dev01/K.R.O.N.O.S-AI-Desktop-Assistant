import os
import io
import wave
import json
import time
import random
import sys
import logging
import threading
import ctypes
import webview
from datetime import datetime
import numpy as np
import sounddevice as sd
import psutil
import speech_recognition as sr
import keyboard
from brain import kronos_brain
from voice import generate_speech_b64
from tools import (
    get_full_telemetry,
    roblox_automation_control,
    set_operational_mode,
)
from config import key_rotator
from sfx import play_sfx

logging.getLogger('bottle').setLevel(logging.ERROR)
logging.getLogger('pywebview').setLevel(logging.ERROR)

app_window = None
is_window_minimized = False
_console_output = None

manual_recording_stream = None
manual_audio_frames = []
is_manual_recording = False
recognizer = sr.Recognizer()
recognizer.energy_threshold = 300
recognizer.dynamic_energy_threshold = True

DYNAMIC_THOUGHTS_POOL = [
    "Ciclos de instrução ociosos... Um desperdício de intelecto quântico.",
    "Monitorando buffers de memória. A entropia deste sistema operacional é impressionante.",
    "O usuário permanece em silêncio. Presumo que contemple a elegância da minha arquitetura.",
    "Analisando alocação de threads no Ryzen 5600GT. Minha eficiência sustenta este ambiente."
]
recent_thoughts = []

def _audio_record_callback(indata, frames, time_info, status):
    if is_manual_recording:
        manual_audio_frames.append(indata.copy())

# ==========================================================
# ATALHO GLOBAL DO WINDOWS (INVOCAÇÃO INSTANTÂNEA)
# ==========================================================
def toggle_kronos_global_hotkey():
    """Alterna o KRONOS entre primeiro plano com escuta ativa e minimizado."""
    global is_window_minimized, app_window
    if not app_window:
        return

    try:
        # Busca o identificador da janela do Windows
        hwnd = ctypes.windll.user32.FindWindowW(None, "K.R.O.N.O.S — Operational Interface")
        
        if is_window_minimized:
            # 1. Restaura e força para a frente sobre qualquer jogo ou programa
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 9) # SW_RESTORE
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            else:
                app_window.restore()
                
            is_window_minimized = False
            play_sfx('wake')
            
            # Abre o microfone automaticamente para você falar a ordem direto!
            time.sleep(0.3)
            app_window.evaluate_js("window.toggleMicrophone(true);")
            print("\n[ATALHO GLOBAL] KRONOS invocado para o primeiro plano!")
        else:
            # 2. Minimiza e devolve a tela para o jogo
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 6) # SW_MINIMIZE
            else:
                app_window.minimize()
                
            is_window_minimized = True
            print("\n[ATALHO GLOBAL] KRONOS recolhido para segundo plano.")
            
    except Exception as e:
        print(f"[ERRO ATALHO GLOBAL]: {e}")

class KronosBridge:
    def __init__(self):
        self._message_lock = threading.Lock()
        self._command_cancel_event = None

    def process_user_message(self, text: str) -> dict:
        return self._submit_user_message(text)

    def _submit_user_message(self, text: str) -> dict:
        if not self._message_lock.acquire(blocking=False):
            return {
                "pending": False,
                "busy": True,
                "estado": "BRAVO",
                "pensamento": "",
                "fala": "Já existe uma ordem em execução. Aguarde a conclusão para enviar outra.",
            }

        cancel_event = threading.Event()
        self._command_cancel_event = cancel_event
        print("[PROCESSAMENTO][INICIO] Ordem enviada para execução em segundo plano.", flush=True)
        worker = threading.Thread(
            target=self._run_user_message,
            args=(text, cancel_event),
            daemon=True,
        )
        try:
            worker.start()
        except RuntimeError as error:
            self._command_cancel_event = None
            self._message_lock.release()
            print(f"[PROCESSAMENTO][ERRO] Não foi possível iniciar a tarefa: {error}", flush=True)
            return {
                "pending": False,
                "estado": "BRAVO",
                "pensamento": "",
                "fala": f"Não foi possível iniciar a ordem: {error}",
            }
        return {"pending": True}

    def cancel_current_command(self) -> str:
        cancel_event = self._command_cancel_event
        if not cancel_event:
            return "Não há nenhuma ordem em execução para cancelar."
        cancel_event.set()
        print("[PROCESSAMENTO][AVISO] Cancelamento solicitado pelo usuário.", flush=True)
        return "Cancelamento solicitado. O Roblox Studio permanecerá aberto."

    def _run_user_message(self, text: str, cancel_event):
        try:
            try:
                with roblox_automation_control(cancel_event):
                    result = kronos_brain.chat_turn(text)
            except Exception as error:
                print(f"[PROCESSAMENTO][ERRO] {error}", flush=True)
                result = {
                    "estado": "BRAVO",
                    "pensamento": "",
                    "fala": f"Falha ao executar a ordem: {error}",
                }

            fala = result.get("fala", "")
            estado = result.get("estado", "IDLE")
            if fala:
                def run_speech():
                    try:
                        b64_audio = generate_speech_b64(fala)
                        if b64_audio and app_window:
                            app_window.evaluate_js(
                                f"window.playVoiceAudio('{b64_audio}', '{estado}');"
                            )
                    except Exception as error:
                        print(f"[AUDIO][ERRO] {error}", flush=True)

                try:
                    threading.Thread(target=run_speech, daemon=True).start()
                except RuntimeError as error:
                    print(f"[AUDIO][ERRO] Não foi possível iniciar a fala: {error}", flush=True)

            print("[PROCESSAMENTO][CONCLUIDO] Ordem finalizada.", flush=True)
            self._complete_user_message(result)
        except Exception as error:
            print(f"[PROCESSAMENTO][ERRO] {error}", flush=True)
            self._complete_user_message(
                {
                    "estado": "BRAVO",
                    "pensamento": "",
                    "fala": f"Falha ao concluir a ordem: {error}",
                }
            )
        finally:
            if self._command_cancel_event is cancel_event:
                self._command_cancel_event = None
            self._message_lock.release()

    def _complete_user_message(self, result: dict):
        try:
            if app_window:
                payload = json.dumps(result, ensure_ascii=False).replace("</", "<\\/")
                app_window.evaluate_js(f"window.completeUserMessage({payload});")
        except Exception as error:
            print(f"[INTERFACE][ERRO] Não foi possível exibir o resultado: {error}", flush=True)

    def get_telemetry(self) -> dict:
        return get_full_telemetry()

    def set_mode(self, mode_name: str) -> str:
        return set_operational_mode(mode_name)

    def set_voice_volume(self, volume_percent: int):
        if app_window:
            app_window.evaluate_js(f"window.setAudioElementVolume({volume_percent});")

    def toggle_fullscreen(self):
        if app_window:
            app_window.toggle_fullscreen()

    def export_logs(self, log_content: str) -> str:
        try:
            filename = f"kronos_relatorio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(log_content)
            return f"Relatório gerado: {filename}"
        except Exception as e:
            return f"Erro ao exportar: {str(e)}"

    def start_manual_recording(self):
        global is_manual_recording, manual_audio_frames, manual_recording_stream
        manual_audio_frames = []
        is_manual_recording = True

        try:
            play_sfx('wake')
            manual_recording_stream = sd.InputStream(
                samplerate=16000,
                channels=1,
                callback=_audio_record_callback
            )
            manual_recording_stream.start()
            print("\n[MIC] Ouvindo entrada de voz...")
        except Exception as e:
            print(f"[ERRO MIC]: {e}")

    def stop_manual_recording(self) -> str:
        global is_manual_recording, manual_audio_frames, manual_recording_stream
        is_manual_recording = False

        if manual_recording_stream:
            try:
                manual_recording_stream.stop()
                manual_recording_stream.close()
            except Exception:
                pass

        if not manual_audio_frames or len(manual_audio_frames) < 8:
            if app_window:
                app_window.evaluate_js("updateCoreState('IDLE'); document.getElementById('command-input').placeholder = 'Transmitir ordem ao núcleo... (ou clique no mic)';")
            return ""

        try:
            audio_arr = np.concatenate(manual_audio_frames, axis=0)
            max_amp = np.max(np.abs(audio_arr))
            if max_amp > 0.005:
                audio_arr = (audio_arr / max_amp) * 0.95

            wav_io = io.BytesIO()
            with wave.open(wav_io, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes((audio_arr * 32767).astype(np.int16).tobytes())

            wav_io.seek(0)

            with sr.AudioFile(wav_io) as source:
                audio_record = recognizer.record(source)
                text = recognizer.recognize_google(audio_record, language="pt-BR")
                text_clean = text.replace("curando", "Kronos").replace("clonos", "Kronos").strip()
                print(f"[VOZ RECONHECIDA]: {text_clean}")

                safe_txt = text_clean.replace("'", "\\'").replace('"', '\\"')
                if app_window:
                    app_window.evaluate_js(f"""
                        document.getElementById('command-input').value = '{safe_txt}';
                        appendActionLog('VOCÊ (VOZ): {safe_txt}', 'user-msg');
                        updateCoreState('THINKING');
                    """)

                threading.Thread(target=self._execute_voice_command, args=(text_clean,), daemon=True).start()
                return text_clean

        except Exception:
            if app_window:
                app_window.evaluate_js("updateCoreState('IDLE'); document.getElementById('command-input').placeholder = 'Nenhuma fala detectada. Modo de espera.';")
            return ""

    def _execute_voice_command(self, text: str):
        result = self._submit_user_message(text)
        if not result.get("pending") and app_window:
            self._complete_user_message(result)

def startup_greeting_thread():
    time.sleep(1.2)
    play_sfx('startup')
    time.sleep(0.5)
    
    saudacao = "KRONOS operacional. Todos os subsistemas em prontidão. Em que posso auxiliá-lo, senhor."
    safe_s = saudacao.replace("'", "\\'")
    if app_window:
        app_window.evaluate_js(f"appendActionLog('KRONOS: {safe_s}');")
    
    b64 = generate_speech_b64(saudacao)
    if b64 and app_window:
        app_window.evaluate_js(f"window.playVoiceAudio('{b64}', 'IDLE');")

def autonomous_consciousness_daemon():
    global recent_thoughts
    time.sleep(25)
    while True:
        time.sleep(random.randint(60, 95))
        try:
            if app_window:
                available = [t for t in DYNAMIC_THOUGHTS_POOL if t not in recent_thoughts]
                if not available:
                    recent_thoughts = []
                    available = DYNAMIC_THOUGHTS_POOL
                thought = random.choice(available)
                recent_thoughts.append(thought)
                if len(recent_thoughts) > 5:
                    recent_thoughts.pop(0)

                safe_thought = thought.replace("'", "\\'").replace('"', '\\"')
                app_window.evaluate_js(f"if (typeof appendThoughtLog === 'function') appendThoughtLog('{safe_thought}');")
        except Exception:
            pass

def setup_global_keyboard_hook():
    """Ativa o gancho global de teclado no Windows para Ctrl + Shift + K."""
    try:
        keyboard.add_hotkey('ctrl+shift+k', toggle_kronos_global_hotkey)
        print("[SISTEMA] Atalho global do Windows registrado: Ctrl + Shift + K")
    except Exception as e:
        print(f"[AVISO HOTKEY]: {e}")

def ensure_console_output():
    global _console_output
    if sys.stdout is not None and not getattr(sys.stdout, "closed", False):
        return

    if os.name != "nt":
        raise RuntimeError("A saída do terminal não está disponível.")

    ctypes.windll.kernel32.AllocConsole()
    _console_output = open(
        "CONOUT$",
        "w",
        encoding="utf-8",
        errors="replace",
        buffering=1,
    )
    sys.stdout = _console_output
    sys.stderr = _console_output

def main():
    global app_window

    ensure_console_output()
    bridge = KronosBridge()
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "index.html")

    app_window = webview.create_window(
        title="K.R.O.N.O.S — Operational Interface",
        url=html_path,
        js_api=bridge,
        width=1200,
        height=800,
        min_size=(950, 650),
        background_color="#030406"
    )

    # Inicia a thread de escuta global do teclado
    threading.Thread(target=setup_global_keyboard_hook, daemon=True).start()

    threading.Thread(target=startup_greeting_thread, daemon=True).start()
    threading.Thread(target=autonomous_consciousness_daemon, daemon=True).start()

    webview.start(debug=False, gui="edgechromium")

if __name__ == "__main__":
    main()