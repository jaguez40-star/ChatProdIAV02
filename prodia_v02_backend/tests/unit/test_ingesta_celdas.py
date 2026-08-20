"""Tests de la lectura de celdas — se aplica a CADA celda que atraviesa el ETL.

El origen no tenía ninguno de estos tests (G9: 34 líneas en total y el único sustantivo
siempre saltado). Cambiar cuándo estas funciones devuelven `None` cambia en silencio lo
que acaba en PostgreSQL, así que aquí se fija el comportamiento portado.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from src.features.ingesta.celdas import NOISE, num, s, to_date

# ── s() — texto limpio ───────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize("ruido", sorted(NOISE))
def test_s_convierte_el_ruido_de_excel_en_none(ruido: str) -> None:
    """Un `#REF!` es un dato ausente, no una fila inválida."""
    assert s(ruido) is None


@pytest.mark.unit
def test_s_recorta_espacios() -> None:
    assert s("  CASTILLA  ") == "CASTILLA"


@pytest.mark.unit
def test_s_convierte_numeros_a_texto() -> None:
    assert s(2026) == "2026"


@pytest.mark.unit
def test_s_de_none_es_none() -> None:
    assert s(None) is None


# ── num() — números ──────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [(1.5, 1.5), (3, 3.0), ("1.5", 1.5), ("  2  ", 2.0), (-0.25, -0.25)],
)
def test_num_convierte_valores_numericos(entrada: Any, esperado: float) -> None:
    assert num(entrada) == esperado


@pytest.mark.unit
@pytest.mark.parametrize(
    "entrada", ["#REF!", "#DIV/0!", "", "(en blanco)", "hola", None]
)
def test_num_devuelve_none_ante_ruido_o_texto(entrada: Any) -> None:
    assert num(entrada) is None


@pytest.mark.unit
def test_num_trata_los_booleanos_como_1_y_0() -> None:
    """Comportamiento heredado: en Python un bool ES un int. Convertirlo a `None`
    'por limpieza' transformaría un flag verdadero en dato ausente."""
    assert num(True) == 1.0
    assert num(False) == 0.0


@pytest.mark.unit
def test_num_preserva_volumenes_grandes() -> None:
    assert num(314952.75) == 314952.75


# ── to_date() — fechas ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_to_date_desde_entero_yyyymmdd() -> None:
    assert to_date(20240930) == dt.date(2024, 9, 30)


@pytest.mark.unit
def test_to_date_desde_float_que_excel_devuelve_como_texto() -> None:
    """Excel entrega enteros como float: '20240930.0' debe leerse igual."""
    assert to_date("20240930.0") == dt.date(2024, 9, 30)


@pytest.mark.unit
def test_to_date_desde_datetime_y_date() -> None:
    assert to_date(dt.datetime(2026, 8, 15, 13, 45)) == dt.date(2026, 8, 15)
    assert to_date(dt.date(2026, 8, 15)) == dt.date(2026, 8, 15)


@pytest.mark.unit
def test_to_date_desde_iso() -> None:
    assert to_date("2026-08-15") == dt.date(2026, 8, 15)
    assert to_date("2026-08-15T10:00:00") == dt.date(2026, 8, 15)


@pytest.mark.unit
@pytest.mark.parametrize("entrada", [None, "", 0, "#REF!", "no-es-fecha"])
def test_to_date_devuelve_none_ante_vacio_o_invalido(entrada: Any) -> None:
    """El 0 se trata como vacío: las hojas lo usan donde no hay fecha."""
    assert to_date(entrada) is None


@pytest.mark.unit
@pytest.mark.parametrize("entrada", [20241332, "20240230"])
def test_to_date_rechaza_fechas_imposibles(entrada: Any) -> None:
    """Mes 13 o 30 de febrero: 8 dígitos no bastan para ser una fecha."""
    assert to_date(entrada) is None
