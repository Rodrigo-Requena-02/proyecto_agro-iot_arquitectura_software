#!/usr/bin/env python3
import argparse
import json
import math
import os
import random
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone

import requests

# Rangos fisicos aceptados (los mismos que valida el API: defensa en profundidad)
RANGOS = {"t": (-40, 60), "h": (0, 100), "r": (0, 1500), "p": (0, 10)}

# Letra de sector (campo "s" del Arduino) -> id de sector en la API, y el jefe de terreno de cada uno.
SECTORES = {"A": 1, "B": 2, "C": 3}
JEFE_DE_SECTOR = {1: "jefe.a@agro.cl", 2: "jefe.b@agro.cl", 3: "jefe.c@agro.cl"}


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------------- parseo
def parsear_linea(linea: str, sector_id: int, sectores: dict[str, int] | None = None) -> dict | None:
    """Convierte una linea del Arduino en el JSON que espera el API.

    Devuelve None si es un comentario ('# ...') o vacia. Lanza ValueError si esta malformada
    o fuera de rango (por ejemplo ruido al abrir el puerto, o un sensor defectuoso).

    Si la linea trae el campo "s" (letra de sector) se usa para elegir el sector; si no, `sector_id`.
    """
    linea = linea.strip()
    if not linea or linea.startswith("#"):
        return None
    try:
        d = json.loads(linea)
    except json.JSONDecodeError:
        raise ValueError(f"linea no es JSON: {linea[:60]!r}")
    if not isinstance(d, dict):
        raise ValueError("el JSON no es un objeto")

    for k, (lo, hi) in RANGOS.items():
        v = d.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or math.isnan(v) or math.isinf(v):
            raise ValueError(f"campo '{k}' ausente o no numerico")
        if not lo <= v <= hi:
            raise ValueError(f"campo '{k}'={v} fuera de rango [{lo}, {hi}]")

    if "s" in d:
        destino = (sectores or SECTORES).get(str(d["s"]).upper())
        if destino is None:
            raise ValueError(f"sector desconocido: {d['s']!r}")
        sector_id = destino

    sensor = str(d.get("id", "UNO-A01"))
    return {
        "sector_id": sector_id,
        "sensor_id": sensor,
        "temperatura_c": float(d["t"]),
        "humedad_suelo_pct": float(d["h"]),
        "radiacion_wm2": float(d["r"]),
        "presion_bar": float(d["p"]),
        # El Arduino no tiene reloj: el gateway sella el instante real de recepcion (UTC).
        "tomada_en": datetime.now(timezone.utc).isoformat(),
    }


# --------------------------------------------------------------------------- buffer edge
class EdgeBuffer:
    """Cache local SQLite (ADR-001): nada se pierde si el API o la red caen."""

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


# --------------------------------------------------------------------------- cliente API
class SinConexion(Exception):
    pass


class Rechazado(Exception):
    def __init__(self, status: int, mensaje: str):
        super().__init__(mensaje)
        self.status = status


class ApiClient:
    def __init__(self, base: str, email: str, password: str):
        self.base, self.email, self.password = base.rstrip("/"), email, password
        self.token: str | None = None

    def _req(self, metodo: str, ruta: str, **kw):
        try:
            return requests.request(metodo, self.base + ruta, timeout=5, **kw)
        except (requests.ConnectionError, requests.Timeout):
            raise SinConexion("API no disponible")

    def login(self) -> None:
        r = self._req("POST", "/api/v1/auth/login", json={"email": self.email, "password": self.password})
        if r.status_code != 200:
            msg = r.json().get("error", {}).get("message", r.text) if r.content else r.text
            raise Rechazado(r.status_code, f"login fallido: {msg}")
        self.token = r.json()["access_token"]
        log(f"Autenticado como {self.email}")

    def enviar_lote(self, lecturas: list[dict]) -> dict:
        for intento in (1, 2):
            if not self.token:
                self.login()
            r = self._req("POST", "/api/v1/telemetria/lote", json={"lecturas": lecturas},
                          headers={"Authorization": f"Bearer {self.token}"})
            if r.status_code == 401 and intento == 1:  # token vencido: renovar y reintentar
                self.token = None
                continue
            if r.status_code >= 500:
                raise SinConexion(f"API respondio {r.status_code}")
            if r.status_code >= 400:
                msg = r.json().get("error", {}).get("message", r.text) if r.content else r.text
                raise Rechazado(r.status_code, msg)
            return r.json()
        raise Rechazado(401, "no autorizado")


