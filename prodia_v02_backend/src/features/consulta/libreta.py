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
from typing import Any, Literal, TypedDict, cast

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


FiltroLibreta = Literal["todas", "pendientes", "sospecha", "corregidas"]

_FILTROS: dict[FiltroLibreta, str] = {
    # «Pendientes» = TODO lo que falta por juzgar, sospechas incluidas.
    #
    # F4 escribió aquí `veredicto = 'pendiente'`, que excluye las sospechas — y
    # eso contradice al `ORDER BY` de esta misma función, que las pone primero
    # "porque no es cosmético: son las que más valor tienen para revisar". Con
    # el filtro estrecho, la vista «Pendientes» escondía justo esas filas.
    #
    # La sospecha NO es un veredicto (es una bandera de prioridad), así que una
    # fila sospechosa sigue sin juzgar y pertenece a esta lista.
    "pendientes": "veredicto IN ('pendiente', 'sospecha')",
    "sospecha": "veredicto = 'sospecha'",
    "corregidas": "veredicto LIKE 'corregido%'",
    "todas": "1=1",
}


class ResumenLibreta(TypedDict):
    """Los KPIs del ciclo de crecimiento del clasificador."""

    total: int
    por_veredicto: dict[str, int]
    pct_capa1: float | None


class VistaLibreta(TypedDict):
    filas: list[dict[str, Any]]
    resumen: ResumenLibreta


def resumir(db: Session) -> ResumenLibreta:
    """Conteos por veredicto y **% resuelto por la Capa 1** (regex).

    `pct_capa1` es el KPI que justifica que esta libreta exista: si la regex
    resuelve menos de la mitad, el motor depende demasiado del LLM y lo que
    toca es engordar patrones (regla A4). Se calcula sobre el total histórico,
    no sobre la página que se esté mirando — si dependiera del filtro activo,
    cambiaría al pulsar un chip y dejaría de ser una medida.
    """
    filas = db.execute(text("""
            SELECT veredicto,
                   COUNT(*) AS n,
                   -- `COUNT(*) FILTER (WHERE …)` es sintaxis de PostgreSQL y de
                   -- SQLite >= 3.30; el SUM(CASE) funciona en cualquiera de los
                   -- dos y no obliga a fijar una versión mínima del motor.
                   SUM(CASE WHEN capa_resolutora = 'regex' THEN 1 ELSE 0 END) AS n_regex
              FROM clasificacion_log
             GROUP BY veredicto
            """)).mappings()

    por_veredicto: dict[str, int] = {}
    total = 0
    regex = 0
    for fila in filas:
        por_veredicto[str(fila["veredicto"])] = int(fila["n"])
        total += int(fila["n"])
        regex += int(fila["n_regex"] or 0)

    return {
        "total": total,
        "por_veredicto": por_veredicto,
        "pct_capa1": round(100 * regex / total, 1) if total else None,
    }


def listar(
    db: Session, limite: int = 100, filtro: FiltroLibreta = "todas"
) -> VistaLibreta:
    """Filas de la libreta, las sospechosas primero, con el resumen del ciclo.

    El orden no es cosmético: las sospechas son justamente las que más valor
    tienen para revisar.

    `filtro` es un `Literal`, no un `str` libre. F4 usaba `_FILTROS.get(filtro,
    "1=1")`, que ante una errata —`"sospechas"` en plural— devolvía la libreta
    ENTERA sin avisar, y el revisor creía estar viendo solo las sospechas. Sobre
    el dato que decide qué entra al golden, esa degradación silenciosa es peor
    que un error: el `KeyError` de aquí solo puede dispararlo un bug nuestro,
    porque en el borde HTTP FastAPI ya rechaza cualquier otro valor con un 422.
    """
    limite = max(1, min(500, limite))
    condicion = _FILTROS[filtro]

    filas = db.execute(
        text(f"""
            SELECT id, ts, usuario, conversacion_id, texto_pregunta,
                   grupo_asignado, capa_resolutora, entidad_cruda, llm_diag,
                   veredicto, grupo_correcto, fuente_veredicto, nota_revision
              FROM clasificacion_log
             WHERE {condicion}
             ORDER BY (veredicto = 'sospecha') DESC, ts DESC
             LIMIT :limite
            """),  # noqa: S608 — `condicion` sale de `_FILTROS`, con clave tipada
        {"limite": limite},
    ).mappings()

    return {"filas": [dict(f) for f in filas], "resumen": resumir(db)}


def poner_veredictos_en_lote(
    db: Session,
    items: list[tuple[int, str, str | None]],
    *,
    fuente: str = "revision",
    nota: str | None = None,
) -> tuple[int, int]:
    """Control 3 por lotes. Devuelve `(aplicados, total)`.

    Una fila inválida o inexistente **no tumba el resto**: se cuenta como no
    aplicada y el llamador decide qué decir. Devolver solo `ok=True` escondería
    que 30 de 100 veredictos no se guardaron.
    """
    aplicados = 0
    for log_id, veredicto, grupo_correcto in items:
        if poner_veredicto(
            db,
            log_id,
            veredicto,
            grupo_correcto=grupo_correcto,
            fuente=fuente,
            nota=nota,
        ):
            aplicados += 1
    return aplicados, len(items)
