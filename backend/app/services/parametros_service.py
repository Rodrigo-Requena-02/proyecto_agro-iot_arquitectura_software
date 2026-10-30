from dataclasses import asdict

from app.core.errors import LecturaInvalida
from app.core.tiempo import TOLERANCIA_RELOJ, a_utc_naive, utcnow
from app.models import ParametrosRiego, Usuario
from app.repositories.interfaces import ParametrosRepository, SectorRepository
from app.schemas import CambioParametrosIn, CambioParametrosOut, ParametrosOut
from app.services.autorizacion import autorizar_sector
from app.strategies.alertas import Umbrales

_CAMPOS = ("helada_critica_c", "helada_media_c", "humedad_critica_pct", "humedad_media_pct",
           "radiacion_umbral_wm2")


class ParametrosService:
    def __init__(self, parametros: ParametrosRepository, sectores: SectorRepository):
        self.parametros = parametros
        self.sectores = sectores

    @staticmethod
    def _a_out(sector_id: int, p: ParametrosRiego | None) -> ParametrosOut:
        if p is None:  # sin configuración propia: valores por defecto (no se escribe nada al leer)
            return ParametrosOut(sector_id=sector_id, **asdict(Umbrales()))
        return ParametrosOut(
            sector_id=sector_id, **{c: getattr(p, c) for c in _CAMPOS},
            actualizado_en=p.actualizado_en, actualizado_por=p.usuario.nombre if p.usuario else None,
        )

    # ------------------------------------------------------------------ lecturas
    def obtener_interno(self, sector_id: int) -> ParametrosOut:
        """Sin autorización: lo usa el dashboard, que ya filtró los sectores por rol."""
        return self._a_out(sector_id, self.parametros.obtener(sector_id))

    def obtener(self, sector_id: int, usuario: Usuario) -> ParametrosOut:
        autorizar_sector(self.sectores, usuario, sector_id)
        return self.obtener_interno(sector_id)

    def umbrales(self, sector_id: int) -> Umbrales:
        """Umbrales vigentes del sector para las estrategias de alerta."""
        p = self.parametros.obtener(sector_id)
        return Umbrales() if p is None else Umbrales(**{c: getattr(p, c) for c in _CAMPOS})

    # ------------------------------------------------------------------ escritura
    def cambiar(self, sector_id: int, datos: CambioParametrosIn, usuario: Usuario) -> CambioParametrosOut:
        autorizar_sector(self.sectores, usuario, sector_id)
        instante = a_utc_naive(datos.accion_en)
        if instante > utcnow() + TOLERANCIA_RELOJ:
            raise LecturaInvalida("La marca de tiempo del cambio está en el futuro")

        actual = self.parametros.obtener(sector_id)
        if actual is not None and actual.actualizado_en is not None and instante < actual.actualizado_en:
            quien = actual.usuario.nombre if actual.usuario else "otro usuario"
            return CambioParametrosOut(
                aplicado=False,
                motivo=f"LWW: ya existe una configuración más reciente ({quien}); su cambio más antiguo se descartó",
                parametros=self._a_out(sector_id, actual),
            )

        p = actual or ParametrosRiego(sector_id=sector_id)
        for c in _CAMPOS:
            setattr(p, c, getattr(datos, c))
        p.actualizado_en = instante
        p.actualizado_por = usuario.id
        return CambioParametrosOut(aplicado=True, motivo=None,
                                   parametros=self._a_out(sector_id, self.parametros.guardar(p)))
