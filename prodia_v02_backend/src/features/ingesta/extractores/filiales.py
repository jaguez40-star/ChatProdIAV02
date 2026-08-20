"""Extractores de las hojas de filiales — portados literalmente del sistema viejo.

Tres hojas:

- `Producción filiales` → 8 tablas. La más compleja de las 17: mezcla dos familias de
  tabla en la misma hoja (series por fecha y matrices por categoría).
- `POP Filiales y Exploración` → 2 tablas mensuales.
- `INICIO` → 1 tabla (lo único de esa hoja que se ingiere).

`Producción filiales` es el único extractor que trabaja sobre una **lista de listas**
(0-based) en vez del grid `{(fila, columna): valor}` (1-based) que usan los demás: recorre
la hoja secuencialmente buscando bloques, y necesita el orden. Se conserva esa estructura
porque cambiarla obligaría a recalcular todos los índices, que es justo donde se cuelan
los errores silenciosos.
"""

from __future__ import annotations

import re
from typing import Any

from openpyxl.worksheet.worksheet import Worksheet

from src.features.ingesta.celdas import num, s
from src.features.ingesta.celdas import to_date as a_fecha
from src.features.ingesta.extractores.comunes import (
    ResultadoExtractor,
    construir_grid,
    meses_contiguos,
)
from src.features.ingesta.transforms import norm_emp, norm_prod, split_label

# Empresas reconocidas a nivel de fila (las variantes se unifican con `norm_emp`).
EMPRESAS: frozenset[str] = frozenset({"HOCOL", "AMERICA", "PERMIAN", "EAI", "EA"})

# Bloques diarios de la familia A → qué tabla alimenta cada uno.
_TABLAS_POR_PRODUCTO: dict[str, tuple[int, str]] = {
    "REAL": (1, "Tabla 1 (REAL)"),
    "PROGRAMA": (2, "Tabla 2 (PROGRAMA)"),
    "PROYECC": (3, "Tabla 3 (PROYECCIÓN)"),
}
_TABLAS_POR_EMPRESA: dict[str, tuple[int, str]] = {
    "REAL": (6, "Tabla 6 (REAL total empresa)"),
    "PROGRAMA": (7, "Tabla 7 (PROGRAMA total empresa)"),
}

_TABLAS_FILIALES = [
    (1, "Tabla 1 (REAL)"),
    (2, "Tabla 2 (PROGRAMA)"),
    (3, "Tabla 3 (PROYECCIÓN)"),
    (4, "Tabla 4 (FILIALES mes/semana)"),
    (5, "Tabla 5 (Seguimiento semanal)"),
    (6, "Tabla 6 (REAL total empresa)"),
    (7, "Tabla 7 (PROGRAMA total empresa)"),
    (8, "Tabla 8 (Desempeño P50)"),
]


def _limpiar(valor: Any) -> str:
    """Texto normalizado a espacios simples; cadena vacía si la celda es ruido."""
    texto = s(valor)
    return re.sub(r"\s+", " ", texto) if texto else ""


def _rellenar_hacia_delante(secuencia: list[Any]) -> list[str]:
    """Propaga el último valor no vacío — las cabeceras combinadas de Excel dejan
    huecos en las celdas siguientes al texto."""
    salida: list[str] = []
    ultimo = ""
    for valor in secuencia:
        limpio = _limpiar(valor)
        if limpio:
            ultimo = limpio
        salida.append(ultimo)
    return salida


