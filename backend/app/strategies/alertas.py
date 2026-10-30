"""PATRÓN 2 - STRATEGY (reglas de alerta sobre telemetría).

Problema que resuelve: en la Evaluación 1 identificamos el riesgo de que el módulo de
lógica de riego se convirtiera en Spaghetti Code (cadenas de IF/ELSE por cada regla
climática que pidan los agrónomos). Con Strategy cada regla es una clase independiente
que implementa la misma interfaz; agregar una regla = agregar una clase y registrarla
(Open/Closed), sin modificar el servicio.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models import Telemetria


@dataclass(frozen=True)
class ResultadoAlerta:
    regla: str
    severidad: str  # MEDIA | CRITICA
    mensaje: str
    # Respuesta automática sugerida por la regla: (tipo de actuador, encender?, motivo).
    # La regla solo la DECLARA; quien la ejecuta es el ControlOperativoService.
    accion: tuple[str, bool, str] | None = None


class EstrategiaAlerta(ABC):
    @abstractmethod
    def evaluar(self, lectura: Telemetria) -> ResultadoAlerta | None:
        """Devuelve una alerta si la regla se cumple, o None."""

    def describir(self) -> dict:
        """Descripción de solo lectura de la regla (para mostrarla en la UI)."""
        return {"regla": type(self).__name__, "variable": "-", "respuesta": "-"}


class EstrategiaHelada(EstrategiaAlerta):
    def __init__(self, umbral_critico_c: float = 2.0, umbral_medio_c: float = 4.0):
        self.critico, self.medio = umbral_critico_c, umbral_medio_c

    def describir(self) -> dict:
        return {"regla": "HELADA", "variable": "Temperatura",
                "condicion_critica": f"≤ {self.critico:g} °C", "condicion_media": f"≤ {self.medio:g} °C",
                "respuesta": "Riego anti-helada (solo severidad crítica)"}

    def evaluar(self, l: Telemetria) -> ResultadoAlerta | None:
        if l.temperatura_c <= self.critico:
            return ResultadoAlerta("HELADA", "CRITICA", f"Riesgo de helada: {l.temperatura_c:.1f} °C",
                                   accion=("RIEGO", True, "Riego anti-helada"))
        if l.temperatura_c <= self.medio:
            return ResultadoAlerta("HELADA", "MEDIA", f"Temperatura baja: {l.temperatura_c:.1f} °C")
        return None


class EstrategiaEstresHidrico(EstrategiaAlerta):
    def __init__(self, umbral_critico_pct: float = 20.0, umbral_medio_pct: float = 30.0):
        self.critico, self.medio = umbral_critico_pct, umbral_medio_pct

    def describir(self) -> dict:
        return {"regla": "ESTRES_HIDRICO", "variable": "Humedad de suelo",
                "condicion_critica": f"≤ {self.critico:g} %", "condicion_media": f"≤ {self.medio:g} %",
                "respuesta": "Riego"}

    def evaluar(self, l: Telemetria) -> ResultadoAlerta | None:
        if l.humedad_suelo_pct <= self.critico:
            return ResultadoAlerta("ESTRES_HIDRICO", "CRITICA", f"Humedad crítica: {l.humedad_suelo_pct:.0f} %",
                                   accion=("RIEGO", True, "Riego por estrés hídrico"))
        if l.humedad_suelo_pct <= self.medio:
            return ResultadoAlerta("ESTRES_HIDRICO", "MEDIA", f"Humedad baja: {l.humedad_suelo_pct:.0f} %",
                                   accion=("RIEGO", True, "Riego por humedad baja"))
        return None


class EstrategiaRadiacionAlta(EstrategiaAlerta):
    def __init__(self, umbral_wm2: float = 900.0):
        self.umbral = umbral_wm2

    def describir(self) -> dict:
        return {"regla": "RADIACION_ALTA", "variable": "Radiación solar",
                "condicion_critica": None, "condicion_media": f"≥ {self.umbral:g} W/m²",
                "respuesta": "Ventilación"}

    def evaluar(self, l: Telemetria) -> ResultadoAlerta | None:
        if l.radiacion_wm2 >= self.umbral:
            return ResultadoAlerta("RADIACION_ALTA", "MEDIA", f"Radiación alta: {l.radiacion_wm2:.0f} W/m²",
                                   accion=("VENTILACION", True, "Ventilación por radiación alta"))
        return None


def estrategias_por_defecto() -> list[EstrategiaAlerta]:
    return [EstrategiaHelada(), EstrategiaEstresHidrico(), EstrategiaRadiacionAlta()]
