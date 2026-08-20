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
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import src.shared.db_auth as _db_auth_module
from src.features.auth.models import PermissionGroup, User
from src.shared.db_auth import Base
from src.shared.db_auth import get_db as _get_db

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
        # 🔑 `StaticPool` es obligatorio con `:memory:`. Sin él, el pool abre una
        # conexión NUEVA por cada checkout, y en SQLite cada conexión a
        # `:memory:` crea su PROPIA base vacía: las tablas que este módulo crea
        # aquí no existirían para el resto del proceso.
        #
        # Los tests que solo usan `SessionLocal` no lo notaban porque reutilizan
        # la misma sesión de principio a fin. Se destapó al montar el primer
        # endpoint que resuelve su sesión por `Depends`: pedía una conexión
        # distinta y encontraba una base sin ninguna tabla ("no such table:
        # clasificacion_log"), que el manejador global traducía a un 503.
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn: Any, _: Any) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)

    # Las tablas de F4 viven solo en la migración 0004, no en un modelo ORM:
    # `libreta.py` usa SQL directo, y declararlas dos veces (modelo + DDL de
    # Alembic) las dejaría divergir en silencio. Aquí se crean explícitamente
    # para que los tests de integración ejerciten el SQL real.
    with engine.begin() as conexion:
        conexion.execute(text("""
                CREATE TABLE IF NOT EXISTS clasificacion_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    usuario VARCHAR(120),
                    conversacion_id VARCHAR(64),
                    texto_pregunta TEXT NOT NULL,
                    grupo_asignado VARCHAR(20) NOT NULL,
                    capa_resolutora VARCHAR(20) NOT NULL,
                    patrones_atrapados TEXT,
                    entidad_cruda VARCHAR(200),
                    llm_diag VARCHAR(40),
                    veredicto VARCHAR(30) NOT NULL DEFAULT 'pendiente',
                    grupo_correcto VARCHAR(20),
                    fuente_veredicto VARCHAR(20),
                    ts_veredicto TIMESTAMP,
                    nota_revision TEXT
                )
                """))

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

    # `get_db` se importa POR VALOR en los routers (`from ... import get_db`),
    # así que parchear `SessionLocal` no alcanza a las dependencias ya resueltas
    # por FastAPI: seguirían abriendo la BD real de archivo. El
    # `dependency_overrides` es el mecanismo del framework para esto, y es el
    # mismo patrón que F1 introdujo para `get_prod_db`.
    from src.main import app

    def _sesion_de_test() -> Any:
        db = integration_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[_get_db] = _sesion_de_test

    yield integration_session

    app.dependency_overrides.pop(_get_db, None)


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


# ── .xlsm de muestra para los extractores de F3 ─────────────────────────────


@pytest.fixture(scope="session")
def libro_muestra_new() -> Any:
    """El reporte NEW de muestra, cargado UNA vez para toda la suite.

    Alcance `session` a propósito: el libro pesa 125 MB y tener dos vivos a la vez
    (un fixture por módulo de test) hacía caer el proceso con un access violation de
    Windows dentro de openpyxl.

    `read_only=True, data_only=True` replica exactamente cómo lo abre el ETL en
    producción: `data_only` lee los valores calculados en caché, no las fórmulas.
    """
    from openpyxl import load_workbook

    from tests.fakes.muestras_xlsm import DIRECTORIO_MUESTRAS, hay_muestras

    if not hay_muestras():
        pytest.skip(f"no hay .xlsm de muestra en {DIRECTORIO_MUESTRAS}")

    archivos = sorted(DIRECTORIO_MUESTRAS.glob("*New*.xlsm"))
    if not archivos:
        pytest.skip("no hay ningún .xlsm NEW de muestra")

    libro = load_workbook(archivos[0], read_only=True, data_only=True, keep_links=False)
    yield libro
    libro.close()


# ── db_prod (PostgreSQL) en tests — hallazgo H1/H2 del plan F1 ──────────────


@pytest.fixture
def patch_prod_db() -> Any:
    """Sustituye la sesión de `db_prod` por un doble, sin tocar PostgreSQL.

    Devuelve una factoría: `patch_prod_db(datos=..., fallar=...)` registra el override
    y entrega la `SesionProdFalsa` usada, para poder inspeccionar el SQL emitido.

    A diferencia de `patch_db_for_integration` (que hace monkeypatch de `SessionLocal`),
    aquí se usa `app.dependency_overrides` — el patrón de FastAPI — porque `db_prod` NO
    expone un `SessionLocal` de módulo: construye el engine con `get_prod_engine()`
    cacheado por `@lru_cache`, así que parchear settings no bastaría (la caché ya tendría
    el engine viejo). Es el único mecanismo que corta la conexión real de raíz.

    Sin esto, cualquier test de `tablas` intentaría alcanzar el servidor 10.100.26.139 y
    fallaría en CI, que no levanta Postgres ni define `PROD_DATABASE_URL`.
    """
    from src.main import app
    from src.shared.db_prod import get_prod_db
    from tests.fakes.prod_db_falsa import SesionProdFalsa

    creadas: list[SesionProdFalsa] = []

    def _registrar(
        datos: dict[str, Any] | None = None, fallar: bool = False
    ) -> SesionProdFalsa:
        sesion = SesionProdFalsa(datos=datos, fallar=fallar)
        creadas.append(sesion)

        def _override() -> Any:
            yield sesion

        app.dependency_overrides[get_prod_db] = _override
        return sesion

    yield _registrar

    app.dependency_overrides.pop(get_prod_db, None)


