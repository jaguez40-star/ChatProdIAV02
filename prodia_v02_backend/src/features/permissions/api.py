"""Router permissions — permisos del usuario autenticado. Copiado literal de
Robustez V02 (L1-L11). Montado bajo /api/v1 por main.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.features.auth.schemas import UserPermissionsOut
from src.features.permissions.services import PermissionService
from src.shared.db_auth import get_db

router = APIRouter(prefix="/permissions", tags=["Permissions"])


@router.get(
    "/my-permissions",
    response_model=UserPermissionsOut,
    summary="Mis permisos",
    description="Retorna campos y secciones autorizadas del usuario autenticado.",
    responses={401: {"description": "No autenticado"}},
)
async def my_permissions(
    request: Request,
    db: Session = Depends(get_db),
) -> UserPermissionsOut:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="No autenticado")

    perm_service = PermissionService(db)
    campos = perm_service.get_effective_campos(user.id, user.group_id)
    sections = perm_service.get_effective_sections(user.id, user.group_id)

    return UserPermissionsOut(campos=campos, sections=sections)
