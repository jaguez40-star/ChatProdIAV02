"""Carga perezosa de los `config/*.yaml` del Motor Q.

**Dos correcciones sobre el sistema de origen, ambas deliberadas:**

1. **CERO I/O en tiempo de import (H4/AP-2).** El origen carga el catálogo a
   nivel de módulo (`respuesta_cuantificar.py:27` ejecuta `_catalogo.get()` al
   importarse) para tener un "arranque ruidoso si el YAML está mal". El
   objetivo es bueno; el momento, no: aquí el hook `gen-types-check` importa
   la app entera en cada `git commit` del equipo, así que leer disco al
   importar colgaría commits ajenos. La validación ruidosa se conserva, pero
   se dispara desde el `lifespan` con `validar_configuracion()`.

2. **Lock con doble chequeo (A1).** El origen usa `global X; if X is not None`
   sin lock: bajo concurrencia, N peticiones simultáneas parsean el mismo YAML
   N veces. Es idempotente —no corrompe— pero desperdicia trabajo en el primer
   pico de tráfico. Mismo patrón que `shared/catalogo_entidades` de F2.

Editar un YAML sigue exigiendo reiniciar el backend: la caché no se invalida.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import yaml

_DIR_CONFIG = Path(__file__).resolve().parent / "config"

_CACHE: dict[str, Any] = {}
_LOCK = threading.Lock()


def cargar(nombre: str) -> Any:
    """Devuelve el YAML `nombre` parseado, cacheado por proceso.

    `nombre` es el nombre del fichero dentro de `config/` (p. ej.
    `"patrones_grupo.yaml"`).
    """
    en_cache = _CACHE.get(nombre)
    if en_cache is not None:
        return en_cache

    with _LOCK:
        # Doble chequeo: otro hilo pudo cargarlo mientras esperábamos el lock.
        en_cache = _CACHE.get(nombre)
        if en_cache is not None:
            return en_cache

        ruta = _DIR_CONFIG / nombre
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
        if datos is None:
            raise ValueError(f"{nombre}: YAML vacío o mal formado ({ruta})")
        _CACHE[nombre] = datos
        return datos


def reset_cache() -> None:
    """Vacía la caché. Solo para tests — en producción nada la invalida."""
    with _LOCK:
        _CACHE.clear()
