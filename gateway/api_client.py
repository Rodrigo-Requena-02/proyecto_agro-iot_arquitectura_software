import requests

from edge_buffer import EdgeBuffer
from edge_common import log

# Códigos HTTP que indican que el DATO es inválido (reintentar no lo arregla).
ESTADOS_DEFINITIVOS = {400, 404, 413, 422}


class ErrorTemporal(Exception):
    """Falla del entorno: conservar las lecturas y reintentar luego."""


class SinConexion(ErrorTemporal):
    pass


class Rechazado(Exception):
    def __init__(self, status: int, mensaje: str):
        super().__init__(mensaje)
        self.status = status


def _mensaje(r) -> str:
    try:
        return r.json().get("error", {}).get("message", r.text) if r.content else r.text
    except ValueError:
        return r.text


class ApiClient:
    def __init__(self, base: str, email: str, password: str):
        self.base, self.email, self.password = base.rstrip("/"), email, password
        self.token: str | None = None

    def _req(self, metodo: str, ruta: str, **kw):
        try:
            return requests.request(metodo, self.base + ruta, timeout=5, **kw)
        except (requests.ConnectionError, requests.Timeout):
            raise SinConexion("API no disponible")

    def login(self) -> None:
        r = self._req("POST", "/api/v1/auth/login", json={"email": self.email, "password": self.password})
        if r.status_code != 200:
            # Credenciales malas o cuenta bloqueada: es un problema de configuración, no de la
            # lectura. Se conservan los datos hasta que se corrija.
            raise ErrorTemporal(f"login fallido ({r.status_code}): {_mensaje(r)}")
        self.token = r.json()["access_token"]
        log(f"Autenticado como {self.email}")

    def enviar_lote(self, lecturas: list[dict]) -> dict:
        for intento in (1, 2):
            if not self.token:
                self.login()
            r = self._req("POST", "/api/v1/telemetria/lote", json={"lecturas": lecturas},
                          headers={"Authorization": f"Bearer {self.token}"})
            if r.status_code == 401 and intento == 1:  # token vencido: renovar y reintentar
                self.token = None
                continue
            if r.status_code in ESTADOS_DEFINITIVOS:
                raise Rechazado(r.status_code, _mensaje(r))
            if r.status_code >= 400:  # 5xx, 401 persistente, 403, 423, 429...
                raise ErrorTemporal(f"API respondio {r.status_code}: {_mensaje(r)}")
            return r.json()
        raise ErrorTemporal("no autorizado")


def sincronizar(buffer: EdgeBuffer, api: ApiClient) -> None:
    """Envia lo pendiente. Un lote con un dato inválido se reintenta lectura por lectura para
    que esa lectura no bloquee la cola para siempre (poison pill). Los ErrorTemporal se propagan
    SIN marcar nada: las lecturas siguen PENDIENTES."""
    pend = buffer.pendientes()
    if not pend:
        return
    ids, lecturas = [i for i, _ in pend], [l for _, l in pend]
    try:
        r = api.enviar_lote(lecturas)
        buffer.marcar(ids, "SINCRONIZADA")
        extra = f", {r['alertas_generadas']} alerta(s) nueva(s)" if r["alertas_generadas"] else ""
        log(f"Sincronizadas {r['nuevas']} lectura(s) ({r['duplicadas']} duplicadas){extra}")
    except Rechazado as e:
        if len(pend) == 1:
            buffer.marcar(ids, "RECHAZADA")
            log(f"Lectura rechazada por el API ({e.status}): {e}")
            return
        for i, l in pend:
            try:
                api.enviar_lote([l])
                buffer.marcar([i], "SINCRONIZADA")
            except Rechazado as e2:
                buffer.marcar([i], "RECHAZADA")
                log(f"Lectura {i} rechazada por el API ({e2.status}): {e2}")
