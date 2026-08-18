"""Tests de shared/app_settings.py — timeout de sesión editable en caliente,
con fallback a .env y cache con TTL."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import Settings
from src.shared.app_settings import (
    get_session_timeout_meta,
    get_session_timeout_minutes,
    invalidate_cache,
    set_session_timeout_minutes,
)
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
def _clear_cache() -> None:
    invalidate_cache()
    yield
    invalidate_cache()


@pytest.mark.unit
def test_timeout_default_sin_fila(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tabla vacía -> usa el valor de .env, sin cachear."""
    settings = Settings(secret_key="x" * 32, session_timeout_minutes=30)
    monkeypatch.setattr("src.shared.app_settings.get_settings", lambda: settings)
    assert get_session_timeout_minutes(db_session) == 30


@pytest.mark.unit
def test_set_y_get_timeout(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(secret_key="x" * 32, session_timeout_minutes=30)
    monkeypatch.setattr("src.shared.app_settings.get_settings", lambda: settings)

    resultado = set_session_timeout_minutes(db_session, 60, updated_by="admin")
    assert resultado == 60
    assert get_session_timeout_minutes(db_session) == 60


@pytest.mark.unit
def test_set_timeout_fuera_de_rango_bajo(db_session: Session) -> None:
    with pytest.raises(ValueError, match="entre 5 y 240"):
        set_session_timeout_minutes(db_session, 2, updated_by="admin")


@pytest.mark.unit
def test_set_timeout_fuera_de_rango_alto(db_session: Session) -> None:
    with pytest.raises(ValueError, match="entre 5 y 240"):
        set_session_timeout_minutes(db_session, 300, updated_by="admin")


@pytest.mark.unit
def test_get_timeout_meta_sin_fila(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(secret_key="x" * 32, session_timeout_minutes=30)
    monkeypatch.setattr("src.shared.app_settings.get_settings", lambda: settings)
    minutos, updated_at, updated_by = get_session_timeout_meta(db_session)
    assert minutos == 30
    assert updated_at is None
    assert updated_by is None


@pytest.mark.unit
def test_get_timeout_meta_con_fila(db_session: Session) -> None:
    set_session_timeout_minutes(db_session, 45, updated_by="javier.guerrero")
    minutos, updated_at, updated_by = get_session_timeout_meta(db_session)
    assert minutos == 45
    assert updated_by == "javier.guerrero"
    assert updated_at is not None


@pytest.mark.unit
def test_cache_evita_segunda_lectura(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tras el primer get, el segundo dentro del TTL no vuelve a golpear la BD."""
    set_session_timeout_minutes(db_session, 90, updated_by="admin")
    assert get_session_timeout_minutes(db_session) == 90

    # Cambiar la fila directamente sin invalidar cache — el segundo get debe
    # seguir devolviendo el valor cacheado, no el nuevo.
    from sqlalchemy import text

    db_session.execute(
        text(
            "UPDATE app_settings SET value = '15' WHERE key = 'session_timeout_minutes'"
        )
    )
    db_session.commit()
    assert get_session_timeout_minutes(db_session) == 90  # aún cacheado

    invalidate_cache()
    assert get_session_timeout_minutes(db_session) == 15  # ahora sí lee de BD
