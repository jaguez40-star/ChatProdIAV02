"""0004_consulta_libreta_conversaciones

Dos tablas para F4 (Consulta / Motor Q v2), ambas en `db_auth`.

**Por qué en `db_auth` y no en `db_prod`** (DA-2/AP-4). El sistema de origen
pone la libreta en `core.clasificacion_log` de PostgreSQL, y su DDL lo justifica
diciendo que los controles necesitan filtros y ventanas de tiempo. Pero allí no
hay Alembic: aplican ficheros `.sql` a mano, y su propio runner admite hacerlo
"sin llevar registro de cuáles ya se aplicaron". Aquí Alembic versiona **solo**
`db_auth`, así que llevar la libreta a Postgres significaría renunciar al
versionado que F0 estableció.

Y hay un argumento de fondo mejor: ambas tablas son **telemetría de uso y
estado de usuario**, no dato de producción. Encajan junto a `auth_events`, y
`db_prod` se mantiene como fuente de solo lectura para el chat.

---

**`clasificacion_log`** — la libreta del clasificador.

Principio del origen: *"anotación sin veredicto es ruido, no aprendizaje"*.
Cada pregunta real queda registrada con su clasificación y un veredicto que
ponen tres jueces (usuario, señal indirecta, revisión por lotes). Solo los
casos VERIFICADOS alimentan el crecimiento de patrones y del golden.

`llm_diag` es lo que distingue un error del clasificador de un timeout por
arranque en frío del modelo (~342 s medidos en el 139). Sin él, al revisar la
libreta semanas después ambos parecen lo mismo.

---

**`conversaciones` y `mensajes`** — la memoria que sobrevive al reinicio.

El origen guarda el contexto en un `dict` de proceso sin TTL: reiniciar el
backend borra toda conversación, y con varios workers cada uno tendría su
propia memoria. El panel "Historial" del cascarón F1a exige lo contrario.

`contenido` y `panel` van como JSON en texto: SQLite no tiene tipo JSON nativo,
y el contrato del panel es una unión discriminada que evoluciona con la
feature — normalizarla en columnas obligaría a migrar en cada tipo nuevo.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_consulta_libreta_conversaciones"
down_revision: Union[str, None] = "0003_seed_padron"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clasificacion_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "ts",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("usuario", sa.String(length=120), nullable=True),
        sa.Column("conversacion_id", sa.String(length=64), nullable=True),
        sa.Column("texto_pregunta", sa.Text(), nullable=False),
        # jerarquizar | cuantificar | analizar | desconocido
        sa.Column("grupo_asignado", sa.String(length=20), nullable=False),
        # regex | regex+filtro | regex+llm | regex+llm_fallo | llm
        sa.Column("capa_resolutora", sa.String(length=20), nullable=False),
        # Solo si la capa fue regex: qué patrones atraparon la pregunta.
        sa.Column("patrones_atrapados", sa.Text(), nullable=True),
        sa.Column("entidad_cruda", sa.String(length=200), nullable=True),
        # timeout | conexion | json_invalido | grupo_invalido | NULL
        sa.Column("llm_diag", sa.String(length=40), nullable=True),
        sa.Column(
            "veredicto",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'pendiente'"),
        ),
        # Null salvo en correcciones: una confirmación no lo duplica.
        sa.Column("grupo_correcto", sa.String(length=20), nullable=True),
        sa.Column("fuente_veredicto", sa.String(length=20), nullable=True),
        sa.Column("ts_veredicto", sa.DateTime(), nullable=True),
        sa.Column("nota_revision", sa.Text(), nullable=True),
    )
    # La revisión filtra por veredicto y ordena por fecha: ese es el acceso
    # real, y el índice lo sigue.
    op.create_index(
        "ix_clasificacion_log_veredicto_ts",
        "clasificacion_log",
        ["veredicto", "ts"],
    )

    op.create_table(
        "conversaciones",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "usuario_id",
            sa.Integer(),
            sa.ForeignKey("app_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("titulo", sa.String(length=300), nullable=True),
        # Contexto conversacional serializado: la unión discriminada de
        # `memoria.py`. Se guarda como JSON porque su forma depende del grupo.
        sa.Column("contexto", sa.Text(), nullable=True),
        sa.Column(
            "creada_en",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "actualizada_en",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    # El panel Historial lista las conversaciones de UN usuario, más recientes
    # primero.
    op.create_index(
        "ix_conversaciones_usuario_actualizada",
        "conversaciones",
        ["usuario_id", "actualizada_en"],
    )

    op.create_table(
        "mensajes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "conversacion_id",
            sa.String(length=64),
            sa.ForeignKey("conversaciones.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # usuario | asistente
        sa.Column("rol", sa.String(length=20), nullable=False),
        sa.Column("contenido", sa.Text(), nullable=False),
        # El panel del resultado, si lo hubo. JSON: es una unión discriminada
        # de 9 tipos que evoluciona con la feature.
        sa.Column("panel", sa.Text(), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_mensajes_conversacion_creado",
        "mensajes",
        ["conversacion_id", "creado_en"],
    )


def downgrade() -> None:
    op.drop_index("ix_mensajes_conversacion_creado", table_name="mensajes")
    op.drop_table("mensajes")
    op.drop_index(
        "ix_conversaciones_usuario_actualizada", table_name="conversaciones"
    )
    op.drop_table("conversaciones")
    op.drop_index(
        "ix_clasificacion_log_veredicto_ts", table_name="clasificacion_log"
    )
    op.drop_table("clasificacion_log")
