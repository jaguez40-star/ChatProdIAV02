"""Engine de la BD de auth (SQLite) — eager, PRAGMA WAL. Copiado literal (L4).

Es el engine CRÍTICO de F0: sin un esquema válido aquí, `main.py` no arranca
(lifespan fail-fast). `check_same_thread=False` es necesario porque FastAPI
sirve requests síncronos en un threadpool.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.core.config import get_settings


def _build_engine() -> Any:
    settings = get_settings()
    connect_args: dict[str, Any] = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(
        settings.database_url, echo=settings.is_dev, connect_args=connect_args
    )
    if settings.database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_conn: Any, _: Any) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


AUTH_REQUIRED_TABLES = ("app_users", "permission_groups", "auth_events")


def verify_auth_db_schema() -> None:
    """Fail-fast: si las tablas críticas no existen, el backend no arranca."""
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    missing = [t for t in AUTH_REQUIRED_TABLES if t not in existing]
    if missing:
        raise RuntimeError(
            f"Esquema de auth inválido — faltan tablas {missing}. "
            "Ejecuta `uv run alembic upgrade head` antes de arrancar."
        )


def check_db_connection() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