def extraer_produccion_filiales(hoja: Worksheet) -> ResultadoExtractor:
    """Hoja 'Producción filiales' → 8 tablas.

    **Familia A — columnas = FECHAS**: tablas 1 REAL, 2 PROGRAMA y 3 PROYECCIÓN
    (empresa × producto), y 6 REAL y 7 PROGRAMA (totales por empresa, sin producto).
    La tabla 7 trae el encabezado de fechas vacío y **reutiliza las de la tabla 6** — de
    ahí `ultimas_fechas_empresa`.

    **Familia B — columnas = CATEGORÍAS** (matriz, `fecha=None`, dims `{fila, columna}`):
    tablas 4 FILIALES mes/semana, 5 Seguimiento semanal y 8 Desempeño P50.

    Layout verificado estable con anclajes idénticos en 4 archivos de muestra.
    """
    grid = [list(fila) for fila in hoja.iter_rows(values_only=True)]
    total_filas = len(grid)
    resultado = ResultadoExtractor(tablas_declaradas=list(_TABLAS_FILIALES))

    def celda(fila: int, columna: int) -> Any:
        if 0 <= fila < total_filas and 0 <= columna < len(grid[fila]):
            return grid[fila][columna]
        return None

    # ── Familia A: bloques diarios (encabezado 'EMPRESA' con fechas) ─────────
    ultimas_fechas_empresa: list[Any] | None = None
    fila = 0
    while fila < total_filas:
        titulo = _limpiar(celda(fila, 0)).upper()
        if titulo == "REAL":
            base = "REAL"
        elif titulo == "PROGRAMA":
            base = "PROGRAMA"
        elif titulo.startswith("PROYECC"):
            base = "PROYECC"
        else:
            fila += 1
            continue

        # El encabezado de fechas ('EMPRESA') va debajo del título, tras filas vacías.
        cabecera = fila + 1
        while cabecera < total_filas and _limpiar(celda(cabecera, 0)) == "":
            cabecera += 1
        if _limpiar(celda(cabecera, 0)).upper() != "EMPRESA":
            fila += 1
            continue  # no es un bloque diario (p. ej. el título 'FILIALES')

        fechas: list[Any] | None = [a_fecha(v) for v in grid[cabecera][1:]]
        if fechas is not None and not any(f is not None for f in fechas):
            fechas = None  # encabezado vacío (tabla 7) → se reutilizan las anteriores

        actual = cabecera + 1
        while actual < total_filas:
            etiqueta = _limpiar(celda(actual, 0))
            etiqueta_mayus = etiqueta.upper()
            if (
                etiqueta == ""
                or etiqueta_mayus == "EMPRESA"
                or etiqueta_mayus in ("REAL", "PROGRAMA")
                or etiqueta_mayus.startswith("PROYECC")
            ):
                break
            if etiqueta_mayus.startswith("TOTAL"):
                actual += 1
                continue

            empresa_cruda, producto_crudo = split_label(etiqueta)
            if empresa_cruda and producto_crudo:
                # Nivel producto → tablas 1/2/3.
                empresa = norm_emp(empresa_cruda)
                producto = norm_prod(producto_crudo)
                if empresa and producto and fechas:
                    indice, etiqueta_tabla = _TABLAS_POR_PRODUCTO[base]
                    for posicion, valor_celda in enumerate(grid[actual][1:]):
                        fecha = fechas[posicion] if posicion < len(fechas) else None
                        valor = num(valor_celda)
                        if fecha is None or valor is None:
                            continue
                        resultado.agregar(
                            indice,
                            etiqueta_tabla,
                            {"empresa": empresa, "producto": producto},
                            fecha,
                            valor,
                        )
            elif etiqueta_mayus in EMPRESAS and base in _TABLAS_POR_EMPRESA:
                # Nivel empresa (total) → tablas 6/7.
                empresa = norm_emp(etiqueta)
                fechas_usadas = fechas if fechas else ultimas_fechas_empresa
                if empresa and fechas_usadas:
                    if fechas:
                        ultimas_fechas_empresa = fechas
                    indice, etiqueta_tabla = _TABLAS_POR_EMPRESA[base]
                    for posicion, valor_celda in enumerate(grid[actual][1:]):
                        fecha = (
                            fechas_usadas[posicion]
                            if posicion < len(fechas_usadas)
                            else None
                        )
                        valor = num(valor_celda)
                        if fecha is None or valor is None:
                            continue
                        resultado.agregar(
                            indice, etiqueta_tabla, {"empresa": empresa}, fecha, valor
                        )
            actual += 1
        fila = actual

    # ── Familia B: matrices (fecha=None, dims {fila, columna}) ──────────────
    def emitir_matriz(
        indice: int,
        etiqueta_tabla: str,
        columna_etiqueta: int,
        fila_metricas: int,
        periodos: list[str] | None,
        fila_inicial: int,
    ) -> None:
        metricas = (
            [_limpiar(v) for v in grid[fila_metricas]]
            if 0 <= fila_metricas < total_filas
            else []
        )
        columnas: dict[int, str] = {}
        for posicion, metrica in enumerate(metricas):
            if posicion == columna_etiqueta or not metrica:
                continue
            periodo = (
                periodos[posicion] if periodos and posicion < len(periodos) else ""
            )
            columnas[posicion] = f"{periodo} {metrica}".strip() if periodo else metrica

        actual = fila_inicial
        while actual < total_filas:
            nombre_fila = _limpiar(celda(actual, columna_etiqueta))
            nombre_mayus = nombre_fila.upper()
            if nombre_mayus not in EMPRESAS and nombre_mayus != "TOTAL":
                break
            for posicion, nombre_columna in columnas.items():
                valor = num(celda(actual, posicion))
                if valor is None:
                    continue
                resultado.agregar(
                    indice,
                    etiqueta_tabla,
                    {"fila": nombre_fila, "columna": nombre_columna},
                    None,
                    valor,
                )
            if nombre_mayus == "TOTAL":
                break  # TOTAL cierra el bloque de la matriz
            actual += 1

    for fila in range(total_filas):
        col_a = _limpiar(celda(fila, 0)).upper()
        col_b = _limpiar(celda(fila, 1)).upper()
        texto_fila = " ".join(_limpiar(c).upper() for c in grid[fila])

        if col_a == "FILIALES" and "MES" in col_b:
            emitir_matriz(
                4,
                "Tabla 4 (FILIALES mes/semana)",
                0,
                fila + 2,
                _rellenar_hacia_delante(grid[fila + 1]),
                fila + 3,
            )
        if "SEGUIMIENTO" in col_b:
            periodos = _rellenar_hacia_delante(
                [
                    (
                        v
                        if ("AL " in _limpiar(v).upper() or _limpiar(v)[:1].isdigit())
                        else ""
                    )
                    for v in grid[fila]
                ]
            )
            emitir_matriz(
                5, "Tabla 5 (Seguimiento semanal)", 0, fila + 1, periodos, fila + 2
            )
        if "DESEMPE" in texto_fila:
            emitir_matriz(8, "Tabla 8 (Desempeño P50)", 3, fila + 1, None, fila + 2)

    return resultado


