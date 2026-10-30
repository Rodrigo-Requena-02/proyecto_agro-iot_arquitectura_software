"""Utilidades de tiempo compartidas. Todo se guarda en UTC sin zona horaria (naive)."""
from datetime import datetime, timedelta, timezone

# Tolerancia por desfase de reloj de dispositivos de campo (Edge/PWA)
TOLERANCIA_RELOJ = timedelta(minutes=5)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def a_utc_naive(dt: datetime | None) -> datetime:
    """Normaliza a UTC naive. None -> ahora."""
    if dt is None:
        return utcnow()
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt
