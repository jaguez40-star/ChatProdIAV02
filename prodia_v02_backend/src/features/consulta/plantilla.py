"""Formateo VERBATIM del análisis — donde viven Q2 y Q4.

Portado de `consulta_v2/analizar/plantilla.py` (328 líneas). Módulo PURO:
recibe el JSON que ya calculó el servicio de análisis y lo redacta. No consulta
BD ni llama al LLM.

═══════════════════════════════════════════════════════════════════════════════
🔑 **Q2 — REGLA CERO: si no hay rezago, se DECLARA. Nunca se fabrica.**
═══════════════════════════════════════════════════════════════════════════════

Un LLM alucinó un déficit inexistente con Castilla al 102,7 % de cumplimiento,
y de ahí sale esta regla. Aquí es código, no una instrucción en un prompt.

**Ramifica en TRES estados, no en dos:**

1. Hay rezago → se explica.
2. No hay rezago **pero hay meta** → "no hay rezago; todo producto con meta va
   en o sobre ella".
3. **No hay meta** → "ningún producto tiene meta definida; no hay cumplimiento
   que evaluar ni rezago que explicar".

`valor_pct is None` (sin meta) **nunca** se confunde con `valor_pct < 100`
(rezagado). Son situaciones distintas y merecen respuestas distintas: decir
"vas al 0 %" cuando no hay meta sería inventar un incumplimiento.

═══════════════════════════════════════════════════════════════════════════════
🔑 **Q4 — la cobertura parcial va EN CABECERA, nombrando los campos.**
═══════════════════════════════════════════════════════════════════════════════

Medido en el origen: NARE tiene 1 de 8 campos en robustez, LISAMA 1 de 6, SURIA
5 de 10. Servir el EBITDA de un campo como "el EBITDA de NARE" sería mentir por
omisión. Por eso la salvedad es la PRIMERA línea, nombra qué se incluyó, y
**cambia el sujeto gramatical** de las cifras que vienen después: dejan de ser
"de esta entidad" para ser "de esos N campos".
"""

from __future__ import annotations

from typing import Any