class ApiPorSector:
    """Un ApiClient por sector: cada lectura se envia con la identidad del jefe de su sector.

    Un jefe de terreno solo puede escribir en su sector (RN1), asi que un unico login para los
    tres sectores seria rechazado. `credencial_unica` fuerza una misma cuenta (modo --email).
    """

    def __init__(self, base: str, password: str, credencial_unica: str | None = None):
        self.base, self.password, self.unica = base, password, credencial_unica
        self.clientes: dict[int, ApiClient] = {}

    def para(self, sector_id: int) -> ApiClient:
        if sector_id not in self.clientes:
            email = self.unica or JEFE_DE_SECTOR.get(sector_id)
            if email is None:
                raise Rechazado(404, f"no hay jefe de terreno configurado para el sector {sector_id}")
            self.clientes[sector_id] = ApiClient(self.base, email, self.password)
        return self.clientes[sector_id]


def sincronizar(buffer: EdgeBuffer, api) -> None:
    """Envia lo pendiente, agrupado por sector (cada grupo con la cuenta de su sector).
    `api` puede ser un ApiClient o un ApiPorSector."""
    pend = buffer.pendientes()
    por_sector: dict[int, list[tuple[int, dict]]] = {}
    for i, l in pend:
        por_sector.setdefault(l.get("sector_id", 0), []).append((i, l))
    for sector_id, grupo in por_sector.items():
        try:
            cliente = api.para(sector_id) if hasattr(api, "para") else api
        except Rechazado as e:
            buffer.marcar([i for i, _ in grupo], "RECHAZADA")
            log(f"Sector {sector_id}: {e}")
            continue
        _sincronizar_grupo(buffer, cliente, grupo)


def _sincronizar_grupo(buffer: EdgeBuffer, api: ApiClient, pend: list[tuple[int, dict]]) -> None:
    """Un lote rechazado se reintenta lectura por lectura para que una lectura mala
    no bloquee la cola para siempre (poison pill)."""
    ids, lecturas = [i for i, _ in pend], [l for _, l in pend]
    try:
        r = api.enviar_lote(lecturas)
        buffer.marcar(ids, "SINCRONIZADA")
        extra = f", {r['alertas_generadas']} alerta(s) nueva(s)" if r["alertas_generadas"] else ""
        log(f"Sector {lecturas[0].get('sector_id')}: sincronizadas {r['nuevas']} lectura(s) ({r['duplicadas']} duplicadas){extra}")
    except Rechazado as e:
        if len(pend) == 1:
            buffer.marcar(ids, "RECHAZADA")
            log(f"Lectura rechazada por el API ({e.status}): {e}")
            return
        for i, l in pend:
            try:
                api.enviar_lote([l])
                buffer.marcar([i], "SINCRONIZADA")
            except Rechazado as e2:
                buffer.marcar([i], "RECHAZADA")
                log(f"Lectura {i} rechazada por el API ({e2.status}): {e2}")


# --------------------------------------------------------------------------- fuentes de datos
class FuenteSerial:
    """Lee lineas del Arduino por USB. Si se desconecta el cable, reintenta abrir el puerto."""

    def __init__(self, puerto: str, baudios: int):
        self.puerto, self.baudios, self.ser = puerto, baudios, None

    def _abrir(self):
        import serial  # import tardio: --simular no necesita pyserial funcionando
        self.ser = serial.Serial(self.puerto, self.baudios, timeout=3)
        time.sleep(2)  # el Arduino UNO se reinicia al abrir el puerto
        self.ser.reset_input_buffer()
        log(f"Conectado a {self.puerto} @ {self.baudios} baudios")

    def lineas(self):
        import serial
        while True:
            try:
                if self.ser is None:
                    self._abrir()
                crudo = self.ser.readline()
                if crudo:
                    yield crudo.decode("utf-8", errors="replace")
            except (serial.SerialException, OSError) as e:
                log(f"Puerto serial no disponible ({e}). Reintentando en 3 s...")
                try:
                    if self.ser:
                        self.ser.close()
                except Exception:
                    pass
                self.ser = None
                time.sleep(3)

    def comando(self, texto: str) -> None:
        """Envia 'h' (todos los sectores) o 'hB' (solo B) al Arduino, terminado en salto de linea."""
        if self.ser:
            self.ser.write((texto + "\n").encode())


