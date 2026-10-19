import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kronos_memory.db")

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()

def init_memory():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chave TEXT UNIQUE,
                valor TEXT
            )
        """)
        cursor.execute("INSERT OR IGNORE INTO facts (chave, valor) VALUES ('usuario_local', 'Curitiba, Santa Cândida, Paraná')")
        cursor.execute("INSERT OR IGNORE INTO facts (chave, valor) VALUES ('softwares_principais', 'Blender, Roblox Studio e ferramentas 3D')")
        cursor.execute("INSERT OR IGNORE INTO facts (chave, valor) VALUES ('hardware', 'Ryzen 5 5600GT com 16GB de RAM e vídeo integrado Radeon')")
        conn.commit()

def get_all_facts() -> str:
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chave, valor FROM facts")
            rows = cursor.fetchall()
            return "; ".join([f"{k}: {v}" for k, v in rows]) if rows else "Nenhum dado pessoal."
    except Exception:
        return ""

def save_fact(chave: str, valor: str):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO facts (chave, valor) VALUES (?, ?)", (chave, valor))
            conn.commit()
    except Exception:
        pass

init_memory()