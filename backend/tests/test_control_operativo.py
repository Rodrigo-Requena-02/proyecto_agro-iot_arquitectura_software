"""Control operativo: actuadores por sector, LWW (ADR-004) y respuesta automática a alertas."""
from datetime import datetime, timedelta, timezone

from app.models import Actuador, Rol, Sector, TipoActuador, Usuario
from app.repositories import interfaces
from app.services.control_service import ControlOperativoService


def ts(segundos_atras: float = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=segundos_atras)).isoformat()


def put(client, headers, sector, tipo, activo, accion_en=None):
    body = {"activo": activo}
    if accion_en:
        body["accion_en"] = accion_en
    return client.put(f"/api/v1/sectores/{sector}/actuadores/{tipo}", json=body, headers=headers)


def estado(client, headers, sector=1):
    r = client.get(f"/api/v1/sectores/{sector}/actuadores", headers=headers)
    assert r.status_code == 200
    return {a["tipo"]: a for a in r.json()}


def lectura(**kw):
    base = dict(sector_id=1, sensor_id="UNO-A01", temperatura_c=18, humedad_suelo_pct=60,
                radiacion_wm2=600, presion_bar=1.0)
    base.update(kw)
    return base


# ---------------- estado y permisos ----------------
def test_estado_inicial_tres_actuadores_inactivos(client, jefe_a):
    e = estado(client, jefe_a)
    assert set(e) == {"RIEGO", "VENTILACION", "NUTRIENTES"}
    assert not any(a["activo"] for a in e.values())


def test_jefe_activa_riego_y_queda_registrado_quien_y_como(client, jefe_a):
    r = put(client, jefe_a, 1, "RIEGO", True)
    assert r.status_code == 200 and r.json()["aplicado"] is True
    riego = estado(client, jefe_a)["RIEGO"]
    assert (riego["activo"], riego["origen"], riego["actualizado_por"]) == (True, "MANUAL", "Juan Jefe (Sector A)")


def test_jefe_no_controla_otro_sector_ni_sin_token(client, jefe_a):
    assert put(client, jefe_a, 2, "RIEGO", True).status_code == 403
    assert client.get("/api/v1/sectores/2/actuadores", headers=jefe_a).status_code == 403
    assert client.get("/api/v1/sectores/1/actuadores").status_code == 401


def test_agronomo_ve_los_actuadores_pero_no_puede_accionarlos(client, jefe_a, agronomo):
    put(client, jefe_a, 1, "RIEGO", True)
    # Lectura: ve cualquier sector y el estado que dejó el jefe
    assert estado(client, agronomo, 1)["RIEGO"]["activo"] is True
    assert client.get("/api/v1/sectores/2/actuadores", headers=agronomo).status_code == 200
    # Escritura: rechazada en todos los sectores y para cualquier actuador
    for sector in (1, 2, 3):
        r = put(client, agronomo, sector, "RIEGO", False)
        assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    assert estado(client, agronomo, 1)["RIEGO"]["activo"] is True  # nada cambió


def test_validaciones_tipo_sector_y_futuro(client, jefe_a):
    assert put(client, jefe_a, 1, "TELETRANSPORTADOR", True).status_code == 422
    assert put(client, jefe_a, 999, "RIEGO", True).status_code == 404
    futuro = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    r = put(client, jefe_a, 1, "RIEGO", True, futuro)
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_READING"


def test_dashboard_incluye_actuadores_por_rol(client, jefe_a, agronomo):
    put(client, jefe_a, 1, "VENTILACION", True)
    sectores = client.get("/api/v1/dashboard", headers=jefe_a).json()["sectores"]
    assert len(sectores) == 1
    ventilacion = next(a for a in sectores[0]["actuadores"] if a["tipo"] == "VENTILACION")
    assert ventilacion["activo"] is True
    assert len(client.get("/api/v1/dashboard", headers=agronomo).json()["sectores"]) == 3


# ---------------- LWW ----------------
def test_lww_orden_manual_antigua_no_pisa_accion_automatica_mas_reciente(client, jefe_a):
    # El sistema activa el riego (helada) con una lectura de hace 5 s...
    client.post("/api/v1/telemetria", json=lectura(temperatura_c=1.0, tomada_en=ts(5)), headers=jefe_a)
    # ...y el jefe, que estaba sin conexión, sincroniza una orden de apagado de hace 1 minuto.
    r = put(client, jefe_a, 1, "RIEGO", False, ts(60)).json()
    assert r["aplicado"] is False and "LWW" in r["motivo"]
    assert r["actuador"]["activo"] is True and r["actuador"]["origen"] == "AUTOMATICO"


def test_lww_automatica_reafirma_estado_y_gana_a_orden_manual_tardia(client, jefe_a):
    # t0: sequía -> riego ON (automático)
    client.post("/api/v1/telemetria", json=lectura(humedad_suelo_pct=10, tomada_en=ts(200)), headers=jefe_a)
    # t2: llega una helada crítica (alerta NUEVA): el riego ya estaba ON, pero la orden se registra (reafirma)
    client.post("/api/v1/telemetria", json=lectura(temperatura_c=1.0, tomada_en=ts(50)), headers=jefe_a)
    assert estado(client, jefe_a)["RIEGO"]["detalle"] == "Riego anti-helada"
    # t1 (entre ambas): el jefe apagó el riego sin conexión y recién ahora sincroniza -> debe perder
    r = put(client, jefe_a, 1, "RIEGO", False, ts(100)).json()
    assert r["aplicado"] is False
    assert estado(client, jefe_a)["RIEGO"]["activo"] is True


