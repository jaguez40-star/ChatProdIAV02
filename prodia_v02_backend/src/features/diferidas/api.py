"""Router `diferidas` — histórico de producción diferida por causa.

Portado de `routes/api.py:562-700`.

**Contrato de degradación: SIEMPRE HTTP 200**, igual que mantenimientos.

El servicio se instancia UNA vez por proceso (no por petición) porque cachea
por entidad: los datos son históricos y estáticos (ene-2023 → jul-2025), así
que el mismo input siempre da la misma salida y recalcularlo sería tirar ~0,7 s
por cada reapertura del panel.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.features.diferidas.services import DiferidasService
from src.shared.catalogo_entidades import campos_de_activo
from src.shared.db_prod import get_prod_db

router = APIRouter(prefix="/diferidas", tags=["Diferidas"])

RESPUESTAS_COMUNES: dict[int | str, dict[str, str]] = {
    401: {"description": "No autenticado — falta la cookie de sesión o es inválida"},
}

# Instancia única: su caché por entidad solo sirve si se comparte entre
# peticiones.
_servicio = DiferidasService()


def get_diferidas_service() -> DiferidasService:
    return _servicio


@router.get(
    "/frecuencia",
    summary="Diferidas históricas por causa: Pareto, tendencia e impacto",
    description=(
        "Frecuencia de causas de producción diferida para una entidad, medida "
        "en **INCIDENTES** (no en días).\n\n"
        "El grano de la tabla es día-pozo: sin colapsar por evento, uno de 30 "
        "días contaría 30 veces y el Pareto mediría duración en vez de "
        "frecuencia.\n\n"
        "Bloques: `pareto` (grupos de causa por año), `tendencia` (solo los "
        "tipos que EMPEORARON en 2025 vs 2024), `pozos_por_grupo` e `impacto` "
        "(volumen perdido por causa, crudo y gas).\n\n"
        "Responde **siempre 200**: si falta la BD, devuelve `sin_datos` con el "
        "motivo."
    ),
    responses=RESPUESTAS_COMUNES,
)
def frecuencia(
    entidad: str | None = Query(None, description="Entidad analizada."),
    nivel: str | None = Query(
        None, description="Si es `activo`, expande a sus campos."
    ),
    campos: str | None = Query(
        None, description="Campos explícitos, separados por `|`."
    ),
    service: DiferidasService = Depends(get_diferidas_service),
    db: Session = Depends(get_prod_db),
) -> dict[str, Any]:
    objetivo: list[str] = []
    if campos:
        objetivo = [c.strip() for c in campos.split("|") if c.strip()]
    elif nivel and nivel.strip().lower() == "activo" and entidad:
        try:
            objetivo = campos_de_activo(db, entidad)
        except Exception:
            objetivo = []
    if not objetivo and entidad:
        objetivo = [entidad]

    return service.frecuencia(entidad=entidad, campos=objetivo)
