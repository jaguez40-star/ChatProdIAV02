"""Tests del catálogo de entidades — normalización y composición de activos.

La composición del activo es fuente ÚNICA para el tablero (F2) y el chat (F4):
si divergieran, la misma entidad daría cifras distintas en cada uno. Estos
tests fijan ese contrato.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from src.shared.catalogo_entidades import (
    activo_de_campo,
    campos_de_activo,
    fuentes_de_activo,
    norm,
    reset_cache,
)


@pytest.fixture(autouse=True)
def _limpiar_indice() -> Any:
    """El índice se cachea por proceso: sin limpiar, un test heredaría el del
    anterior y los resultados dependerían del orden de ejecución."""
    reset_cache()
    yield
    reset_cache()


class SesionFalsa:
    """Doble mínimo de `Session`: responde por la forma del SQL recibido.

    Falla ruidosamente ante una consulta que no reconoce — si alguien cambia el
    repositorio, el test lo dice en vez de devolver vacío en silencio.
    """

    def __init__(self, mapa: list[tuple[str, str]], fuentes: list[tuple[int, str]]):
        self._mapa = mapa
        self._fuentes = fuentes
        self.consultas: list[str] = []

    def execute(self, sentencia: Any, params: dict[str, Any] | None = None) -> Any:
        sql = " ".join(str(sentencia).split())
        self.consultas.append(sql)
        parametros = params or {}

        if "campo_norm, activo FROM core.map_campo_activo" in sql:
            return _Resultado([(norm(c), a) for c, a in self._mapa])
        if "SELECT campo FROM core.map_campo_activo" in sql:
            objetivo = parametros["activo"]
            return _Resultado(
                [(c,) for c, a in self._mapa if a.strip().upper() == objetivo]
            )
        if "SELECT activo FROM core.map_campo_activo" in sql:
            objetivo = parametros["campo"]
            for campo, activo in self._mapa:
                if norm(campo) == objetivo:
                    return _Resultado([], escalar=activo)
            return _Resultado([], escalar=None)
        if "fuente_id, campo FROM core.dim_fuente" in sql:
            return _Resultado(self._fuentes)

        raise AssertionError(f"Consulta no reconocida por el doble: {sql}")


class _Resultado:
    def __init__(self, filas: list[tuple[Any, ...]], escalar: Any = None):
        self._filas = filas
        self._escalar = escalar

    def all(self) -> list[tuple[Any, ...]]:
        return self._filas

    def scalar(self) -> Any:
        return self._escalar


MAPA = [
    ("CASTILLA", "CASTILLA"),
    ("CASTILLA NORTE", "CASTILLA"),
    ("CHICHIMENE", "CHICHIMENE"),
    ("SURIA", "APIAY"),
]
FUENTES = [
    (1, "CASTILLA"),
    (2, "CASTILLA NORTE"),
    (3, "CHICHIMENE"),
    (4, "SURIA"),
    (5, None),  # ruido de ingesta: campo NULL (D-A3)
]


# ── norm ────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("  castilla  ", "CASTILLA"),
        ("Caño Sur Este", "CANO SUR ESTE"),
        ("CAÑO  SUR", "CANO SUR"),
        ("", ""),
        (None, ""),
    ],
)
def test_norm_pliega_acentos_y_colapsa_espacios(entrada: str, esperado: str) -> None:
    """Mismo criterio en ambos lados de cualquier comparación: el `.xlsx` viene
    en NFC y Postgres no normaliza, así que un match literal rompería campos en
    silencio ante una fuente en NFD."""
    assert norm(entrada) == esperado


# ── Composición del activo ──────────────────────────────────────────────────


@pytest.mark.unit
def test_fuentes_de_activo_agrupa_sus_campos() -> None:
    sesion = SesionFalsa(MAPA, FUENTES)
    assert fuentes_de_activo(sesion, "CASTILLA") == [1, 2]


@pytest.mark.unit
def test_fuentes_de_activo_ignora_campos_nulos() -> None:
    """D-A3: no se rescatan fuentes con `campo` NULL usando `nombre` — son
    ruido de ingesta, y el rescate alteraba cifras validadas (Chichimene sumaba
    +56.003 bl al colar 3 filas NULL homónimas)."""
    sesion = SesionFalsa(MAPA, FUENTES)
    assert 5 not in fuentes_de_activo(sesion, "CHICHIMENE")


@pytest.mark.unit
def test_activo_desconocido_devuelve_vacio() -> None:
    sesion = SesionFalsa(MAPA, FUENTES)
    assert fuentes_de_activo(sesion, "NO EXISTE") == []
    assert fuentes_de_activo(sesion, "") == []


@pytest.mark.unit
def test_campos_de_activo_lista_el_catalogo() -> None:
    sesion = SesionFalsa(MAPA, FUENTES)
    assert campos_de_activo(sesion, "castilla") == ["CASTILLA", "CASTILLA NORTE"]


@pytest.mark.unit
def test_activo_de_campo_es_la_direccion_inversa() -> None:
    sesion = SesionFalsa(MAPA, FUENTES)
    assert activo_de_campo(sesion, "Suria") == "APIAY"


@pytest.mark.unit
def test_campo_sin_activo_devuelve_none() -> None:
    """`None` es legítimo: un campo de un tercero o uno ambiguo sin veredicto."""
    sesion = SesionFalsa(MAPA, FUENTES)
    assert activo_de_campo(sesion, "AULLADOR") is None


# ── Caché e hilos (H3 / patrón A1) ──────────────────────────────────────────


@pytest.mark.unit
def test_el_indice_se_construye_una_sola_vez() -> None:
    sesion = SesionFalsa(MAPA, FUENTES)
    fuentes_de_activo(sesion, "CASTILLA")
    fuentes_de_activo(sesion, "CHICHIMENE")

    construcciones = [
        c
        for c in sesion.consultas
        if "campo_norm, activo FROM core.map_campo_activo" in c
    ]
    assert len(construcciones) == 1, "el índice debe cachearse por proceso"


@pytest.mark.unit
def test_hilos_concurrentes_construyen_el_indice_una_vez() -> None:
    """H3: en el origen estos globales se llenaban sin lock, así que N logins
    concurrentes construían el índice N veces — el mismo defecto que la regla
    A1 describe para `Eventos_OW.xlsx`."""
    sesion = SesionFalsa(MAPA, FUENTES)

    hilos = [
        threading.Thread(target=lambda: fuentes_de_activo(sesion, "CASTILLA"))
        for _ in range(8)
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    construcciones = [
        c
        for c in sesion.consultas
        if "campo_norm, activo FROM core.map_campo_activo" in c
    ]
    assert (
        len(construcciones) == 1
    ), f"lock + doble chequeo roto: {len(construcciones)} construcciones"
