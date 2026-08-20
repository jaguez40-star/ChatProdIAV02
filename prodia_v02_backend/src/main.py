"""Entry point FastAPI — ProdIA V02.

Patrón de Robustez V02 (L1-L11): routers importados uno por uno con alias
explícito (sin auto-discovery, main.py es el índice legible de la app),
lifespan fail-fast, orden de middlewares deliberado (correlation_id primero
en ejecutarse pese a añadirse último — `add_middleware` envuelve en orden
inverso).

Clasificación de BDs (H4/P-6, corrección sobre el original): `db_auth`
(SQLite) es CRÍTICA — sin esquema válido, el backend no arranca. `db_prod`
(PostgreSQL) es CRÍTICA PARA LA FEATURE `tablas` desde F1, pero **no para el
arranque**: si Postgres está caído, `/api/v1/tablas/*` devuelve 503 y /health
reporta `degraded`, mientras el login y el resto de la app (que solo necesitan
`db_auth`) siguen funcionando. Hacer fail-fast del proceso por `db_prod`
tumbaría la aplicación entera por una sola feature — decisión H9 del plan F1.
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
from src.features.analisis.api import router as analisis_router
from src.features.auth.api import router as auth_router
from src.features.diferidas.api import router as diferidas_router
from src.features.ebitda.api import router as ebitda_router
from src.features.mantenimientos.api import router as mantenimientos_router
from src.features.permissions.api import router as permissions_router
from src.features.tablas.api import router as tablas_router
from src.middleware.auth import AuthMiddleware
from src.middleware.correlation_id import CorrelationIdMiddleware
from src.middleware.request_logger import RequestLoggerMiddleware
from src.shared.db_auth import check_db_connection, verify_auth_db_schema
from src.shared.db_ops import check_ops_connection
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
    {
        "name": "Tablas",
        "description": (
            "Visor de reportes de producción (Control): árbol año/mes/día, hojas y "
            "contenido de tablas. Lee `db_prod` — 503 si PostgreSQL no está disponible."
        ),
    },
    {
        "name": "Análisis",
        "description": (
            "Análisis avanzado de producción: fundación de datos (catálogo, "
            "densidad, huella, cobertura). Lee `db_prod` — 503 si PostgreSQL "
            "no está disponible."
        ),
    },
    {
        "name": "EBITDA",
        "description": (
            "Waterfall economico Ingresos-NOPAT. Lee la BD operacional ROBUSTEZ "
            "(`ops`) - 503 si no esta configurada o no responde."
        ),
    },
    {
        "name": "Diferidas",
        "description": (
            "Historico de produccion diferida por causa (SQLite). Degrada "
            "siempre con HTTP 200."
        ),
    },
    {
        "name": "Mantenimientos",
        "description": (
            "Eventos de servicio a pozo que solapan el mes analizado. Degrada "
            "siempre con HTTP 200."
        ),
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

    # db_prod — desde F1 la necesita la feature `tablas`, pero sigue SIN abortar
    # el arranque (H9): si Postgres está caído, `tablas` responde 503 y el resto
    # de la app (login incluido) funciona con normalidad. /health lo reporta.
    if check_prod_connection():
        logger.info("db_prod_connection_ok")
    else:
        logger.warning(
            "db_prod_connection_unavailable",
            detalle=(
                "Postgres no disponible — /api/v1/tablas/* responderá 503; "
                "el resto del backend arranca igual (H9)"
            ),
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
app.include_router(tablas_router, prefix=API_PREFIX)
app.include_router(analisis_router, prefix=API_PREFIX)
app.include_router(ebitda_router, prefix=API_PREFIX)
app.include_router(diferidas_router, prefix=API_PREFIX)
app.include_router(mantenimientos_router, prefix=API_PREFIX)


@app.get(f"{API_PREFIX}/health", tags=["Health"])
async def health_check() -> dict[str, Any]:
    db_auth_ok = check_db_connection()
    db_prod_ok = check_prod_connection()
    # db_ops es OPCIONAL: sin ella solo cae /ebitda, no la app.
    db_ops_ok = check_ops_connection()
    return {
        "status": "ok" if (db_auth_ok and db_prod_ok) else "degraded",
        "version": app.version,
        "database_auth": "connected" if db_auth_ok else "disconnected",
        "database_prod": "connected" if db_prod_ok else "disconnected",
        "database_ops": "connected" if db_ops_ok else "disconnected",
        "environment": settings.app_env,
    }
