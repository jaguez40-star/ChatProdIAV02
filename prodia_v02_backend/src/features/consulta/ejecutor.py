"""Ejecuta la pregunta cuantificable y arma el contrato de respuesta.

Portado de `consulta_v2/cuantificar/ejecutor.py` (253 líneas).

**Frontera dura del módulo**: no tiene SQL propio ni llama al LLM. Consume los
servicios de análisis —inyectados, ver `niveles`— y arma el contrato. La prosa
la pone otro; el formato del número, `validador`.

🔑 **D1 — el NIVEL se dice siempre.** "el Campo CASTILLA" y "el Activo
CASTILLA" son cifras DISTINTAS (6,9 M bbl vs 11,7 M en el sistema viejo) y sin
el rótulo son indistinguibles. Por eso `entidad_cualificada` lleva artículo y
nivel concordados, nunca el nombre pelado.

**Rechazos honestos, no silencios.** Cada `{aplica: False, texto}` explica qué
se pidió, qué sí se puede dar y cómo reformular. El caso canónico es el P50:
existe solo a nivel corporativo y en otra escala, así que compararlo contra un
campo daría un número sin sentido — se declina y se ofrecen las referencias que
sí aplican.
"""

from __future__ import annotations

from typing import Any, Protocol

from src.features.consulta import niveles
from src.features.consulta.niveles import DesempenoFn
from src.features.consulta.validador import fmt_valor


class EscenarioFn(Protocol):
    """Firma del helper de escenarios de presupuesto.

    Está aislado del servicio de desempeño a propósito (AF-4.2 del origen):
    meter OPERATIVO/CONTABLE en la consulta principal cambiaría `sin_cierre` y
    volvería `False` un caso que debía ser `True`.
    """

    def __call__(
        self,
        entidad: str,
        nivel: str | None = None,
        periodo: str | None = None,
        escenarios: tuple[str, ...] = ("OPERATIVO", "CONTABLE"),
    ) -> dict[str, dict[str, float]]: ...


_ESTADO_LABEL = {
    "ok": "Alineado",
    "warn": "Rezagado",
    "alert": "Foco",
    "": "sin meta",
}

# D1: artículo + nivel concordados. "la fuente" para pozo porque el grano de
# pozo no existe en esta BD — es un alias heredado, y nombrarlo "pozo" sería
# prometer un detalle que no hay.
_NIVEL_TEXTO = {
    "campo": "el Campo",
    "activo": "el Activo",
    "gerencia": "la Gerencia",
    "vicepresidencia": "la Vicepresidencia",
    "fuente": "la fuente",
    "pozo": "la fuente",
    "operador": "la operación de",
}

_PROD_MAP = {"crudo": "CRUDO", "gas": "GAS", "blancos": "BLANCOS"}

_REF_LABEL = {
    "PPTO": "presupuesto",
    "OPERATIVO": "presupuesto operativo",
    "CONTABLE": "cierre contable",
    "promedio_anio": "promedio mensual del año",
}
_REF_ESCENARIO = {"OPERATIVO": "OPERATIVO", "CONTABLE": "CONTABLE"}

# Bandas de estado. Mismo eje que usa el tablero, para que el chat no invente
# una escala propia.
_UMBRAL_OK = 90.0
_UMBRAL_WARN = 75.0


def _estado(cumplimiento: float | None) -> str:
    if cumplimiento is None:
        return ""
    if cumplimiento >= _UMBRAL_OK:
        return "ok"
    if cumplimiento >= _UMBRAL_WARN:
        return "warn"
    return "alert"


def _etiqueta_nivel(nivel: str | None, resuelta: dict[str, Any]) -> str:
    """R2: si el resolver marcó `puente`, se rotula con el nivel REAL.

    El `nivel` con el que se consultó NO cambia: esto solo afecta al texto que
    lee el usuario.
    """
    if resuelta.get("puente"):
        return _NIVEL_TEXTO["vicepresidencia"]
    return _NIVEL_TEXTO.get(nivel or "", "")


