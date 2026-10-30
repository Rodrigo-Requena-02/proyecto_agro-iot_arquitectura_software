"""Conexión a la base de datos (SQLAlchemy 2.x).

El motor se elige SOLO por configuración (`DATABASE_URL`); el resto del código no cambia:
  - SQLite      -> demo, pruebas y caché del Gateway Edge (por defecto, cero configuración)
  - PostgreSQL  -> destino de producción en la nube (ADR-005)
"""
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


def normalizar_url(url: str) -> str:
    """Acepta las formas habituales de URL de PostgreSQL y las deja con el driver instalado (psycopg2)."""
    for prefijo in ("postgres://", "postgresql://"):
        if url.startswith(prefijo):
            return "postgresql+psycopg2://" + url[len(prefijo):]
    return url


def motor_de(url: str) -> str:
    """'sqlite' | 'postgresql' | otro (nombre del dialecto)."""
    return make_url(normalizar_url(url)).get_backend_name()


def crear_engine(url: str) -> Engine:
    url = normalizar_url(url)
    if motor_de(url) == "sqlite":
        # SQLite: un solo archivo; FastAPI usa varios hilos, por eso se desactiva la comprobación.
        return create_engine(url, connect_args={"check_same_thread": False}, pool_pre_ping=True)
    # PostgreSQL (y otros servidores): pool de conexiones; pre_ping evita usar conexiones caídas.
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)


engine = crear_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependencia FastAPI: una sesión por request, siempre cerrada."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