def test_lww_gana_la_mas_reciente_aunque_llegue_primero_la_vieja(client, jefe_a):
    # Llega primero la acción de hace 30 s y después una más antigua aún (hace 90 s).
    assert put(client, jefe_a, 1, "RIEGO", True, ts(30)).json()["aplicado"] is True
    assert put(client, jefe_a, 1, "RIEGO", False, ts(90)).json()["aplicado"] is False
    # Y una realmente nueva sí se aplica
    assert put(client, jefe_a, 1, "RIEGO", False, ts(0)).json()["aplicado"] is True
    assert estado(client, jefe_a)["RIEGO"]["activo"] is False


def test_lww_es_por_actuador_no_global(client, jefe_a):
    put(client, jefe_a, 1, "RIEGO", True, ts(5))
    assert put(client, jefe_a, 1, "NUTRIENTES", True, ts(60)).json()["aplicado"] is True


# ---------------- respuesta automática a alertas ----------------
def test_helada_critica_activa_riego_automaticamente(client, jefe_a):
    client.post("/api/v1/telemetria", json=lectura(temperatura_c=1.0), headers=jefe_a)
    riego = estado(client, jefe_a)["RIEGO"]
    assert (riego["activo"], riego["origen"], riego["detalle"]) == (True, "AUTOMATICO", "Riego anti-helada")
    assert not estado(client, jefe_a)["VENTILACION"]["activo"]


def test_radiacion_alta_activa_ventilacion(client, jefe_a):
    client.post("/api/v1/telemetria", json=lectura(radiacion_wm2=1000), headers=jefe_a)
    assert estado(client, jefe_a)["VENTILACION"]["activo"] is True


def test_decision_humana_mas_reciente_no_es_pisada_por_lectura_antigua(client, jefe_a):
    # 1) Operador apaga el riego "ahora".
    put(client, jefe_a, 1, "RIEGO", True, ts(100))
    put(client, jefe_a, 1, "RIEGO", False, ts(10))
    # 2) Llega (por sincronización offline) una lectura de sequía tomada hace 2 minutos.
    client.post("/api/v1/telemetria", json=lectura(humedad_suelo_pct=10, tomada_en=ts(120)), headers=jefe_a)
    assert estado(client, jefe_a)["RIEGO"]["activo"] is False  # la acción humana más reciente gana


def test_orden_automatica_mas_reciente_reafirma_y_la_mas_antigua_no_pisa_lo_manual(client, jefe_a):
    put(client, jefe_a, 1, "RIEGO", True, ts(50))                       # manual ON hace 50 s
    # Una lectura de helada ANTERIOR a esa orden manual no puede pisarla
    client.post("/api/v1/telemetria", json=lectura(temperatura_c=1.0, tomada_en=ts(100)), headers=jefe_a)
    assert estado(client, jefe_a)["RIEGO"]["origen"] == "MANUAL"
    # Una lectura POSTERIOR sí reafirma: el último que decide es el sistema
    client.post("/api/v1/telemetria", json=lectura(humedad_suelo_pct=10, tomada_en=ts(0)), headers=jefe_a)
    assert estado(client, jefe_a)["RIEGO"]["origen"] == "AUTOMATICO"


# ---------------- Repository: el servicio sin base de datos ----------------
class MemAct(interfaces.ActuadorRepository):
    def __init__(self): self.items = []
    def obtener(self, s, t): return next((a for a in self.items if a.sector_id == s and a.tipo == t), None)
    def listar(self, s): return [a for a in self.items if a.sector_id == s]
    def guardar(self, a):
        if a not in self.items: self.items.append(a)
        return a


class MemSec(interfaces.SectorRepository):
    def obtener_por_id(self, i): return Sector(id=i, nombre="S", tipo="x")
    def listar(self): return []
    def guardar(self, s): return s


def test_servicio_de_control_con_repositorio_en_memoria():
    svc = ControlOperativoService(MemAct(), MemSec())
    jefe = Usuario(id=2, nombre="Jefe", rol=Rol.JEFE_TERRENO, sector_id=1)
    ahora = datetime.now(timezone.utc)
    assert svc.cambiar(1, TipoActuador.RIEGO, True, ahora, jefe).aplicado is True
    viejo = svc.cambiar(1, TipoActuador.RIEGO, False, ahora - timedelta(minutes=5), jefe)
    assert viejo.aplicado is False and viejo.actuador.activo is True


def test_regla_de_negocio_solo_el_jefe_acciona_sin_base_de_datos():
    from app.core.errors import AccesoDenegado
    import pytest
    svc = ControlOperativoService(MemAct(), MemSec())
    agro = Usuario(id=1, nombre="Ana", rol=Rol.AGRONOMO)
    with pytest.raises(AccesoDenegado):
        svc.cambiar(1, TipoActuador.RIEGO, True, None, agro)
