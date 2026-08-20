"""Análisis Ejecutivo ECP — valle, gap reconciliado, tarjetas, focos y tesis.

Portado de `INGESTA/Rep_Prod/backend/app/features/analisis/api.py:669-1581`.

**Python calcula, el LLM redacta** (Q1). Todo lo de este módulo es
determinista: las cifras, las etiquetas de estado, los flags y el composer de
las 4 secciones. El LLM solo pule prosa, y el composer determinista es el
entregable por defecto — nunca queda en blanco.

⚠️ **Dos ejes de estado conviven a propósito** (H13 del plan):

- `estado()` — umbrales 90/75 — sirve los chips y las pestañas existentes.
- `estado_cierre()` — banda ámbar del 93 % — sirve las tarjetas KPI de cierre.

Unificarlos descalibraría tarjetas ya validadas contra mayo-2026 (Rubiales
95,6 % → ajustado; APIAY 50,7 % → actuar). **No se tocan.**
"""

from __future__ import annotations

import re
from typing import Any

from src.core.config import get_settings
from src.shared.catalogo_entidades import norm

# Unidad por producto. `dim_tipo_producto` NO tiene columna de unidad, así que
# se declara en código. GAS = MSCF (miles de pies cúbicos estándar, decisión
# del usuario 2026-07-21); CRUDO y BLANCOS en barriles. A5: cada producto con
# SU escala — mezclarlas ya causó un bug real (P50 de gas mostrado como "0,03
# MSCF" en vez de "33.453,2 bpd").
UNIDADES_PRODUCTO = {"CRUDO": "bbl", "BLANCOS": "bbl", "GAS": "MSCF"}

# Orden FIJO de los focos (decisión del usuario 2026-07-26). Ya NO se rankea
# por impacto ni se filtra a los rezagados: los 3 productos salen SIEMPRE.
ORDEN_PRODUCTOS = ["CRUDO", "GAS", "BLANCOS"]

# Etiquetas de los chips, derivadas del estado por Python (nunca por el LLM).
ETIQUETAS_ESTADO = {"ok": "Alineado", "warn": "Rezagado", "alert": "Foco", "": "—"}

# Detección de valle: run contiguo de >=3 días bajo la media*0.997, con al
# menos 5 puntos de serie. Los valores vienen del origen y están calibrados.
_UMBRAL_VALLE = 0.997
_MIN_DIAS_VALLE = 3
_MIN_PUNTOS_SERIE = 5

# Umbrales de los flags.
_PCT_CRITICO = 60
_CONCENTRACION_ALTA = 70
_PACE_EXIGENTE = 10


def estado(pct: float | None) -> str:
    """Chip de estado por cumplimiento. `""` = producto inexistente.

    INS-B: un producto que la entidad no produce (p.ej. Castilla no produce
    gas) va en NEUTRO, no en rojo — no es un incumplimiento.
    """
    if pct is None:
        return ""
    return "ok" if pct >= 90 else ("warn" if pct >= 75 else "alert")


def estado_cierre(proyectado: float, meta: float) -> str:
    """alineado (>=meta) / ajustado (>=meta*umbral) / actuar / "" (sin meta).

    Meta 0 devuelve `""`, no "actuar": un producto sin PPTO no está incumpliendo
    nada, simplemente no tiene con qué compararse.
    """
    if not meta:
        return ""
    proporcion = proyectado / meta
    umbral = get_settings().kpi_cierre_ambar_pct
    if proporcion >= 1.0:
        return "alineado"
    if proporcion >= umbral:
        return "ajustado"
    return "actuar"


def _formato(numero: float) -> str:
    """Miles con punto, formato es-CO."""
    return f"{abs(float(numero)):,.0f}".replace(",", ".")


# ── Tarjetas KPI de cierre (Nivel 1) ────────────────────────────────────────


