"""Router `mantenimientos` — eventos de servicio a pozo (Eventos_OW.xlsx).

Portado de `routes/api.py:492-559`.

**Contrato de degradación: SIEMPRE HTTP 200.** Un archivo ausente o un periodo
ilegible devuelven `sin_datos` con su motivo. Esta pill vive dentro del
acordeón de foco: un 500 tumbaría el panel entero por un dato accesorio.

El conjunto de campos de un activo sale de `core.map_campo_activo` vía la
dependencia compartida, NUNCA de un CSV paralelo (H11): dos fuentes del mismo
mapa hacían que el panel discrepara del tablero para la misma entidad.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.features.mantenimientos.repositories import MantenimientosRepository
from src.features.mantenimientos.services import MantenimientosService
from src.shared.catalogo_entidades import campos_de_activo
from src.shared.db_prod import get_prod_db

router = APIRouter(prefix="/mantenimientos", tags=["Mantenimientos"])

RESPUESTAS_COMUNES: dict[int | str, dict[str, str]] = {
    401: {"description": "No autenticado — falta la cookie de sesión o es inválida"},
}


def get_mantenimientos_service() -> MantenimientosService:
    return MantenimientosService(MantenimientosRepository())


@router.get(
    "/eventos",
    summary="Eventos de servicio a pozo que solapan el mes analizado",
    description=(
        "Eventos del archivo Eventos_OW que **solapan** el mes indicado.\n\n"
        "El criterio es el solape con el mes, **no** la vigencia contra hoy: "
        "el archivo es un snapshot cuyo grueso ya cerró, así que filtrar contra "
        "la fecha actual dejaría 3 eventos en toda la compañía frente a los "
        "2.741 que tiene el mes analizado.\n\n"
        "Un evento sin fecha de cierre está **ABIERTO**, no es una fila "
        "inválida: son el 48 % del archivo y son justamente los que siguen "
        "corriendo. Se listan primero.\n\n"
        "Responde **siempre 200**: si falta el archivo o el periodo no es "
        "legible, devuelve `sin_datos` con el motivo."
    ),
    responses=RESPUESTAS_COMUNES,
)
def eventos(
    entidad: str | None = Query(None, description="Entidad analizada."),
    nivel: str | None = Query(
        None, description="Si es `activo`, expande a sus campos."
    ),
    campos: str | None = Query(
        None, description="Campos explícitos, separados por `|`."
    ),
    periodo: str | None = Query(None, description="`YYYY-MM` o `Mayo 2026`."),
    service: MantenimientosService = Depends(get_mantenimientos_service),
    db: Session = Depends(get_prod_db),
) -> dict[str, Any]:
    objetivo: list[str] = []
    if campos:
        objetivo = [c.strip() for c in campos.split("|") if c.strip()]
    elif nivel and nivel.strip().lower() == "activo" and entidad:
        try:
            objetivo = campos_de_activo(db, entidad)
        except Exception:
            # Si Postgres no responde, se degrada al match literal por entidad
            # en vez de tumbar la pill.
            objetivo = []
    if not objetivo and entidad:
        objetivo = [entidad]

    return service.eventos(entidad=entidad, campos=objetivo, periodo=periodo)
