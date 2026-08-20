"""Tarjetas KPI de cierre — Nivel 1 del panel ejecutivo.

Portado de `INGESTA/Rep_Prod/backend/tests/test_analisis_tarjetas_kpi.py`.
Tests puros: no tocan BD ni LLM.

⚠️ DOS TESTS DEL ORIGEN SE PORTAN CORREGIDOS, NO COPIADOS.
`test_foco_por_promedio_cuando_no_hay_ppto` y
`test_sin_tarjetas_no_genera_focos_de_promedio` **fallan hoy en el propio
sistema viejo** (verificado ejecutando su suite: `2 failed, 14 passed`).
Quedaron obsoletos por la decisión del usuario del 2026-07-26: los focos pasan
a emitir UNA tarjeta por producto en orden fijo Crudo→Gas→Blancos, en vez de
solo los rezagados. Sus asserts esperaban la conducta anterior (lista vacía o
sin entrada para el producto que va bien).

Aquí se portan verificando la conducta REAL y vigente, con el matiz que sí
importa: que un producto sin PPTO pero por debajo de su promedio del año se
marque como foco de tipo `promedio`, y que uno por encima NO lo haga.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.features.analisis.services_ejecutivo import (
    UNIDADES_PRODUCTO,
    estado_cierre,
    focos,
    tarjetas_kpi,
)


def _t(producto: str, real: float, ppto: float) -> dict[str, Any]:
    return {
        "producto": producto,
        "real": real,
        "ppto": ppto,
        "valor_pct": None,
        "estado": "",
        "texto": "",
    }


# ── estado_cierre: la banda ámbar (eje propio, 93%) ─────────────────────────


@pytest.mark.unit
def test_alineado_cuando_supera_meta() -> None:
    assert estado_cierre(120, 100) == "alineado"


@pytest.mark.unit
def test_ajustado_en_la_banda_ambar() -> None:
    assert estado_cierre(95, 100) == "ajustado"  # 95% >= umbral 93%
    assert estado_cierre(93, 100) == "ajustado"


@pytest.mark.unit
def test_actuar_bajo_el_umbral_ambar() -> None:
    assert estado_cierre(92.9, 100) == "actuar"
    assert estado_cierre(50.7, 100) == "actuar"  # caso real APIAY


@pytest.mark.unit
def test_sin_meta_no_es_actuar() -> None:
    """Meta 0 (producto sin PPTO/PROGRAMA) NO debe leerse como 'actuar' (rojo)
    — es neutral: no hay con qué comparar."""
    assert estado_cierre(500, 0) == ""


# ── tarjetas_kpi ────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_no_divergencia_proyectado_cierre_es_titular_real() -> None:
    """`titular.real` YA es la proyección de cierre del mes completo: sumarle
    días de más la infla. El frontend verifica esta igualdad byte a byte."""
    titular = [_t("CRUDO", 12357703, 12928000)]
    tarjetas = tarjetas_kpi(titular)
    assert tarjetas[0]["proyectado_cierre"] == titular[0]["real"]
    assert tarjetas[0]["meta_mes"] == titular[0]["ppto"]


@pytest.mark.unit
def test_relleno_topa_en_100_sin_desbordar() -> None:
    tarjeta = tarjetas_kpi([_t("CRUDO", 150, 100)])[0]
    assert tarjeta["relleno_pct"] == 100.0
    assert tarjeta["alcanza"] is True
    assert tarjeta["brecha_abs"] == -50  # meta - proy; negativo = excedente


@pytest.mark.unit
def test_unidad_por_producto() -> None:
    """A5: cada producto con SU escala. GAS en MSCF, NUNCA en bbl."""
    tarjetas = tarjetas_kpi([_t("CRUDO", 1, 1), _t("GAS", 1, 1), _t("BLANCOS", 1, 1)])
    por_producto = {t["producto"]: t for t in tarjetas}
    assert por_producto["CRUDO"]["unidad"] == "bbl"
    assert por_producto["BLANCOS"]["unidad"] == "bbl"
    assert por_producto["GAS"]["unidad"] == "MSCF"
    assert UNIDADES_PRODUCTO["GAS"] == "MSCF"


@pytest.mark.unit
def test_producto_sin_meta_no_fabrica_cumplimiento() -> None:
    tarjeta = tarjetas_kpi([_t("GAS", 500, 0)])[0]
    assert tarjeta["alcanza"] is False
    assert tarjeta["estado"] == ""
    assert tarjeta["relleno_pct"] == 0.0


@pytest.mark.unit
def test_bopd_por_producto_reconcilia() -> None:
    """El ritmo diario se adjunta solo a los productos cuya curva diaria
    reconcilia con el mensual (Crudo, Gas). Blancos, cuyo diario suma ~2x el
    mes, queda sin ritmo: mostrarlo sería inventar una tasa."""
    titular = [_t("CRUDO", 100, 120), _t("GAS", 50, 60), _t("BLANCOS", 10, 20)]
    pace = {
        "CRUDO": {
            "promedio_dia": 2850000,
            "requerido_dia": 3230000,
            "delta_pct": 13.4,
        },
        "GAS": {"promedio_dia": 2340000, "requerido_dia": 3080000, "delta_pct": 31.6},
    }
    por_producto = {t["producto"]: t for t in tarjetas_kpi(titular, pace)}
    assert por_producto["CRUDO"]["bopd"] == {
        "real": 2850000,
        "requerido": 3230000,
        "delta_pct": 13.4,
    }
    assert por_producto["GAS"]["bopd"] == {
        "real": 2340000,
        "requerido": 3080000,
        "delta_pct": 31.6,
    }
    assert por_producto["BLANCOS"]["bopd"] is None


@pytest.mark.unit
def test_bopd_none_sin_pace() -> None:
    assert tarjetas_kpi([_t("CRUDO", 100, 120)])[0]["bopd"] is None
    assert tarjetas_kpi([_t("CRUDO", 100, 120)], None)[0]["bopd"] is None


@pytest.mark.unit
def test_hist_prom_se_adjunta() -> None:
    tarjetas = tarjetas_kpi([_t("BLANCOS", 618914, 1057263)], None, {"BLANCOS": 828212})
    assert tarjetas[0]["hist_prom"] == 828212


@pytest.mark.unit
def test_hist_prom_none_sin_historico() -> None:
    assert tarjetas_kpi([_t("BLANCOS", 1, 1)])[0]["hist_prom"] is None


@pytest.mark.unit
def test_fallback_sin_ppto_usa_promedio_del_anio() -> None:
    """Entidad SIN PPTO pero con promedio del año → ese promedio pasa a ser la
    meta de cierre. Evita la tarjeta muerta 'Sin meta definida'. Caso real:
    campo CUSIANA, sin presupuesto propio."""
    tarjeta = tarjetas_kpi([_t("CRUDO", 6300, 0)], None, {"CRUDO": 6000})[0]
    assert tarjeta["meta_de_promedio"] is True
    assert tarjeta["meta_mes"] == 6000.0
    assert tarjeta["alcanza"] is True
    assert tarjeta["estado"] == "alineado"
    assert tarjeta["relleno_pct"] == 100.0


@pytest.mark.unit
def test_sin_ppto_y_sin_promedio_sigue_sin_meta() -> None:
    """Sin PPTO y sin histórico NO se inventa meta (D-A4: nunca se fabrica)."""
    tarjeta = tarjetas_kpi([_t("GAS", 500, 0)], None, None)[0]
    assert tarjeta["meta_de_promedio"] is False
    assert tarjeta["meta_mes"] == 0.0
    assert tarjeta["estado"] == ""


# ── focos por promedio (adaptados: ver el aviso del docstring) ──────────────


@pytest.mark.unit
def test_foco_por_promedio_cuando_no_hay_ppto() -> None:
    """Sin PPTO, un producto que proyecta por DEBAJO de su promedio del año es
    un foco de tipo `promedio` (caso real: GAS de CUSIANA al 80%).

    El de arriba sigue emitiendo tarjeta —los 3 productos salen siempre desde
    2026-07-26— pero marcada `es_ok`, sin faltante y sin causa.
    """
    titular = [
        {"producto": "GAS", "real": 2631705, "ppto": 0, "valor_pct": None},
        {"producto": "CRUDO", "real": 6000, "ppto": 0, "valor_pct": None},
    ]
    tarjetas = tarjetas_kpi(titular, None, {"GAS": 3305551, "CRUDO": 5676})
    resultado = focos(titular, {}, None, [], tarjetas)

    gas = [f for f in resultado if f["producto"] == "GAS"][0]
    assert gas["tipo"] == "promedio"
    assert gas["es_ok"] is False
    assert "por debajo de su promedio" in gas["titulo"]

    crudo = [f for f in resultado if f["producto"] == "CRUDO"][0]
    assert crudo["tipo"] == "ok", "un producto por encima de su promedio no es foco"
    assert crudo["es_ok"] is True


@pytest.mark.unit
def test_sin_tarjetas_no_hay_focos_de_promedio() -> None:
    """Sin el argumento `tarjetas` no puede haber focos de tipo `promedio`: la
    meta-de-promedio se calcula justamente ahí.

    El producto sigue apareciendo (orden fijo Crudo→Gas→Blancos), pero como
    `ok`, no como foco.
    """
    titular = [{"producto": "GAS", "real": 100, "ppto": 0, "valor_pct": None}]
    resultado = focos(titular, {}, None, [])
    assert [f["tipo"] for f in resultado] == ["ok"]
    assert not [f for f in resultado if f["tipo"] == "promedio"]
