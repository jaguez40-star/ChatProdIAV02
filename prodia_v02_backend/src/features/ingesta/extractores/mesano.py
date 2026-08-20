"""Extractor de 'NEW MES-AÑO' — el cubo fuente de P50 y POP.

Trece tablas en una sola hoja, repartidas en **dos bloques de columnas** que comparten
estructura pero no posición:

- **A–O**: REAL y PROYECCIÓN (7 tablas). Etiquetas en A (producto/concepto) y B
  (vice/empresa); los meses van en C–N.
- **S–AH**: P50 y POP (6 tablas). Etiquetas en T y U —la columna S es un índice y se
  ignora—; los meses van en V–AG.

Todas las coordenadas están pactadas con el archivo real y verificadas en 3 archivos. La
tabla que las recorre (`_TABLAS_MESANO`) es el corazón del extractor: cada fila define de
dónde sale una de las 13 tablas.

Los valores se ingieren **tal como aparecen**; esta hoja es la fuente de la que otras
derivan, pero aquí no se recalcula nada.
"""

from __future__ import annotations

from typing import Any

from openpyxl.worksheet.worksheet import Worksheet

from src.features.ingesta.celdas import num, s
from src.features.ingesta.extractores.comunes import (
    ResultadoExtractor,
    construir_grid,
    meses_contiguos,
)

_TABLAS_MESANO = [
    (1, "T1 Parámetros calendario (A-O)"),
    (2, "T2 REAL PROMEDIO MES ECP (A-O)"),
    (3, "T3 REAL PROMEDIO MES Filiales (A-O)"),
    (4, "T4 PROYECCIÓN AÑO ECP (A-O)"),
    (5, "T5 PROYECCIÓN AÑO Filiales (A-O)"),
    (6, "T6 POP/PROY EXPLORACIÓN+G.E. (A-O)"),
    (7, "T7 POP Filiales (A-O)"),
    (8, "T8 P50 ECP (S-AH)"),
    (9, "T9 P50 Filiales (S-AH)"),
    (10, "T10 P50 EXPLORACIÓN+G.E. (S-AH)"),
    (11, "T11 POP ECP (S-AH)"),
    (12, "T12 POP Filiales (S-AH)"),
    (13, "T13 POP EXPLORACIÓN+G.E. (S-AH)"),
]

# Entidades de exploración reconocidas en las tablas 6, 10 y 13.
_ENTIDADES_EXPLORACION: frozenset[str] = frozenset({"GON", "GOO", "VEX"})

# Columnas de etiqueta de cada bloque.
_AO_ECP = [(1, "producto"), (2, "vice")]
_AO_FILIALES = [(1, "producto"), (2, "empresa")]
_SAH_ECP = [(20, "producto"), (21, "vice")]
_SAH_FILIALES = [(20, "producto"), (21, "empresa")]

# (tabla, fila_encabezado, fila_inicial, fila_final, columna_inicial_meses, dims, modo)
#
# `modo` distingue tres comportamientos:
#   ""         — dims normales, tomadas de las columnas de etiqueta.
#   "skiphdr"  — el rango incluye la propia fila de encabezado; hay que saltarla.
#   "entidad"  — la fila solo cuenta si nombra una entidad conocida (GON/GOO/VEX o
#                'GRUPO EMPRESARIAL'); el resto del rango se ignora.
_ESPECIFICACIONES: list[tuple[int, int, int, int, int, list[tuple[int, str]], str]] = [
    (1, 7, 6, 10, 3, [(1, "concepto")], "skiphdr"),
    (2, 13, 14, 35, 3, _AO_ECP, ""),
    (3, 39, 40, 47, 3, _AO_FILIALES, ""),
    (4, 59, 60, 81, 3, _AO_ECP, ""),
    (5, 84, 85, 97, 3, _AO_FILIALES, ""),
    (6, 99, 99, 105, 3, [(1, "a"), (2, "b")], "entidad"),
    (7, 112, 113, 116, 3, [(2, "empresa")], ""),
    (8, 8, 9, 27, 22, _SAH_ECP, ""),
    (9, 30, 31, 43, 22, _SAH_FILIALES, ""),
    (10, 46, 46, 52, 22, [(20, "a"), (21, "b")], "entidad"),
    (11, 59, 60, 81, 22, _SAH_ECP, ""),
    (12, 84, 85, 97, 22, _SAH_FILIALES, ""),
    (13, 99, 99, 105, 22, [(20, "a"), (21, "b")], "entidad"),
]


def _entidad_de(etiqueta_a: str | None, etiqueta_b: str | None) -> str | None:
    """Nombre de entidad de una fila de las tablas 6/10/13, o `None` si no la nombra."""
    if etiqueta_b and etiqueta_b.upper() in _ENTIDADES_EXPLORACION:
        return etiqueta_b.upper()
    if etiqueta_a and "GRUPO EMP" in etiqueta_a.upper():
        return "GRUPO EMPRESARIAL"
    if etiqueta_b and "GRUPO EMP" in etiqueta_b.upper():
        return "GRUPO EMPRESARIAL"
    return None


def extraer_mesano(hoja: Worksheet) -> ResultadoExtractor:
    """Hoja 'NEW MES-AÑO' → 13 tablas mensuales.

    Los meses de cada tabla salen de su propia fila de encabezado, y el corte en la
    primera no-fecha **excluye la columna 'Promedio Año'** (O y AH), que es un derivado.

    Las filas de total y subtotal se incluyen: llegan con la columna B (o U) vacía, así
    que sus `dims` quedan solo con el producto o concepto y no colisionan con el detalle.

    'REAL PROMEDIO MES' acumula distinto número de meses según el año del archivo; es una
    variación legítima, no un error.

    Quedan fuera los bloques de GRÁFICAS, META AÑO y la serie diaria: viven en otras
    columnas y no forman parte del cubo.
    """
    grid, _ = construir_grid(hoja)
    resultado = ResultadoExtractor(tablas_declaradas=list(_TABLAS_MESANO))
    etiquetas = dict(_TABLAS_MESANO)

    for (
        indice,
        cabecera,
        desde,
        hasta,
        columna_meses,
        columnas_dim,
        modo,
    ) in _ESPECIFICACIONES:
        meses = meses_contiguos(grid, cabecera, columna_meses)
        if not meses:
            continue

        for fila in range(desde, hasta + 1):
            if modo == "skiphdr" and fila == cabecera:
                continue

            dims: dict[str, Any]
            if modo == "entidad":
                entidad = _entidad_de(
                    s(grid.get((fila, columnas_dim[0][0]))),
                    s(grid.get((fila, columnas_dim[1][0]))),
                )
                if entidad is None:
                    continue
                dims = {"entidad": entidad}
            else:
                dims = {}
                for columna, nombre in columnas_dim:
                    valor_dim = s(grid.get((fila, columna)))
                    if valor_dim is not None:
                        dims[nombre] = valor_dim
                if not dims:
                    continue

            for columna, fecha in meses:
                valor = num(grid.get((fila, columna)))
                if valor is None:
                    continue
                resultado.agregar(indice, etiquetas[indice], dims, fecha, valor)

    return resultado
