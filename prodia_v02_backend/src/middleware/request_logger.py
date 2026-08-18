"""Middleware request logger — método, ruta, status, latencia. Copiado literal (L1).

Una sola línea `request_completed` por request (no entrada+salida duplicadas),
con `perf_counter` (monotónico, no afectado por ajustes del reloj del sistema).
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.core.logger import get_logger

logger = get_logger("request")


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    """Loguea cada request con latencia en ms."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)

        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            latency_ms=latency_ms,
        )
        return response
