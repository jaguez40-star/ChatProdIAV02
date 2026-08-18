"""Schemas Pydantic — request/response para auth y permisos. Copiado literal
de Robustez V02 (L1-L11), con `docstring`/`examples` adaptados a ProdIA."""

from __future__ import annotations

from pydantic import BaseModel, Field

# ── Request ─────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    username: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Usuario de red sin dominio (ej: jguerrero, no jguerrero@ecopetrol.com.co)",
        examples=["jguerrero"],
    )
    password: str = Field(
        ...,
        min_length=1,
        description="Contraseña de directorio activo corporativo",
        examples=["••••••••"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {"username": "jguerrero", "password": "mi_clave_ad"}
        }
    }


# ── Response ────────────────────────────────────────────────────────────────


class LoginResponse(BaseModel):
    access_token: str = Field(
        description="Token de sesión firmado (itsdangerous). Se envía además como cookie HttpOnly `prodia_session`.",
        examples=["InVzZXJfaWQiOiAxfQ.ZkV4Sg.abc123"],
    )
    token_type: str = Field(
        default="bearer", description="Tipo de token", examples=["bearer"]
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "access_token": "InVzZXJfaWQiOiAxfQ.ZkV4Sg.abc123",
                "token_type": "bearer",
            }
        }
    }


class PermissionGroupOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    is_admin: bool

    model_config = {"from_attributes": True}


class CampoPermissionOut(BaseModel):
    campo: str

    model_config = {"from_attributes": True}


class SectionPermissionOut(BaseModel):
    section_id: str

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    """Representación pública de un usuario (sin datos sensibles)."""

    id: int = Field(description="ID interno del usuario", examples=[1])
    username: str = Field(
        description="Usuario de red (sin dominio)", examples=["jguerrero"]
    )
    email: str = Field(
        description="Correo corporativo", examples=["jguerrero@ecopetrol.com.co"]
    )
    full_name: str | None = Field(
        default=None, description="Nombre completo", examples=["Javier Guerrero"]
    )
    is_admin: bool = Field(description="Tiene privilegios de administrador")
    is_active: bool = Field(description="Cuenta habilitada en la aplicación")
    group: PermissionGroupOut | None = Field(
        default=None, description="Grupo de permisos asignado"
    )
    last_login_at: str | None = Field(
        default=None,
        description="Último login exitoso (ISO UTC)",
        examples=["2026-05-06T14:30:00Z"],
    )
    created_at: str = Field(
        description="Fecha de creación (ISO UTC)", examples=["2026-01-15T08:00:00Z"]
    )
    updated_at: str = Field(
        description="Última modificación (ISO UTC)", examples=["2026-05-06T14:30:00Z"]
    )

    model_config = {"from_attributes": True}


class UserPermissionsOut(BaseModel):
    """Permisos consolidados de un usuario (grupo + individuales)."""

    campos: list[str] = Field(default_factory=list, description="Campos autorizados")
    sections: list[str] = Field(
        default_factory=list, description="Secciones autorizadas"
    )


class LogoutResponse(BaseModel):
    """Respuesta de POST /auth/logout."""

    message: str = Field(
        description="Confirmación de cierre de sesión", examples=["Sesión cerrada"]
    )

    model_config = {"json_schema_extra": {"example": {"message": "Sesión cerrada"}}}


class MeResponse(BaseModel):
    """Respuesta de GET /auth/me — usuario actual + permisos."""

    user: UserOut = Field(description="Datos del usuario autenticado")
    permissions: UserPermissionsOut = Field(
        description="Permisos efectivos (grupo + individuales)"
    )


class SessionTimeoutOut(BaseModel):
    """Respuesta de GET /auth/session-timeout — solo el valor vigente.

    De solo lectura para cualquier usuario autenticado; la necesita el modal
    de inactividad del frontend para saber cuánto esperar antes de avisar.
    """

    session_timeout_minutes: int = Field(
        description="Minutos de inactividad antes de que la sesión expire",
        examples=[30],
    )
