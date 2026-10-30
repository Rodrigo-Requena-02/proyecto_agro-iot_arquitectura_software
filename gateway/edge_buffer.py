"""Cache local SQLite del gateway (ADR-001): nada se pierde si el API o la red caen."""
import json
import sqlite3
import threading


class EdgeBuffer:
    def __init__(self, ruta: str):
        self.db = sqlite3.connect(ruta, check_same_thread=False)
        self.lock = threading.Lock()
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS lecturas (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 payload TEXT NOT NULL,
                 estado TEXT NOT NULL DEFAULT 'PENDIENTE')"""
        )
        self.db.commit()

    def guardar(self, lectura: dict) -> None:
        with self.lock:
            self.db.execute("INSERT INTO lecturas (payload) VALUES (?)", (json.dumps(lectura),))
            self.db.commit()

    def pendientes(self, limite: int = 200) -> list[tuple[int, dict]]:
        with self.lock:
            filas = self.db.execute(
                "SELECT id, payload FROM lecturas WHERE estado='PENDIENTE' ORDER BY id LIMIT ?", (limite,)
            ).fetchall()
        return [(i, json.loads(p)) for i, p in filas]

    def contar_pendientes(self) -> int:
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM lecturas WHERE estado='PENDIENTE'").fetchone()[0]

    def marcar(self, ids: list[int], estado: str) -> None:
        if not ids:
            return
        with self.lock:
            self.db.executemany("UPDATE lecturas SET estado=? WHERE id=?", [(estado, i) for i in ids])
            self.db.commit()
