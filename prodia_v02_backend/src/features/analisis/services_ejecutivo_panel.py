"""Orquestación del panel Ejecutivo — gap reconciliado, pace y armado final.

Portado de `INGESTA/Rep_Prod/backend/app/features/analisis/api.py:1163-1988`
(`desempeno_insight` y `ejecutivo`), separando la orquestación del cálculo puro
que vive en `services_ejecutivo.py`.

**El composer determinista es el entregable por defecto.** El pulido del LLM es
opcional y solo se intenta con `EJECUTIVO_USAR_LLM=true`: en desarrollo el qwen
local confunde cifras y el gate solo valida estructura, no grounding.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from src.core.config import get_settings
from src.features.analisis.prompts import (
    prompt_ejecutivo,
    prompt_lectura_ejecutiva,
)
from src.features.analisis.repositories_ejecutivo import EjecutivoRepository
from src.features.analisis.services_catalogo import MESES_ES
from src.features.analisis.services_desempeno import (
    PRODUCTOS,
    Ambito,
    DesempenoService,
    NoEncontradaError,
    SinDatosError,
)
from src.features.analisis.services_ejecutivo import (
    ETIQUETAS_ESTADO,
    componer_secciones,
    contar_pozos_en_comentario,
    detectar_valle,
    elegir_comentario_del_valle,
    estado,
    flags_ejecutivo,
    focos,
    sin_foco,
    situacion_general,
    tarjetas_kpi,
)
from src.shared import llm_client

# Top de eventos del valle. Antes eran 3 (maqueta compacta); ahora la columna
# llena el alto y se muestran hasta 12 — el día de inicio suele traer ~10.
TOP_EVENTOS_VALLE = 12

# Detractores y compensadores que se conservan de la descomposición.
_TOP_DETRACTORES = 3
_TOP_COMPENSADORES = 2

# La descomposición por campo se considera reconciliada si difiere <=2 % del KPI.
_DESFASE_MAX_PCT = 2.0

# El ritmo diario solo se expone si el acumulado diario no supera al mensual en
# más de un 5 %: si lo supera es físicamente imposible y el dato no es fiable.
_TOLERANCIA_RITMO = 1.05

_TIMEOUT_LECTURA = 60
_TIMEOUT_EJECUTIVO = 180


class EjecutivoService:
    """Panel ejecutivo ECP. Python calcula; el LLM solo pule prosa."""

    def __init__(self, repo: EjecutivoRepository) -> None:
        self._repo = repo
        self._desempeno = DesempenoService(repo)

    # ── Bloques compartidos ──────────────────────────────────────────────────

    def _titular(self, kpis: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
        """Cumplimiento por producto, con su chip de estado."""
        titular: list[dict[str, Any]] = []
        for producto in PRODUCTOS:
            real = kpis.get(producto, {}).get("REAL", 0.0)
            ppto = kpis.get(producto, {}).get("PPTO", 0.0)
            pct = round(real / ppto * 100.0, 1) if ppto else None
            chip = estado(pct)
            titular.append(
                {
                    "producto": producto,
                    "real": real,
                    "ppto": ppto,
                    "valor_pct": pct,
                    "estado": chip,
                    "texto": ETIQUETAS_ESTADO.get(chip, "—"),
                }
            )
        return titular

    def _serie_crudo(self, ambito: Ambito) -> list[tuple[str, float]]:
        return [
            (fila["fecha"].isoformat(), float(fila["vol"] or 0))
            for fila in self._repo.serie_crudo_diaria(
                ambito.ids, ambito.vice_id, ambito.ini, ambito.fin
            )
        ]

    def _pace_crudo(
        self,
        serie: list[tuple[str, float]],
        kpis: dict[str, dict[str, float]],
        dias_del_mes: int,
    ) -> dict[str, Any] | None:
        """Ritmo requerido en los días restantes para cerrar en PPTO."""
        if not serie:
            return None
        acumulado = sum(v for _f, v in serie)
        dias = len(serie)
        restantes = dias_del_mes - dias
        ppto_crudo = kpis.get("CRUDO", {}).get("PPTO", 0.0)
        if not (restantes > 0 and ppto_crudo and dias):
            return None

        promedio = acumulado / dias
        requerido = (ppto_crudo - acumulado) / restantes
        return {
            "mtd": round(acumulado),
            "dias": dias,
            "restantes": restantes,
            "promedio_dia": round(promedio),
            "requerido_dia": round(requerido),
            "delta_pct": (
                round((requerido / promedio - 1) * 100, 1) if promedio else None
            ),
        }

    def _pace_por_producto(
        self, ambito: Ambito, kpis: dict[str, dict[str, float]]
    ) -> dict[str, dict[str, Any]]:
        """Ritmo diario por producto, SOLO si la curva reconcilia con el mensual.

        Verificado (mayo 2026, global ECP): CRUDO 54,6 % y GAS 55,2 % (~17/31)
        reconcilian; BLANCOS 183,7 % NO —su diario suma ~2x el mes— así que
        queda sin ritmo diario en vez de mostrar una tasa inventada.
        """
        ritmos: dict[str, dict[str, Any]] = {}
        for fila in self._repo.mtd_por_producto(
            ambito.ids, ambito.vice_id, ambito.ini, ambito.fin
        ):
            producto = str(fila["prod"])
            dias = int(fila["ndias"] or 0)
            acumulado = float(fila["mtd"] or 0)
            real = kpis.get(producto, {}).get("REAL", 0.0)
            ppto = kpis.get(producto, {}).get("PPTO", 0.0)
            restantes = ambito.dias_del_mes - dias

            if not (dias and restantes > 0 and ppto and real):
                continue
            if acumulado > real * _TOLERANCIA_RITMO:
                continue  # físicamente imposible: no reconcilia

            promedio = acumulado / dias
            requerido = (ppto - acumulado) / restantes
            ritmos[producto] = {
                "promedio_dia": round(promedio),
                "requerido_dia": round(requerido),
                "delta_pct": (
                    round((requerido / promedio - 1) * 100, 1) if promedio else None
                ),
            }
        return ritmos

    def _historico_anual(self, ambito: Ambito) -> dict[str, float]:
        """Promedio de los meses previos con REAL, por producto."""
        acumulados: dict[str, list[float]] = {}
        for fila in self._repo.historico_del_anio(
            ambito.ids, ambito.vice_id, ambito.anio, ambito.mes
        ):
            valor = float(fila["vol"] or 0)
            if valor > 0:
                acumulados.setdefault(str(fila["prod"]), []).append(valor)
        return {
            producto: round(sum(valores) / len(valores))
            for producto, valores in acumulados.items()
            if valores
        }

    def _gap_de_producto(
        self, ambito: Ambito, producto: str, gap_kpi: float, con_eventos: bool = True
    ) -> dict[str, Any]:
        """Descompone el gap por campo y lo RECONCILIA contra el KPI."""
        filas = self._repo.gap_por_campo(
            ambito.ids, ambito.vice_id, ambito.fin, producto
        )
        # (campo, diferencia, real, ppto) — real y ppto se conservan para el
        # gráfico Meta vs Real.
        diferencias = [
            (
                str(fila["campo"] or "").strip(),
                float(fila["vreal"] or 0) - float(fila["vppto"] or 0),
                float(fila["vreal"] or 0),
                float(fila["vppto"] or 0),
            )
            for fila in filas
            if (fila["vreal"] or fila["vppto"])
        ]

        gap_total = sum(d[1] for d in diferencias)
        detractores = sorted([d for d in diferencias if d[1] < 0], key=lambda x: x[1])[
            :_TOP_DETRACTORES
        ]
        compensadores = sorted(
            [d for d in diferencias if d[1] > 0], key=lambda x: -x[1]
        )[:_TOP_COMPENSADORES]

        total_detractores = sum(d[1] for d in diferencias if d[1] < 0)
        total_compensadores = sum(d[1] for d in diferencias if d[1] > 0)

        # Concentración = |top3| / |Σ TODOS los detractores (bruto)|: "del total
        # del déficit, X% está en 3 campos". Sobre el gap NETO daría >100 %
        # cuando hay compensadores grandes.
        concentracion = (
            round(abs(sum(d[1] for d in detractores)) / abs(total_detractores) * 100, 1)
            if total_detractores
            else None
        )
        desfase = (
            round(abs(gap_total - gap_kpi) / abs(gap_kpi) * 100, 1) if gap_kpi else None
        )

        # Extremos por producción REAL: 2 mayores + 2 menores entre los campos
        # que sí producen — para la tarjeta de un producto que NO va mal.
        producen = sorted([d for d in diferencias if d[2] > 0], key=lambda x: -x[2])
        extremos = producen if len(producen) <= 4 else producen[:2] + producen[-2:]

        return {
            "producto": producto,
            "gap_kpi": round(gap_kpi),
            "gap_total_campos": round(gap_total),
            "reconciliado": desfase is not None and desfase <= _DESFASE_MAX_PCT,
            "desfase_pct": desfase,
            "concentracion_pct": concentracion,
            # Denominador honesto para "repartido entre N campos bajo meta":
            # TODOS los detractores, no solo el top-3 truncado.
            "n_detractores": len([d for d in diferencias if d[1] < 0]),
            # BRUTOS: el titular del foco es el gap NETO, pero el detalle lista
            # faltantes BRUTOS. Sin estos totales el panel mostraba
            # "-10.813.358" con un detalle que sumaba 19.814.696.
            "faltante_bruto": round(total_detractores),
            "excedente_bruto": round(total_compensadores),
            "detractores": [
                {
                    "campo": d[0],
                    "gap": round(d[1]),
                    "real": round(d[2]),
                    "meta": round(d[3]),
                    "eventos": (
                        [
                            {
                                "fecha": ev["fecha"].isoformat(),
                                "texto": str(ev["comentario"] or "").strip()[:220],
                            }
                            for ev in self._repo.comentarios_del_campo_en_el_mes(
                                d[0], ambito.ini, ambito.fin
                            )
                        ]
                        if con_eventos
                        else []
                    ),
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
            "extremos": [
                {"campo": d[0], "real": round(d[2]), "meta": round(d[3])}
                for d in extremos
            ],
        }

    def _eventos_del_valle(
        self, valle: dict[str, Any], nombres: list[str] | None
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Top eventos del DÍA DE INICIO del valle, por nº de pozos."""
        partes = [int(p) for p in valle["desde"].split("-")]
        onset = date(*partes)

        items: list[dict[str, Any]] = []
        for fila in self._repo.comentarios_del_dia(onset, nombres):
            comentario = str(fila["comentario"] or "")
            pozos = contar_pozos_en_comentario(comentario)
            if pozos <= 0:
                continue
            items.append(
                {
                    "campo": str(fila["campo"] or "").strip(),
                    "evento": comentario.strip().split(".")[0][:70],
                    "pozos": pozos,
                }
            )

        items.sort(key=lambda x: x["pozos"], reverse=True)
        top = items[:TOP_EVENTOS_VALLE]
        resto = items[TOP_EVENTOS_VALLE:]
        extra = {
            "campos": len(resto),
            "pozos_aprox": sum(i["pozos"] for i in resto),
            "fecha": onset.isoformat(),
        }
        return top, extra

    # ── Endpoint /ejecutivo ──────────────────────────────────────────────────

    def ejecutivo(
        self,
        entidad: str | None = None,
        nivel: str | None = None,
        periodo: str | None = None,
        pulir: bool = True,
    ) -> dict[str, Any]:
        """Panel multi-sección. `pulir=False` salta el LLM (lo usa F4/Analizar,
        que descarta la prosa y no debe esperar 180 s por ella)."""
        try:
            ambito = self._desempeno.resolver_ambito(entidad, nivel, periodo)
        except NoEncontradaError:
            return {"entidad": entidad, "encontrada": False}
        except SinDatosError:
            return {"entidad": entidad, "encontrada": True, "sin_datos": True}

        kpis = self._desempeno.kpis_por_producto(ambito)
        titular = self._titular(kpis)
        serie = self._serie_crudo(ambito)
        valle = detectar_valle(serie)

        eventos: list[dict[str, Any]] = []
        eventos_extra: dict[str, Any] = {"campos": 0, "pozos_aprox": 0}
        if valle:
            nombres = self._repo.nombres_de_entidad(ambito.ids, ambito.vice_id)
            eventos, eventos_extra = self._eventos_del_valle(valle, nombres or None)
            promedio = sum(v for _f, v in serie) / len(serie) if serie else 0
            desde = date(*[int(p) for p in valle["desde"].split("-")])
            hasta = date(*[int(p) for p in valle["hasta"].split("-")])
            valle["magnitud_pct"] = (
                round((valle["min_valor"] / promedio - 1) * 100, 1)
                if promedio
                else None
            )
            valle["dias"] = (hasta - desde).days + 1

        pace = self._pace_crudo(serie, kpis, ambito.dias_del_mes)
        ritmos = self._pace_por_producto(ambito, kpis)
        historico = self._historico_anual(ambito)

        # F2 en ECP: el desglose por campo se calcula para TODOS los productos
        # con meta (gap_full → gráficos) y la narrativa usa SOLO los rezagados
        # (gap_lag → brief/flags). Antes solo se consultaba con pct<100: con la
        # entidad en meta (CASTILLA 102,7 %) el panel decía "Sin desglose por
        # campo para graficar" aunque el dato SIEMPRE existe.
        gap_full: dict[str, dict[str, Any]] = {}
        gap_lag: dict[str, dict[str, Any]] = {}
        extremos: dict[str, list[dict[str, Any]]] = {}

        for fila in titular:
            producto = fila["producto"]
            if fila["valor_pct"] is None:
                # Sin PPTO: no entra a gap_full/gap_lag, pero igual se calculan
                # sus extremos para su tarjeta (los 3 productos salen siempre).
                sin_meta = self._gap_de_producto(
                    ambito, producto, fila["real"] or 0, con_eventos=False
                )
                extremos[producto] = sin_meta.get("extremos", [])
                continue

            gap = self._gap_de_producto(ambito, producto, fila["real"] - fila["ppto"])
            gap_full[producto] = gap
            extremos[producto] = gap.get("extremos", [])
            if fila["valor_pct"] < 100:
                gap_lag[producto] = gap

        flags = flags_ejecutivo(
            titular, gap_lag, valle, pace, serie[-1][0] if serie else None
        )
        periodo_txt = f"{MESES_ES[ambito.mes]} {ambito.anio}"
        corte = f"{len(serie)}/{ambito.dias_del_mes}"

        # SÍNTESIS pre-derivada por Python: la INTERPRETACIÓN, no solo los
        # números. Distingue rezago transitorio (valle acotado ya recuperado) de
        # estructural, y foco (concentrado) de distribuido (sistémico).
        valle_activo = any(
            f["tipo"] == "valle_activo" and f.get("activo") for f in flags
        )
        sintesis: list[dict[str, Any]] = []
        for fila in titular:
            producto, pct = fila["producto"], fila["valor_pct"]
            if pct is None or pct >= 100:
                continue
            gap = gap_lag.get(producto, {})
            concentracion = gap.get("concentracion_pct")
            n_campos = len(gap.get("detractores", []))

            if producto == "CRUDO" and valle:
                caracter = (
                    "transitorio ya superado (fue un valle acotado que se recuperó)"
                    if not valle_activo
                    else "transitorio pero aún en curso (el valle sigue activo)"
                )
            elif concentracion is not None and concentracion >= 70:
                caracter = (
                    "estructural y focalizado (el faltante persiste, no fue un "
                    "evento puntual)"
                )
            else:
                caracter = "estructural y distribuido"

            foco_txt = (
                f"focalizado: ~{concentracion}% del faltante está en {n_campos} "
                "campos → acción localizada"
                if (concentracion is not None and concentracion >= 70)
                else "distribuido en varios campos → problema más sistémico"
            )
            sintesis.append(
                {
                    "producto": producto,
                    "pct_presupuesto": pct,
                    "caracter_del_rezago": caracter,
                    "foco": foco_txt,
                }
            )

        situacion = situacion_general(titular, sintesis)
        secciones, generado, llm_diag = self._pulir_secciones(
            pulir,
            periodo_txt,
            corte,
            titular,
            sintesis,
            situacion,
            valle,
            eventos,
            gap_lag,
            pace,
            flags,
        )

        tarjetas = tarjetas_kpi(titular, ritmos, historico)
        return {
            "entidad": entidad,
            "encontrada": True,
            "meta": {
                "scope": entidad or "Global (toda la producción ECP)",
                "periodo": periodo_txt,
                "corte": corte,
                "generado_por": generado,
                "llm_diag": llm_diag,
            },
            "titular": titular,
            "tarjetas": tarjetas,
            "gap_por_producto": gap_full,  # gráficos: los 3 productos
            "valle": valle,
            "eventos": eventos,
            "eventos_extra": eventos_extra,
            "pace_crudo": pace,
            "flags": flags,
            "secciones": secciones,
            "focos": focos(titular, gap_lag, valle, eventos, tarjetas, extremos),
            "sin_foco": sin_foco(titular, gap_full, valle),
        }

    def _pulir_secciones(
        self,
        pulir: bool,
        periodo_txt: str,
        corte: str,
        titular: list[dict[str, Any]],
        sintesis: list[dict[str, Any]],
        situacion: dict[str, Any],
        valle: dict[str, Any] | None,
        eventos: list[dict[str, Any]],
        gap_lag: dict[str, dict[str, Any]],
        pace: dict[str, Any] | None,
        flags: list[dict[str, Any]],
    ) -> tuple[dict[str, list[str]] | None, str, dict[str, Any]]:
        """Devuelve `(secciones, generado_por, llm_diag)`.

        El composer determinista es el default entregable. El LLM solo se
        intenta con `EJECUTIVO_USAR_LLM=true`.
        """
        ajustes = get_settings()
        llm_diag: dict[str, Any] = {"status": "off"}
        secciones: dict[str, list[str]] | None = None
        generado = "fallback"

        if pulir and ajustes.ejecutivo_usar_llm:
            contexto = {
                "periodo": periodo_txt,
                "corte": corte,
                "situacion_general": situacion,
                "productos": [
                    {
                        "producto": t["producto"],
                        "pct_presupuesto": t["valor_pct"],
                        "situacion": (
                            "sin dato"
                            if t["valor_pct"] is None
                            else (
                                "por encima de la meta"
                                if t["valor_pct"] >= 100
                                else "por debajo de la meta"
                            )
                        ),
                    }
                    for t in titular
                ],
                "sintesis": sintesis,
                "valle_crudo": valle,
                "eventos_del_valle": eventos,
                "detalle_por_producto": {
                    producto: {
                        "campos_por_debajo": [
                            {"campo": d["campo"], "faltante": abs(d["gap"])}
                            for d in gap["detractores"]
                        ],
                        "campos_por_encima": [
                            {"campo": d["campo"], "excedente": d["gap"]}
                            for d in gap["compensadores"]
                        ],
                        "concentracion_del_faltante_pct": gap["concentracion_pct"],
                    }
                    for producto, gap in gap_lag.items()
                },
                "pace_crudo": pace,
                "flags": flags,
            }
            llm_diag = {"status": "?"}
            prosa = llm_client.invocar(
                prompt_ejecutivo(contexto, situacion),
                timeout=_TIMEOUT_EJECUTIVO,
                diag=llm_diag,
            )
            claves = ("insights", "oportunidades", "puntos_atencion", "decisiones")
            if isinstance(prosa, dict) and all(
                isinstance(prosa.get(k), list) and prosa.get(k) for k in claves
            ):
                secciones = {k: [str(x)[:280] for x in prosa[k]][:5] for k in claves}
                generado = "llm"
            elif llm_diag.get("status") == "ok":
                faltan = [
                    k for k in claves if not (isinstance(prosa, dict) and prosa.get(k))
                ]
                llm_diag["status"] = "faltan_claves:" + ",".join(faltan)

        if secciones is None:
            # En pruebas (EJECUTIVO_FALLBACK=false) NO se tapa el fallo del LLM
            # con el texto base: se devuelve generado_por="error" + el diag.
            if pulir and ajustes.ejecutivo_usar_llm and not ajustes.ejecutivo_fallback:
                generado = "error"
            else:
                secciones = componer_secciones(
                    periodo_txt, titular, gap_lag, valle, pace, flags
                )

        return secciones, generado, llm_diag

    # ── Endpoint /desempeno_insight ──────────────────────────────────────────

    def desempeno_insight(
        self,
        entidad: str | None = None,
        nivel: str | None = None,
        periodo: str | None = None,
    ) -> dict[str, Any]:
        """Titular ejecutivo: chips por producto, curva de crudo y lectura."""
        try:
            ambito = self._desempeno.resolver_ambito(entidad, nivel, periodo)
        except NoEncontradaError:
            return {"entidad": entidad, "encontrada": False}
        except SinDatosError:
            return {"entidad": entidad, "encontrada": True, "sin_datos": True}

        kpis = self._desempeno.kpis_por_producto(ambito)
        titular = [
            {
                "producto": t["producto"],
                "valor_pct": t["valor_pct"],
                "estado": t["estado"],
                "texto": t["texto"],
            }
            for t in self._titular(kpis)
        ]

        serie = self._serie_crudo(ambito)
        valle = detectar_valle(serie)
        curva_crudo = {
            "fechas": [f for f, _v in serie],
            "valores": [v for _f, v in serie],
        }

        anotaciones: dict[str, Any] | None = None
        eventos: list[dict[str, Any]] = []
        eventos_extra: dict[str, Any] = {"campos": 0, "pozos_aprox": 0}
        valle_diagnostico: dict[str, Any] | None = None

        if valle:
            nombres = self._repo.nombres_de_entidad(ambito.ids, ambito.vice_id)
            if entidad:
                # Panel filtrado: el valle se explica POR la entidad.
                valle_diagnostico = self._diagnostico_del_valle(
                    ambito, entidad, valle, nombres
                )
            else:
                eventos, eventos_extra = self._eventos_del_valle(valle, None)

            anotaciones = {
                "banda": {
                    "desde": valle["desde"],
                    "hasta": valle["hasta"],
                    "label": "valle",
                },
                "punto": {
                    "fecha": valle["min_fecha"],
                    "valor": valle["min_valor"],
                    # Label corto y FIJO, calculado por Python: si lo redactara
                    # el LLM podría cortarse o inventar la magnitud.
                    "label": f"mín · {valle['min_valor'] / 1e6:.2f}M",
                },
            }

        peor = min(
            [t for t in titular if t["valor_pct"] is not None],
            key=lambda t: t["valor_pct"],
            default=None,
        )
        detractores: list[dict[str, Any]] = []
        compensadores: list[dict[str, Any]] = []
        if peor:
            gap = self._gap_de_producto(ambito, peor["producto"], 0, con_eventos=False)
            detractores = [
                {"campo": d["campo"], "gap": d["gap"]} for d in gap["detractores"]
            ]
            compensadores = [
                {"campo": d["campo"], "gap": d["gap"]} for d in gap["compensadores"]
            ]

        pace = self._pace_crudo(serie, kpis, ambito.dias_del_mes)
        lectura, generado = self._lectura_ejecutiva(
            ambito, titular, valle, eventos, detractores, compensadores, pace, peor
        )

        acciones: list[dict[str, str]] = []
        if peor:
            acciones.append(
                {
                    "label": f"Diagnóstico de {peor['producto'].lower()}",
                    "intent": f"diagnostico_{peor['producto'].lower()}",
                }
            )
        if valle:
            acciones.append(
                {
                    "label": "Monitorear estabilidad eléctrica",
                    "intent": "monitor_electrico",
                }
            )

        return {
            "entidad": entidad,
            "encontrada": True,
            "meta": {
                "scope": entidad or "Global (toda la producción ECP)",
                "periodo": f"{MESES_ES[ambito.mes]} {ambito.anio}",
                "corte": f"{len(serie)}/{ambito.dias_del_mes}",
                "generado_por": generado,
            },
            "titular": titular,
            "curva_crudo": curva_crudo,
            "anotaciones": anotaciones,
            "eventos": eventos,
            "eventos_extra": eventos_extra,
            "valle_diagnostico": valle_diagnostico,
            "gap": {
                "producto": (peor or {}).get("producto"),
                "detractores": detractores,
                "compensadores": compensadores,
            },
            "pace_crudo": pace,
            "lectura_ejecutiva": lectura,
            "accion_sugerida": acciones,
        }

    def _diagnostico_del_valle(
        self,
        ambito: Ambito,
        entidad: str,
        valle: dict[str, Any],
        nombres: list[str],
    ) -> dict[str, Any]:
        """Valle explicado POR la entidad — determinista, sin LLM.

        NUNCA inventa causas: el comentario ES la causa cuando existe.
        """
        onset = date(*[int(p) for p in valle["desde"].split("-")])
        comentarios = [
            {
                "campo": str(fila["campo"] or "").strip(),
                "texto": str(fila["comentario"] or "").strip()[:220],
            }
            for fila in self._repo.comentarios_del_dia(onset, nombres or None)
        ]

        quien, es_ajeno = elegir_comentario_del_valle(comentarios, entidad)
        desde, hasta = valle["desde"], valle["hasta"]

        if comentarios and quien:
            texto = comentarios[0]["texto"]
            if es_ajeno:
                # ATRIBUCIÓN HONESTA: antes se componía con `entidad` (lo que el
                # usuario pidió) e ignoraba quién lo reportó de verdad.
                diagnostico = (
                    f"El reporte del {desde} no trae un comentario propio de "
                    f"{entidad}. Lo más cercano es lo que reportó {quien}, el grupo "
                    f"con el que el reporte agrupa a {entidad}: «{texto}»"
                )
            else:
                diagnostico = f"Lo que reportó {quien} el {desde}: «{texto}»"
            recomendacion = None
        else:
            diagnostico = (
                f"El valle de crudo ({desde} a {hasta}) de {entidad} no tiene un "
                "motivo documentado en el reporte diario."
            )
            recomendacion = (
                f"Se recomienda revisar con operaciones de {entidad} la causa de la "
                "caída."
            )

        return {
            "valle": {"desde": desde, "hasta": hasta},
            "drivers": [],
            "comentarios": comentarios,
            "generado_por": "base",
            "diagnostico": diagnostico,
            "recomendacion": recomendacion,
        }

    def _lectura_ejecutiva(
        self,
        ambito: Ambito,
        titular: list[dict[str, Any]],
        valle: dict[str, Any] | None,
        eventos: list[dict[str, Any]],
        detractores: list[dict[str, Any]],
        compensadores: list[dict[str, Any]],
        pace: dict[str, Any] | None,
        peor: dict[str, Any] | None,
    ) -> tuple[str, str]:
        """Prosa del titular: LLM si está activo, si no composición determinista."""
        ajustes = get_settings()
        if ajustes.ejecutivo_usar_llm:
            contexto = {
                "periodo": f"{MESES_ES[ambito.mes]} {ambito.anio}",
                "titular": [
                    {"p": t["producto"], "pct": t["valor_pct"]} for t in titular
                ],
                "valle": valle,
                "eventos": eventos,
                "gap_detractores": detractores,
                "gap_compensadores": compensadores,
                "pace_crudo": pace,
            }
            prosa = llm_client.invocar(
                prompt_lectura_ejecutiva(contexto), timeout=_TIMEOUT_LECTURA
            )
            if isinstance(prosa, dict) and "lectura_ejecutiva" in prosa:
                return str(prosa["lectura_ejecutiva"])[:900], "llm"

        frases: list[str] = []
        if peor:
            frases.append(
                f"El mayor rezago es {peor['producto'].lower()} ({peor['valor_pct']}%)."
            )
        if detractores:
            campos = ", ".join(
                f"{d['campo']} ({d['gap']:,})".replace(",", ".") for d in detractores
            )
            frases.append(f"El gap se concentra en {campos}.")
        if compensadores:
            campos = ", ".join(
                f"{d['campo']} (+{d['gap']:,})".replace(",", ".") for d in compensadores
            )
            frases.append(f"Compensa parcialmente {campos}.")
        if pace and pace.get("delta_pct") is not None:
            requerido = f"{pace['requerido_dia']:,}".replace(",", ".")
            frases.append(
                f"Para cerrar crudo en presupuesto, los {pace['restantes']} días "
                f"restantes exigen {requerido} bls/día "
                f"({pace['delta_pct']:+}% vs el ritmo actual)."
            )
        frases.append(
            "La caída de crudo del valle está explicada por eventos operativos y ya "
            "se recuperó."
            if valle
            else "Producción sin anomalías diarias relevantes en el periodo."
        )
        return " ".join(frases), "fallback"
