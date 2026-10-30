"""Configuración central. Se puede sobreescribir con variables de entorno o un archivo .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLite por defecto (cero configuración para la demo). PostgreSQL está integrado pero NO se usa
    # hasta que se defina DATABASE_URL, p. ej.: postgresql+psycopg2://agro:agro@localhost:5432/agro
    database_url: str = "sqlite:///./agro_iot.db"

    # En producción esta clave debe venir de un secreto, nunca del código.
    jwt_secret: str = "cambiar-en-produccion-clave-demo-de-al-menos-32-bytes"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Bloqueo anti fuerza bruta
    max_failed_logins: int = 5
    lockout_minutes: int = 5

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


settings = Settings()
