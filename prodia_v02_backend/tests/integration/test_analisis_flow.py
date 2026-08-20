"""Tests de integración de `analisis` — deny-by-default y aislamiento de PostgreSQL.

Mismo valor doble que `test_tablas_flow.py`:

1. La feature queda tras el `AuthMiddleware`: un anónimo recibe 401 en TODOS
   sus endpoints, con el contrato de error uniforme.
2. La suite jamás alcanza el PostgreSQL real — si alguien rompe el override,
   estos tests lo cazan antes de que CI empiece a intentar conectar al 139.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

RUTAS_ANALISIS = [
    "/api/v1/analisis/catalogo",
    "/api/v1/analisis/densidad",
    "/api/v1/analisis/densidad?entidad=CASTILLA",
    "/api/v1/analisis/huella",
    "/api/v1/analisis/cobertura",
    "/api/v1/analisis/desempeno",
    "/api/v1/analisis/desempeno?entidad=CASTILLA&nivel=campo",
    "/api/v1/analisis/desempeno_insight",
    "/api/v1/analisis/ejecutivo",
    "/api/v1/analisis/ejecutivo?segmento=filiales",
    "/api/v1/analisis/tendencia_filial?empresa=Hocol",
    "/api/v1/analisis/president",
    "/api/v1/ebitda/unificado-waterfall",
    "/api/v1/diferidas/frecuencia",
    "/api/v1/mantenimientos/eventos",
]


@pytest.mark.integration
@pytest.mark.parametrize("ruta", RUTAS_ANALISIS)
async def test_analisis_exige_sesion(async_client: AsyncClient, ruta: str) -> None:
    """Ningún endpoint de Análisis es público."""
    respuesta = await async_client.get(ruta)

    assert respuesta.status_code == 401
    cuerpo = respuesta.json()
    assert cuerpo["status"] == 401
    assert "correlation_id" in cuerpo  # N6


@pytest.mark.integration
async def test_override_de_db_prod_cubre_analisis(patch_prod_db: Any) -> None:
    """El fixture debe interceptar `get_prod_db` también para esta feature."""
    from src.main import app
    from src.shared.db_prod import get_prod_db

    sesion_falsa = patch_prod_db()

    assert get_prod_db in app.dependency_overrides
    generador = app.dependency_overrides[get_prod_db]()
    assert next(generador) is sesion_falsa


@pytest.mark.integration
def test_los_endpoints_de_analisis_son_sincronos() -> None:
    """AP-9: `def`, nunca `async def`.

    Esta feature hace SQLAlchemy síncrona y, desde el bloque 5, llamadas
    bloqueantes a Ollama con timeout de 180 s. Un `async def` con trabajo
    bloqueante dentro congelaría el event loop —y con él el login— durante ese
    tiempo. Declarándolos `def`, Starlette los manda a su threadpool.

    Se verifica automáticamente porque es una regla fácil de romper por
    costumbre: el resto del repositorio usa `async def`.
    """
    import inspect

    from src.features.analisis import api

    for nombre in (
        "catalogo",
        "densidad",
        "huella",
        "cobertura",
        "desempeno",
        "desempeno_insight",
        "ejecutivo",
    ):
        funcion = getattr(api, nombre)
        assert not inspect.iscoroutinefunction(
            funcion
        ), f"`{nombre}` es async: bloquearía el event loop (AP-9). Usa `def`."
