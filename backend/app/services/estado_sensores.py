"""Estado de los sensores: CONECTADO / DESCONECTADO y BUENO / DAÑADO.

Se DERIVA de la telemetría ya guardada (no necesita tablas ni columnas nuevas) y es lógica pura:
no conoce la BD ni HTTP, así que se prueba con objetos simples.

Reglas:
  RS1. Conexión: un sensor está CONECTADO si su última lectura llegó hace SEGUNDOS_DESCONEXION
       segundos o menos (el Arduino/gateway envía cada ~2 s). Si no, DESCONECTADO.
  RS2. Salud: un sensor está DAÑADO si
         a) "valores congelados": sus últimas LECTURAS_PARA_ATASCO lecturas son idénticas en las
            cuatro variables (un sensor sano siempre tiene algo de ruido), o
         b) su última lectura está en el límite del rango físico del sensor
            (temperatura -40/60 °C, humedad 0/100 %, presión 10 bar): típico de un sensor en
            cortocircuito o sin alimentación.
       En otro caso está BUENO.
  RS3. La salud se calcula con las últimas lecturas aunque el sensor esté desconectado
       (un sensor desconectado puede haber quedado dañado).
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence

SEGUNDOS_DESCONEXION = 15
LECTURAS_PARA_ATASCO = 5

CONECTADO, DESCONECTADO = "CONECTADO", "DESCONECTADO"
BUENO, DANADO = "BUENO", "DANADO"

# Límites físicos del sensor (los mismos de la validación de la API)
_LIMITES = {
    "temperatura_c": (-40.0, 60.0),
    "humedad_suelo_pct": (0.0, 100.0),
    "presion_bar": (None, 10.0),  # 0 bar es válido (bomba apagada); solo el tope indica falla
}
_VARIABLES = ("temperatura_c", "humedad_suelo_pct", "radiacion_wm2", "presion_bar")


class LecturaLike(Protocol):
    temperatura_c: float
    humedad_suelo_pct: float
    radiacion_wm2: float
    presion_bar: float
    tomada_en: datetime


@dataclass(frozen=True)
class EstadoSensor:
    sensor_id: str
    conexion: str  # CONECTADO | DESCONECTADO
    salud: str  # BUENO | DANADO
    motivo: str | None  # explicación legible cuando hay algo que informar
    ultima_lectura_en: datetime
    segundos_sin_datos: int


def _motivo_dano(lecturas: Sequence[LecturaLike]) -> str | None:
    ultima = lecturas[0]
    for variable, (lo, hi) in _LIMITES.items():
        valor = getattr(ultima, variable)
        if (lo is not None and valor <= lo) or (hi is not None and valor >= hi):
            return f"Lectura en el límite del rango físico ({variable} = {valor:g})"

    if len(lecturas) >= LECTURAS_PARA_ATASCO:
        ventana = lecturas[:LECTURAS_PARA_ATASCO]
        if all(tuple(getattr(l, v) for v in _VARIABLES) == tuple(getattr(ultima, v) for v in _VARIABLES) for l in ventana):
            return f"Valores congelados: las últimas {LECTURAS_PARA_ATASCO} lecturas son idénticas"
    return None


def evaluar_sensor(sensor_id: str, lecturas: Sequence[LecturaLike], ahora: datetime) -> EstadoSensor:
    """`lecturas`: las más recientes del sensor, la más nueva primero (al menos una)."""
    ultima = lecturas[0]
    segundos = max(0, int((ahora - ultima.tomada_en).total_seconds()))
    conectado = segundos <= SEGUNDOS_DESCONEXION
    motivo_dano = _motivo_dano(lecturas)

    if motivo_dano:
        motivo = motivo_dano
    elif not conectado:
        motivo = f"Sin datos hace más de {SEGUNDOS_DESCONEXION} s"
    else:
        motivo = None

    return EstadoSensor(
        sensor_id=sensor_id,
        conexion=CONECTADO if conectado else DESCONECTADO,
        salud=DANADO if motivo_dano else BUENO,
        motivo=motivo,
        ultima_lectura_en=ultima.tomada_en,
        segundos_sin_datos=segundos,
    )


def evaluar_sensores(por_sensor: dict[str, Sequence[LecturaLike]], ahora: datetime) -> list[EstadoSensor]:
    """Un estado por sensor, ordenado por id. Ignora sensores sin lecturas."""
    return [evaluar_sensor(sid, ls, ahora) for sid, ls in sorted(por_sensor.items()) if ls]
