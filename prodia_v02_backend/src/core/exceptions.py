"""Exception handlers globales — JSON estructurado con correlation_id.

Copiado literal de Robustez V02 (L1). Nota de diseño heredada: NO define una
jerarquía de excepciones de dominio — la estabilidad viene de la FORMA
uniforme del JSON, no de una jerarquía de tipos. Los tres handlers normalizan
lo que ya lanza FastAPI/Starlette.

Corrección C12 sobre el original: se añade un campo `code` simbólico opcional
para permitir que features futuras (F1+) lancen excepciones de dominio con un
código estable (p.ej. "NOT_FOUND") sin tener que inventar la infraestructura
de error en ese momento — el contrato del JSON ya lo admite desde F0.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from src.core.logger import get_logger

logger = get_logger("exceptions")


def _get_correlation_id() -> str | None:
    """Extrae correlation_id del contexto structlog."""
    ctx: dict[str, Any] = structlog.contextvars.get_contextvars()
    return ctx.get("correlation_id")


def _error_response(
    status: int, detail: str, errors: Any = None, code: str | None = None
) -> JSONResponse:
    body: dict[str, Any] = {
        "status": status,
        "detail": detail,
        "correlation_id": _get_correlation_id(),
    }
    if code is not None:
        body["code"] = code
    if errors is not None:
        body["errors"] = errors
    return JSONResponse(status_code=status, content=body)


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    logger.warning(
        "http_exception",
        status=exc.status_code,
        detail=exc.detail,
        path=request.url.path,
    )
    return _error_response(exc.status_code, str(exc.detail))


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    logger.warning(
        "validation_error",
        path=request.url.path,
        errors=exc.errors(),
    )
    return _error_response(422, "Error de validación", errors=exc.errors())


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # El 500 NUNCA filtra el mensaje interno al cliente — el detalle real va
    # al log con exc_type; el cliente solo recibe el correlation_id para
    # que el usuario lo reporte y se busque en logs.
    logger.exception(
        "unhandled_exception",
        path=request.url.path,
        exc_type=type(exc).__name__,
    )
    return _error_response(500, "Error interno del servidor")


def register_exception_handlers(app: FastAPI) -> None:
    """Registra todos los exception handlers en la app FastAPI."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
