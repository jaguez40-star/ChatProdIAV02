"""La tesis del Análisis Ejecutivo: el prompt NUNCA pide un rezago inexistente.

Portado de `INGESTA/Rep_Prod/backend/tests/test_analisis_ejecutivo_tesis.py`.
La política de reintento del LLM que ese archivo también cubría vive ahora en
`test_llm_client.py`, junto al módulo que la implementa.

**Q2 — REGLA CERO.** Origen: CASTILLA como campo (mayo 2026, corte 17/31) tiene
CRUDO al 102,7 % y GAS/BLANCOS sin meta, así que `sintesis` y
`detalle_por_producto` llegan vacíos. El prompt igual exigía "la historia del
mes" y "contrasta lo transitorio con lo estructural", de modo que Gemma fabricó
un "déficit significativo" y luego descarriló el JSON.

El JSON roto era el síntoma; **la alucinación era la enfermedad**: con el JSON
bien formado, ese brief falso se habría pintado como válido. Python declara la
verdad y el prompt se ramifica sobre ella.

Funciones puras: no tocan BD ni LLM.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.features.analisis.prompts import reglas_tesis
from src.features.analisis.services_ejecutivo import situacion_general


def _t(producto: str, pct: float | None) -> dict[str, Any]:
    return {"producto": producto, "valor_pct": pct}


# CASTILLA campo: el caso real que rompió.
CASTILLA = [_t("CRUDO", 102.7), _t("GAS", None), _t("BLANCOS", None)]

# Rama con rezago: la usa el brief global de ECP y no debe cambiar.
CON_REZAGO = [_t("CRUDO", 94.7), _t("GAS", 87.0), _t("BLANCOS", 58.5)]
SINTESIS = [
    {"producto": "CRUDO", "pct_presupuesto": 94.7},
    {"producto": "BLANCOS", "pct_presupuesto": 58.5},
]


# ── situacion_general: la verdad que declara Python ─────────────────────────


@pytest.mark.unit
def test_castilla_campo_no_tiene_rezago() -> None:
    """Todo en meta o sin meta ⇒ `hay_rezago` False. Es el gate de la rama."""
    situacion = situacion_general(CASTILLA, sintesis=[])
    assert situacion["hay_rezago"] is False
    assert situacion["productos_rezagados"] == []
    assert situacion["productos_sin_meta"] == ["GAS", "BLANCOS"]


@pytest.mark.unit
def test_sin_meta_se_declara_como_no_faltante() -> None:
    """Un producto sin meta NO es un faltante: el resumen debe decirlo, porque
    el modelo tendía a leer 'REAL 0 / PPTO 0' como producción caída."""
    situacion = situacion_general(CASTILLA, sintesis=[])
    assert "NO es un faltante" in situacion["resumen"]
    assert "GAS, BLANCOS" in situacion["resumen"]


@pytest.mark.unit
def test_resumen_sin_rezago_lleva_el_pct_exacto() -> None:
    situacion = situacion_general(CASTILLA, sintesis=[])
    assert "NO hay rezago" in situacion["resumen"]
    assert "CRUDO 102.7%" in situacion["resumen"]


@pytest.mark.unit
def test_sin_ninguna_meta_no_hay_cumplimiento_que_evaluar() -> None:
    """Sin PPTO en ningún producto: ni rezago ni logro."""
    situacion = situacion_general(
        [_t("CRUDO", None), _t("GAS", None), _t("BLANCOS", None)], sintesis=[]
    )
    assert situacion["hay_rezago"] is False
    assert "no hay cumplimiento que evaluar" in situacion["resumen"]


@pytest.mark.unit
def test_con_rezago_lista_los_productos_por_debajo() -> None:
    situacion = situacion_general(CON_REZAGO, SINTESIS)
    assert situacion["hay_rezago"] is True
    assert situacion["productos_rezagados"] == ["CRUDO", "BLANCOS"]


# ── reglas_tesis: el prompt se ramifica sobre esa verdad ────────────────────


@pytest.mark.unit
def test_prompt_sin_rezago_prohibe_inventarlo() -> None:
    """El corazón del fix (Q2): sin rezago, la instrucción PROHÍBE fabricar uno."""
    reglas = reglas_tesis(situacion_general(CASTILLA, sintesis=[]))
    assert "REGLA CERO" in reglas
    assert "PROHIBIDO inventar" in reglas
    assert "NO HAY REZAGO" in reglas


@pytest.mark.unit
def test_prompt_sin_rezago_no_pide_narrar_la_sintesis_vacia() -> None:
    """Regresión directa: `sintesis` llegaba vacía y el prompt decía 'es tu
    tesis, nárrala'. Tampoco debe pedir contrastar transitorio vs estructural
    ni mencionar campos — no los hay."""
    reglas = reglas_tesis(situacion_general(CASTILLA, sintesis=[]))
    assert "es tu tesis, nárrala" not in reglas
    assert "contrasta lo transitorio" not in reglas
    assert "NO menciones campos" in reglas


@pytest.mark.unit
def test_prompt_sin_rezago_explica_como_leer_el_pace() -> None:
    """Gemma leyó el pace al revés: dijo 'déficit' con requerido < promedio, o
    sea con el ritmo sobrado."""
    reglas = reglas_tesis(situacion_general(CASTILLA, sintesis=[]))
    assert "SOBRA" in reglas


@pytest.mark.unit
def test_con_rezago_conserva_la_tesis_original() -> None:
    reglas = reglas_tesis(situacion_general(CON_REZAGO, SINTESIS))
    assert "es tu tesis, nárrala" in reglas
    assert "REGLA CERO" not in reglas


@pytest.mark.unit
def test_las_dos_ramas_son_excluyentes() -> None:
    """Ninguna combinación debe emitir las dos tesis a la vez: se contradicen."""
    for titular, sintesis in ((CASTILLA, []), (CON_REZAGO, SINTESIS)):
        reglas = reglas_tesis(situacion_general(titular, sintesis))
        assert ("REGLA CERO" in reglas) != ("es tu tesis, nárrala" in reglas)
