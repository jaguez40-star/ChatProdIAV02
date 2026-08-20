"""Lógica de la Fundación de datos — catálogo, densidad, huella y cobertura.

Portado de `INGESTA/Rep_Prod/backend/app/features/analisis/api.py:20-348`,
donde vivía dentro de los endpoints. Aquí baja a la capa de servicio (molde
`tablas`: el router no calcula).
"""

from __future__ import annotations

import calendar
from collections import OrderedDict
from datetime import date
from typing import Any

from src.features.analisis.repositories_catalogo import CatalogoRepository
from src.features.analisis.schemas import (
    CardinalidadOut,
    CatalogoOut,
    CategoriaCoberturaOut,
    CoberturaOut,
    ColisionOut,
    DensidadOut,
    DiaDensidadOut,
    FamiliaSemaforoOut,
    HojaCoberturaOut,
    HuellaOut,
    MesDensidadOut,
    ProductoValidoOut,
    ResumenColisionesOut,
    ResumenDensidadOut,
    SerieHuellaOut,
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

# Mapeo dim_tipo_producto → término de negocio del conversacional.
# 'agua' NO existe en dim_tipo_producto (solo CRUDO/GAS/BLANCOS) → se rechaza
# en el slot-filling.
PRODUCTOS_VALIDOS = [
    {"termino": "aceite", "dim": "CRUDO"},
    {"termino": "gas", "dim": "GAS"},
    {"termino": "blancos", "dim": "BLANCOS"},
]

ORDEN_NIVELES = ["vicepresidencia", "gerencia", "activo", "area", "campo", "fuente"]

# Categorías de hoja, en orden de prioridad: una hoja que cae en dos se queda
# con la más específica (la de índice menor).
CATEGORIAS_COBERTURA = [
    "Producción ECP",
    "Filiales",
    "Comentarios",
    "Hojas modeladas (visor)",
    "Preservada en crudo (Bronze)",
]

_DESTINOS_ECP = {
    "core.fact_produccion_dia_ecp",
    "core.fact_produccion_mes_ecp",
    "core.fact_programa_ecp",
}
_DESTINOS_FILIALES = {
    "core.fact_produccion_diaria",
    "core.fact_plan_mensual",
    "core.fact_promedio_validado",
}

# Umbrales del semáforo: 20 días continuos habilitan tendencias; menos de 7 no.
_RACHA_VERDE = 20
_RACHA_AMARILLA = 7


def severidad(niveles: list[str]) -> str:
    """Regla de contrapregunta del chat: dura/media contrapregunta, blanda
    aplica el default 'campo' con aviso.

    `gerencia` se trata como DURA: agrega muchos campos y pozos, o sea la misma
    magnitud de ambigüedad que 'activo'.
    """
    if "activo" in niveles or "gerencia" in niveles:
        return "dura"  # colisiona en gran agregación (cientos de pozos vs uno)
    if "area" in niveles:
        return "media"  # colisiona area+campo
    return "blanda"  # típicamente campo <-> fuente


def _categoria_de(destino: str | None) -> str:
    tabla = (destino or "").lower()
    if tabla in _DESTINOS_ECP:
        return "Producción ECP"
    if tabla in _DESTINOS_FILIALES:
        return "Filiales"
    if tabla == "core.fact_comentarios_produccion":
        return "Comentarios"
    if tabla == "core.fact_tabla_hoja":
        return "Hojas modeladas (visor)"
    return "Preservada en crudo (Bronze)"


def _contar_hojas_con_entidad(por_hoja: dict[str, dict[str, Any]]) -> int:
    """Hojas donde la entidad aparece en al menos un reporte."""
    total = 0
    for datos in por_hoja.values():
        presentes = datos["reportes_entidad"] or 0
        if int(presentes) > 0:
            total += 1
    return total


class CatalogoService:
    """Fundación de datos. Solo lectura, sin LLM."""

    def __init__(self, repo: CatalogoRepository) -> None:
        self._repo = repo

    # ── Catálogo ─────────────────────────────────────────────────────────────

    def catalogo(self) -> CatalogoOut:
        conteos = {
            str(fila["nivel"]): int(fila["n"]) for fila in self._repo.cardinalidad()
        }
        conteos["vicepresidencia"] = self._repo.total_vicepresidencias()

        colisiones: list[ColisionOut] = []
        resumen = {"dura": 0, "media": 0, "blanda": 0}
        for fila in self._repo.colisiones():
            niveles = [str(n) for n in fila["niveles"]]
            sev = severidad(niveles)
            resumen[sev] += 1
            colisiones.append(
                ColisionOut(
                    nombre=str(fila["nombre"]),
                    niveles=niveles,
                    n_niveles=int(fila["n_niveles"]),
                    severidad=sev,  # type: ignore[arg-type]
                )
            )

        return CatalogoOut(
            cardinalidad=[
                CardinalidadOut(nivel=n, n=conteos.get(n, 0)) for n in ORDEN_NIVELES
            ],
            productos_validos=[ProductoValidoOut(**p) for p in PRODUCTOS_VALIDOS],
            colisiones=colisiones,
            resumen_colisiones=ResumenColisionesOut(**resumen, total=len(colisiones)),
            filiales=self._repo.filiales(),
            entidades_por_nivel=self._repo.entidades_por_nivel(),
        )

    # ── Densidad ─────────────────────────────────────────────────────────────

    def densidad(self, entidad: str | None = None) -> DensidadOut:
        """Auditoría de densidad temporal sobre `fact_produccion_dia_ecp`.

        Vicepresidencias y filiales NO tienen grano diario ECP: en ese caso
        `aplica_ecp=False` y la serie va vacía. **No es un error** — es la
        respuesta correcta, y el frontend la explica.
        """
        aplica_ecp = True
        filas: Any = []

        if entidad:
            objetivo = entidad.strip().upper()
            ids = self._repo.fuentes_de_entidad(objetivo)
            vice_id = self._repo.vice_id_de(objetivo)
            if ids or vice_id is not None:
                filas = self._repo.densidad_de_entidad(ids, vice_id)
                if not filas:
                    # Entidad reconocida pero sin filas a grano diario ECP.
                    aplica_ecp = False
            else:
                aplica_ecp = False
        else:
            filas = self._repo.densidad_global()

        dias = [
            DiaDensidadOut(
                fecha=fila["fecha"].isoformat(),
                filas=int(fila["filas"]),
                fuentes=int(fila["fuentes"]),
            )
            for fila in filas
        ]
        fechas: list[date] = [fila["fecha"] for fila in filas]

        # Huecos por mes: días del mes sin ningún dato.
        por_mes_map: OrderedDict[tuple[int, int], set[int]] = OrderedDict()
        for fecha in fechas:
            por_mes_map.setdefault((fecha.year, fecha.month), set()).add(fecha.day)

        por_mes: list[MesDensidadOut] = []
        huecos_totales = 0
        for (anio, mes), dias_con_dato in por_mes_map.items():
            dias_del_mes = calendar.monthrange(anio, mes)[1]
            huecos = dias_del_mes - len(dias_con_dato)
            huecos_totales += huecos
            por_mes.append(
                MesDensidadOut(
                    anio=anio,
                    mes=mes,
                    mes_nombre=MESES_ES[mes],
                    dias_con_data=len(dias_con_dato),
                    dias_del_mes=dias_del_mes,
                    huecos=huecos,
                    rango=[
                        f"{anio:04d}-{mes:02d}-{min(dias_con_dato):02d}",
                        f"{anio:04d}-{mes:02d}-{max(dias_con_dato):02d}",
                    ],
                )
            )

        # Racha máxima de días CONSECUTIVOS: es lo que habilita tendencias.
        racha_maxima = 0
        actual = 0
        anterior: date | None = None
        for fecha in fechas:
            actual = (
                actual + 1
                if (anterior is not None and (fecha - anterior).days == 1)
                else 1
            )
            racha_maxima = max(racha_maxima, actual)
            anterior = fecha

        nivel = (
            "verde"
            if racha_maxima >= _RACHA_VERDE
            else ("amarillo" if racha_maxima >= _RACHA_AMARILLA else "rojo")
        )

        # Semáforo por las 5 familias estadísticas, en orden canónico.
        # Movimiento y Anomalías dependen de la racha de días CONTINUOS; las
        # otras 3 funcionan con cualquier dato.
        semaforo = [
            FamiliaSemaforoOut(
                familia="La foto (totales/promedios/rankings)",
                nivel="verde",
                necesita_continuidad=False,
            ),
            FamiliaSemaforoOut(
                familia="El movimiento (Δ%, tendencias, rachas)",
                nivel=nivel,  # type: ignore[arg-type]
                necesita_continuidad=True,
            ),
            FamiliaSemaforoOut(
                familia="Concentración / Pareto",
                nivel="verde",
                necesita_continuidad=False,
            ),
            FamiliaSemaforoOut(
                familia="Anomalías (z-scores, cierres, outliers)",
                nivel=nivel,  # type: ignore[arg-type]
                necesita_continuidad=True,
            ),
            FamiliaSemaforoOut(
                familia="Descomposición del cambio (waterfall)",
                nivel="verde",
                necesita_continuidad=False,
            ),
        ]

        return DensidadOut(
            entidad=entidad,
            aplica_ecp=aplica_ecp,
            dias=dias,
            por_mes=por_mes,
            resumen=ResumenDensidadOut(
                total_dias=len(fechas),
                rango=(
                    [fechas[0].isoformat(), fechas[-1].isoformat()]
                    if fechas
                    else [None, None]
                ),
                huecos_totales=huecos_totales,
                racha_maxima=racha_maxima,
            ),
            semaforo=semaforo,
        )

    # ── Huella ───────────────────────────────────────────────────────────────

    def huella(self, entidad: str | None = None) -> HuellaOut:
        """Huella de datos por fact/escenario.

        Es METADATA (conteo de FILAS, no barriles): muestra en qué facts
        estructurados vive una entidad y con qué escenarios. NO consulta
        `fact_tabla_hoja` (P50/DPP/Whatsapp): esas son hojas derivadas, fuera
        del alcance.
        """
        self._repo.fijar_timeout("40s")
        series: list[SerieHuellaOut] = []

        if entidad:
            objetivo = entidad.strip().upper()
            ids = self._repo.fuentes_para_huella(objetivo)
            if not ids:
                return HuellaOut(entidad=entidad, encontrada=False, series=[])

            series.append(
                SerieHuellaOut(
                    fuente="REAL diario",
                    grupo="dia",
                    filas=self._repo.contar_dia_ecp(ids),
                    hoja="BDP_datos_dia",
                )
            )
            for fila in self._repo.mes_ecp_por_escenario(ids):
                series.append(
                    SerieHuellaOut(
                        fuente=f"Mes {fila['nombre']}",
                        grupo="mes",
                        filas=int(fila["filas"]),
                        hoja="BDP_datos_mes",
                    )
                )
            series.append(
                SerieHuellaOut(
                    fuente="Programa",
                    grupo="programa",
                    filas=self._repo.contar_programa(ids, objetivo),
                    hoja="BDP_Programa",
                )
            )
            return HuellaOut(entidad=entidad, encontrada=True, series=series)

        # Panorama global.
        series.append(
            SerieHuellaOut(
                fuente="REAL diario",
                grupo="dia",
                filas=self._repo.contar_dia_ecp(),
                hoja="BDP_datos_dia",
            )
        )
        for fila in self._repo.mes_ecp_por_escenario():
            series.append(
                SerieHuellaOut(
                    fuente=f"Mes {fila['nombre']}",
                    grupo="mes",
                    filas=int(fila["filas"]),
                    hoja="BDP_datos_mes",
                )
            )
        series.append(
            SerieHuellaOut(
                fuente="Programa",
                grupo="programa",
                filas=self._repo.contar_programa(),
                hoja="BDP_Programa",
            )
        )
        return HuellaOut(entidad=None, encontrada=True, series=series)

    # ── Cobertura ────────────────────────────────────────────────────────────

    def _presencia_de_entidad(self, entidad: str) -> dict[str, int]:
        """{hoja: nº de reportes donde aparece la entidad}.

        RAW (BDP_datos_dia/mes/Programa) vía facts ECP, resolviendo por fuente
        (incluido `operador` → filiales como Hocol) y por `vice_id` — MISMO
        criterio que `densidad`, para que ambos módulos coincidan. El resto vía
        `bronze.hoja_landing`, sin tocar los 62M de filas.
        """
        objetivo = (entidad or "").strip().upper()
        ids = self._repo.fuentes_de_entidad(objetivo)
        vice_id = self._repo.vice_id_de(objetivo)

        presencia: dict[str, int] = {
            "BDP_datos_dia": self._repo.presencia_en_facts(
                "fact_produccion_dia_ecp", ids, vice_id
            ),
            "BDP_datos_mes": self._repo.presencia_en_facts(
                "fact_produccion_mes_ecp", ids, vice_id
            ),
            "BDP_Programa": self._repo.presencia_en_facts(
                "fact_programa_ecp",
                ids,
                vice_id,
                extra_cond="UPPER(TRIM(campo))=:e OR UPPER(TRIM(area))=:e",
                entidad=objetivo,
            ),
        }

        # Escape de comodines: un nombre con `%` o `_` haría un ILIKE que
        # calzaría de más y contaría reportes ajenos.
        patron = (
            "%"
            + objetivo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            + "%"
        )
        for fila in self._repo.presencia_en_landing(patron):
            presencia[str(fila["hoja"])] = int(fila["reps"])
        return presencia

    def cobertura(self, entidad: str | None = None) -> CoberturaOut:
        """Mapa de cobertura del reporte: TODAS las hojas por categoría."""
        self._repo.fijar_timeout("60s")
        prioridad = {c: i for i, c in enumerate(CATEGORIAS_COBERTURA)}

        por_hoja: dict[str, dict[str, Any]] = {}
        for fila in self._repo.hojas_de_ingesta():
            hoja = str(fila["hoja"] or "(sin nombre)")
            categoria = _categoria_de(fila["tabla_destino"])
            actual = por_hoja.get(hoja)
            if actual is None or prioridad[categoria] < prioridad[actual["categoria"]]:
                por_hoja[hoja] = {
                    "hoja": hoja,
                    "categoria": categoria,
                    "reportes_total": int(fila["reps"]),
                    "reportes_entidad": None,
                }

        if entidad:
            presencia = self._presencia_de_entidad(entidad)
            for datos in por_hoja.values():
                datos["reportes_entidad"] = int(presencia.get(datos["hoja"], 0))

        def _orden(datos: dict[str, Any]) -> int:
            """Ordena por presencia de la entidad si se filtró; si no, por el
            total de reportes. Descendente en ambos casos."""
            valor = datos["reportes_entidad"]
            if valor is None:
                valor = datos["reportes_total"]
            return -int(valor)

        agrupadas: OrderedDict[str, list[HojaCoberturaOut]] = OrderedDict(
            (categoria, []) for categoria in CATEGORIAS_COBERTURA
        )
        for datos in sorted(por_hoja.values(), key=_orden):
            agrupadas[datos["categoria"]].append(HojaCoberturaOut(**datos))

        return CoberturaOut(
            entidad=entidad,
            total_hojas=len(por_hoja),
            categorias=[
                CategoriaCoberturaOut(categoria=c, hojas=h)
                for c, h in agrupadas.items()
                if h
            ],
            hojas_con_entidad=(
                sum(1 for d in por_hoja.values() if (d["reportes_entidad"] or 0) > 0)
                if entidad
                else None
            ),
        )
