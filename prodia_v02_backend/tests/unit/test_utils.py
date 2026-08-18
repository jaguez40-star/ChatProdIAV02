"""Tests de _sanitize_col (DT-18/A6): Infinity/NaN -> None."""

from __future__ import annotations

import math

import pytest

from src.shared.utils import _sanitize_col


@pytest.mark.unit
def test_sanitize_col_reemplaza_infinity() -> None:
    assert _sanitize_col([1.0, math.inf, -math.inf, 2.0]) == [1.0, None, None, 2.0]


@pytest.mark.unit
def test_sanitize_col_reemplaza_nan() -> None:
    result = _sanitize_col([1.0, math.nan, 2.0])
    assert result == [1.0, None, 2.0]


@pytest.mark.unit
def test_sanitize_col_preserva_none() -> None:
    assert _sanitize_col([None, 1.0, None]) == [None, 1.0, None]


@pytest.mark.unit
def test_sanitize_col_lista_vacia() -> None:
    assert _sanitize_col([]) == []


@pytest.mark.unit
def test_sanitize_col_sin_valores_problematicos() -> None:
    assert _sanitize_col([1.0, 2.0, 3.0]) == [1.0, 2.0, 3.0]
