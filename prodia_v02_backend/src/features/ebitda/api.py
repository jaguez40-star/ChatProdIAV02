"""Router `ebitda` — waterfall económico Ingresos → NOPAT.

Portado de `INGESTA/Rep_Prod/backend/app/features/ebitda/api.py`.

Única feature de F2 que lee `db_ops` (PostgreSQL `robustez_v02`, schema
`ops.*`), no `db_prod`. Los engines nunca se mezclan.

**Dos fallos distintos, dos 503 distintos** (AP-10):

- `OPS_DATABASE_URL` vacía → `OpsNoConfiguradaError`. NO es un fallo de base de
  datos, es configuración ausente: sin este caso explícito saldría como 500
  genérico y el operador no sabría que solo le falta una variable de entorno.
- La BD no responde → `SQLAlchemyError`, que el handler global ya traduce.

Endpoints `def` (sync), como el resto de F2 (AP-9).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.core.logger import get_logger
from src.features.ebitda.repositories import EbitdaRepository, PeriodoProdRepository
from src.features.ebitda.schemas import WaterfallOut
from src.features.ebitda.services import EbitdaService
from src.shared.db_ops import OpsNoConfiguradaError, get_ops_db
from src.shared.db_prod import get_prod_db

logger = get_logger("ebitda.api")

router = APIRouter(prefix="/ebitda", tags=["EBITDA"])

RESPUESTAS_COMUNES: dict[int | str, dict[str, str]] = {
    401: {"description": "No autenticado — falta la cookie de sesión o es inválida"},
    503: {
        "description": (
            "`OPS_DATABASE_URL` sin configurar, o la BD operacional ROBUSTEZ "
            "no está disponible"
        )
    },
}


def get_ebitda_service(db: Session = Depends(get_ops_db)) -> EbitdaService:
    return EbitdaService(EbitdaRepository(db))


def get_periodo_repo(db: Session = Depends(get_prod_db)) -> PeriodoProdRepository:
    return PeriodoProdRepository(db)


@router.get(
    "/unificado-waterfall",
    response_model=WaterfallOut,
    summary="Waterfall económico: Ingresos → EBITDA → EBIT → NOPAT",
    description=(
        "18 componentes en orden fijo, en kUSD y en USD/BI, para el periodo y "
        "el ámbito indicados.\n\n"
        "Sin `year`/`month` se alinea con el último mes con REAL de la BD de "
        "producción, para que el waterfall y el resto del panel hablen del "
        "mismo periodo.\n\n"
        "`entidad` admite varios valores separados por `|`: un foco agrupa "
        "varios campos.\n\n"
        "Solo aplica a **crudo** (variante `_a` de la BD operacional)."
    ),
    responses=RESPUESTAS_COMUNES,
)
def unificado_waterfall(
    year: int | None = Query(None, description="Año. Sin él, el último con REAL."),
    month: int | None = Query(None, description="Mes 1-12."),
    nivel: str | None = Query(None, description="global | activo | campo."),
    entidad: str | None = Query(
        None, description="Entidad(es), separadas por `|` si son varias."
    ),
    service: EbitdaService = Depends(get_ebitda_service),
    periodo_repo: PeriodoProdRepository = Depends(get_periodo_repo),
) -> WaterfallOut:
    try:
        if not year or not month:
            resuelto = periodo_repo.ultimo_mes_con_real()
            if resuelto is None:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "No se pudo resolver el período: la base de datos de "
                        "producción no está disponible."
                    ),
                )
            year, month = resuelto

        return service.waterfall(year, month, nivel, entidad)

    except OpsNoConfiguradaError as exc:
        # Configuración ausente, NO un fallo de BD: el mensaje dice exactamente
        # qué falta para que el operador pueda resolverlo.
        logger.error("ops_no_configurada", detalle=str(exc))
        raise HTTPException(
            status_code=503,
            detail=(
                "La base de datos operacional (ROBUSTEZ/ops) no está "
                "configurada. Defina OPS_DATABASE_URL para habilitar el EBITDA."
            ),
        ) from exc
    except SQLAlchemyError as exc:
        logger.error("db_ops_no_disponible", error=str(exc))
        raise HTTPException(
            status_code=503,
            detail=(
                "La base de datos operacional no está disponible. Intente más " "tarde."
            ),
        ) from exc