# ── Fuentes de datos de F2 (Análisis) ───────────────────────────────────────
#
# Mismo principio que `patch_prod_db`: NINGÚN test sale a la red ni abre los
# ficheros reales. La BD de diferidas pesa 954 MB y el LLM vive en otro host —
# tocarlos haría la suite lenta, frágil y dependiente de la VPN.


@pytest.fixture
def patch_ops_db() -> Any:
    """Sustituye la sesión de `db_ops` (PostgreSQL `robustez_v02`) por un doble.

    Gemelo de `patch_prod_db` y por el mismo motivo: `db_ops` construye su
    engine con `@lru_cache`, así que parchear settings no bastaría.
    """
    from src.main import app
    from src.shared.db_ops import get_ops_db
    from tests.fakes.prod_db_falsa import SesionProdFalsa

    def _registrar(
        datos: dict[str, Any] | None = None, fallar: bool = False
    ) -> SesionProdFalsa:
        sesion = SesionProdFalsa(datos=datos, fallar=fallar)

        def _override() -> Any:
            yield sesion

        app.dependency_overrides[get_ops_db] = _override
        return sesion

    yield _registrar

    app.dependency_overrides.pop(get_ops_db, None)


@pytest.fixture
def diferidas_db_falsa(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """SQLite temporal con la forma REAL de `AVM_DATADIF` (18 columnas).

    Se replican las columnas que el endpoint consulta, incluidas
    `ACEITE_PERDIDO`/`GAS_PERDIDO`: la BD real las tiene y el bloque `impacto`
    depende de ellas. Un fixture con menos columnas dejaría pasar un portado
    incompleto.

    Devuelve una factoría `diferidas_db_falsa(filas)` que crea el fichero y
    apunta `DIFERIDAS_DB_PATH` a él.
    """
    import sqlite3

    from src.core.config import get_settings

    def _crear(filas: list[tuple[Any, ...]] | None = None) -> Any:
        ruta = tmp_path / "diferidas_test.db"
        conexion = sqlite3.connect(ruta)
        conexion.execute("""
            CREATE TABLE AVM_DATADIF (
                id_row INTEGER, VICE TEXT, GERENCIA TEXT, AREA TEXT, CAMPO TEXT,
                EVENT_DATE TEXT, COMPLETION TEXT, INI_DATE TEXT, END_DATE TEXT,
                CAUSE_NIVEL2 TEXT, CAUSE_NIVEL3 TEXT, CAUSE_NIVEL4 TEXT,
                CAUSE_NIVEL5 TEXT, CAUSE TEXT, COMENTARIO TEXT,
                ACEITE_PERDIDO REAL, AGUA_PERDIDO REAL, GAS_PERDIDO REAL
            )
            """)
        if filas:
            conexion.executemany(
                "INSERT INTO AVM_DATADIF VALUES (" + ",".join("?" * 18) + ")", filas
            )
        conexion.commit()
        conexion.close()

        monkeypatch.setenv("DIFERIDAS_DB_PATH", str(ruta))
        get_settings.cache_clear()
        return ruta

    yield _crear

    # La caché de settings es global al proceso: sin limpiarla, el siguiente
    # test heredaría la ruta temporal ya borrada.
    get_settings.cache_clear()


@pytest.fixture
def stub_llm(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Sustituye la llamada a Ollama por una respuesta fija.

    Se parchea `_invocar_una_vez` y no `invocar` a propósito: así la política
    de reintento real (T4 — reintentar solo ante `generacion_abortada`) sigue
    ejecutándose y queda cubierta por los tests.
    """
    from src.shared import llm_client

    def _registrar(respuestas: list[Any]) -> list[int]:
        """`respuestas` se consumen en orden; la última se repite si hace falta."""
        llamadas = [0]
        pendientes = list(respuestas)

        def _falso(
            prompt: str, timeout: int, diag: dict[str, Any] | None
        ) -> Any | None:
            llamadas[0] += 1
            valor = pendientes.pop(0) if len(pendientes) > 1 else pendientes[0]
            if isinstance(valor, str) and diag is not None:
                # Una cadena representa un fallo: se usa como `status` del diag.
                diag["status"] = valor
                return None
            return valor

        monkeypatch.setattr(llm_client, "_invocar_una_vez", _falso)
        return llamadas

    return _registrar
