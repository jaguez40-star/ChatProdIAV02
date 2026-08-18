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


def require_admin(request: Request) -> None:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="No autenticado")
    if user.is_admin:
        return
    if user.group is not None and user.group.is_admin:
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
    user = getattr(request.state, "user", None)
    if user is None:
        return []
    if user.is_admin:
        return None
    if user.group is not None and user.group.is_admin:
        return None
    return PermissionService(auth_db).get_effective_campos(user.id, user.group_id)
