"""N5 — ranking de entidades por magnitud dentro de un mes.

Portado de `consulta_v2/cuantificar/ranking.py` (418 líneas). Es el eje
ORTOGONAL a N1-N4: aquellos miden UNA entidad a lo largo del tiempo, este
ordena VARIAS dentro de un mes.

Porta su propia consulta sobre el mismo fact que el resto de cuantificar. No
reusa el servicio de análisis porque este trabaja por-entidad y aquí hace falta
el universo completo.

═══════════════════════════════════════════════════════════════════════════════
🔑 **D3 — la semántica de orden es `(metrica, direccion)`, NUNCA `(eje, asc/desc)`.**
═══════════════════════════════════════════════════════════════════════════════

Esa segunda forma es un bug real del plan v1 del origen: devolvía **lo
contrario a lo pedido**. "Qué campos se quedaron más cortos vs presupuesto"
daba los que SUPERARON el presupuesto. Las cuatro combinaciones son explícitas:

| métrica | dirección | significa |
|---------|-----------|-----------|
| `real`  | `top`     | los que más producen |
| `real`  | `bottom`  | la producción más baja (con real > 0) |
| `gap`   | `bottom`  | **mayor faltante** — el DEFAULT de gap |
| `gap`   | `top`     | mayor excedente |

En métrica `gap` el default es `bottom` porque es la intención dominante:
"mayor faltante" debe dar faltante aunque la frase diga "mayor". Por eso las
palabras de faltante MANDAN sobre "MAYOR".

🔑 **D4 — CERO TRAICIONERO.** Un cero no es "poca producción": es *sin
registro*. Se excluyen del ranking y se declaran aparte; si no, el fondo de la
tabla lo ocuparían entidades que simplemente no reportaron.

**Terceros incluidos y rotulados**: el reporte trae campos operados por
terceros, y ocultarlos daría un ranking falso. Se incluyen y se nombra al
operador cuando no es Ecopetrol.
"""

from __future__ import annotations

import calendar
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.features.consulta.normaliza import norm

# ── Vocabulario de detección, sobre texto NORMALIZADO ────────────────────────

# Plural y singular por separado: la comparación es por TOKEN exacto, así que
# "los mayores productores" no casaría con "MAYOR" a secas.
_SUPERLATIVO = (
    "MAYOR",
    "MAYORES",
    "MENOR",
    "MENORES",
    "MAS",
    "MENOS",
    "TOP",
    "RANKING",
    "MAXIMA",
    "MAXIMO",
    "MINIMA",
    "MINIMO",
    "MEJORES",
    "PEORES",
    "MEJOR",
    "PEOR",
    "PRIMEROS",
    "ULTIMOS",
)

_NIVEL_TOK = {
    "CAMPO": "campo",
    "CAMPOS": "campo",
    "ACTIVO": "activo",
    "ACTIVOS": "activo",
    "GERENCIA": "gerencia",
    "GERENCIAS": "gerencia",
    "VICEPRESIDENCIA": "vicepresidencia",
    "VICEPRESIDENCIAS": "vicepresidencia",
    "POZO": "pozo",
    "POZOS": "pozo",
}

# Token exacto, nunca substring: "BAJO" está dentro de "trabajo".
_BOTTOM_TOK = (
    "MENOR",
    "MENORES",
    "MENOS",
    "PEOR",
    "PEORES",
    "MINIMA",
    "MINIMO",
    "BAJA",
    "BAJO",
    "BAJAS",
    "CORTO",
    "CORTOS",
    "CORTAS",
    "FALTANTE",
    "FALTANTES",
    "REZAGADOS",
    "REZAGADO",
    "INCUMPLIERON",
    "ULTIMOS",
)
_BOTTOM_PHRASE = ("LOS QUE MENOS", "POR DEBAJO", "QUEDARON CORTOS", "DE ABAJO")

_TOP_GAP_TOK = (
    "SUPERARON",
    "SUPERO",
    "EXCEDIERON",
    "EXCEDENTE",
    "EXCEDIO",
    "SOBRECUMPLIERON",
)
_TOP_GAP_PHRASE = ("POR ENCIMA",)

