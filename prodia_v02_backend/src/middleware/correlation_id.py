"""Middleware de correlation_id — UUID por request. Copiado literal (L1).

Acepta el header entrante (trazabilidad cross-service), si no lo genera, lo
bindea al contexto structlog (todos los logs del request lo heredan vía
merge_contextvars), y lo devuelve en la respuesta — el usuario reporta un ID
y se busca en logs. `clear_contextvars()` evita fugas entre requests que
reusan el mismo task.
"""

from __future__ import annotations

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

CORRELATION_ID_HEADER = "x-correlation-id"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Genera o propaga correlation_id por request."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        correlation_id = request.headers.get(CORRELATION_ID_HEADER) or str(uuid.uuid4())

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        response = await call_next(request)
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response
