"""
memoria.py — Memória de leads já enriquecidos (não re-rodar o enriquecimento).

Cada lead vira um UUID DETERMINÍSTICO a partir do NOME (Outscraper) + cidade.
Quando o mesmo nome+cidade volta, o /enrich PULA — não gasta Tavily/Apify/LLM
nem duplica trabalho. Persistência em SQLite (stdlib, sem dependência).

⚠️ No EasyPanel, aponte MEMORIA_PATH para um VOLUME persistente (ex.:
/data/memoria.db) — senão a memória zera a cada redeploy.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from app.normalize import normalizar

# Namespace fixo — garante UUID estável p/ o mesmo nome+cidade entre execuções.
_NS = uuid.uuid5(uuid.NAMESPACE_DNS, "rede360.prospeccao.lumix")
_lock = threading.Lock()


def uuid_de(nome: str, cidade: str = "") -> str:
    """UUID determinístico do lead (mesmo nome+cidade -> sempre o mesmo UUID)."""
    chave = normalizar(nome) + "|" + normalizar(cidade)
    return str(uuid.uuid5(_NS, chave))


class Memoria:
    def __init__(self, path: str | None = None):
        self.path = path or os.getenv("MEMORIA_PATH", "data/memoria.db")
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        with self._conn() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS processados ("
                "uuid TEXT PRIMARY KEY, nome TEXT, cidade TEXT, primeira_vez TEXT)"
            )

    def _conn(self):
        return sqlite3.connect(self.path, timeout=10)

    def ja_visto(self, uid: str) -> bool:
        with self._conn() as c:
            return c.execute("SELECT 1 FROM processados WHERE uuid=?", (uid,)).fetchone() is not None

    def marcar(self, uid: str, nome: str = "", cidade: str = "") -> None:
        with _lock, self._conn() as c:
            c.execute(
                "INSERT OR IGNORE INTO processados (uuid, nome, cidade, primeira_vez) VALUES (?,?,?,?)",
                (uid, nome, cidade, datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )

    def total(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM processados").fetchone()[0]

    def limpar(self) -> int:
        with _lock, self._conn() as c:
            n = c.execute("SELECT COUNT(*) FROM processados").fetchone()[0]
            c.execute("DELETE FROM processados")
            return n
