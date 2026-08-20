"""Histórico de diferidas por causa — Pareto, tendencia e impacto.

Portado de `routes/api.py:562-700`.

La métrica principal es **FRECUENCIA POR INCIDENTES**, en % dentro de la
entidad: cuántas veces ocurre cada causa, no cuántos días dura. El volumen
perdido va aparte, en el bloque `impacto`.

**Degradación: SIEMPRE HTTP 200** — archivo ausente, entidad sin diferidas o
error de lectura devuelven `sin_datos` con su motivo, nunca un 500.

Los datos son HISTÓRICOS y estáticos (ene-2023 → jul-2025), así que el
resultado por entidad se cachea: mismo input, misma salida.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Any, TypedDict

from src.features.diferidas.repositories import DiferidasRepository
from src.shared.db_diferidas import abrir_conexion, ruta_diferidas


class FilaPareto(TypedDict):
    """Una barra del Pareto de causas.

    Tipada explícitamente (y no como `dict[str, Any]`) porque mezcla `str`,
    `int`, `float` y un dict anidado: sin el TypedDict, mypy no puede validar
    ni el `sort` por `total` ni la suma de los años del bucket "Otros".
    """

    grupo: str
    total: int
    pct: float
    anios: dict[str, int]


ANIOS = ("2023", "2024", "2025")
RANGO_TEXTO = "ene-2023 → jul-2025"

TOP_GRUPOS = 8
TOP_CAUSAS_IMPACTO = 6

# Un cambio de menos de medio punto porcentual entre años es ruido, no
# tendencia.
_UMBRAL_TENDENCIA_PP = 0.5

SIN_CLASIFICAR = "Sin clasificar"


def clasificar_tendencia(porcentajes: dict[str, float]) -> str:
    """`empeora` / `mejora` / `estable`, comparando 2025 contra 2024."""
    diferencia = (porcentajes.get("2025") or 0) - (porcentajes.get("2024") or 0)
    if abs(diferencia) <= _UMBRAL_TENDENCIA_PP:
        return "estable"
    return "empeora" if diferencia > 0 else "mejora"


class DiferidasService:
    """Diferidas históricas. Cachea por entidad: los datos no cambian."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, ...], dict[str, Any]] = {}

    def frecuencia(
        self, entidad: str | None = None, campos: list[str] | None = None
    ) -> dict[str, Any]:
        etiqueta = self._etiqueta_alcance(entidad, campos)
        objetivo = [c.upper() for c in (campos or [])]

        ruta = ruta_diferidas()
        if ruta is None:
            return {
                "sin_datos": True,
                "motivo": "BD de diferidas no disponible en este entorno",
                "meta": {"scope_label": etiqueta},
            }

        clave = ((entidad or "").upper(), *sorted(objetivo))
        if clave in self._cache:
            return self._cache[clave]

        try:
            with abrir_conexion(ruta) as conexion:
                repo = DiferidasRepository(conexion)
                incidentes = repo.incidentes(objetivo)
                volumen = repo.volumen_perdido(objetivo)
        except sqlite3.Error as exc:
            # NO se cachea: un fallo transitorio no debe quedar congelado.
            return {
                "sin_datos": True,
                "motivo": f"Error leyendo diferidas: {exc}",
                "meta": {"scope_label": etiqueta},
            }

        total = len(incidentes)
        if not total:
            vacio = {
                "sin_datos": True,
                "meta": {
                    "scope_label": etiqueta,
                    "rango": RANGO_TEXTO,
                    "total_incidentes": 0,
                    "pozos_total": 0,
                },
            }
            # Vacío GENUINO (no transitorio) = estático → cacheable.
            self._cache[clave] = vacio
            return vacio

        resultado = self._componer(incidentes, volumen, total, etiqueta, objetivo)
        self._cache[clave] = resultado
        return resultado

    def _componer(
        self,
        incidentes: list[tuple[Any, ...]],
        volumen: list[tuple[Any, ...]],
        total: int,
        etiqueta: str,
        campos: list[str],
    ) -> dict[str, Any]:
        por_grupo: dict[str, dict[str, int]] = defaultdict(
            lambda: dict.fromkeys(ANIOS, 0)
        )
        por_causa: dict[str, dict[str, int]] = defaultdict(
            lambda: dict.fromkeys(ANIOS, 0)
        )
        pozos_totales: set[str] = set()
        pozos_por_grupo: dict[str, set[str]] = defaultdict(set)

        for pozo, causa_n4, grupo_n2, anio in incidentes:
            grupo = grupo_n2 or SIN_CLASIFICAR
            causa = causa_n4 or SIN_CLASIFICAR
            if anio in por_grupo[grupo]:
                por_grupo[grupo][anio] += 1
            if anio in por_causa[causa]:
                por_causa[causa][anio] += 1
            pozos_totales.add(pozo)
            pozos_por_grupo[grupo].add(pozo)

        return {
            "pareto": self._pareto(por_grupo, total),
            "tendencia": self._tendencia(por_causa),
            "pozos_por_grupo": sorted(
                [
                    {"grupo": grupo, "pozos": len(pozos)}
                    for grupo, pozos in pozos_por_grupo.items()
                ],
                key=lambda x: -x["pozos"],
            ),
            "impacto": {
                "CRUDO": self._impacto(volumen, 1),
                "GAS": self._impacto(volumen, 2),
            },
            "meta": {
                "scope_label": etiqueta,
                "rango": RANGO_TEXTO,
                "total_incidentes": total,
                "pozos_total": len(pozos_totales),
                "campos": campos,
            },
        }

    def _pareto(
        self, por_grupo: dict[str, dict[str, int]], total: int
    ) -> list[FilaPareto]:
        """Grupos de causa (N2), apilados por año, en % de incidentes."""
        pareto: list[FilaPareto] = [
            FilaPareto(
                grupo=grupo,
                total=sum(anios.values()),
                pct=round(sum(anios.values()) / total * 100, 1),
                anios=anios,
            )
            for grupo, anios in por_grupo.items()
        ]
        pareto.sort(key=lambda x: -x["total"])

        if len(pareto) > TOP_GRUPOS:
            resto = pareto[TOP_GRUPOS:]
            pareto = pareto[:TOP_GRUPOS]
            total_resto = sum(x["total"] for x in resto)
            pareto.append(
                FilaPareto(
                    grupo="Otros",
                    total=total_resto,
                    pct=round(total_resto / total * 100, 1),
                    anios={
                        anio: sum(x["anios"][anio] for x in resto) for anio in ANIOS
                    },
                )
            )
        return pareto

    def _tendencia(self, por_causa: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
        """Tipos de causa (N4) que EMPEORARON en 2025 vs 2024.

        Decisión del usuario 2026-07-24: la tarjeta muestra únicamente lo que
        se deterioró — sin "mejora", "estable" ni un bucket "Otros".
        """
        total_por_anio = {
            anio: sum(causa[anio] for causa in por_causa.values()) for anio in ANIOS
        }

        filas: list[dict[str, Any]] = []
        for causa, conteos in por_causa.items():
            porcentajes = {
                anio: (
                    round(conteos[anio] / total_por_anio[anio] * 100, 1)
                    if total_por_anio[anio]
                    else 0.0
                )
                for anio in ANIOS
            }
            filas.append(
                {
                    "causa": causa,
                    "pct": porcentajes,
                    "tendencia": clasificar_tendencia(porcentajes),
                }
            )

        filas.sort(key=lambda x: -x["pct"]["2025"])
        return [f for f in filas if f["tendencia"] == "empeora"]

    def _impacto(self, volumen: list[tuple[Any, ...]], indice: int) -> dict[str, Any]:
        """Volumen perdido por causa: top-6 + 'Otros'.

        Crudo = `ACEITE_PERDIDO` (bbl). Gas = `GAS_PERDIDO`, en la misma unidad
        que la producción (verificado: la fracción perdido/producido da
        0,4-0,8 %, la misma banda que el crudo). Blancos no tiene columna de
        volumen, así que ese panel conserva "pozos afectados".
        """
        valores = [
            (str(fila[0] or SIN_CLASIFICAR), float(fila[indice] or 0))
            for fila in volumen
        ]
        valores = [(causa, valor) for causa, valor in valores if valor > 0]
        total = sum(valor for _causa, valor in valores)
        if not total:
            return {"total": 0, "causas": []}

        valores.sort(key=lambda x: -x[1])
        causas: list[dict[str, Any]] = [
            {"causa": causa, "vol": round(valor), "pct": round(valor / total * 100, 1)}
            for causa, valor in valores[:TOP_CAUSAS_IMPACTO]
        ]

        resto = valores[TOP_CAUSAS_IMPACTO:]
        if resto:
            volumen_resto = sum(valor for _causa, valor in resto)
            causas.append(
                {
                    "causa": "Otros",
                    "vol": round(volumen_resto),
                    "pct": round(volumen_resto / total * 100, 1),
                    "n_otros": len(resto),
                }
            )
        return {"total": round(total), "causas": causas}

    def _etiqueta_alcance(self, entidad: str | None, campos: list[str] | None) -> str:
        if entidad:
            return entidad
        if campos:
            resumen = ", ".join(campos[:3])
            return resumen + ("…" if len(campos) > 3 else "")
        return "ECP (global)"
