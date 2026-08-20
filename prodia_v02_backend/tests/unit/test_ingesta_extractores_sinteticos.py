"""Tests de extractores con hojas sintéticas — los que SÍ corren en CI.

Complementan a los de `-m muestras`: aquellos verifican que las posiciones pactadas son
correctas contra el `.xlsm` real; estos verifican que la lógica funciona, y lo hacen sin
depender de archivos externos, que es lo que permite que cuenten para la cobertura de CI
(hallazgo H5 del plan).

Cada hoja replica el andamiaje mínimo que el extractor busca: la fila de encabezado con
sus fechas, la columna de anclaje y un par de filas de datos.
"""

from __future__ import annotations

import datetime as dt

import pytest

from src.features.ingesta.extractores.comunes import (
    construir_grid,
    es_total,
    filas_con_titulo,
    filas_que_empiezan_por,
    meses_contiguos,
)
from src.features.ingesta.extractores.filiales import (
    extraer_inicio,
    extraer_pop_filiales,
    extraer_produccion_filiales,
)
from src.features.ingesta.extractores.p50 import (
    extraer_p50_acumulado,
    extraer_p50_quemado,
)
from tests.fakes.hoja_sintetica import hoja_desde_celdas, hoja_desde_filas

ENE = dt.date(2026, 1, 1)
FEB = dt.date(2026, 2, 1)


# ── Helpers de comunes.py ────────────────────────────────────────────────────


@pytest.mark.unit
def test_el_grid_omite_las_celdas_vacias() -> None:
    hoja = hoja_desde_filas([["a", None, "  "], [None, "b"]])

    grid, ultima_fila = construir_grid(hoja)

    assert grid == {(1, 1): "a", (2, 2): "b"}
    assert ultima_fila == 2


@pytest.mark.unit
def test_el_grid_respeta_su_tope_de_filas() -> None:
    """Sin tope, una hoja RAW enorme agotaría la memoria."""
    hoja = hoja_desde_filas([[f"fila-{i}"] for i in range(1, 60)])

    _, ultima_fila = construir_grid(hoja, max_filas=10)

    assert ultima_fila <= 11


@pytest.mark.unit
def test_los_meses_contiguos_cortan_en_la_primera_no_fecha() -> None:
    """Regla A4: el corte evita cruzar a la tabla vecina que comparte encabezado."""
    hoja = hoja_desde_celdas(
        {(1, 3): ENE, (1, 4): FEB, (1, 5): "Promedio Año", (1, 6): dt.date(2026, 3, 1)}
    )
    grid, _ = construir_grid(hoja)

    meses = meses_contiguos(grid, 1, 3)

    assert [c for c, _ in meses] == [3, 4]  # se detiene antes de 'Promedio Año'
    assert [f for _, f in meses] == [ENE, FEB]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("Total", True),
        ("TOTAL VDP", True),
        ("  total x", True),
        ("Castilla", False),
        (None, False),
    ],
)
def test_reconoce_las_filas_de_subtotal(valor: object, esperado: bool) -> None:
    assert es_total(valor) is esperado


@pytest.mark.unit
def test_localiza_titulos_exactos_y_por_prefijo() -> None:
    hoja = hoja_desde_celdas(
        {(2, 1): "P50", (5, 1): "P50 FILIALES", (9, 1): "RETO CORPORATIVO"}
    )
    grid, _ = construir_grid(hoja)

    assert filas_con_titulo(grid, "P50") == [2]  # exacto: no arrastra 'P50 FILIALES'
    assert filas_que_empiezan_por(grid, "RETO") == [9]


# ── P50 Quemado ──────────────────────────────────────────────────────────────


def _hoja_p50_quemado() -> object:
    """Encabezado de meses en la fila 2 desde la columna F; datos desde la fila 3."""
    return hoja_desde_celdas(
        {
            (2, 6): ENE,
            (2, 7): FEB,
            (3, 1): "REAL", (3, 2): "CRUDO", (3, 3): "VPR", (3, 4): "CASTILLA",
            (3, 5): "ORIENTE", (3, 6): 100.0, (3, 7): 110.0,
            (4, 1): "REAL", (4, 2): "CRUDO", (4, 3): "VPR", (4, 4): "CASTILLA",
            (4, 5): "Total oriente", (4, 6): 999.0,
        }
    )  # fmt: skip


