import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway import ApiPorSector, EdgeBuffer, FuenteSimulada, Rechazado, parsear_linea, sincronizar  # noqa: E402

OK = '{"id":"UNO-A01","t":18.2,"h":60.1,"r":612,"p":1.013}'


def test_linea_valida_se_convierte_al_formato_del_api():
    l = parsear_linea(OK, sector_id=1)
    assert (l["sensor_id"], l["sector_id"], l["temperatura_c"], l["radiacion_wm2"]) == ("UNO-A01", 1, 18.2, 612.0)
    assert l["tomada_en"].endswith("+00:00")  # el gateway sella la hora en UTC


@pytest.mark.parametrize("linea", ["", "   ", "# simulador listo"])
def test_comentarios_y_vacias_se_ignoran(linea):
    assert parsear_linea(linea, 1) is None


@pytest.mark.parametrize("linea", [
    "basura\x00\xff",                                    # ruido al abrir el puerto
    '{"id":"X","t":18.2,"h":60.1,"r":612',               # JSON cortado (cable desconectado a medias)
    '{"id":"X","t":18.2,"h":60.1,"r":612}',              # falta presión
    '{"id":"X","t":"18","h":60,"r":612,"p":1}',          # tipo incorrecto
    '{"id":"X","t":99,"h":60,"r":612,"p":1}',            # temperatura fuera de rango
    '{"id":"X","t":18,"h":140,"r":612,"p":1}',           # humedad fuera de rango
    '[1,2,3]',
])
def test_lineas_invalidas_lanzan_valueerror(linea):
    with pytest.raises(ValueError):
        parsear_linea(linea, 1)


def test_buffer_conserva_pendientes_y_marca_sincronizadas(tmp_path):
    ruta = str(tmp_path / "edge.sqlite")
    b = EdgeBuffer(ruta)
    for i in range(3):
        b.guardar({"n": i})
    assert b.contar_pendientes() == 3
    # Persiste aunque el proceso se reinicie (corte de energía del gateway)
    b2 = EdgeBuffer(ruta)
    pend = b2.pendientes()
    assert [p["n"] for _, p in pend] == [0, 1, 2]
    b2.marcar([pend[0][0], pend[1][0]], "SINCRONIZADA")
    assert b2.contar_pendientes() == 1


# ---------------- 3 sectores (A, B, C) con datos distintos ----------------
def test_el_campo_s_enruta_la_lectura_a_su_sector():
    base = '{"id":"UNO-%s01","s":"%s","t":18,"h":60,"r":600,"p":1}'
    assert [parsear_linea(base % (x, x), sector_id=1)["sector_id"] for x in "ABC"] == [1, 2, 3]
    assert parsear_linea(base % ("b", "b"), sector_id=1)["sector_id"] == 2   # minuscula tambien


def test_sector_desconocido_se_rechaza():
    with pytest.raises(ValueError, match="sector desconocido"):
        parsear_linea('{"id":"X","s":"Z","t":18,"h":60,"r":600,"p":1}', sector_id=1)


def test_sin_campo_s_se_usa_el_sector_por_defecto():
    assert parsear_linea(OK, sector_id=3)["sector_id"] == 3


def test_cada_sector_se_autentica_con_su_jefe():
    api = ApiPorSector("http://x", "pw")
    assert [api.para(i).email for i in (1, 2, 3)] == ["jefe.a@agro.cl", "jefe.b@agro.cl", "jefe.c@agro.cl"]
    assert api.para(2) is api.para(2)                       # un cliente (y un token) por sector
    with pytest.raises(Rechazado):
        api.para(9)
    assert ApiPorSector("http://x", "pw", "uno@agro.cl").para(3).email == "uno@agro.cl"


class FalsoApi:
    def __init__(self): self.enviados = []
    def enviar_lote(self, lecturas):
        self.enviados.append([l["sector_id"] for l in lecturas])
        return {"nuevas": len(lecturas), "duplicadas": 0, "alertas_generadas": 0}