def _valor_referencia(
    ref: str,
    fila: dict[str, Any],
    desempeno: dict[str, Any],
    dim_producto: str,
    resuelta: dict[str, Any],
    slots: dict[str, Any],
    escenario_fn: EscenarioFn | None,
) -> tuple[float | None, str]:
    """Valor y etiqueta de la referencia elegida."""
    label = _REF_LABEL.get(ref, "presupuesto")

    if ref == "PPTO":
        return fila.get("ppto"), label

    if ref == "promedio_anio":
        ritmo = desempeno.get("ritmo_mensual") or {}
        valor = (ritmo.get("promedio_mes") or {}).get(dim_producto)
        return valor, label

    if escenario_fn is None:
        return None, label

    nombre_escenario = _REF_ESCENARIO.get(ref)
    if nombre_escenario is None:
        return None, label

    escenarios = escenario_fn(
        resuelta["valor"],
        nivel=resuelta.get("nivel"),
        periodo=slots.get("periodo_texto"),
        escenarios=(nombre_escenario,),
    )
    return (escenarios.get(dim_producto) or {}).get(nombre_escenario), label


def _rechazo_comun(
    resuelta: dict[str, Any], slots: dict[str, Any]
) -> dict[str, Any] | None:
    """Validaciones compartidas. `None` si la pregunta puede seguir."""
    if resuelta.get("rama") == "B":
        return {
            "aplica": False,
            "texto": (
                f"«{resuelta['valor']}» es una filial; su cuantificación llega "
                "en una próxima fase."
            ),
        }
    if slots.get("producto") not in _PROD_MAP:
        return {
            "aplica": False,
            "texto": (
                f"No sé cuantificar «{slots.get('producto')}»; puedo con crudo, "
                "gas o blancos."
            ),
        }
    return None


def ejecutar(
    resuelta: dict[str, Any],
    slots: dict[str, Any],
    *,
    desempeno_fn: DesempenoFn,
    escenario_fn: EscenarioFn | None = None,
) -> dict[str, Any]:
    """Despacha por nivel temporal: N1 puntual · N2 acumulado · N3 · N4."""
    nivel_temporal = slots.get("nivel_temporal")
    if nivel_temporal == "N4":
        return ejecutar_n4(resuelta, slots, desempeno_fn=desempeno_fn)
    if nivel_temporal == "N3":
        return ejecutar_n3(resuelta, slots, desempeno_fn=desempeno_fn)
    if nivel_temporal == "N2":
        return ejecutar_n2(resuelta, slots, desempeno_fn=desempeno_fn)
    return ejecutar_n1(
        resuelta, slots, desempeno_fn=desempeno_fn, escenario_fn=escenario_fn
    )


