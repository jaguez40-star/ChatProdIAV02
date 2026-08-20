"""Desempeño ECP — resolución de periodo y contrato de `escenario_mes`.

Tests puros del cimiento nivel+periodo aware. La parte que toca BD se cubre en
los tests de integración con el doble de sesión.
"""

from __future__ import annotations

import pytest

from src.features.analisis.services_desempeno import (
    parse_periodo,
    periodo_es_default,
)

# Mes de referencia: mayo 2026 (el último con dato en el corpus real).
ANIO_REF, MES_REF = 2026, 5


# ── periodo_es_default ──────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    "texto",
    [None, "", "este mes", "MES ACTUAL", "el mes", "mes en curso"],
)
def test_textos_que_significan_el_mes_por_defecto(texto: str | None) -> None:
    assert periodo_es_default(texto) is True


@pytest.mark.unit
def test_solo_espacios_no_cuenta_como_default_pero_tampoco_rompe() -> None:
    """Conducta del origen, verificada ejecutando su código: `"  "` NO es
    default (la comparación se hace tras `.strip().lower()` contra el conjunto,
    y `""` no está en él), pero `parse_periodo` igual devuelve `None`.

    El resultado práctico es el mismo —se sirve el último mes con dato— con una
    diferencia: `periodo_ok` queda en False, o sea el panel DECLARA que no pudo
    honrar lo pedido. Es la conducta honesta y se conserva tal cual.
    """
    assert periodo_es_default("  ") is False
    assert parse_periodo("  ", ANIO_REF, MES_REF) is None


@pytest.mark.unit
def test_un_mes_explicito_no_es_el_default() -> None:
    assert periodo_es_default("marzo") is False


# ── parse_periodo ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_default_devuelve_none_para_usar_el_ultimo_con_dato() -> None:
    assert parse_periodo(None, ANIO_REF, MES_REF) is None
    assert parse_periodo("este mes", ANIO_REF, MES_REF) is None


@pytest.mark.unit
def test_mes_por_nombre_hereda_el_anio_de_referencia() -> None:
    assert parse_periodo("marzo", ANIO_REF, MES_REF) == (2026, 3)


@pytest.mark.unit
def test_mes_con_anio_explicito() -> None:
    assert parse_periodo("marzo 2025", ANIO_REF, MES_REF) == (2025, 3)


@pytest.mark.unit
def test_acepta_setiembre_sin_p() -> None:
    """Variante ortográfica válida en español: el usuario escribe ambas."""
    assert parse_periodo("setiembre", ANIO_REF, MES_REF) == (2026, 9)


@pytest.mark.unit
def test_mes_pasado_retrocede_uno() -> None:
    assert parse_periodo("mes pasado", ANIO_REF, MES_REF) == (2026, 4)
    assert parse_periodo("el mes anterior", ANIO_REF, MES_REF) == (2026, 4)


@pytest.mark.unit
def test_mes_pasado_cruza_el_cambio_de_anio() -> None:
    """En enero, el mes pasado es diciembre del año anterior."""
    assert parse_periodo("mes pasado", 2026, 1) == (2025, 12)


@pytest.mark.unit
@pytest.mark.parametrize(
    "texto", ["2026", "esta semana", "primer trimestre", "el año", "ayer"]
)
def test_periodos_no_soportados_devuelven_none(texto: str) -> None:
    """v1 solo soporta MES.

    Devolver `None` es lo correcto: el llamador sirve el default y lo DECLARA
    con `periodo_ok=False`, en vez de entregar en silencio un periodo distinto
    al que se pidió.
    """
    assert parse_periodo(texto, ANIO_REF, MES_REF) is None


# ── Contrato de `escenario_mes` (H15) ───────────────────────────────────────


@pytest.mark.unit
def test_escenario_mes_no_es_un_endpoint() -> None:
    """AF-4.11: es un helper que F4/Cuantificar llama como función normal.

    Si se expusiera como ruta, sus parámetros llegarían como objetos `Query` de
    FastAPI en vez de valores. Este test fija que nadie lo convierta en
    endpoint por descuido.
    """
    from src.features.analisis import api
    from src.features.analisis.services_desempeno import escenario_mes

    rutas = {getattr(r, "path", "") for r in api.router.routes}
    assert not any("escenario" in ruta for ruta in rutas)
    assert callable(escenario_mes)
