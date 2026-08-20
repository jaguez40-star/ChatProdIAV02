"""Puente entre el ETL (síncrono) y el flujo de eventos (asíncrono).

## El problema que resuelve

El ETL es código síncrono y bloqueante: abre el Excel, recorre 315.000 filas y escribe en
PostgreSQL. Si se ejecutara en el bucle de eventos, congelaría el servidor entero durante
minutos. Se lanza por tanto en un hilo aparte, y este módulo transporta sus eventos al
generador asíncrono que los emite.

## Por qué la cola tiene timeout

El origen usaba `queue.Queue.get()` **sin timeout** (G3): si el hilo moría de forma que no
llegara a poner el centinela, el generador quedaba colgado para siempre. Aquí la espera
tiene límite y se comprueba si el hilo sigue vivo, así que un hilo muerto termina el flujo
en vez de dejarlo esperando eternamente.

## La verdad sobre el commit

El evento final es el único que afirma si los datos quedaron guardados (G2). Se emite
**después** de que la transacción se haya confirmado o revertido, no antes: por eso el ETL
completo vive dentro del `with` de `get_prod_tx` y el `EventoFin` se construye al salir.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import anyio
from sqlalchemy.exc import SQLAlchemyError

from src.core.logger import get_logger
from src.features.ingesta.repositories import IngestaRepository
from src.features.ingesta.schemas import (
    CodigoErrorIngesta,
    EventoFin,
    EventoIngesta,
    ResultadoIngesta,
)
from src.features.ingesta.services import IngestaService
from src.shared.db_prod import get_prod_tx

logger = get_logger("ingesta.sse")

# Cuánto espera el generador antes de comprobar si el hilo sigue vivo.
ESPERA_MAXIMA_S = 1.0

# Centinela que marca el final del flujo.
_FIN = object()


class _EstadoDelTrabajo:
    """Lo que el hilo del ETL deja para el generador cuando termina."""

    def __init__(self) -> None:
        self.resultado: ResultadoIngesta | None = None
        self.error: Exception | None = None
        self.hoja_del_error: str | None = None


def _codigo_de(excepcion: Exception) -> CodigoErrorIngesta:
    """Traduce la excepción al código que el frontend sabe interpretar."""
    if isinstance(excepcion, SQLAlchemyError):
        return CodigoErrorIngesta.BD_NO_DISPONIBLE
    if isinstance(excepcion, (KeyError, ValueError, TypeError)):
        return CodigoErrorIngesta.HOJA_ILEGIBLE
    if isinstance(excepcion, OSError):
        return CodigoErrorIngesta.ARCHIVO_INVALIDO
    return CodigoErrorIngesta.ERROR_INTERNO


def _ejecutar_etl(
    ruta: Path, cola: queue.Queue[Any], estado: _EstadoDelTrabajo
) -> None:
    """Corre la ingesta completa en un hilo y publica sus eventos en la cola.

    Toda la ingesta ocurre dentro del `with`, así que al salir la transacción ya se
    confirmó (o se revirtió) y el resultado es una afirmación fiable.
    """
    hoja_en_curso: list[str | None] = [None]

    def publicar(evento: EventoIngesta) -> None:
        if evento.tipo == "hoja":
            hoja_en_curso[0] = evento.hoja
        cola.put(evento)

    try:
        for sesion in get_prod_tx():
            servicio = IngestaService(IngestaRepository(sesion), observador=publicar)
            estado.resultado = servicio.ingerir(ruta)
    except Exception as excepcion:  # noqa: BLE001 — se reporta, no se propaga al hilo
        estado.error = excepcion
        estado.hoja_del_error = hoja_en_curso[0]
        logger.error(
            "ingesta_revertida",
            archivo=ruta.name,
            hoja=hoja_en_curso[0],
            error=str(excepcion),
            exc_info=True,
        )
    finally:
        cola.put(_FIN)


def _evento_final(estado: _EstadoDelTrabajo) -> EventoFin:
    """El único evento que dice si los datos quedaron guardados."""
    if estado.error is None and estado.resultado is not None:
        return EventoFin(estado="confirmado", resultado=estado.resultado)
    excepcion = estado.error or RuntimeError("la ingesta terminó sin resultado")
    return EventoFin(
        estado="revertido",
        code=_codigo_de(excepcion),
        hoja=estado.hoja_del_error,
        detalle=(
            "La ingesta se revirtió: no se guardó ningún dato. "
            f"{str(excepcion)[:200]}"
        ),
    )


async def generar_eventos_de_ingesta(
    ruta: Path,
) -> AsyncGenerator[dict[str, str], None]:
    """Ejecuta el ETL en un hilo y emite sus eventos como SSE.

    Cada elemento es lo que `sse-starlette` espera: un dict con el nombre del evento y su
    contenido serializado. El nombre permite al cliente suscribirse por tipo en vez de
    inspeccionar el JSON.
    """
    cola: queue.Queue[Any] = queue.Queue()
    estado = _EstadoDelTrabajo()
    hilo = threading.Thread(
        target=_ejecutar_etl, args=(ruta, cola, estado), daemon=True
    )
    hilo.start()

    while True:
        try:
            elemento = await anyio.to_thread.run_sync(
                lambda: cola.get(timeout=ESPERA_MAXIMA_S)
            )
        except queue.Empty:
            # Nada nuevo. Si el hilo ya no vive y la cola sigue vacía, algo lo mató sin
            # llegar al `finally`: se corta en vez de esperar para siempre (G3).
            if not hilo.is_alive() and cola.empty():
                logger.warning("hilo_de_ingesta_terminado_sin_centinela")
                break
            continue

        if elemento is _FIN:
            break
        evento: EventoIngesta = elemento
        yield {"event": evento.tipo, "data": evento.model_dump_json()}

    final = _evento_final(estado)
    yield {"event": "fin", "data": final.model_dump_json()}
