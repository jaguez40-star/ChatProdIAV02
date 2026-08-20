"""Caché TTL + single-flight para los paneles caros de Análisis (regla A4).

**Por qué vive aquí y no en un proxy.** En el sistema viejo esta caché estaba
en el proxy Flask (`routes/api.py:153-228`), no en el backend FastAPI. El
propio comentario del origen lo admite: *"/analisis/ejecutivo NO tiene caché en
FastAPI (verificado) → cada petición re-invoca a Gemma (~180 s)"*. Como el
proxy desaparece al migrar, sin este módulo el prefetch del login dispararía N
generaciones de LLM en paralelo; Ollama las serializa y la última revienta el
timeout. La regla A4 del CLAUDE.md existe por ese incidente.

Dos mecanismos, no uno:

1. **TTL** — el payload se reutiliza N segundos (default 900 = 15 min; el
   reporte de producción cambia una vez al día).
2. **Single-flight** — si M peticiones piden la MISMA clave y no hay caché,
   solo UNA ejecuta el cálculo; las demás esperan y reciben su resultado. Sin
   esto, el TTL no evita la estampida inicial: N peticiones simultáneas ven la
   caché vacía a la vez y todas llaman al LLM.

**Solo se cachean respuestas buenas.** Cachear un error dejaría el panel
mostrando basura sin reintentar hasta que expire el TTL — 15 minutos de fallo
congelado. El criterio de cacheabilidad se pasa por parámetro porque cada
endpoint sabe qué es "bueno" para él.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class CacheTTL(Generic[T]):
    """Caché en memoria de proceso con expiración y single-flight por clave.

    No es un caché distribuido ni pretende serlo: el backend de ProdIA corre
    como un solo proceso y el dato cacheado es un panel de lectura que se
    regenera solo. Si algún día hay varios workers, cada uno tendrá el suyo —
    aceptable, porque el coste que evita (una generación de LLM) es por worker.
    """

    def __init__(self, ttl_s: int) -> None:
        self._ttl_s = ttl_s
        # `_guard` protege los dos diccionarios de abajo; los locks de
        # `_en_vuelo` protegen cada cálculo individual. Son niveles distintos:
        # nunca se ejecuta el cálculo con `_guard` tomado (bloquearía a todas
        # las claves, no solo a la que se está calculando).
        self._guard = threading.Lock()
        self._entradas: dict[str, tuple[float, T]] = {}
        self._en_vuelo: dict[str, threading.Lock] = {}

    def _leer(self, clave: str) -> tuple[T] | None:
        """Devuelve `(valor,)` si hay entrada viva, `None` si no hay o expiró.

        Se envuelve en tupla para poder distinguir "cacheado y vale None" de
        "no hay nada cacheado" — un `None` desnudo confundiría ambos casos.
        """
        with self._guard:
            entrada = self._entradas.get(clave)
            if entrada is None:
                return None
            expira_en, valor = entrada
            if expira_en <= time.time():
                del self._entradas[clave]
                return None
            return (valor,)

    def _lock_de(self, clave: str) -> threading.Lock:
        with self._guard:
            lock = self._en_vuelo.get(clave)
            if lock is None:
                lock = threading.Lock()
                self._en_vuelo[clave] = lock
            return lock

    def obtener_o_calcular(
        self,
        clave: str,
        calcular: Callable[[], T],
        es_cacheable: Callable[[T], bool],
    ) -> T:
        """Devuelve el valor cacheado o ejecuta `calcular` una sola vez.

        `es_cacheable` decide si el resultado merece guardarse: un error o una
        respuesta vacía se devuelven al llamador pero NO se cachean, para que
        la siguiente petición reintente en vez de heredar el fallo.
        """
        cacheado = self._leer(clave)
        if cacheado is not None:
            return cacheado[0]

        # Single-flight: solo un hilo por clave entra a calcular.
        with self._lock_de(clave):
            # Doble chequeo: otro hilo pudo llenar la caché mientras
            # esperábamos el lock. Sin esto, los hilos encolados recalcularían
            # en fila justo lo que el primero acaba de dejar listo.
            cacheado = self._leer(clave)
            if cacheado is not None:
                return cacheado[0]

            valor = calcular()

            if es_cacheable(valor):
                with self._guard:
                    self._entradas[clave] = (time.time() + self._ttl_s, valor)
            return valor

    def invalidar(self) -> None:
        """Vacía la caché. Para tests y para un eventual endpoint de refresco."""
        with self._guard:
            self._entradas.clear()


def clave_de(ruta: str, params: dict[str, object]) -> str:
    """Clave estable a partir de la ruta y sus parámetros.

    Los parámetros se ORDENAN: `?entidad=X&nivel=campo` y `?nivel=campo&entidad=X`
    son la misma consulta y deben compartir entrada de caché. Los valores vacíos
    se descartan por el mismo motivo — el origen ya lo hacía al construir los
    params del proxy (`routes/api.py:251`), porque `entidad=""` no es lo mismo
    que no mandar `entidad`.
    """
    utiles = {k: v for k, v in params.items() if v not in (None, "")}
    return ruta + "?" + "&".join(f"{k}={utiles[k]}" for k in sorted(utiles))