# 🔑 SIN "META" a propósito: `META` es patrón del grupo ANALIZAR y gana por
# precedencia, así que una pregunta con "meta" nunca llega aquí. Incluirla
# crearía la ilusión de que se soporta.
_METRICA_GAP = (
    "PPTO",
    "PRESUPUESTO",
    "FALTANTE",
    "FALTANTES",
    "CORTO",
    "CORTOS",
    "CORTAS",
    "EXCEDENTE",
    "INCUMPLIERON",
    "SUPERARON",
)

_PROD_TOK = {"GAS": "gas", "BLANCOS": "blancos", "BLANCO": "blancos"}
_PROD_MAP = {"crudo": "CRUDO", "gas": "GAS", "blancos": "BLANCOS"}

_MESES = (
    "enero febrero marzo abril mayo junio julio agosto septiembre setiembre "
    "octubre noviembre diciembre"
).split()
_MES_NUM = {m: i + 1 for i, m in enumerate(_MESES)}
_MES_NUM["setiembre"] = 9

_PUNCT = "¿?¡!.,;:()[]{}\"'`"

# Niveles que se declinan, cada uno con SU motivo. Un "no puedo" sin razón
# invita a insistir; con razón, el usuario reformula.
_NIVEL_DIFERIDO = {
    "gerencia": (
        "El ranking por gerencia llega en una próxima fase: en la jerarquía "
        "oficial varias «gerencias» del reporte son en realidad "
        "vicepresidencias, y compararlas sin reconciliar mezclaría niveles "
        "distintos. Puedo rankear campos o activos."
    ),
    "vicepresidencia": (
        "El ranking por vicepresidencia llega en una próxima fase. Puedo "
        "rankear campos o activos."
    ),
    "pozo": (
        "No puedo rankear pozos: el grano de pozo no está en el reporte "
        "diario, que llega hasta el detalle por campo. Puedo rankear campos "
        "o activos."
    ),
}
_NIVEL_PLURAL = {"campo": "campos", "activo": "activos"}


def _tokens(t: str) -> set[str]:
    return {p for p in (w.strip(_PUNCT) for w in t.split()) if p}


def detectar(texto: str) -> dict[str, Any] | None:
    """Reconoce la FORMA N5. Determinista, sin LLM y sin BD.

    Exige superlativo **y** sustantivo de nivel: sin ambos no es un ranking y
    la pregunta sigue su curso por N1-N4. Así "¿cuál es la mayor producción de
    Rubiales?" se responde como la cifra de Rubiales, no como un ranking.
    """
    t = norm(texto or "")
    toks = _tokens(t)

    # Las palabras de dirección (SUPERARON, INCUMPLIERON, FALTANTE) también
    # implican comparación entre entidades cuando van con un sustantivo de
    # nivel. Sin ellas, "qué campos superaron el presupuesto" no se detectaba.
    hay_comparacion = (
        any(s in toks for s in _SUPERLATIVO)
        or any(s in toks for s in _BOTTOM_TOK)
        or any(s in toks for s in _TOP_GAP_TOK)
        or "TOP" in t
        or "RANKING" in t
    )
    if not hay_comparacion:
        return None

    nivel = next((_NIVEL_TOK[k] for k in _NIVEL_TOK if k in toks), None)
    if nivel is None:
        return None
    if nivel in _NIVEL_DIFERIDO:
        return {"nivel_ranking": nivel, "diferido": _NIVEL_DIFERIDO[nivel]}

    metrica = "gap" if any(k in toks for k in _METRICA_GAP) else "real"
    es_bottom = any(k in toks for k in _BOTTOM_TOK) or any(
        p in t for p in _BOTTOM_PHRASE
    )

    if metrica == "gap":
        # ⚠️ D3: el DEFAULT de gap es `bottom` (faltante). Solo palabras
        # explícitas de excedente lo suben a `top`.
        es_top_gap = any(k in toks for k in _TOP_GAP_TOK) or any(
            p in t for p in _TOP_GAP_PHRASE
        )
        direccion = "top" if (es_top_gap and not es_bottom) else "bottom"
    else:
        direccion = "bottom" if es_bottom else "top"

    coincidencia = re.search(r"\bTOP\s+(\d+)\b", t) or re.search(
        r"\b(\d+)\s+(?:CAMPOS?|ACTIVOS?)\b", t
    )
    if coincidencia:
        top_n = max(1, min(20, int(coincidencia.group(1))))
    else:
        # El singular pide UNO ("el campo que más produce"); el plural, cinco.
        singular = ("CAMPO" in toks and "CAMPOS" not in toks) or (
            "ACTIVO" in toks and "ACTIVOS" not in toks
        )
        top_n = 1 if singular else 5

    producto = next((_PROD_TOK[k] for k in _PROD_TOK if k in toks), "crudo")
    periodo = next((m for m in _MESES if m in (texto or "").lower()), None)

    return {
        "nivel_ranking": nivel,
        "metrica": metrica,
        "direccion": direccion,
        "top_n": top_n,
        "producto": producto,
        "periodo_texto": periodo,
    }


