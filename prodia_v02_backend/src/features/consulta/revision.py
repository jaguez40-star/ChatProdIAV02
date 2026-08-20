"""Lógica del Control 3 que sí se puede probar.

El CLI (`scripts/revisar_lote.py`) es interactivo y vive fuera de `src` para no
arrastrar el umbral de cobertura (AP-2). Lo que aquí queda es lo que decide su
comportamiento —el orden de la cola y el mapeo de teclas—, y eso sí tiene tests.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# Las mismas teclas que el origen, porque el revisor ya las tiene en los dedos.
GRUPOS_POR_TECLA: dict[str, str] = {
    "1": "jerarquizar",
    "2": "cuantificar",
    "3": "analizar",
    "4": "desconocido",
}


def cola_de_revision(db: Session, limite: int = 30) -> list[dict[str, Any]]:
    """Los casos sin juzgar, en el orden en que conviene mirarlos.

    El orden **es** la funcionalidad, y tiene dos escalones:

    1. **Las sospechas primero.** Son las que una señal indirecta marcó como
       probablemente mal clasificadas: el revisor rinde más empezando por ahí.
    2. **Luego lo que resolvió el LLM.** Si la Capa 1 (regex) atrapó la pregunta,
       la decisión es determinista y auditable; cuando decidió el modelo, es
       donde de verdad puede haber deriva.

    Dentro de cada escalón, las más antiguas primero: una cola que se revisa por
    lo más reciente deja un fondo que nadie mira nunca.
    """
    limite = max(1, min(500, limite))
    filas = db.execute(
        text("""
            SELECT id, ts, usuario, texto_pregunta, grupo_asignado,
                   capa_resolutora, veredicto, llm_diag
              FROM clasificacion_log
             WHERE veredicto IN ('pendiente', 'sospecha')
             ORDER BY (veredicto = 'sospecha') DESC,
                      (capa_resolutora IN ('llm', 'regex+llm')) DESC,
                      ts
             LIMIT :limite
            """),
        {"limite": limite},
    ).mappings()
    return [dict(f) for f in filas]
