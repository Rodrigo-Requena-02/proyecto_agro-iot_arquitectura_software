"""El dashboard entrega el estado de cada sensor, por sector y respetando los roles."""
from datetime import datetime, timedelta, timezone


def lectura(hace_s=0, **kw):
    base = dict(sector_id=1, sensor_id="UNO-A01", temperatura_c=18.5, humedad_suelo_pct=60,
                radiacion_wm2=600, presion_bar=1.013)
    base.update(kw)
    base["tomada_en"] = (datetime.now(timezone.utc) - timedelta(seconds=hace_s)).isoformat()
    return base


def sensores_sector_a(client, headers):
    dash = client.get("/api/v1/dashboard", headers=headers).json()
    return next(s for s in dash["sectores"] if s["sector_id"] == 1)["sensores"]


def test_sector_sin_lecturas_no_tiene_sensores(client, jefe_a):
    assert sensores_sector_a(client, jefe_a) == []


def test_sensor_que_acaba_de_reportar_esta_conectado_y_bueno(client, jefe_a, agronomo):
    assert client.post("/api/v1/telemetria", json=lectura(), headers=jefe_a).status_code == 201
    for h in (jefe_a, agronomo):  # los dos roles ven el estado
        (s,) = sensores_sector_a(client, h)
        assert (s["sensor_id"], s["conexion"], s["salud"]) == ("UNO-A01", "CONECTADO", "BUENO")


def test_sensor_que_dejo_de_reportar_esta_desconectado(client, jefe_a):
    client.post("/api/v1/telemetria", json=lectura(hace_s=120), headers=jefe_a)
    (s,) = sensores_sector_a(client, jefe_a)
    assert s["conexion"] == "DESCONECTADO" and s["segundos_sin_datos"] >= 119


def test_valores_congelados_se_reportan_como_danado(client, jefe_a):
    for i in range(5):  # mismas cuatro variables, instantes distintos
        assert client.post("/api/v1/telemetria", json=lectura(hace_s=i), headers=jefe_a).status_code == 201
    (s,) = sensores_sector_a(client, jefe_a)
    assert (s["conexion"], s["salud"]) == ("CONECTADO", "DANADO") and "congelados" in s["motivo"]


def test_cada_sensor_del_sector_tiene_su_propio_estado(client, jefe_a):
    client.post("/api/v1/telemetria", json=lectura(), headers=jefe_a)
    client.post("/api/v1/telemetria", json=lectura(sensor_id="UNO-A02", hace_s=300), headers=jefe_a)
    estados = {s["sensor_id"]: s["conexion"] for s in sensores_sector_a(client, jefe_a)}
    assert estados == {"UNO-A01": "CONECTADO", "UNO-A02": "DESCONECTADO"}


def test_el_jefe_solo_ve_los_sensores_de_su_sector(client, jefe_a, agronomo):
    client.post("/api/v1/telemetria", json=lectura(), headers=jefe_a)
    assert len(client.get("/api/v1/dashboard", headers=jefe_a).json()["sectores"]) == 1
