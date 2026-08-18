"""Logger structlog — JSON estructurado, UTC, con correlation_id automático.

Copiado literal de Robustez V02 (L1): `merge_contextvars` es el procesador que
inyecta correlation_id en cada línea de log sin pasarlo por parámetro — lo
bindea CorrelationIdMiddleware una vez por request y de ahí en adelante viaja
solo. `ensure_ascii=False` preserva acentos en español.
"""

from __future__ import annotations

import logging
import sys

import structlog


def setup_logging(*, json_output: bool = True) -> None:
    """Configura structlog para toda la aplicación.

    Args:
        json_output: True para JSON (producción), False para consola coloreada (dev).
    """
    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_output:
        processors.append(structlog.processors.JSONRenderer(ensure_ascii=False))
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Obtiene un logger con contexto bound."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
