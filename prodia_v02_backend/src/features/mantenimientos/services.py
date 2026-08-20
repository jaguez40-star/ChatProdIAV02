"""Eventos de servicio a pozo que solapan el mes analizado.

Portado de `routes/api.py:468-559`.

**A3 — el criterio es SOLAPE CON EL MES, no "vigentes vs hoy".** El archivo es
un snapshot cuyo grueso ya cerró: filtrar contra la fecha actual deja **3
eventos en TODA la compañía**, mientras que el mes que analiza el panel
(mayo 2026) tiene **2.741 en 92 campos**. Además así el panel comparte marco
temporal con el resto del análisis.

**Degradación: SIEMPRE HTTP 200.** Un archivo ausente o un periodo ilegible no
son errores del servidor — el panel muestra su mensaje y el resto sigue.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.features.mantenimientos.repositories import (
    EventoOW,
    MantenimientosRepository,
    normalizar,
)

MESES_ES = [
    "",
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
]

# Se listan los 8 más relevantes; el resto se resume en el contador.
TOP_EVENTOS = 8


def parsear_periodo(periodo: str | None) -> tuple[int, int] | None:
    """`'2026-05'` o `'Mayo 2026'` → `(2026, 5)`. `None` si no se puede derivar.

    🔑 Valida el RANGO, no solo el formato: `'2026-13'` calza el patrón pero
    `datetime(y, 13, 1)` lanza `ValueError`, lo que rompería el contrato de
    "siempre 200" con un 500. Un mes fuera de 1-12 se trata como periodo no
    derivable y cae a la degradación ya prevista.
    """
    texto = (periodo or "").strip()
    if not texto:
        return None

    anio: int | None = None
    mes: int | None = None

    if (
        len(texto) == 7
        and texto[4] == "-"
        and texto[:4].isdigit()
        and texto[5:].isdigit()
    ):
        anio, mes = int(texto[:4]), int(texto[5:])
    else:
        partes = texto.split()
        if len(partes) == 2 and partes[1].isdigit():
            nombre = partes[0].capitalize()
            if nombre in MESES_ES:
                anio, mes = int(partes[1]), MESES_ES.index(nombre)

    if anio is None or mes is None:
        return None
    if not (1 <= mes <= 12) or not (1900 <= anio <= 2999):
        return None
    return anio, mes


def solapa_el_mes(evento: EventoOW, inicio_mes: datetime, fin_mes: datetime) -> bool:
    """A3: empezó antes de que el mes terminara Y (sigue abierto O cerró
    después de que el mes empezó)."""
    return evento["inicio"] < fin_mes and (
        evento["fin"] is None or evento["fin"] >= inicio_mes
    )


def _fecha_corta(momento: datetime | None) -> str:
    return f"{momento.day} {MESES_ES[momento.month][:3]}" if momento else "—"


class MantenimientosService:
    """Eventos de servicio a pozo. Degrada siempre con HTTP 200."""

    def __init__(self, repo: MantenimientosRepository) -> None:
        self._repo = repo

    def eventos(
        self,
        entidad: str | None = None,
        campos: list[str] | None = None,
        periodo: str | None = None,
    ) -> dict[str, Any]:
        etiqueta = self._etiqueta_alcance(entidad, campos)

        eventos = self._repo.eventos()
        if eventos is None:
            return {
                "sin_datos": True,
                "motivo": "Archivo de eventos no disponible en este entorno",
                "meta": {"scope_label": etiqueta},
            }

        objetivo = {normalizar(c) for c in (campos or [])}
        base = [e for e in eventos if not objetivo or e["campo"] in objetivo]

        periodo_resuelto = parsear_periodo(periodo)
        if periodo_resuelto is None:
            # Sin periodo utilizable: se cae al mes más reciente CON eventos,
            # que es más útil que no mostrar nada.
            if not base:
                return {
                    "sin_datos": True,
                    "motivo": None,
                    "meta": {"scope_label": etiqueta},
                }
            ultimo = max(e["inicio"] for e in base)
            periodo_resuelto = (ultimo.year, ultimo.month)

        anio, mes = periodo_resuelto
        inicio_mes = datetime(anio, mes, 1)
        fin_mes = datetime(anio + 1, 1, 1) if mes == 12 else datetime(anio, mes + 1, 1)

        solapan = [e for e in base if solapa_el_mes(e, inicio_mes, fin_mes)]
        if not solapan:
            return {
                "sin_datos": True,
                "motivo": None,
                "meta": {
                    "scope_label": etiqueta,
                    "periodo": f"{MESES_ES[mes]} {anio}",
                },
            }

        # Abiertos primero (lo que sigue corriendo); dentro de cada grupo, el
        # más reciente arriba.
        solapan.sort(key=lambda e: (e["fin"] is not None, -e["inicio"].timestamp()))
        top = solapan[:TOP_EVENTOS]

        return {
            "sin_datos": False,
            "eventos": [
                {
                    "pozo": e["pozo"],
                    "tipo": e["tipo"],
                    "estado": "abierto" if e["fin"] is None else "cerrado",
                    "inicio": _fecha_corta(e["inicio"]),
                    "fin": _fecha_corta(e["fin"]),
                }
                for e in top
            ],
            "meta": {
                "scope_label": etiqueta,
                "periodo": f"{MESES_ES[mes]} {anio}",
                "total": len(solapan),
                "mostrados": len(top),
                "abiertos": sum(1 for e in solapan if e["fin"] is None),
            },
        }

    def _etiqueta_alcance(self, entidad: str | None, campos: list[str] | None) -> str:
        if entidad:
            return entidad
        if campos:
            resumen = ", ".join(campos[:3])
            return resumen + ("…" if len(campos) > 3 else "")
        return "ECP (global)"
