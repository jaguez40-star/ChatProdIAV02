"""Prompts del Análisis Ejecutivo — la prosa aislada del cálculo.

Portado de `INGESTA/Rep_Prod/backend/app/features/analisis/api.py:1038-1089`
y los prompts de `desempeno_insight`/`ejecutivo`.

**Python calcula, el LLM redacta** (Q1). Estos textos NUNCA piden al modelo que
calcule, deduzca ni complete cifras: los números llegan ya resueltos en el
bloque `Datos` y el modelo solo los envuelve en prosa.

Viven en su propio módulo porque son la parte más volátil del sistema —se
ajustan con cada hallazgo de redacción— y no deben obligar a tocar la lógica.
"""

from __future__ import annotations

import json
from typing import Any


def reglas_tesis(situacion: dict[str, Any]) -> str:
    """Reglas de análisis, RAMIFICADAS según haya rezago o no (Q2).

    El prompt original asumía que SIEMPRE hay un rezago que explicar. Cuando no
    lo hay, `sintesis` y `detalle_por_producto` llegan vacíos y esas mismas
    reglas ('nárrala', 'contrasta lo transitorio con lo estructural',
    'menciona campos') empujan al modelo a FABRICAR el problema que le piden.

    Aquí la instrucción se adapta a la verdad que Python ya calculó.
    """
    if situacion["hay_rezago"]:
        return (
            "TU TAREA NO ES DESCRIBIR, ES ANALIZAR. No recites producto por producto de "
            "forma mecánica: identifica LA historia del mes, lo NO obvio, y prioriza. "
            "Apóyate en el bloque 'sintesis' (ya trae la interpretación: qué rezago es "
            "transitorio y cuál estructural, y si el faltante está focalizado en pocos "
            "campos o es sistémico) — es tu tesis, nárrala.\n"
            "2. El PRIMER insight es LA historia del mes en 1-2 frases: contrasta lo "
            "transitorio (ya superado, no preocupa) con lo estructural (persiste, es el "
            "foco real). Ej. de forma: 'El mes tiene dos caras: X ya se recuperó de un "
            "bache puntual, pero Y arrastra un déficit que persiste'.\n"
            "3. Distingue SIEMPRE foco de problema sistémico: si el faltante está "
            "concentrado en pocos campos, dilo como una VENTAJA (el problema es "
            "localizado, se ataca en esos campos), no solo como un riesgo.\n"
            "4. Al mencionar campos, contrasta los dos lados (los que arrastran el "
            "faltante y los que lo amortiguan produciendo por encima de su meta). No "
            "repitas el mismo dato en dos secciones.\n"
            "SECCIONES: insights = la historia del mes (regla 2) + el hallazgo no obvio "
            "(foco) + pace de crudo. oportunidades = palancas reales (campos por encima "
            "de su meta que conviene sostener; un rezago focalizado que se puede cerrar "
            "atacando pocos campos). puntos_atencion = riesgos priorizados. decisiones = "
            "acciones concretas y priorizadas.\n"
        )

    # Sin rezago: la única falla posible aquí es inventarse uno.
    resumen = str(situacion["resumen"])
    return (
        "TU TAREA NO ES DESCRIBIR, ES ANALIZAR — pero lee primero "
        "'situacion_general': " + resumen + "\n"
        "REGLA CERO, INQUEBRANTABLE: ESTE MES NO HAY REZAGO. Está PROHIBIDO inventar un "
        "déficit, un faltante, una caída estructural o un problema que los datos no "
        "muestran. Sería FALSO y el directivo tomaría decisiones sobre un problema "
        "inexistente. Si te falta material para una sección, escribe UNA sola frase "
        "honesta (ej. 'Sin puntos de atención críticos en el periodo') en vez de "
        "rellenar.\n"
        "2. El PRIMER insight es que la entidad va en meta o por encima, con el "
        "porcentaje EXACTO. Lo analítico aquí no es buscar culpables: es decir QUÉ "
        "sostiene el resultado y qué lo pondría en riesgo de cara al cierre.\n"
        "3. 'detalle_por_producto' viene VACÍO porque no hay faltante que descomponer. "
        "NO menciones campos ni inventes nombres: no tienes ese dato.\n"
        "4. Si hubo un valle de crudo ya recuperado, es contexto de un bache puntual "
        "superado, NO un rezago del mes. Atribuye una causa SOLO si aparece en "
        "'eventos_del_valle'. Si ese bloque viene vacío, no tienes la causa a la mano: "
        "NO la inventes, y tampoco afirmes que no existe (puede estar documentada en "
        "otra parte del reporte).\n"
        "5. Mira 'pace_crudo': si 'requerido_dia' es MENOR que 'promedio_dia' el ritmo "
        "actual SOBRA para cerrar en meta (buena noticia, delta_pct negativo); solo si "
        "es mayor hay exigencia. NO lo leas al revés.\n"
        "SECCIONES: insights = el resultado y con qué margen + qué lo sostiene + lectura "
        "del pace. oportunidades = qué conviene sostener o aprovechar. puntos_atencion = "
        "riesgos REALES de cara al cierre (si no los hay, dilo en una frase). decisiones "
        "= acciones concretas para sostener el desempeño (si no hay nada que corregir, "
        "basta con monitorear lo que corresponda).\n"
    )


