"""Auth middleware — cookie firmada + sliding refresh + headers.

Copiado de Robustez V02 (L1-L11), con tres cambios: nombre de cookie
(`prodia_session`, no `robustez_session`); `PUBLIC_PATHS` reducido a lo que
F0 expone (N5, deny-by-default — solo `login` y `health` públicos; Robustez
V02 también exime sus rutas de KPIs de mercado, que ProdIA no tiene); y
corrección N6 — los 401 que este middleware construye ahora incluyen
`correlation_id` en el BODY, no solo en el header `x-correlation-id`. En el
original, `CorrelationIdMiddleware` añade el header a cualquier respuesta
(porque envuelve a AuthMiddleware), pero el JSON del body lo arma cada
JSONResponse por su cuenta sin pasar por `core/exceptions.py::_error_response`
— quedaba inconsistente con los errores de los routers, que sí lo llevan.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from itsdangerous import SignatureExpired
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.core.config import get_settings
from src.core.logger import get_logger
from src.features.auth.services import AuthService
from src.shared.app_settings import get_session_timeout_minutes
from src.shared.db_auth import SessionLocal

logger = get_logger("middleware.auth")


def _correlation_id() -> str | None:
    ctx: dict[str, Any] = structlog.contextvars.get_contextvars()
    return ctx.get("correlation_id")


def _unauth_response(detail: str, *, session_expired: bool = False) -> JSONResponse:
    """401 con el mismo contrato que core/exceptions.py::_error_response (N6):
    {status, detail, correlation_id}. CorrelationIdMiddleware ya bindeó el id
    al contexto structlog antes de que este middleware corra (se añade último
    en main.py = se ejecuta primero), así que está disponible aquí."""
    resp = JSONResponse(
        status_code=401,
        content={"status": 401, "detail": detail, "correlation_id": _correlation_id()},
    )
    if session_expired:
        resp.headers["X-Session-Expired"] = "true"
    return resp


SESSION_COOKIE_NAME = "prodia_session"

# N5 — deny-by-default: solo login/health/docs públicos. Todo lo demás exige
# cookie de sesión válida. Robustez V02 también exime sus rutas de KPIs de
# mercado (públicas en su dominio); ProdIA no tiene endpoints públicos de
# datos en F0 — F2+ añadirá aquí lo que decida exponer sin auth, si acaso.
PUBLIC_PATHS: set[str] = {
    "/api/v1/auth/login",
    "/api/v1/health",
    "/docs",
    "/redoc",
    "/openapi.json",
}

PUBLIC_PREFIXES: tuple[str, ...] = (
    "/docs",
    "/redoc",
)


def _es_recurso_del_frontend(path: str) -> bool:
    """¿Es una petición del navegador al frontend, y no a la API?

    Se decide por exclusión —todo lo que NO cuelga de `/api/`— y solo cuando
    el backend sirve los estáticos. Definirlo al revés (lista de extensiones
    conocidas) fallaría con cada tipo de fichero nuevo que Vite emitiera, y el
    síntoma sería un 401 en un recurso suelto: difícil de diagnosticar.
    """
    return get_settings().serve_static and not path.startswith("/api/")


class AuthMiddleware(BaseHTTPMiddleware):
    """Verifica cookie firmada. Inyecta user en request.state. Hace sliding refresh."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        path = request.url.path

        if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
            return await call_next(request)

        # F6/B-4 — el frontend compilado es público, y tiene que serlo.
        #
        # 🔑 Sin esto, servir el `dist/` desde el backend deja la app
        # INARRANCABLE: un usuario sin sesión pide `/` y recibe un 401 en vez
        # de la pantalla de login, así que no tiene forma de autenticarse. Ni
        # siquiera cargarían el HTML ni el CSS de esa pantalla.
        #
        # No abre ningún agujero: los ficheros son los mismos que hoy sirve
        # Vite sin pasar por el backend. Deny-by-default sigue intacto donde
        # importa — TODO `/api/v1/*` no listado arriba exige cookie válida, y
        # esa es la frontera que protege los datos.
        if _es_recurso_del_frontend(path):
            return await call_next(request)

        token = request.cookies.get(SESSION_COOKIE_NAME)
        if not token:
            # Si no hay cookie en una ruta protegida, la sesión expiró y el
            # navegador purgó la cookie (max_age vencido). Sin X-Session-Expired
            # el frontend no detecta el vencimiento y el usuario se queda viendo
            # "Error cargando datos" sin aviso.
            return _unauth_response(
                "No autenticado — cookie ausente", session_expired=True
            )

        settings = get_settings()
        db = SessionLocal()
        try:
            service = AuthService(db)

            # Detectar expiración explícita para emitir header al frontend
            try:
                user_id = service.validate_session_token(token)
            except SignatureExpired:
                return _unauth_response("Sesión expirada", session_expired=True)

            if user_id is None:
                return _unauth_response("Sesión inválida")

            from src.features.auth.repositories import UserRepository

            repo = UserRepository(db)
            user = repo.get_by_id(user_id)
            if user is None or not user.is_active:
                return _unauth_response("Usuario no encontrado o desactivado")

            request.state.user = user
            # El `is_admin` del GRUPO se resuelve aquí, con la sesión todavía
            # viva, por la misma razón que `timeout_min`: `user.group` es una
            # relación perezosa y el `finally` de abajo cierra la sesión. Un
            # guard que la navegara después obtendría `DetachedInstanceError`,
            # que el manejador global convierte en un 503 — y un administrador
            # legítimo vería "base de datos no disponible" en vez de entrar.
            # El criterio admin se resuelve AQUÍ, con la sesión viva, y viaja
            # como un bool en `request.state`.
            #
            # No es una optimización: es la única forma de que funcione. El
            # `finally` de abajo cierra la sesión, y cualquier commit posterior
            # EXPIRA los atributos del objeto. A partir de ahí, leer `is_admin`
            # —una columna corriente— dispara un refresco contra una sesión
            # muerta y levanta `DetachedInstanceError`, que el manejador global
            # traduce a un 503: un administrador legítimo vería "base de datos
            # no disponible" en vez de entrar.
            #
            # Se guardan valores planos, no el `User`, porque un int y un bool
            # no caducan. `get_allowed_campos` usa los identificadores.
            request.state.es_admin = bool(
                user.is_admin or (user.group is not None and user.group.is_admin)
            )
            request.state.user_id = int(user.id)
            request.state.group_id = user.group_id
            # Se lee ACÁ, no más abajo: el finally cierra la sesión y el
            # sliding refresh que necesita este valor corre después del
            # call_next.
            timeout_min = get_session_timeout_minutes(db)
        finally:
            db.close()

        response = await call_next(request)

        # ── Sliding refresh ──────────────────────────────────────────────
        # Renovar cookie si el token tiene <50% de vida restante
        settings = get_settings()
        max_age_sec = timeout_min * 60
        remaining = _token_remaining_seconds(token, settings.secret_key, max_age_sec)

        if remaining is not None and remaining < max_age_sec / 2:
            new_token = service.create_session_token(user_id)
            response.set_cookie(
                key=SESSION_COOKIE_NAME,
                value=new_token,
                httponly=True,
                samesite="lax",
                secure=not settings.is_dev,
                max_age=max_age_sec,
                path="/",
            )
            logger.debug("session_cookie_refreshed", user_id=user_id)

        # ── X-Session-Expires header ─────────────────────────────────────
        # Informa al frontend cuándo expira la sesión actual
        if remaining is not None:
            expires_at = datetime.now(timezone.utc).timestamp() + remaining
            response.headers["X-Session-Expires"] = datetime.fromtimestamp(
                expires_at, tz=timezone.utc
            ).isoformat()

        return response


def _token_remaining_seconds(
    token: str, secret_key: str, max_age_sec: int
) -> int | None:
    """Retorna segundos restantes del token. None si no se puede determinar."""
    from itsdangerous import BadSignature, URLSafeTimedSerializer

    serializer = URLSafeTimedSerializer(secret_key)
    try:
        import time

        from itsdangerous import SignatureExpired as SE  # noqa: N817

        # Forzar expiración con max_age=0 para obtener date_signed del token
        try:
            serializer.loads(token, max_age=0)
            # Si no lanzó, el token es válido — casi sin tiempo transcurrido
            return max_age_sec
        except SE as exc:
            if exc.date_signed is not None:
                elapsed = int(time.time() - exc.date_signed.timestamp())
                return max(0, max_age_sec - elapsed)
            return None
    except BadSignature:
        return None
