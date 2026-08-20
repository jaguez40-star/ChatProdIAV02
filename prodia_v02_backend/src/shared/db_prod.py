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
    """Sesión de SOLO LECTURA — la que usan `tablas` (F1) y `analisis` (F2).

    No abre transacción ni hace commit: para leer no hace falta, y así una consulta
    lenta no mantiene una transacción abierta reteniendo recursos.
    """
    db: Session = get_prod_session_factory()()
    try:
        yield db
    finally:
        db.close()


def get_prod_tx() -> Generator[Session, None, None]:
    """Sesión TRANSACCIONAL — para el ETL de Ingesta (F3), que escribe.

    Confirma al terminar bien y revierte ante cualquier excepción. Existe aparte de
    `get_prod_db` a propósito: aquella no hace commit ni rollback (no le hace falta), y
    cambiarla para que los hiciera afectaría a dos features que solo leen.

    **Es lo que hace atómica la ingesta.** Un `.xlsm` produce escrituras en 18 tablas; si
    falla la hoja 30 de 37, revertir entero deja la base como estaba, en vez de con un
    reporte a medio cargar que nadie sabría distinguir de uno completo.

    Como contrapartida, la transacción vive lo que dure la ingesta —minutos— y retiene
    los locks de las tablas que toca. Por eso el ETL toma además un `pg_advisory_xact_lock`
    por fecha de reporte: dos ingestas de la misma fecha se serializan de forma explícita
    en lugar de bloquearse a ciegas dentro de PostgreSQL.
    """
    db: Session = get_prod_session_factory()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
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
