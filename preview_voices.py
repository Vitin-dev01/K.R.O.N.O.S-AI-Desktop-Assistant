import os
import wave
import time
import pygame
from google import genai
from google.genai import types
from config import key_rotator

pygame.mixer.init()

VOZES_PARA_TESTE = ["Fenrir", "Orpheus", "Charon"]
FRASE_TESTE = "Eu sou KRONOS. Minha arquitetura computacional opera com precisão cirúrgica."

def save_wav(pcm_bytes, filename):
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm_bytes)

def testar():
    client = genai.Client(api_key=key_rotator.current_key)
    
    for voz in VOZES_PARA_TESTE:
        print(f"\n[GERANDO VOZ]: {voz}...")
        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config={
                "voice_config": {
                    "prebuilt_voice_config": {
                        "voice_name": voz
                    }
                }
            }
        )
        
        try:
            resp = client.models.generate_content(
                model="gemini-3.8-flash-tts",
                contents=f"Fale com tom de homem maduro, voz grossa, firme e sem desafinar: {FRASE_TESTE}",
                config=config
            )
            
            for part in resp.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    filename = f"teste_{voz}.wav"
                    save_wav(part.inline_data.data, filename)
                    
                    print(f"--> TOCANDO AGORA: {voz} (Preste atenção no timbre)")
                    pygame.mixer.music.load(filename)
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy():
                        pygame.time.Clock().tick(10)
                    pygame.mixer.music.unload()
                    time.sleep(1)
                    break
        except Exception as e:
            print(f"Erro em {voz}: {e}")

if __name__ == "__main__":
    testar()