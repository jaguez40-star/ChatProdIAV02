"""Catálogo de variables cuantificables — cargador + validación.

Portado de `consulta_v2/cuantificar/catalogo.py` (51 líneas). Solo CARGADOR y
VALIDADOR: los datos viven en `config/variables_cuantificables.yaml`.

**Falla RUIDOSO si el YAML está mal**, y eso se conserva del origen: un
catálogo corrupto en silencio es peor que un arranque roto, porque
`cuantificar` respondería con datos a medias sin avisar a nadie.

Lo que **cambia** respecto al origen es *cuándo* falla. Allí
`respuesta_cuantificar.py:27` fuerza la carga al importarse; aquí eso violaría
la regla de CERO I/O en tiempo de import (H4/AP-2), así que la validación la
dispara el `lifespan` llamando a `validar()`. Se conserva el arranque ruidoso
sin colgar el `git commit` de nadie.
"""

from __future__ import annotations

from typing import Any

from src.features.consulta import config_yaml

_ARCHIVO = "variables_cuantificables.yaml"

_SECCIONES_REQUERIDAS = (
    "meta",
    "referencias",
    "niveles",
    "productos",
    "derivadas",
    "conteos",
    "robustez_especialista",
    "no_soportado",
    "reglas",
)


def _validar(cfg: dict[str, Any]) -> None:
    """Comprueba que el catálogo trae lo mínimo para responder.

    Las tres reglas son del origen y cada una protege una respuesta concreta:
    sin `productos.produccion_crudo` no hay núcleo, y sin la referencia `PPTO`
    no hay contra qué comparar por defecto.
    """
    faltantes = [s for s in _SECCIONES_REQUERIDAS if s not in cfg]
    if faltantes:
        raise ValueError(f"{_ARCHIVO}: faltan secciones {faltantes}")

    productos = cfg.get("productos") or {}
    if "produccion_crudo" not in productos:
        raise ValueError(
            f"{_ARCHIVO}: falta 'productos.produccion_crudo' (núcleo Fase 1)"
        )

    crudo = productos["produccion_crudo"]
    for campo in ("unidad", "fuente", "referencias", "granos"):
        if campo not in crudo:
            raise ValueError(f"{_ARCHIVO}: produccion_crudo sin '{campo}'")

    if "PPTO" not in (cfg.get("referencias") or {}):
        raise ValueError(f"{_ARCHIVO}: falta la referencia 'PPTO' (default de Fase 1)")


def get() -> dict[str, Any]:
    """Catálogo completo, cargado y validado. Lanza `ValueError` si es inválido."""
    cfg = config_yaml.cargar(_ARCHIVO)
    if not isinstance(cfg, dict):
        raise ValueError(f"{_ARCHIVO}: YAML vacío o mal formado")
    _validar(cfg)
    return cfg


def validar() -> None:
    """Fuerza la carga y validación. La llama el `lifespan` para conservar el
    arranque ruidoso del origen sin pagar I/O en tiempo de import."""
    get()
