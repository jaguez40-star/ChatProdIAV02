"""Modelos ORM — mapeo de las 8 tablas de prodia_v02_auth.db.

Copiado literal de Robustez V02 (plan L1-L11). Nota: server_default usa
sintaxis SQLite ("(datetime('now'))") porque la BD de auth SIEMPRE es SQLite
en este proyecto -- nunca PostgreSQL.
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.shared.db_auth import Base


class PermissionGroup(Base):
    __tablename__ = "permission_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_admin: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="(datetime('now'))"
    )
    updated_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="(datetime('now'))"
    )

    users: Mapped[list[User]] = relationship("User", back_populates="group")
    campo_permissions: Mapped[list[GroupCampoPermission]] = relationship(
        "GroupCampoPermission",
        back_populates="group",
        cascade="all, delete-orphan",
    )
    section_permissions: Mapped[list[GroupSectionPermission]] = relationship(
        "GroupSectionPermission",
        back_populates="group",
        cascade="all, delete-orphan",
    )

    __table_args__ = (CheckConstraint("is_admin IN (0, 1)", name="ck_pg_is_admin"),)


class User(Base):
    __tablename__ = "app_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_admin: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    group_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("permission_groups.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_login_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="(datetime('now'))"
    )
    updated_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="(datetime('now'))"
    )

    group: Mapped[PermissionGroup | None] = relationship(
        "PermissionGroup", back_populates="users"
    )
    campo_permissions: Mapped[list[UserCampoPermission]] = relationship(
        "UserCampoPermission",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    section_permissions: Mapped[list[UserSectionPermission]] = relationship(
        "UserSectionPermission",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint("is_admin IN (0, 1)", name="ck_au_is_admin"),
        CheckConstraint("is_active IN (0, 1)", name="ck_au_is_active"),
        Index("idx_app_users_username", "username"),
        Index("idx_app_users_email", "email"),
        Index("idx_app_users_group", "group_id"),
        Index("idx_app_users_last_login", "last_login_at"),
    )


class GroupCampoPermission(Base):
    __tablename__ = "group_campo_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("permission_groups.id", ondelete="CASCADE"),
        nullable=False,
    )
    campo: Mapped[str] = mapped_column(Text, nullable=False)

    group: Mapped[PermissionGroup] = relationship(
        "PermissionGroup", back_populates="campo_permissions"
    )

    __table_args__ = (
        UniqueConstraint("group_id", "campo", name="uq_gcp_group_campo"),
        Index("idx_gcp_group", "group_id"),
    )


class GroupSectionPermission(Base):
    __tablename__ = "group_section_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("permission_groups.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[str] = mapped_column(Text, nullable=False)

    group: Mapped[PermissionGroup] = relationship(
        "PermissionGroup", back_populates="section_permissions"
    )

    __table_args__ = (
        UniqueConstraint("group_id", "section_id", name="uq_gsp_group_section"),
        Index("idx_gsp_group", "group_id"),
    )


class UserCampoPermission(Base):
    __tablename__ = "user_campo_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    campo: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="(datetime('now'))"
    )

    user: Mapped[User] = relationship("User", back_populates="campo_permissions")

    __table_args__ = (
        UniqueConstraint("user_id", "campo", name="uq_ucp_user_campo"),
        Index("idx_ucp_user_id", "user_id"),
        Index("idx_ucp_campo", "campo"),
    )


class UserSectionPermission(Base):
    __tablename__ = "user_section_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="(datetime('now'))"
    )

    user: Mapped[User] = relationship("User", back_populates="section_permissions")

    __table_args__ = (
        UniqueConstraint("user_id", "section_id", name="uq_usp_user_section"),
        Index("idx_usp_user_id", "user_id"),
    )


class UserAction(Base):
    __tablename__ = "user_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    section: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="(datetime('now'))"
    )

    __table_args__ = (
        CheckConstraint(
            "details IS NULL OR json_valid(details)",
            name="ck_ua_details_json",
        ),
        Index("idx_ua_username", "username"),
        Index("idx_ua_created", "created_at"),
        Index("idx_ua_action", "action_type"),
        Index("idx_ua_correlation", "correlation_id"),
        Index("idx_ua_user_action_created", "username", "action_type", "created_at"),
    )


class AuthEvent(Base):
    __tablename__ = "auth_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="(datetime('now'))"
    )

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('login_success', 'login_failure', 'logout', 'session_expired')",
            name="ck_ae_event_type",
        ),
        Index("idx_ae_username", "username"),
        Index("idx_ae_created", "created_at"),
        Index("idx_ae_event", "event_type"),
        Index("idx_ae_correlation", "correlation_id"),
    )
