"""Lógica del EBITDA Inspector — aplicación de signos y USD/BI."""

from __future__ import annotations

from typing import Any

from src.features.ebitda.repositories import COMPONENTES, EbitdaRepository
from src.features.ebitda.schemas import (
    ComponenteOut,
    MetaEbitdaOut,
    WaterfallOut,
)


def aplicar_signo(valor: float, modo: str) -> float:
    """Lleva el valor guardado al signo que le toca en el waterfall.

    Los cuatro modos existen porque la BD guarda cada familia de conceptos con
    una convención distinta; unificarlos aquí es lo que hace que el gráfico
    cuadre. Ver el detalle en `repositories.COMPONENTES`.
    """
    if modo == "negabs":
        return -abs(valor)
    if modo == "neg":
        return -valor
    return valor  # pos / asis


class EbitdaService:
    """Waterfall Ingresos → EBITDA → EBIT → NOPAT. Solo lectura."""

    def __init__(self, repo: EbitdaRepository) -> None:
        self._repo = repo

    def waterfall(
        self,
        anio: int,
        mes: int,
        nivel: str | None = None,
        entidad: str | None = None,
    ) -> WaterfallOut:
        nivel_norm = (nivel or "").strip().lower()

        # `entidad` puede traer varios valores separados por "|": un foco
        # agrupa N campos, igual que en Diferidas.
        entidades = (
            [v.strip().upper() for v in str(entidad).split("|") if v.strip()]
            if entidad
            else []
        )

        fila = self._repo.waterfall(anio, mes, nivel_norm, entidades)
        datos: dict[str, Any] = dict(fila) if fila else {}
        barriles = float(datos.get("total_bls") or 0)

        componentes: list[ComponenteOut] = []
        for label, clave, _tabla, _columna, tipo, modo in COMPONENTES:
            valor = aplicar_signo(float(datos.get(clave) or 0), modo)
            componentes.append(
                ComponenteOut(
                    key=clave,
                    label=label,
                    value_kusd=round(valor),
                    # kUSD → USD, dividido entre los barriles del ámbito.
                    # Sin barriles se declara 0: dividir daría infinito.
                    value_usd_bl=(
                        round(valor * 1000 / barriles, 2) if barriles else 0.0
                    ),
                    type=tipo,
                )
            )

        return WaterfallOut(
            components=componentes,
            total_bls=round(barriles),
            meta=MetaEbitdaOut(
                year=anio,
                month=mes,
                nivel=nivel_norm or "global",
                entidad=entidad or None,
                producto="CRUDO",
                unidad_default="USD/BI",
            ),
        )
