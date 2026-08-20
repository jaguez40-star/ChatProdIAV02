"""Focos tipo `gap`: coherencia entre lo que el titular dice y lo que lista el detalle.

Portado de `INGESTA/Rep_Prod/backend/tests/test_analisis_focos_gap.py`.

Caso real que motivó estos tests (GAS, mayo-2026, global ECP — verificado
contra la BD):

    titular : -10.813.358        ← gap NETO (faltantes menos excedentes)
    detalle : CUSIANA -16.667.554 · CUPIAGUA -2.616.860 · ARAUCA -530.282
    título  : "CUSIANA + CUPIAGUA · 90.6% del faltante en 2 campos"

Dos incoherencias: (1) el 90,6 % era la concentración del top-3 —incluía
ARAUCA— mientras el texto nombraba 2 campos, y con 2 el valor real es 88,2 %;
(2) el titular era neto y el detalle bruto, sin nada que explicara por qué los
campos listados suman casi el doble.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.features.analisis.services_ejecutivo import focos


def _gap(
    detr: list[tuple[str, float]],
    comp: list[tuple[str, float]],
    bruto: float,
    exced: float,
    conc_top3: float | None,
) -> dict[str, Any]:
    """Simula la salida de `gap_campo` para un producto."""
    return {
        "detractores": [
            {"campo": c, "gap": g, "real": 0, "meta": 0, "eventos": []} for c, g in detr
        ],
        "compensadores": [
            {"campo": c, "gap": g, "real": 0, "meta": 0} for c, g in comp
        ],
        "faltante_bruto": bruto,
        "excedente_bruto": exced,
        "concentracion_pct": conc_top3,
    }


# Cifras reales de GAS · mayo-2026 · global ECP
_GAS = _gap(
    detr=[("CUSIANA", -16667554), ("CUPIAGUA", -2616859), ("ARAUCA", -530282)],
    comp=[("PAUTO SUR", 5756510), ("CHUCHUPA", 2282052)],
    bruto=-21862963,
    exced=11049613,
    conc_top3=90.6,
)
_TITULAR = [{"producto": "GAS", "real": 9868311, "ppto": 20681661, "valor_pct": 47.7}]


def _foco_gas() -> dict[str, Any]:
    return [f for f in focos(_TITULAR, {"GAS": _GAS}, None, []) if f["tipo"] == "gap"][
        0
    ]


@pytest.mark.unit
def test_concentracion_corresponde_a_los_campos_nombrados() -> None:
    """El % del título se calcula sobre los campos que el título NOMBRA (2), no
    sobre el top-3 fijo."""
    foco = _foco_gas()
    assert foco["entidades"] == ["CUSIANA", "CUPIAGUA"]
    assert "88.2% del faltante en 2 campos" in foco["titulo"]
    assert "90.6%" not in foco["titulo"]
    assert foco["peso_relativo_pct"] == 88.2


@pytest.mark.unit
def test_titulo_no_repite_las_entidades() -> None:
    """El frontend antepone `entidades`; si el título también las trae sale
    duplicado ("GAS · CUSIANA + CUPIAGUA CUSIANA + CUPIAGUA · 88.2%…")."""
    foco = _foco_gas()
    for entidad in foco["entidades"]:
        assert entidad not in foco["titulo"]


@pytest.mark.unit
def test_detalle_cierra_la_aritmetica_bruto_neto() -> None:
    """El detalle explica por qué los faltantes listados no suman el titular.

    Sin esta línea el panel mostraba "-10.813.358" con un detalle que sumaba
    19.814.696 y nada que justificara la diferencia.
    """
    foco = _foco_gas()
    assert foco["faltante_abs"] == -10813350  # neto = real - ppto
    cierre = foco["causa"]["detalle"][-1]
    assert "Faltante bruto 21.862.963" in cierre
    assert "excedentes 11.049.613" in cierre
    assert "neto 10.813.350" in cierre
    # Invariante auditable: bruto + excedentes == neto
    assert foco["faltante_bruto"] + foco["excedente_bruto"] == -10813350


@pytest.mark.unit
def test_un_solo_detractor_no_usa_plantilla_de_concentracion() -> None:
    """Con un único campo el título no habla de concentración: no hay nada que
    concentrar."""
    gap = _gap(
        detr=[("CUPIAGUA", -2616859)],
        comp=[],
        bruto=-2616859,
        exced=0,
        conc_top3=100.0,
    )
    titular = [
        {"producto": "GAS", "real": 9868311, "ppto": 12485170, "valor_pct": 79.0}
    ]
    foco = [f for f in focos(titular, {"GAS": gap}, None, []) if f["tipo"] == "gap"][0]

    assert foco["titulo"] == "concentra el rezago del producto"
    assert foco["entidades"] == ["CUPIAGUA"]
    # Sin excedentes no se agrega la línea de cierre: no hay diferencia que explicar.
    assert all("Faltante bruto" not in d for d in foco["causa"]["detalle"])
