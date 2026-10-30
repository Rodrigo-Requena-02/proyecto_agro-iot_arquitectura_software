"""Inyección de dependencias: aquí (y solo aquí) se enlazan interfaces con implementaciones."""
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AccesoDenegado, TokenInvalido
from app.models import Rol, Usuario
from app.repositories.sqlalchemy_repos import (
    SqlActuadorRepository, SqlAlertaRepository, SqlSectorRepository, SqlTelemetriaRepository,
    SqlUsuarioRepository,
)
from app.services.auth_service import AuthService
from app.services.control_service import ControlOperativoService
from app.services.telemetria_service import TelemetriaService

bearer = HTTPBearer(auto_error=False)


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(SqlUsuarioRepository(db))


def get_control_service(db: Session = Depends(get_db)) -> ControlOperativoService:
    return ControlOperativoService(SqlActuadorRepository(db), SqlSectorRepository(db))


def get_telemetria_service(
    db: Session = Depends(get_db), control: ControlOperativoService = Depends(get_control_service)
) -> TelemetriaService:
    return TelemetriaService(
        SqlTelemetriaRepository(db), SqlAlertaRepository(db), SqlSectorRepository(db), control=control
    )


def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    auth: AuthService = Depends(get_auth_service),
) -> Usuario:
    if cred is None:
        raise TokenInvalido("Falta el token de autenticación")
    return auth.usuario_desde_token(cred.credentials)


def require_roles(*roles: Rol):
    """Autorización por rol (RBAC) como dependencia reutilizable."""
    def checker(usuario: Usuario = Depends(get_current_user)) -> Usuario:
        if usuario.rol not in roles:
            raise AccesoDenegado("Su rol no permite realizar esta operación")
        return usuario
    return checker