class FuenteSimulada:
    """Mismos datos que el sketch (3 sectores con perfiles distintos), generados por software."""

    # Perfil normal por sector: temperatura, humedad, radiacion, presion
    PERFIL = {
        "A": {"t": 22.0, "h": 65.0, "r": 450.0, "p": 1.000},   # invernadero: calido y humedo
        "B": {"t": 24.0, "h": 80.0, "r": 250.0, "p": 2.500},   # hidroponico: muy humedo, presion de bomba
        "C": {"t": 14.0, "h": 42.0, "r": 750.0, "p": 1.800},   # frutal: fresco, seco, mucha radiacion
    }
    ESCENARIO = {"h": ("t", 0.5), "s": ("h", 15.0), "r": ("r", 1000.0)}
    PASOS = {"t": (0.35, 0.25), "h": (0.25, 0.8), "r": (0.20, 15), "p": (0.05, 0.002)}

    def __init__(self, intervalo: float):
        self.intervalo = intervalo
        self.obj = {k: dict(v) for k, v in self.PERFIL.items()}
        self.v = {k: {m: x + random.uniform(-0.02, 0.02) * x for m, x in v.items()} for k, v in self.PERFIL.items()}

    def comando(self, texto: str) -> None:
        """'h' aplica a todos los sectores; 'hB' solo al B (igual que el sketch)."""
        texto = texto.strip()
        esc, sec = texto[:1].lower(), texto[1:2].upper()
        if esc not in ("n", "h", "s", "r") or (sec and sec not in self.PERFIL):
            return
        for letra in ([sec] if sec else self.PERFIL):
            if esc == "n":
                self.obj[letra] = dict(self.PERFIL[letra])
            else:
                magnitud, valor = self.ESCENARIO[esc]
                self.obj[letra][magnitud] = valor
        log(f"# escenario={esc} sector={sec or 'TODOS'}")

    def lineas(self):
        while True:
            for letra in self.PERFIL:
                v, o = self.v[letra], self.obj[letra]
                for k, (frac, amp) in self.PASOS.items():
                    lo, hi = RANGOS[k]
                    v[k] = max(lo, min(hi, v[k] + (o[k] - v[k]) * frac + random.uniform(-amp, amp)))
                yield json.dumps({"id": f"SIM-{letra}01", "s": letra, "t": round(v["t"], 1), "h": round(v["h"], 1),
                                  "r": round(v["r"]), "p": round(v["p"], 3)})
            time.sleep(self.intervalo)


class FallasSensor:
    """Simula fallas de hardware por sector, sobre cualquier fuente (Arduino real o simulada).

    x = desconectado: las lecturas del sector se descartan (el API deja de recibir datos).
    d = dañado: el sensor "se congela" y repite siempre el mismo valor.
    n = repara ambas fallas.
    """

    def __init__(self, sectores: dict[str, int] | None = None):
        self.letra_de = {sid: letra for letra, sid in (sectores or SECTORES).items()}
        self.letras = set(self.letra_de.values())
        self.desconectados: set[str] = set()
        self.danados: set[str] = set()
        self.congelado: dict[str, dict] = {}

    def comando(self, texto: str) -> bool:
        """Aplica 'x', 'd' o 'n' (con letra de sector opcional). Devuelve False si no es un comando de falla."""
        texto = texto.strip()
        accion, sec = texto[:1].lower(), texto[1:2].upper()
        if accion not in ("x", "d", "n") or (sec and sec not in self.letras):
            return False
        for letra in ([sec] if sec else sorted(self.letras)):
            if accion == "x":
                self.desconectados.add(letra)
            elif accion == "d":
                self.danados.add(letra)
            else:
                self.desconectados.discard(letra)
                self.danados.discard(letra)
                self.congelado.pop(letra, None)
        estado = {"x": "sensor DESCONECTADO", "d": "sensor DAÑADO (valores congelados)", "n": "sensor reparado y conectado"}[accion]
        log(f"# sector={sec or 'TODOS'}: {estado}")
        return True

    def aplicar(self, lectura: dict) -> dict | None:
        """Devuelve la lectura (posiblemente congelada) o None si el sensor está desconectado."""
        letra = self.letra_de.get(lectura["sector_id"])
        if letra in self.desconectados:
            return None
        if letra in self.danados:
            valores = self.congelado.setdefault(
                letra, {k: lectura[k] for k in ("temperatura_c", "humedad_suelo_pct", "radiacion_wm2", "presion_bar")}
            )
            return {**lectura, **valores}
        return lectura


