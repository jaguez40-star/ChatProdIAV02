"""DTOs del EBITDA Inspector."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TipoComponente = Literal["total", "delta"]


class ComponenteOut(BaseModel):
    """Una barra del waterfall.

    `type` distingue las barras ACUMULADAS (Ingresos, EBITDA, EBIT, NOPAT) de
    los movimientos que las conectan. El frontend las pinta distinto: un total
    arranca desde cero, un delta desde donde quedó el anterior.
    """

    key: str = Field(..., description="Clave estable.", examples=["ebitda"])
    label: str = Field(..., description="Etiqueta legible.", examples=["EBITDA"])
    value_kusd: float = Field(..., description="Valor en miles de USD, con signo.")
    value_usd_bl: float = Field(
        ..., description="USD por barril. 0 si no hay barriles en el periodo."
    )
    type: TipoComponente = Field(..., description="total | delta.")


class MetaEbitdaOut(BaseModel):
    year: int
    month: int
    nivel: str = Field(..., description="global | activo | campo.")
    entidad: str | None = None
    producto: str = Field(
        "CRUDO",
        description="El waterfall económico solo aplica a crudo (variante _a).",
    )
    unidad_default: str = "USD/BI"


class WaterfallOut(BaseModel):
    components: list[ComponenteOut]
    total_bls: float = Field(..., description="Barriles del periodo y ámbito.")
    meta: MetaEbitdaOut
