from fastapi import APIRouter, Depends, Query

from app.models import Rol, Usuario
from app.routers.deps import get_current_user, get_telemetria_service, require_roles
from app.schemas import (
    AlertaOut, DashboardOut, LecturaIn, LecturaOut, LoteIn, LoteOut, RegistroOut, UmbralOut,
)
from app.services.telemetria_service import TelemetriaService

router = APIRouter(prefix="/api/v1", tags=["telemetria"])


@router.post("/telemetria", response_model=RegistroOut, status_code=201)
def registrar_lectura(
    datos: LecturaIn,
    usuario: Usuario = Depends(require_roles(Rol.JEFE_TERRENO)),  # el agrónomo es de solo lectura
    svc: TelemetriaService = Depends(get_telemetria_service),
):
    return svc.registrar(datos, usuario)


@router.post("/telemetria/lote", response_model=LoteOut, status_code=201)
def sincronizar_lote(
    datos: LoteIn,
    usuario: Usuario = Depends(require_roles(Rol.JEFE_TERRENO)),
    svc: TelemetriaService = Depends(get_telemetria_service),
):
    """Endpoint de sincronización: la PWA/Edge sube la cola acumulada sin conexión."""
    return svc.registrar_lote(datos.lecturas, usuario)


@router.get("/telemetria", response_model=list[LecturaOut])
def historial(
    sector_id: int = Query(gt=0),
    limite: int = Query(default=20, ge=1, le=200),
    usuario: Usuario = Depends(get_current_user),
    svc: TelemetriaService = Depends(get_telemetria_service),
):
    """Últimas lecturas de un sector (más recientes primero)."""
    return svc.historial(sector_id, limite, usuario)


@router.get("/alertas/umbrales", response_model=list[UmbralOut])
def umbrales(
    _: Usuario = Depends(get_current_user),
    svc: TelemetriaService = Depends(get_telemetria_service),
):
    """Reglas de alerta vigentes. Solo lectura: son datos generados por el sistema, nadie los edita."""
    return svc.umbrales()


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(
    usuario: Usuario = Depends(get_current_user),
    svc: TelemetriaService = Depends(get_telemetria_service),
):
    return svc.dashboard(usuario)


@router.patch("/alertas/{alerta_id}/reconocer", response_model=AlertaOut)
def reconocer(
    alerta_id: int,
    usuario: Usuario = Depends(require_roles(Rol.JEFE_TERRENO)),
    svc: TelemetriaService = Depends(get_telemetria_service),
):
    return svc.reconocer_alerta(alerta_id, usuario)