def extraer_pop_filiales(hoja: Worksheet) -> ResultadoExtractor:
    """Hoja 'POP Filiales y Exploración' → 2 tablas mensuales.

    Reporte derivado: **no recalcula**, ingiere los valores cacheados tal cual.

    - T1 'POP Filiales' (filas 3-19, cabecera fila 2): dims producto(B) × empresa(C).
    - T2 'POP Exploración' (filas 23-26, cabecera fila 22): dims vr(B) × ger(C).

    Los meses salen contiguos desde la columna D; el corte en la primera no-fecha
    **excluye la columna 'Promedio Año'**. Los subtotales sí se incluyen: llegan con la
    columna C vacía, así que sus dims quedan sin la segunda clave y no colisionan.
    """
    grid, _ = construir_grid(hoja)
    declaradas = [(1, "POP Filiales"), (2, "POP Exploración")]
    etiquetas = dict(declaradas)
    resultado = ResultadoExtractor(tablas_declaradas=declaradas)

    # (tabla, fila_cabecera, fila_inicial, fila_final, nombre dim B, nombre dim C)
    especificaciones = [
        (1, 2, 3, 19, "producto", "empresa"),
        (2, 22, 23, 26, "vr", "ger"),
    ]
    for indice, cabecera, desde, hasta, dim_b, dim_c in especificaciones:
        meses = meses_contiguos(grid, cabecera, 4)
        if not meses:
            continue
        for fila in range(desde, hasta + 1):
            principal = s(grid.get((fila, 2)))
            if principal is None:
                continue
            dims: dict[str, Any] = {dim_b: principal}
            secundaria = s(grid.get((fila, 3)))
            if secundaria is not None:
                dims[dim_c] = secundaria
            for columna, fecha in meses:
                valor = num(grid.get((fila, columna)))
                if valor is None:
                    continue
                resultado.agregar(indice, etiquetas[indice], dims, fecha, valor)

    return resultado


def extraer_inicio(hoja: Worksheet) -> ResultadoExtractor:
    """Hoja 'INICIO' → 1 tabla: 'REAL PROMEDIO MES (YTD) Filiales'.

    Es el único dato de esa hoja que se ingiere; el resto son parámetros y lookups de
    configuración. Se ancla **por título**, no por fila fija, porque la tabla se desplaza
    entre archivos NEW (~fila 34) y STD (~fila 38).
    """
    grid, ultima_fila = construir_grid(hoja)
    declaradas = [(1, "REAL PROMEDIO MES (YTD) Filiales")]
    resultado = ResultadoExtractor(tablas_declaradas=declaradas)

    fila_titulo = None
    for fila in range(1, ultima_fila + 1):
        encabezado_fila = s(grid.get((fila, 1)))
        if encabezado_fila and encabezado_fila.upper().startswith(
            "REAL PROMEDIO MES (YTD) FILIALES"
        ):
            fila_titulo = fila
            break
    if fila_titulo is None:
        return resultado

    cabecera = fila_titulo + 1
    meses = meses_contiguos(grid, cabecera, 3)
    fila = cabecera + 1
    while fila <= ultima_fila and s(grid.get((fila, 1))) is not None:
        producto = s(grid.get((fila, 1)))
        dims: dict[str, Any] = {"producto": producto}
        empresa = s(grid.get((fila, 2)))
        if empresa is not None:
            dims["empresa"] = empresa
        for columna, fecha in meses:
            valor = num(grid.get((fila, columna)))
            if valor is not None:
                resultado.agregar(
                    1, "REAL PROMEDIO MES (YTD) Filiales", dims, fecha, valor
                )
        fila += 1

    return resultado
