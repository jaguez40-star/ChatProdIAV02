"""Panel del segmento FILIALES y tarjeta P50 (president).

Portado de `INGESTA/Rep_Prod/backend/app/features/analisis/api.py:2001-2619`.

⚠️ **Las filiales NO tienen presupuesto.** Dos bases de comparación conviven, y
cada una responde a una pregunta distinta:

- **PROGRAMA misma-ventana** → los KPIs y el gap por empresa. Responde "¿cómo
  vamos contra lo programado en los días que llevamos?".
- **PROMEDIO 2026** → las tarjetas y los focos. Responde "¿este mes va mejor o
  peor que nuestro año?". El mes en curso se lleva a proyección de cierre para
  comparar mes-completo contra mes-completo (Opción B del usuario, 2026-07-21).

Mezclarlas fue el bug original: el bloque central usaba la primera y las
tarjetas la segunda, así que Permian salía como "excedente en crudo" mientras
su tarjeta lo marcaba 148k por debajo.
"""

from __future__ import annotations

import calendar
from typing import Any

from src.features.analisis.repositories_filiales import FilialesRepository
from src.features.analisis.services_catalogo import MESES_ES
from src.features.analisis.services_desempeno import PRODUCTOS
from src.features.analisis.services_ejecutivo import (
    ETIQUETAS_ESTADO,
    componer_secciones,
    detectar_valle,
    estado,
    flags_ejecutivo,
    tarjetas_kpi,
)
from src.features.analisis.services_filiales import (
    BANDA_EN_LINEA_PCT,
    focos_filiales,
    sin_foco_filiales,
)

ALCANCE_FILIALES = "Filiales (Hocol · America · Permian)"

_TOP_DETRACTORES = 3
_TOP_COMPENSADORES = 2
_DESFASE_MAX_PCT = 2.0

# Un mes con menos del 60 % de sus días no entra en la serie de tendencia: uno
# con 1 día (Nov-2025 en el corpus real) la distorsionaría por completo.
_COBERTURA_MINIMA_MES = 0.6


