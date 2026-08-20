"""Integración de `consulta` — deny-by-default y contrato del endpoint.

Confirma dos cosas que solo se ven a nivel de aplicación:

1. La feature queda tras el `AuthMiddleware`: un anónimo recibe 401 con el
   contrato de error uniforme, sin llegar al motor.
2. El `usuario` **no se acepta del body**. El origen lo recibe como campo del
   request, es decir, el cliente declara quién es. Aquí sale de la cookie.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

RUTAS_CONSULTA = [
    "/api/v1/consulta/preguntar",
    "/api/v1/consulta/veredicto",
]


@pytest.mark.integration
@pytest.mark.parametrize("ruta", RUTAS_CONSULTA)
async def test_consulta_exige_sesion(async_client: AsyncClient, ruta: str) -> None:
    """Deny-by-default: sin cookie no se llega al motor."""
    response = await async_client.post(ruta, json={})

    assert response.status_code == 401
    body = response.json()
    assert body["status"] == 401
    # N6: el correlation_id viaja también en el cuerpo del error, no solo en
    # la cabecera — es lo que permite hacer grep desde un reporte de usuario.
    assert "correlation_id" in body


@pytest.mark.integration
async def test_el_usuario_no_se_acepta_del_body(async_client: AsyncClient) -> None:
    """🔑 Un campo `usuario` en el body sería suplantación por diseño.

    El esquema no lo declara, así que aunque el cliente lo envíe, Pydantic lo
    ignora. Se comprueba que el contrato no lo tiene.
    """
    from src.features.consulta.schemas import PreguntarIn

    assert "usuario" not in PreguntarIn.model_fields
    assert set(PreguntarIn.model_fields) == {"texto", "conversacion_id"}


@pytest.mark.integration
async def test_el_veredicto_no_acepta_la_fuente_del_cliente() -> None:
    """La pone el servidor: si viniera del cliente, un usuario podría marcar
    sus propios veredictos como si fueran de la revisión por lotes."""
    from src.features.consulta.schemas import VeredictoIn

    assert "fuente" not in VeredictoIn.model_fields


@pytest.mark.integration
async def test_los_dos_endpoints_estan_en_el_openapi() -> None:
    """Si un endpoint desaparece del esquema, el cliente tipado del frontend
    dejaría de generarlo sin que nada falle en el backend."""
    from src.main import app

    rutas = app.openapi()["paths"]
    assert "/api/v1/consulta/preguntar" in rutas
    assert "/api/v1/consulta/veredicto" in rutas


@pytest.mark.integration
async def test_escenario_mes_sigue_fuera_del_openapi() -> None:
    """AF-4.11: `escenario_mes` es una función que F4 consume directamente, no
    una ruta. Exponerla haría que sus parámetros llegaran como objetos `Query`
    de FastAPI en vez de valores."""
    from src.main import app

    rutas = app.openapi()["paths"]
    assert not any("escenario" in r for r in rutas)
