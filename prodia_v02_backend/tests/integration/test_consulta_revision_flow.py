"""Test Clas — deny-by-default, admin-only y la no-regresión de F4.

Tres cosas que solo se pueden verificar por HTTP:

1. Los endpoints de revisión exigen sesión (401 sin cookie).
2. Exigen ser **administrador** (403 con sesión de un usuario normal). Un 403,
   no una lista vacía: un permiso que se manifiesta como "no hay datos" es
   indistinguible de un bug.
3. **Los endpoints de F4 siguen abiertos a un no-admin.** Es la regresión que
   delataría un `require_admin` puesto donde no toca — y la razón por la que la
   revisión vive en un router aparte.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.core.config import get_settings

RUTAS_DE_REVISION = [
    ("GET", "/api/v1/consulta/revision/libreta"),
    ("POST", "/api/v1/consulta/revision/escanear"),
    ("POST", "/api/v1/consulta/revision/veredicto-lote"),
]


@pytest.fixture
def usuario_no_admin(integration_engine: Engine) -> Iterator[str]:
    """Un usuario SIN privilegios, creado y retirado por el propio test.

    🔑 **Aditivo a propósito.** `_seed_integration_db` siembra un único usuario
    —`test.user`, con `is_admin=1`— y lo comparten los 800+ tests de la suite;
    tocarlo para añadir un segundo usuario arriesgaría romper cualquiera que
    cuente filas.

    🔑 **Y se limpia.** El engine es de SESIÓN: sin el borrado del final, esta
    fila seguiría viva para los tests siguientes y el fallo aparecería en otro
    archivo, donde nadie lo buscaría.
    """
    username = "raso.sinprivilegios"
    with integration_engine.begin() as conexion:
        conexion.execute(
            text("""
                INSERT INTO app_users (username, email, full_name, is_admin, is_active)
                VALUES (:u, :e, :n, 0, 1)
                """),
            {
                "u": username,
                "e": f"{username}@ecopetrol.com.co",
                "n": "Usuario Sin Privilegios",
            },
        )
    try:
        yield username
    finally:
        with integration_engine.begin() as conexion:
            conexion.execute(
                text("DELETE FROM app_users WHERE username = :u"), {"u": username}
            )


@pytest.fixture
def _login_local(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ENABLE_LOCAL_LOGIN", "true")
    monkeypatch.setenv("LOCAL_LOGIN_PASSWORD", "clave-integracion")
    monkeypatch.setenv("LOCAL_LOGIN_ALLOWED_IPS", "127.0.0.1,::1,testclient")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _entrar(cliente: AsyncClient, username: str) -> None:
    monkey_user = {"username": username, "password": "clave-integracion"}
    respuesta = await cliente.post("/api/v1/auth/login", json=monkey_user)
    assert respuesta.status_code == 200, respuesta.text


def _cuerpo_de(metodo: str) -> dict[str, Any] | None:
    if metodo != "POST":
        return None
    return {"items": [{"log_id": 1, "veredicto": "confirmado_revision"}]}


# ── 1) Deny-by-default ───────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.parametrize(("metodo", "ruta"), RUTAS_DE_REVISION)
async def test_la_revision_exige_sesion(
    async_client: AsyncClient, metodo: str, ruta: str
) -> None:
    respuesta = await async_client.request(metodo, ruta, json=_cuerpo_de(metodo))

    assert respuesta.status_code == 401
    cuerpo = respuesta.json()
    assert cuerpo["status"] == 401
    assert "correlation_id" in cuerpo  # N6


# ── 2) Admin-only ────────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.parametrize(("metodo", "ruta"), RUTAS_DE_REVISION)
async def test_la_revision_rechaza_a_un_usuario_normal(
    integration_client: AsyncClient,
    usuario_no_admin: str,
    _login_local: None,
    monkeypatch: pytest.MonkeyPatch,
    metodo: str,
    ruta: str,
) -> None:
    """403 explícito, nunca una lista vacía."""
    monkeypatch.setenv("LOCAL_LOGIN_USERNAME", usuario_no_admin)
    get_settings.cache_clear()
    await _entrar(integration_client, usuario_no_admin)

    respuesta = await integration_client.request(metodo, ruta, json=_cuerpo_de(metodo))

    assert respuesta.status_code == 403
    assert "correlation_id" in respuesta.json()


@pytest.mark.integration
async def test_un_admin_si_puede_leer_la_libreta(
    integration_client: AsyncClient,
    _login_local: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.main import app
    from src.shared.db_auth import get_db

    # Si esto falla, el endpoint estaría leyendo la BD REAL de archivo en vez de
    # la de memoria — y el test "pasaría" o fallaría por razones ajenas a lo que
    # pretende verificar.
    assert get_db in app.dependency_overrides

    monkeypatch.setenv("LOCAL_LOGIN_USERNAME", "test.user")
    get_settings.cache_clear()
    await _entrar(integration_client, "test.user")

    respuesta = await integration_client.get("/api/v1/consulta/revision/libreta")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert "filas" in cuerpo
    assert "resumen" in cuerpo
    assert "pct_capa1" in cuerpo["resumen"]


@pytest.mark.integration
async def test_un_filtro_invalido_es_422_no_una_libreta_entera(
    integration_client: AsyncClient,
    _login_local: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La corrección de F5: antes degradaba a «todas» en silencio y el revisor
    creía estar viendo solo las sospechas."""
    monkeypatch.setenv("LOCAL_LOGIN_USERNAME", "test.user")
    get_settings.cache_clear()
    await _entrar(integration_client, "test.user")

    respuesta = await integration_client.get(
        "/api/v1/consulta/revision/libreta?filtro=sospechas"  # plural: errata
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["errors"]


# ── 3) No-regresión: F4 sigue abierto ────────────────────────────────────────


@pytest.mark.integration
async def test_los_endpoints_de_f4_siguen_abiertos_a_un_no_admin(
    integration_client: AsyncClient,
    usuario_no_admin: str,
    _login_local: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`/consulta/veredicto` es de TODO usuario autenticado: cualquiera juzga su
    propia pregunta con el ✓/✗ del chat.

    Si algún día alguien mueve `require_admin` al router de F4, este test lo
    caza. Lo que se afirma es **la ausencia del 403**, no un código concreto:
    sin PostgreSQL levantado la respuesta es 503 (la dependencia `get_prod_db`
    del router de F4 no resuelve), y ese 503 demuestra igual de bien que la
    petición **atravesó la autorización** — un no-admin llegó hasta la capa de
    datos en vez de rebotar en el guard.
    """
    monkeypatch.setenv("LOCAL_LOGIN_USERNAME", usuario_no_admin)
    get_settings.cache_clear()
    await _entrar(integration_client, usuario_no_admin)

    respuesta = await integration_client.post(
        "/api/v1/consulta/veredicto",
        json={"log_id": 999_999, "veredicto": "confirmado_usuario"},
    )

    assert respuesta.status_code != 403
    assert respuesta.status_code in (400, 503)
