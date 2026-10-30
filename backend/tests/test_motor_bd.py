"""Selección de motor de BD por configuración: SQLite por defecto, PostgreSQL integrado."""
from app.core.database import crear_engine, motor_de, normalizar_url


def test_sqlite_es_el_motor_por_defecto():
    from app.core.config import Settings
    assert motor_de(Settings().database_url) == "sqlite"


def test_urls_de_postgres_se_normalizan_al_driver_instalado():
    esperado = "postgresql+psycopg2://agro:agro@localhost:5432/agro"
    assert normalizar_url("postgresql://agro:agro@localhost:5432/agro") == esperado
    assert normalizar_url("postgres://agro:agro@localhost:5432/agro") == esperado
    assert normalizar_url(esperado) == esperado
    assert normalizar_url("sqlite:///./x.db") == "sqlite:///./x.db"


def test_se_crea_engine_de_postgres_sin_conectar():
    # create_engine es perezoso: valida que el driver esté instalado sin necesitar un servidor.
    eng = crear_engine("postgresql://agro:agro@localhost:5432/agro")
    assert eng.dialect.name == "postgresql" and eng.dialect.driver == "psycopg2"
    assert eng.pool.size() == 5


def test_se_crea_engine_de_sqlite_en_memoria():
    assert crear_engine("sqlite://").dialect.name == "sqlite"
