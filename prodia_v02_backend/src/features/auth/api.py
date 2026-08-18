"""Router auth — login, logout, me, session-timeout. Copiado literal de
Robustez V02 (L1-L11), adaptado a la cookie `prodia_session` y al engine
`db_auth` de este proyecto."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.core.logger import get_logger
from src.features.auth.schemas import (
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    MeResponse,
    SessionTimeoutOut,
    UserOut,
    UserPermissionsOut,
)
from src.features.auth.services import AuthService, LDAPError
from src.features.permissions.services import PermissionService
from src.middleware.auth import SESSION_COOKIE_NAME
from src.shared.app_settings import get_session_timeout_minutes
from src.shared.db_auth import get_db

logger = get_logger("auth.api")

router = APIRouter(prefix="/auth", tags=["Auth"])


def _get_correlation_id() -> str | None:
    ctx: dict[str, Any] = structlog.contextvars.get_contextvars()
    return ctx.get("correlation_id")


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Login LDAP corporativo",
    description=(
        "Autentica usuario contra Active Directory (`red.ecopetrol.com.co`). "
        "En caso de éxito establece cookie `prodia_session` (HttpOnly, SameSite=Lax) "
        "y registra evento `login` en `auth_events`. "
        "El token también se devuelve en el cuerpo para clientes sin soporte de cookies."
    ),
    responses={
        401: {
            "description": "Credenciales inválidas, usuario inactivo o no registrado en `app_users`"
        },
        503: {"description": "Servidor LDAP no disponible o timeout de conexión"},
        500: {"description": "Error interno del servidor"},
    },
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    settings = get_settings()
    service = AuthService(db)

    try:
        user = service.authenticate_ldap(
            body.username,
            body.password,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            correlation_id=_get_correlation_id(),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except LDAPError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    token = service.create_session_token(user.id)

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=not settings.is_dev,
        max_age=get_session_timeout_minutes(db) * 60,
        path="/",
    )

    return LoginResponse(access_token=token, token_type="bearer")


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Cerrar sesión",
    description=(
        "Elimina la cookie `prodia_session` del cliente y registra evento `logout` "
        "en `auth_events`. Requiere cookie de sesión válida."
    ),
    responses={
        401: {"description": "No autenticado — cookie ausente o inválida"},
        500: {"description": "Error interno del servidor"},
    },
)
async def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LogoutResponse:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="No autenticado")

    settings = get_settings()
    service = AuthService(db)
    service.logout(
        user.username,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        correlation_id=_get_correlation_id(),
    )

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=not settings.is_dev,
    )

    return LogoutResponse(message="Sesión cerrada")


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Sesión actual",
    description=(
        "Retorna el usuario autenticado y sus permisos efectivos (campos + secciones). "
        "Los permisos son la unión de los del grupo más los individuales. "
        "El header `X-Session-Expires` indica cuándo expira la sesión (ISO UTC)."
    ),
    responses={
        401: {
            "description": "No autenticado — cookie ausente, inválida o sesión expirada"
        },
        500: {"description": "Error interno del servidor"},
    },
)
async def me(
    request: Request,
    db: Session = Depends(get_db),
) -> MeResponse:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="No autenticado")

    perm_service = PermissionService(db)
    campos = perm_service.get_effective_campos(user.id, user.group_id)
    sections = perm_service.get_effective_sections(user.id, user.group_id)

    return MeResponse(
        user=UserOut.model_validate(user),
        permissions=UserPermissionsOut(campos=campos, sections=sections),
    )


@router.get(
    "/session-timeout",
    response_model=SessionTimeoutOut,
    summary="Timeout de sesión vigente (solo lectura)",
    description=(
        "Minutos de inactividad antes de que la sesión expire. Requiere sesión "
        "válida — lo consume el modal de inactividad del frontend. "
        "Editar el valor queda para el panel de administración (fuera de F0)."
    ),
    responses={
        401: {
            "description": "No autenticado — cookie ausente, inválida o sesión expirada"
        }
    },
)
async def session_timeout(
    request: Request,
    db: Session = Depends(get_db),
) -> SessionTimeoutOut:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="No autenticado")

    return SessionTimeoutOut(session_timeout_minutes=get_session_timeout_minutes(db))
