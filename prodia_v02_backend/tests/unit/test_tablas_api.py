"""Tests del router `tablas` — degradación a 503 cuando PostgreSQL cae (H9).

Los endpoints se invocan directamente (son corrutinas) con un service construido sobre el
doble en modo `fallar=True`. Así se ejercita el `except SQLAlchemyError -> 503` sin
levantar Postgres ni atravesar el middleware de auth.

Regla H9: la caída de `db_prod` degrada ESTA feature, no la aplicación. El backend sigue
arrancando y el login funciona — por eso el fallo se traduce a 503 aquí y no a un `raise`
en el lifespan.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.features.tablas import api
from src.features.tablas.repositories import TablasRepository
from src.features.tablas.services import TablasService
from tests.fakes.prod_db_falsa import SesionProdFalsa


def _service_caido() -> TablasService:
    return TablasService(TablasRepository(SesionProdFalsa(fallar=True)))  # type: ignore[arg-type]


@pytest.mark.unit
async def test_arbol_devuelve_503_si_postgres_cae() -> None:
    with pytest.raises(HTTPException) as excinfo:
        await api.arbol_reportes(service=_service_caido())

    assert excinfo.value.status_code == 503


@pytest.mark.unit
async def test_hojas_devuelve_503_si_postgres_cae() -> None:
    with pytest.raises(HTTPException) as excinfo:
        await api.hojas_de_reporte(reporte_id=1042, service=_service_caido())

    assert excinfo.value.status_code == 503


@pytest.mark.unit
async def test_listar_tablas_devuelve_503_si_postgres_cae() -> None:
    with pytest.raises(HTTPException) as excinfo:
        await api.listar_tablas(reporte_id=1042, hoja="H", service=_service_caido())

    assert excinfo.value.status_code == 503


@pytest.mark.unit
async def test_datos_devuelve_503_si_postgres_cae() -> None:
    with pytest.raises(HTTPException) as excinfo:
        await api.datos_tabla(
            reporte_id=1042, hoja="H", tabla_idx=1, service=_service_caido()
        )

    assert excinfo.value.status_code == 503


@pytest.mark.unit
async def test_reportes_y_cobertura_devuelven_503_si_postgres_cae() -> None:
    with pytest.raises(HTTPException) as excinfo:
        await api.listar_reportes(service=_service_caido())
    assert excinfo.value.status_code == 503

    with pytest.raises(HTTPException) as excinfo:
        await api.cobertura(service=_service_caido())
    assert excinfo.value.status_code == 503


@pytest.mark.unit
async def test_kpi_devuelve_503_si_postgres_cae() -> None:
    with pytest.raises(HTTPException) as excinfo:
        await api.produccion_dia(fecha="2026-08-15", service=_service_caido())

    assert excinfo.value.status_code == 503


@pytest.mark.unit
async def test_el_503_no_filtra_el_mensaje_del_driver() -> None:
    """L1 — el error interno va al log, nunca al cliente."""
    with pytest.raises(HTTPException) as excinfo:
        await api.arbol_reportes(service=_service_caido())

    detalle = str(excinfo.value.detail)
    assert "conexión rechazada" not in detalle
    assert "OperationalError" not in detalle
    assert "base de datos de producción no está disponible" in detalle


@pytest.mark.unit
async def test_camino_feliz_devuelve_datos() -> None:
    """Contraprueba: con Postgres sano, el mismo endpoint responde normal."""
    service = TablasService(TablasRepository(SesionProdFalsa()))  # type: ignore[arg-type]

    arbol = await api.arbol_reportes(service=service)

    assert arbol[0].anio == 2026