# ── SQL. ⚠️ U3: copiado IDÉNTICO del origen ──────────────────────────────────
# 🔑 El nivel `activo` NO inventa operador: el sistema v1 hardcodeaba
# 'ECOPETROL' sin verificarlo. Devuelve NULL y el formateador simplemente no
# rotula operador a ese nivel.
_SQL = {
    "campo": """
        SELECT COALESCE(NULLIF(TRIM(f.campo),''), f.nombre) AS ent,
               SUM(CASE WHEN es.nombre='REAL' THEN m.volumen ELSE 0 END) AS vreal,
               SUM(CASE WHEN es.nombre='PPTO' THEN m.volumen ELSE 0 END) AS vppto,
               MAX(f.operador) AS operador
        FROM core.fact_produccion_mes_ecp m
        JOIN core.dim_tipo_producto tp ON tp.tipo_producto_id = m.tipo_producto_id
        JOIN core.dim_escenario es     ON es.escenario_id     = m.escenario_id
        JOIN core.dim_fuente f         ON f.fuente_id         = m.fuente_id
        WHERE m.fecha = :fin AND tp.nombre = :prod AND es.nombre IN ('REAL','PPTO')
        GROUP BY 1""",
    "activo": """
        SELECT a.activo AS ent,
               SUM(CASE WHEN es.nombre='REAL' THEN m.volumen ELSE 0 END) AS vreal,
               SUM(CASE WHEN es.nombre='PPTO' THEN m.volumen ELSE 0 END) AS vppto,
               NULL AS operador
        FROM core.fact_produccion_mes_ecp m
        JOIN core.dim_tipo_producto tp ON tp.tipo_producto_id = m.tipo_producto_id
        JOIN core.dim_escenario es     ON es.escenario_id     = m.escenario_id
        JOIN core.dim_fuente f         ON f.fuente_id         = m.fuente_id
        JOIN core.map_campo_activo a
             ON a.campo_norm = UPPER(COALESCE(NULLIF(TRIM(f.campo),''), f.nombre))
        WHERE m.fecha = :fin AND tp.nombre = :prod AND es.nombre IN ('REAL','PPTO')
        GROUP BY 1""",
}


def _fin_mes(db: Session, periodo_texto: str | None) -> tuple[Any, ...] | None:
    """Mes a rankear: `(fin, anio, mes, nombre, es_proyeccion)` o `None`.

    Por defecto, el último mes con REAL. `es_proyeccion` marca que el corte no
    llega a fin de mes: el REAL del mes en curso es un cierre proyectado, y
    presentarlo como definitivo sería engañoso.
    """
    max_real = db.execute(text("""
        SELECT MAX(m.fecha) FROM core.fact_produccion_mes_ecp m
        JOIN core.dim_escenario es ON es.escenario_id = m.escenario_id
        WHERE es.nombre = 'REAL'""")).scalar()
    if max_real is None:
        return None

    anio, mes = max_real.year, max_real.month
    if periodo_texto and periodo_texto in _MES_NUM:
        mes = _MES_NUM[periodo_texto]

    dias_mes = calendar.monthrange(anio, mes)[1]
    fin = f"{anio:04d}-{mes:02d}-{dias_mes:02d}"

    max_dia = db.execute(
        text("SELECT MAX(fecha) FROM core.fact_produccion_dia_ecp")
    ).scalar()
    es_proyeccion = bool(
        max_dia
        and max_dia.year == anio
        and max_dia.month == mes
        and max_dia.day < dias_mes
    )
    return fin, anio, mes, _MESES[mes - 1], es_proyeccion


