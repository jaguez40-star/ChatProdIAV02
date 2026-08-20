"""Ranking N5 — D3 (semántica de orden) y D4 (cero traicionero).

El test que da sentido al archivo es
`test_los_que_quedaron_mas_cortos_no_son_los_que_superaron`: fija el bug real
que la forma `(eje, asc/desc)` producía en el plan v1 del origen.
"""

from __future__ import annotations

from datetime import date
from typing import Any, cast

import pytest
from sqlalchemy.orm import Session

from src.features.consulta.ranking import calcular, detectar

pytestmark = pytest.mark.unit


class _SesionRankingFalsa:
    """Doble mínimo: un universo de 4 campos con faltantes y excedentes."""

    def __init__(
        self,
        filas: list[tuple[Any, ...]] | None = None,
        *,
        max_real: date | None = date(2026, 5, 31),
        max_dia: date | None = date(2026, 5, 31),
    ) -> None:
        self.filas = (
            filas
            if filas is not None
            else [
                # (entidad, real, ppto, operador)
                ("RUBIALES", 1000.0, 900.0, "ECOPETROL"),  # excedente +100
                ("CASTILLA", 800.0, 1000.0, "ECOPETROL"),  # faltante  -200
                ("QUIFA", 600.0, 500.0, "FRONTERA"),  # excedente +100, tercero
                ("APIAY", 400.0, 900.0, "ECOPETROL"),  # faltante  -500 (el mayor)
            ]
        )
        self.max_real = max_real
        self.max_dia = max_dia

    def execute(self, consulta: Any, params: Any = None) -> Any:
        sql = str(consulta)

        class _R:
            def __init__(self, valor: Any = None, filas: Any = None) -> None:
                self._valor = valor
                self._filas = filas or []

            def scalar(self) -> Any:
                return self._valor

            def all(self) -> Any:
                return self._filas

        if "MAX(m.fecha)" in sql:
            return _R(valor=self.max_real)
        if "MAX(fecha) FROM core.fact_produccion_dia_ecp" in sql:
            return _R(valor=self.max_dia)
        if "fact_produccion_mes_ecp" in sql:
            return _R(filas=self.filas)

        raise AssertionError(f"SQL no reconocido por el doble:\n{sql}")


def _db(**kwargs: Any) -> Session:
    return cast(Session, _SesionRankingFalsa(**kwargs))


# ═════════════════════════════════════════════════════════════════════════════
# D3 — la semántica de orden
# ═════════════════════════════════════════════════════════════════════════════


def test_los_que_quedaron_mas_cortos_no_son_los_que_superaron() -> None:
    """🔑 D3, el bug que motiva la regla.

    Con la forma `(eje, asc/desc)` esta pregunta devolvía los que SUPERARON el
    presupuesto — exactamente lo contrario de lo pedido.
    """
    slots = detectar("qué campos se quedaron más cortos vs presupuesto")
    assert slots is not None
    assert slots["metrica"] == "gap"
    assert slots["direccion"] == "bottom"

    res = calcular(slots, _db())
    assert res["aplica"] is True
    # El primero debe ser el de MAYOR faltante, no el de mayor excedente.
    assert res["items"][0]["entidad"] == "APIAY"
    assert res["items"][0]["gap"] == -500


def test_mayor_faltante_da_faltante_aunque_diga_mayor() -> None:
    """Las palabras de faltante MANDAN sobre "mayor": es la intención
    dominante, y por eso el default de gap es `bottom`."""
    slots = detectar("cuáles campos tienen mayor faltante")
    assert slots is not None
    assert slots["direccion"] == "bottom"


def test_el_excedente_explicito_si_sube_a_top() -> None:
    slots = detectar("qué campos superaron el presupuesto")
    assert slots is not None
    assert slots["metrica"] == "gap"
    assert slots["direccion"] == "top"

    res = calcular(slots, _db())
    assert res["items"][0]["gap"] > 0


def test_los_que_mas_producen_ordenan_por_real_descendente() -> None:
    slots = detectar("cuáles campos son los mayores productores de crudo")
    assert slots is not None
    assert slots["metrica"] == "real"
    assert slots["direccion"] == "top"

    res = calcular(slots, _db())
    assert [i["entidad"] for i in res["items"]][:2] == ["RUBIALES", "CASTILLA"]


def test_la_produccion_mas_baja_ordena_ascendente() -> None:
    slots = detectar("cuáles campos tienen la menor produccion")
    assert slots is not None
    assert slots["direccion"] == "bottom"

    res = calcular(slots, _db())
    assert res["items"][0]["entidad"] == "APIAY"  # el de menor real > 0


# ═════════════════════════════════════════════════════════════════════════════
# D4 — cero traicionero
# ═════════════════════════════════════════════════════════════════════════════


