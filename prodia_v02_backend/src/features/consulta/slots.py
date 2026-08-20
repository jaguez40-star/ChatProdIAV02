"""Aterrizaje de slots contra el catálogo — 100 % determinista.

Portado de `consulta_v2/cuantificar/slots.py` (151 líneas).

**No interviene el LLM.** Los grados de libertad del usuario son el MES, el
NIVEL TEMPORAL (N1 puntual / N2 acumulado / N3 serie / N4 variación) y el
PRODUCTO, y los tres se resuelven por diccionario sobre texto normalizado. Lo
demás son valores por defecto del catálogo. Es lo que hace que Q1 se sostenga:
si el modelo cae, la interpretación de la pregunta no se pierde.

═══════════════════════════════════════════════════════════════════════════════
🔑 **D2 — el SEGUNDO eslabón de Q3.**
═══════════════════════════════════════════════════════════════════════════════

`drills.py` resuelve que "promedio del año" sea una continuación de REFERENCIA
y no de acumulado. Aquí se resuelve el mismo conflicto un nivel más abajo, en
la interpretación del texto ya autocontenido. **Reescribir solo uno de los dos
revive el bug.**

Y con un matiz que el origen corrigió después (AF-4.9 revisado): el override
distingue señales DÉBILES de FUERTES. "del año" puede venir de la propia frase
de referencia; "acumulada" o "YTD" son inequívocas. Si hay una fuerte, se
respeta el acumulado aunque la referencia sea otra — forzar N1 ahí perdía el
"acumulado" en silencio, que es peor que declarar la salvedad.
"""

from __future__ import annotations

import re
from typing import Any, TypedDict

from src.features.consulta import catalogo
from src.features.consulta.normaliza import norm


class Slots(TypedDict):
    """Lo que el motor entendió de la pregunta, listo para ejecutar."""

    variable: str
    producto: str
    unidad: str
    descargo: str | None
    nivel_temporal: str
    referencia: str
    periodo_texto: str | None
    defaults_asumidos: list[str]


# ⚠️ D2: señales DÉBILES vs FUERTES de acumulado. Las débiles pueden formar
# parte de una frase de referencia ("promedio DEL AÑO") sin que el usuario pida
# un acumulado; las fuertes son inequívocas.
_ACUM_KW_DEBIL = ("EN EL ANO", "DEL ANO")
_ACUM_KW_FUERTE = (
    "ACUMULADO",
    "ACUMULADA",
    "EN LO QUE VA",
    "YTD",
    "HASTA AHORA",
    "EN TOTAL",
    "TOTAL DEL ANO",
)
_ACUM_KW = _ACUM_KW_FUERTE + _ACUM_KW_DEBIL

# N3 (serie) y N4 (variación). Las palabras sueltas se comparan por TOKEN, no
# por substring: si no, "BAJO" casaría dentro de "trabajo" y "VARIO" dentro de
# "varios". Las multi-palabra sí van por substring.
# Sin "MES"/"MENSUAL" a secas: pisarían N1.
_VAR_WORDS = frozenset(
    {
        "VARIACION",
        "VARIO",
        "VARIARON",
        "CAMBIO",
        "CAMBIARON",
        "SUBIO",
        "BAJO",
        "CRECIO",
        "CAYO",
        "DELTA",
    }
)
_VAR_PHRASES = ("DE UN MES A OTRO", "DIFERENCIA ENTRE MESES")
_SERIE_WORDS = frozenset({"SERIE", "EVOLUCION", "MENSUALES"})
_SERIE_PHRASES = ("MES A MES", "MES POR MES", "POR MES", "CADA MES")

# Producto por TOKEN, no substring: "GAS" suelto, nunca dentro de "GASOLINA".
_PROD_TOKENS = {"GAS": "gas", "BLANCOS": "blancos", "BLANCO": "blancos"}

# Contra qué se compara el REAL. P50 se reconoce para poder rechazarlo con
# honestidad, no porque se sepa responder.
_REF_MATCH: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("P50", ("P50", "COMPROMISO", "BASE P50")),
    ("CONTABLE", ("CONTABLE",)),
    ("OPERATIVO", ("OPERATIVO",)),
    (
        "promedio_anio",
        (
            "PROMEDIO DEL ANO",
            "PROMEDIO ANUAL",
            "PROMEDIO MENSUAL",
            "VS EL PROMEDIO",
            "CONTRA EL PROMEDIO",
            "RESPECTO AL PROMEDIO",
        ),
    ),
)

