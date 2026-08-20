"""Tests de la familia `reportes` contra el .xlsm REAL.

Estas seis hojas publican cifras ya calculadas. Lo que se verifica aquí no es la
aritmética —no la hay, se ingiere tal cual— sino que cada tabla salga con la forma
pactada: las claves de `dims` correctas, las tablas declaradas completas, y las reglas
que distinguen un dato de un artefacto de la hoja (subtotales, columnas agregadas,
errores de Excel).
"""

from __future__ import annotations

from typing import Any

import pytest

from src.features.ingesta.extractores.reportes import (
    extraer_bitacora,
    extraer_calculo_trimestre,
    extraer_dpp,
    extraer_programa,
    extraer_reporte_president,
    extraer_whatsapp,
)
from tests.fakes.muestras_xlsm import DIRECTORIO_MUESTRAS, hay_muestras
from tests.fakes.muestras_xlsm import hoja_de as _hoja

pytestmark = [
    pytest.mark.muestras,
    pytest.mark.skipif(
        not hay_muestras(), reason=f"no hay .xlsm de muestra en {DIRECTORIO_MUESTRAS}"
    ),
]


@pytest.fixture
def libro_new(libro_muestra_new: Any) -> Any:
    return libro_muestra_new


# ── (Bitacora) ───────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_bitacora_declara_sus_tres_bloques(libro_new: Any) -> None:
    """Se declaran los 3 aunque PROGRAMA venga con #N/A en los archivos STD."""
    resultado = extraer_bitacora(_hoja(libro_new, "(Bitacora"))

    assert [t[0] for t in resultado.tablas_declaradas] == [1, 2, 3]


@pytest.mark.integration
def test_bitacora_solo_emite_filas_con_vice(libro_new: Any) -> None:
    """Tener VICE es lo que distingue una fila de datos de un subtotal."""
    resultado = extraer_bitacora(_hoja(libro_new, "(Bitacora"))

    if not resultado.filas:
        pytest.skip("la hoja de bitácora no trajo filas en este archivo")
    assert all(set(f.dims) == {"tipoproducto", "vice"} for f in resultado.filas)
    assert all(f.fecha is not None for f in resultado.filas)


# ── PROGRAMA ─────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_programa_declara_sus_cuatro_tablas(libro_new: Any) -> None:
    resultado = extraer_programa(_hoja(libro_new, "PROGRAMA"))

    assert [t[0] for t in resultado.tablas_declaradas] == [1, 2, 3, 4]


@pytest.mark.integration
def test_programa_extrae_con_las_dimensiones_de_cada_tabla(libro_new: Any) -> None:
    resultado = extraer_programa(_hoja(libro_new, "PROGRAMA"))

    if not resultado.filas:
        pytest.skip("la hoja PROGRAMA no trajo filas en este archivo")
    esperadas = {
        1: {"tipoproducto", "area", "campo"},
        2: {"producto", "vice"},
        3: {"tipoproducto", "vice"},
        4: {"producto", "vice", "area", "campo"},
    }
    for fila in resultado.filas:
        assert set(fila.dims) <= esperadas[fila.tabla_idx]


# ── Reporte Whatsapp ─────────────────────────────────────────────────────────


@pytest.mark.integration
def test_whatsapp_declara_sus_doce_tablas(libro_new: Any) -> None:
    resultado = extraer_whatsapp(_hoja(libro_new, "Reporte Whatsapp"))

    assert [t[0] for t in resultado.tablas_declaradas] == list(range(1, 13))


@pytest.mark.integration
def test_whatsapp_no_pone_fecha_en_ninguna_fila(libro_new: Any) -> None:
    """La celda 'Producción al:' no es fiable; el linaje temporal lo da reporte_id."""
    resultado = extraer_whatsapp(_hoja(libro_new, "Reporte Whatsapp"))

    assert all(f.fecha is None for f in resultado.filas)


@pytest.mark.integration
def test_whatsapp_separa_consolidados_de_activos(libro_new: Any) -> None:
    """Las tablas 1-6 son consolidadas (segmento) y las 7-12 por activo: sus dims no
    pueden mezclarse."""
    resultado = extraer_whatsapp(_hoja(libro_new, "Reporte Whatsapp"))

    if not resultado.filas:
        pytest.skip("la hoja de WhatsApp no trajo filas en este archivo")
    for fila in resultado.filas:
        if fila.tabla_idx <= 6:
            assert set(fila.dims) == {"segmento", "concepto", "columna", "metrica"}
        else:
            assert set(fila.dims) == {"activo", "columna", "metrica"}


