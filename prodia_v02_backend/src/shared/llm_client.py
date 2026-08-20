"""Cliente de Ollama para el pulido de prosa del Análisis Ejecutivo.

Portado de `INGESTA/Rep_Prod/backend/app/features/analisis/api.py:966-1160`
(`_extraer_json`, `_llm_insight`, `_llm_insight_once`). Vive en `shared/` y no
en la feature porque F4 (Consulta) lo reutilizará, y ADR-001 prohíbe que una
feature importe de otra.

**Python calcula, el LLM redacta** (Q1). Este módulo NO decide nada: entrega el
texto que el modelo devolvió, ya parseado, o `None`. Ninguna cifra, fecha,
etiqueta de estado ni label de gráfico puede salir de aquí — el llamador
compone los números y el LLM solo los envuelve en prosa.

**Cero I/O en tiempo de import** (AP-2): no se abre ni se resuelve nada al
importar el módulo. `scripts/export_openapi.py` importa `src.main` entero, y
con él este archivo; si aquí se contactara a Ollama, cada `git commit` (el hook
`gen-types-check`) y cada corrida de CI intentarían alcanzar el servidor.

Las cuatro trampas del original se conservan con su explicación — cada una es
un fallo real que costó horas de diagnóstico:

- **T1** `format="json"`: obliga a Ollama a emitir JSON sintácticamente válido.
  Elimina de raíz los fences ```` ```json ````, la prosa antes/después y las
  comas finales.
- **T2** `num_ctx` EXPLÍCITO: el default de Ollama puede ser 2048. Con un
  prompt de ~1.200-1.700 tokens, el objeto de 4 secciones no cabe y la
  generación se corta a media llave. El síntoma es un `json_invalido` que manda
  a depurar el prompt cuando el problema era la ventana de contexto.
- **T3** `done=false` significa **generación abortada** (runner caído, presión
  de memoria). El `response` que la acompaña es un FRAGMENTO, no la respuesta.
  Parsearlo producía "json_invalido · objeto sin cierre", culpando al JSON de
  algo que no era del JSON.
- **T4** Reintento SOLO ante aborto. Un `json_invalido` con `temperature=0`
  daría exactamente lo mismo al repetir: solo añade latencia.
"""

from __future__ import annotations

import json
import re
import urllib.request
from typing import Any

from src.core.config import get_settings
from src.core.logger import get_logger

logger = get_logger("shared.llm_client")

# Comillas tipográficas → rectas. Gemma las emite al redactar en español y
# rompen `json.loads` aunque el resto del objeto sea correcto.
_COMILLAS_TIPOGRAFICAS = {0x201C: 0x22, 0x201D: 0x22, 0x2018: 0x27, 0x2019: 0x27}


def extraer_json(texto: str | None, diag: dict[str, Any] | None = None) -> Any | None:
    """Extrae y parsea el primer objeto JSON de la salida del LLM.

    Tolerante a los defectos típicos de Gemma: fences, prosa antes/después,
    comas finales (`,]` / `,}`) y comillas tipográficas. Devuelve `None` si no
    hay JSON recuperable, y deja el motivo exacto en `diag["parse_err"]`.
    """
    if not texto:
        return None

    limpio = texto.strip()
    limpio = re.sub(r"^```(?:json)?\s*", "", limpio)
    limpio = re.sub(r"\s*```$", "", limpio)
    limpio = limpio.translate(_COMILLAS_TIPOGRAFICAS)

    inicio = limpio.find("{")
    if inicio < 0:
        return None

    # Localizar el `}` que balancea el primer `{`, respetando cadenas y
    # escapes: un `}` dentro de un texto no cierra el objeto.
    profundidad = 0
    fin = -1
    en_cadena = False
    escapado = False
    for i in range(inicio, len(limpio)):
        caracter = limpio[i]
        if en_cadena:
            if escapado:
                escapado = False
            elif caracter == "\\":
                escapado = True
            elif caracter == '"':
                en_cadena = False
        elif caracter == '"':
            en_cadena = True
        elif caracter == "{":
            profundidad += 1
        elif caracter == "}":
            profundidad -= 1
            if profundidad == 0:
                fin = i + 1
                break

    if fin < 0:
        if diag is not None:
            diag["parse_err"] = "objeto sin cierre (llaves no balanceadas)"
        return None

    candidato = limpio[inicio:fin]
    sin_comas_finales = re.sub(r",(\s*[}\]])", r"\1", candidato)

    error: Exception | None = None
    for intento in (candidato, sin_comas_finales):
        try:
            return json.loads(intento)
        except (ValueError, TypeError) as exc:
            error = exc

    if diag is not None and error is not None:
        diag["parse_err"] = str(error)
    return None