def ejecutar_n1(
    resuelta: dict[str, Any],
    slots: dict[str, Any],
    *,
    desempeno_fn: DesempenoFn,
    escenario_fn: EscenarioFn | None = None,
) -> dict[str, Any]:
    """N1: la cifra de UN mes contra su referencia."""
    rechazo = _rechazo_comun(resuelta, slots)
    if rechazo:
        return rechazo

    producto = slots["producto"]
    unidad = slots.get("unidad", "bbl")
    ref = slots.get("referencia", "PPTO")

    if ref == "P50":
        # Rechazo honesto: el P50 vive en otra escala y a otro nivel. Compararlo
        # contra un campo daría un número sin significado.
        return {
            "aplica": False,
            "texto": (
                "El P50 (compromiso) solo existe a nivel corporativo ECP-global, "
                "en kbpe, y no reconcilia con el reporte a nivel "
                f"campo/activo/gerencia; no puedo comparar «{resuelta['valor']}» "
                "contra P50. Puedo con el presupuesto (PPTO), el operativo, el "
                "contable o el promedio del año."
            ),
        }

    dim_producto = _PROD_MAP[producto]
    desempeno = niveles._como_dict(
        desempeno_fn(
            entidad=resuelta["valor"],
            nivel=resuelta.get("nivel"),
            periodo=slots.get("periodo_texto"),
        )
    )

    if not desempeno.get("encontrada") or desempeno.get("sin_datos"):
        return {
            "aplica": False,
            "texto": f"No tengo datos de producción para «{resuelta['valor']}».",
        }
    if desempeno.get("sin_cierre"):
        return {
            "aplica": False,
            "texto": (
                f"«{resuelta['valor']}» aún no tiene cierre mensual (REAL/PPTO) "
                "para ese mes."
            ),
        }

    mes = desempeno["mes"]
    fila = next(
        (p for p in desempeno["por_producto"] if p["producto"] == dim_producto), None
    )
    if fila is None or (fila["real"] == 0 and fila["ppto"] == 0):
        return {
            "aplica": False,
            "texto": f"«{resuelta['valor']}» no reporta {producto} en ese periodo.",
        }

    real = fila["real"]
    ref_valor, ref_label = _valor_referencia(
        ref, fila, desempeno, dim_producto, resuelta, slots, escenario_fn
    )

    # El cumplimiento se recalcula contra la referencia ELEGIDA, no se hereda
    # del payload: si no, "vs operativo" mostraría el porcentaje del PPTO.
    cumplimiento = round(real / ref_valor * 100.0, 1) if ref_valor else None

    if ref == "promedio_anio" and cumplimiento is not None:
        # El promedio no es una meta: decir "Rezagado" contra él sería juzgar
        # con una vara que nadie pactó.
        estado = "sobre el promedio" if cumplimiento >= 100 else "bajo el promedio"
    else:
        estado = _ESTADO_LABEL.get(_estado(cumplimiento), "")

    nivel = resuelta.get("nivel")
    proyeccion = (not mes["completo"]) and bool(mes["dias_con_data"])

    avisos: list[str] = []
    if slots.get("descargo"):
        avisos.append(slots["descargo"])
    if ref != "PPTO" and not ref_valor:
        avisos.append(
            f"No hay {ref_label} registrado para {mes['nombre']} {mes['anio']}; "
            "muestro lo producido."
        )
    for sin_meta in desempeno.get("campos_sin_meta") or []:
        if sin_meta["producto"] == dim_producto:
            avisos.append(
                f"El campo {sin_meta['campo']} produce sin meta asignada "
                f"({fmt_valor(sin_meta['real'], producto)} {unidad} fuera del "
                "presupuesto)."
            )

    return {
        "aplica": True,
        "grupo": "cuantificar",
        "variable": slots.get("variable", "produccion_crudo"),
        "nivel": "N1",
        "entidad": {"nombre": resuelta["valor"], "nivel": nivel, "fue_asumida": False},
        "entidad_cualificada": (
            f"{_etiqueta_nivel(nivel, resuelta)} {resuelta['valor']}".strip()
        ),
        "producto": producto,
        "referencia": ref,
        "referencia_label": ref_label,
        "unidad": unidad,
        "grano": "mes",
        "universo": "reporte_diario",
        "huella": {
            "registros": mes.get("dias_con_data"),
            "rango_disponible": [
                f"{mes['anio']}-{mes['mes']:02d}-01",
                f"{mes['anio']}-{mes['mes']:02d}-{mes['dias_del_mes']:02d}",
            ],
            "dias_del_mes": mes.get("dias_del_mes"),
            "es_proyeccion": proyeccion,
        },
        "resultado": {"valor": real},
        "referencia_valor": ref_valor,
        "cumplimiento_pct": cumplimiento,
        "estado": estado,
        "mes": mes,
        "defaults_asumidos": slots.get("defaults_asumidos", []),
        "avisos": avisos,
        "zoom": resuelta.get("zoom", []),
    }


def ejecutar_n2(
    resuelta: dict[str, Any],
    slots: dict[str, Any],
    *,
    desempeno_fn: DesempenoFn,
) -> dict[str, Any]:
    """N2: acumulado de los meses cerrados del año.

    🔑 HE6: NO fabrica un `mes` sintético. Trae sus propias claves
    (`periodo_label`, `meses_cerrados`, `en_curso`), porque un acumulado no es
    un mes y fingir que lo es confundiría al formateador.
    """
    rechazo = _rechazo_comun(resuelta, slots)
    if rechazo:
        return rechazo

    producto = slots["producto"]
    unidad = slots.get("unidad", "bbl")

    acumulado = niveles.acumulado(resuelta, _PROD_MAP[producto], desempeno_fn)
    if not acumulado.get("aplica"):
        return {"aplica": False, "texto": acumulado["texto"]}

    real = acumulado["real"]
    ppto = acumulado["ppto"]
    cumplimiento = round(real / ppto * 100.0, 1) if ppto else None
    estado = _ESTADO_LABEL.get(_estado(cumplimiento), "")

    meses = acumulado["meses"]
    periodo_label = (
        meses[0] if len(meses) == 1 else f"{meses[0]}–{meses[-1]}"
    ) + f" {acumulado['anio']}"

    avisos: list[str] = []
    if slots.get("descargo"):
        avisos.append(slots["descargo"])
    if acumulado.get("en_curso"):
        avisos.append(
            f"El mes de {acumulado['en_curso']['nombre']} sigue en curso; su "
            "proyección NO está incluida en el acumulado."
        )
    if slots.get("referencia", "PPTO") != "PPTO":
        # AF-4.7: se declara en vez de aplicar en silencio una referencia que
        # no corresponde al acumulado.
        avisos.append(
            "Las referencias alternas (operativo/contable/promedio) por ahora "
            "solo aplican al dato puntual de un mes; el acumulado se compara "
            "con el presupuesto (PPTO)."
        )

    nivel = resuelta.get("nivel")
    return {
        "aplica": True,
        "grupo": "cuantificar",
        "variable": slots.get("variable", "produccion_crudo"),
        "nivel": "N2",
        "entidad": {"nombre": resuelta["valor"], "nivel": nivel, "fue_asumida": False},
        "entidad_cualificada": (
            f"{_etiqueta_nivel(nivel, resuelta)} {resuelta['valor']}".strip()
        ),
        "producto": producto,
        "unidad": unidad,
        "grano": "mes",
        "periodo_label": periodo_label,
        "meses_cerrados": len(meses),
        "en_curso": acumulado.get("en_curso"),
        "resultado": {"valor": real},
        "referencia_valor": ppto,
        "cumplimiento_pct": cumplimiento,
        "estado": estado,
        "anio": acumulado["anio"],
        "defaults_asumidos": slots.get("defaults_asumidos", []),
        "avisos": avisos,
        "zoom": resuelta.get("zoom", []),
    }


