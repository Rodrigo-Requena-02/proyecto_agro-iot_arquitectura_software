"""Lógica de negocio de autenticación. No conoce HTTP ni SQL: usa el Repository."""
from datetime import datetime, timedelta, timezone

from app.core import security
from app.core.config import settings
from app.core.errors import CredencialesInvalidas, CuentaBloqueada, TokenInvalido
from app.models import Usuario
from app.repositories.interfaces import UsuarioRepository

# Hash de relleno: se verifica aunque el email no exista para igualar tiempos de respuesta
# (evita enumerar usuarios midiendo latencia).
_DUMMY_HASH = security.hash_password("dummy-password")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AuthService:
    def __init__(self, usuarios: UsuarioRepository):
        self.usuarios = usuarios

    def login(self, email: str, password: str) -> tuple[Usuario, str, int]:
        usuario = self.usuarios.obtener_por_email(email)

        if usuario is None:
            security.verify_password(password, _DUMMY_HASH)
            raise CredencialesInvalidas("Correo o contraseña incorrectos")

        ahora = _utcnow()
        if usuario.bloqueado_hasta and usuario.bloqueado_hasta > ahora:
            minutos = int((usuario.bloqueado_hasta - ahora).total_seconds() // 60) + 1
            raise CuentaBloqueada(f"Cuenta bloqueada temporalmente. Reintente en {minutos} min")

        if not security.verify_password(password, usuario.password_hash):
            usuario.intentos_fallidos += 1
            if usuario.intentos_fallidos >= settings.max_failed_logins:
                usuario.bloqueado_hasta = ahora + timedelta(minutes=settings.lockout_minutes)
                usuario.intentos_fallidos = 0
            self.usuarios.guardar(usuario)
            raise CredencialesInvalidas("Correo o contraseña incorrectos")

        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
        self.usuarios.guardar(usuario)

        token, expira_en = security.create_access_token(usuario.id, usuario.rol.value, usuario.sector_id)
        return usuario, token, expira_en

    def usuario_desde_token(self, token: str) -> Usuario:
        claims = security.decode_token(token)
        usuario = self.usuarios.obtener_por_id(int(claims["sub"]))
        if usuario is None:
            raise TokenInvalido("El usuario del token ya no existe")
        return usuario
