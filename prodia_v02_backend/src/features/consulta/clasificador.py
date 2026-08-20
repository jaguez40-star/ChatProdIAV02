"""Capa 2 del clasificador — el LLM, cerrado y con diagnóstico.

Portado de `consulta_v2/clasificador_llm.py` (103 líneas), pero **reusando
`shared/llm_client`** de F2 en vez de repetir la plomería de `urllib`: el
origen duplica esa fontanería en cuatro módulos con parámetros ligeramente
distintos, y `llm_client` ya resuelve las cuatro trampas de Ollama (JSON
forzado, `num_ctx` explícito, `done=false` como aborto, reintento solo ante
aborto).

**El LLM decide el grupo en solo dos situaciones**: cuando la regex no atrapó
nada, y cuando atrapó pero el dominio es apenas "estructural" y hace falta
confirmar. Nunca calcula.

🔑 **La entidad que devuelve el LLM se IGNORA a propósito** (D6 del origen). El
modelo alucina nombres de campo con facilidad; la entidad la resuelve el
catálogo, que es cerrado y verificable. Se conserva en el diagnóstico para
poder auditar qué dijo, pero no se usa para consultar.

`clasificar_capa2` devuelve `None` cuando no hay veredicto utilizable, y deja
el motivo en `diag["llm_diag"]`: `timeout`, `conexion`, `json_invalido` o
`grupo_invalido`. Sin ese campo, un timeout por arranque en frío del modelo
—~342 s medidos en el 139— parecería un error del clasificador al revisar la
libreta después.
"""

from __future__ import annotations

from typing import Any

from src.features.consulta.prompts import GRUPOS_VALIDOS, PROMPT_CLASIFICADOR
from src.shared import llm_client

# El origen usa 30 s aquí. Es una decisión deliberada frente al arranque en
# frío: si el modelo no está caliente, es preferible caer al camino
# determinista que dejar al usuario esperando minutos.
TIMEOUT_S = 30


def parsear(bruto: Any, diag: dict[str, Any] | None = None) -> str | None:
    """Valida la respuesta del modelo y devuelve el grupo, o `None`.

    Defensivo a propósito: cualquier forma inesperada se convierte en `None`
    con su motivo, nunca en una excepción que tumbe la petición.
    """
    if not isinstance(bruto, dict):
        if diag is not None:
            diag["llm_diag"] = "json_invalido"
        return None

    grupo = bruto.get("grupo")
    if not isinstance(grupo, str) or grupo not in GRUPOS_VALIDOS:
        if diag is not None:
            diag["llm_diag"] = "grupo_invalido"
        return None

    # D6: la entidad se guarda para auditoría pero NO se usa para consultar.
    entidad = bruto.get("entidad")
    if diag is not None and isinstance(entidad, str):
        diag["entidad_llm"] = entidad

    return grupo


def clasificar_capa2(texto: str, diag: dict[str, Any] | None = None) -> str | None:
    """Pide al LLM que clasifique la pregunta. `None` si no hubo veredicto."""
    prompt = PROMPT_CLASIFICADOR.format(texto=texto)

    interno: dict[str, Any] = {}
    bruto = llm_client.invocar(prompt, timeout=TIMEOUT_S, diag=interno)

    if diag is not None:
        # Se propaga el diagnóstico del cliente (modelo, host, motivo del
        # fallo) para poder auditar la libreta más tarde.
        diag.update(interno)

    if bruto is None:
        if diag is not None and "llm_diag" not in diag:
            # `llm_client` ya distingue timeout de fallo de conexión; si no
            # dejó motivo, se registra el genérico.
            diag["llm_diag"] = interno.get("error") or "conexion"
        return None

    return parsear(bruto, diag)
