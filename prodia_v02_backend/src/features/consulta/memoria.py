"""Memoria conversacional del Motor Q — contexto tipado.

Portado de `maquina_q.py:30-56` (`_CTX = {}`), con dos cambios de fondo.

**1. El contexto es una unión discriminada, no un `dict` suelto.**

En el origen conviven CUATRO formas distintas en la misma variable, sin tipo
común, y dos de ellas —ranking y analizar— **no llevan la clave `entidad`**.
Eso obliga a que sus drills corten con un `return` propio: si la ejecución
siguiera hacia abajo, los drills N1/N2 harían `ctx['entidad']` y reventarían
con `KeyError`. El propio origen lo documenta como la razón de ese orden.

Al tipar el contexto esa fragilidad desaparece: `mypy` impide leer `entidad`
de un contexto que no la tiene. **El orden de los drills se conserva igual**,
porque además de defensivo es semántico (ver `drills.py`).

**2. Persiste fuera del proceso.**

El origen guarda en un `dict` de módulo, sin TTL ni lock: reiniciar el backend
borra toda conversación, y con varios workers cada uno tendría su memoria. El
panel "Historial" del cascarón F1a exige lo contrario. Este módulo define el
contrato; el almacén llega con la migración `0004`.

**Regla madre del origen, conservada**: la memoria nunca tumba la respuesta.
Quien la actualice debe tragarse cualquier excepción.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True, slots=True)
class ContextoJerarquizar:
    """Tras responder estructura. `ofrece_produccion` marca que el cierre
    invitó a ver cifras, así que un "sí" debe ir a producción."""

    grupo: Literal["jerarquizar"] = "jerarquizar"
    entidad: str = ""
    nivel: str | None = None
    hijos: frozenset[str] = field(default_factory=frozenset)
    ofrece_produccion: bool = False


@dataclass(frozen=True, slots=True)
class ContextoCuantificar:
    """Tras dar una cifra. Conserva el producto para que un "acumulado" tras
    un N1 de gas no vuelva a crudo (AF9 del origen)."""

    grupo: Literal["cuantificar"] = "cuantificar"
    entidad: str = ""
    producto: str = "crudo"


@dataclass(frozen=True, slots=True)
class ContextoRanking:
    """Tras un ranking (N5). **No lleva `entidad`**: el ranking es global, no
    de una entidad — por eso su drill corta siempre."""

    grupo: Literal["cuantificar"] = "cuantificar"
    subgrupo: Literal["ranking"] = "ranking"
    nivel_ranking: str = "campo"
    metrica: str = "gap"
    direccion: str = "top"
    producto: str = "crudo"


@dataclass(frozen=True, slots=True)
class ContextoAnalizar:
    """Tras un análisis. `entidad` puede ser `None` (análisis global ECP), y
    `vp` recuerda la vicepresidencia que ofreció un declinar de referencia —
    sin ella, elegir "la vicepresidencia" repetía el campo y entraba en bucle.
    """

    grupo: Literal["analizar"] = "analizar"
    entidad: str | None = None
    sub: str = "causal"
    producto: str | None = None
    vp: str | None = None


ContextoConversacion = (
    ContextoJerarquizar | ContextoCuantificar | ContextoRanking | ContextoAnalizar
)


class MemoriaEnProceso:
    """Almacén por proceso, protegido por lock.

    Es el mismo alcance que el origen —se pierde al reiniciar— pero con la
    interfaz que usará el almacén persistente, para que cambiarlo no toque a
    los llamadores. Bajo lock porque `dict` no garantiza consistencia entre
    lectura y escritura compuestas bajo concurrencia.
    """

    def __init__(self) -> None:
        self._datos: dict[str, ContextoConversacion] = {}
        self._lock = threading.Lock()

    def obtener(self, conversacion_id: str | None) -> ContextoConversacion | None:
        if not conversacion_id:
            return None
        with self._lock:
            return self._datos.get(conversacion_id)

    def guardar(self, conversacion_id: str | None, ctx: ContextoConversacion) -> None:
        if not conversacion_id:
            return
        with self._lock:
            self._datos[conversacion_id] = ctx

    def olvidar(self, conversacion_id: str) -> None:
        with self._lock:
            self._datos.pop(conversacion_id, None)

    def limpiar(self) -> None:
        """Vacía la memoria. Para tests y para el arranque."""
        with self._lock:
            self._datos.clear()


MEMORIA = MemoriaEnProceso()
