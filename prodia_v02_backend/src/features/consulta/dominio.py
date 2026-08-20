"""Filtro de dominio — ¿la pregunta menciona vocabulario de producción?

Portado de `consulta_v2/dominio.py` (64 líneas). Módulo PURO: solo depende de
`normaliza` (sin BD, sin LLM), así que se testea sin dobles.

Es el segundo criterio del filtro; el primero es detectar una entidad conocida.

**DOS NIVELES, no una lista plana** (decisión del origen, 2026-08-02): "campos"
es a la vez entidad del modelo y sustantivo común del español ("los campos de
un formulario"), así que es evidencia DÉBIL y exige que la Capa 2 confirme.
"""

from __future__ import annotations

import re

from src.features.consulta import config_yaml
from src.features.consulta.normaliza import norm

_ARCHIVO = "vocabulario_dominio.yaml"

NivelDominio = str  # "fuerte" | "estructural"


def _compilar(lista: object) -> re.Pattern[str] | None:
    """Une los fragmentos en un solo regex `\\b(a|b|...)\\b`.

    `None` si la lista viene vacía — un regex vacío casaría con todo.
    """
    if not isinstance(lista, list):
        return None
    items = [str(v) for v in lista if v]
    return re.compile(r"\b(" + "|".join(items) + r")\b") if items else None


def _regex() -> dict[str, re.Pattern[str] | None]:
    """Compila ambas listas. La caché del YAML ya es perezosa y va bajo lock."""
    cfg = config_yaml.cargar(_ARCHIVO)
    return {
        "fuerte": _compilar(cfg.get("vocabulario")),
        "estructural": _compilar(cfg.get("estructural")),
    }


def nivel_dominio(texto: str) -> NivelDominio | None:
    """Cuánta certeza de dominio aporta el vocabulario.

    - `"fuerte"` — término inequívoco (CRUDO, P50, EBITDA…): enruta directo,
      sin gastar una llamada al LLM.
    - `"estructural"` — CAMPOS/POZOS/ACTIVOS: entidad del modelo **y** español
      común, así que la Capa 2 confirma. Si además hay una palabra fuerte,
      gana `"fuerte"` (D3 del origen) — de ahí que se compruebe primero.
    - `None` — ninguna palabra del vocabulario.
    """
    compilados = _regex()
    n = norm(texto)
    fuerte = compilados["fuerte"]
    if fuerte is not None and fuerte.search(n):
        return "fuerte"
    estructural = compilados["estructural"]
    if estructural is not None and estructural.search(n):
        return "estructural"
    return None


def hay_palabra_dominio(texto: str) -> bool:
    """¿Hay CUALQUIER palabra de dominio, fuerte o estructural?

    Se conserva del origen porque expresa la pregunta binaria original del
    filtro y la usan sus tests portados.
    """
    return nivel_dominio(texto) is not None
