"""Fixtures compartidos para toda la suite de tests.

Copiado literal de Robustez V02 (L2): SQLite en memoria REAL (no MagicMock)
con PRAGMA foreign_keys=ON, httpx.AsyncClient + ASGITransport (mismo código
async en tests y producción, sin threadpool intermedio), y el fixture que
aísla structlog de cada test.
"""

from __future__ import annotations

from typing import Any

import pytest
import structlog
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import src.shared.db_auth as _db_auth_module
from src.features.auth.models import PermissionGroup, User
from src.shared.db_auth import Base

# ── Logging aislado por test ────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _structlog_no_escribe_a_stdout_cerrado() -> None:
    """Manda structlog a un logger nulo durante cada test unitario.

    `structlog.configure()` es un singleton POR PROCESO, y
    `src.core.logger.setup_logging` fija el destino con
    `PrintLoggerFactory(file=sys.stdout)`, que captura el stream por valor.
    pytest reemplaza `sys.stdout` por un buffer distinto en cada test y lo
    cierra al terminarlo, así que un `setup_logging()` ejecutado dentro de un
    test deja el logger global apuntando a un archivo ya cerrado. El
    siguiente test que loguee de verdad revienta con
    `ValueError: I/O operation on closed file` — un fallo por orden de
    ejecución, no por su propia lógica. Producción NO está afectada:
    `main.py` llama `setup_logging()` una sola vez con el stdout real del
    proceso, que no se cierra.
    """
    structlog.configure(
        processors=[],
        logger_factory=structlog.ReturnLoggerFactory(),
        cache_logger_on_first_use=False,
    )


# ── BD en memoria para tests de integración ─────────────────────────────────


def _make_integration_engine() -> Engine:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn: Any, _: Any) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine


def _seed_integration_db(session: Session) -> User:
    """Crea grupo Administradores + usuario de prueba en la BD de test."""
    group = PermissionGroup(name="Administradores", description="Admin", is_admin=1)
    session.add(group)
    session.flush()

    user = User(
        username="test.user",
        email="test.user@ecopetrol.com.co",
        full_name="Usuario de Prueba",
        is_admin=1,
        is_active=1,
        group_id=group.id,
    )
    session.add(user)
    session.commit()
    return user


@pytest.fixture(scope="session")
def integration_engine() -> Engine:
    """Engine SQLite en memoria compartido por toda la sesión de tests."""
    return _make_integration_engine()


@pytest.fixture(autouse=False)
def patch_db_for_integration(
    integration_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Any:
    """Parchea SessionLocal para que apunte a BD en memoria.

    Usar en tests de integración que escriben en BD (login, logout, etc.).

    Parchea DOS lugares, no uno: `src.shared.db_auth.SessionLocal` (de donde
    lee `get_db()`, usado por los routers vía `Depends`) Y
    `src.middleware.auth.SessionLocal` (que hace `from ... import
    SessionLocal` — una importación por VALOR, no por referencia al módulo:
    si `src.middleware.auth` ya fue importado por un test anterior en la
    misma sesión de pytest, su nombre local `SessionLocal` quedó apuntando
    al engine REAL de archivo y parchear solo `db_auth` no lo alcanza. Sin
    este segundo parche, cualquier request AUTENTICADO (con cookie) pasaría
    por el middleware usando la BD real en vez de la de test — un flujo
    login→endpoint-protegido parecería funcionar pero estaría leyendo/
    escribiendo en `data/prodia_v02_auth.db`, no en memoria.
    """
    integration_session = sessionmaker(bind=integration_engine, expire_on_commit=False)
    monkeypatch.setattr(_db_auth_module, "SessionLocal", integration_session)

    import src.middleware.auth as _auth_middleware_module

    monkeypatch.setattr(_auth_middleware_module, "SessionLocal", integration_session)

    with integration_session() as session:
        existing = session.query(User).filter_by(username="test.user").first()
        if not existing:
            _seed_integration_db(session)

    yield integration_session


# ── Fixtures base ────────────────────────────────────────────────────────────


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def async_client() -> Any:
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
async def integration_client(patch_db_for_integration: Any) -> Any:
    """Cliente HTTP que usa BD en memoria — para tests que escriben en BD."""
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
