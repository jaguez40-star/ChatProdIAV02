"""Extractores de las hojas P50 — portados literalmente del sistema viejo.

Dos hojas:

- `P50 Quemado <año> ECP y Filiales` → 2 tablas (quemado, filiales).
- `P50 Acumulado` → 4 tablas (P50 ECP/FILIALES + RETO CORP ECP/FILIALES).

Ambas leen **por posición**: las coordenadas están pactadas con el archivo real, no
deducidas. Cambiarlas "por claridad" rompe la extracción sin producir ningún error —
simplemente saldrían cero filas.
"""

from __future__ import annotations

from openpyxl.worksheet.worksheet import Worksheet

from src.features.ingesta.celdas import num, s
from src.features.ingesta.extractores.comunes import (
    ResultadoExtractor,
    construir_grid,
    es_total,
    filas_con_titulo,
    filas_que_empiezan_por,
    meses_contiguos,
)


def extraer_p50_quemado(hoja: Worksheet) -> ResultadoExtractor:
    """Hoja 'P50 Quemado <año> ECP y Filiales' → 2 tablas.

    Tabla 1 = quemado (escenario/producto/vice/activos/area); Tabla 2 = filiales
    (producto/empresa). Meses contiguos —corta antes de la tabla VR/GER—; descarta
    subtotales y la fila 'Promedio Año'.
    """
    grid, ultima_fila = construir_grid(hoja)
    resultado = ResultadoExtractor(tablas_declaradas=[(1, "Tabla 1"), (2, "Tabla 2")])

    # ── Tabla 1: encabezado en la fila 2, meses desde la columna F ───────────
    meses_t1 = meses_contiguos(grid, 2, 6)
    for fila in range(3, ultima_fila + 1):
        area = grid.get((fila, 5))
        if area is None or es_total(area):
            continue
        dims = {
            "escenario": s(grid.get((fila, 1))),
            "producto": s(grid.get((fila, 2))),
            "vice": s(grid.get((fila, 3))),
            "activos": s(grid.get((fila, 4))),
            "area": s(area),
        }
        for columna, fecha in meses_t1:
            valor = num(grid.get((fila, columna)))
            if valor is None:
                continue
            resultado.agregar(1, "Tabla 1", dims, fecha, valor)

    # ── Tabla 2: anclada al título 'P50 filiales', esté donde esté ───────────
    titulo = next(
        (
            (fila, columna)
            for (fila, columna), valor in grid.items()
            if isinstance(valor, str) and valor.strip().lower() == "p50 filiales"
        ),
        None,
    )
    if titulo is not None:
        fila_titulo, columna_titulo = titulo
        encabezado = fila_titulo + 1
        meses_t2 = meses_contiguos(grid, encabezado, columna_titulo + 3)
        for fila in range(encabezado + 1, ultima_fila + 1):
            empresa = grid.get((fila, columna_titulo + 2))
            if empresa is None:
                continue
            producto = grid.get((fila, columna_titulo))
            if es_total(producto):
                continue
            dims = {"producto": s(producto), "empresa": s(empresa)}
            for columna, fecha in meses_t2:
                valor = num(grid.get((fila, columna)))
                if valor is None:
                    continue
                resultado.agregar(2, "Tabla 2", dims, fecha, valor)

    return resultado


def extraer_p50_acumulado(hoja: Worksheet) -> ResultadoExtractor:
    """Hoja 'P50 Acumulado' → 4 tablas de promedios ACUMULADOS ya calculados.

    **No recalcula**: toma los valores cacheados tal como aparecen (decisión del usuario,
    2026-06-29). La hoja es un derivado de 'NEW MES-AÑO', pero por requerimiento se
    ingieren sus cifras tal cual.

    La hoja tiene dos secciones (verificado en 5 archivos, ene–may 2026):

    - Sección 'P50' base: Tabla 1 (P50 ECP, título 'P50') y Tabla 2 (P50 FILIALES).
    - Sección 'RETO CORPORATIVO' — el «compromiso» (decisión del usuario, 2026-07-26):
      Tabla 3 (RETO CORP ECP) y Tabla 4 (RETO CORP FILIALES), con los mismos títulos.

    El acotamiento por el **título siguiente** es lo que arregla un bug real: antes, la
    Tabla 2 arrastraba el bloque RETO-ECP y conflaba Filiales con RETO-ECP bajo el mismo
    producto, provocando colisión `(dims, fecha)` con last-wins en la BD.

    Los meses salen del encabezado contiguo desde la columna C: `to_date` corta en la
    primera no-fecha, lo que excluye la columna 'PROMEDIO ACUMULADO'.

    Queda fuera a propósito el sub-bloque 'RETO 761K' (presente en 1 de 5 archivos, sin
    etiquetas de producto): no es el compromiso pedido, y el acotamiento lo descarta solo.
    """
    grid, ultima_fila = construir_grid(hoja)
    declaradas = [
        (1, "Tabla 1 (P50 ECP)"),
        (2, "Tabla 2 (P50 FILIALES)"),
        (3, "Tabla 3 (RETO CORP ECP)"),
        (4, "Tabla 4 (RETO CORP FILIALES)"),
    ]
    resultado = ResultadoExtractor(tablas_declaradas=declaradas)

    filas_p50 = filas_con_titulo(grid, "P50")
    filas_filiales = filas_con_titulo(grid, "P50 FILIALES")
    filas_reto = filas_que_empiezan_por(grid, "RETO")
    # Fila donde empieza la sección RETO CORPORATIVO; si no existe, todo es sección base.
    inicio_reto = min(filas_reto) if filas_reto else ultima_fila + 1

    todos_los_titulos = sorted(set(filas_p50) | set(filas_filiales) | set(filas_reto))

    def siguiente_titulo(desde: int) -> int:
        return next((t for t in todos_los_titulos if t > desde), ultima_fila + 1)

    def emitir(indice: int, etiqueta: str, fila_titulo: int | None) -> None:
        if fila_titulo is None:
            return
        encabezado = fila_titulo + 1
        meses = meses_contiguos(grid, encabezado, 3)
        if not meses:
            return
        fin = siguiente_titulo(encabezado)  # se detiene ANTES del siguiente título
        for fila in range(encabezado + 1, fin):
            producto = s(grid.get((fila, 1)))
            if not producto:
                continue
            dims = {"producto": producto}
            for columna, fecha in meses:
                valor = num(grid.get((fila, columna)))
                if valor is None:
                    continue
                resultado.agregar(indice, etiqueta, dims, fecha, valor)

    emitir(
        1, "Tabla 1 (P50 ECP)", next((f for f in filas_p50 if f < inicio_reto), None)
    )
    emitir(
        2,
        "Tabla 2 (P50 FILIALES)",
        next((f for f in filas_filiales if f < inicio_reto), None),
    )
    emitir(
        3,
        "Tabla 3 (RETO CORP ECP)",
        next((f for f in filas_p50 if f > inicio_reto), None),
    )
    emitir(
        4,
        "Tabla 4 (RETO CORP FILIALES)",
        next((f for f in filas_filiales if f > inicio_reto), None),
    )
    return resultado
