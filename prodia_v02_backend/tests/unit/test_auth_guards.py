"""Tests de shared/auth_guards.py — require_admin y get_allowed_campos (C6).

Se apoyan en que el middleware ya garantizó autenticación e inyectó
request.state.user; aquí se simula ese estado con un SimpleNamespace.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from src.shared.auth_guards import get_allowed_campos, require_admin


def _fake_request(user: Any) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(user=user))


@pytest.mark.unit
def test_require_admin_usuario_admin_directo() -> None:
    user = SimpleNamespace(is_admin=1, group=None)
    require_admin(_fake_request(user))  # no debe lanzar


@pytest.mark.unit
def test_require_admin_admin_por_grupo() -> None:
    user = SimpleNamespace(is_admin=0, group=SimpleNamespace(is_admin=1))
    require_admin(_fake_request(user))  # no debe lanzar


@pytest.mark.unit
def test_require_admin_sin_privilegios() -> None:
    user = SimpleNamespace(is_admin=0, group=SimpleNamespace(is_admin=0))
    with pytest.raises(HTTPException) as exc_info:
        require_admin(_fake_request(user))
    assert exc_info.value.status_code == 403


@pytest.mark.unit
def test_require_admin_sin_autenticar() -> None:
    with pytest.raises(HTTPException) as exc_info:
        require_admin(_fake_request(None))
    assert exc_info.value.status_code == 401


@pytest.mark.unit
def test_get_allowed_campos_admin_devuelve_none() -> None:
    user = SimpleNamespace(is_admin=1, group=None, id=1, group_id=None)
    result = get_allowed_campos(_fake_request(user), auth_db=None)  # type: ignore[arg-type]
    assert result is None


@pytest.mark.unit
def test_get_allowed_campos_admin_por_grupo_devuelve_none() -> None:
    user = SimpleNamespace(
        is_admin=0, group=SimpleNamespace(is_admin=1), id=1, group_id=1
    )
    result = get_allowed_campos(_fake_request(user), auth_db=None)  # type: ignore[arg-type]
    assert result is None


@pytest.mark.unit
def test_get_allowed_campos_sin_autenticar_devuelve_lista_vacia() -> None:
    result = get_allowed_campos(_fake_request(None), auth_db=None)  # type: ignore[arg-type]
    assert result == []