def _invocar_una_vez(
    prompt: str, timeout: int, diag: dict[str, Any] | None
) -> Any | None:
    """Una sola llamada a Ollama. Ver `invocar` para la política de reintento."""
    settings = get_settings()

    if diag is not None:
        # Modelo y host efectivos: permiten confirmar que la petición fue al
        # servidor esperado aunque después falle el parseo.
        diag["model"] = settings.consulta_llm_model
        diag["host"] = settings.consulta_ollama_url

    cuerpo = json.dumps(
        {
            "model": settings.consulta_llm_model,
            "prompt": prompt,
            "stream": False,
            "format": "json",  # T1
            "keep_alive": settings.keep_alive_ollama,
            "options": {
                "temperature": 0,
                "num_predict": 2048,
                "num_ctx": 8192,  # T2
            },
        }
    ).encode()

    try:
        peticion = urllib.request.Request(  # noqa: S310 — URL de configuración
            settings.consulta_ollama_url,
            data=cuerpo,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(
            peticion, timeout=timeout
        ) as respuesta:  # noqa: S310
            datos = json.load(respuesta)
    except Exception as exc:
        # Red caída, timeout, DNS, 500 del servidor... todo se trata igual: el
        # llamador sirve su fallback determinista. El detalle va al diag.
        if diag is not None:
            diag["status"] = "timeout_o_red:" + type(exc).__name__
        logger.warning("llm_no_disponible", exc_type=type(exc).__name__)
        return None

    salida = datos.get("response", "")
    if diag is not None:
        diag["raw"] = (salida or "")[:2000]
        diag["raw_len"] = len(salida or "")
        # POR QUÉ paró el modelo. Sin esto, un fragmento cortado y un JSON mal
        # escrito son indistinguibles: ambos caen en "json_invalido".
        diag["done_reason"] = datos.get("done_reason")
        diag["out_tok"] = datos.get("eval_count")
        diag["prompt_tok"] = datos.get("prompt_eval_count")

    # T3 — generación abortada: el `response` es un fragmento, no se parsea.
    if datos.get("done") is False:
        if diag is not None:
            diag["status"] = "generacion_abortada"
        logger.warning("llm_generacion_abortada", modelo=settings.consulta_llm_model)
        return None

    parseado = extraer_json(salida, diag=diag)
    if parseado is None:
        if diag is not None:
            diag["status"] = "json_invalido"
        return None

    if diag is not None:
        diag["status"] = "ok"
    return parseado


def invocar(
    prompt: str,
    timeout: int = 60,
    diag: dict[str, Any] | None = None,
    intentos: int = 2,
) -> Any | None:
    """Llama al LLM y devuelve el objeto parseado, o `None` si no fue posible.

    `None` NUNCA es un error para el llamador: significa "sirve tu fallback
    determinista". El composer de Python es el entregable por defecto y el
    pulido del LLM es opcional (H4 del origen).

    T4 — se reintenta SOLO si Ollama abortó la generación (`done=false`). Ese
    fallo es transitorio y no determinista: el mismo prompt completa unas veces
    y aborta otras (verificado en dev), así que reintentar es el arreglo, no un
    parche. Un `json_invalido` no se reintenta: el modelo sí respondió entero y
    con `temperature=0` repetir daría idéntico resultado.
    """
    for intento in range(1, intentos + 1):
        resultado = _invocar_una_vez(prompt, timeout=timeout, diag=diag)
        if resultado is not None:
            return resultado
        if (diag or {}).get("status") != "generacion_abortada":
            return None
        if diag is not None:
            diag["intentos"] = intento
    return None
