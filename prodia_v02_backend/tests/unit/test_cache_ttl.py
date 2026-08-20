"""Tests de la caché TTL + single-flight (regla A4).

Lo que se protege aquí no es "que guarde valores", sino las tres propiedades
que hacen que el prefetch del login no dispare N generaciones de LLM.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from src.shared.cache_ttl import CacheTTL, clave_de


def SIEMPRE(_valor: Any) -> bool:  # noqa: N802 — constante-predicado del test
    """Todo resultado es cacheable (para los tests que no prueban ese filtro)."""
    return True


@pytest.mark.unit
def test_segunda_llamada_no_recalcula() -> None:
    cache: CacheTTL[int] = CacheTTL(ttl_s=60)
    llamadas = 0

    def calcular() -> int:
        nonlocal llamadas
        llamadas += 1
        return 42

    assert cache.obtener_o_calcular("k", calcular, SIEMPRE) == 42
    assert cache.obtener_o_calcular("k", calcular, SIEMPRE) == 42
    assert llamadas == 1


@pytest.mark.unit
def test_entrada_expirada_se_recalcula() -> None:
    cache: CacheTTL[int] = CacheTTL(ttl_s=0)  # expira de inmediato
    llamadas = 0

    def calcular() -> int:
        nonlocal llamadas
        llamadas += 1
        return llamadas

    assert cache.obtener_o_calcular("k", calcular, SIEMPRE) == 1
    time.sleep(0.01)
    assert cache.obtener_o_calcular("k", calcular, SIEMPRE) == 2


@pytest.mark.unit
def test_un_error_no_se_cachea() -> None:
    """Cachear un error dejaría el panel roto durante todo el TTL — 15 minutos
    de fallo congelado sin posibilidad de reintentar."""
    cache: CacheTTL[dict[str, Any]] = CacheTTL(ttl_s=60)
    llamadas = 0

    def calcular() -> dict[str, Any]:
        nonlocal llamadas
        llamadas += 1
        return {"encontrada": False}

    def es_bueno(valor: dict[str, Any]) -> bool:
        return valor.get("encontrada") is not False

    cache.obtener_o_calcular("k", calcular, es_bueno)
    cache.obtener_o_calcular("k", calcular, es_bueno)
    assert llamadas == 2, "un error no debe quedar cacheado"


@pytest.mark.unit
def test_single_flight_una_sola_ejecucion_con_hilos_concurrentes() -> None:
    """La propiedad crítica de A4: N peticiones simultáneas sobre la MISMA
    clave producen UNA sola generación, no N.

    Sin single-flight, el TTL no basta: los N hilos ven la caché vacía a la vez
    y todos llaman al LLM antes de que el primero termine de escribir.
    """
    cache: CacheTTL[int] = CacheTTL(ttl_s=60)
    llamadas = 0
    candado = threading.Lock()

    def calcular() -> int:
        nonlocal llamadas
        with candado:
            llamadas += 1
        time.sleep(0.05)  # simula una generación lenta
        return 7

    hilos = [
        threading.Thread(
            target=lambda: cache.obtener_o_calcular("misma", calcular, SIEMPRE)
        )
        for _ in range(8)
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert llamadas == 1, f"single-flight roto: {llamadas} generaciones en paralelo"


@pytest.mark.unit
def test_claves_distintas_no_se_pisan() -> None:
    cache: CacheTTL[str] = CacheTTL(ttl_s=60)
    assert cache.obtener_o_calcular("a", lambda: "A", SIEMPRE) == "A"
    assert cache.obtener_o_calcular("b", lambda: "B", SIEMPRE) == "B"


@pytest.mark.unit
def test_clave_ignora_el_orden_de_los_parametros() -> None:
    """`?entidad=X&nivel=campo` y `?nivel=campo&entidad=X` son la misma
    consulta: deben compartir entrada de caché."""
    uno = clave_de("/analisis/ejecutivo", {"entidad": "CASTILLA", "nivel": "campo"})
    otro = clave_de("/analisis/ejecutivo", {"nivel": "campo", "entidad": "CASTILLA"})
    assert uno == otro


@pytest.mark.unit
def test_clave_descarta_parametros_vacios() -> None:
    """`entidad=""` no es lo mismo que no mandar `entidad` — el origen ya
    filtraba los vacíos al construir los params del proxy."""
    con_vacio = clave_de("/analisis/desempeno", {"entidad": "", "nivel": None})
    sin_nada = clave_de("/analisis/desempeno", {})
    assert con_vacio == sin_nada
