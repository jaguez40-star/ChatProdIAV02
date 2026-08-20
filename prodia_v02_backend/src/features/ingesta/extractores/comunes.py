"""Contrato y helpers compartidos por los 17 extractores de hoja.

**El contrato.** En el sistema viejo había DOS formas de retorno: unos extractores
devolvían `list[dict]` y otros `{"rows": [...], "tablas": DECLARED}`, y el despachador
decidía con un `isinstance(res, dict)`. Aquí todos devuelven `ResultadoExtractor`, así que
el `isinstance` desaparece y mypy verifica la forma en cada extractor.

`tablas_declaradas` importa más de lo que parece: es la lista de tablas que la hoja
*debería* producir, y se emite **aunque salgan con cero filas**. Sin ella, una tabla vacía
sería indistinguible de una tabla inexistente y el cambio de layout de una hoja pasaría
inadvertido (G5 — el fallo silencioso que el origen no detectaba).

`construir_grid` carga la hoja entera en un diccionario `{(fila, columna): valor}`. Es
memoria a cambio de acceso aleatorio: los extractores leen por posiciones pactadas y
saltan hacia adelante y atrás, cosa que `iter_rows` no permite. El tope de filas evita que
una hoja RAW enorme agote la RAM.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Protocol

from openpyxl.worksheet.worksheet import Worksheet

from src.features.ingesta.celdas import to_date

# Tope de filas que se cargan al grid. Heredado del origen: las hojas modeladas caben
# de sobra, y las RAW (que sí superan esto) tienen sus propios extractores.
MAX_FILAS_GRID = 250

# {(fila, columna): valor} — coordenadas 1-based, como las muestra Excel.
Grid = dict[tuple[int, int], Any]


@dataclass(frozen=True)
class FilaExtraida:
    """Una celda con significado: sus dimensiones, su fecha y su valor.

    `fecha` es `None` en las tablas matriciales (fila × columna), y eso NO es un dato
    inválido: es lo que las distingue de las series temporales aguas abajo.
    """

    tabla_idx: int
    tabla_label: str
    dims: dict[str, Any]
    fecha: dt.date | None
    valor: float | str | None


@dataclass
class ResultadoExtractor:
    """Lo que devuelve todo extractor: las filas y las tablas que declaró producir."""

    filas: list[FilaExtraida] = field(default_factory=list)
    tablas_declaradas: list[tuple[int, str]] = field(default_factory=list)

    def agregar(
        self,
        tabla_idx: int,
        tabla_label: str,
        dims: dict[str, Any],
        fecha: dt.date | None,
        valor: float | str | None,
    ) -> None:
        self.filas.append(FilaExtraida(tabla_idx, tabla_label, dims, fecha, valor))

    def tablas_vacias(self) -> list[tuple[int, str]]:
        """Tablas declaradas que no produjeron ni una fila — la señal de G5."""
        con_filas = {f.tabla_idx for f in self.filas}
        return [
            (idx, etq) for idx, etq in self.tablas_declaradas if idx not in con_filas
        ]


class Extractor(Protocol):
    """Firma que cumplen los 17."""

    def __call__(self, hoja: Worksheet) -> ResultadoExtractor: ...


def construir_grid(
    hoja: Worksheet, max_filas: int = MAX_FILAS_GRID
) -> tuple[Grid, int]:
    """Carga la hoja en `{(fila, columna): valor}`, omitiendo celdas vacías.

    Devuelve también la última fila con contenido: los extractores la usan como límite
    de sus barridos en vez de recorrer hasta el final de la hoja.
    """
    grid: Grid = {}
    ultima_fila = 0
    for fila, valores in enumerate(hoja.iter_rows(values_only=True), start=1):
        for columna, valor in enumerate(valores, start=1):
            if valor is not None and str(valor).strip() != "":
                grid[(fila, columna)] = valor
                if fila > ultima_fila:
                    ultima_fila = fila
        if fila > max_filas:
            break
    return grid, ultima_fila


def meses_contiguos(
    grid: Grid, fila_encabezado: int, columna_inicial: int
) -> list[tuple[int, dt.date]]:
    """Columnas de mes CONTIGUAS desde `columna_inicial`; corta en la primera no-fecha.

    Crítico (auditoría A4 del origen): el corte en la primera no-fecha es lo que evita
    cruzar a la tabla VR/GER, que comparte fila de encabezado con la tabla P50. Sin él,
    columnas de otra tabla entrarían como si fueran meses de esta.
    """
    columnas: list[tuple[int, dt.date]] = []
    columna = columna_inicial
    while True:
        fecha = to_date(grid.get((fila_encabezado, columna)))
        if fecha is None:
            break
        columnas.append((columna, fecha))
        columna += 1
    return columnas


def es_total(valor: Any) -> bool:
    """True si la celda es una fila de subtotal ('Total …'), que no se ingiere."""
    return valor is not None and str(valor).strip().lower().startswith("total")


def filas_con_titulo(grid: Grid, titulo: str, columna: int = 1) -> list[int]:
    """Filas cuya celda en `columna` es exactamente `titulo` (sin distinguir mayúsculas)."""
    objetivo = titulo.strip().upper()
    return sorted(
        fila
        for (fila, col), valor in grid.items()
        if col == columna
        and isinstance(valor, str)
        and valor.strip().upper() == objetivo
    )


def filas_que_empiezan_por(grid: Grid, prefijo: str, columna: int = 1) -> list[int]:
    """Filas cuya celda en `columna` empieza por `prefijo` (sin distinguir mayúsculas)."""
    objetivo = prefijo.strip().upper()
    return sorted(
        fila
        for (fila, col), valor in grid.items()
        if col == columna
        and isinstance(valor, str)
        and valor.strip().upper().startswith(objetivo)
    )
