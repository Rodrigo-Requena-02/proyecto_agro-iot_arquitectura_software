from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Actuador, Alerta, Sector, Telemetria, TipoActuador, Usuario
from app.repositories import interfaces


class _Base:
    def __init__(self, db: Session):
        self.db = db

    def _persist(self, obj):
        try:
            self.db.add(obj)
            self.db.commit()
            self.db.refresh(obj)
            return obj
        except Exception:
            self.db.rollback()
            raise


class SqlUsuarioRepository(_Base, interfaces.UsuarioRepository):
    def obtener_por_email(self, email: str) -> Usuario | None:
        return self.db.scalar(select(Usuario).where(Usuario.email == email.lower()))

    def obtener_por_id(self, user_id: int) -> Usuario | None:
        return self.db.get(Usuario, user_id)

    def guardar(self, usuario: Usuario) -> Usuario:
        return self._persist(usuario)


class SqlSectorRepository(_Base, interfaces.SectorRepository):
    def obtener_por_id(self, sector_id: int) -> Sector | None:
        return self.db.get(Sector, sector_id)

    def listar(self) -> list[Sector]:
        return list(self.db.scalars(select(Sector).order_by(Sector.id)))

    def guardar(self, sector: Sector) -> Sector:
        return self._persist(sector)


class SqlTelemetriaRepository(_Base, interfaces.TelemetriaRepository):
    def obtener(self, sensor_id: str, tomada_en: datetime) -> Telemetria | None:
        stmt = select(Telemetria).where(
            Telemetria.sensor_id == sensor_id, Telemetria.tomada_en == tomada_en
        )
        return self.db.scalar(stmt)

    def guardar(self, lectura: Telemetria) -> Telemetria:
        return self._persist(lectura)

    def ultima_por_sector(self, sector_id: int) -> Telemetria | None:
        stmt = (
            select(Telemetria)
            .where(Telemetria.sector_id == sector_id)
            .order_by(Telemetria.tomada_en.desc())
            .limit(1)
        )
        return self.db.scalar(stmt)

    def historial(self, sector_id: int, limite: int) -> list[Telemetria]:
        stmt = (
            select(Telemetria)
            .where(Telemetria.sector_id == sector_id)
            .order_by(Telemetria.tomada_en.desc())
            .limit(limite)
        )
        return list(self.db.scalars(stmt))

    def lecturas_por_sensor(self, sector_id: int, por_sensor: int) -> dict[str, list[Telemetria]]:
        sensores = self.db.scalars(
            select(Telemetria.sensor_id).where(Telemetria.sector_id == sector_id).distinct()
        ).all()
        resultado: dict[str, list[Telemetria]] = {}
        for sensor_id in sensores:
            stmt = (
                select(Telemetria)
                .where(Telemetria.sector_id == sector_id, Telemetria.sensor_id == sensor_id)
                .order_by(Telemetria.tomada_en.desc())
                .limit(por_sensor)
            )
            resultado[sensor_id] = list(self.db.scalars(stmt))
        return resultado


class SqlAlertaRepository(_Base, interfaces.AlertaRepository):
    def guardar(self, alerta: Alerta) -> Alerta:
        return self._persist(alerta)

    def listar(self, sector_id: int | None, limite: int) -> list[Alerta]:
        stmt = select(Alerta).order_by(Alerta.creada_en.desc()).limit(limite)
        if sector_id is not None:
            stmt = stmt.where(Alerta.sector_id == sector_id)
        return list(self.db.scalars(stmt))

    def obtener_por_id(self, alerta_id: int) -> Alerta | None:
        return self.db.get(Alerta, alerta_id)

    def buscar_activa(self, sector_id: int, regla: str, severidad: str) -> Alerta | None:
        stmt = select(Alerta).where(
            Alerta.sector_id == sector_id,
            Alerta.regla == regla,
            Alerta.severidad == severidad,
            Alerta.reconocida.is_(False),
        ).limit(1)
        return self.db.scalar(stmt)


class SqlActuadorRepository(_Base, interfaces.ActuadorRepository):
    def obtener(self, sector_id: int, tipo: TipoActuador) -> Actuador | None:
        return self.db.scalar(
            select(Actuador).where(Actuador.sector_id == sector_id, Actuador.tipo == tipo)
        )

    def listar(self, sector_id: int) -> list[Actuador]:
        return list(self.db.scalars(select(Actuador).where(Actuador.sector_id == sector_id).order_by(Actuador.id)))

    def guardar(self, actuador: Actuador) -> Actuador:
        return self._persist(actuador)