_MESES = (
    "enero febrero marzo abril mayo junio julio agosto septiembre setiembre "
    "octubre noviembre diciembre"
).split()

# `norm()` pliega acentos pero NO retira puntuación, así que "¿serie" o "gas?"
# nunca casarían por igualdad exacta sin despegarla.
_PUNCT = "¿?¡!.,;:()[]{}\"'`"


def _tokens(t: str) -> set[str]:
    """Tokens de un texto YA normalizado, sin puntuación de borde."""
    return {p for p in (w.strip(_PUNCT) for w in t.split()) if p}


def _tiene(t: str, palabras: frozenset[str], frases: tuple[str, ...]) -> bool:
    return any(w in _tokens(t) for w in palabras) or any(f in t for f in frases)


def _nivel_temporal(texto: str) -> str:
    """N1 puntual / N2 acumulado / N3 serie / N4 variación.

    N4 se comprueba antes que N3 porque la variación es más específica: quien
    pregunta "cómo varió mes a mes" quiere los deltas, no la serie cruda.
    """
    t = norm(texto or "")
    if _tiene(t, _VAR_WORDS, _VAR_PHRASES):
        return "N4"
    if _tiene(t, _SERIE_WORDS, _SERIE_PHRASES):
        return "N3"
    if any(k in t for k in _ACUM_KW):
        return "N2"
    return "N1"


def _producto(texto: str, entidad_valor: str | None = None) -> str:
    """crudo (default) | gas | blancos.

    🔑 AF10: se EXCLUYEN los tokens del nombre de la entidad. Un campo llamado
    "CAÑO BLANCO" no debe leerse como producto blancos; y "cuánto gas produjo
    Caño Blanco" sí da gas, porque "GAS" no es token del nombre.
    """
    tokens = _tokens(norm(texto or ""))
    if entidad_valor:
        tokens -= _tokens(norm(entidad_valor))
    for token, producto in _PROD_TOKENS.items():
        if token in tokens:
            return producto
    return "crudo"


def _referencia(texto: str) -> str:
    t = norm(texto or "")
    for codigo, claves in _REF_MATCH:
        if any(k in t for k in claves):
            return codigo
    return "PPTO"


def _periodo_texto(texto: str) -> str | None:
    """Nombre del mes hallado, o `None` para el mes por defecto.

    "mes pasado" y "anterior" viajan literales: el servicio de desempeño
    también los entiende, así que no hace falta resolverlos aquí.
    """
    t = (texto or "").lower()
    if "pasado" in t or "anterior" in t:
        return "mes pasado"
    mes = next((m for m in _MESES if m in t), None)
    if mes is None:
        return None
    anio = re.search(r"20\d\d", t)
    return f"{mes} {anio.group(0)}" if anio else mes


def extraer_slots(texto: str, entidad_valor: str | None = None) -> Slots:
    """Interpreta la pregunta. Determinista: mismo texto, mismos slots."""
    producto = _producto(texto, entidad_valor)
    variable = f"produccion_{producto}"

    productos: dict[str, Any] = catalogo.get().get("productos") or {}
    cfg_producto: dict[str, Any] = productos.get(variable, {})
    unidad = cfg_producto.get("unidad", "bbl")

    # El descargo solo viaja si el grano-mes es de confianza MEDIA: es una
    # salvedad de honestidad, no un adorno.
    cfg_mes = (cfg_producto.get("granos") or {}).get("mes", {})
    descargo = cfg_mes.get("descargo") if cfg_mes.get("confianza") == "media" else None

    referencia = _referencia(texto)
    nivel = _nivel_temporal(texto)

    # ⚠️ D2 — segundo eslabón de Q3. Solo se fuerza N1 si la ÚNICA señal de
    # acumulado fue la débil. Con una fuerte presente ("acumulada", "YTD") se
    # respeta el N2: el aviso del ejecutor explicará que esa referencia no
    # aplica al acumulado, y eso es más honesto que perder el "acumulado".
    if referencia == "promedio_anio" and not any(
        k in norm(texto) for k in _ACUM_KW_FUERTE
    ):
        nivel = "N1"

    periodo = _periodo_texto(texto)
    defaults = [f"producto={producto}", f"referencia={referencia}"]
    if periodo is None:
        defaults.append("periodo=mes actual")

    return Slots(
        variable=variable,
        producto=producto,
        unidad=unidad,
        descargo=descargo,
        nivel_temporal=nivel,
        referencia=referencia,
        periodo_texto=periodo,
        defaults_asumidos=defaults,
    )
