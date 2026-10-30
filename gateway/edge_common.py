"""Utilidades compartidas del gateway: log y parseo/validación de líneas del Arduino."""
import json
import math
from datetime import datetime, timezone

# Rangos fisicos aceptados (los mismos que valida el API: defensa en profundidad)
RANGOS = {"t": (-40, 60), "h": (0, 100), "r": (0, 1500), "p": (0, 10)}


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def parsear_linea(linea: str, sector_id: int) -> dict | None:
    """Convierte una linea del Arduino en el JSON que espera el API.

    Devuelve None si es un comentario ('# ...') o vacia. Lanza ValueError si esta malformada
    o fuera de rango (por ejemplo ruido al abrir el puerto, o un sensor defectuoso).
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
