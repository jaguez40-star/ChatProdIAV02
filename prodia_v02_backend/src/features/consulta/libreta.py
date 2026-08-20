"""Libreta de clasificación — cada pregunta real, con su veredicto.

Portada de `consulta_v2/log.py` (113 líneas), con **un cambio de fondo: vive en
`db_auth`, no en `db_prod`** (DA-2/AP-4).

El origen la pone en `core.clasificacion_log` de PostgreSQL porque no usa
Alembic: aplica ficheros `.sql` a mano, y su propio runner admite hacerlo "sin
llevar registro de cuáles ya se aplicaron". Aquí Alembic versiona **solo**
`db_auth`, así que ponerla en Postgres exigiría renunciar al versionado. Y hay
un argumento de fondo mejor: esto es telemetría de uso, no dato de producción
— encaja junto a `auth_events`.

**Principio del origen, conservado**: solo los casos VERIFICADOS alimentan el
crecimiento de patrones y del golden. Anotar sin veredicto es ruido, no
aprendizaje.

**Tres jueces** ponen ese veredicto:

1. El usuario, con ✓/✗ en la burbuja → `confirmado_usuario` / `corregido_usuario`
2. Señales indirectas → `sospecha` (bandera de prioridad, **no** veredicto)
3. La revisión por lotes → `confirmado_revision` / `corregido_revision`

`llm_diag` es lo que permite distinguir un error del clasificador de un timeout
por arranque en frío del modelo (~342 s medidos). Sin él, al revisar la libreta
semanas después, ambos parecen lo mismo.
"""

from __future__ import annotations

import json
from typing import Any, cast

from sqlalchemy import CursorResult, text
from sqlalchemy.orm import Session

GRUPOS = frozenset({"jerarquizar", "cuantificar", "analizar", "desconocido"})

VEREDICTOS_VALIDOS = frozenset(
    {
        "confirmado_usuario",
        "corregido_usuario",
        "confirmado_revision",
        "corregido_revision",
    }
)


def registrar(
    db: Session,
    *,
    texto: str,
    grupo: str,
    capa: str,
    patrones: list[str] | None = None,
    entidad: str | None = None,
    usuario: str | None = None,
    conversacion_id: str | None = None,
    llm_diag: str | None = None,
) -> int | None:
    """Anota una clasificación y devuelve su id.

    El veredicto arranca en `pendiente`: nadie lo ha juzgado todavía.
    """
    fila = db.execute(
        text("""
            INSERT INTO clasificacion_log
                (usuario, conversacion_id, texto_pregunta, grupo_asignado,
                 capa_resolutora, patrones_atrapados, entidad_cruda, llm_diag)
            VALUES (:usuario, :conv, :texto, :grupo, :capa, :patrones, :entidad, :diag)
            RETURNING id
            """),
        {
            "usuario": usuario,
            "conv": conversacion_id,
            "texto": texto,
            "grupo": grupo,
            "capa": capa,
            "patrones": json.dumps(patrones) if patrones else None,
            "entidad": entidad,
            "diag": llm_diag,
        },
    ).scalar()
    db.commit()
    return int(fila) if fila is not None else None


def poner_veredicto(
    db: Session,
    log_id: int,
    veredicto: str,
    *,
    grupo_correcto: str | None = None,
    fuente: str = "usuario",
    nota: str | None = None,
) -> bool:
    """Veredicto de un juez humano. `False` si los datos no son válidos.

    Una corrección DEBE decir cuál era el grupo correcto —si no, no enseña
    nada—, y una confirmación fuerza `grupo_correcto` a `None`: el grupo
    correcto ya es el asignado, y duplicarlo invitaría a que diverjan.
    """
    if veredicto not in VEREDICTOS_VALIDOS:
        return False
    if veredicto.startswith("corregido") and grupo_correcto not in GRUPOS:
        return False
    if veredicto.startswith("confirmado"):
        grupo_correcto = None

    resultado = db.execute(
        text("""
            UPDATE clasificacion_log
               SET veredicto = :veredicto,
                   grupo_correcto = :grupo,
                   fuente_veredicto = :fuente,
                   ts_veredicto = CURRENT_TIMESTAMP,
                   nota_revision = COALESCE(:nota, nota_revision)
             WHERE id = :id
            """),
        {
            "veredicto": veredicto,
            "grupo": grupo_correcto,
            "fuente": fuente,
            "nota": nota,
            "id": log_id,
        },
    )
    db.commit()
    # `rowcount` solo lo declara CursorResult; el Result generico de execute() no.
    return bool(cast(CursorResult[Any], resultado).rowcount)


def marcar_sospecha(db: Session, log_id: int, nota: str | None = None) -> bool:
    """Señal indirecta: bandera de prioridad, NO veredicto.

    🔑 `WHERE veredicto = 'pendiente'` — una señal automática **jamás** pisa el
    juicio de una persona.
    """
    resultado = db.execute(
        text("""
            UPDATE clasificacion_log
               SET veredicto = 'sospecha',
                   fuente_veredicto = 'indirecta',
                   nota_revision = COALESCE(:nota, nota_revision)
             WHERE id = :id AND veredicto = 'pendiente'
            """),
        {"nota": nota, "id": log_id},
    )
    db.commit()
    return bool(cast(CursorResult[Any], resultado).rowcount)


_FILTROS = {
    "pendientes": "veredicto = 'pendiente'",
    "sospecha": "veredicto = 'sospecha'",
    "corregidas": "veredicto LIKE 'corregido%'",
    "todas": "1=1",
}


def listar(db: Session, limite: int = 100, filtro: str = "todas") -> dict[str, Any]:
    """Filas de la libreta, las sospechosas primero.

    El orden no es cosmético: las sospechas son justamente las que más valor
    tienen para revisar.
    """
    limite = max(1, min(500, limite))
    condicion = _FILTROS.get(filtro, "1=1")

    filas = db.execute(
        text(f"""
            SELECT id, ts, usuario, conversacion_id, texto_pregunta,
                   grupo_asignado, capa_resolutora, entidad_cruda, llm_diag,
                   veredicto, grupo_correcto, fuente_veredicto, nota_revision
              FROM clasificacion_log
             WHERE {condicion}
             ORDER BY (veredicto = 'sospecha') DESC, ts DESC
             LIMIT :limite
            """),  # noqa: S608 — `condicion` sale de `_FILTROS`, nunca del usuario
        {"limite": limite},
    ).mappings()

    return {"filas": [dict(f) for f in filas]}
