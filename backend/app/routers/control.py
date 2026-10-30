from fastapi import APIRouter, Depends

from app.models import Rol, TipoActuador, Usuario
from app.routers.deps import get_control_service, get_current_user, require_roles
from app.schemas import ActuadorOut, CambioActuadorIn, CambioActuadorOut
from app.services.control_service import ControlOperativoService

router = APIRouter(prefix="/api/v1/sectores", tags=["control-operativo"])


@router.get("/{sector_id}/actuadores", response_model=list[ActuadorOut])
def listar_actuadores(
    sector_id: int,
    usuario: Usuario = Depends(get_current_user),
    svc: ControlOperativoService = Depends(get_control_service),
):
    return svc.listar(sector_id, usuario)


@router.put("/{sector_id}/actuadores/{tipo}", response_model=CambioActuadorOut)
def cambiar_actuador(
    sector_id: int,
    tipo: TipoActuador,
    datos: CambioActuadorIn,
    usuario: Usuario = Depends(require_roles(Rol.JEFE_TERRENO)),  # el agrónomo solo puede consultar
    svc: ControlOperativoService = Depends(get_control_service),
):
    """Activa/desactiva un actuador. Responde 200 con `aplicado=false` si LWW descartó la acción."""
    return svc.cambiar(sector_id, tipo, datos.activo, datos.accion_en, usuario)
