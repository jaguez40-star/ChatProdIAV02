"""0003_seed_padron

Siembra el padrón de usuarios de ProdIA V02 (D2/C14) — corrección real sobre
Robustez V02, que NO tiene ningún mecanismo para crear su primer usuario
(sus migraciones 0001/0002 son solo DDL). Sin esta migración, `app_users`
queda vacía y TODO login falla con 401 "Usuario no registrado en la
aplicación", incluso con LDAP válido.

Qué hace (medido contra la BD real de Robustez V02, 2026-08-17 — ver
docs/decisions/ADR-002-padron-usuarios-propio.md):
  - Crea 2 grupos: `Administradores` (is_admin=1) y `Consulta` (is_admin=0).
  - Importa de `robustez_v02_auth.db` SOLO 3 columnas: username, email,
    full_name. NO copia grupos, permisos de campo/sección ni bitácora de
    esa aplicación — son de un dominio de secciones distinto (Robustez:
    'ebitda_rank', 'analytics'... vs ProdIA: 'ingesta', 'consulta'...).
  - full_name se copia TAL CUAL, incluidos los 27 de 29 registros vacíos
    (verificado) — no se inventan nombres.
  - Los usuarios listados en SEED_ADMIN_USERNAMES entran al grupo
    Administradores; el resto, a Consulta.

Salvaguardas (evitan las dos formas de fallar en silencio):
  - La BD origen se abre con `mode=ro` (URI de SQLite) — escribir en ella
    lanza OperationalError; nunca se modifica robustez_v02_auth.db.
  - Si SEED_SOURCE_AUTH_DB no existe o SEED_ADMIN_USERNAMES está vacío,
    la migración ABORTA con un mensaje de instrucciones — nunca deja un
    padrón sin ningún administrador (eso dejaría la app inaccesible para
    todos, el mismo problema que tiene Robustez V02 hoy).
  - Idempotente vía `INSERT ... ON CONFLICT DO NOTHING`: re-ejecutar
    `alembic upgrade head` no duplica filas.

Revision ID: 0003_seed_padron
Revises: 0002_app_settings
Create Date: 2026-08-18

"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0003_seed_padron"
down_revision: Union[str, None] = "0002_app_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ADMIN_GROUP = "Administradores"
_DEFAULT_GROUP = "Consulta"


def _read_source_users(source_path: str) -> list[tuple[str, str, str | None]]:
    """Lee (username, email, full_name) de la BD de Robustez V02, EN SOLO
    LECTURA. `mode=ro` hace que cualquier intento de escritura falle con
    OperationalError — no hay forma de que esta función modifique el origen."""
    uri = f"file:{Path(source_path).as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        rows = conn.execute(
            "SELECT username, email, full_name FROM app_users ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return [(r[0], r[1], r[2]) for r in rows]


def upgrade() -> None:
    from src.core.config import get_settings

    settings = get_settings()

    # ── Salvaguarda 1: BD origen debe existir ──────────────────────────────
    source_path = settings.seed_source_auth_db
    if not source_path or not Path(source_path).exists():
        raise RuntimeError(
            "0003_seed_padron: SEED_SOURCE_AUTH_DB no está configurada o el "
            f"archivo no existe (valor actual: {source_path!r}). "
            "Define en .env la ruta a robustez_v02_auth.db, por ejemplo:\n"
            "  SEED_SOURCE_AUTH_DB=C:/APLICACIONES/Robustez/Des_robustez_2.0/"
            "robustez_v02_backend/data/robustez_v02_auth.db"
        )

    # ── Salvaguarda 2: al menos un admin ────────────────────────────────────
    admin_usernames = set(settings.seed_admin_usernames_list)
    if not admin_usernames:
        raise RuntimeError(
            "0003_seed_padron: SEED_ADMIN_USERNAMES está vacía. Sin al menos "
            "un administrador, nadie podría gestionar la aplicación tras el "
            "seed. Define en .env, por ejemplo:\n"
            "  SEED_ADMIN_USERNAMES=jguerrero,otro.usuario"
        )

    source_users = _read_source_users(source_path)

    bind = op.get_bind()

    # ── Grupos ──────────────────────────────────────────────────────────
    bind.execute(
        sa.text(
            "INSERT INTO permission_groups (name, description, is_admin) "
            "VALUES (:name, :desc, :is_admin) "
            "ON CONFLICT(name) DO NOTHING"
        ),
        {"name": _ADMIN_GROUP, "desc": "Acceso total a ProdIA V02", "is_admin": 1},
    )
    bind.execute(
        sa.text(
            "INSERT INTO permission_groups (name, description, is_admin) "
            "VALUES (:name, :desc, :is_admin) "
            "ON CONFLICT(name) DO NOTHING"
        ),
        {
            "name": _DEFAULT_GROUP,
            "desc": "Usuarios del padrón importado, sin privilegios de admin",
            "is_admin": 0,
        },
    )

    admin_group_id = bind.execute(
        sa.text("SELECT id FROM permission_groups WHERE name = :name"),
        {"name": _ADMIN_GROUP},
    ).scalar_one()
    default_group_id = bind.execute(
        sa.text("SELECT id FROM permission_groups WHERE name = :name"),
        {"name": _DEFAULT_GROUP},
    ).scalar_one()

    # ── Usuarios (solo username/email/full_name — nada más de Robustez) ────
    # Comparación case-insensitive: admin_usernames viene normalizado a
    # lowercase (Settings.seed_admin_usernames_list); los username de origen
    # están en minúscula HOY (verificado contra la BD real) pero no es un
    # invariante garantizado del origen — no asumirlo.
    unknown_admins = set(admin_usernames)
    for username, email, full_name in source_users:
        username_lower = username.lower()
        is_admin_user = username_lower in admin_usernames
        group_id = admin_group_id if is_admin_user else default_group_id
        unknown_admins.discard(username_lower)
        bind.execute(
            sa.text(
                "INSERT INTO app_users "
                "(username, email, full_name, is_admin, is_active, group_id) "
                "VALUES (:username, :email, :full_name, :is_admin, 1, :group_id) "
                "ON CONFLICT(username) DO NOTHING"
            ),
            {
                "username": username,
                "email": email,
                "full_name": full_name,  # tal cual — 27/29 vienen vacíos, no se inventan
                # is_admin individual ADEMÁS del grupo: `require_admin` acepta
                # `is_admin OR group.is_admin`, así que el grupo bastaría — pero
                # dejar el flag en 0 haría que mover al usuario de grupo le
                # quitara admin en silencio. V6 exige is_admin=1 explícito.
                "is_admin": 1 if is_admin_user else 0,
                "group_id": group_id,
            },
        )

    if unknown_admins:
        raise RuntimeError(
            "0003_seed_padron: SEED_ADMIN_USERNAMES contiene usuarios que NO "
            f"existen en la BD origen: {sorted(unknown_admins)}. Verifica el "
            "username exacto (case-insensitive) contra robustez_v02_auth.db."
        )


def downgrade() -> None:
    # Esta migración es la ÚNICA que escribe app_users/permission_groups en
    # esta cadena (0001/0002 son solo DDL) — vaciar ambas tablas es seguro.
    op.execute(sa.text("DELETE FROM app_users"))
    op.execute(sa.text("DELETE FROM permission_groups"))
