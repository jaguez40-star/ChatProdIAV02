"""Slots y validador — Q1 y el segundo eslabón de Q3 (D2).

Tests portados y ampliados de `test_cuantificar.py` del sistema de origen.
"""

from __future__ import annotations

import pytest

from src.features.consulta.slots import extraer_slots
from src.features.consulta.validador import fmt_valor, formatear_cuerpo, intro_valido

pytestmark = pytest.mark.unit


# ═════════════════════════════════════════════════════════════════════════════
# D2 — el segundo eslabón de Q3
# ═════════════════════════════════════════════════════════════════════════════


def test_promedio_del_anio_es_referencia_y_fuerza_n1() -> None:
    """🔑 D2. `drills` ya resolvió que "promedio del año" es una continuación
    de REFERENCIA; aquí se resuelve el mismo conflicto sobre el texto ya
    autocontenido. La señal "DEL ANO" viene de la propia frase de referencia,
    no de un pedido de acumulado."""
    slots = extraer_slots("produccion de CASTILLA vs el promedio del año")

    assert slots["referencia"] == "promedio_anio"
    assert slots["nivel_temporal"] == "N1"


def test_una_senal_fuerte_conserva_el_acumulado_aunque_haya_referencia() -> None:
    """AF-4.9 revisado: "la producción ACUMULADA ... por debajo de su promedio
    anual" SÍ pide el acumulado, con el promedio como referencia. Forzar N1
    aquí perdía el "acumulado" en silencio, que es peor que declarar que la
    referencia no aplica."""
    slots = extraer_slots("la produccion acumulada de RUBIALES vs su promedio anual")

    assert slots["referencia"] == "promedio_anio"
    assert slots["nivel_temporal"] == "N2"


@pytest.mark.parametrize("fuerte", ["acumulado", "YTD", "en lo que va", "hasta ahora"])
def test_las_senales_fuertes_dan_n2(fuerte: str) -> None:
    assert extraer_slots(f"produccion {fuerte} de CASTILLA")["nivel_temporal"] == "N2"


# ═════════════════════════════════════════════════════════════════════════════
# Nivel temporal
# ═════════════════════════════════════════════════════════════════════════════


def test_pregunta_puntual_es_n1() -> None:
    assert extraer_slots("cuanto produjo CASTILLA en mayo")["nivel_temporal"] == "N1"


def test_serie_es_n3() -> None:
    assert extraer_slots("produccion de CASTILLA mes a mes")["nivel_temporal"] == "N3"


def test_variacion_gana_a_serie() -> None:
    """N4 es más específico: quien pregunta "cómo varió mes a mes" quiere los
    deltas, no la serie cruda."""
    slots = extraer_slots("como vario la produccion de CASTILLA mes a mes")
    assert slots["nivel_temporal"] == "N4"


def test_las_palabras_sueltas_se_comparan_por_token() -> None:
    """Si se compararan por substring, "BAJO" casaría dentro de "trabajo" y
    daría una variación donde no la hay."""
    assert extraer_slots("produccion del trabajo en CASTILLA")["nivel_temporal"] == "N1"


# ═════════════════════════════════════════════════════════════════════════════
# Producto
# ═════════════════════════════════════════════════════════════════════════════


def test_producto_por_defecto_es_crudo() -> None:
    slots = extraer_slots("cuanto produjo CASTILLA")
    assert slots["producto"] == "crudo"
    assert slots["unidad"] == "bbl"


def test_detecta_gas_y_su_unidad() -> None:
    slots = extraer_slots("cuanto gas produjo CUSIANA")
    assert slots["producto"] == "gas"
    assert slots["unidad"] == "MSCF"


def test_el_nombre_de_la_entidad_no_se_lee_como_producto() -> None:
    """🔑 AF10: un campo llamado "CAÑO BLANCO" no es el producto blancos."""
    slots = extraer_slots("cuanto produjo CAÑO BLANCO", entidad_valor="CAÑO BLANCO")
    assert slots["producto"] == "crudo"