def _base_serie(
    resuelta: dict[str, Any], slots: dict[str, Any], nivel_q: str
) -> dict[str, Any]:
    """Claves comunes de N3 y N4."""
    nivel = resuelta.get("nivel")
    return {
        "aplica": True,
        "grupo": "cuantificar",
        "variable": slots.get("variable", "produccion_crudo"),
        "nivel": nivel_q,
        "entidad": {"nombre": resuelta["valor"], "nivel": nivel, "fue_asumida": False},
        "entidad_cualificada": (
            f"{_etiqueta_nivel(nivel, resuelta)} {resuelta['valor']}".strip()
        ),
        "producto": slots["producto"],
        "unidad": slots.get("unidad", "bbl"),
        "grano": "mes",
        "defaults_asumidos": slots.get("defaults_asumidos", []),
        "zoom": resuelta.get("zoom", []),
    }


def _avisos_proyeccion(slots: dict[str, Any], proyeccion_mes: str | None) -> list[str]:
    avisos: list[str] = []
    if slots.get("descargo"):
        avisos.append(slots["descargo"])
    if proyeccion_mes:
        avisos.append(
            f"El mes de {proyeccion_mes} sigue en curso; su valor es una proyección."
        )
    return avisos


def ejecutar_n3(
    resuelta: dict[str, Any],
    slots: dict[str, Any],
    *,
    desempeno_fn: DesempenoFn,
) -> dict[str, Any]:
    """N3: la serie mensual."""
    rechazo = _rechazo_comun(resuelta, slots)
    if rechazo:
        return rechazo

    resultado = niveles.serie(resuelta, _PROD_MAP[slots["producto"]], desempeno_fn)
    if not resultado.get("aplica"):
        return {"aplica": False, "texto": resultado["texto"]}

    salida = _base_serie(resuelta, slots, "N3")
    salida.update(
        {
            "serie": resultado["serie"],
            "promedio": resultado["promedio"],
            "anio": resultado["anio"],
            "proyeccion_mes": resultado["proyeccion_mes"],
            "avisos": _avisos_proyeccion(slots, resultado["proyeccion_mes"]),
        }
    )
    return salida


def ejecutar_n4(
    resuelta: dict[str, Any],
    slots: dict[str, Any],
    *,
    desempeno_fn: DesempenoFn,
) -> dict[str, Any]:
    """N4: la variación mes a mes."""
    rechazo = _rechazo_comun(resuelta, slots)
    if rechazo:
        return rechazo

    resultado = niveles.variacion(resuelta, _PROD_MAP[slots["producto"]], desempeno_fn)
    if not resultado.get("aplica"):
        return {"aplica": False, "texto": resultado["texto"]}

    salida = _base_serie(resuelta, slots, "N4")
    salida.update(
        {
            "deltas": resultado["deltas"],
            "ultimo": resultado["ultimo"],
            "anio": resultado["anio"],
            "proyeccion_mes": resultado["proyeccion_mes"],
            "avisos": _avisos_proyeccion(slots, resultado["proyeccion_mes"]),
        }
    )
    return salida
