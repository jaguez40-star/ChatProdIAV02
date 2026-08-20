"""Router `tablas` — visor de reportes de producción (F1: Control + Tablas).

Agrupa los 7 endpoints portados de tres features del sistema viejo (`tablas`, `reportes`,
`kpis_prod`): eran tan pequeñas que separarlas aquí daría tres paquetes triviales.

Acceso: **todo usuario autenticado** (decisión del usuario, 2026-08-20). No lleva
`require_admin` — basta el deny-by-default del `AuthMiddleware`, que ya rechaza cualquier
ruta fuera de `PUBLIC_PATHS` sin cookie válida.

H9 — `db_prod` es crítica para ESTA feature, pero no para el arranque: si PostgreSQL está
caído, estos endpoints devuelven **503** con el contrato de error uniforme; el backend
sigue en pie y el login (que solo necesita `db_auth`) funciona igual. Nunca un `raise` en
el lifespan por `db_prod` — eso tumbaría la app entera por una feature.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.core.logger import get_logger
from src.features.tablas.repositories import TablasRepository
from src.features.tablas.schemas import (
    AnioArbolOut,
    CoberturaOut,
    HojasReporteOut,
    ProduccionDiaOut,
    ReporteOut,
    TablaDatosOut,
    TablaLogicaOut,
)
from src.features.tablas.services import TablasService
from src.shared.db_prod import get_prod_db

logger = get_logger("tablas.api")

router = APIRouter(prefix="/tablas", tags=["Tablas"])

RESPUESTAS_COMUNES: dict[int | str, dict[str, str]] = {
    401: {"description": "No autenticado — falta la cookie de sesión o es inválida"},
    503: {"description": "PostgreSQL (`db_prod`) no disponible"},
}


def get_service(db: Session = Depends(get_prod_db)) -> TablasService:
    """Dependencia única de la feature: arma repositorio + service sobre la sesión de
    `db_prod`. Los tests la sustituyen vía `app.dependency_overrides[get_prod_db]`."""
    return TablasService(TablasRepository(db))


def _error_db(exc: SQLAlchemyError, operacion: str) -> HTTPException:
    """Traduce un fallo de PostgreSQL a 503 (H9). El detalle interno va al log, no al
    cliente — el contrato de error nunca filtra el mensaje del driver (L1)."""
    logger.error("db_prod_no_disponible", operacion=operacion, error=str(exc))
    return HTTPException(
        status_code=503,
        detail="La base de datos de producción no está disponible. Intente más tarde.",
    )


# ── Árbol de reportes ────────────────────────────────────────────────────────


@router.get(
    "/arbol",
    response_model=list[AnioArbolOut],
    summary="Árbol de reportes (año → mes → día)",
    description=(
        "Metadata de todos los reportes, jerarquizada. **No** incluye el desglose de "
        "hojas/tablas: eso se carga bajo demanda con `/tablas/arbol/{reporte_id}` al "
        "expandir un día. Solo toca `core.config_reporte` (una fila por reporte), así "
        "que es instantánea sin importar cuántos reportes existan."
    ),
    responses=RESPUESTAS_COMUNES,
)
async def arbol_reportes(
    service: TablasService = Depends(get_service),
) -> list[AnioArbolOut]:
    try:
        return service.arbol_reportes()
    except SQLAlchemyError as exc:
        raise _error_db(exc, "arbol_reportes") from exc


@router.get(
    "/arbol/{reporte_id}",
    response_model=HojasReporteOut,
    summary="Hojas y tablas de un reporte (carga perezosa)",
    description=(
        "Desglose de un solo reporte. Filtrado por `reporte_id` para usar el índice "
        "`(reporte_id, hoja, tabla_idx)` en vez de agregar `core.fact_tabla_hoja` entera."
    ),
    responses=RESPUESTAS_COMUNES,
)
async def hojas_de_reporte(
    reporte_id: int,
    service: TablasService = Depends(get_service),
) -> HojasReporteOut:
    try:
        return service.hojas_de_reporte(reporte_id)
    except SQLAlchemyError as exc:
        raise _error_db(exc, "hojas_de_reporte") from exc


# ── Tablas de una hoja y su contenido ────────────────────────────────────────


@router.get(
    "",
    response_model=list[TablaLogicaOut],
    summary="Tablas lógicas de una hoja",
    description=(
        "Los ítems clicables del visor. `COMENTARIOS` es un caso aparte: no vive en "
        "`core.fact_tabla_hoja` (es texto), sino en su fact dedicado."
    ),
    responses=RESPUESTAS_COMUNES,
)
async def listar_tablas(
    reporte_id: int = Query(..., description="Id del reporte."),
    hoja: str = Query(..., description="Nombre de la hoja."),
    service: TablasService = Depends(get_service),
) -> list[TablaLogicaOut]:
    try:
        return service.tablas_de_hoja(reporte_id, hoja)
    except SQLAlchemyError as exc:
        raise _error_db(exc, "listar_tablas") from exc


@router.get(
    "/datos",
    response_model=TablaDatosOut,
    summary="Contenido de una tabla en formato ancho",
    description=(
        "Devuelve la tabla en uno de tres modos, indicado en `modo`:\n\n"
        "- `fechas`: columnas = fechas (serie temporal).\n"
        "- `matriz`: columnas = categorías; se conserva el **orden de aparición** porque "
        "en las matrices el orden de columnas es significativo.\n"
        "- `texto`: `COMENTARIOS`, desde su fact dedicado.\n\n"
        "Solo se devuelven las primeras 100 filas (`CAP_FILAS`); `total_filas` trae el "
        "total real."
    ),
    responses=RESPUESTAS_COMUNES,
)
async def datos_tabla(
    reporte_id: int = Query(..., description="Id del reporte."),
    hoja: str = Query(..., description="Nombre de la hoja."),
    tabla_idx: int = Query(..., description="Índice de la tabla dentro de la hoja."),
    service: TablasService = Depends(get_service),
) -> TablaDatosOut:
    try:
        return service.datos_tabla(reporte_id, hoja, tabla_idx)
    except SQLAlchemyError as exc:
        raise _error_db(exc, "datos_tabla") from exc


# ── Reportes y cobertura ─────────────────────────────────────────────────────


@router.get(
    "/reportes",
    response_model=list[ReporteOut],
    summary="Lista plana de reportes",
    responses=RESPUESTAS_COMUNES,
)
async def listar_reportes(
    service: TablasService = Depends(get_service),
) -> list[ReporteOut]:
    try:
        return service.listar_reportes()
    except SQLAlchemyError as exc:
        raise _error_db(exc, "listar_reportes") from exc


@router.get(
    "/reportes/cobertura",
    response_model=list[CoberturaOut],
    summary="Cobertura de cada reporte por fact",
    description="Cuántos registros aportó cada reporte a cada fact — diagnóstico de ingesta.",
    responses=RESPUESTAS_COMUNES,
)
async def cobertura(
    service: TablasService = Depends(get_service),
) -> list[CoberturaOut]:
    try:
        return service.cobertura()
    except SQLAlchemyError as exc:
        raise _error_db(exc, "cobertura") from exc


# ── KPIs ─────────────────────────────────────────────────────────────────────


@router.get(
    "/kpis/produccion-dia",
    response_model=list[ProduccionDiaOut],
    summary="Producción estimada por tipo de producto en una fecha",
    description="Suma `vol_estimado` del grupo `ECOPETROL` para la fecha indicada.",
    responses=RESPUESTAS_COMUNES,
)
async def produccion_dia(
    fecha: str = Query(
        ..., description="Fecha en formato ISO (YYYY-MM-DD).", examples=["2026-08-15"]
    ),
    service: TablasService = Depends(get_service),
) -> list[ProduccionDiaOut]:
    try:
        return service.produccion_dia(fecha)
    except SQLAlchemyError as exc:
        raise _error_db(exc, "produccion_dia") from exc
