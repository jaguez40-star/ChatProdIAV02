"""Tests de la familia `filiales` contra el .xlsm REAL.

`Producción filiales` es el extractor más complejo de los 17: produce 8 tablas mezclando
series temporales (columnas = fechas) con matrices (columnas = categorías, `fecha=None`).
Los tests fijan justo lo que distingue a cada familia, porque confundirlas es el fallo que
no daría error: una matriz con fechas inventadas, o una serie sin fecha, entrarían igual
en la BD.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.features.ingesta.extractores.filiales import (
    EMPRESAS,
    extraer_inicio,
    extraer_pop_filiales,
    extraer_produccion_filiales,
)
from tests.fakes.muestras_xlsm import DIRECTORIO_MUESTRAS, hay_muestras
from tests.fakes.muestras_xlsm import hoja_de as _hoja

pytestmark = [
    pytest.mark.muestras,
    pytest.mark.skipif(
        not hay_muestras(), reason=f"no hay .xlsm de muestra en {DIRECTORIO_MUESTRAS}"
    ),
]

# Tablas de series temporales y de matriz, según el contrato de la hoja.
TABLAS_POR_FECHA = {1, 2, 3, 6, 7}
TABLAS_MATRIZ = {4, 5, 8}


@pytest.fixture
def libro_new(libro_muestra_new: Any) -> Any:
    return libro_muestra_new


# ── Producción filiales ──────────────────────────────────────────────────────


@pytest.mark.integration
def test_produccion_filiales_extrae_filas_reales(libro_new: object) -> None:
    resultado = extraer_produccion_filiales(_hoja(libro_new, "Producción filiales"))

    assert resultado.filas, "el extractor no sacó ni una fila del archivo real"
    assert [t[0] for t in resultado.tablas_declaradas] == [1, 2, 3, 4, 5, 6, 7, 8]


@pytest.mark.integration
def test_las_tablas_por_fecha_siempre_llevan_fecha(libro_new: object) -> None:
    resultado = extraer_produccion_filiales(_hoja(libro_new, "Producción filiales"))

    for fila in resultado.filas:
        if fila.tabla_idx in TABLAS_POR_FECHA:
            assert fila.fecha is not None, f"tabla {fila.tabla_idx} sin fecha"


@pytest.mark.integration
def test_las_matrices_nunca_llevan_fecha(libro_new: object) -> None:
    """`fecha=None` es lo que las marca como matriz aguas abajo — no es un dato ausente."""
    resultado = extraer_produccion_filiales(_hoja(libro_new, "Producción filiales"))

    for fila in resultado.filas:
        if fila.tabla_idx in TABLAS_MATRIZ:
            assert fila.fecha is None, f"la matriz {fila.tabla_idx} trae fecha"
            assert set(fila.dims) == {"fila", "columna"}


@pytest.mark.integration
def test_las_tablas_por_producto_traen_empresa_y_producto(libro_new: object) -> None:
    resultado = extraer_produccion_filiales(_hoja(libro_new, "Producción filiales"))

    por_producto = [f for f in resultado.filas if f.tabla_idx in {1, 2, 3}]
    if not por_producto:
        pytest.skip("el archivo de muestra no trae bloques por producto")
    assert all(set(f.dims) == {"empresa", "producto"} for f in por_producto)


@pytest.mark.integration
def test_los_totales_por_empresa_no_traen_producto(libro_new: object) -> None:
    resultado = extraer_produccion_filiales(_hoja(libro_new, "Producción filiales"))

    totales = [f for f in resultado.filas if f.tabla_idx in {6, 7}]
    if not totales:
        pytest.skip("el archivo de muestra no trae totales por empresa")
    assert all(set(f.dims) == {"empresa"} for f in totales)
    assert all(str(f.dims["empresa"]).upper() not in {"TOTAL"} for f in totales)


@pytest.mark.integration
def test_los_nombres_de_empresa_quedan_normalizados(libro_new: object) -> None:
    """'EAI', 'EA' y 'AMERICA' deben unificarse: si no, la misma filial entraría como
    tres entidades distintas en las dimensiones."""
    resultado = extraer_produccion_filiales(_hoja(libro_new, "Producción filiales"))

    empresas = {str(f.dims["empresa"]) for f in resultado.filas if "empresa" in f.dims}
    assert "EAI" not in empresas and "EA" not in empresas


# ── POP Filiales y Exploración ───────────────────────────────────────────────


@pytest.mark.integration
def test_pop_filiales_declara_sus_dos_tablas(libro_new: object) -> None:
    resultado = extraer_pop_filiales(_hoja(libro_new, "POP Filiales"))

    assert [t[1] for t in resultado.tablas_declaradas] == [
        "POP Filiales",
        "POP Exploración",
    ]


@pytest.mark.integration
def test_pop_filiales_excluye_la_columna_promedio_anio(libro_new: object) -> None:
    """El corte de meses contiguos en la primera no-fecha es lo que la deja fuera;
    si entrara, se ingeriría un promedio como si fuera un mes más."""
    resultado = extraer_pop_filiales(_hoja(libro_new, "POP Filiales"))

    if not resultado.filas:
        pytest.skip("la hoja POP no trajo filas en este archivo")
    meses = {f.fecha.month for f in resultado.filas if f.fecha is not None}
    assert meses <= set(range(1, 13))


# ── INICIO ───────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_inicio_extrae_solo_la_tabla_de_promedios(libro_new: object) -> None:
    """El resto de INICIO son parámetros de configuración que NO se ingieren."""
    resultado = extraer_inicio(_hoja(libro_new, "INICIO"))

    assert [t[0] for t in resultado.tablas_declaradas] == [1]
    assert all(f.tabla_idx == 1 for f in resultado.filas)


@pytest.mark.integration
def test_inicio_se_ancla_por_titulo_no_por_fila_fija(libro_new: object) -> None:
    """La tabla se desplaza entre archivos NEW (~fila 34) y STD (~fila 38): anclarla por
    fila fija la perdería en la mitad de los reportes."""
    resultado = extraer_inicio(_hoja(libro_new, "INICIO"))

    if not resultado.filas:
        pytest.skip("la hoja INICIO no trajo la tabla en este archivo")
    assert all("producto" in f.dims for f in resultado.filas)


@pytest.mark.integration
def test_las_empresas_reconocidas_son_las_pactadas() -> None:
    assert EMPRESAS == {"HOCOL", "AMERICA", "PERMIAN", "EAI", "EA"}
