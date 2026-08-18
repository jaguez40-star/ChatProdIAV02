"""Configuración del sistema editable en caliente (tabla app_settings).

Copiado literal de Robustez V02 (L1-L11). Por qué existe: los valores de
.env los carga `get_settings()`, decorado con `@lru_cache(maxsize=1)`, así
que cambiarlos exige reiniciar el backend. Los ajustes que un administrador
debe poder tocar desde un panel (F1+) viven aquí.

El timeout se consulta en CADA petición autenticada (middleware y
validate_session_token), de ahí el cache con TTL. Solo se cachea el valor
que viene de la BD: si no hay fila o la consulta falla, se usa el de .env
y NO se cachea, para que un fallo puntual no quede congelado 30 segundos.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy import Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from src.core.config import get_settings
from src.core.logger import get_logger
from src.shared.db_auth import Base

logger = get_logger("app_settings")

SESSION_TIMEOUT_KEY = "session_timeout_minutes"

# Guardrails: por debajo de 5 min la app es inusable; por encima de 240 una
# sesión robada sobrevive demasiado. Se validan en el servicio, no solo en la UI.
SESSION_TIMEOUT_MIN = 5
SESSION_TIMEOUT_MAX = 240

_CACHE_TTL_SEC = 30.0


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="(datetime('now'))"
    )
    updated_by: Mapped[str | None] = mapped_column(Text, nullable=True)


# (valor, momento en que se cacheó). Vacío = nada cacheado.
_cache: dict[str, tuple[int, float]] = {}


def _utcnow_str() -> str:
    """Timestamp UTC 'YYYY-MM-DD HH:MM:SS' (paridad con el server_default SQLite)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def invalidate_cache() -> None:
    """Borra el cache. La usan el endpoint de escritura y los tests."""
    _cache.clear()


def _rollback_silencioso(db: Session) -> None:
    """Deja la sesión usable tras un fallo de lectura. Nunca propaga.

    SQLAlchemy 2.0 marca la sesión como inactiva cuando una consulta falla
    dentro de una transacción implícita: sin este rollback, la siguiente
    operación sobre la misma sesión lanza PendingRollbackError en vez del
    error original, y se pierde el rastro de la causa real.
    """
    try:
        db.rollback()
    except Exception:  # la sesión ya estaba rota; no hay nada que salvar
        pass


def get_session_timeout_minutes(db: Session) -> int:
    """Minutos de inactividad antes de cerrar la sesión.

    Orden: cache -> tabla app_settings -> valor de .env (fallback). El
    fallback preserva el comportamiento previo a esta tabla si algo falla,
    y este código corre en el camino crítico de autenticación: nunca debe
    lanzar.
    """
    cached = _cache.get(SESSION_TIMEOUT_KEY)
    if cached is not None and (time.monotonic() - cached[1]) < _CACHE_TTL_SEC:
        return cached[0]

    try:
        raw = db.execute(
            select(AppSetting.value).where(AppSetting.key == SESSION_TIMEOUT_KEY)
        ).scalar_one_or_none()
    except Exception as exc:  # tabla ausente, BD bloqueada, lo que sea
        logger.warning("app_settings_read_failed", detalle=str(exc))
        _rollback_silencioso(db)
        return get_settings().session_timeout_minutes

    if raw is None:
        # Sin fila configurada: manda el .env. No se cachea (ver docstring).
        return get_settings().session_timeout_minutes

    try:
        minutos = int(raw)
    except ValueError:
        logger.warning("app_settings_valor_invalido", key=SESSION_TIMEOUT_KEY, raw=raw)
        return get_settings().session_timeout_minutes

    _cache[SESSION_TIMEOUT_KEY] = (minutos, time.monotonic())
    return minutos


def set_session_timeout_minutes(
    db: Session, minutos: int, updated_by: str | None
) -> int:
    """Guarda el timeout y devuelve el valor aplicado. Hace commit e invalida el cache.

    Lanza ValueError si está fuera del rango permitido: el router lo traduce
    a HTTP 400. Validar aquí y no solo en la UI es deliberado — la UI se
    puede saltar llamando al endpoint directo.
    """
    if minutos < SESSION_TIMEOUT_MIN or minutos > SESSION_TIMEOUT_MAX:
        raise ValueError(
            f"El timeout debe estar entre {SESSION_TIMEOUT_MIN} y "
            f"{SESSION_TIMEOUT_MAX} minutos (recibido: {minutos})"
        )

    # A diferencia de las lecturas, un fallo de BD aquí NO se degrada: el
    # admin pidió guardar y debe enterarse de que no se guardó.
    try:
        fila = db.get(AppSetting, SESSION_TIMEOUT_KEY)
        if fila is None:
            db.add(
                AppSetting(
                    key=SESSION_TIMEOUT_KEY,
                    value=str(minutos),
                    updated_at=_utcnow_str(),
                    updated_by=updated_by,
                )
            )
        else:
            fila.value = str(minutos)
            fila.updated_at = _utcnow_str()
            fila.updated_by = updated_by

        db.commit()
    except Exception:
        _rollback_silencioso(db)
        raise

    invalidate_cache()
    logger.info("session_timeout_actualizado", minutos=minutos, por=updated_by)
    return minutos


def get_session_timeout_meta(db: Session) -> tuple[int, str | None, str | None]:
    """(minutos, updated_at, updated_by) para mostrarlo en un panel de admin.

    Distinto de get_session_timeout_minutes: no usa cache y devuelve el
    rastro de quién lo cambió. Degrada igual: si la tabla no existe o la
    BD falla, devuelve el valor de .env en vez de tumbar la pestaña con 500.
    """
    try:
        fila = db.get(AppSetting, SESSION_TIMEOUT_KEY)
    except Exception as exc:
        logger.warning("app_settings_meta_read_failed", detalle=str(exc))
        _rollback_silencioso(db)
        return get_settings().session_timeout_minutes, None, None

    if fila is None:
        return get_settings().session_timeout_minutes, None, None
    try:
        minutos = int(fila.value)
    except ValueError:
        minutos = get_settings().session_timeout_minutes
    return minutos, fila.updated_at, fila.updated_by
