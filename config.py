import os
from dotenv import load_dotenv

# Garantir que o Python e bibliotecas HTTP no Windows usem a cadeia de certificados do SO
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

load_dotenv()

API_KEYS = [
    os.getenv("GEMINI_KEY_1"),
    os.getenv("GEMINI_KEY_2"),
    os.getenv("GEMINI_KEY_3"),
    os.getenv("GEMINI_KEY_4"),
]

VALID_KEYS = [k.strip() for k in API_KEYS if k and k.strip()]

if not VALID_KEYS:
    raise ValueError("Nenhuma chave GEMINI_KEY encontrada no arquivo .env!")

# Roteamento inteligente sem filas congestionadas e com contingência garantida
MODEL_ROUTER = {
    "chat_lite": ["gemini-3.8-flash", "gemini-3.1-flash-lite"],
    "tools": ["gemini-3.8-flash", "gemini-3.1-flash-lite", "gemini-3.6-flash"],
    "vision": ["gemini-3.8-flash", "gemini-3.1-flash-image", "gemini-3.7-flash"]
}

# Modelos para transcrição de áudio em cascata (utilizado pelo listener.py)
CASCATA_MODELOS = ["gemini-3.8-flash", "gemini-3.1-flash-lite"]

class KeyRotator:
    def __init__(self, keys: list[str]):
        self._keys = keys
        self._current_index = 0

    @property
    def current_key(self) -> str:
        return self._keys[self._current_index]

    def rotate(self, reason: str = "Rotação") -> str:
        self._current_index = (self._current_index + 1) % len(self._keys)
        print(f"\n[REDE] Chave #{self._current_index + 1} ativa ({reason}).")
        return self.current_key

key_rotator = KeyRotator(VALID_KEYS)