class FalsoPorSector:
    def __init__(self): self.apis = {}
    def para(self, sector_id): return self.apis.setdefault(sector_id, FalsoApi())


def test_la_sincronizacion_agrupa_por_sector(tmp_path):
    b = EdgeBuffer(str(tmp_path / "e.sqlite"))
    for sec in (1, 2, 3, 1, 2):
        b.guardar({"sector_id": sec})
    api = FalsoPorSector()
    sincronizar(b, api)
    assert {k: v.enviados for k, v in api.apis.items()} == {1: [[1, 1]], 2: [[2, 2]], 3: [[3]]}
    assert b.contar_pendientes() == 0


def test_simulador_genera_datos_distintos_por_sector():
    f = FuenteSimulada(0)
    it = f.lineas()
    filas = [json.loads(next(it)) for _ in range(3)]
    assert [x["s"] for x in filas] == ["A", "B", "C"]
    assert len({x["t"] for x in filas}) == 3 and len({x["h"] for x in filas}) == 3   # ninguno igual
    assert filas[1]["h"] > filas[0]["h"] > filas[2]["h"]    # B hidroponico > A invernadero > C frutal


def test_comando_de_escenario_por_sector_o_global():
    f = FuenteSimulada(0)
    f.comando("hB")
    assert f.obj["B"]["t"] == 0.5 and f.obj["A"]["t"] == 22.0 and f.obj["C"]["t"] == 14.0
    f.comando("n")                                           # sin letra: todos vuelven a lo normal
    assert f.obj["B"]["t"] == 24.0
    f.comando("s")
    assert all(f.obj[x]["h"] == 15.0 for x in "ABC")
    f.comando("hZ")                                          # sector inexistente: se ignora
    assert f.obj["A"]["t"] == 22.0


# ---------------- simulación de fallas de sensor (desconectado / dañado) ----------------
def lectura_sector(sector_id, t=20.0):
    return {"sector_id": sector_id, "sensor_id": "X", "temperatura_c": t, "humedad_suelo_pct": 60.0,
            "radiacion_wm2": 500.0, "presion_bar": 1.0, "tomada_en": "2026-01-01T00:00:00+00:00"}


def test_sensor_desconectado_descarta_solo_su_sector():
    from gateway import FallasSensor
    f = FallasSensor()
    assert f.comando("xB") is True
    assert f.aplicar(lectura_sector(2)) is None            # B: sin datos
    assert f.aplicar(lectura_sector(1)) is not None        # A sigue enviando
    assert f.aplicar(lectura_sector(3)) is not None


def test_sensor_danado_repite_siempre_el_mismo_valor():
    from gateway import FallasSensor
    f = FallasSensor()
    f.comando("dC")
    primera = f.aplicar(lectura_sector(3, t=14.2))
    segunda = f.aplicar(lectura_sector(3, t=15.9))
    assert primera["temperatura_c"] == segunda["temperatura_c"] == 14.2
    assert f.aplicar(lectura_sector(1, t=22.5))["temperatura_c"] == 22.5   # otros sectores intactos


def test_n_repara_y_reconecta_y_sin_letra_aplica_a_todos():
    from gateway import FallasSensor
    f = FallasSensor()
    f.comando("x")
    assert all(f.aplicar(lectura_sector(i)) is None for i in (1, 2, 3))
    f.comando("nA")
    assert f.aplicar(lectura_sector(1)) is not None and f.aplicar(lectura_sector(2)) is None
    f.comando("d")
    f.comando("n")
    assert f.aplicar(lectura_sector(2, t=19.0))["temperatura_c"] == 19.0


def test_comandos_de_falla_invalidos_se_ignoran():
    from gateway import FallasSensor
    f = FallasSensor()
    assert f.comando("xZ") is False and f.comando("h") is False and f.comando("") is False
