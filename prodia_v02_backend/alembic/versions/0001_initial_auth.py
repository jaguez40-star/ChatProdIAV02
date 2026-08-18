"""0001_initial_auth

Crea las 8 tablas de la BD de auth (SQLite): permission_groups, app_users,
group_campo_permissions, group_section_permissions, user_campo_permissions,
user_section_permissions, user_actions, auth_events.

Convenciones (patrón Robustez V02, L1-L11):
- timestamps como Text con server_default=(datetime('now')) — SQLite, no
  DateTime nativo
- booleanos como Integer + CheckConstraint("x IN (0,1)")
- JSON validado con json_valid() en vez de un tipo JSON nativo
- downgrade() completo, borrando en orden inverso de FKs

Revision ID: 0001_initial_auth
Revises:
Create Date: 2026-08-18

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_auth"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "permission_groups",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_admin", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.Text, nullable=False, server_default=sa.text("(datetime('now'))")
        ),
        sa.Column(
            "updated_at", sa.Text, nullable=False, server_default=sa.text("(datetime('now'))")
        ),
        sa.CheckConstraint("is_admin IN (0, 1)", name="ck_pg_is_admin"),
    )

    op.create_table(
        "app_users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.Text, nullable=False, unique=True),
        sa.Column("email", sa.Text, nullable=False, unique=True),
        sa.Column("full_name", sa.Text, nullable=True),
        sa.Column("is_admin", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "group_id",
            sa.Integer,
            sa.ForeignKey("permission_groups.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("last_login_at", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.Text, nullable=False, server_default=sa.text("(datetime('now'))")
        ),
        sa.Column(
            "updated_at", sa.Text, nullable=False, server_default=sa.text("(datetime('now'))")
        ),
        sa.CheckConstraint("is_admin IN (0, 1)", name="ck_au_is_admin"),
        sa.CheckConstraint("is_active IN (0, 1)", name="ck_au_is_active"),
    )
    op.create_index("idx_app_users_username", "app_users", ["username"])
    op.create_index("idx_app_users_email", "app_users", ["email"])
    op.create_index("idx_app_users_group", "app_users", ["group_id"])
    op.create_index("idx_app_users_last_login", "app_users", ["last_login_at"])

    op.create_table(
        "group_campo_permissions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "group_id",
            sa.Integer,
            sa.ForeignKey("permission_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("campo", sa.Text, nullable=False),
        sa.UniqueConstraint("group_id", "campo", name="uq_gcp_group_campo"),
    )
    op.create_index("idx_gcp_group", "group_campo_permissions", ["group_id"])

    op.create_table(
        "group_section_permissions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "group_id",
            sa.Integer,
            sa.ForeignKey("permission_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("section_id", sa.Text, nullable=False),
        sa.UniqueConstraint("group_id", "section_id", name="uq_gsp_group_section"),
    )
    op.create_index("idx_gsp_group", "group_section_permissions", ["group_id"])

    op.create_table(
        "user_campo_permissions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("app_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("campo", sa.Text, nullable=False),
        sa.Column(
            "created_at", sa.Text, nullable=False, server_default=sa.text("(datetime('now'))")
        ),
        sa.UniqueConstraint("user_id", "campo", name="uq_ucp_user_campo"),
    )
    op.create_index("idx_ucp_user_id", "user_campo_permissions", ["user_id"])
    op.create_index("idx_ucp_campo", "user_campo_permissions", ["campo"])

    op.create_table(
        "user_section_permissions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("app_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("section_id", sa.Text, nullable=False),
        sa.Column(
            "created_at", sa.Text, nullable=False, server_default=sa.text("(datetime('now'))")
        ),
        sa.UniqueConstraint("user_id", "section_id", name="uq_usp_user_section"),
    )
    op.create_index("idx_usp_user_id", "user_section_permissions", ["user_id"])

    op.create_table(
        "user_actions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.Text, nullable=False),
        sa.Column("action_type", sa.Text, nullable=False),
        sa.Column("section", sa.Text, nullable=True),
        sa.Column("details", sa.Text, nullable=True),
        sa.Column("ip_address", sa.Text, nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("correlation_id", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.Text, nullable=False, server_default=sa.text("(datetime('now'))")
        ),
        sa.CheckConstraint(
            "details IS NULL OR json_valid(details)", name="ck_ua_details_json"
        ),
    )
    op.create_index("idx_ua_username", "user_actions", ["username"])
    op.create_index("idx_ua_created", "user_actions", ["created_at"])
    op.create_index("idx_ua_action", "user_actions", ["action_type"])
    op.create_index("idx_ua_correlation", "user_actions", ["correlation_id"])
    op.create_index(
        "idx_ua_user_action_created",
        "user_actions",
        ["username", "action_type", "created_at"],
    )

    op.create_table(
        "auth_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.Text, nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("domain", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("ip_address", sa.Text, nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("correlation_id", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.Text, nullable=False, server_default=sa.text("(datetime('now'))")
        ),
        sa.CheckConstraint(
            "event_type IN ('login_success', 'login_failure', 'logout', 'session_expired')",
            name="ck_ae_event_type",
        ),
    )
    op.create_index("idx_ae_username", "auth_events", ["username"])
    op.create_index("idx_ae_created", "auth_events", ["created_at"])
    op.create_index("idx_ae_event", "auth_events", ["event_type"])
    op.create_index("idx_ae_correlation", "auth_events", ["correlation_id"])


def downgrade() -> None:
    op.drop_table("auth_events")
    op.drop_table("user_actions")
    op.drop_table("user_section_permissions")
    op.drop_table("user_campo_permissions")
    op.drop_table("group_section_permissions")
    op.drop_table("group_campo_permissions")
    op.drop_table("app_users")
    op.drop_table("permission_groups")
