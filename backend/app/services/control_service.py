"""Control operativo por sector: riego, ventilación y dosificador de nutrientes.

Reglas de negocio:
  RC1. Solo el JEFE DE TERRENO acciona actuadores, y únicamente los de su sector (RN1).
       El agrónomo tiene acceso de solo lectura (puede ver el estado, no cambiarlo).
  RC2. LWW (Last Write Wins, ADR-004): una acción con marca de tiempo MÁS ANTIGUA que la
       última acción registrada se descarta y se informa; gana la más reciente, sin importar
       en qué orden llegue al servidor (ej. un cambio hecho offline que se sincroniza tarde).
  RC3. No se aceptan acciones del futuro (tolerancia 5 min por desfase de reloj).
  RC4. Una alerta puede activar un actuador automáticamente, pero con LWW: nunca pisa una
       decisión humana MÁS RECIENTE. Si el actuador ya estaba activo, la orden automática se
       registra igualmente (reafirma el estado con su marca de tiempo), de modo que una orden
       manual ANTIGUA que llegue después por sincronización offline no pueda apagarlo.
"""
from datetime import datetime

from app.core.errors import AccesoDenegado, LecturaInvalida
from app.core.tiempo import TOLERANCIA_RELOJ, a_utc_naive, utcnow
from app.models import Actuador, Rol, TipoActuador, Usuario
from app.repositories.interfaces import ActuadorRepository, SectorRepository
from app.schemas import ActuadorOut, CambioActuadorOut
from app.services.autorizacion import autorizar_sector


class ControlOperativoService:
    def __init__(self, actuadores: ActuadorRepository, sectores: SectorRepository):
        self.actuadores = actuadores
        self.sectores = sectores

    # ------------------------------------------------------------------ helpers
    def _asegurar(self, sector_id: int) -> dict[TipoActuador, Actuador]:
        """Devuelve los 3 actuadores del sector; crea (inactivos) los que falten."""
        existentes = {a.tipo: a for a in self.actuadores.listar(sector_id)}
        for tipo in TipoActuador:
            if tipo not in existentes:
                existentes[tipo] = self.actuadores.guardar(
                    Actuador(sector_id=sector_id, tipo=tipo, activo=False, origen="SISTEMA")
                )
        return existentes

    @staticmethod
    def _a_out(a: Actuador) -> ActuadorOut:
        return ActuadorOut(
            sector_id=a.sector_id, tipo=a.tipo, activo=a.activo, origen=a.origen, detalle=a.detalle,
            actualizado_en=a.actualizado_en, actualizado_por=a.usuario.nombre if a.usuario else None,
        )

    @staticmethod
    def _es_mas_antiguo(instante: datetime, a: Actuador) -> bool:
        return a.actualizado_en is not None and instante < a.actualizado_en

    # ------------------------------------------------------------------ casos de uso
    def listar_interno(self, sector_id: int) -> list[ActuadorOut]:
        """Sin autorización: lo usa el dashboard, que ya filtró los sectores por rol."""
        return [self._a_out(a) for a in self._asegurar(sector_id).values()]

    def listar(self, sector_id: int, usuario: Usuario) -> list[ActuadorOut]:
        autorizar_sector(self.sectores, usuario, sector_id)
        return self.listar_interno(sector_id)

    def cambiar(self, sector_id: int, tipo: TipoActuador, activo: bool,
                accion_en: datetime | None, usuario: Usuario) -> CambioActuadorOut:
        if usuario.rol != Rol.JEFE_TERRENO:  # RC1
            raise AccesoDenegado("Solo el jefe de terreno puede accionar actuadores (el agrónomo es de solo lectura)")
        autorizar_sector(self.sectores, usuario, sector_id)
        instante = a_utc_naive(accion_en)
        if instante > utcnow() + TOLERANCIA_RELOJ:
            raise LecturaInvalida("La marca de tiempo de la acción está en el futuro")

        actuador = self._asegurar(sector_id)[tipo]
        if self._es_mas_antiguo(instante, actuador):
            quien = actuador.usuario.nombre if actuador.usuario else actuador.origen.lower()
            return CambioActuadorOut(
                aplicado=False,
                motivo=f"LWW: ya existe un cambio más reciente ({quien}); su acción más antigua se descartó",
                actuador=self._a_out(actuador),
            )

        actuador.activo = activo
        actuador.origen = "MANUAL"
        actuador.detalle = None
        actuador.actualizado_en = instante
        actuador.actualizado_por = usuario.id
        return CambioActuadorOut(aplicado=True, motivo=None, actuador=self._a_out(self.actuadores.guardar(actuador)))

    def aplicar_automatico(self, sector_id: int, tipo: TipoActuador, activo: bool,
                           instante: datetime, detalle: str) -> bool:
        """Acción disparada por una regla de alerta (RC4). Devuelve True si se registró."""
        actuador = self._asegurar(sector_id)[tipo]
        if self._es_mas_antiguo(instante, actuador):
            return False  # ya hay una decisión posterior (humana o automática): gana esa
        actuador.activo = activo
        actuador.origen = "AUTOMATICO"
        actuador.detalle = detalle
        actuador.actualizado_en = instante
        actuador.actualizado_por = None
        self.actuadores.guardar(actuador)
        return True
