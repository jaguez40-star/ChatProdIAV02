"""Lectura de celdas de Excel — portado de `app/shared/utils.py` del sistema viejo.

Estas tres funciones se aplican a **cada celda** que atraviesa el ETL, así que su
comportamiento es parte del contrato de datos: cambiar cuándo devuelven `None` cambia
silenciosamente lo que acaba en PostgreSQL.

`NOISE` es la lista de valores que Excel produce y que NO son datos: errores de fórmula
(`#REF!`, `#DIV/0!`…) y los marcadores de celda vacía que usan las hojas de producción.
Se convierten a `None` sin avisar, por decisión del origen: una celda con `#REF!` es un
dato ausente, no una fila inválida — descartarla perdería toda la fila.

Portado literal salvo los tipos (mypy strict) y el nombre del módulo.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

# Valores de Excel que se tratan como nulos.
NOISE: frozenset[str] = frozenset(
    {
        "",
        "#REF!",
        "#DIV/0!",
        "#N/A",
        "#VALUE!",
        "#NAME?",
        "(en blanco)",
        "(EN BLANCO)",
    }
)

_SOLO_DIGITOS_8 = re.compile(r"\d{8}")


def s(valor: Any) -> str | None:
    """Texto limpio, o `None` si la celda es ruido o está vacía."""
    if valor is None:
        return None
    texto = str(valor).strip()
    return None if texto in NOISE else texto


def num(valor: Any) -> float | None:
    """Número, o `None` si la celda es ruido o no es numérica.

    Los `int`/`float` se devuelven tal cual (sin pasar por `str`) para no perder
    precisión en volúmenes grandes.

    Nota sobre `bool`: en Python `isinstance(True, int)` es verdadero, así que una celda
    con TRUE/FALSE sale como 1.0/0.0. Se conserva ese comportamiento del origen a
    propósito — convertirlo a `None` "por limpieza" transformaría un flag verdadero en
    dato ausente, alterando en silencio lo que se guarda.
    """
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    if texto in NOISE:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def to_date(valor: Any) -> dt.date | None:
    """Fecha desde `int` YYYYMMDD, `datetime`, `date` o ISO. `None` si no es válida.

    El `0` se trata como vacío a propósito: las hojas usan `0` donde no hay fecha, y un
    `date` construido desde 0 reventaría.
    """
    if valor is None or valor == "" or valor == 0:
        return None
    if isinstance(valor, dt.datetime):
        return valor.date()
    if isinstance(valor, dt.date):
        return valor
    texto = str(valor).strip()
    if texto in NOISE:
        return None
    # "20240930.0" -> "20240930": Excel devuelve enteros como float al leerlos.
    texto = texto.split(".")[0]
    if _SOLO_DIGITOS_8.fullmatch(texto):
        try:
            return dt.date(int(texto[:4]), int(texto[4:6]), int(texto[6:8]))
        except ValueError:
            return None
    try:
        return dt.date.fromisoformat(texto[:10])
    except ValueError:
        return None
