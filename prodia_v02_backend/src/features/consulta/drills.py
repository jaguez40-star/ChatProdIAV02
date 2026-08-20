"""Reescritura conversacional — los drills, en su orden exacto.

Portado de `maquina_q.py:58-212`. Aislado en su propio módulo, a diferencia del
origen, para que **el orden sea testeable por sí solo**.

═══════════════════════════════════════════════════════════════════════════════
🔑 **Q3 — EL ORDEN *ES* LA CORRECCIÓN. No reordenar sin leer esto.**
═══════════════════════════════════════════════════════════════════════════════

El caso que lo motiva, con fecha y todo (origen, 2026-08-02): **"promedio del
año" contiene la substring "DEL ANO"**, que es palabra clave de acumulado. Si
el drill de ACUMULADO corriera antes que el de REFERENCIA, esa frase devolvería
el acumulado contra PPTO — *una cifra distinta a la pedida, servida con la
misma confianza*. Por eso `_REF_CONTINUA_KW` se comprueba **antes** que
`_ACUM_KW`.

Esa regla tiene un **segundo eslabón aguas abajo**, en `slots.py`: cuando la
única señal de acumulado fue la DÉBIL (`EN EL ANO`/`DEL ANO`) y hay referencia
`promedio_anio`, el nivel se fuerza a N1. **Reescribir solo uno de los dos
revive el bug.**

Los drills 3 (ranking) y 4 (analizar) **cortan siempre**, con `return` propio.
En el origen eso era defensivo —sus contextos no llevan `entidad` y los drills
de abajo harían `KeyError`—, pero aquí el contexto está tipado y `mypy` ya lo
impide. Se conserva el corte porque además es **semántico**: dentro de una
conversación de ranking, "para crudo" significa *re-lanza el ranking*, no
*dame la producción de crudo*.

Orden completo (primer `return` gana):

| # | Drill | Guarda |
|---|-------|--------|
| 0 | Continuación temporal | excepción de longitud (>5 tokens) |
| 1 | Corte por longitud | `len(toks) > 5` → `None` |
| 2 | Entidad nombrada | `None` si además hay producto o acumulado |
| 3 | **Ranking** | corta siempre |
| 4 | **Analizar** | corta siempre |
| 5 | **Referencia** | ⚠️ ANTES que el 6 |
| 6 | **Acumulado N1→N2** | ⚠️ "promedio del año" ⊃ "DEL ANO" |
| 7 | N1 genérico | mes nuevo, misma entidad |
| 8 | `ofrece_produccion` | post-jerarquizar |
| 9 | Estructural | pronombre elidido |
"""

from __future__ import annotations

from collections.abc import Callable

from src.features.consulta.memoria import (
    ContextoAnalizar,
    ContextoConversacion,
    ContextoCuantificar,
    ContextoJerarquizar,
    ContextoRanking,
)
from src.features.consulta.normaliza import norm

# Afirmaciones sueltas. Un "sí" pelado debe ir al siguiente paso que ofreció el
# cierre anterior; sin esto viajaba desnudo a la Capa 2 y el LLM respondía
# sobre la conjunción "si" → Desconocido (bug real del origen, 2026-08-04).
_AFIRM = frozenset(
    {"SI", "DALE", "OK", "OKEY", "CLARO", "BUENO", "LISTO", "SIP", "VALE", "ESO", "ESA"}
)

_PROD_KW = (
    "PRODUCCION",
    "PRODUJO",
    "PRODUCE",
    "PRODUCIDO",
    "CUANTO",
    "CUANTA",
    "CUANTOS",
    "CUANTAS",
)

# Pregunta ESTRUCTURAL con pronombre elidido ("¿a qué activo pertenece?").
_ESTRUCT_KW = (
    "PERTENECE",
    "ACTIVO",
    "ACTIVOS",
    "GERENCIA",
    "GERENCIAS",
    "VICEPRESIDENCIA",
    "CAMPO",
    "CAMPOS",
    "ESTRUCTURA",
    "CONFORMAN",
    "COMPONE",
    "TIPO",
    "POZO",
    "POZOS",
    "QUE ES",
    "DE QUE",
    "A QUE",
    "CUAL",
)

# ⚠️ Q3: `_REF_CONTINUA_KW` DEBE revisarse ANTES que `_ACUM_KW`.
# "promedio del año" contiene "DEL ANO" y sin ese orden el drill de acumulado
# lo captura primero.
_ACUM_KW = ("ACUMULADO", "EN EL ANO", "DEL ANO", "EN TOTAL", "YTD")
_REF_CONTINUA_KW = ("OPERATIVO", "CONTABLE", "P50", "PROMEDIO")

# Continuación TEMPORAL: habilita heredar la entidad aunque la frase pase de 5
# tokens ("muéstrame la producción mes a mes" son 6).
_TEMP_CONT_KW = ("MES A MES", "VARIACION", "COMO VARIO", "SERIE", "EVOLUCION")