def test_el_producto_gana_aunque_la_entidad_se_llame_parecido() -> None:
    """ "GAS" no es token del nombre, así que sí es el producto."""
    slots = extraer_slots("cuanto gas produjo CAÑO BLANCO", entidad_valor="CAÑO BLANCO")
    assert slots["producto"] == "gas"


# ═════════════════════════════════════════════════════════════════════════════
# Referencia y periodo
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("texto", "esperada"),
    [
        ("produccion de CASTILLA", "PPTO"),
        ("produccion de CASTILLA vs el operativo", "OPERATIVO"),
        ("produccion de CASTILLA contra el contable", "CONTABLE"),
        ("cual es el P50 de CASTILLA", "P50"),
    ],
)
def test_referencias(texto: str, esperada: str) -> None:
    assert extraer_slots(texto)["referencia"] == esperada


def test_extrae_el_mes_y_el_anio() -> None:
    assert extraer_slots("produccion de CASTILLA en abril 2026")["periodo_texto"] == (
        "abril 2026"
    )


def test_mes_pasado_viaja_literal() -> None:
    slots = extraer_slots("produccion de CASTILLA el mes pasado")
    assert slots["periodo_texto"] == "mes pasado"


def test_sin_mes_se_declara_el_default() -> None:
    slots = extraer_slots("cuanto produjo CASTILLA")
    assert slots["periodo_texto"] is None
    assert "periodo=mes actual" in slots["defaults_asumidos"]


# ═════════════════════════════════════════════════════════════════════════════
# Q1 — la red mecánica
# ═════════════════════════════════════════════════════════════════════════════


def test_un_saludo_limpio_es_valido() -> None:
    assert intro_valido("Claro, Javier, aquí tienes lo que encontré:") is True


def test_un_intro_con_digitos_se_rechaza() -> None:
    """🔑 Q1: es así como el modelo se cuela a dar cifras que no calculó."""
    assert intro_valido("Castilla alcanzó el 94% de su meta") is False


@pytest.mark.parametrize(
    "texto",
    [
        "va muy por debajo del presupuesto",
        "produjo varios millones de barriles",
        "la cifra en bbl es buena",
        "el gas en MSCF viene bien",
    ],
)
def test_un_intro_con_lexico_de_magnitud_se_rechaza(texto: str) -> None:
    """No basta con filtrar dígitos: "por debajo del presupuesto" afirma sobre
    la cifra sin escribir ningún número."""
    assert intro_valido(texto) is False


def test_un_intro_vacio_es_invalido() -> None:
    """Vacío significa que el LLM no respondió: el llamador debe servir su
    texto determinista."""
    assert intro_valido("") is False


# ═════════════════════════════════════════════════════════════════════════════
# A5 — la escala depende del producto
# ═════════════════════════════════════════════════════════════════════════════


def test_el_crudo_va_en_barriles_con_separador_de_miles() -> None:
    assert fmt_valor(10966768, "crudo") == "10.966.768"


def test_el_gas_se_divide_entre_un_millon() -> None:
    """🔑 A5: aplicar la escala equivocada da un número mil veces menor SIN
    error visible — el bug que mostró "0,03 MSCF" donde iban "33.453,2 bpd"."""
    assert fmt_valor(3_300_000, "gas") == "3,3"


def test_un_gas_pequeno_conserva_dos_decimales() -> None:
    """Con un solo decimal, 0,08 se redondearía a "0,1"; con cero, a "0"."""
    assert fmt_valor(80_000, "gas") == "0,08"


def test_un_valor_no_numerico_no_tumba_el_formateo() -> None:
    assert fmt_valor("s/d", "crudo") == "s/d"


# ═════════════════════════════════════════════════════════════════════════════
# Cuerpo de la respuesta
# ═════════════════════════════════════════════════════════════════════════════