# --------------------------------------------------------------------------- main
def listar_puertos() -> None:
    from serial.tools import list_ports
    puertos = list(list_ports.comports())
    if not puertos:
        print("No se detectaron puertos seriales. Revise el cable USB y los drivers.")
    for p in puertos:
        print(f"{p.device}\t{p.description}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Gateway Edge: Arduino (USB serial) -> API AgroIoT")
    ap.add_argument("--puerto", help="Puerto serial del Arduino (COM3, /dev/ttyACM0, ...)")
    ap.add_argument("--baudios", type=int, default=9600)
    ap.add_argument("--simular", action="store_true", help="Generar datos por software (sin Arduino)")
    ap.add_argument("--intervalo", type=float, default=2.0, help="Segundos entre lecturas en --simular")
    ap.add_argument("--listar-puertos", action="store_true")
    ap.add_argument("--api", default=os.getenv("AGRO_API", "http://localhost:8000"))
    ap.add_argument("--email", default=os.getenv("AGRO_EMAIL"),
                    help="Cuenta unica para todos los sectores. Sin esto, cada sector usa a su jefe (jefe.a/b/c@agro.cl)")
    ap.add_argument("--password", default=os.getenv("AGRO_PASSWORD", "Terreno2026!"))
    ap.add_argument("--sector", type=int, default=1, help="Sector para las lineas que no traen el campo \"s\"")
    ap.add_argument("--db", default="edge_cache.sqlite", help="Archivo SQLite de cache local")
    a = ap.parse_args()

    if a.listar_puertos:
        listar_puertos()
        return 0
    if not a.simular and not a.puerto:
        ap.error("indique --puerto (use --listar-puertos para verlos) o --simular")

    fuente = FuenteSimulada(a.intervalo) if a.simular else FuenteSerial(a.puerto, a.baudios)
    buffer, api = EdgeBuffer(a.db), ApiPorSector(a.api, a.password, a.email)
    cuentas = a.email or ", ".join(JEFE_DE_SECTOR[i] for i in sorted(JEFE_DE_SECTOR))
    log(f"Gateway iniciado. API={a.api} cache={a.db} ({buffer.contar_pendientes()} pendientes)")
    log(f"Sectores {', '.join(SECTORES)} -> cuentas: {cuentas}")
    log("Escriba n / h / s / r + Enter (todos los sectores) o con letra de sector, ej. hB. Ctrl+C para salir.")
    log("Fallas de sensor: x = desconectar, d = dañar (valores congelados), n = reparar. Ej.: xB, dC.")

    fallas = FallasSensor()

    def leer_teclado():
        for linea in sys.stdin:
            c = linea.strip()[:2]
            if c[:1].lower() in ("n", "h", "s", "r"):
                fuente.comando(c)
            if c[:1].lower() in ("n", "x", "d"):
                fallas.comando(c)
    threading.Thread(target=leer_teclado, daemon=True).start()

    descartadas = 0
    try:
        for linea in fuente.lineas():
            try:
                lectura = parsear_linea(linea, a.sector)
            except ValueError as e:
                descartadas += 1
                log(f"Linea descartada ({descartadas}): {e}")
                continue
            if lectura is None:
                if linea.strip().startswith("#"):
                    log(f"Arduino: {linea.strip()}")
                continue

            lectura = fallas.aplicar(lectura)  # simulación de sensor desconectado / dañado
            if lectura is None:
                continue

            log(f"[{lectura['sector_id']}] {lectura['sensor_id']}: T={lectura['temperatura_c']} C  H={lectura['humedad_suelo_pct']} %  "
                f"R={lectura['radiacion_wm2']:.0f} W/m2  P={lectura['presion_bar']} bar")
            buffer.guardar(lectura)  # primero se persiste localmente, luego se envia
            try:
                sincronizar(buffer, api)
            except SinConexion as e:
                log(f"Sin conexion ({e}): {buffer.contar_pendientes()} lectura(s) en cola local")
            except Rechazado as e:
                log(f"No se pudo autenticar/enviar ({e.status}): {e}")
    except KeyboardInterrupt:
        log(f"Detenido. Pendientes sin sincronizar: {buffer.contar_pendientes()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
