"""Pruebas del flujo vertical: API -> servicio -> repositorio -> BD -> respuesta."""
from datetime import datetime, timedelta, timezone

from tests.conftest import login


def lectura(**kw):
    base = dict(sector_id=1, sensor_id="ESP32-A01", temperatura_c=18.5, humedad_suelo_pct=60,
                radiacion_wm2=650, presion_bar=1.2)
    base.update(kw)
    return base


# ---------------- Login y roles ----------------
def test_login_ok_devuelve_token_y_rol(client):
    r = login(client, "agronomo@agro.cl", "Agro2026!")
    assert r.status_code == 200
    body = r.json()
    assert body["usuario"]["rol"] == "AGRONOMO" and body["access_token"]


def test_login_credenciales_invalidas_mensaje_generico(client):
    mala = login(client, "agronomo@agro.cl", "incorrecta")
    inexistente = login(client, "nadie@agro.cl", "x")
    assert mala.status_code == inexistente.status_code == 401
    # Mismo mensaje: no revela si el correo existe
    assert mala.json()["error"]["message"] == inexistente.json()["error"]["message"]


def test_login_validacion_de_entrada(client):
    r = client.post("/api/v1/auth/login", json={"email": "no-es-correo", "password": ""})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_bloqueo_tras_5_intentos_fallidos(client):
    for _ in range(5):
        login(client, "jefe.a@agro.cl", "mala")
    r = login(client, "jefe.a@agro.cl", "Terreno2026!")  # incluso con la clave correcta
    assert r.status_code == 423 and r.json()["error"]["code"] == "ACCOUNT_LOCKED"


def test_endpoint_protegido_sin_token(client):
    assert client.get("/api/v1/dashboard").status_code == 401


def test_token_manipulado_es_rechazado(client, agronomo):
    h = {"Authorization": agronomo["Authorization"] + "x"}
    assert client.get("/api/v1/dashboard", headers=h).status_code == 401


# ---------------- Telemetría y persistencia ----------------
def test_registrar_lectura_persiste_y_aparece_en_dashboard(client, jefe_a, agronomo):
    r = client.post("/api/v1/telemetria", json=lectura(), headers=jefe_a)
    assert r.status_code == 201 and r.json()["alertas"] == []
    # El agrónomo (solo lectura) ve la lectura que ingresó el jefe de terreno
    dash = client.get("/api/v1/dashboard", headers=agronomo).json()
    sector_a = next(s for s in dash["sectores"] if s["sector_id"] == 1)
    assert sector_a["ultima_lectura"]["temperatura_c"] == 18.5


def test_lectura_de_helada_genera_alerta_critica(client, jefe_a):
    r = client.post("/api/v1/telemetria", json=lectura(temperatura_c=1.0), headers=jefe_a)
    alertas = r.json()["alertas"]
    assert [a["regla"] for a in alertas] == ["HELADA"] and alertas[0]["severidad"] == "CRITICA"


def test_validacion_rangos_fisicos(client, jefe_a):
    r = client.post("/api/v1/telemetria", json=lectura(humedad_suelo_pct=140), headers=jefe_a)
    assert r.status_code == 422
    assert any(d["campo"].endswith("humedad_suelo_pct") for d in r.json()["error"]["details"])


def test_rechaza_lectura_del_futuro(client, jefe_a):
    futuro = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    r = client.post("/api/v1/telemetria", json=lectura(tomada_en=futuro), headers=jefe_a)
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_READING"


def test_sector_inexistente(client, jefe_a):
    r = client.post("/api/v1/telemetria", json=lectura(sector_id=999), headers=jefe_a)
    assert r.status_code == 404


# ---------------- Autorización por rol ----------------
def test_jefe_no_puede_operar_en_otro_sector(client, jefe_a):
    r = client.post("/api/v1/telemetria", json=lectura(sector_id=2), headers=jefe_a)
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"


def test_dashboard_filtrado_por_rol(client, agronomo, jefe_a):
    assert len(client.get("/api/v1/dashboard", headers=agronomo).json()["sectores"]) == 3
    sectores_jefe = client.get("/api/v1/dashboard", headers=jefe_a).json()["sectores"]
    assert [s["sector_id"] for s in sectores_jefe] == [1]


# ---------------- Sincronización offline (idempotencia) ----------------
def test_lote_offline_es_idempotente(client, jefe_a):
    ahora = datetime.now(timezone.utc)
    lote = {"lecturas": [
        lectura(tomada_en=(ahora - timedelta(hours=h)).isoformat(), temperatura_c=1.5 if h == 3 else 15)
        for h in (1, 2, 3)
    ]}
    r1 = client.post("/api/v1/telemetria/lote", json=lote, headers=jefe_a).json()
    assert (r1["nuevas"], r1["duplicadas"], r1["alertas_generadas"]) == (3, 0, 1)
    # Reconexión inestable: el cliente reenvía el mismo lote
    r2 = client.post("/api/v1/telemetria/lote", json=lote, headers=jefe_a).json()
    assert (r2["nuevas"], r2["duplicadas"], r2["alertas_generadas"]) == (0, 3, 0)


def test_reconocer_alerta(client, jefe_a):
    a = client.post("/api/v1/telemetria", json=lectura(temperatura_c=0.5), headers=jefe_a).json()["alertas"][0]
    r = client.patch(f"/api/v1/alertas/{a['id']}/reconocer", headers=jefe_a)
    assert r.status_code == 200 and r.json()["reconocida"] is True


