"""Normalización de texto del Motor Q.

Portado de `consulta_v2/normaliza.py` (10 líneas) sin cambios de conducta.

⚠️ **`norm()` PLIEGA LA Ñ**: `NFKD` descompone `Ñ` en `N` + tilde combinante y
el filtro de `combining` se lleva la tilde. Consecuencia práctica: cualquier
patrón o palabra clave que se compare contra texto normalizado debe escribirse
con `N`, nunca con `Ñ` — `"PEQUEÑOS"` sería código muerto porque el texto
normalizado dice `"PEQUENOS"`. El origen documenta esta trampa en
`respuesta_jerarquizar.py:234-237`.

⚠️ **NO retira signos de puntuación**: `¿cuánto?` normaliza a `¿CUANTO?`. Los
módulos que necesitan tokens limpios recortan la puntuación aparte (el origen
repite un `.strip(_PUNCT)` en cinco sitios distintos por esta razón).
"""

from __future__ import annotations

import unicodedata


def norm(s: str) -> str:
    """UPPER + trim + colapsar espacios + plegar acentos/ñ (NFKD sin combining)."""
    texto = unicodedata.normalize("NFKD", (s or "").strip().upper())
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    return " ".join(texto.split())
