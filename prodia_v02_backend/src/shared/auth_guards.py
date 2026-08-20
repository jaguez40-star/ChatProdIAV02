"""Guards de FastAPI para proteger rutas — se apoyan en que AuthMiddleware ya
garantizó autenticación e inyectó `request.state.user` (deny-by-default, N5).

`require_admin` es copia literal de Robustez V02 (L1-L11).

Corrección C6: Robustez V02 duplica el criterio "admin = is_admin OR
group.is_admin" en `_get_allowed_campos` dentro de CADA feature que filtra
por campo (kpis_produccion/api.py, ebitda_rank/api.py, …) — su propio
docstring admite que es "el mismo criterio" copiado. Aquí vive una sola vez:
`get_allowed_campos` es la dependencia que F2+ debe inyectar en vez de
reescribir el patrón.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.features.permissions.services import PermissionService
from src.shared.db_auth import get_db


def _es_admin(request: Request) -> bool:
    """Criterio aditivo de L10 (admin propio **o** por grupo), ya resuelto.

    ⚠️ **Aquí NO se puede tocar `request.state.user`.** `AuthMiddleware` lo deja
    ahí y acto seguido cierra su sesión; además, cualquier commit posterior
    EXPIRA los atributos del objeto. A partir de entonces, leer siquiera
    `user.is_admin` —una columna corriente— dispara un refresco contra una
    sesión muerta y levanta `DetachedInstanceError`, que el manejador global
    traduce a **503**: un administrador legítimo vería "base de datos no
    disponible" en vez de entrar.

    No se había visto nunca porque hasta F5 **ningún endpoint usaba estos
    guards**: `require_admin` existe desde F0 y jamás se había ejercitado.

    Por eso el middleware calcula el criterio con la sesión viva y deja un bool
    en `request.state.es_admin`. Un bool no caduca.
    """
    return bool(getattr(request.state, "es_admin", False))


def require_admin(request: Request) -> None:
    """Deja pasar solo a administradores. 403 explícito, nunca una lista vacía.

    Sin `Depends(get_db)` a propósito: abrir una sesión nueva aquí añadiría una
    conexión por petición para releer un booleano que el middleware ya calculó.
    """
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="No autenticado")
    if _es_admin(request):
        return
    raise HTTPException(status_code=403, detail="Requiere privilegios de administrador")


def get_allowed_campos(
    request: Request, auth_db: Session = Depends(get_db)
) -> list[str] | None:
    """None = admin (sin restricción). list[str] = campos permitidos.

    Dependencia única (C6) para que las features de F2+ (analisis, ebitda,
    ingesta) filtren sus queries por `WHERE campo = ANY(:allowed_campos)`
    sin reimplementar el criterio admin en cada api.py.
    """
    if getattr(request.state, "user", None) is None:
        return []
    if _es_admin(request):
        return None

    # Igual que `_es_admin`: los identificadores se toman de `request.state`,
    # donde el middleware los dejó como enteros, y NUNCA del objeto `User` —
    # sus atributos pueden estar expirados (ver el aviso de `_es_admin`).
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        return []
    group_id = getattr(request.state, "group_id", None)
    return PermissionService(auth_db).get_effective_campos(int(user_id), group_id)