class FilialesService:
    """Panel de filiales. Solo lectura, sin LLM (composer determinista)."""

    def __init__(self, repo: FilialesRepository) -> None:
        self._repo = repo

    # ── Intermedios comunes ──────────────────────────────────────────────────

    def _intermedios(self) -> dict[str, Any] | None:
        """Bloques compartidos por desempeño, insight y ejecutivo de filiales.

        Devuelve `None` si no hay REAL diario — el llamador responde
        `sin_datos`, que no es un error.
        """
        max_fecha = self._repo.max_fecha_real()
        if max_fecha is None:
            return None

        anio, mes = max_fecha.year, max_fecha.month
        dias_del_mes = calendar.monthrange(anio, mes)[1]
        ini = f"{anio:04d}-{mes:02d}-01"
        fin = f"{anio:04d}-{mes:02d}-{dias_del_mes:02d}"
        ndias = self._repo.dias_con_real(ini, fin)

        kpis: dict[str, dict[str, float]] = {}
        for fila in self._repo.kpis_misma_ventana(ini, fin):
            kpis[str(fila["prod"])] = {
                "REAL": float(fila["real_mtd"] or 0),
                "PROG": float(fila["prog_mtd"] or 0),
            }

        titular: list[dict[str, Any]] = []
        for producto in PRODUCTOS:
            real = kpis.get(producto, {}).get("REAL", 0.0)
            programa = kpis.get(producto, {}).get("PROG", 0.0)
            pct = round(real / programa * 100.0, 1) if programa else None
            chip = estado(pct)
            # `ppto` guarda la META (=PROGRAMA misma-ventana) para reutilizar el
            # frontend sin cambiar claves.
            titular.append(
                {
                    "producto": producto,
                    "real": real,
                    "ppto": programa,
                    "valor_pct": pct,
                    "estado": chip,
                    "texto": ETIQUETAS_ESTADO.get(chip, "—"),
                }
            )

        por_fecha: dict[str, dict[str, float]] = {}
        for fila in self._repo.curva_diaria(ini, fin):
            iso = fila["fecha"].isoformat()
            por_fecha.setdefault(iso, {})[str(fila["prod"])] = float(fila["vol"] or 0)
        fechas = sorted(por_fecha.keys())
        series = {
            p: [por_fecha.get(f, {}).get(p, 0.0) for f in fechas] for p in PRODUCTOS
        }

        serie_crudo = [(f, por_fecha.get(f, {}).get("CRUDO", 0.0)) for f in fechas]
        valle = detectar_valle(serie_crudo)
        anotaciones = None
        if valle:
            anotaciones = {
                "banda": {
                    "desde": valle["desde"],
                    "hasta": valle["hasta"],
                    "label": "valle",
                },
                "punto": {
                    "fecha": valle["min_fecha"],
                    "valor": valle["min_valor"],
                    "label": f"mín · {valle['min_valor'] / 1e6:.2f}M",
                },
            }

        gap_full: dict[str, dict[str, Any]] = {}
        for kpi_producto in titular:
            if kpi_producto["valor_pct"] is not None:
                gap_full[kpi_producto["producto"]] = self._gap_empresa(
                    ini,
                    fin,
                    kpi_producto["producto"],
                    kpi_producto["real"] - kpi_producto["ppto"],
                )
        gap_lag = {
            p: g
            for p, g in gap_full.items()
            if next(t["valor_pct"] for t in titular if t["producto"] == p) < 100
        }

        pace = None
        if serie_crudo:
            acumulado = sum(v for _f, v in serie_crudo)
            restantes = dias_del_mes - ndias
            programa_total = self._repo.programa_mes_completo(ini, fin)
            if restantes > 0 and programa_total and ndias:
                promedio = acumulado / ndias
                requerido = (programa_total - acumulado) / restantes
                pace = {
                    "mtd": round(acumulado),
                    "dias": ndias,
                    "restantes": restantes,
                    "promedio_dia": round(promedio),
                    "requerido_dia": round(requerido),
                    "delta_pct": (
                        round((requerido / promedio - 1) * 100, 1) if promedio else None
                    ),
                }

        promedio_2026 = {
            str(fila["prod"]).strip(): round(float(fila["promedio"] or 0))
            for fila in self._repo.promedio_mensual_del_anio(anio, ini)
        }

        flags = flags_ejecutivo(
            titular, gap_lag, valle, pace, serie_crudo[-1][0] if serie_crudo else None
        )

        return {
            "anio": anio,
            "mes": mes,
            "dias_del_mes": dias_del_mes,
            "ndias": ndias,
            "ini": ini,
            "fin": fin,
            "promedio_2026": promedio_2026,
            "periodo": f"{MESES_ES[mes]} {anio}",
            "corte": f"{ndias}/{dias_del_mes}",
            "titular": titular,
            "kpis": kpis,
            "curva_fechas": fechas,
            "series": series,
            "curva_crudo": {
                "fechas": [f for f, _v in serie_crudo],
                "valores": [v for _f, v in serie_crudo],
            },
            "valle": valle,
            "anotaciones": anotaciones,
            "gap_por_producto": gap_full,
            "gap_lag": gap_lag,
            "pace": pace,
            "flags": flags,
        }

    def _gap_empresa(
        self, ini: str, fin: str, producto: str, gap_kpi: float
    ) -> dict[str, Any]:
        """Descomposición del gap por EMPRESA, reconciliada contra el KPI."""
        diferencias = [
            (
                str(fila["campo"] or "").strip(),
                float(fila["vreal"] or 0) - float(fila["vprog"] or 0),
                float(fila["vreal"] or 0),
                float(fila["vprog"] or 0),
            )
            for fila in self._repo.gap_por_empresa(ini, fin, producto)
            if (fila["vreal"] or fila["vprog"])
        ]

        gap_total = sum(d[1] for d in diferencias)
        detractores = sorted([d for d in diferencias if d[1] < 0], key=lambda x: x[1])[
            :_TOP_DETRACTORES
        ]
        compensadores = sorted(
            [d for d in diferencias if d[1] > 0], key=lambda x: -x[1]
        )[:_TOP_COMPENSADORES]

        total_detractores = sum(d[1] for d in diferencias if d[1] < 0)
        concentracion = (
            round(abs(sum(d[1] for d in detractores)) / abs(total_detractores) * 100, 1)
            if total_detractores
            else None
        )
        desfase = (
            round(abs(gap_total - gap_kpi) / abs(gap_kpi) * 100, 1) if gap_kpi else None
        )

        return {
            "producto": producto,
            "gap_kpi": round(gap_kpi),
            "gap_total_campos": round(gap_total),
            "reconciliado": desfase is not None and desfase <= _DESFASE_MAX_PCT,
            "desfase_pct": desfase,
            "concentracion_pct": concentracion,
            "detractores": [
                {
                    "campo": d[0],
                    "gap": round(d[1]),
                    "real": round(d[2]),
                    "meta": round(d[3]),
                }
                for d in detractores
            ],
            "compensadores": [
                {
                    "campo": d[0],
                    "gap": round(d[1]),
                    "real": round(d[2]),
                    "meta": round(d[3]),
                }
                for d in compensadores
            ],
        }

    # ── Tendencia de UNA filial ──────────────────────────────────────────────

    def tendencia_de_filial(self, empresa_id: int) -> dict[str, Any] | None:
        """Proyección de cierre vs promedio 2026, por producto.

        `None` si la filial no tiene REAL diario. Coherente con el panel
        agregado: misma proyección y misma base.
        """
        max_fecha = self._repo.max_fecha_real(empresa_id)
        if max_fecha is None:
            return None

        anio, mes = max_fecha.year, max_fecha.month
        dias_del_mes = calendar.monthrange(anio, mes)[1]
        ini = f"{anio:04d}-{mes:02d}-01"
        fin = f"{anio:04d}-{mes:02d}-{dias_del_mes:02d}"
        ndias = self._repo.dias_con_real(ini, fin, empresa_id)

        acumulado = {
            str(fila["prod"]).strip(): float(fila["tot"] or 0)
            for fila in self._repo.mtd_de_empresa(empresa_id, ini, fin)
        }
        promedio = {
            str(fila["prod"]).strip(): round(float(fila["promedio"] or 0))
            for fila in self._repo.promedio_mensual_del_anio(anio, ini, empresa_id)
        }

        completo = ndias >= dias_del_mes
        por_producto: list[dict[str, Any]] = []
        for producto in PRODUCTOS:
            mtd = acumulado.get(producto, 0.0)
            base = promedio.get(producto, 0.0)
            if mtd == 0 and base == 0:
                # La filial no reporta ese producto: se declara, no se pinta 0.
                por_producto.append({"producto": producto, "reporta": False})
                continue

            proyeccion = (
                mtd if completo else (mtd / ndias * dias_del_mes if ndias else 0.0)
            )
            variacion = round((proyeccion / base - 1) * 100, 1) if base else None
            direccion = (
                None
                if variacion is None
                else (
                    "en línea"
                    if abs(variacion) <= BANDA_EN_LINEA_PCT
                    else ("por encima" if variacion > 0 else "por debajo")
                )
            )
            por_producto.append(
                {
                    "producto": producto,
                    "proyeccion": round(proyeccion),
                    "mtd": round(mtd),
                    "promedio_2026": base,
                    "variacion_pct": variacion,
                    "direccion": direccion,
                    "reporta": True,
                }
            )

        return {
            "empresa_id": empresa_id,
            "y": anio,
            "mo": mes,
            "dim": dias_del_mes,
            "ndias": ndias,
            "periodo": f"{MESES_ES[mes]} {anio}",
            "completo": completo,
            # `n_base` cuenta PRODUCTOS con promedio (se conserva por
            # compatibilidad); `n_meses` cuenta los MESES que lo sostienen.
            "n_base": sum(1 for v in promedio.values() if v),
            "n_meses": self._repo.meses_completos_del_anio(empresa_id, anio, ini),
            "por_producto": por_producto,
        }

    def serie_mensual(self, empresa_id: int, anio: int, mes: int) -> dict[str, Any]:
        """Serie mensual para el gráfico de evolución de una filial.

        - Meses COMPLETOS (>=60 % de días): valor real.
        - Mes EN CURSO: PROYECCIÓN de cierre, marcada en `proyectado_idx` para
          que el frontend la distinga (coherente con las tarjetas, que ya
          proyectan).
        - Meses casi vacíos: excluidos.
        """
        por_mes: dict[Any, dict[str, tuple[float, int]]] = {}
        for fila in self._repo.serie_mensual_de_empresa(empresa_id):
            por_mes.setdefault(fila["m"], {})[str(fila["prod"]).strip()] = (
                float(fila["tot"] or 0),
                int(fila["dias"] or 0),
            )

        meses: list[str] = []
        series: dict[str, list[float | None]] = {p: [] for p in PRODUCTOS}
        proyectado_idx: int | None = None

        for momento in sorted(por_mes):
            dias_del_mes = calendar.monthrange(momento.year, momento.month)[1]
            es_actual = momento.year == anio and momento.month == mes
            dias_reportados = max((v[1] for v in por_mes[momento].values()), default=0)
            if not es_actual and dias_reportados < _COBERTURA_MINIMA_MES * dias_del_mes:
                continue

            meses.append(f"{MESES_ES[momento.month][:3]} {momento.year}")
            for producto in PRODUCTOS:
                if producto in por_mes[momento]:
                    total, dias = por_mes[momento][producto]
                    series[producto].append(
                        round(total / dias * dias_del_mes)
                        if (es_actual and dias)
                        else round(total)
                    )
                else:
                    series[producto].append(None)  # producto no reportado ese mes
            if es_actual:
                proyectado_idx = len(meses) - 1

        return {
            "meses": meses,
            "series": {
                p: v for p, v in series.items() if any(x is not None for x in v)
            },
            "proyectado_idx": proyectado_idx,
            # Doble eje en el frontend: crudo y blancos en bbl, gas en MSCF.
            "unidades": {"CRUDO": "bbl", "GAS": "MSCF", "BLANCOS": "bbl"},
        }

    # ── Endpoints ────────────────────────────────────────────────────────────

    def desempeno(self) -> dict[str, Any]:
        intermedios = self._intermedios()
        if intermedios is None:
            return {"entidad": None, "encontrada": True, "sin_datos": True}

        sin_cierre = not any(intermedios["kpis"].get(p) for p in PRODUCTOS)
        return {
            "entidad": None,
            "encontrada": True,
            "aplica_diario": True,
            "sin_cierre": sin_cierre,
            "mes": {
                "anio": intermedios["anio"],
                "mes": intermedios["mes"],
                "nombre": MESES_ES[intermedios["mes"]],
                "dias_con_data": intermedios["ndias"],
                "dias_del_mes": intermedios["dias_del_mes"],
                "completo": intermedios["ndias"] >= intermedios["dias_del_mes"],
            },
            "por_producto": [
                {
                    "producto": t["producto"],
                    "real": t["real"],
                    "ppto": t["ppto"],
                    "cumplimiento": t["valor_pct"],
                }
                for t in intermedios["titular"]
            ],
            "curva": {
                "fechas": intermedios["curva_fechas"],
                "series": intermedios["series"],
            },
        }

    def desempeno_insight(self) -> dict[str, Any]:
        intermedios = self._intermedios()
        if intermedios is None:
            return {"entidad": None, "encontrada": True, "sin_datos": True}

        peor = min(
            [t for t in intermedios["titular"] if t["valor_pct"] is not None],
            key=lambda t: t["valor_pct"],
            default=None,
        )
        gap_peor = intermedios["gap_por_producto"].get((peor or {}).get("producto"), {})

        return {
            "entidad": None,
            "encontrada": True,
            "meta": {
                "scope": ALCANCE_FILIALES,
                "periodo": intermedios["periodo"],
                "corte": intermedios["corte"],
                "generado_por": "fallback",
            },
            "titular": intermedios["titular"],
            "curva_crudo": intermedios["curva_crudo"],
            "anotaciones": intermedios["anotaciones"],
            # Los comentarios del reporte son de ECP: para filiales no hay
            # eventos que atribuir, y se declara vacío en vez de inventarlos.
            "eventos": [],
            "eventos_extra": {"campos": 0, "pozos_aprox": 0, "fecha": ""},
            "valle_diagnostico": None,
            "gap": {
                "producto": (peor or {}).get("producto"),
                "detractores": gap_peor.get("detractores", []),
                "compensadores": gap_peor.get("compensadores", []),
            },
            "pace_crudo": intermedios["pace"],
            "lectura_ejecutiva": "",
            "accion_sugerida": [],
        }

    def ejecutivo(self) -> dict[str, Any]:
        intermedios = self._intermedios()
        if intermedios is None:
            return {"entidad": None, "encontrada": True, "sin_datos": True}

        titular = intermedios["titular"]
        ndias = intermedios["ndias"]
        dias_del_mes = intermedios["dias_del_mes"]
        promedio_2026 = intermedios["promedio_2026"]

        # TARJETAS (Nivel 1): la meta es el PROMEDIO 2026 y el mes se lleva a
        # PROYECCIÓN de cierre para comparar mes-completo vs mes-completo.
        # Sin ritmo diario (pace=None): las 3 usan la rama "mes vs promedio del
        # año" del frontend. Los FOCOS (Nivel 2) siguen midiendo vs PROGRAMA.
        titular_cards: list[dict[str, Any]] = []
        for fila in titular:
            proyeccion = (fila["real"] / ndias * dias_del_mes) if ndias else 0.0
            meta = promedio_2026.get(fila["producto"], 0.0)
            pct = round(proyeccion / meta * 100.0, 1) if meta else None
            titular_cards.append(
                {
                    "producto": fila["producto"],
                    "real": proyeccion,
                    "ppto": meta,
                    "valor_pct": pct,
                    "estado": estado(pct),
                    "texto": "",
                }
            )

        secciones = componer_secciones(
            intermedios["periodo"],
            titular,
            intermedios["gap_lag"],
            intermedios["valle"],
            intermedios["pace"],
            intermedios["flags"],
            meta_nombre="programa",
            frase_dependencia="riesgo de concentración en pocas filiales",
            frase_prioridad="las filiales que más arrastran",
        )

        # Desglose POR FILIAL con el MISMO motor que el chat → no divergen.
        por_filial: list[dict[str, Any]] = []
        por_filial_raw: list[dict[str, Any]] = []
        for empresa in self._repo.listar_empresas():
            tendencia = self.tendencia_de_filial(int(empresa["empresa_id"]))
            if tendencia is None:
                continue
            reportados = [p for p in tendencia["por_producto"] if p.get("reporta")]
            if not reportados:
                continue

            por_filial_raw.append({"empresa": empresa["nombre"], "t": tendencia})
            promedios = {
                p["producto"]: (p.get("promedio_2026") or 0) for p in reportados
            }
            tarjetas_filial = tarjetas_kpi(
                [
                    {
                        "producto": p["producto"],
                        "real": p["proyeccion"],
                        "ppto": p.get("promedio_2026") or 0,
                        "valor_pct": p.get("variacion_pct"),
                        "estado": "",
                        "texto": "",
                    }
                    for p in reportados
                ],
                None,
                promedios,
            )
            por_filial.append(
                {
                    "empresa": empresa["nombre"],
                    "periodo": tendencia["periodo"],
                    "n_base": tendencia["n_base"],
                    "n_meses": tendencia["n_meses"],
                    "tarjetas": tarjetas_filial,
                }
            )

        return {
            "entidad": None,
            "encontrada": True,
            "por_filial": por_filial,
            "meta": {
                "scope": ALCANCE_FILIALES,
                "periodo": intermedios["periodo"],
                "corte": intermedios["corte"],
                "generado_por": "fallback",
                "llm_diag": {"status": "off"},
            },
            "titular": titular,
            "tarjetas": tarjetas_kpi(titular_cards, None, promedio_2026),
            "gap_por_producto": intermedios["gap_por_producto"],
            "valle": intermedios["valle"],
            "eventos": [],
            "eventos_extra": {"campos": 0, "pozos_aprox": 0},
            "pace_crudo": intermedios["pace"],
            "flags": intermedios["flags"],
            "secciones": secciones,
            # Nivel 2 sobre la MISMA base que las tarjetas (proy vs promedio).
            "focos": focos_filiales(titular_cards, por_filial_raw),
            "sin_foco": sin_foco_filiales(titular_cards, por_filial_raw),
        }

    def tendencia_filial(self, empresa: str) -> dict[str, Any]:
        """Panel EXCLUSIVO de una filial (lo consume también el chat)."""
        empresa_id = self._repo.empresa_id_de(empresa)
        if empresa_id is None:
            return {"entidad": empresa, "encontrada": False}

        tendencia = self.tendencia_de_filial(empresa_id)
        if tendencia is None:
            return {"entidad": empresa, "encontrada": True, "sin_datos": True}
        if tendencia["n_base"] == 0:
            # Sin meses completos previos no hay contra qué comparar: se
            # declara en vez de mostrar una variación sin base.
            return {
                "entidad": empresa,
                "encontrada": True,
                "sin_tendencia": True,
                "periodo": tendencia["periodo"],
            }

        reportados = [p for p in tendencia["por_producto"] if p.get("reporta")]
        promedios = {p["producto"]: (p.get("promedio_2026") or 0) for p in reportados}
        tarjetas = tarjetas_kpi(
            [
                {
                    "producto": p["producto"],
                    "real": p["proyeccion"],
                    "ppto": p.get("promedio_2026") or 0,
                    "valor_pct": p.get("variacion_pct"),
                    "estado": "",
                    "texto": "",
                }
                for p in reportados
            ],
            None,
            promedios,
        )
        serie = self.serie_mensual(empresa_id, tendencia["y"], tendencia["mo"])

        return {
            "entidad": empresa,
            "encontrada": True,
            "tarjetas": tarjetas,
            "serie_mensual": serie,
            **tendencia,
        }

    # ── President (tarjeta P50) ──────────────────────────────────────────────

    def president(self, periodo: str | None = None) -> dict[str, Any]:
        """Tarjeta P50 por producto desde la hoja REPORTE_PRESIDENT.

        Escala **kbpe corporativa** (el mundo P50), NO la del fact diario — es
        el ejemplo canónico de A5: aplicar aquí la conversión de MSCF daría
        "0,03" en vez de "33.453,2", mil veces menor y sin error visible.

        Este endpoint es AGNÓSTICO a la referencia: devuelve todas las medidas y
        el cumplimiento vs P50; qué semáforo usar lo decide el frontend.
        """
        reporte_id = self._repo.reporte_con_president(periodo)
        if not reporte_id:
            return {"encontrada": False}

        fecha = self._repo.fecha_de_reporte(reporte_id)
        medidas: dict[str, dict[str, float]] = {}
        for fila in self._repo.medidas_president(reporte_id):
            medidas.setdefault(str(fila["ent"]), {})[str(fila["med"])] = float(
                fila["valor"]
            )

        def _tarjeta(entidad: str) -> dict[str, Any]:
            datos = medidas.get(entidad, {})
            real = datos.get("real_mes")
            p50 = datos.get("base_p50")
            compromiso = datos.get("compromiso")
            return {
                "entidad": entidad,
                "real_dia": datos.get("real_dia"),
                "programa_dia": datos.get("programa_dia"),
                "delta_dia": datos.get("delta_dia"),
                "real_mes": real,
                "proy_mes": datos.get("proy_mes"),
                "base_p50": p50,
                "compromiso": compromiso,
                "delta_p50": datos.get("delta_p50"),
                "delta_compromiso": datos.get("delta_compromiso"),
                "cumpl_p50": (round(real / p50 * 100.0, 1) if (real and p50) else None),
                # El compromiso (Reto) puede diferir del P50: el frontend rotula
                # distinto según el caso.
                "compromiso_difiere": (
                    compromiso is not None
                    and p50 is not None
                    and abs(compromiso - p50) > 1e-6
                ),
            }

        return {
            "encontrada": True,
            "reporte_id": reporte_id,
            "corte": fecha.isoformat() if fecha else None,
            "unidad": "kbpe",
            "productos": [
                _tarjeta(e) for e in ["Crudo", "Gas", "Blancos"] if e in medidas
            ],
            "totales": [
                _tarjeta(e)
                for e in ["Ecopetrol", "Filiales", "Upstream"]
                if e in medidas
            ],
        }
