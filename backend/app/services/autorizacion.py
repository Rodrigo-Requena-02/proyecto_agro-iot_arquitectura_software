"""Regla de autorización por sector compartida por los servicios (RN1/RN2)."""
from app.core.errors import AccesoDenegado, NoEncontrado
from app.models import Rol, Usuario
from app.repositories.interfaces import SectorRepository


def autorizar_sector(sectores: SectorRepository, usuario: Usuario, sector_id: int) -> None:
    """RN2: el sector debe existir. RN1: el jefe de terreno solo opera su sector."""
    if sectores.obtener_por_id(sector_id) is None:
        raise NoEncontrado(f"El sector {sector_id} no existe")
    if usuario.rol == Rol.JEFE_TERRENO and usuario.sector_id != sector_id:
        raise AccesoDenegado("No tiene permiso para operar en este sector")
