"""Tests de shared/auth_guards.py — require_admin y get_allowed_campos (C6).

Se apoyan en que el middleware ya garantizó autenticación y dejó su resultado en
`request.state`; aquí se simula ese estado con un `SimpleNamespace`.

⚠️ **El doble replica lo que el middleware deja, no el modelo `User`.** Desde F5,
el criterio admin y los identificadores viajan como valores planos
(`es_admin`, `user_id`, `group_id`) en vez de leerse del objeto ORM. La razón
está en `_es_admin`: el middleware cierra su sesión antes de que corran los
guards, y cualquier commit posterior expira los atributos del `User` — leer
`user.is_admin` desde aquí levantaría `DetachedInstanceError`, que el manejador
global traduce a un 503. Un doble que expusiera `is_admin`/`group` daría verde
mientras producción devuelve "base de datos no disponible" a un administrador.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from src.shared.auth_guards import get_allowed_campos, require_admin


def _fake_request(
    user: Any,
    *,
    es_admin: bool = False,
    user_id: int | None = 1,
    group_id: int | None = None,
) -> SimpleNamespace:
    """Reproduce el `request.state` que deja `AuthMiddleware`."""
    estado = SimpleNamespace(user=user)
    if user is not None:
        estado.es_admin = es_admin
        estado.user_id = user_id
        estado.group_id = group_id
    return SimpleNamespace(state=estado)


@pytest.mark.unit
def test_require_admin_admin_directo() -> None:
    require_admin(_fake_request(SimpleNamespace(), es_admin=True))  # no debe lanzar


@pytest.mark.unit
def test_require_admin_admin_por_grupo() -> None:
    """El middleware resuelve el criterio ADITIVO (propio o por grupo) y deja el
    resultado ya combinado: para el guard, ambos casos son el mismo booleano."""
    require_admin(_fake_request(SimpleNamespace(), es_admin=True))


@pytest.mark.unit
def test_require_admin_sin_privilegios() -> None:
    with pytest.raises(HTTPException) as exc_info:
        require_admin(_fake_request(SimpleNamespace(), es_admin=False))
    assert exc_info.value.status_code == 403


@pytest.mark.unit
def test_require_admin_sin_autenticar() -> None:
    with pytest.raises(HTTPException) as exc_info:
        require_admin(_fake_request(None))
    assert exc_info.value.status_code == 401


@pytest.mark.unit
def test_require_admin_sin_el_flag_del_middleware_niega_el_paso() -> None:
    """Fallar CERRADO es la única opción defendible: si el flag no está —porque
    alguien tocó el middleware— lo seguro es negar, no conceder."""
    request = SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace()))

    with pytest.raises(HTTPException) as exc_info:
        require_admin(request)
    assert exc_info.value.status_code == 403


@pytest.mark.unit
def test_require_admin_no_toca_el_objeto_usuario() -> None:
    """La regresión que este archivo existe para vigilar.

    Si el guard volviera a leer `user.is_admin` o `user.group`, en producción
    tocaría un objeto ORM con la sesión ya cerrada. Aquí el doble explota al
    primer acceso, así que el test falla en vez de dejar pasar el defecto.
    """

    class UsuarioQueNoSeDejaTocar:
        def __getattr__(self, nombre: str) -> Any:
            raise AssertionError(
                f"el guard leyó `user.{nombre}` — en producción eso sería "
                "DetachedInstanceError y un 503 para un administrador"
            )

    require_admin(_fake_request(UsuarioQueNoSeDejaTocar(), es_admin=True))


@pytest.mark.unit
def test_get_allowed_campos_admin_devuelve_none() -> None:
    request = _fake_request(SimpleNamespace(), es_admin=True)
    assert get_allowed_campos(request, auth_db=None) is None  # type: ignore[arg-type]


@pytest.mark.unit
def test_get_allowed_campos_sin_autenticar_devuelve_lista_vacia() -> None:
    assert get_allowed_campos(_fake_request(None), auth_db=None) == []  # type: ignore[arg-type]


@pytest.mark.unit
def test_get_allowed_campos_sin_identificador_no_consulta_la_bd() -> None:
    """`auth_db=None` haría estallar cualquier consulta: si este test pasa, es
    que el guard cortó antes de intentarla."""
    request = _fake_request(SimpleNamespace(), es_admin=False, user_id=None)

    assert get_allowed_campos(request, auth_db=None) == []  # type: ignore[arg-type]
