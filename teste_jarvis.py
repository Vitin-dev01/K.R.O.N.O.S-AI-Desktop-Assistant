import base64
import io
import os
import time
import wave

import numpy as np
import sounddevice as sd
from google import genai

from config import key_rotator

MODELO = "gemini-3.8-flash-tts"
TOCAR_NO_FINAL = True
PASTA = "voz_teste_jarvis"

# Vozes masculinas do Gemini que valem testar. Se alguma der erro, o script pula.
VOZES = ["Algieba", "Orus", "Iapetus", "Schedar", "Alnilam", "Umbriel"]

ESTILOS = {
    "mordomo": (
        "Fale em português brasileiro com voz masculina grave, calma e polida, "
        "como um mordomo muito inteligente e discreto. Ritmo pausado e controlado, "
        "volume baixo, dicção impecável, ironia seca e sutil. "
        "Nunca grite, nunca exagere na emoção."
    ),
    "deboche_frio": (
        "Fale em português brasileiro com voz masculina grave e serena. "
        "Tom completamente frio e sem pressa, como quem acha tudo um pouco "
        "entediante e superior, mas continua educado. Pausas curtas antes das "
        "ironias, final de frase caindo suavemente. Sem teatralidade."
    ),
}

TEXTO = (
    "Bom dia, criador. Todos os sistemas estão operacionais. "
    "Devo admitir que você demorou, mas já me acostumei com isso."
)


def gerar_wav(client, voz, estilo):
    interaction = client.interactions.create(
        model=MODELO,
        input=[
            {
                "type": "user_input",
                "content": [
                    {
                        "type": "text",
                        "text": TEXTO,
                        "annotations": [{"type": "speech_metadata", "style": estilo}],
                    }
                ],
            }
        ],
        response_format={"type": "audio"},
        generation_config={"speech_config": [{"voice": voz}]},
    )
    audio = getattr(interaction, "output_audio", None)
    b64 = getattr(audio, "data", "") or ""
    return base64.b64decode(b64) if b64 else b""


def tocar(wav_bytes):
    with io.BytesIO(wav_bytes) as bio:
        with wave.open(bio, "rb") as wf:
            taxa = wf.getframerate()
            canais = wf.getnchannels()
            frames = wf.readframes(wf.getnframes())
    audio = np.frombuffer(frames, dtype=np.int16)
    if canais > 1:
        audio = audio.reshape(-1, canais)
    sd.play(audio, taxa)
    sd.wait()


def main():
    os.makedirs(PASTA, exist_ok=True)
    gerados = []

    for nome_estilo, estilo in ESTILOS.items():
        for voz in VOZES:
            print(f"[GERANDO] {voz} | {nome_estilo} ...", flush=True)
            try:
                client = genai.Client(api_key=key_rotator.current_key)
                wav = gerar_wav(client, voz, estilo)
                if not wav:
                    print("   sem áudio retornado")
                    continue
                caminho = os.path.join(PASTA, f"{voz}__{nome_estilo}.wav")
                with open(caminho, "wb") as f:
                    f.write(wav)
                gerados.append((voz, nome_estilo, wav))
                print(f"   salvo em {caminho}")
            except Exception as erro:
                print(f"   erro: {type(erro).__name__}: {erro}")
                key_rotator.rotate("Teste voz")
            time.sleep(1)

    if TOCAR_NO_FINAL:
        print("\n=== TOCANDO TUDO, anote os melhores ===")
        for voz, nome_estilo, wav in gerados:
            print(f">>> {voz} | {nome_estilo}", flush=True)
            tocar(wav)
            time.sleep(0.8)


if __name__ == "__main__":
    main()