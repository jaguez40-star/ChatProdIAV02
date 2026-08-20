"""Tests del puente hilo→SSE — sin PostgreSQL y sin archivos reales.

Lo que se prueba aquí no es el ETL (eso ya lo cubren los tests del servicio) sino las tres
promesas del puente: que el flujo **siempre termina** aunque el hilo muera mal (G3), que el
evento final dice la verdad sobre el commit (G2), y que el código de error que recibe el
frontend distingue "la base no está" de "la hoja no se pudo leer".

El ETL se sustituye por una función que publica en la cola lo que cada caso necesita: montar
un libro real solo para comprobar el transporte sería lento y no probaría nada nuevo.
"""

from __future__ import annotations

import datetime as dt
import queue
import threading
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.exc import OperationalError

from src.features.ingesta import sse
from src.features.ingesta.schemas import (
    CodigoErrorIngesta,
    EventoHoja,
    ResultadoIngesta,
)

RUTA = Path("20260101_r.xlsm")


def _resultado() -> ResultadoIngesta:
    return ResultadoIngesta(
        reporte_id=1042,
        fecha_reporte=dt.date(2026, 1, 1),
        tipo_archivo="STD",
        tiene_raw=False,
        archivo=RUTA.name,
        hojas=[],
        filas_por_destino={},
        tablas_vacias=[],
    )


async def _recolectar(ruta: Path = RUTA) -> list[dict[str, str]]:
    return [evento async for evento in sse.generar_eventos_de_ingesta(ruta)]


# ── Traducción del error ─────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    ("excepcion", "esperado"),
    [
        (
            OperationalError("SELECT 1", {}, Exception("caída")),
            CodigoErrorIngesta.BD_NO_DISPONIBLE,
        ),
        (KeyError("FECHA"), CodigoErrorIngesta.HOJA_ILEGIBLE),
        (ValueError("layout"), CodigoErrorIngesta.HOJA_ILEGIBLE),
        (OSError("archivo corrupto"), CodigoErrorIngesta.ARCHIVO_INVALIDO),
        (RuntimeError("vaya"), CodigoErrorIngesta.ERROR_INTERNO),
    ],
)
def test_cada_fallo_llega_al_frontend_con_su_codigo(
    excepcion: Exception, esperado: CodigoErrorIngesta
) -> None:
    """El frontend decide qué decirle al usuario según el código: si todo llegara como
    ERROR_INTERNO, "la base no está" y "esta hoja cambió" se verían igual."""
    assert sse._codigo_de(excepcion) == esperado


# ── El evento final (G2) ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_el_final_solo_dice_confirmado_si_hubo_resultado_y_no_hubo_error() -> None:
    estado = sse._EstadoDelTrabajo()
    estado.resultado = _resultado()

    final = sse._evento_final(estado)

    assert final.estado == "confirmado"
    assert final.resultado is not None


@pytest.mark.unit
def test_un_hilo_que_termina_sin_resultado_ni_error_se_reporta_revertido() -> None:
    """Nunca se afirma que los datos quedaron guardados por defecto: sin resultado, la
    única respuesta honesta es que se revirtió."""
    final = sse._evento_final(sse._EstadoDelTrabajo())

    assert final.estado == "revertido"
    assert final.code == CodigoErrorIngesta.ERROR_INTERNO


@pytest.mark.unit
def test_el_final_revertido_nombra_la_hoja_donde_se_cayo() -> None:
    estado = sse._EstadoDelTrabajo()
    estado.error = ValueError("la fila 37 ya no existe")
    estado.hoja_del_error = "INICIO"

    final = sse._evento_final(estado)

    assert final.hoja == "INICIO"
    assert "no se guardó ningún dato" in (final.detalle or "")


# ── El flujo completo ────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_los_eventos_del_hilo_salen_en_orden_y_cierran_con_fin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def etl_falso(
        _: Path, cola: queue.Queue[Any], estado: sse._EstadoDelTrabajo
    ) -> None:
        cola.put(EventoHoja(hoja="INICIO", estado="procesando"))
        cola.put(EventoHoja(hoja="INICIO", estado="procesada", filas=3))
        estado.resultado = _resultado()
        cola.put(sse._FIN)

    monkeypatch.setattr(sse, "_ejecutar_etl", etl_falso)

    eventos = await _recolectar()

    assert [e["event"] for e in eventos] == ["hoja", "hoja", "fin"]
    assert '"estado":"confirmado"' in eventos[-1]["data"]


@pytest.mark.unit
async def test_un_hilo_que_muere_sin_centinela_no_cuelga_el_flujo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """G3: el origen esperaba en `queue.get()` sin timeout. Si el hilo moría sin poner el
    centinela —un `os._exit`, un OOM, un crash de openpyxl— la conexión SSE se quedaba
    abierta para siempre y el usuario veía una barra de progreso eterna."""

    def etl_que_desaparece(
        _: Path, cola: queue.Queue[Any], __: sse._EstadoDelTrabajo
    ) -> None:
        cola.put(EventoHoja(hoja="INICIO", estado="procesando"))
        # Y se acaba sin poner `_FIN`.

    monkeypatch.setattr(sse, "_ejecutar_etl", etl_que_desaparece)
    monkeypatch.setattr(sse, "ESPERA_MAXIMA_S", 0.05)

    eventos = await _recolectar()

    assert eventos[-1]["event"] == "fin"
    assert '"estado":"revertido"' in eventos[-1]["data"]


@pytest.mark.unit
async def test_el_ultimo_evento_es_fin_aunque_el_etl_reviente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El `finally` del hilo pone el centinela pase lo que pase; el generador traduce el
    error a un `fin` con código, en vez de cortar la conexión sin explicación."""

    def etl_que_revienta(*_: Any, **__: Any) -> None:
        raise OperationalError("INSERT ...", {}, Exception("conexión perdida"))

    monkeypatch.setattr(sse, "get_prod_tx", etl_que_revienta)

    eventos = await _recolectar()

    assert eventos[-1]["event"] == "fin"
    assert CodigoErrorIngesta.BD_NO_DISPONIBLE.value in eventos[-1]["data"]


@pytest.mark.unit
async def test_el_hilo_del_etl_es_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si no lo fuera, un ETL colgado impediría apagar el servidor."""
    hilos: list[threading.Thread] = []
    original = threading.Thread

    def espiar(*args: Any, **kwargs: Any) -> threading.Thread:
        hilo = original(*args, **kwargs)
        hilos.append(hilo)
        return hilo

    monkeypatch.setattr(sse.threading, "Thread", espiar)
    monkeypatch.setattr(
        sse, "_ejecutar_etl", lambda _, cola, __: cola.put(sse._FIN)  # noqa: ARG005
    )

    await _recolectar()

    assert hilos and hilos[0].daemon
