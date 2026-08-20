"""Capa 1 del clasificador de grupo — regex puro, SIN LLM.

Portado de `consulta_v2/patrones.py` (82 líneas). Este módulo es solo el
CARGADOR: los patrones viven en `config/patrones_grupo.yaml` (cero datos aquí,
cero lógica allá). Añadir un patrón al YAML exige reiniciar el backend.

**Reglas de resolución, en este orden exacto:**

1. `precedencia_maxima` primero — resuelve la trampa de la huella: "¿cuántos
   días con reporte hay de X?" trae CUANTOS pero pregunta por disponibilidad,
   no por una cifra.
2. Un solo grupo atrapa → ese grupo.
3. Dos o más → `precedencia_colision` (analizar > cuantificar > jerarquizar).
4. Ninguno → `None`, y baja a la Capa 2 (LLM).
"""

from __future__ import annotations

import re
import threading
from typing import Any, NamedTuple

from src.features.consulta import config_yaml
from src.features.consulta.normaliza import norm

_ARCHIVO = "patrones_grupo.yaml"


class _Compilados(NamedTuple):
    """Los patrones ya compilados. Se guarda el texto original del patrón
    porque es lo que viaja al cliente como `patrones_atrapados` y lo que
    `es_anclado` compara contra la lista de anclados."""

    maximos: list[tuple[str, re.Pattern[str], str]]
    grupos: dict[str, list[tuple[re.Pattern[str], str]]]
    precedencia: list[str]
    anclados: frozenset[str]


_CACHE: _Compilados | None = None
_LOCK = threading.Lock()


def _compilar() -> _Compilados:
    """Compila los regex del YAML. Bajo lock con doble chequeo (A1): sin él, N
    peticiones concurrentes compilarían los mismos ~90 patrones N veces."""
    global _CACHE

    # Se lee a una local en cada chequeo en vez de comprobar `_CACHE` dos
    # veces: mypy razona en un solo hilo, así que tras el primer `is not None`
    # da por imposible el segundo y marca la rama como inalcanzable. Con dos
    # locales distintas el análisis es correcto y no hace falta un `ignore`.
    en_cache = _CACHE
    if en_cache is not None:
        return en_cache

    with _LOCK:
        # Segundo chequeo: otro hilo pudo compilar mientras esperábamos.
        en_cache = _CACHE
        if en_cache is not None:
            return en_cache

        cfg: dict[str, Any] = config_yaml.cargar(_ARCHIVO)

        maximos: list[tuple[str, re.Pattern[str], str]] = []
        for grupo, pats in (cfg.get("precedencia_maxima") or {}).items():
            for patron in pats:
                maximos.append((str(grupo), re.compile(str(patron)), str(patron)))

        grupos: dict[str, list[tuple[re.Pattern[str], str]]] = {}
        for grupo, pats in (cfg.get("grupos") or {}).items():
            grupos[str(grupo)] = [(re.compile(str(p)), str(p)) for p in pats]

        compilados = _Compilados(
            maximos=maximos,
            grupos=grupos,
            precedencia=[str(g) for g in cfg["precedencia_colision"]],
            anclados=frozenset(str(p) for p in (cfg.get("patrones_anclados") or [])),
        )
        _CACHE = compilados
        return compilados


def clasificar_capa1(texto: str) -> tuple[str | None, list[str]]:
    """`(grupo | None, patrones_atrapados)`. Determinista.

    `None` significa "la regex no decidió" y obliga a bajar a la Capa 2.
    """
    t = norm(texto)
    if not t:
        return None, []

    c = _compilar()

    # 1) Precedencia máxima: gana ANTES de evaluar los grupos.
    for grupo, rx, patron in c.maximos:
        if rx.search(t):
            return grupo, [patron]

    # 2) Evaluación por grupo.
    atrapados: dict[str, list[str]] = {}
    for grupo, pares in c.grupos.items():
        hits = [patron for rx, patron in pares if rx.search(t)]
        if hits:
            atrapados[grupo] = hits

    if not atrapados:
        return None, []
    if len(atrapados) == 1:
        grupo = next(iter(atrapados))
        return grupo, atrapados[grupo]

    # 3) Colisión → precedencia fija.
    for grupo in c.precedencia:
        if grupo in atrapados:
            return grupo, atrapados[grupo]

    # Inalcanzable con el YAML actual (la precedencia cubre los 3 grupos);
    # se conserva del origen como red defensiva.
    return None, []


def es_anclado(patrones_lista: list[str] | None) -> bool:
    """¿Alguno de los patrones que atrapó la Capa 1 es de dominio-anclado?

    Los anclados se saltan el filtro de dominio: su sola presencia ya prueba
    que la pregunta es del negocio.

    Nota del origen (H-H): en una colisión, `clasificar_capa1` devuelve solo
    los patrones del grupo GANADOR. El vocabulario cubre los casos en que un
    patrón anclado quedó en el grupo perdedor, porque todos mencionan
    CAMPO/POZO/ACTIVO, que están en el vocabulario.
    """
    if not patrones_lista:
        return False
    anclados = _compilar().anclados
    return any(p in anclados for p in patrones_lista)


def reset_cache() -> None:
    """Vacía la caché de patrones compilados. Solo para tests."""
    global _CACHE
    with _LOCK:
        _CACHE = None
    config_yaml.reset_cache()
