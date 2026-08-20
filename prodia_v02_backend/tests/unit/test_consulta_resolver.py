"""Resolver de entidades y política de desambiguación.

Los casos cubren las tres formas de colisión que el panel Fundación mostró
contra el 139 (151 colisiones reales, 5 de ellas duras): redundante, con
prioridad Campo, y genuina.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from sqlalchemy.orm import Session

from src.features.consulta import resolver as mod_resolver
from tests.fakes.catalogo_falso import SesionCatalogoFalsa

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _limpiar_cache() -> Any:
    """Las cachés son por proceso: sin esto un test vería el índice de otro."""
    mod_resolver.reset_cache()
    yield
    mod_resolver.reset_cache()


def _db(**kwargs: Any) -> Session:
    return cast(Session, SesionCatalogoFalsa(**kwargs))


# ── Match exacto y backstop ──────────────────────────────────────────────────


def test_resuelve_un_nombre_exacto() -> None:
    identidades = mod_resolver.resolver("SURIA", _db())
    assert [i["nivel"] for i in identidades] == ["fuente", "campo"]


def test_el_nombre_se_normaliza() -> None:
    """Minúsculas y acentos no deben impedir el match."""
    assert mod_resolver.resolver("suria", _db())


def test_un_nombre_desconocido_no_resuelve() -> None:
    assert mod_resolver.resolver("MARTE", _db()) == []


def test_el_backstop_encuentra_la_entidad_dentro_de_una_frase() -> None:
    hit = mod_resolver.buscar_en_texto("¿cuánto produjo SURIA en mayo?", _db())
    assert hit is not None
    gram, identidades = hit
    assert gram == "SURIA"
    assert identidades


def test_el_backstop_ignora_las_palabras_funcionales() -> None:
    """Sin `_STOP`, "mes" o "crudo" se resolverían como si fueran entidades."""
    assert mod_resolver.buscar_en_texto("cuanto crudo en el mes", _db()) is None


# ── Las tres formas de colisión ──────────────────────────────────────────────


def test_colision_redundante_se_resuelve_sola() -> None:
    """RUBIALES es fuente, campo y activo, pero los tres cubren la MISMA
    fuente física: es el mismo dato con tres nombres, no una ambigüedad."""
    resuelta = mod_resolver.resolver_unico("RUBIALES", _db())

    assert resuelta is not None
    assert "ambiguo" not in resuelta
    # Gana el nivel de mayor prioridad entre los redundantes.
    assert resuelta["nivel"] == "campo"


def test_prioridad_campo_responde_directo_y_ofrece_zoom() -> None:
    """D-D5: APIAY es campo (1 fuente) y activo (2 fuentes) — conjuntos
    distintos, así que es colisión real. Con exactamente un campo y ninguna
    filial se responde Campo y el activo queda como zoom, en vez de
    contrapreguntar."""
    resuelta = mod_resolver.resolver_unico("APIAY", _db())

    assert resuelta is not None
    assert "ambiguo" not in resuelta
    assert resuelta["nivel"] == "campo"
    assert [z["nivel"] for z in resuelta["zoom"]] == ["activo"]


def test_colision_genuina_pide_desambiguar() -> None:
    """HOCOL es filial (rama B) y campo: dos cosas distintas. La prioridad
    Campo NO aplica cuando hay una filial de por medio."""
    resuelta = mod_resolver.resolver_unico("HOCOL", _db())

    assert resuelta is not None
    assert "ambiguo" in resuelta
    ramas = {r.get("rama") for r in resuelta["ambiguo"]}
    assert "B" in ramas


def test_sin_match_devuelve_none() -> None:
    assert mod_resolver.resolver_unico("MARTE", _db()) is None


# ── Puente de nivel (R2) ─────────────────────────────────────────────────────


def test_marca_puente_en_la_gerencia_que_es_vicepresidencia() -> None:
    """GOR figura como "gerencia" en `dim_fuente` pero en robustez es
    VICEPRESIDENCIA. Se marca para rotularlo bien; el nivel de consulta no
    cambia."""
    resuelta = mod_resolver.resolver_unico("GOR", _db())

    assert resuelta is not None
    assert resuelta["nivel"] == "gerencia"  # el nivel de query NO se toca
    assert resuelta.get("puente") is True


def test_no_marca_puente_si_el_codigo_es_ambiguo() -> None:
    """GAA existe como VP *y* como gerencia real: no hay evidencia para
    relabelar, así que gana el nivel más específico."""
    resuelta = mod_resolver.resolver_unico("GAA", _db())

    assert resuelta is not None
    assert resuelta.get("puente") is not True


def test_sin_robustez_degrada_con_gracia() -> None:
    """Si `map_campo_robustez` no está, no se marca ningún puente — pero se
    responde igual. El puente mejora el rótulo, no es requisito."""
    resuelta = mod_resolver.resolver_unico("GOR", _db(sin_robustez=True))

    assert resuelta is not None
    assert resuelta.get("puente") is not True


# ── Cachés ───────────────────────────────────────────────────────────────────


def test_el_indice_se_construye_una_sola_vez() -> None:
    """El índice hace 7 consultas: reconstruirlo en cada pregunta sería caro."""
    db = SesionCatalogoFalsa()
    sesion = cast(Session, db)

    mod_resolver.resolver("SURIA", sesion)
    consultas_tras_la_primera = len(db.consultas)
    mod_resolver.resolver("APIAY", sesion)

    assert len(db.consultas) == consultas_tras_la_primera
