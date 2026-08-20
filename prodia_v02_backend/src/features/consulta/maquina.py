"""Orquestador del Motor Q — Capa 1 → filtro de dominio → Capa 2.

Portado de `consulta_v2/maquina_q.py:313-446`.

**El flujo, en orden:**

1. **Capa 1** (`patrones`): regex determinista. Si atrapa, tenemos la FORMA.
2. **Filtro de dominio**: la regex vio la forma, pero ¿el TEMA es de
   producción? Solo se aplica a patrones genéricos — los anclados ya son señal
   de dominio por sí mismos.
3. **Capa 2** (LLM): solo cuando la regex no decidió, o cuando decidió con
   evidencia apenas "estructural".

🔑 **D4 — FALLBACK OBLIGATORIO.** Si el LLM falla (timeout, conexión, JSON
malo), se **CONSERVA** el grupo que dio la regex. Una caída del modelo degrada
al comportamiento previo; jamás se traga una pregunta legítima.

🔑 **D6 — la entidad del LLM se ignora.** Se escaló precisamente porque el
catálogo no encontró ninguna; si el modelo la inventa, mentiría.

**Diferencia con el origen**: allí un solo flag `log` decide a la vez si se
escribe en la libreta y si se responde de verdad (`elif grupo == "X" and log`).
Son dos preguntas distintas y aquí van separadas: `registrar` y `responder`.
Mezclarlas hacía que el golden, al pasar `log=False`, ejercitara un camino
distinto del de producción.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from src.features.consulta import drills
from src.features.consulta.clasificador import clasificar_capa2
from src.features.consulta.dominio import nivel_dominio
from src.features.consulta.memoria import ContextoConversacion
from src.features.consulta.patrones import clasificar_capa1, es_anclado

GRUPO_LABEL = {
    "jerarquizar": "Jerarquizar",
    "cuantificar": "Cuantificar",
    "analizar": "Analizar",
    "desconocido": "Desconocido",
}

# Detector de entidad contra el catálogo. Se inyecta porque necesita sesión de
# BD y este módulo debe poder razonarse sin ella.
DetectorEntidad = Callable[[str], str | None]

# Escritor de la libreta. Devuelve el id del registro, o `None` si falló.
RegistradorLibreta = Callable[..., int | None]


def _mensaje_base(grupo: str, entidad: str | None) -> str:
    """Mensaje cuando no hay un redactor de grupo conectado todavía."""
    if grupo == "desconocido":
        return (
            "Esa pregunta está fuera de lo que puedo responder. Manejo tres "
            "temas: estructura organizacional, cifras de producción y análisis "
            "de desempeño. ¿Cuál te interesa?"
        )
    etiqueta = GRUPO_LABEL.get(grupo, grupo)
    if entidad:
        return f"[{etiqueta}] Entendí que preguntas por «{entidad}»."
    return f"[{etiqueta}] Entendí el tipo de pregunta."


def clasificar_nucleo(
    texto: str,
    *,
    detectar_entidad: DetectorEntidad,
) -> dict[str, Any]:
    """Decide el grupo. Sin memoria, sin libreta y sin despacho.

    Es el núcleo puro: mismo texto, mismo veredicto. Lo envuelve `clasificar`.
    """
    grupo, patrones = clasificar_capa1(texto)
    capa = "regex"
    entidad: str | None = None
    diagnostico: dict[str, Any] = {}

    if grupo is not None:
        # La regex atrapó la FORMA; toca confirmar el TEMA.
        if not es_anclado(patrones):
            entidad = detectar_entidad(texto)
            if not entidad:
                nivel = nivel_dominio(texto)
                if nivel is None:
                    # Ni entidad del catálogo ni vocabulario: fuera de dominio.
                    # Se conservan los patrones para poder trazar POR QUÉ
                    # disparó la regex.
                    grupo, capa = "desconocido", "regex+filtro"
                elif nivel == "estructural":
                    # Certeza DÉBIL: "campos de la dieta mediterránea" y
                    # "campos por debajo de la meta" traen la misma palabra, y
                    # la regex no ve el contexto gramatical. Lo confirma el LLM.
                    veredicto = clasificar_capa2(texto, diagnostico)
                    if veredicto is None:
                        # 🔑 D4: el LLM falló → se CONSERVA el grupo de la regex.
                        capa = "regex+llm_fallo"
                    else:
                        grupo, capa = veredicto, "regex+llm"
    else:
        veredicto = clasificar_capa2(texto, diagnostico)
        grupo = veredicto or "desconocido"
        capa = "llm"
        patrones = []
        # 🔑 D6: la entidad que devolvió el LLM NO se usa para consultar.

    if not entidad:
        entidad = detectar_entidad(texto)

    return {
        "grupo": grupo,
        "capa_resolutora": capa,
        "entidad_cruda": entidad,
        "patrones": patrones or [],
        "llm_diag": diagnostico.get("llm_diag"),
    }


def clasificar(
    texto: str,
    *,
    detectar_entidad: DetectorEntidad,
    contexto: ContextoConversacion | None = None,
    registrar: RegistradorLibreta | None = None,
    usuario: str | None = None,
    conversacion_id: str | None = None,
) -> dict[str, Any]:
    """Clasifica una pregunta, aplicando antes la reescritura conversacional.

    `registrar` es opcional: si no se pasa, no se escribe en la libreta. Eso
    permite que el golden y los tests ejerciten EL MISMO camino que producción,
    a diferencia del origen.
    """
    efectivo = texto
    continuacion = False

    if contexto is not None:
        reescrito = drills.reescribir(texto, contexto, detectar_entidad)
        if reescrito:
            efectivo, continuacion = reescrito, True

    nucleo = clasificar_nucleo(efectivo, detectar_entidad=detectar_entidad)

    log_id: int | None = None
    if registrar is not None:
        try:
            log_id = registrar(
                texto=efectivo,
                grupo=nucleo["grupo"],
                capa=nucleo["capa_resolutora"],
                patrones=nucleo["patrones"] or None,
                entidad=nucleo["entidad_cruda"],
                usuario=usuario,
                conversacion_id=conversacion_id,
                llm_diag=nucleo["llm_diag"],
            )
        except Exception:
            # 🔑 Regla madre: la libreta NUNCA tumba la respuesta.
            log_id = None

    respuesta: dict[str, Any] = {
        "log_id": log_id,
        "texto_original": texto,
        "grupo": nucleo["grupo"],
        "grupo_label": GRUPO_LABEL.get(nucleo["grupo"], nucleo["grupo"]),
        "capa_resolutora": nucleo["capa_resolutora"],
        "entidad_cruda": nucleo["entidad_cruda"],
        "patrones": nucleo["patrones"],
        "llm_diag": nucleo["llm_diag"],
        "timestamp": datetime.now(UTC).isoformat(),
        "mensaje": _mensaje_base(nucleo["grupo"], nucleo["entidad_cruda"]),
        "panel": None,
        "vp_ofrecida": None,
    }

    if continuacion:
        # Se muestra lo que el usuario escribió, no lo reescrito.
        respuesta["continuacion"] = True
        respuesta["texto_efectivo"] = efectivo

    return respuesta
