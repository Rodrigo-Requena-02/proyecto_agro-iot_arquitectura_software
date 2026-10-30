from fastapi import APIRouter, Depends

from app.models import Usuario
from app.routers.deps import get_current_user, get_parametros_service
from app.schemas import CambioParametrosIn, CambioParametrosOut, ParametrosOut
from app.services.parametros_service import ParametrosService

router = APIRouter(prefix="/api/v1/sectores", tags=["parametros-riego"])


@router.get("/{sector_id}/parametros-riego", response_model=ParametrosOut)
def obtener_parametros(
    sector_id: int,
    usuario: Usuario = Depends(get_current_user),
    svc: ParametrosService = Depends(get_parametros_service),
):
    return svc.obtener(sector_id, usuario)


@router.put("/{sector_id}/parametros-riego", response_model=CambioParametrosOut)
def cambiar_parametros(
    sector_id: int,
    datos: CambioParametrosIn,
    usuario: Usuario = Depends(get_current_user),
    svc: ParametrosService = Depends(get_parametros_service),
):
    """Agrónomo (todos los sectores) o jefe de su sector. 200 con `aplicado=false` si LWW descartó el cambio."""
    return svc.cambiar(sector_id, datos, usuario)