# Palabras que invierten el orden de un ranking.
_FLIP_KW = (
    "REVES",
    "INVIERTE",
    "INVERTIR",
    "ASCENDENTE",
    "CAMBIA",
    "CAMBIANDO",
    "ORDEN",
    "MENOS",
    "MENOR",
    "MENORES",
    "ABAJO",
    "ULTIMOS",
    "PEORES",
)

# Detector de entidad nombrada. Se inyecta porque vive en `respuesta_jerarquizar`,
# que llega en el Bloque 7: así este módulo es puro y testeable hoy.
DetectorEntidad = Callable[[str], str | None]


def _pieza_producto(producto: str | None) -> str:
    """ "gas de " / "" para crudo. El crudo se omite porque es el producto por
    defecto de `slots`, y nombrarlo no cambia la interpretación."""
    if not producto or producto == "crudo":
        return ""
    return f"{producto} de "


def _drill_ranking(t: str, ctx: ContextoRanking) -> str | None:
    """N5: "para crudo" / "al revés" re-lanzan el MISMO ranking.

    Corta siempre (devuelve `None` si no aplica, sin seguir a los de abajo):
    dentro de una conversación de ranking, esas frases significan re-lanzar,
    no pedir producción.
    """
    nuevo_producto = (
        "gas"
        if "GAS" in t
        else (
            "blancos"
            if ("BLANCOS" in t or "BLANCO" in t)
            else "crudo" if "CRUDO" in t else None
        )
    )
    invertir = any(k in t for k in _FLIP_KW)
    if not (nuevo_producto or invertir):
        return None

    producto = nuevo_producto or ctx.producto
    direccion = ctx.direccion
    if invertir:
        direccion = "bottom" if direccion == "top" else "top"

    nivel_plural = "activos" if ctx.nivel_ranking == "activo" else "campos"
    if ctx.metrica == "gap":
        que = "con mayor excedente" if direccion == "top" else "que quedaron mas cortos"
        return f"cuales {nivel_plural} {que} frente al presupuesto de {producto}"

    palabra = "mayores" if direccion == "top" else "menores"
    return f"cuales {nivel_plural} son los {palabra} productores de {producto}"


def _destino_analizar(t: str, ctx: ContextoAnalizar) -> str | None:
    """Qué sub-intención pidió la respuesta corta.

    Una palabra explícita gana sobre la opción por defecto del cierre.
    """
    if any(k in t for k in ("EBITDA", "NOPAT", "MARGEN", "RENTABILIDAD")):
        return "economia"
    if any(k in t for k in ("DIFERIDAS", "MANTENIMIENTO", "MANTENIMIENTOS")):
        return "diferidas"
    if any(k in t for k in ("PROYECCION", "PROYECTA", "CIERRE", "CERRAR")):
        return "proyeccion"
    if any(
        k in t
        for k in (
            "CAMPO",
            "CAMPOS",
            "DETALLE",
            "DETRACTORES",
            "FALTANTE",
            "EXPLICA",
            "EXPLICAN",
            "CAUSA",
            "CAUSAS",
        )
    ):
        return "causal"
    # Palabras del cierre del declinar de referencia: sin esto, ninguna de sus
    # dos opciones tenía continuación reconocida y caía a Desconocido.
    if any(k in t for k in ("PRESUPUESTO", "PPTO")):
        return "causal"
    if any(k in t for k in ("VICEPRESIDENCIA", "VP")):
        return "referencia"
    if t in _AFIRM:
        # "sí" a secas: se toma lo que ofreció el cierre de ESA sub-intención.
        # Tras proyección se ofreció el causal; tras causal, la proyección (el
        # detalle por campo ya venía en el bloque que el usuario acaba de leer).
        return "causal" if ctx.sub in ("proyeccion", "referencia") else "proyeccion"
    return None


def _drill_analizar(t: str, ctx: ContextoAnalizar) -> str | None:
    """Los cierres de analizar OFRECEN un siguiente paso; el drill lo enruta.

    Todas las reescrituras llevan la palabra "produccion", que es vocabulario
    FUERTE del filtro de dominio: así enrutan por regex sin gastar una llamada
    al LLM.
    """
    destino = _destino_analizar(t, ctx)
    if destino is None:
        return None

    pieza = f"de {ctx.producto} " if ctx.producto else ""
    cola = f"de {ctx.entidad} " if ctx.entidad else ""

    if destino == "economia":
        return f"ebitda de la produccion {cola}".strip()
    if destino == "diferidas":
        return f"diferidas de la produccion {pieza}{cola}".strip()
    if destino == "proyeccion":
        return f"cual es la proyeccion de cierre de la produccion {pieza}{cola}".strip()
    if destino == "referencia":
        # 🔑 Si el turno anterior ofreció una vicepresidencia, "la
        # vicepresidencia" se refiere a ESA, no al campo del contexto. Sin
        # esto la reescritura repetía el campo, volvía a declinar y entraba en
        # BUCLE (bug real reproducido en la verificación del origen).
        if ctx.vp:
            return f"cual es el p50 de la produccion {pieza}de {ctx.vp}".strip()
        return f"cual es el p50 de la produccion {pieza}{cola}".strip()
    return f"por que la produccion {pieza}{cola}esta corta".strip()


