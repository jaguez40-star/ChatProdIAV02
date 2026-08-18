"""Tests de AuthService.authenticate_ldap — las 5 ramas del flujo (L5), con
_ldap_bind parcheado para no depender de LDAP/VPN real."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import Settings
from src.features.auth.models import PermissionGroup, User
from src.features.auth.services import AuthService, LDAPError
from src.shared.db_auth import Base


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "secret_key": "x" * 32,
        "enable_local_login": False,
        "auth_ad_domain": "red.ecopetrol.com.co",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()

    group = PermissionGroup(id=1, name="Consulta", is_admin=0)
    session.add(group)
    session.flush()
    session.add(
        User(
            id=1,
            username="test.user",
            email="test.user@ecopetrol.com.co",
            is_admin=0,
            is_active=1,
            group_id=1,
        )
    )
    session.add(
        User(
            id=2,
            username="inactivo",
            email="inactivo@ecopetrol.com.co",
            is_admin=0,
            is_active=0,
            group_id=1,
        )
    )
    session.commit()
    yield session
    session.close()


@pytest.mark.unit
def test_usuario_no_registrado(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.features.auth.services.get_settings", lambda: _settings())
    service = AuthService(db_session)
    with pytest.raises(PermissionError, match="no registrado"):
        service.authenticate_ldap("desconocido", "cualquiera")

    events = db_session.execute(
        text("SELECT reason FROM auth_events WHERE username='desconocido'")
    ).fetchall()
    assert len(events) == 1
    assert events[0][0] == "not_in_app_users"


@pytest.mark.unit
def test_usuario_inactivo(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.features.auth.services.get_settings", lambda: _settings())
    service = AuthService(db_session)
    with pytest.raises(PermissionError, match="desactivado"):
        service.authenticate_ldap("inactivo", "cualquiera")


@pytest.mark.unit
def test_login_local_exitoso(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(
        enable_local_login=True,
        local_login_username="test.user",
        local_login_password="clave-dev",
        local_login_allowed_ips="127.0.0.1",
    )
    monkeypatch.setattr("src.features.auth.services.get_settings", lambda: settings)
    service = AuthService(db_session)
    user = service.authenticate_ldap("test.user", "clave-dev", ip_address="127.0.0.1")
    assert user.username == "test.user"

    row = db_session.execute(
        text(
            "SELECT reason FROM auth_events WHERE username='test.user' AND event_type='login_success'"
        )
    ).fetchone()
    assert row is not None
    assert row[0] == "local_login_dev"


@pytest.mark.unit
def test_ldap_bind_exitoso(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.features.auth.services.get_settings", lambda: _settings())
    service = AuthService(db_session)
    monkeypatch.setattr(service, "_resolve_ldap_server", lambda: "ldap://fake")
    monkeypatch.setattr(service, "_ldap_bind", lambda url, u, p: True)

    user = service.authenticate_ldap("test.user", "clave-cualquiera")
    assert user.username == "test.user"


@pytest.mark.unit
def test_ldap_credenciales_invalidas(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.features.auth.services.get_settings", lambda: _settings())
    service = AuthService(db_session)
    monkeypatch.setattr(service, "_resolve_ldap_server", lambda: "ldap://fake")
    monkeypatch.setattr(service, "_ldap_bind", lambda url, u, p: False)

    with pytest.raises(PermissionError, match="Credenciales inválidas"):
        service.authenticate_ldap("test.user", "clave-mala")


@pytest.mark.unit
def test_ldap_inalcanzable(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.features.auth.services.get_settings", lambda: _settings())
    service = AuthService(db_session)

    def _raise(*args: object, **kwargs: object) -> str:
        raise LDAPError("simulado: LDAP no responde")

    monkeypatch.setattr(service, "_resolve_ldap_server", _raise)

    with pytest.raises(LDAPError):
        service.authenticate_ldap("test.user", "clave-cualquiera")

    row = db_session.execute(
        text(
            "SELECT reason FROM auth_events WHERE username='test.user' AND event_type='login_failure'"
        )
    ).fetchone()
    assert row is not None
    assert row[0] == "ldap_unreachable"


@pytest.mark.unit
def test_session_token_roundtrip(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.features.auth.services.get_settings", lambda: _settings())
    service = AuthService(db_session)
    token = service.create_session_token(user_id=42)
    user_id = service.validate_session_token(token)
    assert user_id == 42


@pytest.mark.unit
def test_session_token_invalido(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.features.auth.services.get_settings", lambda: _settings())
    service = AuthService(db_session)
    assert service.validate_session_token("token-basura-invalido") is None


@pytest.mark.unit
def test_logout_registra_evento(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.features.auth.services.get_settings", lambda: _settings())
    service = AuthService(db_session)
    service.logout("test.user")

    row = db_session.execute(
        text(
            "SELECT event_type FROM auth_events WHERE username='test.user' AND event_type='logout'"
        )
    ).fetchone()
    assert row is not None
