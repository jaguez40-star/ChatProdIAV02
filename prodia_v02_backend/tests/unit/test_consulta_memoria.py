"""Memoria conversacional tipada."""

from __future__ import annotations

import threading

import pytest

from src.features.consulta.memoria import (
    ContextoAnalizar,
    ContextoCuantificar,
    ContextoJerarquizar,
    ContextoRanking,
    MemoriaEnProceso,
)

pytestmark = pytest.mark.unit


def test_guarda_y_recupera_por_conversacion() -> None:
    memoria = MemoriaEnProceso()
    ctx = ContextoCuantificar(entidad="CASTILLA", producto="gas")
    memoria.guardar("conv-1", ctx)

    assert memoria.obtener("conv-1") == ctx
    assert memoria.obtener("conv-2") is None


def test_sin_id_de_conversacion_no_guarda_ni_recupera() -> None:
    """Un turno sin hilo no debe contaminar la memoria de nadie."""
    memoria = MemoriaEnProceso()
    memoria.guardar(None, ContextoCuantificar(entidad="X"))
    assert memoria.obtener(None) is None


def test_olvidar_y_limpiar() -> None:
    memoria = MemoriaEnProceso()
    memoria.guardar("a", ContextoCuantificar(entidad="A"))
    memoria.guardar("b", ContextoCuantificar(entidad="B"))

    memoria.olvidar("a")
    assert memoria.obtener("a") is None
    assert memoria.obtener("b") is not None

    memoria.limpiar()
    assert memoria.obtener("b") is None


def test_el_contexto_de_ranking_no_tiene_entidad() -> None:
    """Es la asimetría que en el origen obligaba a que su drill cortara
    siempre: los drills de abajo hacían `ctx['entidad']` y reventaban con
    KeyError. Aquí el tipo lo impide en tiempo de compilación."""
    assert not hasattr(ContextoRanking(), "entidad")


def test_el_contexto_de_analizar_admite_entidad_nula() -> None:
    """Análisis global ECP: no hay una entidad concreta."""
    assert ContextoAnalizar().entidad is None


def test_los_contextos_son_inmutables() -> None:
    """Congelados a propósito: un contexto compartido entre hilos que alguien
    mutara daría respuestas cruzadas entre conversaciones."""
    ctx = ContextoJerarquizar(entidad="RUBIALES")
    with pytest.raises(AttributeError):
        ctx.entidad = "OTRA"  # type: ignore[misc]


def test_es_seguro_bajo_concurrencia() -> None:
    memoria = MemoriaEnProceso()
    barrera = threading.Barrier(8)

    def _escribir(n: int) -> None:
        barrera.wait()
        memoria.guardar(f"conv-{n}", ContextoCuantificar(entidad=f"E{n}"))

    hilos = [threading.Thread(target=_escribir, args=(i,)) for i in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    for i in range(8):
        ctx = memoria.obtener(f"conv-{i}")
        assert isinstance(ctx, ContextoCuantificar)
        assert ctx.entidad == f"E{i}"
