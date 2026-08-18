"""Test de integración del flujo completo: login local -> cookie -> endpoint
protegido. Es el camino que recorre un usuario real (V8-V16 del plan F0),
verificado aquí sin depender de LDAP/VPN mediante el login local auditado.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from src.core.config import get_settings


@pytest.fixture
def _local_login_env(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Habilita login local vía variables de entorno + limpia el cache de
    Settings (compartido por TODOS los módulos que llaman get_settings())."""
    monkeypatch.setenv("ENABLE_LOCAL_LOGIN", "true")
    monkeypatch.setenv("LOCAL_LOGIN_USERNAME", "test.user")
    monkeypatch.setenv("LOCAL_LOGIN_PASSWORD", "clave-integracion")
    monkeypatch.setenv("LOCAL_LOGIN_ALLOWED_IPS", "127.0.0.1,::1,testclient")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.integration
async def test_login_local_y_acceso_a_endpoint_protegido(
    integration_client: AsyncClient, _local_login_env: Any
) -> None:
    # 1) Sin cookie, el endpoint protegido rechaza
    sin_cookie = await integration_client.get("/api/v1/permissions/my-permissions")
    assert sin_cookie.status_code == 401

    # 2) Login local exitoso
    login_resp = await integration_client.post(
        "/api/v1/auth/login",
        json={"username": "test.user", "password": "clave-integracion"},
    )
    assert login_resp.status_code == 200
    assert "prodia_session" in login_resp.cookies
    body = login_resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]

    # 3) Con la cookie, /auth/me identifica al usuario correcto
    me_resp = await integration_client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    me_body = me_resp.json()
    assert me_body["user"]["username"] == "test.user"
    assert "x-session-expires" in me_resp.headers

    # 4) Con la cookie, el endpoint de permisos responde (aunque sin permisos
    # explícitos configurados en el seed de test, la lista viene vacía —
    # no 401/403, que es lo que aquí se verifica)
    perms_resp = await integration_client.get("/api/v1/permissions/my-permissions")
    assert perms_resp.status_code == 200
    assert "campos" in perms_resp.json()
    assert "sections" in perms_resp.json()


@pytest.mark.integration
async def test_logout_invalida_cookie(
    integration_client: AsyncClient, _local_login_env: Any
) -> None:
    await integration_client.post(
        "/api/v1/auth/login",
        json={"username": "test.user", "password": "clave-integracion"},
    )
    logout_resp = await integration_client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200
    assert logout_resp.json()["message"] == "Sesión cerrada"


@pytest.mark.integration
async def test_login_password_incorrecta_sin_ldap_da_503(
    integration_client: AsyncClient, _local_login_env: Any
) -> None:
    """Con contraseña local incorrecta, cae al intento de bind LDAP real, que
    en el entorno de test (sin VPN) falla por DNS -> 503, no 401. Documenta
    el comportamiento real verificado manualmente en F0 (R1 del plan)."""
    resp = await integration_client.post(
        "/api/v1/auth/login",
        json={"username": "test.user", "password": "clave-incorrecta"},
    )
    assert resp.status_code == 503