def prompt_ejecutivo(contexto: dict[str, Any], situacion: dict[str, Any]) -> str:
    """Prompt multi-sección: 4 arrays de frases para directivos NO técnicos."""
    return (
        "Eres analista de producción petrolera y escribes para directivos NO técnicos. "
        "Con estos datos EXACTOS (no inventes ni recalcules cifras) devuelve SOLO un "
        'JSON con 4 arrays de frases: {"insights":[],"oportunidades":[],'
        '"puntos_atencion":[],"decisiones":[]}.\n'
        "FORMATO ESTRICTO: responde ÚNICAMENTE el objeto JSON, sin ``` ni texto antes o "
        "después; usa comillas dobles; NO pongas comas finales; NO uses comillas dobles "
        "dentro de las frases (si necesitas citar un campo, escríbelo sin comillas).\n"
        + reglas_tesis(situacion)
        + "REGLAS DE REDACCIÓN (obligatorias):\n"
        "1. Español claro, sin jerga. PROHIBIDO la palabra 'gap'. Un número positivo es "
        "un 'excedente' o 'produjo por encima de su meta'; un negativo es un 'faltante' "
        "o 'rezago'.\n"
        "5. decisiones: conecta causa->acción y PRIORIZA (primero lo estructural/crítico, "
        "luego lo transitorio); acciones concretas, no genéricas ('implementar planes' a "
        "secas no sirve).\n"
        "6. Longitud: insights 3-4 frases; oportunidades, puntos_atencion y decisiones "
        "1-3 c/u. Frases BREVES y directas (~25 palabras máx); nada de párrafos largos.\n"
        "7. Un producto SIN meta definida no es un faltante ni un problema: no hay con "
        "qué compararlo. Menciónalo como tal o no lo menciones; NUNCA lo presentes como "
        "un rezago.\n"
        "Datos: " + json.dumps(contexto, ensure_ascii=False)
    )


def prompt_lectura_ejecutiva(contexto: dict[str, Any]) -> str:
    """Prompt de `desempeno_insight`: 3-5 frases de lectura ejecutiva.

    Las etiquetas de estado del chip y el label del valle son CLASIFICACIONES
    derivadas del número → las fija Python, no el modelo.
    """
    return (
        "Eres analista de producción. Con estos datos EXACTOS (no inventes ni calcules "
        "números, no agregues cifras nuevas), responde SOLO un JSON de una línea: "
        '{"lectura_ejecutiva":"..."}. '
        "lectura_ejecutiva: 3-5 frases ejecutivas que cubran: (1) el desempeño del mes "
        "por producto; (2) si hay valle, su causa; (3) qué campos explican el rezago del "
        "producto más bajo (gap_detractores, en volumen) y quién compensa "
        "(gap_compensadores); (4) el pace de cierre de crudo: con pace_crudo, indica si "
        "el ritmo requerido en los días restantes (requerido_dia, delta_pct) es "
        "alcanzable frente al promedio actual (promedio_dia). "
        "Datos: " + json.dumps(contexto, ensure_ascii=False)
    )
