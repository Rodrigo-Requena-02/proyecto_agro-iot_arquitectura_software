"""Excepciones de dominio y su traducción a respuestas HTTP uniformes.

La capa de servicios lanza estas excepciones (no conoce HTTP); la capa de presentación
las convierte en JSON con un formato único: {"error": {"code", "message"}}.
"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, SQLAlchemyError


class DomainError(Exception):
    status_code = 400
    code = "DOMAIN_ERROR"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class CredencialesInvalidas(DomainError):
    status_code = 401
    code = "INVALID_CREDENTIALS"


class TokenInvalido(DomainError):
    status_code = 401
    code = "INVALID_TOKEN"


class CuentaBloqueada(DomainError):
    status_code = 423
    code = "ACCOUNT_LOCKED"


class AccesoDenegado(DomainError):
    status_code = 403
    code = "FORBIDDEN"


class NoEncontrado(DomainError):
    status_code = 404
    code = "NOT_FOUND"


class LecturaInvalida(DomainError):
    status_code = 422
    code = "INVALID_READING"


def _body(code: str, message: str, details=None) -> dict:
    err = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    return {"error": err}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError):
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(_body(exc.code, exc.message), status_code=exc.status_code, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [
            {"campo": ".".join(str(p) for p in e["loc"] if p != "body"), "motivo": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(_body("VALIDATION_ERROR", "Datos de entrada inválidos", details), status_code=422)

    @app.exception_handler(OperationalError)
    async def _db_down(_: Request, __: OperationalError):
        # Falla previsible: la BD no responde. No se filtran detalles internos.
        return JSONResponse(_body("DB_UNAVAILABLE", "Base de datos no disponible, reintente"), status_code=503)

    @app.exception_handler(SQLAlchemyError)
    async def _db(_: Request, __: SQLAlchemyError):
        return JSONResponse(_body("DB_ERROR", "Error al acceder a los datos"), status_code=500)
