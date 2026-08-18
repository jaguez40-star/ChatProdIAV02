"""Repositorio auth — queries de acceso a datos (cero lógica de negocio).

Copiado literal de Robustez V02 (L1-L11). get_campos/get_sections implementan
el modelo de permisos ADITIVO (L10): permisos_efectivos = UNION(grupo,
individuales), sin denegaciones. `sorted()` da salida determinista.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from src.features.auth.models import (
    AuthEvent,
    GroupCampoPermission,
    GroupSectionPermission,
    User,
    UserCampoPermission,
    UserSectionPermission,
)


class UserRepository:
    """Acceso a datos de usuarios y permisos."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_username(self, username: str) -> User | None:
        stmt = (
            select(User)
            .options(joinedload(User.group))
            .where(User.username == username)
        )
        return self._db.execute(stmt).scalars().first()

    def get_by_id(self, user_id: int) -> User | None:
        stmt = select(User).options(joinedload(User.group)).where(User.id == user_id)
        return self._db.execute(stmt).scalars().first()

    def get_campos(self, user_id: int, group_id: int | None) -> list[str]:
        """Campos autorizados = grupo + individuales (sin duplicados)."""
        campos: set[str] = set()

        if group_id is not None:
            stmt = select(GroupCampoPermission.campo).where(
                GroupCampoPermission.group_id == group_id,
            )
            campos.update(self._db.execute(stmt).scalars().all())

        stmt_user = select(UserCampoPermission.campo).where(
            UserCampoPermission.user_id == user_id,
        )
        campos.update(self._db.execute(stmt_user).scalars().all())

        return sorted(campos)

    def get_sections(self, user_id: int, group_id: int | None) -> list[str]:
        """Secciones autorizadas = grupo + individuales (sin duplicados)."""
        sections: set[str] = set()

        if group_id is not None:
            stmt = select(GroupSectionPermission.section_id).where(
                GroupSectionPermission.group_id == group_id,
            )
            sections.update(self._db.execute(stmt).scalars().all())

        stmt_user = select(UserSectionPermission.section_id).where(
            UserSectionPermission.user_id == user_id,
        )
        sections.update(self._db.execute(stmt_user).scalars().all())

        return sorted(sections)

    def update_last_login(self, user_id: int, timestamp: str) -> None:
        """Actualiza cache de último login en app_users."""
        user = self._db.get(User, user_id)
        if user is not None:
            user.last_login_at = timestamp
            self._db.flush()

    def create_auth_event(
        self,
        *,
        username: str,
        event_type: str,
        domain: str,
        reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None,
    ) -> AuthEvent:
        """Registra evento de autenticación en auth_events."""
        event = AuthEvent(
            username=username,
            event_type=event_type,
            domain=domain,
            reason=reason,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
        )
        self._db.add(event)
        self._db.flush()
        return event
