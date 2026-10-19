import io
import wave
import re
import time
import base64
import sys
from array import array
from google import genai
from google.genai import types
from config import key_rotator

TTS_CASCATA = [
    "gemini-3.8-flash-tts",
    "gemini-2.5-flash-preview-tts",
]
SPEECH_SAMPLE_RATE = 24000
KRONOS_VOICE = "Orus"
KRONOS_SPEECH_STYLE = (
    "Fale em português brasileiro com voz masculina grave e serena. "
    "Tom completamente frio e sem pressa, como quem acha tudo um pouco "
    "entediante e superior, mas continua educado. Pausas curtas antes das "
    "ironias, final de frase caindo suavemente. Sem teatralidade."
)

def _prepare_text(text: str) -> str:
    """Remove marcação de resposta sem apagar a prosódia da pontuação."""
    t = re.sub(r"===.+?===", "", text)
    t = re.sub(r"[💭•\*\#\_\[\]\(\)]", "", t)
    t = re.sub(r"\s*[—–]\s*", ", ", t)
    t = re.sub(r"\.{3,}", "...", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()

def _save_pcm_to_wav_bytes(pcm_bytes: bytes) -> bytes:
    if len(pcm_bytes) % 2:
        raise ValueError("O áudio PCM contém uma amostra incompleta.")

    samples = array("h")
    samples.frombytes(pcm_bytes)
    if sys.byteorder != "little":
        samples.byteswap()

    fade_samples = min(len(samples), SPEECH_SAMPLE_RATE * 30 // 1000)
    if fade_samples:
        fade_start = len(samples) - fade_samples
        fade_denominator = max(1, fade_samples - 1)
        for index in range(fade_start, len(samples)):
            gain = (len(samples) - 1 - index) / fade_denominator
            samples[index] = round(samples[index] * gain)

    if sys.byteorder != "little":
        samples.byteswap()

    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SPEECH_SAMPLE_RATE)
        wf.writeframes(samples.tobytes())
    return wav_io.getvalue()

def _generate_tts_audio(client, model: str, clean: str) -> str:
    if model == "gemini-3.8-flash-tts":
        interaction = client.interactions.create(
            model=model,
            input=[
                {
                    "type": "user_input",
                    "content": [
                        {
                            "type": "text",
                            "text": clean,
                            "annotations": [
                                {
                                    "type": "speech_metadata",
                                    "style": KRONOS_SPEECH_STYLE,
                                }
                            ],
                        }
                    ],
                }
            ],
            response_format={"type": "audio"},
            generation_config={"speech_config": [{"voice": KRONOS_VOICE}]},
        )
        audio = getattr(interaction, "output_audio", None)
        return getattr(audio, "data", "") or ""

    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            language_code="pt-BR",
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=KRONOS_VOICE
                )
            )
        )
    )
    response = client.models.generate_content(
        model=model,
        contents=f"Fale o texto a seguir com {KRONOS_SPEECH_STYLE} Texto: {clean}",
        config=config
    )
    for candidate in getattr(response, "candidates", []):
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []):
            inline_data = getattr(part, "inline_data", None)
            if inline_data:
                raw_pcm = inline_data.data
                wav_bytes = _save_pcm_to_wav_bytes(raw_pcm)
                return base64.b64encode(wav_bytes).decode("utf-8")
    return ""

def generate_speech_b64(text: str) -> str:
    clean = _prepare_text(text)
    if not clean:
        return ""

    for tts_model in TTS_CASCATA:
        for _ in range(len(key_rotator._keys)):
            try:
                client = genai.Client(api_key=key_rotator.current_key)
                audio_b64 = _generate_tts_audio(client, tts_model, clean)
                if audio_b64:
                    print(
                        f"[VOZ][GERADA] modelo={tts_model}; voz={KRONOS_VOICE}",
                        flush=True,
                    )
                    return audio_b64
            except Exception as error:
                print(
                    f"[VOZ][AVISO] Falha no modelo {tts_model}: "
                    f"{type(error).__name__}: {error}",
                    flush=True,
                )
                key_rotator.rotate("Contingência Voz")
                time.sleep(0.3)

    return ""


def speak(text: str):
    """Gera o áudio da fala do KRONOS e reproduz no dispositivo de som."""
    b64 = generate_speech_b64(text)
    if not b64:
        return
    try:
        wav_bytes = base64.b64decode(b64)
        with io.BytesIO(wav_bytes) as bio:
            with wave.open(bio, "rb") as wf:
                sample_rate = wf.getframerate()
                channels = wf.getnchannels()
                frames = wf.readframes(wf.getnframes())
                import numpy as np
                import sounddevice as sd
                audio_array = np.frombuffer(frames, dtype=np.int16)
                if channels > 1:
                    audio_array = audio_array.reshape(-1, channels)
                sd.play(audio_array, sample_rate)
                sd.wait()
    except Exception as e:
        print(f"[VOZ][AVISO] Falha ao reproduzir áudio: {e}", flush=True)
