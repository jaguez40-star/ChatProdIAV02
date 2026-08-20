"""Tests de integración de `tablas` — deny-by-default y aislamiento de PostgreSQL.

El valor de estos tests es doble:

1. Confirmar que la feature nueva queda tras el `AuthMiddleware` (deny-by-default): un
   anónimo recibe 401 en TODOS sus endpoints, con el contrato de error uniforme.
2. Garantizar que la suite jamás alcanza el PostgreSQL real (H1): el fixture
   `patch_prod_db` sustituye `get_prod_db` vía `app.dependency_overrides`, y aquí se
   verifica que ese mecanismo funciona de verdad. Si alguien lo rompe, este test lo caza
   antes de que CI empiece a intentar conectar al 10.100.26.139.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

RUTAS_TABLAS = [
    "/api/v1/tablas/arbol",
    "/api/v1/tablas/arbol/1042",
    "/api/v1/tablas?reporte_id=1042&hoja=NEW%20MES-A%C3%91O",
    "/api/v1/tablas/datos?reporte_id=1042&hoja=H&tabla_idx=1",
    "/api/v1/tablas/reportes",
    "/api/v1/tablas/reportes/cobertura",
    "/api/v1/tablas/kpis/produccion-dia?fecha=2026-08-15",
]


@pytest.mark.integration
@pytest.mark.parametrize("ruta", RUTAS_TABLAS)
async def test_tablas_exige_sesion(async_client: AsyncClient, ruta: str) -> None:
    """Ningún endpoint de la feature es público — Control exige sesión (aunque no
    exige ser admin: la decisión de F1 es 'todo usuario autenticado')."""
    response = await async_client.get(ruta)

    assert response.status_code == 401
    body = response.json()
    assert body["status"] == 401
    assert "correlation_id" in body  # N6


@pytest.mark.integration
async def test_override_de_db_prod_evita_postgres_real(patch_prod_db: Any) -> None:
    """El fixture debe interceptar `get_prod_db` — si no, CI intentaría conectar al 139."""
    from src.main import app
    from src.shared.db_prod import get_prod_db

    sesion_falsa = patch_prod_db()

    assert get_prod_db in app.dependency_overrides
    generador = app.dependency_overrides[get_prod_db]()
    assert next(generador) is sesion_falsa


@pytest.mark.integration
async def test_fallo_de_bd_en_la_dependencia_sale_como_503_no_500() -> None:
    """Regresión H9: si `PROD_DATABASE_URL` está vacía o mal formada, `create_engine`
    lanza `ArgumentError` DENTRO de la dependencia `get_prod_db`, antes del cuerpo del
    endpoint — donde el `try/except` local no alcanza. Sin el handler global de
    `SQLAlchemyError`, el cliente recibía un 500 genérico en vez del 503 del contrato.
    """
    from sqlalchemy.exc import ArgumentError

    from src.core.exceptions import database_exception_handler

    class _PeticionFalsa:
        url = type("Url", (), {"path": "/api/v1/tablas/arbol"})()

    respuesta = await database_exception_handler(
        _PeticionFalsa(),  # type: ignore[arg-type]
        ArgumentError("Could not parse SQLAlchemy URL from given URL string"),
    )

    assert respuesta.status_code == 503
    cuerpo = respuesta.body.decode()
    assert "DB_UNAVAILABLE" in cuerpo
    assert "SQLAlchemy URL" not in cuerpo  # L1 — no filtra el detalle interno


@pytest.mark.integration
async def test_la_cadena_dependencia_repo_service_funciona_sin_postgres(
    patch_prod_db: Any,
) -> None:
    """Sanidad de la feature completa (dependencia → repositorio → service) con el doble."""
    from src.features.tablas.api import get_service

    sesion_falsa = patch_prod_db()
    service = get_service(db=sesion_falsa)

    arbol = service.arbol_reportes()

    assert arbol[0].anio == 2026
    assert any("core.config_reporte" in sql for sql in sesion_falsa.consultas)