@pytest.mark.unit
def test_p50_quemado_extrae_con_sus_cinco_dimensiones() -> None:
    resultado = extraer_p50_quemado(_hoja_p50_quemado())  # type: ignore[arg-type]

    filas = [f for f in resultado.filas if f.tabla_idx == 1]
    assert len(filas) == 2  # dos meses de la fila válida
    assert set(filas[0].dims) == {"escenario", "producto", "vice", "activos", "area"}
    assert filas[0].valor == 100.0
    assert filas[0].fecha == ENE


@pytest.mark.unit
def test_p50_quemado_descarta_la_fila_de_subtotal() -> None:
    resultado = extraer_p50_quemado(_hoja_p50_quemado())  # type: ignore[arg-type]

    assert 999.0 not in [f.valor for f in resultado.filas]


@pytest.mark.unit
def test_p50_quemado_declara_sus_tablas_aunque_no_haya_datos() -> None:
    """Una hoja sin datos debe seguir declarando sus tablas (G5)."""
    resultado = extraer_p50_quemado(hoja_desde_celdas({(1, 1): "vacía"}))  # type: ignore[arg-type]

    assert [t[0] for t in resultado.tablas_declaradas] == [1, 2]
    assert [t[0] for t in resultado.tablas_vacias()] == [1, 2]


@pytest.mark.unit
def test_p50_quemado_extrae_la_tabla_de_filiales() -> None:
    hoja = hoja_desde_celdas(
        {
            (10, 2): "P50 filiales",
            (11, 5): ENE,
            (12, 2): "CRUDO", (12, 4): "Hocol", (12, 5): 55.0,
        }
    )  # fmt: skip

    resultado = extraer_p50_quemado(hoja)  # type: ignore[arg-type]

    filiales = [f for f in resultado.filas if f.tabla_idx == 2]
    assert len(filiales) == 1
    assert filiales[0].dims == {"producto": "CRUDO", "empresa": "Hocol"}


# ── P50 Acumulado ────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_p50_acumulado_separa_la_seccion_base_de_la_de_reto() -> None:
    """El bug que esto previene: sin acotar por el título siguiente, la tabla de
    filiales arrastraba el bloque RETO y ambos colisionaban en (dims, fecha)."""
    hoja = hoja_desde_celdas(
        {
            (1, 1): "P50", (2, 3): ENE, (3, 1): "CRUDO", (3, 3): 10.0,
            (5, 1): "P50 FILIALES", (6, 3): ENE, (7, 1): "CRUDO", (7, 3): 20.0,
            (9, 1): "RETO CORPORATIVO",
            (11, 1): "P50", (12, 3): ENE, (13, 1): "CRUDO", (13, 3): 30.0,
            (15, 1): "P50 FILIALES", (16, 3): ENE, (17, 1): "CRUDO", (17, 3): 40.0,
        }
    )  # fmt: skip

    resultado = extraer_p50_acumulado(hoja)  # type: ignore[arg-type]

    por_tabla = {f.tabla_idx: f.valor for f in resultado.filas}
    assert por_tabla == {1: 10.0, 2: 20.0, 3: 30.0, 4: 40.0}


@pytest.mark.unit
def test_p50_acumulado_declara_cuatro_tablas_aunque_falte_la_seccion_reto() -> None:
    hoja = hoja_desde_celdas(
        {(1, 1): "P50", (2, 3): ENE, (3, 1): "CRUDO", (3, 3): 10.0}
    )

    resultado = extraer_p50_acumulado(hoja)  # type: ignore[arg-type]

    assert len(resultado.tablas_declaradas) == 4
    assert {t[0] for t in resultado.tablas_vacias()} == {2, 3, 4}


# ── Producción filiales ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_filiales_extrae_el_bloque_por_producto() -> None:
    hoja = hoja_desde_filas(
        [
            ["REAL"],
            ["EMPRESA", ENE, FEB],
            ["Hocol (crudo)", 10.0, 20.0],
            ["Total", 999.0],
        ]
    )

    resultado = extraer_produccion_filiales(hoja)  # type: ignore[arg-type]

    filas = [f for f in resultado.filas if f.tabla_idx == 1]
    assert len(filas) == 2
    assert filas[0].dims == {"empresa": "Hocol", "producto": "CRUDO"}
    assert 999.0 not in [f.valor for f in resultado.filas]


