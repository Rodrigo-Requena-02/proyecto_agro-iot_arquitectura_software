"""Pruebas unitarias que EVIDENCIAN los patrones: sin BD ni HTTP.

- Repository: el servicio funciona con repositorios en memoria (cumplen la misma interfaz).
- Strategy: cada regla se prueba aislada y el servicio acepta reglas inyectadas.
"""
from datetime import datetime

import pytest

from app.core.errors import AccesoDenegado
from app.models import Alerta, Rol, Sector, Telemetria, Usuario
from app.repositories import interfaces
from app.schemas import LecturaIn
from app.services.telemetria_service import TelemetriaService
from app.strategies.alertas import (
    EstrategiaAlerta, EstrategiaEstresHidrico, EstrategiaHelada, EstrategiaRadiacionAlta, ResultadoAlerta,
)


def t(**kw):
    base = dict(temperatura_c=20, humedad_suelo_pct=60, radiacion_wm2=500)
    base.update(kw)
    return Telemetria(**base)


# ---------- Strategy: reglas aisladas ----------
@pytest.mark.parametrize("temp,esperado", [(1.9, "CRITICA"), (3.5, "MEDIA"), (10, None)])
def test_estrategia_helada(temp, esperado):
    r = EstrategiaHelada().evaluar(t(temperatura_c=temp))
    assert (r.severidad if r else None) == esperado


def test_estrategia_estres_hidrico_y_radiacion():
    assert EstrategiaEstresHidrico().evaluar(t(humedad_suelo_pct=15)).severidad == "CRITICA"
    assert EstrategiaRadiacionAlta().evaluar(t(radiacion_wm2=950)).regla == "RADIACION_ALTA"
    assert EstrategiaRadiacionAlta().evaluar(t()) is None


# ---------- Repository: implementaciones en memoria ----------
class MemTel(interfaces.TelemetriaRepository):
    def __init__(self): self.items = []
    def obtener(self, s, ts): return next((i for i in self.items if i.sensor_id == s and i.tomada_en == ts), None)
    def guardar(self, l): l.id = len(self.items) + 1; self.items.append(l); return l
    def ultima_por_sector(self, sid): return None
    def historial(self, sid, n): return self.items
    def lecturas_por_sensor(self, sid, n): return {}


class MemAlert(interfaces.AlertaRepository):
    def __init__(self): self.items = []
    def guardar(self, a): a.id = len(self.items) + 1; self.items.append(a); return a
    def listar(self, sid, n): return self.items
    def obtener_por_id(self, i): return None
    def buscar_activa(self, sid, regla, sev):
        return next((a for a in self.items if a.sector_id == sid and a.regla == regla
                     and a.severidad == sev and not a.reconocida), None)


class MemSector(interfaces.SectorRepository):
    def obtener_por_id(self, i): return Sector(id=i, nombre="S", tipo="x")
    def listar(self): return []
    def guardar(self, s): return s


class AlwaysFire(EstrategiaAlerta):
    """Regla nueva inyectada sin tocar el servicio (Open/Closed)."""
    def evaluar(self, lectura): return ResultadoAlerta("PRUEBA", "MEDIA", "siempre")


def datos(**kw):
    base = dict(sector_id=1, sensor_id="ESP32-X1", temperatura_c=20, humedad_suelo_pct=60,
                radiacion_wm2=500, presion_bar=1.0, tomada_en=datetime(2026, 1, 1, 12, 0))
    base.update(kw)
    return LecturaIn(**base)


def test_servicio_con_repositorios_en_memoria_y_estrategia_inyectada():
    svc = TelemetriaService(MemTel(), MemAlert(), MemSector(), estrategias=[AlwaysFire()])
    agro = Usuario(id=1, rol=Rol.AGRONOMO)
    out = svc.registrar(datos(), agro)
    assert [a.regla for a in out.alertas] == ["PRUEBA"]
    assert svc.registrar(datos(), agro).duplicada is True  # idempotencia (RN4)


def test_regla_negocio_sector_asignado_sin_base_de_datos():
    svc = TelemetriaService(MemTel(), MemAlert(), MemSector(), estrategias=[])
    jefe = Usuario(id=2, rol=Rol.JEFE_TERRENO, sector_id=1)
    with pytest.raises(AccesoDenegado):
        svc.registrar(datos(sector_id=2), jefe)
