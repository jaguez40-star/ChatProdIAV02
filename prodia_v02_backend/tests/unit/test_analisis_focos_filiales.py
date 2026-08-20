"""Focos de FILIALES coherentes con sus tarjetas (base promedio 2026).

Portado de `INGESTA/Rep_Prod/backend/tests/test_analisis_focos_filiales.py`.

Regresión del bug: el bloque central de "Desempeño Filiales" usaba el `focos`
de ECP —que mide REAL vs PROGRAMA misma-ventana— y **contradecía a las
tarjetas**: Permian aparecía como "excedente en crudo" mientras su propia
tarjeta lo marcaba 148k por DEBAJO de su promedio 2026.

Estas funciones descomponen el faltante del grupo por filial sobre la MISMA
base que las tarjetas y que el desglose por filial, así que no pueden divergir.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.features.analisis.services_filiales import focos_filiales, sin_foco_filiales

# `titular_cards`: real = proyección de cierre, ppto = promedio 2026.
_TITULAR = [
    {"producto": "CRUDO", "real": 2227220, "ppto": 2370338},  # 94% → por debajo
    {"producto": "GAS", "real": 1025027, "ppto": 1006772},  # 102% → por encima
    {"producto": "BLANCOS", "real": 648951, "ppto": 620628},  # 104% → por encima
]


def _filial(empresa: str, productos: dict[str, tuple[float, float]]) -> dict[str, Any]:
    """`productos`: {producto: (proyeccion, promedio_2026)}."""
    por_producto = [
        {"producto": p, "proyeccion": v[0], "promedio_2026": v[1], "reporta": True}
        for p, v in productos.items()
    ]
    return {"empresa": empresa, "t": {"por_producto": por_producto}}


_POR_FILIAL_RAW = [
    _filial("Hocol", {"CRUDO": (601862, 619192), "GAS": (349201, 373666)}),
    _filial("America", {"CRUDO": (268238, 245963), "GAS": (65877, 60563)}),
    _filial(
        "Permian",
        {
            "CRUDO": (1357121, 1505183),
            "GAS": (609950, 572544),
            "BLANCOS": (648951, 620628),
        },
    ),
]


@pytest.mark.unit
def test_foco_es_crudo_y_solo_crudo() -> None:
    """Solo Crudo proyecta por debajo de su promedio a nivel grupo."""
    resultado = focos_filiales(_TITULAR, _POR_FILIAL_RAW)
    assert [f["producto"] for f in resultado] == ["CRUDO"]


@pytest.mark.unit
def test_detractores_son_permian_y_hocol() -> None:
    """Las dos filiales por debajo, más negativa primero (Permian -148k, Hocol
    -17k). America NO: está por encima."""
    crudo = focos_filiales(_TITULAR, _POR_FILIAL_RAW)[0]
    assert crudo["entidades"] == ["Permian", "Hocol"]
    assert "America" not in crudo["entidades"]


@pytest.mark.unit
def test_faltante_grupo_reconcilia() -> None:
    crudo = focos_filiales(_TITULAR, _POR_FILIAL_RAW)[0]
    assert crudo["faltante_abs"] == 2227220 - 2370338


@pytest.mark.unit
def test_permian_no_es_excedente_en_crudo() -> None:
    """El corazón del bug: Permian está por debajo en crudo, así que NUNCA debe
    listarse como excedente en crudo."""
    texto = sin_foco_filiales(_TITULAR, _POR_FILIAL_RAW)
    assert "en crudo" in texto.lower()  # sí hay excedente de crudo (America)…
    assert "Permian en crudo" not in texto  # …pero no Permian
    assert "America en crudo" in texto


@pytest.mark.unit
def test_titulo_no_repite_entidades() -> None:
    """El frontend antepone `entidades`; el título no debe volver a nombrarlas."""
    crudo = focos_filiales(_TITULAR, _POR_FILIAL_RAW)[0]
    assert "Permian" not in crudo["titulo"]
    assert "Hocol" not in crudo["titulo"]


@pytest.mark.unit
def test_sin_foco_cuando_todo_en_meta() -> None:
    titular_ok = [{"producto": "CRUDO", "real": 100, "ppto": 90}]
    raw = [_filial("Hocol", {"CRUDO": (100, 90)})]
    assert focos_filiales(titular_ok, raw) == []