# ---------------- Telemetría continua (Arduino -> Gateway -> API) ----------------
def test_condicion_sostenida_no_duplica_alertas(client, jefe_a):
    """RN6: 5 lecturas seguidas de helada generan UNA alerta, no cinco."""
    ahora = datetime.now(timezone.utc)
    for i in range(5):
        ts = (ahora - timedelta(seconds=10 - i)).isoformat()
        client.post("/api/v1/telemetria", json=lectura(temperatura_c=1.0 - i * 0.1, tomada_en=ts), headers=jefe_a)
    alertas = client.get("/api/v1/dashboard", headers=jefe_a).json()["alertas_recientes"]
    assert [a["regla"] for a in alertas] == ["HELADA"]


def test_alerta_reconocida_permite_nueva_alerta(client, jefe_a):
    a = client.post("/api/v1/telemetria", json=lectura(temperatura_c=1.0), headers=jefe_a).json()["alertas"][0]
    client.patch(f"/api/v1/alertas/{a['id']}/reconocer", headers=jefe_a)
    ts = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
    r = client.post("/api/v1/telemetria", json=lectura(temperatura_c=0.8, tomada_en=ts), headers=jefe_a)
    assert len(r.json()["alertas"]) == 1


def test_escalar_severidad_crea_nueva_alerta(client, jefe_a):
    ahora = datetime.now(timezone.utc)
    client.post("/api/v1/telemetria", json=lectura(temperatura_c=3.5, tomada_en=(ahora - timedelta(seconds=5)).isoformat()), headers=jefe_a)
    r = client.post("/api/v1/telemetria", json=lectura(temperatura_c=1.0, tomada_en=ahora.isoformat()), headers=jefe_a)
    assert r.json()["alertas"][0]["severidad"] == "CRITICA"


def test_historial_devuelve_ultimas_lecturas_ordenadas(client, jefe_a):
    ahora = datetime.now(timezone.utc)
    for i in range(3):
        ts = (ahora - timedelta(minutes=3 - i)).isoformat()
        client.post("/api/v1/telemetria", json=lectura(temperatura_c=10 + i, tomada_en=ts), headers=jefe_a)
    r = client.get("/api/v1/telemetria?sector_id=1&limite=2", headers=jefe_a)
    assert r.status_code == 200
    assert [x["temperatura_c"] for x in r.json()] == [12, 11]  # más reciente primero


def test_historial_respeta_sector_del_jefe_y_requiere_token(client, jefe_a):
    assert client.get("/api/v1/telemetria?sector_id=2", headers=jefe_a).status_code == 403
    assert client.get("/api/v1/telemetria?sector_id=1").status_code == 401
    assert client.get("/api/v1/telemetria?sector_id=1&limite=9999", headers=jefe_a).status_code == 422


# ---------------- Agrónomo: solo lectura / umbrales generados ----------------
def test_agronomo_es_solo_lectura_en_operaciones_de_campo(client, agronomo, jefe_a):
    a = client.post("/api/v1/telemetria", json=lectura(temperatura_c=1.0), headers=jefe_a).json()["alertas"][0]
    assert client.post("/api/v1/telemetria", json=lectura(), headers=agronomo).status_code == 403
    assert client.post("/api/v1/telemetria/lote", json={"lecturas": [lectura()]}, headers=agronomo).status_code == 403
    assert client.patch(f"/api/v1/alertas/{a['id']}/reconocer", headers=agronomo).status_code == 403
    # ...pero consulta todo
    assert client.get("/api/v1/dashboard", headers=agronomo).status_code == 200
    assert client.get("/api/v1/telemetria?sector_id=1", headers=agronomo).status_code == 200
    assert client.get("/api/v1/alertas/umbrales", headers=agronomo).status_code == 200


def test_umbrales_son_de_solo_lectura_y_vienen_del_sistema(client, jefe_a):
    r = client.get("/api/v1/alertas/umbrales", headers=jefe_a)
    assert r.status_code == 200
    reglas = {u["regla"]: u for u in r.json()}
    assert set(reglas) == {"HELADA", "ESTRES_HIDRICO", "RADIACION_ALTA"}
    assert reglas["HELADA"]["condicion_critica"] == "≤ 2 °C"
    # Nadie puede editarlos: no existe ningún método de escritura
    for metodo in (client.put, client.post, client.patch, client.delete):
        assert metodo("/api/v1/alertas/umbrales", headers=jefe_a).status_code in (404, 405)
    assert client.get("/api/v1/alertas/umbrales").status_code == 401


def test_lectura_de_prueba_repetida_informa_que_la_alerta_ya_esta_activa(client, jefe_a):
    ahora = datetime.now(timezone.utc)
    r1 = client.post("/api/v1/telemetria", json=lectura(temperatura_c=1.0, tomada_en=(ahora - timedelta(seconds=5)).isoformat()), headers=jefe_a).json()
    r2 = client.post("/api/v1/telemetria", json=lectura(temperatura_c=1.0, tomada_en=ahora.isoformat()), headers=jefe_a).json()
    assert len(r1["alertas"]) == 1 and r1["alertas_repetidas"] == []
    assert r2["alertas"] == [] and [a["regla"] for a in r2["alertas_repetidas"]] == ["HELADA"]
