"""Engine de PostgreSQL `robustez_v02` (schema `ops.*`) — fuente del EBITDA.

Cuarto engine del sistema (CLAUDE.md §3). Regla de oro: **los engines nunca se
mezclan**. `ops` es de SOLO LECTURA — ProdIA V02 consume la BD operacional de
Robustez V02, no la administra.

Mismo patrón que `db_prod` (L4): `lru_cache` para crear el engine una sola vez,
`pool_pre_ping=True` para sobrevivir a cortes de VPN (reintenta la conexión en
vez de fallar con una conexión zombie del pool).

**Cero I/O en tiempo de import** (AP-2): `create_engine` solo se ejecuta dentro
de `get_ops_engine()`. `scripts/export_openapi.py` importa `src.main` —y con él
este módulo— en cada `git commit` y en CI; si el engine se creara al importar,
esos flujos intentarían resolver la URL sin VPN.

**`OPS_DATABASE_URL` vacía es un estado válido, no un error de arranque.** El
backend arranca igual; solo `/ebitda/*` responde 503. Ninguna BD que no sea
`db_auth` puede tumbar la aplicación entera.
"""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import get_settings


class OpsNoConfiguradaError(RuntimeError):
    """`OPS_DATABASE_URL` está vacía — no hay a dónde conectarse.

    Excepción propia y no `SQLAlchemyError` a propósito: el handler global de
    `core/exceptions.py` traduce los fallos de SQLAlchemy a 503, pero esto NO
    es un fallo de base de datos — es una configuración ausente. Sin este tipo,
    el caso saldría como 500 genérico y el operador no sabría que solo le falta
    una variable de entorno (AP-10).
    """


@lru_cache(maxsize=1)
def get_ops_engine() -> Any:
    settings = get_settings()
    if not settings.ops_database_url:
        raise OpsNoConfiguradaError(
            "OPS_DATABASE_URL no está configurada — la BD operacional de "
            "ROBUSTEZ (schema ops) es la fuente del EBITDA."
        )
    return create_engine(
        settings.ops_database_url,
        echo=settings.is_dev,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


def get_ops_session_factory() -> Any:
    return sessionmaker(bind=get_ops_engine())


def get_ops_db() -> Generator[Session, None, None]:
    """Dependencia FastAPI. Los tests la sustituyen con
    `app.dependency_overrides[get_ops_db]` — jamás tocan el servidor real."""
    db: Session = get_ops_session_factory()()
    try:
        yield db
    finally:
        db.close()


def check_ops_connection() -> bool:
    """No lanza: `/health` la usa para reportar estado, no para abortar."""
    settings = get_settings()
    if not settings.ops_database_url:
        return False
    try:
        with get_ops_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
