"""Estado de sensores (CONECTADO / DESCONECTADO, BUENO / DAÑADO): lógica pura, sin BD ni HTTP."""
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services.estado_sensores import (
    LECTURAS_PARA_ATASCO, SEGUNDOS_DESCONEXION, evaluar_sensor, evaluar_sensores,
)

AHORA = datetime(2026, 10, 29, 12, 0, 0)


def lec(hace_s=0, t=20.0, h=60.0, r=500.0, p=1.0):
    return SimpleNamespace(temperatura_c=t, humedad_suelo_pct=h, radiacion_wm2=r, presion_bar=p,
                           tomada_en=AHORA - timedelta(seconds=hace_s))


def con_ruido(n=5):
    """n lecturas distintas (un sensor sano siempre tiene algo de ruido), la más nueva primero."""
    return [lec(hace_s=2 * i, t=20 + i * 0.1, h=60 + i * 0.2) for i in range(n)]


def test_sensor_reciente_y_con_ruido_esta_conectado_y_bueno():
    e = evaluar_sensor("S1", con_ruido(), AHORA)
    assert (e.conexion, e.salud, e.motivo) == ("CONECTADO", "BUENO", None)


def test_sin_datos_recientes_esta_desconectado():
    justo = evaluar_sensor("S1", [lec(hace_s=SEGUNDOS_DESCONEXION)], AHORA)
    pasado = evaluar_sensor("S1", [lec(hace_s=SEGUNDOS_DESCONEXION + 1)], AHORA)
    assert justo.conexion == "CONECTADO"
    assert pasado.conexion == "DESCONECTADO" and "Sin datos" in pasado.motivo
    assert pasado.salud == "BUENO"  # desconectado no implica dañado


def test_valores_congelados_marcan_el_sensor_como_danado():
    iguales = [lec(hace_s=2 * i) for i in range(LECTURAS_PARA_ATASCO)]
    e = evaluar_sensor("S1", iguales, AHORA)
    assert e.salud == "DANADO" and "congelados" in e.motivo
    assert e.conexion == "CONECTADO"


def test_pocas_lecturas_iguales_no_alcanzan_para_declarar_dano():
    assert evaluar_sensor("S1", [lec(), lec(hace_s=2)], AHORA).salud == "BUENO"


def test_un_solo_valor_distinto_en_la_ventana_evita_el_falso_positivo():
    ls = [lec(hace_s=2 * i) for i in range(LECTURAS_PARA_ATASCO)]
    ls[-1] = lec(hace_s=8, t=20.1)
    assert evaluar_sensor("S1", ls, AHORA).salud == "BUENO"


def test_valor_en_el_limite_fisico_marca_dano():
    for kw in ({"t": 60.0}, {"t": -40.0}, {"h": 0.0}, {"h": 100.0}, {"p": 10.0}):
        e = evaluar_sensor("S1", [lec(**kw)], AHORA)
        assert e.salud == "DANADO" and "límite" in e.motivo, kw


def test_radiacion_cero_y_presion_cero_son_validas():
    # De noche la radiación es 0 y una bomba apagada marca 0 bar: no son fallas.
    assert evaluar_sensor("S1", [lec(r=0.0, p=0.0)], AHORA).salud == "BUENO"


def test_desconectado_y_danado_a_la_vez_prioriza_el_motivo_del_dano():
    e = evaluar_sensor("S1", [lec(hace_s=120, t=60.0)], AHORA)
    assert (e.conexion, e.salud) == ("DESCONECTADO", "DANADO") and "límite" in e.motivo


def test_lectura_con_reloj_adelantado_no_da_segundos_negativos():
    assert evaluar_sensor("S1", [lec(hace_s=-30)], AHORA).segundos_sin_datos == 0


def test_evaluar_sensores_ordena_por_id_e_ignora_vacios():
    out = evaluar_sensores({"B": con_ruido(1), "A": con_ruido(1), "C": []}, AHORA)
    assert [e.sensor_id for e in out] == ["A", "B"]