def _res_n1() -> dict:
    return {
        "nivel": "N1",
        "producto": "crudo",
        "unidad": "bbl",
        "entidad_cualificada": "el Campo CASTILLA",
        "resultado": {"valor": 1_000_000},
        "cumplimiento_pct": 94.7,
        "referencia_valor": 1_056_000,
        "referencia_label": "presupuesto",
        "estado": "Rezagado",
        "mes": {
            "nombre": "Mayo",
            "anio": 2026,
            "completo": False,
            "dias_con_data": 17,
            "dias_del_mes": 31,
        },
        "avisos": [],
    }


def test_el_cuerpo_puntual_declara_el_nivel_y_la_proyeccion() -> None:
    """D1: "el Campo CASTILLA" y "el Activo CASTILLA" son cifras DISTINTAS.
    Y un mes incompleto se declara como proyección, con sus días."""
    cuerpo = formatear_cuerpo(_res_n1())

    assert "el Campo CASTILLA" in cuerpo
    assert "proyección · 17/31 días" in cuerpo
    assert "1.000.000 bbl" in cuerpo


def test_los_avisos_van_siempre_al_final() -> None:
    res = _res_n1()
    res["avisos"] = ["cobertura parcial"]
    assert formatear_cuerpo(res).endswith("⚠️ cobertura parcial")


def test_el_promedio_anual_no_repite_el_calificador_temporal() -> None:
    """ "promedio mensual del año del mes" es redundante; las demás
    referencias sí necesitan el "del mes"."""
    res = _res_n1()
    res["referencia"] = "promedio_anio"
    res["referencia_label"] = "promedio mensual del año"
    cuerpo = formatear_cuerpo(res)

    assert "del año del mes" not in cuerpo


def test_la_serie_no_lee_las_claves_que_no_tiene() -> None:
    """🔑 N3/N4 se resuelven ANTES de tocar `resultado`/`mes`: esas claves no
    existen en su contrato y leerlas reventaría con KeyError."""
    res = {
        "nivel": "N3",
        "producto": "crudo",
        "unidad": "bbl",
        "entidad_cualificada": "el Campo CASTILLA",
        "anio": 2026,
        "serie": [{"mes": "Ene", "valor": 100}, {"mes": "Feb", "valor": 200}],
        "promedio": 150,
        "avisos": [],
    }
    cuerpo = formatear_cuerpo(res)

    assert "Ene 100" in cuerpo
    assert "Promedio mensual" in cuerpo


def test_la_variacion_dice_si_subio_o_bajo() -> None:
    res = {
        "nivel": "N4",
        "producto": "crudo",
        "unidad": "bbl",
        "entidad_cualificada": "el Campo CASTILLA",
        "ultimo": {"de": "Abril", "a": "Mayo", "delta": -5000, "pct": -4.2},
        "deltas": [{"de": "Abril", "a": "Mayo", "delta": -5000}],
        "avisos": [],
    }
    cuerpo = formatear_cuerpo(res)

    assert "bajó" in cuerpo
    assert "5.000" in cuerpo


def test_el_acumulado_dice_cuantos_meses_cerrados() -> None:
    res = {
        "nivel": "N2",
        "producto": "crudo",
        "unidad": "bbl",
        "entidad_cualificada": "el Campo CASTILLA",
        "resultado": {"valor": 5_000_000},
        "cumplimiento_pct": 98.0,
        "referencia_valor": 5_100_000,
        "periodo_label": "2026",
        "meses_cerrados": 4,
        "estado": "Alineado",
        "avisos": [],
    }
    cuerpo = formatear_cuerpo(res)

    assert "4 meses cerrados" in cuerpo
    assert "Presupuesto acumulado" in cuerpo


def test_un_solo_mes_cerrado_va_en_singular() -> None:
    res = {
        "nivel": "N2",
        "producto": "crudo",
        "unidad": "bbl",
        "entidad_cualificada": "el Campo CASTILLA",
        "resultado": {"valor": 1_000_000},
        "cumplimiento_pct": 100.0,
        "referencia_valor": None,
        "periodo_label": "2026",
        "meses_cerrados": 1,
        "estado": "Alineado",
        "avisos": [],
    }
    assert "1 mes cerrado" in formatear_cuerpo(res)
