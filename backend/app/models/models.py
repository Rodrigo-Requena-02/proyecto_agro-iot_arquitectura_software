"""Modelo de datos relacional (PostgreSQL en producción, SQLite en la demo).

Las lecturas de sensores masivas irían a una BD Time-Series (ADR-002); para el módulo
demostrativo se persisten en la misma BD relacional detrás del mismo Repository,
de modo que cambiar el motor no afecta a los servicios.
"""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Rol(str, enum.Enum):
    AGRONOMO = "AGRONOMO"
    JEFE_TERRENO = "JEFE_TERRENO"


class Sector(Base):
    __tablename__ = "sectores"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)
    tipo: Mapped[str] = mapped_column(String(40))  # invernadero | hidroponico | frutal


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(128))
    rol: Mapped[Rol] = mapped_column(Enum(Rol))
    # Jefe de terreno: sector asignado. Agrónomo: None (ve todos los sectores).
    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectores.id"), nullable=True)
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    sector: Mapped[Sector | None] = relationship()


class Telemetria(Base):
    __tablename__ = "telemetria"
    __table_args__ = (
        # Idempotencia: reenviar un lote tras una reconexión no duplica lecturas.
        UniqueConstraint("sensor_id", "tomada_en", name="uq_sensor_instante"),
        Index("ix_tel_sector_fecha", "sector_id", "tomada_en"),
        # Estado de sensores: última(s) lectura(s) de cada sensor de un sector
        Index("ix_tel_sector_sensor_fecha", "sector_id", "sensor_id", "tomada_en"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sector_id: Mapped[int] = mapped_column(ForeignKey("sectores.id"))
    sensor_id: Mapped[str] = mapped_column(String(40))
    temperatura_c: Mapped[float] = mapped_column(Float)
    humedad_suelo_pct: Mapped[float] = mapped_column(Float)
    radiacion_wm2: Mapped[float] = mapped_column(Float)
    presion_bar: Mapped[float] = mapped_column(Float)
    tomada_en: Mapped[datetime] = mapped_column(DateTime)  # UTC, instante de la medición
    registrada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)


class TipoActuador(str, enum.Enum):
    RIEGO = "RIEGO"
    VENTILACION = "VENTILACION"
    NUTRIENTES = "NUTRIENTES"


class Actuador(Base):
    """Estado de un actuador por sector (válvula de riego, ventilación, dosificador).

    `actualizado_en` es el instante de la ACCIÓN (no el de recepción): base de la regla
    Last-Write-Wins (ADR-004) cuando un jefe de terreno offline y un agrónomo chocan.
    """
    __tablename__ = "actuadores"
    __table_args__ = (UniqueConstraint("sector_id", "tipo", name="uq_sector_tipo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sector_id: Mapped[int] = mapped_column(ForeignKey("sectores.id"))
    tipo: Mapped[TipoActuador] = mapped_column(Enum(TipoActuador))
    activo: Mapped[bool] = mapped_column(default=False)
    origen: Mapped[str] = mapped_column(String(12), default="SISTEMA")  # MANUAL | AUTOMATICO | SISTEMA
    detalle: Mapped[str | None] = mapped_column(String(120), nullable=True)
    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)

    usuario: Mapped[Usuario | None] = relationship()


class Alerta(Base):
    __tablename__ = "alertas"

    id: Mapped[int] = mapped_column(primary_key=True)
    sector_id: Mapped[int] = mapped_column(ForeignKey("sectores.id"))
    regla: Mapped[str] = mapped_column(String(40))  # HELADA | ESTRES_HIDRICO | RADIACION_ALTA
    severidad: Mapped[str] = mapped_column(String(20))  # MEDIA | CRITICA
    mensaje: Mapped[str] = mapped_column(String(240))
    creada_en: Mapped[datetime] = mapped_column(DateTime)
    reconocida: Mapped[bool] = mapped_column(default=False)