_MES = (
    "",
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

_PROD_L = {"CRUDO": "crudo", "GAS": "gas", "BLANCOS": "blancos"}
_UNIDAD = {"CRUDO": "bbl", "GAS": "MSCF", "BLANCOS": "bbl"}

# D-A5: el nivel se declara SIEMPRE. "el Campo APIAY" y "el Activo APIAY" son
# cifras distintas y sin el rótulo son indistinguibles.
_NIVEL_TXT = {"campo": "el Campo", "activo": "el Activo"}


def _fmt(valor: Any, producto: str) -> str:
    """Formatea con la escala del producto (A5): gas ÷1e6, resto en barriles."""
    try:
        if producto == "GAS":
            millones = float(valor) / 1e6
            decimales = 1 if abs(millones) >= 1 else 2
            return f"{millones:.{decimales}f}".replace(".", ",")
        return f"{float(valor):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return str(valor)


def _dia_mes(iso: Any) -> str:
    """`2026-05-06` → `6 de mayo`. Devuelve el ISO crudo si no parsea."""
    try:
        _anio, mes, dia = str(iso).split("-")
        return f"{int(dia)} de {_MES[int(mes)]}"
    except (ValueError, IndexError):
        return str(iso)


def rezagados(datos: dict[str, Any]) -> list[dict[str, Any]]:
    """Productos CON meta y por debajo de ella.

    🔑 Es la base de Q2, y la condición es doble a propósito: `valor_pct is not
    None` (hay meta) **y** `< 100` (va corto). Un producto sin meta no está
    rezagado, simplemente no tiene contra qué medirse.
    """
    return [
        t
        for t in datos.get("titular", [])
        if t.get("valor_pct") is not None and t["valor_pct"] < 100
    ]


def _delta_texto(datos: dict[str, Any], producto: str) -> str | None:
    """Comparación contra la propia historia del producto, o `None`.

    Aporta contexto incluso cuando no hay rezago: ir al 101 % de una meta baja
    no es lo mismo que ir al 101 % estando por encima del histórico.
    """
    tarjeta = next(
        (x for x in datos.get("tarjetas", []) if x.get("producto") == producto), None
    )
    if (
        not tarjeta
        or tarjeta.get("hist_prom") in (None, 0)
        or tarjeta.get("proyectado_cierre") is None
    ):
        return None

    real = tarjeta["proyectado_cierre"]
    historico = tarjeta["hist_prom"]
    diferencia = real - historico
    sentido = "por encima de" if diferencia >= 0 else "por debajo de"
    unidad = _UNIDAD.get(producto, "bbl")
    signo = "+" if diferencia >= 0 else "−"

    return (
        f"va en {_fmt(real, producto)} {unidad} vs su promedio de "
        f"{_fmt(historico, producto)} {unidad} "
        f"({signo}{_fmt(abs(diferencia), producto)} {unidad}, {sentido} su "
        "propia historia)"
    )


def _cabecera(datos: dict[str, Any], entidad: str | None) -> tuple[str, str]:
    meta = datos.get("meta") or {}
    scope = meta.get("scope") or entidad or "la producción ECP"
    periodo = meta.get("periodo") or "el periodo"
    return scope, periodo


def _sin_rezago_producto(
    datos: dict[str, Any], scope: str, periodo: str, producto: str
) -> str:
    """Q2 acotada a un producto que el usuario nombró y que NO va corto.

    No se listan los otros productos: no los pidió.
    """
    etiqueta = _PROD_L.get(producto, producto.lower())
    titular = next(
        (x for x in datos.get("titular", []) if x.get("producto") == producto), None
    )
    lineas = [f"📊 {scope} · {periodo}"]

    if titular and titular.get("valor_pct") is not None:
        lineas.append(
            f"HECHO · {etiqueta}: no hay rezago — {etiqueta} va al "
            f"{titular['valor_pct']}% del presupuesto "
            f"({titular.get('texto', '—')}); no hay faltante que explicar."
        )
        delta = _delta_texto(datos, producto)
        if delta:
            lineas.append(f"DELTA · {etiqueta}: {delta}.")
    else:
        # Tercer estado de Q2: sin meta no hay rezago que explicar.
        lineas.append(
            f"HECHO · {etiqueta}: no tiene meta definida en el periodo — no hay "
            "rezago que explicar."
        )

    return "\n".join(lineas)


def _sin_rezago_global(datos: dict[str, Any], scope: str, periodo: str) -> str:
    """Q2 en su forma completa: los tres estados."""
    con_meta = [t for t in datos.get("titular", []) if t.get("valor_pct") is not None]
    lineas = [f"📊 {scope} · {periodo}"]

    if con_meta:
        estado = ", ".join(
            f"{_PROD_L.get(t['producto'], t['producto'])} {t['valor_pct']}%"
            for t in con_meta
        )
        lineas.append(
            f"HECHO: no hay rezago — todo producto con meta va en o sobre ella "
            f"({estado})."
        )
        for titular in con_meta:
            delta = _delta_texto(datos, titular["producto"])
            if delta:
                etiqueta = _PROD_L.get(titular["producto"], titular["producto"])
                lineas.append(f"DELTA · {etiqueta}: {delta}.")
    else:
        # 🔑 Tercer estado: sin meta NO es lo mismo que ir al 0 %.
        lineas.append(
            "HECHO: ningún producto tiene meta definida en el periodo — no hay "
            "cumplimiento que evaluar ni rezago que explicar."
        )

    return "\n".join(lineas)


def causal(
    datos: dict[str, Any],
    entidad: str | None,
    producto: str | None = None,
) -> str:
    """Narrativa causal: dónde está el faltante y por qué.

    Si `producto` viene, el análisis se ACOTA a ese producto — antes se
    analizaban los tres aunque el usuario pidiera uno.
    """
    scope, periodo = _cabecera(datos, entidad)
    rezago = rezagados(datos)

    if producto:
        rezago = [t for t in rezago if t.get("producto") == producto]
        if not rezago:
            return _sin_rezago_producto(datos, scope, periodo, producto)

    # ⚠️ Q2 — REGLA CERO.
    if not rezago:
        return _sin_rezago_global(datos, scope, periodo)

    lineas = [f"📊 {scope} · {periodo}"]
    for titular in rezago:
        etiqueta = _PROD_L.get(titular["producto"], titular["producto"])
        unidad = _UNIDAD.get(titular["producto"], "bbl")
        faltante = titular.get("faltante_abs")
        detalle = (
            f" ({_fmt(abs(faltante), titular['producto'])} {unidad} por debajo)"
            if faltante
            else ""
        )
        lineas.append(
            f"HECHO · {etiqueta}: va al {titular['valor_pct']}% del "
            f"presupuesto{detalle}."
        )

        for causa in (datos.get("causas") or {}).get(titular["producto"], []):
            lineas.append(f"CAUSA · {etiqueta}: {causa}.")

    return "\n".join(lineas)


def proyeccion(datos: dict[str, Any], entidad: str | None) -> str:
    """Cómo va a cerrar el periodo."""
    scope, periodo = _cabecera(datos, entidad)
    lineas = [f"📊 {scope} · {periodo}"]

    tarjetas = datos.get("tarjetas") or []
    if not tarjetas:
        # No se fabrica una proyección: se declara que no hay.
        lineas.append("HECHO: no hay proyección de cierre disponible para el periodo.")
        return "\n".join(lineas)

    for tarjeta in tarjetas:
        producto = tarjeta.get("producto", "")
        etiqueta = _PROD_L.get(producto, producto.lower())
        unidad = _UNIDAD.get(producto, "bbl")
        cierre = tarjeta.get("proyectado_cierre")
        meta = tarjeta.get("meta_mes")

        if cierre is None:
            continue
        if meta:
            pct = round(cierre / meta * 100, 1)
            lineas.append(
                f"HECHO · {etiqueta}: proyecta cerrar en "
                f"{_fmt(cierre, producto)} {unidad}, {pct}% de su meta."
            )
        else:
            lineas.append(
                f"HECHO · {etiqueta}: proyecta cerrar en "
                f"{_fmt(cierre, producto)} {unidad}; sin meta definida para comparar."
            )

    return "\n".join(lineas)


def economia(
    datos: dict[str, Any],
    entidad: str,
    nivel: str | None = None,
    incluidos: list[str] | None = None,
    total: int | None = None,
) -> str:
    """EBITDA/NOPAT, **con la cobertura declarada en cabecera (Q4)**.

    `incluidos` son los campos que sí están en la fuente económica y `total`
    cuántos tiene el alcance. Cuando no coinciden, la salvedad va primero.
    """
    etiqueta_nivel = _NIVEL_TXT.get(nivel or "", "")
    scope = f"{etiqueta_nivel} {entidad}".strip()
    lineas = [f"📊 {scope}"]

    incluidos = incluidos or []
    omitidos = (total - len(incluidos)) if total is not None else 0

    # 🔑 Q4 — la cobertura parcial es la PRIMERA línea y nombra los campos.
    de_quien = "de esta entidad"
    if omitidos > 0:
        lineas.append(
            f"⚠️ COBERTURA PARCIAL: {len(incluidos)} de {total} campos del "
            f"alcance están en la fuente económica. Las cifras cubren SOLO: "
            f"{', '.join(incluidos)}. Los otros {omitidos} (terceros o sin "
            "reconciliar) NO están incluidos."
        )
        # El sujeto de las cifras cambia: ya no son "de esta entidad".
        de_quien = f"de esos {len(incluidos)} campos"

    componentes = datos.get("components") or []
    if not componentes:
        lineas.append("HECHO: no hay cifras económicas disponibles para el periodo.")
        return "\n".join(lineas)

    for componente in componentes:
        etiqueta = componente.get("label", componente.get("key", ""))
        valor = componente.get("valueKusd")
        if valor is None:
            continue
        lineas.append(f"HECHO · {etiqueta} {de_quien}: {_fmt(valor, 'CRUDO')} kUSD.")

    return "\n".join(lineas)


def diferidas(datos: dict[str, Any], entidad: str, nivel: str | None = None) -> str:
    """Causas de producción diferida.

    Rotula el histórico explícitamente: la fuente termina antes del mes en
    curso, y presentarla como actual sería engañoso.
    """
    etiqueta_nivel = _NIVEL_TXT.get(nivel or "", "")
    scope = f"{etiqueta_nivel} {entidad}".strip()
    lineas = [f"📊 {scope}"]

    if datos.get("sin_datos"):
        lineas.append(
            f"HECHO: {datos.get('motivo') or 'no hay histórico de diferidas disponible'}."
        )
        return "\n".join(lineas)

    pareto = datos.get("pareto") or []
    if not pareto:
        lineas.append("HECHO: no hay causas de diferidas registradas para el alcance.")
        return "\n".join(lineas)

    lineas.append("CONTEXTO: el histórico de diferidas NO refleja el mes en curso.")
    for fila in pareto[:5]:
        lineas.append(
            f"CAUSA · {fila.get('grupo', '—')}: {fila.get('pct', 0)}% del volumen diferido."
        )

    return "\n".join(lineas)