def calcular(slots: dict[str, Any], db: Session) -> dict[str, Any]:
    """Ejecuta el ranking. Contrato N5, o `{aplica: False, texto}`."""
    nivel = slots.get("nivel_ranking")
    if nivel not in _SQL:
        return {
            "aplica": False,
            "texto": slots.get("diferido", "Ese ranking no está soportado."),
        }

    producto = slots.get("producto", "crudo")
    producto_dim = _PROD_MAP.get(producto, "CRUDO")
    unidad = "MSCF" if producto == "gas" else "bbl"
    metrica = slots["metrica"]
    direccion = slots["direccion"]
    top_n = slots["top_n"]
    plural = _NIVEL_PLURAL[nivel]

    info = _fin_mes(db, slots.get("periodo_texto"))
    if info is None:
        return {
            "aplica": False,
            "texto": "No hay datos de producción cargados para rankear.",
        }
    fin, anio, _mes, nombre_mes, es_proyeccion = info

    filas = db.execute(text(_SQL[nivel]), {"fin": fin, "prod": producto_dim}).all()

    datos = [
        (
            (f[0] or "").strip(),
            float(f[1] or 0),
            float(f[2] or 0),
            (f[3] or "").strip() if f[3] else "",
        )
        for f in filas
        if (f[1] or f[2])
    ]

    # 🔑 D4 — CERO TRAICIONERO: un cero es "sin registro", no "poca
    # producción". Se excluye del orden y se declara aparte.
    con_real = [d for d in datos if d[1] > 0]
    sin_registro = len(datos) - len(con_real)

    if not con_real:
        return {
            "aplica": False,
            "texto": (
                f"No hay producción de {producto} registrada en {nombre_mes} "
                f"{anio} para rankear {plural}."
            ),
        }

    if metrica == "gap":
        pool = [d for d in con_real if (d[1] - d[2]) != 0]

        def clave(d: tuple[Any, ...]) -> float:
            return float(d[1] - d[2])

    else:
        pool = con_real

        def clave(d: tuple[Any, ...]) -> float:
            return float(d[1])

    reverse = direccion == "top"

    if not pool:
        return {
            "aplica": False,
            "texto": (
                f"Todos los {plural} con producción de {producto} en "
                f"{nombre_mes} {anio} coinciden con su presupuesto; no hay "
                "faltantes ni excedentes que rankear."
            ),
        }

    ordenado = sorted(pool, key=clave, reverse=reverse)
    top = ordenado[:top_n]

    # La concentración SOLO tiene sentido con métrica real y dirección top
    # ("los que más producen concentran X %"). En bottom sería engañosa.
    concentracion = None
    if metrica == "real" and direccion == "top":
        total = sum(d[1] for d in con_real)
        if total > 0:
            concentracion = round(sum(d[1] for d in top) / total * 100, 1)

    items = [
        {
            "pos": i + 1,
            "entidad": d[0],
            "valor": d[1],
            "gap": d[1] - d[2],
            "ppto": d[2],
            "operador": d[3],
            "es_ecp": (not d[3]) or d[3].upper().startswith("ECOPETROL"),
        }
        for i, d in enumerate(top)
    ]

    return {
        "aplica": True,
        "grupo": "cuantificar",
        "nivel": "N5",
        "nivel_ranking": nivel,
        "metrica": metrica,
        "direccion": direccion,
        "producto": producto,
        "unidad": unidad,
        "periodo_label": f"{nombre_mes} {anio}",
        "es_proyeccion": es_proyeccion,
        "items": items,
        "total_universo": len(con_real),
        "sin_registro": sin_registro,
        "concentracion_pct": concentracion,
    }
