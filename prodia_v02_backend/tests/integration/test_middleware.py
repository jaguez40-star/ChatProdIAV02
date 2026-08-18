"""Tests de integración — correlation_id, request_logger y auth deny-by-default
vía HTTP real (httpx.AsyncClient + ASGITransport). Copiado del patrón de
Robustez V02 (L2)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.integration
async def test_correlation_id_generated(async_client: AsyncClient) -> None:
    """Requests sin correlation_id reciben uno generado en la respuesta."""
    response = await async_client.get("/docs")
    assert "x-correlation-id" in response.headers
    cid = response.headers["x-correlation-id"]
    assert len(cid) == 36  # formato UUID4


@pytest.mark.integration
async def test_correlation_id_propagated(async_client: AsyncClient) -> None:
    """Requests con correlation_id propio lo devuelven igual."""
    my_cid = "my-custom-correlation-id"
    response = await async_client.get("/docs", headers={"x-correlation-id": my_cid})
    assert response.headers.get("x-correlation-id") == my_cid


@pytest.mark.integration
async def test_unauthenticated_unknown_route_returns_401_not_404(
    async_client: AsyncClient,
) -> None:
    """N5/deny-by-default: una ruta que NI SIQUIERA EXISTE responde 401, no
    404 — prueba de que el middleware de auth corre ANTES del routing y no
    filtra qué rutas existen a un anónimo."""
    response = await async_client.get("/api/v1/ruta-que-no-existe")
    assert response.status_code == 401
    body = response.json()
    assert body["status"] == 401
    assert "correlation_id" in body  # N6


@pytest.mark.integration
async def test_unauthenticated_api_returns_401_with_correlation_id(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get("/api/v1/permissions/my-permissions")
    assert response.status_code == 401
    body = response.json()
    assert body["status"] == 401
    assert body["correlation_id"] is not None
    assert response.headers.get("x-session-expired") == "true"


@pytest.mark.integration
async def test_docs_is_public(async_client: AsyncClient) -> None:
    response = await async_client.get("/docs")
    assert response.status_code == 200


@pytest.mark.integration
async def test_health_is_public(async_client: AsyncClient) -> None:
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("ok", "degraded")
    assert "database_auth" in body
    assert "database_prod" in body