def tarjetas_kpi(
    titular: list[dict[str, Any]],
    pace_por_producto: dict[str, dict[str, Any]] | None = None,
    hist_por_producto: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Una tarjeta por producto para el Nivel 1.

    `proyectado_cierre = titular['real']` SIN recalcular: ese valor YA es la
    proyección de cierre del mes completo, así que sumarle días de más lo
    infla. No se redondea aquí — el frontend verifica la igualdad byte a byte
    contra `titular.real` como gate de no-divergencia.

    `pace_por_producto` solo trae los productos cuya curva diaria RECONCILIA
    con el mensual. Los demás (p.ej. BLANCOS, cuyo diario suma ~2x el mes)
    quedan sin ritmo diario: el frontend les muestra solo la proyección
    mensual, en vez de inventar una tasa que no existe.
    """
    pace_por_producto = pace_por_producto or {}
    hist_por_producto = hist_por_producto or {}
    salida: list[dict[str, Any]] = []

    for fila in titular:
        producto = fila["producto"]
        meta = fila.get("ppto") or 0.0
        proyectado = fila.get("real") or 0.0
        historico = hist_por_producto.get(producto)

        # Fallback "sin meta formal": si el producto NO tiene PPTO pero sí
        # promedio del año, ese promedio pasa a ser la meta de cierre (mismo
        # criterio que las filiales, que no tienen presupuesto). Evita la
        # tarjeta muerta "Sin meta definida" y deja el % coherente con la
        # comparación "mes vs promedio del año" que el frontend ya muestra.
        meta_de_promedio = bool(not meta and historico)
        if meta_de_promedio and historico:
            meta = float(historico)

        relleno = round(min(proyectado / meta, 1.0) * 100, 1) if meta else 0.0

        ritmo = pace_por_producto.get(producto)
        bopd = None
        if ritmo and ritmo.get("promedio_dia") and ritmo.get("requerido_dia"):
            bopd = {
                "real": ritmo["promedio_dia"],
                "requerido": ritmo["requerido_dia"],
                "delta_pct": ritmo.get("delta_pct"),
            }

        salida.append(
            {
                "producto": producto,
                "unidad": UNIDADES_PRODUCTO.get(producto),
                "meta_mes": meta,
                "proyectado_cierre": proyectado,
                "brecha_abs": meta - proyectado,
                "relleno_pct": relleno,
                "alcanza": meta > 0 and proyectado >= meta,
                "estado": estado_cierre(proyectado, meta),
                "metodo": "proyeccion_de_cierre_del_reporte",
                "meta_de_promedio": meta_de_promedio,
                "bopd": bopd,
                "hist_prom": historico,
            }
        )
    return salida


# ── Detección y diagnóstico del valle ───────────────────────────────────────


def detectar_valle(serie: list[tuple[str, float]]) -> dict[str, Any] | None:
    """Valle = run contiguo más largo de >=3 días bajo la media*0.997."""
    if len(serie) < _MIN_PUNTOS_SERIE:
        return None

    valores = [v for _f, v in serie]
    umbral = (sum(valores) / len(valores)) * _UMBRAL_VALLE

    runs: list[list[tuple[str, float]]] = []
    actual: list[tuple[str, float]] = []
    for fecha, valor in serie:
        if valor < umbral:
            actual.append((fecha, valor))
        else:
            if len(actual) >= _MIN_DIAS_VALLE:
                runs.append(actual)
            actual = []
    if len(actual) >= _MIN_DIAS_VALLE:
        runs.append(actual)

    if not runs:
        return None

    valle = max(runs, key=len)
    minimo = min(valle, key=lambda x: x[1])
    return {
        "desde": valle[0][0],
        "hasta": valle[-1][0],
        "min_fecha": minimo[0],
        "min_valor": minimo[1],
    }


def _base_sin_producto(texto: str | None) -> str:
    """`CUPIAGUA (CRUDO)` → `CUPIAGUA`.

    En `fact_comentarios_produccion` el área trae a veces el producto como
    sufijo, porque el reporte separa el comentario por producto (144 de 648
    comentarios de mayo-2026). Comparar en crudo declaraba ajeno un comentario
    propio.
    """
    return norm((texto or "").split("(")[0].strip())


def elegir_comentario_del_valle(
    comentarios: list[dict[str, Any]], entidad: str
) -> tuple[str, bool]:
    """Devuelve `(quien_reporto, es_ajeno)` — atribución HONESTA.

    El comentario PROPIO de la entidad manda; el del grupo es el respaldo.
    `nombres_entidad` incluye `grupo1`/`activos`, o sea el grupo con el que el
    reporte agrupa a la entidad: LORITO trae `{LORITO, CPO-09}`, así que un
    comentario del área CPO-09 calza.

    El bug que esto corrige: el panel decía «Lo que reportó LORITO: "…apagado
    de los pozos AK107…"» cuando AK107 es de AKACIAS y el evento lo reportó
    CPO-09. El dato era relevante; la atribución, falsa.
    """
    if not comentarios:
        return "", False

    ordenados = sorted(
        comentarios,
        key=lambda c: 0 if _base_sin_producto(c.get("campo")) == norm(entidad) else 1,
    )
    quien = (ordenados[0].get("campo") or "").strip()
    es_ajeno = bool(quien) and _base_sin_producto(quien) != norm(entidad)
    return quien, es_ajeno


def contar_pozos_en_comentario(texto: str | None) -> int:
    """Suma los "N pozos" que menciona un comentario del reporte."""
    return sum(int(n) for n in re.findall(r"(\d+)\s*pozos", texto or ""))


# ── Situación general y tesis (Q2 — REGLA CERO) ─────────────────────────────


def situacion_general(
    titular: list[dict[str, Any]], sintesis: list[dict[str, Any]]
) -> dict[str, Any]:
    """La VERDAD del mes, declarada por Python: ¿hay rezago o no?

    Cuando NINGÚN producto va por debajo de su meta, `sintesis` y
    `detalle_por_producto` quedan vacíos: no hay rezago que analizar. Sin
    decírselo, el prompt igual le exigía a Gemma "la historia del mes" y
    "contrasta lo transitorio con lo estructural" → se inventaba el rezago.

    Caso verificado: CASTILLA campo, CRUDO al 102,7 % y pace sobrado, y Gemma
    narró un "déficit significativo respecto al promedio histórico". **La
    alucinación era lo grave**: con el JSON bien formado, ese brief falso se
    habría pintado como válido.
    """
    rezagados = [s["producto"] for s in sintesis]
    sin_meta = [t["producto"] for t in titular if t["valor_pct"] is None]
    con_meta = [t for t in titular if t["valor_pct"] is not None]

    if rezagados:
        resumen = "Hay rezago en: " + ", ".join(rezagados) + "."
    elif con_meta:
        detalle = ", ".join(f"{t['producto']} {t['valor_pct']}%" for t in con_meta)
        resumen = (
            "NO hay rezago: ningún producto con meta está por debajo de ella "
            f"({detalle})."
        )
    else:
        resumen = (
            "Ningún producto tiene meta definida en el periodo: no hay "
            "cumplimiento que evaluar."
        )

    if sin_meta:
        resumen += (
            " Sin meta definida (NO es un faltante, no hay con qué compararlos): "
            + ", ".join(sin_meta)
            + "."
        )

    return {
        "hay_rezago": bool(rezagados),
        "productos_rezagados": rezagados,
        "productos_sin_meta": sin_meta,
        "resumen": resumen,
    }


# ── Flags deterministas ─────────────────────────────────────────────────────


def flags_ejecutivo(
    titular: list[dict[str, Any]],
    gap_por_producto: dict[str, dict[str, Any]],
    valle: dict[str, Any] | None,
    pace: dict[str, Any] | None,
    ultimo_dia: str | None,
) -> list[dict[str, Any]]:
    """Flags calculados por Python, NUNCA por el LLM."""
    flags: list[dict[str, Any]] = []

    for fila in titular:
        if fila["valor_pct"] is not None and fila["valor_pct"] < _PCT_CRITICO:
            flags.append(
                {
                    "tipo": "producto_critico",
                    "severidad": "alta",
                    "producto": fila["producto"],
                    "pct": fila["valor_pct"],
                }
            )

    for producto, gap in gap_por_producto.items():
        concentracion = gap.get("concentracion_pct")
        if concentracion is not None and concentracion >= _CONCENTRACION_ALTA:
            flags.append(
                {
                    "tipo": "gap_concentrado",
                    "severidad": "media",
                    "producto": producto,
                    "concentracion_pct": concentracion,
                    "campos": [d["campo"] for d in gap["detractores"]],
                }
            )

    if valle:
        # El valle sigue ACTIVO si no se ha recuperado a la fecha de corte.
        activo = bool(ultimo_dia) and valle["hasta"] == ultimo_dia
        flags.append(
            {
                "tipo": "valle_activo",
                "severidad": "media" if activo else "baja",
                "activo": activo,
                "desde": valle["desde"],
                "hasta": valle["hasta"],
            }
        )

    if (
        pace
        and pace.get("delta_pct") is not None
        and pace["delta_pct"] >= _PACE_EXIGENTE
    ):
        flags.append(
            {
                "tipo": "pace_exigente",
                "severidad": "media",
                "delta_pct": pace["delta_pct"],
                "requerido_dia": pace["requerido_dia"],
                "promedio_dia": pace["promedio_dia"],
                "restantes": pace["restantes"],
            }
        )

    return flags


# ── Focos (Nivel 2) ─────────────────────────────────────────────────────────


def _etiqueta_ok(fila: dict[str, Any], tiene_produccion: bool) -> str:
    """Etiqueta honesta de un producto que NO va mal."""
    pct = fila.get("valor_pct")
    if pct is not None and pct >= 100:
        return "Alineado"
    if pct is not None:
        return "Ajustado"
    return "Sin meta" if tiene_produccion else "Sin producción"


def _sin_produccion(fila: dict[str, Any], tiene_produccion: bool) -> bool:
    """True SOLO cuando el producto no produce y no tiene meta.

    El frontend omite esos bloques: un campo que solo da crudo no debe pintar
    tarjetas vacías de gas y blancos.

    ⚠️ Un producto que produce 0 TENIENDO meta NO entra aquí. Eso es una merma
    real —el caso ARAUCA/gas verificado el 25-jul, con un paro de 30+17 días— y
    tiene que seguir visible.
    """
    return (fila or {}).get("valor_pct") is None and not tiene_produccion


def focos(
    titular: list[dict[str, Any]],
    gap_lag: dict[str, dict[str, Any]],
    valle: dict[str, Any] | None,
    eventos: list[dict[str, Any]],
    tarjetas: list[dict[str, Any]] | None = None,
    extremos: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """UNA tarjeta por producto, en orden FIJO Crudo→Gas→Blancos.

    Decisión del usuario 2026-07-26: ya NO se rankea por impacto ni se filtra a
    los rezagados. Un producto rezagado muestra sus campos que fallan y la
    causa; uno que va bien muestra un panorama con sus 2 mayores y 2 menores.
    """
    extremos = extremos or {}
    por_producto = {t["producto"]: t for t in titular}
    tarjeta_de = {k.get("producto"): k for k in (tarjetas or [])}
    salida: list[dict[str, Any]] = []

    for rango, producto in enumerate(ORDEN_PRODUCTOS, 1):
        fila = por_producto.get(producto)
        if not fila:
            continue

        pct = fila["valor_pct"]
        gap = gap_lag.get(producto)
        tarjeta = tarjeta_de.get(producto)

        rezago_por_gap = (
            pct is not None and pct < 100 and bool(gap and gap.get("detractores"))
        )
        rezago_por_promedio = (
            not rezago_por_gap
            and bool(tarjeta and tarjeta.get("meta_de_promedio"))
            and bool(tarjeta and (tarjeta.get("meta_mes") or 0))
            and bool(
                tarjeta
                and (tarjeta.get("proyectado_cierre") or 0)
                < (tarjeta.get("meta_mes") or 0)
            )
        )

        if rezago_por_gap and gap:
            salida.append(_foco_de_gap(producto, fila, gap, rango))
        elif rezago_por_promedio and tarjeta:
            salida.append(_foco_de_promedio(producto, tarjeta, rango))
        else:
            salida.append(_foco_ok(producto, fila, extremos.get(producto, []), rango))

    return salida


def _foco_de_gap(
    producto: str, fila: dict[str, Any], gap: dict[str, Any], rango: int
) -> dict[str, Any]:
    detractores = gap["detractores"][:2]
    entidades = [d["campo"] for d in detractores]
    faltante_neto = float(fila["real"]) - float(fila["ppto"])

    # 🔑 La concentración se calcula sobre LOS CAMPOS QUE SE NOMBRAN, no sobre
    # el top-3 fijo: con 2 campos el valor real de CUSIANA+CUPIAGUA es 88,2 %,
    # no el 90,6 % del top-3.
    bruto = abs(float(gap.get("faltante_bruto") or 0))
    concentracion = (
        round(abs(sum(d["gap"] for d in detractores)) / bruto * 100, 1)
        if bruto
        else None
    )

    titulo = (
        "concentra el rezago del producto"
        if (len(entidades) == 1 or concentracion is None)
        else f"{concentracion}% del faltante en {len(entidades)} campos"
    )

    compensador = gap["compensadores"][0] if gap.get("compensadores") else None
    accion = (
        f"sostener {compensador['campo']} (+{_formato(compensador['gap'])}) como amortiguador"
        if compensador
        else "plan de recuperación específico"
    )

    # El detalle lista faltantes BRUTOS; el titular es el NETO. Sin la línea de
    # cierre, el panel mostraba "-10.813.358" con un detalle que sumaba
    # 19.814.696 y nada que explicara la diferencia.
    detalle = [
        f"{d['campo']}: faltante {_formato(d['gap'])}" for d in gap["detractores"]
    ]
    excedente = float(gap.get("excedente_bruto") or 0)
    if bruto and excedente:
        detalle.append(
            f"Faltante bruto {_formato(bruto)} − excedentes {_formato(excedente)} "
            f"= neto {_formato(faltante_neto)}"
        )

    # Fuente/soporte real: comentarios del reporte para los campos NOMBRADOS.
    # NUNCA se inventa una causa: sin comentario que calce, texto genérico.
    eventos_causa = [
        {"campo": d["campo"], "fecha": ev["fecha"], "texto": ev["texto"]}
        for d in detractores
        for ev in (d.get("eventos") or [])
    ]
    if eventos_causa:
        primero = eventos_causa[0]
        causa_texto = f"{primero['campo']} ({primero['fecha']}): «{primero['texto']}»"
        cobertura = "con_evento"
    else:
        causa_texto = (
            "sin evento asociado en comentarios — requiere validación en campo"
        )
        cobertura = "sin_evento"

    return {
        "producto": producto,
        "entidades": entidades,
        "faltante_abs": round(faltante_neto),
        "faltante_bruto": gap.get("faltante_bruto"),
        "excedente_bruto": gap.get("excedente_bruto"),
        "magnitud_txt": None,
        "peso_relativo_pct": concentracion,
        "es_ok": False,
        "estado_label": "Foco",
        "sin_produccion": False,
        "titulo": titulo,
        "causa": {
            "texto": causa_texto,
            "cobertura": cobertura,
            "detalle": detalle,
            "eventos": eventos_causa,
        },
        "accion": accion,
        "tipo": "gap",
        "score": round(abs(faltante_neto)),
        "rank": rango,
    }


def _foco_de_promedio(
    producto: str, tarjeta: dict[str, Any], rango: int
) -> dict[str, Any]:
    proyectado = tarjeta.get("proyectado_cierre") or 0.0
    meta = tarjeta.get("meta_mes") or 0.0
    desviacion = round((1 - proyectado / meta) * 100) if meta else 0
    return {
        "producto": producto,
        "entidades": [],
        "faltante_abs": round(proyectado - meta),
        "magnitud_txt": None,
        "peso_relativo_pct": None,
        "es_ok": False,
        "estado_label": "Foco",
        "sin_produccion": False,
        "titulo": f"{desviacion}% por debajo de su promedio 2026",
        "causa": {
            "texto": (
                "produjo por debajo de su promedio del año — sin meta "
                "presupuestal en el periodo"
            ),
            "cobertura": "sin_meta",
            "detalle": [],
        },
        "accion": "revisar el comportamiento del producto frente a su histórico",
        "tipo": "promedio",
        "score": round(abs(proyectado - meta)),
        "rank": rango,
    }


def _foco_ok(
    producto: str,
    fila: dict[str, Any],
    extremos: list[dict[str, Any]],
    rango: int,
) -> dict[str, Any]:
    """Producto que va bien: panorama con sus 2 mayores y 2 menores."""
    return {
        "producto": producto,
        "entidades": [e["campo"] for e in extremos],
        "faltante_abs": None,
        "faltante_bruto": None,
        "excedente_bruto": None,
        "magnitud_txt": None,
        "peso_relativo_pct": None,
        "es_ok": True,
        "estado_label": _etiqueta_ok(fila, bool(extremos)),
        "sin_produccion": _sin_produccion(fila, bool(extremos)),
        "titulo": "",
        "extremos": extremos,
        "causa": {"texto": "", "cobertura": "ok", "detalle": [], "eventos": []},
        "accion": "",
        "tipo": "ok",
        "score": 0,
        "rank": rango,
    }


def sin_foco(
    titular: list[dict[str, Any]],
    gap_full: dict[str, dict[str, Any]],
    valle: dict[str, Any] | None,
) -> str:
    """Texto de cierre con los excedentes reales del periodo."""
    positivos: list[str] = []
    for fila in titular:
        gap = gap_full.get(fila["producto"])
        for compensador in (gap.get("compensadores") if gap else []) or []:
            positivos.append(
                f"{compensador['campo']} en {fila['producto'].lower()} "
                f"(+{_formato(compensador['gap'])})"
            )

    partes: list[str] = []
    if positivos:
        partes.append("con excedentes: " + ", ".join(positivos[:3]))
    if valle:
        partes.append("Crudo recuperado del valle")
    return " · ".join(partes) if partes else "Sin elementos adicionales."


# ── Composer determinista (el entregable por defecto) ───────────────────────


def componer_secciones(
    periodo: str,
    titular: list[dict[str, Any]],
    gap_por_producto: dict[str, dict[str, Any]],
    valle: dict[str, Any] | None,
    pace: dict[str, Any] | None,
    flags: list[dict[str, Any]],
    meta_nombre: str = "presupuesto",
    frase_dependencia: str = "riesgo de dependencia de pocos campos",
    frase_prioridad: str = "los campos que más arrastran",
) -> dict[str, list[str]]:
    """Arma las 4 secciones desde las cifras ya reconciliadas.

    ES el entregable por defecto: debe quedar completo y legible SIN el LLM.
    El segmento filiales pasa `meta_nombre`/`frase_*` distintos (programa,
    filiales).
    """
    valle_activo = any(f["tipo"] == "valle_activo" and f["activo"] for f in flags)

    insights: list[str] = []
    partes = [
        f"{t['producto'].capitalize()} {t['valor_pct']}%"
        for t in titular
        if t["valor_pct"] is not None
    ]
    if partes:
        insights.append(
            f"Cierre de {periodo}: " + ", ".join(partes) + f" del {meta_nombre}."
        )

    peor = min(
        [t for t in titular if t["valor_pct"] is not None],
        key=lambda t: t["valor_pct"],
        default=None,
    )
    if peor:
        # El guard `>= 100` evita hablar de "rezago" cuando todos los productos
        # cerraron por encima de la meta (caso real de filiales).
        if peor["valor_pct"] >= 100:
            insights.append(
                f"Todos los productos cerraron por encima del {meta_nombre}; el más "
                f"ajustado es {peor['producto'].lower()} ({peor['valor_pct']}%)."
            )
        else:
            insights.append(
                f"El mayor rezago está en {peor['producto'].lower()} "
                f"({peor['valor_pct']}% del {meta_nombre})."
            )

    if valle:
        estado_valle = (
            "y continúa sin recuperarse a la fecha de corte"
            if valle_activo
            else "y ya se recuperó"
        )
        insights.append(
            f"La producción de crudo tuvo un valle entre el {valle['desde']} y el "
            f"{valle['hasta']} (mínimo el {valle['min_fecha']}) {estado_valle}."
        )

    for producto, gap in gap_por_producto.items():
        if gap["detractores"]:
            campos = ", ".join(
                f"{d['campo']} (faltante {_formato(abs(d['gap']))})"
                for d in gap["detractores"]
            )
            concentracion = (
                f" — concentración {gap['concentracion_pct']}%"
                if gap["concentracion_pct"] is not None
                else ""
            )
            insights.append(
                f"El faltante de {producto.lower()} se concentra en {campos}"
                f"{concentracion}."
            )

    if pace and pace.get("delta_pct") is not None:
        insights.append(
            f"Para cerrar crudo en {meta_nombre} se requieren "
            f"{_formato(pace['requerido_dia'])} bls/día en los {pace['restantes']} días "
            f"restantes ({pace['delta_pct']:+}% vs el promedio actual de "
            f"{_formato(pace['promedio_dia'])})."
        )

    if not insights:
        insights.append("Producción sin hallazgos relevantes en el periodo.")

    oportunidades: list[str] = []
    for producto, gap in gap_por_producto.items():
        if gap["compensadores"]:
            campos = ", ".join(
                f"{d['campo']} (excedente {_formato(d['gap'])})"
                for d in gap["compensadores"]
            )
            oportunidades.append(
                f"{campos} produjeron por encima de su meta y amortiguan parte del "
                f"faltante de {producto.lower()}; sostener su ritmo ayuda a cerrar la "
                "brecha."
            )
    if valle and not valle_activo:
        oportunidades.append(
            "El valle de crudo fue transitorio (eventos operativos) — no hay evidencia "
            "de una caída estructural."
        )
    if not oportunidades:
        oportunidades.append(
            "Sin oportunidades adicionales identificadas en el periodo."
        )

    puntos_atencion: list[str] = []
    for flag in flags:
        if flag["tipo"] == "producto_critico":
            puntos_atencion.append(
                f"{flag['producto']} está en zona crítica: {flag['pct']}% del "
                f"{meta_nombre} (<60%)."
            )
        elif flag["tipo"] == "gap_concentrado":
            puntos_atencion.append(
                f"El faltante de {flag['producto'].lower()} está muy concentrado "
                f"(~{flag['concentracion_pct']}% en {', '.join(flag['campos'])}) — "
                f"{frase_dependencia}."
            )
        elif flag["tipo"] == "pace_exigente":
            puntos_atencion.append(
                f"El ritmo requerido para crudo exige un +{flag['delta_pct']}% sobre el "
                "promedio actual — meta exigente para los días restantes."
            )
        elif flag["tipo"] == "valle_activo" and flag["activo"]:
            puntos_atencion.append(
                f"El valle de crudo iniciado el {flag['desde']} continúa a la fecha de "
                "corte, sin señales de recuperación."
            )

    for producto, gap in gap_por_producto.items():
        if gap["reconciliado"] is False:
            puntos_atencion.append(
                f"La descomposición por campo de {producto.lower()} presenta un desfase "
                f"de {gap['desfase_pct']}% frente al KPI; cifras a validar."
            )
    if not puntos_atencion:
        puntos_atencion.append("Sin puntos de atención críticos en el periodo.")

    decisiones: list[str] = []
    for producto, gap in gap_por_producto.items():
        if gap["detractores"]:
            campos = " y ".join(d["campo"] for d in gap["detractores"][:2])
            decisiones.append(
                f"Priorizar diagnóstico operativo en {campos} ({frase_prioridad} el "
                f"faltante de {producto.lower()})."
            )
    if valle:
        decisiones.append(
            "Monitorear la estabilidad eléctrica/operativa en los campos afectados por "
            "el valle de crudo."
        )
    if (
        pace
        and pace.get("delta_pct") is not None
        and pace["delta_pct"] >= _PACE_EXIGENTE
    ):
        decisiones.append(
            f"Acordar con operaciones un ritmo de {_formato(pace['requerido_dia'])} "
            f"bls/día de crudo para los próximos {pace['restantes']} días."
        )
    if not decisiones:
        decisiones.append(
            "Mantener el seguimiento habitual del cierre de mes; sin acciones "
            "adicionales urgentes."
        )

    return {
        "insights": insights[:5],
        "oportunidades": oportunidades[:4],
        "puntos_atencion": puntos_atencion[:4],
        "decisiones": decisiones[:4],
    }
