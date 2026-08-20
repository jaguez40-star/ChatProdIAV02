"""Sub-intenciones de "analizar" — Python puro, sin LLM.

Portado de `consulta_v2/analizar/subrouter.py` (40 líneas).

El clasificador mete cinco preguntas distintas bajo "analizar"; este módulo
elige la ruta. La **precedencia es fija y significativa**:

    economia > diferidas > proyeccion > referencia > causal (default)

- `economia` y `diferidas` van primero porque leen **fuentes distintas**
  (EBITDA y el histórico de diferidas): si la pregunta las nombra, ninguna otra
  ruta puede responderla.
- `referencia` va **DEBAJO de proyeccion** a propósito: *"¿vamos a llegar al
  P50?"* sigue siendo una proyección. Solo las preguntas que piden LA CIFRA del
  P50 caen en referencia.
- `referencia` exige además que NO haya señal causal explícita: "¿por qué no
  llegamos al P50?" pregunta por la causa, no por el número.
"""

from __future__ import annotations

from src.features.consulta.normaliza import norm

_PROY = (
    "COMO VAMOS",
    "VAMOS A LLEGAR",
    "VAMOS A CERRAR",
    "VAMOS A ALCANZAR",
    "PROYECCION",
    "SE VE RECUPERACION",
    "VA A CERRAR",
    "COMO VA A CERRAR",
    "PROYECTA",
    "CAMINO DE",
    "TENDENCIA",
)
_DIFERIDAS = ("DIFERIDAS", "MANTENIMIENTO", "MANTENIMIENTOS")
_ECON = ("EBITDA", "NOPAT", "MARGEN", "RENTABILIDAD", "PLATA")

# Token exacto: `norm()` no retira signos, así que "…del P50?" no casaría con
# una comparación de frase a secas.
_REFERENCIA = ("P50",)
_CAUSAL_EXPL = (
    "POR QUE",
    "A QUE SE DEBE",
    "EXPLICA",
    "CAUSAS DE",
    "DETRACTORES",
    "QUE PASO CON",
    "PESAN",
    "PESA",
)

_PUNCT = "¿?¡!.,;:()[]{}\"'`"


def sub_intencion(texto: str) -> str:
    """`causal` | `proyeccion` | `diferidas` | `economia` | `referencia`."""
    t = norm(texto or "")

    if any(k in t for k in _ECON):
        return "economia"
    if any(k in t for k in _DIFERIDAS):
        return "diferidas"
    if any(k in t for k in _PROY):
        return "proyeccion"

    tokens = {w.strip(_PUNCT) for w in t.split()}
    if any(k in tokens for k in _REFERENCIA) and not any(k in t for k in _CAUSAL_EXPL):
        return "referencia"

    return "causal"
