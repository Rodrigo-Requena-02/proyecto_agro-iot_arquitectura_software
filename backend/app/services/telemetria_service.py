
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from app.core.errors import AccesoDenegado, LecturaInvalida, NoEncontrado
from app.models import Alerta, Rol, Telemetria, TipoActuador, Usuario
from app.repositories.interfaces import AlertaRepository, SectorRepository, TelemetriaRepository
from app.schemas import (
    AlertaOut, DashboardOut, LecturaIn, LecturaOut, LoteOut, RegistroOut, SectorResumenOut, SensorEstadoOut,
    UmbralOut,
)
from app.services.estado_sensores import LECTURAS_PARA_ATASCO, evaluar_sensores
from app.strategies.alertas import EstrategiaAlerta, estrategias_por_defecto

from app.core.tiempo import TOLERANCIA_RELOJ
from app.core.tiempo import a_utc_naive as _a_utc_naive
from app.core.tiempo import utcnow as _utcnow
from app.services.autorizacion import autorizar_sector

if TYPE_CHECKING:  # evita importación circular en tiempo de ejecución
    from app.services.control_service import ControlOperativoService


class TelemetriaService:
    def __init__(
        self,
        telemetria: TelemetriaRepository,
        alertas: AlertaRepository,
        sectores: SectorRepository,
        estrategias: list[EstrategiaAlerta] | None = None,
        control: "ControlOperativoService | None" = None,
    ):
        self.telemetria = telemetria
        self.alertas = alertas
        self.sectores = sectores
        # Strategy inyectada: el servicio no conoce ninguna regla concreta.
        self.estrategias = estrategias if estrategias is not None else estrategias_por_defecto()
        # Control operativo (opcional): permite que una alerta accione actuadores automáticamente.
        self.control = control

    # ---------------- helpers ----------------
    def _autorizar_sector(self, usuario: Usuario, sector_id: int) -> None:
        autorizar_sector(self.sectores, usuario, sector_id)

    def _evaluar(self, lectura: Telemetria) -> tuple[list[Alerta], list[Alerta]]:
        """Devuelve (alertas nuevas, alertas ya activas que esta lectura volvió a cumplir)."""
        generadas, repetidas = [], []
        for estrategia in self.estrategias:
            resultado = estrategia.evaluar(lectura)
            if resultado is None:
                continue
            # RN6: con telemetría continua, una condición sostenida (ej. helada de 2 h) no debe
            # generar una alerta por lectura. Se crea una nueva solo si no hay otra activa
            # (no reconocida) de la misma regla y severidad; si la severidad escala, sí se crea.
            activa = self.alertas.buscar_activa(lectura.sector_id, resultado.regla, resultado.severidad)
            if activa is not None:
                repetidas.append(activa)
                continue
            generadas.append(
                self.alertas.guardar(
                    Alerta(
                        sector_id=lectura.sector_id,
                        regla=resultado.regla,
                        severidad=resultado.severidad,
                        mensaje=resultado.mensaje,
                        creada_en=_utcnow(),
                        reconocida=False,  # explícito: no depender del default de la BD
                    )
                )
            )
            # RC4: la regla declara la respuesta; el control operativo la ejecuta con LWW,
            # usando el instante de la LECTURA (no el de recepción) como marca de la acción.
            if resultado.accion and self.control:
                tipo, encender, detalle = resultado.accion
                self.control.aplicar_automatico(
                    lectura.sector_id, TipoActuador(tipo), encender, lectura.tomada_en, detalle
                )
        return generadas, repetidas

    def _registrar_una(
        self, datos: LecturaIn, usuario: Usuario
    ) -> tuple[Telemetria, list[Alerta], list[Alerta], bool]:
        self._autorizar_sector(usuario, datos.sector_id)
        instante = _a_utc_naive(datos.tomada_en)
        if instante > _utcnow() + TOLERANCIA_RELOJ:
            raise LecturaInvalida("La marca de tiempo de la lectura está en el futuro")

        previa = self.telemetria.obtener(datos.sensor_id, instante)
        if previa is not None:
            return previa, [], [], True

        lectura = self.telemetria.guardar(
            Telemetria(
                sector_id=datos.sector_id,
                sensor_id=datos.sensor_id,
                temperatura_c=datos.temperatura_c,
                humedad_suelo_pct=datos.humedad_suelo_pct,
                radiacion_wm2=datos.radiacion_wm2,
                presion_bar=datos.presion_bar,
                tomada_en=instante,
                registrada_por=usuario.id,
            )
        )
        generadas, repetidas = self._evaluar(lectura)
        return lectura, generadas, repetidas, False

    # ---------------- casos de uso ----------------
    def registrar(self, datos: LecturaIn, usuario: Usuario) -> RegistroOut:
        lectura, alertas, repetidas, dup = self._registrar_una(datos, usuario)
        return RegistroOut(
            lectura=LecturaOut.model_validate(lectura),
            alertas=[AlertaOut.model_validate(a) for a in alertas],
            alertas_repetidas=[AlertaOut.model_validate(a) for a in repetidas],
            duplicada=dup,
        )

    def registrar_lote(self, lecturas: list[LecturaIn], usuario: Usuario) -> LoteOut:
        """Sincronización offline -> online: procesa en orden cronológico."""
        nuevas = dups = n_alertas = 0
        for datos in sorted(lecturas, key=lambda x: _a_utc_naive(x.tomada_en)):
            _, alertas, _, dup = self._registrar_una(datos, usuario)
            if dup:
                dups += 1
            else:
                nuevas += 1
                n_alertas += len(alertas)
        return LoteOut(recibidas=len(lecturas), nuevas=nuevas, duplicadas=dups, alertas_generadas=n_alertas)

    def umbrales(self) -> list[UmbralOut]:
        """Reglas de alerta vigentes. Son datos generados por el sistema: de solo lectura."""
        return [UmbralOut(**e.describir()) for e in self.estrategias]

    def historial(self, sector_id: int, limite: int, usuario: Usuario) -> list[LecturaOut]:
        self._autorizar_sector(usuario, sector_id)  # RN1 también para lectura
        return [LecturaOut.model_validate(l) for l in self.telemetria.historial(sector_id, limite)]

    def _estado_sensores(self, sector_id: int) -> list[SensorEstadoOut]:
        """RS1-RS3: conexión y salud de cada sensor del sector, derivadas de su telemetría."""
        por_sensor = self.telemetria.lecturas_por_sensor(sector_id, LECTURAS_PARA_ATASCO)
        return [SensorEstadoOut(**asdict(e)) for e in evaluar_sensores(por_sensor, _utcnow())]

    def dashboard(self, usuario: Usuario) -> DashboardOut:
        sectores = self.sectores.listar()
        if usuario.rol == Rol.JEFE_TERRENO:
            sectores = [s for s in sectores if s.id == usuario.sector_id]

        resumen, recientes = [], []
        for s in sectores:
            ultima = self.telemetria.ultima_por_sector(s.id)
            alertas = self.alertas.listar(s.id, 20)
            activas = [a for a in alertas if not a.reconocida]
            recientes.extend(alertas[:5])
            resumen.append(
                SectorResumenOut(
                    sector_id=s.id,
                    nombre=s.nombre,
                    tipo=s.tipo,
                    ultima_lectura=LecturaOut.model_validate(ultima) if ultima else None,
                    alertas_activas=len(activas),
                    actuadores=self.control.listar_interno(s.id) if self.control else [],
                    sensores=self._estado_sensores(s.id),
                )
            )
        recientes.sort(key=lambda a: a.creada_en, reverse=True)
        return DashboardOut(
            rol=usuario.rol,
            sectores=resumen,
            alertas_recientes=[AlertaOut.model_validate(a) for a in recientes[:10]],
        )

    def reconocer_alerta(self, alerta_id: int, usuario: Usuario) -> AlertaOut:
        alerta = self.alertas.obtener_por_id(alerta_id)
        if alerta is None:
            raise NoEncontrado("La alerta no existe")
        self._autorizar_sector(usuario, alerta.sector_id)
        alerta.reconocida = True
        return AlertaOut.model_validate(self.alertas.guardar(alerta))
