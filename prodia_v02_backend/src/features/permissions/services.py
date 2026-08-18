"""PermissionService — lógica de permisos consolidada. Copiado literal de
Robustez V02 (L10): permisos_efectivos = UNIÓN(grupo, individuales)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.features.auth.repositories import UserRepository


class PermissionService:
    """Consolida permisos de grupo + individuales."""

    def __init__(self, db: Session) -> None:
        self._repo = UserRepository(db)

    def get_effective_campos(self, user_id: int, group_id: int | None) -> list[str]:
        """Campos autorizados (grupo + individuales, sin duplicados, ordenados)."""
        return self._repo.get_campos(user_id, group_id)

    def get_effective_sections(self, user_id: int, group_id: int | None) -> list[str]:
        """Secciones autorizadas (grupo + individuales, sin duplicados, ordenadas)."""
        return self._repo.get_sections(user_id, group_id)

    def has_campo(self, user_id: int, group_id: int | None, campo: str) -> bool:
        """¿El usuario tiene acceso al campo dado?"""
        return campo in self._repo.get_campos(user_id, group_id)

    def has_section(self, user_id: int, group_id: int | None, section_id: str) -> bool:
        """¿El usuario tiene acceso a la sección dada?"""
        return section_id in self._repo.get_sections(user_id, group_id)

    def is_admin(self, user_id: int) -> bool:
        """¿El usuario es admin? (por su grupo o flag personal)."""
        user = self._repo.get_by_id(user_id)
        if user is None:
            return False
        if user.is_admin:
            return True
        if user.group and user.group.is_admin:
            return True
        return False
