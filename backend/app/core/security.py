"""Hash de contraseñas (bcrypt) y emisión/validación de JWT firmado (JWS, HS256)."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings
from app.core.errors import TokenInvalido


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, role: str, sector_id: int | None) -> tuple[str, int]:
    expires = timedelta(minutes=settings.jwt_expire_minutes)
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "sector_id": sector_id,
        "iat": now,
        "exp": now + expires,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(expires.total_seconds())


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise TokenInvalido("La sesión expiró, inicie sesión nuevamente")
    except jwt.PyJWTError:
        raise TokenInvalido("Token inválido")
