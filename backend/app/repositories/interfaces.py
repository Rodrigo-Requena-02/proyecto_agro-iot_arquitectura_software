from abc import ABC, abstractmethod
from datetime import datetime

from app.models import Actuador, Alerta, Sector, Telemetria, TipoActuador, Usuario


class UsuarioRepository(ABC):
    @abstractmethod
    def obtener_por_email(self, email: str) -> Usuario | None: ...

    @abstractmethod
    def obtener_por_id(self, user_id: int) -> Usuario | None: ...

    @abstractmethod
    def guardar(self, usuario: Usuario) -> Usuario: ...


class SectorRepository(ABC):
    @abstractmethod
    def obtener_por_id(self, sector_id: int) -> Sector | None: ...

    @abstractmethod
    def listar(self) -> list[Sector]: ...

    @abstractmethod
    def guardar(self, sector: Sector) -> Sector: ...


class TelemetriaRepository(ABC):
    @abstractmethod
    def obtener(self, sensor_id: str, tomada_en: datetime) -> Telemetria | None: ...

    @abstractmethod
    def guardar(self, lectura: Telemetria) -> Telemetria: ...

    @abstractmethod
    def ultima_por_sector(self, sector_id: int) -> Telemetria | None: ...

    @abstractmethod
    def historial(self, sector_id: int, limite: int) -> list[Telemetria]: ...

    @abstractmethod
    def lecturas_por_sensor(self, sector_id: int, por_sensor: int) -> dict[str, list[Telemetria]]:
        """Las `por_sensor` lecturas más recientes de CADA sensor del sector (más nueva primero)."""


class AlertaRepository(ABC):
    @abstractmethod
    def guardar(self, alerta: Alerta) -> Alerta: ...

    @abstractmethod
    def listar(self, sector_id: int | None, limite: int) -> list[Alerta]: ...

    @abstractmethod
    def obtener_por_id(self, alerta_id: int) -> Alerta | None: ...

    @abstractmethod
    def buscar_activa(self, sector_id: int, regla: str, severidad: str) -> Alerta | None:
        """Alerta NO reconocida del mismo sector, regla y severidad (para no duplicarla)."""


class ActuadorRepository(ABC):
    @abstractmethod
    def obtener(self, sector_id: int, tipo: TipoActuador) -> Actuador | None: ...

    @abstractmethod
    def listar(self, sector_id: int) -> list[Actuador]: ...

    @abstractmethod
    def guardar(self, actuador: Actuador) -> Actuador: ...