def reescribir(
    texto: str,
    ctx: ContextoConversacion | None,
    detectar_entidad: DetectorEntidad,
) -> str | None:
    """Reescribe una respuesta CORTA en una pregunta autocontenida, o `None`.

    `None` significa "no es una continuación": el texto sigue tal cual.

    Solo frases de ≤5 tokens, salvo la excepción temporal del drill 0: una
    pregunta larga es intención propia, no una continuación.
    """
    if ctx is None:
        return None

    tokens = norm(texto).split()
    if not tokens:
        return None
    t = " ".join(tokens)

    entidad_nombrada = detectar_entidad(texto)

    # ── 0. Continuación TEMPORAL: excepción a la regla de longitud ──────────
    # Exige contexto de cuantificar CON entidad y que la frase no nombre una
    # entidad nueva (esa sería autocontenida).
    if (
        isinstance(ctx, ContextoCuantificar)
        and ctx.entidad
        and not entidad_nombrada
        and any(k in t for k in _TEMP_CONT_KW)
    ):
        return f"produccion de {_pieza_producto(ctx.producto)}{ctx.entidad} {texto.strip()}"

    # ── 1. Corte por longitud ───────────────────────────────────────────────
    if len(tokens) > 5:
        return None

    trae_produccion = any(w in t for w in _PROD_KW)

    # ── 2. La frase nombra una entidad ──────────────────────────────────────
    if entidad_nombrada:
        # 🔑 Si ADEMÁS trae intención propia, la frase es AUTOCONTENIDA y NO se
        # reescribe: la plantilla "produccion de {ent}" borraría los slots que
        # el texto ya traía. Bug real (2026-08-02): "cuántos blancos produjo
        # Cupiagua" son 4 tokens, entraba al reescritor, y respondía CRUDO a
        # una pregunta de BLANCOS.
        if trae_produccion or any(k in t for k in _ACUM_KW):
            return None
        return f"que es {entidad_nombrada}"

    # ── 3. Ranking: corta siempre ───────────────────────────────────────────
    if isinstance(ctx, ContextoRanking):
        return _drill_ranking(t, ctx)

    # ── 4. Analizar: corta siempre ──────────────────────────────────────────
    if isinstance(ctx, ContextoAnalizar):
        return _drill_analizar(t, ctx)

    # ── 5. REFERENCIA ── ⚠️ Q3: ANTES que el acumulado ──────────────────────
    if isinstance(ctx, ContextoCuantificar) and any(k in t for k in _REF_CONTINUA_KW):
        # La referencia viaja VERBATIM en el texto reescrito; la detecta
        # `slots` aguas abajo, incluido el override que fuerza N1.
        return f"produccion de {_pieza_producto(ctx.producto)}{ctx.entidad} {texto.strip()}"

    # ── 6. ACUMULADO N1 → N2 ── ⚠️ Q3: DESPUÉS de la referencia ─────────────
    if isinstance(ctx, ContextoCuantificar) and (
        any(k in t for k in _ACUM_KW) or t in _AFIRM
    ):
        # AF9: preservar el producto — si no, "acumulado" tras un N1 de gas
        # volvería a crudo.
        return f"acumulado de {_pieza_producto(ctx.producto)}{ctx.entidad}"

    # ── 7. N1 genérico: mes nuevo, misma entidad ────────────────────────────
    # "Mayo, ¿cuánto ha producido?" tras hablar de Rubiales. El texto ORIGINAL
    # viaja completo: es ahí donde `slots` encuentra el mes.
    if isinstance(ctx, ContextoCuantificar) and trae_produccion:
        return f"produccion de {_pieza_producto(ctx.producto)}{ctx.entidad} {texto.strip()}"

    # ── 8. El cierre de jerarquizar ofreció producción ──────────────────────
    if isinstance(ctx, ContextoJerarquizar):
        if ctx.ofrece_produccion and (trae_produccion or t in _AFIRM):
            return f"produccion de {ctx.entidad}"

        # ── 9. Estructural con pronombre elidido ────────────────────────────
        # Se reescribe a "que es {entidad}" porque SIEMPRE clasifica
        # jerarquizar, y el árbol completo ya trae activo/gerencia/VP/campos.
        # Añadir la entidad al texto tal cual era frágil: "y sus campos
        # CHICHIMENE" no casa con ningún patrón.
        if any(k in t for k in _ESTRUCT_KW):
            return f"que es {ctx.entidad}"

    return None