@pytest.mark.unit
def test_filiales_extrae_el_total_por_empresa_sin_producto() -> None:
    hoja = hoja_desde_filas([["REAL"], ["EMPRESA", ENE], ["HOCOL", 77.0]])

    resultado = extraer_produccion_filiales(hoja)  # type: ignore[arg-type]

    totales = [f for f in resultado.filas if f.tabla_idx == 6]
    assert len(totales) == 1
    assert totales[0].dims == {"empresa": "Hocol"}


@pytest.mark.unit
def test_filiales_reutiliza_las_fechas_cuando_el_encabezado_viene_vacio() -> None:
    """La tabla 7 (PROGRAMA total empresa) trae el encabezado de fechas vacío: sin
    reutilizar las de la tabla 6, se perdería entera."""
    hoja = hoja_desde_filas(
        [
            ["REAL"],
            ["EMPRESA", ENE],
            ["HOCOL", 10.0],
            ["PROGRAMA"],
            ["EMPRESA"],
            ["HOCOL", 20.0],
        ]
    )

    resultado = extraer_produccion_filiales(hoja)  # type: ignore[arg-type]

    programa = [f for f in resultado.filas if f.tabla_idx == 7]
    assert len(programa) == 1
    assert programa[0].fecha == ENE
    assert programa[0].valor == 20.0


@pytest.mark.unit
def test_filiales_ignora_un_producto_desconocido() -> None:
    """`norm_prod` devuelve None ante un producto fuera del mapa, y la fila se descarta:
    el producto decide la escala de la cifra (A5)."""
    hoja = hoja_desde_filas([["REAL"], ["EMPRESA", ENE], ["Hocol (plasma)", 10.0]])

    resultado = extraer_produccion_filiales(hoja)  # type: ignore[arg-type]

    assert [f for f in resultado.filas if f.tabla_idx == 1] == []


@pytest.mark.unit
def test_filiales_declara_sus_ocho_tablas() -> None:
    resultado = extraer_produccion_filiales(hoja_desde_filas([["nada"]]))  # type: ignore[arg-type]

    assert [t[0] for t in resultado.tablas_declaradas] == [1, 2, 3, 4, 5, 6, 7, 8]


# ── POP Filiales e INICIO ────────────────────────────────────────────────────


@pytest.mark.unit
def test_pop_filiales_usa_la_segunda_dimension_solo_si_esta() -> None:
    """Los subtotales llegan con la columna C vacía: sus dims quedan con una sola
    clave, y por eso no colisionan con las filas de detalle."""
    hoja = hoja_desde_celdas(
        {
            (2, 4): ENE,
            (3, 2): "CRUDO", (3, 3): "Hocol", (3, 4): 10.0,
            (4, 2): "CRUDO", (4, 4): 20.0,
        }
    )  # fmt: skip

    resultado = extraer_pop_filiales(hoja)  # type: ignore[arg-type]

    dims = [f.dims for f in resultado.filas]
    assert {"producto": "CRUDO", "empresa": "Hocol"} in dims
    assert {"producto": "CRUDO"} in dims


@pytest.mark.unit
def test_inicio_encuentra_la_tabla_este_en_la_fila_que_este() -> None:
    hoja = hoja_desde_celdas(
        {
            (30, 1): "REAL PROMEDIO MES (YTD) Filiales",
            (31, 3): ENE,
            (32, 1): "CRUDO", (32, 2): "Hocol", (32, 3): 42.0,
        }
    )  # fmt: skip

    resultado = extraer_inicio(hoja)  # type: ignore[arg-type]

    assert len(resultado.filas) == 1
    assert resultado.filas[0].dims == {"producto": "CRUDO", "empresa": "Hocol"}
    assert resultado.filas[0].valor == 42.0


@pytest.mark.unit
def test_inicio_sin_la_tabla_devuelve_vacio_pero_la_declara() -> None:
    resultado = extraer_inicio(hoja_desde_celdas({(1, 1): "Parámetros"}))  # type: ignore[arg-type]

    assert resultado.filas == []
    assert [t[1] for t in resultado.tablas_declaradas] == [
        "REAL PROMEDIO MES (YTD) Filiales"
    ]
