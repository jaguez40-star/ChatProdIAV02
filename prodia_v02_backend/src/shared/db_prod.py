"""Engine de PostgreSQL `daily_report_prod` — lazy, `pool_pre_ping`. Copiado
del patrón `db_ops.py` de Robustez V02 (L4): `pool_pre_ping=True` es lo que
sobrevive a cortes de VPN (reintenta la conexión en vez de fallar con una
conexión zombie del pool). Nunca se mezcla con `db_auth` (L4 — dos engines
separados, regla declarada en el propio código de la plantilla).

Clasificación H4/P-6 → H9 (F1): la feature `tablas` depende de este engine, pero
`main.py` sigue SIN abortar el arranque si Postgres está caído. El fallo se
degrada donde importa: `/api/v1/tablas/*` devuelve 503 y /health reporta
`degraded`; login y el resto de la app (que solo usan `db_auth`) no se ven
afectados. Hacer fail-fast aquí tumbaría toda la aplicación por una feature.

Nota para tests: `get_prod_db` es la dependencia que se sustituye con
`app.dependency_overrides[get_prod_db]` (ver `tests/conftest.py::patch_prod_db`).
El engine está cacheado con `@lru_cache`, así que NO basta con parchear settings:
hay que override-ar la dependencia o limpiar la caché.
"""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import get_settings


@lru_cache(maxsize=1)
def get_prod_engine() -> Any:
    settings = get_settings()
    return create_engine(
        settings.prod_database_url,
        echo=settings.is_dev,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


def get_prod_session_factory() -> Any:
    return sessionmaker(bind=get_prod_engine())


def get_prod_db() -> Generator[Session, None, None]:
    db: Session = get_prod_session_factory()()
    try:
        yield db
    finally:
        db.close()


def check_prod_connection() -> bool:
    """No lanza — F0 la trata como opcional. Devuelve False si no conecta
    (Postgres apagado, URL vacía, credenciales inválidas, lo que sea)."""
    settings = get_settings()
    if not settings.prod_database_url:
        return False
    try:
        with get_prod_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
