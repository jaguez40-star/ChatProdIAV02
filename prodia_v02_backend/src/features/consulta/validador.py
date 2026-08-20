"""Garantía mecánica de Q1 + formateo del cuerpo de la respuesta.

Portado de `consulta_v2/cuantificar/validador.py` (105 líneas). Tres piezas:

- `fmt_valor` — el número, con la escala de SU producto.
- `formatear_cuerpo` — el cuerpo VERBATIM que escribe Python.
- `intro_valido` — la red que impide que el LLM meta cifras.

═══════════════════════════════════════════════════════════════════════════════
🔑 **Q1 — Python calcula, el LLM solo redacta.**
═══════════════════════════════════════════════════════════════════════════════

`intro_valido` es esa regla hecha código: rechaza cualquier texto del modelo
que traiga un dígito o una unidad. **Aquí hay una corrección sobre el origen
(H9)**: allí conviven TRES versiones divergentes —`cuantificar` filtra dígitos
y unidades, `analizar` solo dígitos, y `jerarquizar` no valida nada—, así que
un intro de jerarquizar podía inventar cifras sin ninguna red. En F4 hay UNA
sola, la más estricta, y la usan los tres grupos.

⚠️ **A5 — la escala depende del producto, no es cosmética.** El gas se reporta
en MSCF (÷1e6) y el crudo en barriles. Aplicar la conversión equivocada da un
número mil veces menor **sin ningún error visible**: es el bug que en el
sistema viejo mostró "0,03 MSCF" donde debía decir "33.453,2 bpd". Por eso
`fmt_valor` recibe el producto y nunca hay un formateador genérico.
"""

from __future__ import annotations

import re
from typing import Any

_TIENE_DIGITO = re.compile(r"\d")

# Léxico que delata que el LLM se metió a dar cifras aunque no escriba números
# ("va por debajo del presupuesto", "millones de barriles").
_UNIDADES = (
    "barril",
    "bbl",
    "mscf",
    "%",
    "porcentaje",
    "presupuesto",
    "millones",
    "millón",
)


def fmt_valor(n: Any, producto: str) -> str:
    """Formatea un volumen con la escala de su producto, en es-CO.

    - **gas** → ÷1e6 y MSCF; 1 decimal si el valor es ≥1, 2 si es menor (así
      un valor pequeño no se redondea a "0").
    - **crudo / blancos** → barriles tal cual, separador de miles con punto.

    Degrada a `str(n)` ante un valor no numérico: formatear no debe tumbar una
    respuesta que ya se calculó.
    """
    try:
        if producto == "gas":
            millones = float(n) / 1e6
            decimales = 1 if abs(millones) >= 1 else 2
            return f"{millones:.{decimales}f}".replace(".", ",")
        return f"{float(n):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return str(n)


def formatear_cuerpo(res: dict[str, Any]) -> str:
    """Cuerpo VERBATIM desde el contrato del ejecutor.

    ⚠️ **N3 y N4 se resuelven ANTES de leer `resultado`/`mes`**: esas claves no
    existen en sus contratos, y leerlas antes de descartarlos reventaría con
    `KeyError`. El orden de estas ramas no es estético.
    """
    producto = res.get("producto", "crudo")
    unidad = res.get("unidad", "bbl")
    nivel = res.get("nivel")

    if nivel == "N3":
        return _cuerpo_serie(res, producto, unidad)
    if nivel == "N4":
        return _cuerpo_variacion(res, producto, unidad)
    if nivel == "N2":
        return _cuerpo_acumulado(res, producto, unidad)
    return _cuerpo_puntual(res, producto, unidad)


def _con_avisos(linea: str, res: dict[str, Any]) -> str:
    """Los avisos van al final y SIEMPRE se muestran: son las salvedades que
    hacen honesta la cifra (cobertura parcial, grano dudoso, proyección)."""
    for aviso in res.get("avisos", []):
        linea += f" ⚠️ {aviso}"
    return linea


def _cuerpo_serie(res: dict[str, Any], producto: str, unidad: str) -> str:
    pares = " · ".join(
        f"{p['mes']} {fmt_valor(p['valor'], producto)}" for p in res["serie"]
    )
    linea = (
        f"{res['entidad_cualificada']} de {producto}, mes a mes en "
        f"{res['anio']}: {pares} {unidad}."
    )
    if res.get("promedio") is not None:
        linea += (
            " Promedio mensual (meses cerrados): "
            f"{fmt_valor(res['promedio'], producto)} {unidad}."
        )
    return _con_avisos(linea, res)