def test_un_cero_no_es_poca_produccion() -> None:
    """🔑 D4: un cero es "sin registro". Si contara como producción baja, el
    fondo del ranking lo ocuparían entidades que simplemente no reportaron."""
    filas = [
        ("RUBIALES", 1000.0, 900.0, "ECOPETROL"),
        ("SIN_DATO", 0.0, 500.0, "ECOPETROL"),
    ]
    slots = detectar("cuáles campos tienen la menor produccion")
    assert slots is not None

    res = calcular(slots, _db(filas=filas))
    assert [i["entidad"] for i in res["items"]] == ["RUBIALES"]
    assert res["sin_registro"] == 1


def test_sin_ninguna_produccion_lo_dice() -> None:
    filas = [("SIN_DATO", 0.0, 500.0, "ECOPETROL")]
    slots = detectar("cuáles campos son los mayores productores de crudo")
    assert slots is not None

    res = calcular(slots, _db(filas=filas))
    assert res["aplica"] is False
    assert "No hay producción" in res["texto"]


def test_si_todos_cumplen_exacto_lo_declara() -> None:
    """Sin esta guarda, un ranking de gap sin faltantes daría una lista vacía
    presentada como si fuera un resultado."""
    filas = [("RUBIALES", 900.0, 900.0, "ECOPETROL")]
    slots = detectar("qué campos quedaron cortos vs presupuesto")
    assert slots is not None

    res = calcular(slots, _db(filas=filas))
    assert res["aplica"] is False
    assert "coinciden con su presupuesto" in res["texto"]


# ═════════════════════════════════════════════════════════════════════════════
# Detección
# ═════════════════════════════════════════════════════════════════════════════


def test_exige_superlativo_y_nivel() -> None:
    """ "¿cuál es la mayor producción de Rubiales?" NO es un ranking: es la
    cifra de Rubiales. Sin sustantivo de nivel, la pregunta sigue por N1-N4."""
    assert detectar("cuál es la mayor produccion de Rubiales") is None


def test_sin_superlativo_no_es_ranking() -> None:
    assert detectar("cuántos campos hay") is None


def test_el_singular_pide_uno_y_el_plural_cinco() -> None:
    uno = detectar("cuál es el campo que más produce")
    varios = detectar("cuáles son los campos que más producen")
    assert uno is not None and uno["top_n"] == 1
    assert varios is not None and varios["top_n"] == 5


def test_top_n_explicito_se_respeta_y_se_acota() -> None:
    diez = detectar("top 10 campos de crudo")
    assert diez is not None and diez["top_n"] == 10

    enorme = detectar("top 500 campos de crudo")
    assert enorme is not None and enorme["top_n"] == 20  # tope de seguridad


def test_detecta_el_producto_y_su_unidad() -> None:
    slots = detectar("cuáles campos son los mayores productores de gas")
    assert slots is not None and slots["producto"] == "gas"

    res = calcular(slots, _db())
    assert res["unidad"] == "MSCF"


@pytest.mark.parametrize("nivel", ["gerencia", "vicepresidencia", "pozo"])
def test_los_niveles_diferidos_declinan_con_su_motivo(nivel: str) -> None:
    """Un "no puedo" sin razón invita a insistir; con razón, el usuario
    reformula."""
    slots = detectar(f"cuáles son las mayores {nivel}s")
    if slots is None:  # el plural irregular puede no casar; se prueba directo
        slots = {"nivel_ranking": nivel, "diferido": "motivo"}

    res = calcular(slots, _db())
    assert res["aplica"] is False
    assert res["texto"]


# ═════════════════════════════════════════════════════════════════════════════
# Contrato
# ═════════════════════════════════════════════════════════════════════════════


def test_marca_los_terceros_sin_ocultarlos() -> None:
    """El reporte incluye campos operados por terceros; ocultarlos daría un
    ranking falso. Se incluyen y se rotula el operador."""
    slots = detectar("cuáles campos son los mayores productores de crudo")
    assert slots is not None

    res = calcular(slots, _db())
    quifa = next(i for i in res["items"] if i["entidad"] == "QUIFA")
    assert quifa["es_ecp"] is False
    assert quifa["operador"] == "FRONTERA"


def test_la_concentracion_solo_aplica_a_real_top() -> None:
    """En bottom, "los que menos producen concentran X %" sería una cifra
    engañosa."""
    top = detectar("cuáles campos son los mayores productores de crudo")
    bottom = detectar("cuáles campos tienen la menor produccion")
    assert top is not None and bottom is not None

    assert calcular(top, _db())["concentracion_pct"] is not None
    assert calcular(bottom, _db())["concentracion_pct"] is None


def test_declara_que_el_mes_es_proyeccion() -> None:
    """El REAL del mes en curso es un cierre proyectado; presentarlo como
    definitivo sería engañoso."""
    slots = detectar("cuáles campos son los mayores productores de crudo")
    assert slots is not None

    res = calcular(slots, _db(max_dia=date(2026, 5, 17)))
    assert res["es_proyeccion"] is True


def test_sin_datos_cargados_lo_dice() -> None:
    slots = detectar("cuáles campos son los mayores productores de crudo")
    assert slots is not None

    res = calcular(slots, _db(max_real=None))
    assert res["aplica"] is False
    assert "No hay datos" in res["texto"]
