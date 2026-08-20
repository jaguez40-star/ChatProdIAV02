"""Detector de formas EN dominio pero FUERA de capacidad.

Portado de `consulta_v2/no_soportado.py` (73 líneas). Espejo conceptual de
`dominio.py`: módulo PURO, sin BD ni LLM.

NO decide dominio —eso ya lo hizo el filtro— sino que reconoce, entre las
preguntas que YA cayeron en "desconocido", las que tienen la FORMA de una
capacidad que el motor todavía no construye, para poder declinar con honestidad
en vez de responder cualquier cosa.

🔑 **El gate de contexto vive FUERA de este módulo** (en el orquestador): solo
se consulta cuando ya hay una entidad en el hilo. Razón verificada por el
origen el 2026-08-03: en arranque frío, "¿cuántos días tiene un trimestre?"
(ajena) y "del primer trimestre ¿cuánto?" (de dominio) traen la MISMA palabra;
sin contexto no se puede afirmar "no soportado" sin mentir.

🔑 **El mensaje NUNCA termina en pregunta sí/no** (H1 del origen): un "sí" del
usuario caería en el drill de afirmación y se reescribiría a "acumulado de
{entidad}", entregando el acumulado en vez de lo ofrecido. Por eso el cierre
invita a una frase explícita.

Los regex se compilan en tiempo de import, lo que es CPU y no I/O: no viola la
regla de CERO I/O al importar (AP-2).
"""

from __future__ import annotations

import re
from typing import NamedTuple

from src.features.consulta.normaliza import norm


class _Forma(NamedTuple):
    codigo: str
    rx: re.Pattern[str]
    pidio: str
    puedo: str
    sugerencia: str


# H2: "promedio anual" / "promedio del año" es la referencia SOPORTADA
# `promedio_anio`, así que si el texto trae PROMEDIO la forma `anio` NO aplica.
_RX_PROMEDIO = re.compile(r"\bPROMEDIO\b")

# H3 del origen: sin abreviaturas de trimestre ("4T"/"Q1") — valor marginal y
# falsos positivos contra el catálogo de entidades.
_FORMAS: tuple[_Forma, ...] = (
    _Forma(
        "rango_dias",
        re.compile(
            r"\bENTRE\s+EL\s+\d+\s+Y\s+EL\s+\d+|\bDEL\s+\d+\s+AL\s+\d+|"
            r"\bLOS\s+\d+\s+DIAS|\b\d+\s+DIAS\s+DE\b|\bPRIMEROS\s+\d+\s+DIAS"
        ),
        "un rango de días",
        "el mes completo",
        "Si me nombras el mes, te doy esa cifra.",
    ),
    _Forma(
        "trimestre",
        re.compile(r"\bTRIMESTRE|\bTRIMESTRAL"),
        "un trimestre",
        "un mes puntual o el acumulado del año",
        "Dime el mes que te interesa, o pídeme el acumulado del año.",
    ),
    _Forma(
        "anio",
        re.compile(
            r"\bTODO\s+EL\s+ANO|\bEN\s+EL\s+ANO\s+20\d\d|\bDURANTE\s+20\d\d|\bANUAL\b"
        ),
        "un año completo",
        "un mes puntual o el acumulado del año",
        "Dime el mes que te interesa, o pídeme el acumulado del año.",
    ),
    _Forma(
        "semana",
        re.compile(r"\bSEMANA|\bSEMANAL"),
        "una semana",
        "el mes completo",
        "Si me nombras el mes, te doy esa cifra.",
    ),
)


def detectar(texto: str) -> str | None:
    """Código de la 1ª forma no-soportada que calza, o `None`. Puro."""
    t = norm(texto or "")
    for forma in _FORMAS:
        if forma.codigo == "anio" and _RX_PROMEDIO.search(t):
            continue  # H2: es la referencia promedio_anio, que SÍ se soporta.
        if forma.rx.search(t):
            return forma.codigo
    return None


def mensaje(codigo: str, entidad: str) -> str:
    """Rechazo honesto: nombra la entidad, dice qué pidió, qué SÍ puede y cómo
    reformular. Determinista — jamás pasa por el LLM."""
    tabla = {f.codigo: (f.pidio, f.puedo, f.sugerencia) for f in _FORMAS}
    pidio, puedo, sugerencia = tabla.get(
        codigo,
        ("ese periodo", "el mes completo", "Si me nombras el mes, te doy esa cifra."),
    )
    return f"Sobre {entidad}: me pediste {pidio} y por ahora solo puedo darte {puedo}. {sugerencia}"
