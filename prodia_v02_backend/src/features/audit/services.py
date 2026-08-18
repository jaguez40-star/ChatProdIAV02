"""AuditService — encapsula creación de eventos de auditoría. Copiado literal
de Robustez V02 (L1-L11).

Contrato transaccional: los métodos `log_*` hacen `flush()`, NUNCA `commit()`.
El commit lo hace `AuthService.authenticate_ldap()` — respeta esto o los
eventos de auditoría se pierden en el rollback (ver services.py de auth).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.core.logger import get_logger
from src.features.auth.models import AuthEvent
from src.features.auth.repositories import UserRepository

logger = get_logger("audit.service")


class AuditService:
    """Métodos semánticos para registrar eventos de auditoría."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = UserRepository(db)
        self._settings = get_settings()

    def _create_event(
        self,
        *,
        username: str,
        event_type: str,
        reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None,
    ) -> AuthEvent:
        return self._repo.create_auth_event(
            username=username,
            event_type=event_type,
            domain=self._settings.auth_ad_domain,
            reason=reason,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
        )

    def log_login_success(
        self,
        *,
        username: str,
        user_id: int,
        timestamp: str,
        reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None,
    ) -> AuthEvent:
        """Registra login exitoso + actualiza last_login_at. Hace flush, NO commit."""
        event = self._create_event(
            username=username,
            event_type="login_success",
            reason=reason,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
        )
        self._repo.update_last_login(user_id, timestamp)
        logger.info("audit_login_success", username=username)
        return event

    def log_login_failure(
        self,
        *,
        username: str,
        reason: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None,
    ) -> AuthEvent:
        """Registra login fallido. Hace flush, NO commit."""
        event = self._create_event(
            username=username,
            event_type="login_failure",
            reason=reason,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
        )
        logger.warning("audit_login_failure", username=username, reason=reason)
        return event

    def log_logout(
        self,
        *,
        username: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None,
    ) -> AuthEvent:
        """Registra logout. Hace flush, NO commit."""
        event = self._create_event(
            username=username,
            event_type="logout",
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
        )
        logger.info("audit_logout", username=username)
        return event

    def get_events(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        username: str | None = None,
        event_type: str | None = None,
    ) -> list[AuthEvent]:
        """Consulta eventos de auditoría con filtros opcionales."""
        from sqlalchemy import select

        stmt = select(AuthEvent).order_by(AuthEvent.created_at.desc())

        if username:
            stmt = stmt.where(AuthEvent.username == username)
        if event_type:
            stmt = stmt.where(AuthEvent.event_type == event_type)

        stmt = stmt.offset(offset).limit(limit)
        return list(self._db.execute(stmt).scalars().all())

    def count_events(
        self,
        *,
        username: str | None = None,
        event_type: str | None = None,
    ) -> int:
        """Cuenta total de eventos (para paginación)."""
        from sqlalchemy import func, select

        stmt = select(func.count(AuthEvent.id))

        if username:
            stmt = stmt.where(AuthEvent.username == username)
        if event_type:
            stmt = stmt.where(AuthEvent.event_type == event_type)

        result = self._db.execute(stmt).scalar()
        return result or 0
