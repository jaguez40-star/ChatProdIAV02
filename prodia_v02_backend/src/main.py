"""Entry point FastAPI — ProdIA V02.

Patrón de Robustez V02 (L1-L11): routers importados uno por uno con alias
explícito (sin auto-discovery, main.py es el índice legible de la app),
lifespan fail-fast, orden de middlewares deliberado (correlation_id primero
en ejecutarse pese a añadirse último — `add_middleware` envuelve en orden
inverso).

Clasificación de BDs (H4/P-6, corrección sobre el original): `db_auth`
(SQLite) es CRÍTICA — sin esquema válido, el backend no arranca. `db_prod`
(PostgreSQL) es OPCIONAL en F0 — verificado con Postgres apagado durante el
desarrollo de esta fase, el backend debe arrancar igual y reportar
`degraded` en /health. TODO[F1]: reclasificar a crítica cuando `tablas`
dependa de ella.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import get_settings
from src.core.exceptions import register_exception_handlers
from src.core.logger import get_logger, setup_logging
from src.features.auth.api import router as auth_router
from src.features.permissions.api import router as permissions_router
from src.middleware.auth import AuthMiddleware
from src.middleware.correlation_id import CorrelationIdMiddleware
from src.middleware.request_logger import RequestLoggerMiddleware
from src.shared.db_auth import check_db_connection, verify_auth_db_schema
from src.shared.db_prod import check_prod_connection

settings = get_settings()
logger = get_logger("startup")
setup_logging(json_output=not settings.is_dev)

OPENAPI_TAGS: list[dict[str, str]] = [
    {"name": "Auth", "description": "Login LDAP, logout y sesión actual."},
    {
        "name": "Permissions",
        "description": "Permisos efectivos del usuario autenticado.",
    },
    {"name": "Health", "description": "Estado del backend y sus bases de datos."},
]

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # db_auth — CRÍTICA. Sin esquema válido, el backend no debe servir tráfico.
    if check_db_connection():
        logger.info("db_auth_connection_ok", database_url=settings.database_url)
    else:
        logger.error("db_auth_connection_failed", database_url=settings.database_url)

    try:
        verify_auth_db_schema()
    except RuntimeError as exc:
        logger.error("auth_db_schema_invalid", detalle=str(exc))
        raise

    # db_prod — OPCIONAL en F0 (H4/P-6). Se registra el estado pero NUNCA
    # aborta el arranque. /health reporta el resultado.
    if check_prod_connection():
        logger.info("db_prod_connection_ok")
    else:
        logger.warning(
            "db_prod_connection_unavailable",
            detalle="Postgres opcional en F0 — el backend arranca igual (H4/P-6)",
        )

    yield


app = FastAPI(
    title="ProdIA V02 API",
    version="0.1.0",
    description=(
        "Backend de ProdIA V02 — reconstrucción de 'Análisis avanzado de "
        "producción diaria' sobre las convenciones de Robustez V02."
    ),
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Orden inverso de ejecución: CorrelationId corre PRIMERO (se añade último).
app.add_middleware(AuthMiddleware)
app.add_middleware(RequestLoggerMiddleware)
app.add_middleware(CorrelationIdMiddleware)

register_exception_handlers(app)

app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(permissions_router, prefix=API_PREFIX)


@app.get(f"{API_PREFIX}/health", tags=["Health"])
async def health_check() -> dict[str, Any]:
    db_auth_ok = check_db_connection()
    db_prod_ok = check_prod_connection()
    return {
        "status": "ok" if (db_auth_ok and db_prod_ok) else "degraded",
        "version": app.version,
        "database_auth": "connected" if db_auth_ok else "disconnected",
        "database_prod": "connected" if db_prod_ok else "disconnected",
        "environment": settings.app_env,
    }
