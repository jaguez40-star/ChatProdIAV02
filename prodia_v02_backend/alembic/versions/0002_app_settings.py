"""0002_app_settings

Crea la tabla app_settings (key/value/updated_at/updated_by) — configuración
editable en caliente sin reiniciar el backend. Arranca vacía a propósito
(ver shared/app_settings.py): mientras no tenga filas, get_session_timeout_minutes
usa el valor de .env.

Revision ID: 0002_app_settings
Revises: 0001_initial_auth
Create Date: 2026-08-18

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_app_settings"
down_revision: Union[str, None] = "0001_initial_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column(
            "updated_at", sa.Text, nullable=False, server_default=sa.text("(datetime('now'))")
        ),
        sa.Column("updated_by", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