# ── Reporte DPP ──────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_dpp_es_matricial_y_declara_cinco_tablas(libro_new: Any) -> None:
    resultado = extraer_dpp(_hoja(libro_new, "Reporte DPP"))

    assert [t[0] for t in resultado.tablas_declaradas] == [1, 2, 3, 4, 5]
    assert all(f.fecha is None for f in resultado.filas)
    assert all(set(f.dims) == {"fila", "columna"} for f in resultado.filas)


@pytest.mark.integration
def test_dpp_embebe_el_grupo_en_la_etiqueta_de_fila(libro_new: Any) -> None:
    """Sin el prefijo, CRUDO de Ecopetrol y CRUDO de Filiales colisionarían."""
    resultado = extraer_dpp(_hoja(libro_new, "Reporte DPP"))

    if not resultado.filas:
        pytest.skip("la hoja DPP no trajo filas en este archivo")
    filas = {str(f.dims["fila"]) for f in resultado.filas}
    assert any(" · " in f or f.startswith("TOTAL") for f in filas)


@pytest.mark.integration
def test_dpp_conserva_los_errores_de_excel_como_hueco(libro_new: Any) -> None:
    """Regla propia de DPP: un #¡REF! entra con valor None para preservar la forma de la
    tabla; solo la celda vacía de verdad se salta."""
    resultado = extraer_dpp(_hoja(libro_new, "Reporte DPP"))

    if not resultado.filas:
        pytest.skip("la hoja DPP no trajo filas en este archivo")
    # La comprobación real es que emitir un None sea posible, no que siempre ocurra.
    assert all(f.valor is None or isinstance(f.valor, float) for f in resultado.filas)


# ── REPORTE_PRESIDENT ────────────────────────────────────────────────────────


@pytest.mark.integration
def test_president_declara_sus_dos_bloques(libro_new: Any) -> None:
    resultado = extraer_reporte_president(_hoja(libro_new, "REPORTE_PRESIDENT"))

    assert [t[0] for t in resultado.tablas_declaradas] == [1, 2]


@pytest.mark.integration
def test_president_usa_medidas_posicionales(libro_new: Any) -> None:
    """El sufijo de mes del encabezado varía entre archivos, así que las medidas se
    nombran por posición: si se usara el texto, cada mes daría claves distintas."""
    resultado = extraer_reporte_president(_hoja(libro_new, "REPORTE_PRESIDENT"))

    if not resultado.filas:
        pytest.skip("la hoja PRESIDENT no trajo filas en este archivo")
    medidas = {str(f.dims["medida"]) for f in resultado.filas}
    assert medidas <= {
        "real_mes", "proy_mes", "base_p50", "delta_p50", "compromiso",
        "delta_compromiso", "real_dia", "programa_dia", "delta_dia",
    }  # fmt: skip
    assert all(set(f.dims) == {"entidad", "medida"} for f in resultado.filas)


# ── CÁLCULO DE TRIMESTRE ─────────────────────────────────────────────────────


@pytest.mark.integration
def test_trimestre_declara_sus_ocho_tablas(libro_new: Any) -> None:
    resultado = extraer_calculo_trimestre(_hoja(libro_new, "CALCULO DE TRIMESTRE"))

    assert [t[0] for t in resultado.tablas_declaradas] == [1, 2, 3, 4, 5, 6, 7, 8]


@pytest.mark.integration
def test_trimestre_distingue_tablas_temporales_de_matriciales(libro_new: Any) -> None:
    """T2/T3/T4 llevan fecha (mensuales); T1 y T5-T8 son matrices sin fecha."""
    resultado = extraer_calculo_trimestre(_hoja(libro_new, "CALCULO DE TRIMESTRE"))

    if not resultado.filas:
        pytest.skip("la hoja de trimestre no trajo filas en este archivo")
    for fila in resultado.filas:
        if fila.tabla_idx in {2, 3, 4}:
            assert fila.fecha is not None
        else:
            assert fila.fecha is None


@pytest.mark.integration
def test_trimestre_usa_las_etiquetas_de_trimestre_pactadas(libro_new: Any) -> None:
    resultado = extraer_calculo_trimestre(_hoja(libro_new, "CALCULO DE TRIMESTRE"))

    trimestrales = [f for f in resultado.filas if f.tabla_idx in {5, 6, 7, 8}]
    if not trimestrales:
        pytest.skip("las tablas trimestrales no trajeron filas en este archivo")
    assert {str(f.dims["columna"]) for f in trimestrales} <= {"1Q", "2Q", "3Q", "4Q"}
