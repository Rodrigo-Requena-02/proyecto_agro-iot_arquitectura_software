"""Contratos de entrada/salida de la API (validación declarativa con Pydantic)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import Rol, TipoActuador


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    nombre: str
    rol: Rol
    sector_id: int | None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    usuario: UsuarioOut


class LecturaIn(BaseModel):
    sector_id: int = Field(gt=0)
    sensor_id: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_\-]+$")
    temperatura_c: float = Field(ge=-40, le=60)
    humedad_suelo_pct: float = Field(ge=0, le=100)
    radiacion_wm2: float = Field(ge=0, le=1500)
    presion_bar: float = Field(ge=0, le=10)
    # Instante real de la medición (clave para el modo offline). Si falta, se usa "ahora".
    tomada_en: datetime | None = None


class LoteIn(BaseModel):
    lecturas: list[LecturaIn] = Field(min_length=1, max_length=500)


class AlertaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sector_id: int
    regla: str
    severidad: str
    mensaje: str
    creada_en: datetime
    reconocida: bool


class LecturaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sector_id: int
    sensor_id: str
    temperatura_c: float
    humedad_suelo_pct: float
    radiacion_wm2: float
    presion_bar: float
    tomada_en: datetime


class RegistroOut(BaseModel):
    lectura: LecturaOut
    alertas: list[AlertaOut]  # alertas NUEVAS generadas por esta lectura
    # Condiciones de alerta que se cumplen pero que ya tienen una alerta activa (RN6): no se duplican.
    alertas_repetidas: list[AlertaOut] = []
    duplicada: bool = False


class UmbralOut(BaseModel):
    """Regla de alerta del sistema (datos generados, de solo lectura)."""
    regla: str
    variable: str
    condicion_critica: str | None = None
    condicion_media: str | None = None
    respuesta: str


class LoteOut(BaseModel):
    recibidas: int
    nuevas: int
    duplicadas: int
    alertas_generadas: int


class ActuadorOut(BaseModel):
    sector_id: int
    tipo: TipoActuador
    activo: bool
    origen: str  # MANUAL | AUTOMATICO | SISTEMA
    detalle: str | None = None
    actualizado_en: datetime | None = None
    actualizado_por: str | None = None


class CambioActuadorIn(BaseModel):
    activo: bool
    # Instante real de la acción en el dispositivo (clave para LWW cuando se hizo offline).
    accion_en: datetime | None = None


class CambioActuadorOut(BaseModel):
    aplicado: bool
    motivo: str | None = None
    actuador: ActuadorOut


class SensorEstadoOut(BaseModel):
    """Estado de un sensor, derivado de su telemetría (ver services/estado_sensores.py)."""
    sensor_id: str
    conexion: str  # CONECTADO | DESCONECTADO
    salud: str  # BUENO | DANADO
    motivo: str | None = None
    ultima_lectura_en: datetime
    segundos_sin_datos: int


class SectorResumenOut(BaseModel):
    sector_id: int
    nombre: str
    tipo: str
    ultima_lectura: LecturaOut | None
    alertas_activas: int
    actuadores: list[ActuadorOut] = []
    sensores: list[SensorEstadoOut] = []


class DashboardOut(BaseModel):
    rol: Rol
    sectores: list[SectorResumenOut]
    alertas_recientes: list[AlertaOut]
