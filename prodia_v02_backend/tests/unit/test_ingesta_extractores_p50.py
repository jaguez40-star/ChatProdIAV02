"""Tests de los extractores P50 contra el .xlsm REAL.

Por qué contra el archivo real y no contra una hoja fabricada: estos extractores leen por
posiciones pactadas con ese archivo (columna 5, fila 2, columna C…). Un test con una hoja
inventada verificaría que el código hace lo que el código hace, no que extrae bien de la
hoja de verdad — que es justo el fallo silencioso de G5.

Si el `.xlsm` de muestra no está disponible, los tests se **saltan con motivo visible**, no
se dan por buenos. El origen tenía este mismo patrón pero con una ruta a
`c:\\Users\\user\\...` que no existe en ninguna máquina, así que su único test sustantivo
llevaba meses saltándose sin que nadie lo notara (G9).
"""

from __future__ import annotations

from typing import Any

import pytest

from src.features.ingesta.extractores.p50 import (
    extraer_p50_acumulado,
    extraer_p50_quemado,
)
from tests.fakes.muestras_xlsm import DIRECTORIO_MUESTRAS, hay_muestras
from tests.fakes.muestras_xlsm import hoja_de as _hoja

# Excluidos del run por defecto (ver `addopts` en pyproject.toml): CI no tiene estos
# archivos. El libro lo aporta `libro_muestra_new`, un fixture de alcance session
# (conftest) para no cargar 125 MB por módulo.
pytestmark = [
    pytest.mark.muestras,
    pytest.mark.skipif(
        not hay_muestras(), reason=f"no hay .xlsm de muestra en {DIRECTORIO_MUESTRAS}"
    ),
]


@pytest.fixture
def libro_new(libro_muestra_new: Any) -> Any:
    return libro_muestra_new


# ── P50 Quemado ──────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_p50_quemado_extrae_filas_reales(libro_new: object) -> None:
    resultado = extraer_p50_quemado(_hoja(libro_new, "P50 Quemado"))

    assert resultado.filas, "el extractor no sacó ni una fila del archivo real"
    assert {t[0] for t in resultado.tablas_declaradas} == {1, 2}


@pytest.mark.integration
def test_p50_quemado_declara_las_dimensiones_pactadas(libro_new: object) -> None:
    resultado = extraer_p50_quemado(_hoja(libro_new, "P50 Quemado"))

    tabla1 = [f for f in resultado.filas if f.tabla_idx == 1]
    assert tabla1, "la tabla 1 (quemado) salió vacía"
    assert set(tabla1[0].dims) == {"escenario", "producto", "vice", "activos", "area"}


@pytest.mark.integration
def test_p50_quemado_descarta_los_subtotales(libro_new: object) -> None:
    """Las filas 'Total …' son agregados de la propia hoja: ingerirlas duplicaría."""
    resultado = extraer_p50_quemado(_hoja(libro_new, "P50 Quemado"))

    areas = [str(f.dims.get("area") or "").lower() for f in resultado.filas]
    assert not [a for a in areas if a.startswith("total")]


@pytest.mark.integration
def test_p50_quemado_todas_las_filas_llevan_fecha_y_valor(libro_new: object) -> None:
    """Es una serie temporal: sin fecha, la fila no sabría a qué mes pertenece."""
    resultado = extraer_p50_quemado(_hoja(libro_new, "P50 Quemado"))

    assert all(f.fecha is not None for f in resultado.filas)
    assert all(isinstance(f.valor, float) for f in resultado.filas)


# ── P50 Acumulado ────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_p50_acumulado_declara_siempre_sus_cuatro_tablas(libro_new: object) -> None:
    """Se declaran aunque vengan vacías, para que el front las liste (G5)."""
    resultado = extraer_p50_acumulado(_hoja(libro_new, "P50 Acumulado"))

    assert [t[0] for t in resultado.tablas_declaradas] == [1, 2, 3, 4]


@pytest.mark.integration
def test_p50_acumulado_extrae_filas_reales(libro_new: object) -> None:
    resultado = extraer_p50_acumulado(_hoja(libro_new, "P50 Acumulado"))

    assert resultado.filas, "el extractor no sacó ni una fila del archivo real"
    assert all(set(f.dims) == {"producto"} for f in resultado.filas)


@pytest.mark.integration
def test_p50_acumulado_no_confla_filiales_con_reto(libro_new: object) -> None:
    """Regresión del bug documentado: sin acotar por el título siguiente, la Tabla 2
    arrastraba el bloque RETO-ECP y ambos colisionaban en (dims, fecha) con last-wins.
    """
    resultado = extraer_p50_acumulado(_hoja(libro_new, "P50 Acumulado"))

    por_tabla: dict[int, set[tuple[str, object]]] = {}
    for fila in resultado.filas:
        clave = (str(fila.dims.get("producto")), fila.fecha)
        por_tabla.setdefault(fila.tabla_idx, set()).add(clave)

    # Ninguna tabla puede tener la misma clave dos veces (eso indicaría solape).
    for indice, claves in por_tabla.items():
        filas_tabla = [f for f in resultado.filas if f.tabla_idx == indice]
        assert len(claves) == len(
            filas_tabla
        ), f"claves duplicadas en la tabla {indice}"
