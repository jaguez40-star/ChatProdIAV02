"""Tests unitarios de PermissionService — modelo aditivo (L10):
permisos_efectivos = UNIÓN(grupo, individuales)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from src.features.auth.models import (
    GroupCampoPermission,
    GroupSectionPermission,
    PermissionGroup,
    User,
    UserCampoPermission,
    UserSectionPermission,
)
from src.features.permissions.services import PermissionService
from src.shared.db_auth import Base


@pytest.fixture
def db_session() -> Session:
    """BD SQLite en memoria con tablas auth."""
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()

    admin_group = PermissionGroup(id=1, name="Administradores", is_admin=1)
    limited_group = PermissionGroup(id=2, name="Consulta", is_admin=0)
    session.add_all([admin_group, limited_group])
    session.flush()

    admin_user = User(
        id=1,
        username="admin",
        email="admin@test.com",
        is_admin=1,
        is_active=1,
        group_id=1,
    )
    limited_user = User(
        id=2,
        username="limitado",
        email="limitado@test.com",
        is_admin=0,
        is_active=1,
        group_id=2,
    )
    session.add_all([admin_user, limited_user])
    session.flush()

    session.add_all(
        [
            GroupCampoPermission(group_id=2, campo="CASTILLA"),
            GroupCampoPermission(group_id=2, campo="CHICHIMENE"),
            GroupSectionPermission(group_id=2, section_id="consulta"),
            GroupSectionPermission(group_id=2, section_id="analisis"),
        ]
    )
    session.flush()

    session.add(UserCampoPermission(user_id=2, campo="APIAY"))
    session.add(UserSectionPermission(user_id=2, section_id="ingesta"))
    session.flush()

    session.commit()
    yield session
    session.close()


@pytest.mark.unit
def test_get_effective_campos(db_session: Session) -> None:
    service = PermissionService(db_session)
    campos = service.get_effective_campos(user_id=2, group_id=2)
    assert campos == ["APIAY", "CASTILLA", "CHICHIMENE"]


@pytest.mark.unit
def test_get_effective_sections(db_session: Session) -> None:
    service = PermissionService(db_session)
    sections = service.get_effective_sections(user_id=2, group_id=2)
    assert sections == ["analisis", "consulta", "ingesta"]


@pytest.mark.unit
def test_has_campo_true(db_session: Session) -> None:
    service = PermissionService(db_session)
    assert service.has_campo(user_id=2, group_id=2, campo="CASTILLA") is True


@pytest.mark.unit
def test_has_campo_false(db_session: Session) -> None:
    service = PermissionService(db_session)
    assert service.has_campo(user_id=2, group_id=2, campo="RUBIALES") is False


@pytest.mark.unit
def test_has_section_true(db_session: Session) -> None:
    service = PermissionService(db_session)
    assert service.has_section(user_id=2, group_id=2, section_id="ingesta") is True


@pytest.mark.unit
def test_has_section_false(db_session: Session) -> None:
    service = PermissionService(db_session)
    assert service.has_section(user_id=2, group_id=2, section_id="testclas") is False


@pytest.mark.unit
def test_is_admin_true(db_session: Session) -> None:
    service = PermissionService(db_session)
    assert service.is_admin(user_id=1) is True


@pytest.mark.unit
def test_is_admin_false(db_session: Session) -> None:
    service = PermissionService(db_session)
    assert service.is_admin(user_id=2) is False


@pytest.mark.unit
def test_is_admin_nonexistent(db_session: Session) -> None:
    service = PermissionService(db_session)
    assert service.is_admin(user_id=999) is False


@pytest.mark.unit
def test_campos_without_group(db_session: Session) -> None:
    """Usuario sin grupo solo tiene permisos individuales."""
    service = PermissionService(db_session)
    campos = service.get_effective_campos(user_id=2, group_id=None)
    assert campos == ["APIAY"]
