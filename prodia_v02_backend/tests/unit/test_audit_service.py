"""Tests de AuditService — registro y consulta de auth_events."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import Settings
from src.features.audit.services import AuditService
from src.shared.db_auth import Base


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(secret_key="x" * 32, auth_ad_domain="red.ecopetrol.com.co")
    monkeypatch.setattr("src.features.audit.services.get_settings", lambda: settings)


@pytest.mark.unit
def test_log_login_failure_y_listar(db_session: Session) -> None:
    audit = AuditService(db_session)
    audit.log_login_failure(username="test.user", reason="invalid_credentials")
    db_session.commit()

    events = audit.get_events(username="test.user")
    assert len(events) == 1
    assert events[0].event_type == "login_failure"
    assert events[0].reason == "invalid_credentials"
    assert events[0].domain == "red.ecopetrol.com.co"


@pytest.mark.unit
def test_log_logout(db_session: Session) -> None:
    audit = AuditService(db_session)
    audit.log_logout(username="test.user")
    db_session.commit()

    events = audit.get_events(username="test.user", event_type="logout")
    assert len(events) == 1


@pytest.mark.unit
def test_count_events_con_filtros(db_session: Session) -> None:
    audit = AuditService(db_session)
    audit.log_login_failure(username="a", reason="invalid_credentials")
    audit.log_login_failure(username="a", reason="invalid_credentials")
    audit.log_login_failure(username="b", reason="not_in_app_users")
    db_session.commit()

    assert audit.count_events(username="a") == 2
    assert audit.count_events() == 3
    assert audit.count_events(event_type="login_failure") == 3


@pytest.mark.unit
def test_get_events_paginacion(db_session: Session) -> None:
    audit = AuditService(db_session)
    for i in range(5):
        audit.log_logout(username=f"user{i}")
    db_session.commit()

    page1 = audit.get_events(limit=2, offset=0)
    page2 = audit.get_events(limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert page1[0].id != page2[0].id
