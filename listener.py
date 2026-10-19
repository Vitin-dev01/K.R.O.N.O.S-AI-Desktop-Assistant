import os
import io
import time
import wave
import threading
import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types
from config import key_rotator, CASCATA_MODELOS

SAMPLE_RATE = 16000
CHANNELS = 1
SILENCE_THRESHOLD = 0.022  # Sensibilidade de captação de voz
SILENCE_DURATION = 1.1     # Pausa que indica fim da frase

class KronosListener:
    def __init__(self, on_command_callback):
        self.on_command = on_command_callback
        self.is_listening = False
        self.audio_buffer = []

    def _transcribe(self, wav_bytes: bytes) -> str:
        """Transcreve o áudio com cascata de contingência de modelos."""
        for model_name in CASCATA_MODELOS:
            try:
                client = genai.Client(api_key=key_rotator.current_key)
                response = client.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
                        "Transcreva com exatidão o que foi dito em português do Brasil. "
                        "Retorne APENAS o texto puro sem aspas, formatação Markdown ou comentários."
                    ]
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                err_msg = str(e).lower()
                print(f"\n[AVISO - TRANSCRIÇÃO ({model_name})]: {err_msg}")
                if "404" in err_msg or "not found" in err_msg:
                    continue
                key_rotator.rotate(f"Falha de transcrição em {model_name}")
        return ""

    def _audio_callback(self, indata, frames, time_info, status):
        vol = np.linalg.norm(indata) / np.sqrt(len(indata))
        self.audio_buffer.append((indata.copy(), vol))

    def start(self):
        """Inicia escuta contínua em thread separada."""
        self.is_listening = True
        threading.Thread(target=self._listen_loop, daemon=True).start()

    def stop(self):
        """Interrompe a escuta contínua."""
        self.is_listening = False

    def _listen_loop(self):
        print("\n[MICROFONE] KRONOS escuta contínua ativa. Diga 'Kronos...'")
        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, callback=self._audio_callback):
                while self.is_listening:
                    time.sleep(0.08)
                    # Detecta voz acima do ruído ambiente
                    if self.audio_buffer and any(v > SILENCE_THRESHOLD for _, v in self.audio_buffer[-4:]):
                        recording = []
                        silence_start = None

                        while self.is_listening:
                            if self.audio_buffer:
                                chunk, v = self.audio_buffer.pop(0)
                                recording.append(chunk)

                                if v < SILENCE_THRESHOLD:
                                    if silence_start is None:
                                        silence_start = time.time()
                                    elif time.time() - silence_start > SILENCE_DURATION:
                                        break
                                else:
                                    silence_start = None
                            time.sleep(0.02)

                        if len(recording) > 12:
                            audio_arr = np.concatenate(recording, axis=0)

                            wav_io = io.BytesIO()
                            with wave.open(wav_io, 'wb') as wf:
                                wf.setnchannels(CHANNELS)
                                wf.setsampwidth(2)
                                wf.setframerate(SAMPLE_RATE)
                                wf.writeframes((audio_arr * 32767).astype(np.int16).tobytes())

                            text = self._transcribe(wav_io.getvalue())

                            if text:
                                lower = text.lower()
                                # Gatilho de invocação: só aciona se invocar nominalmente
                                if "kronos" in lower or "cronos" in lower:
                                    print(f"\n[VOZ RECONHECIDA]: {text}")
                                    clean = lower.replace("kronos", "").replace("cronos", "").strip(" ,.!?")
                                    cmd = clean if clean else "Olá"
                                    if callable(self.on_command):
                                        self.on_command(cmd)
        except Exception as e:
            print(f"\n[ERRO MICROFONE ESCUTA CONTÍNUA]: {str(e)}")