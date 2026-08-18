"""Utilidades compartidas de backend.

`_sanitize_col` — corrección DT-18 de la plantilla Robustez V02 (A6): sin esto,
un cálculo que produce Infinity/NaN (división por cero, promedio de conjunto
vacío) rompe la serialización JSON en silencio o produce un valor no válido
que el frontend no puede parsear. Se aplica ANTES de construir cualquier
response de una feature numérica (F2 en adelante).
"""

from __future__ import annotations

import math
from collections.abc import Iterable


def _sanitize_col(values: Iterable[float | None]) -> list[float | None]:
    """Reemplaza Infinity/-Infinity/NaN por None. Preserva None ya existentes."""
    out: list[float | None] = []
    for v in values:
        if v is None:
            out.append(None)
        elif isinstance(v, float) and (math.isinf(v) or math.isnan(v)):
            out.append(None)
        else:
            out.append(v)
    return out