def _cuerpo_variacion(res: dict[str, Any], producto: str, unidad: str) -> str:
    ultimo = res["ultimo"]
    subio = ultimo["delta"] >= 0
    pct = (
        f" ({'+' if subio else '-'}{abs(ultimo['pct'])}%)"
        if ultimo.get("pct") is not None
        else ""
    )
    cambios = " · ".join(
        f"{d['de']}→{d['a']} {'+' if d['delta'] >= 0 else '-'}"
        f"{fmt_valor(abs(d['delta']), producto)}"
        for d in res["deltas"]
    )
    linea = (
        f"{res['entidad_cualificada']} de {producto}: del mes de {ultimo['de']} "
        f"al de {ultimo['a']} {'subió' if subio else 'bajó'} "
        f"{fmt_valor(abs(ultimo['delta']), producto)} {unidad}{pct}. "
        f"Serie de cambios: {cambios} {unidad}."
    )
    return _con_avisos(linea, res)


def _cuerpo_acumulado(res: dict[str, Any], producto: str, unidad: str) -> str:
    real = fmt_valor(res["resultado"]["valor"], producto)
    pct = (
        f"{res['cumplimiento_pct']}%"
        if res.get("cumplimiento_pct") is not None
        else "s/d"
    )
    meses = res["meses_cerrados"]
    plural_mes = "es" if meses != 1 else ""
    plural_cerrado = "s" if meses != 1 else ""
    linea = (
        f"{res['entidad_cualificada']} acumuló {real} {unidad} de {producto} en "
        f"{res['periodo_label']} ({meses} mes{plural_mes} "
        f"cerrado{plural_cerrado}) — {pct} del presupuesto ({res['estado']})."
    )
    if res.get("referencia_valor"):
        ppto = fmt_valor(res["referencia_valor"], producto)
        linea += f" Presupuesto acumulado: {ppto} {unidad}."
    return _con_avisos(linea, res)


def _cuerpo_puntual(res: dict[str, Any], producto: str, unidad: str) -> str:
    real = fmt_valor(res["resultado"]["valor"], producto)
    pct = (
        f"{res['cumplimiento_pct']}%"
        if res.get("cumplimiento_pct") is not None
        else "s/d"
    )
    mes = res["mes"]
    ref_label = res.get("referencia_label", "presupuesto")

    # Un mes incompleto se DECLARA como proyección, con los días que lo
    # sostienen: la cifra no se presenta como si fuera el cierre.
    corte = (
        "mes cerrado"
        if mes["completo"]
        else f"proyección · {mes['dias_con_data']}/{mes['dias_del_mes']} días"
    )
    linea = (
        f"{res['entidad_cualificada']} produjo {real} {unidad} de {producto} en "
        f"{mes['nombre']} {mes['anio']} — {pct} del {ref_label} "
        f"({res['estado']}) · {corte}."
    )

    if res.get("referencia_valor"):
        ppto = fmt_valor(res["referencia_valor"], producto)
        # "promedio mensual del año" ya trae su propio calificador temporal:
        # añadirle "del mes" queda redundante. Las demás referencias sí lo
        # necesitan.
        if res.get("referencia") == "promedio_anio":
            linea += f" {ref_label.capitalize()}: {ppto} {unidad}."
        else:
            linea += f" {ref_label.capitalize()} del mes: {ppto} {unidad}."

    return _con_avisos(linea, res)


def intro_valido(intro: str) -> bool:
    """¿El intro del LLM es SOLO un saludo?

    🔑 **Es la red mecánica de Q1** y la única del proyecto: los tres grupos la
    usan. Rechaza dígitos y léxico de magnitud, que es como el modelo se cuela
    a "ayudar" con cifras que no calculó.

    Un intro vacío también es inválido: significa que el LLM no respondió, y el
    llamador debe servir su texto determinista.
    """
    if not intro:
        return False
    if _TIENE_DIGITO.search(intro):
        return False
    minusculas = intro.lower()
    return not any(u in minusculas for u in _UNIDADES)
