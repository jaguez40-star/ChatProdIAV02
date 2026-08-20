"""Panel Ejecutivo contra un doble de repositorio.

Cubre la orquestación: gap reconciliado, pace, ritmo por producto y el armado
final del panel. El LLM se sustituye por un stub — ningún test sale a la red.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from src.features.analisis.services_ejecutivo_panel import EjecutivoService


class RepoEjecutivoFalso:
    """Doble del repositorio ejecutivo."""

    db = None

    def __init__(self, **datos: Any) -> None:
        self._datos = datos

    # Ámbito
    def fuentes_por_columna(self, columna: str, entidad: str) -> list[int]:
        return self._datos.get("ids", [1])

    def fuentes_union(self, entidad: str) -> list[int]:
        return self._datos.get("ids", [1])

    def vice_id_de(self, entidad: str) -> int | None:
        return self._datos.get("vice_id")

    def max_fecha_diaria(self, ids: list[int], vice_id: int | None) -> Any:
        return self._datos.get("max_dia", date(2026, 5, 17))

    def max_fecha_mensual_real(self, ids: list[int], vice_id: int | None) -> Any:
        return self._datos.get("max_mes")

    # KPIs y series
    def kpis_mes(self, *args: Any) -> list[dict[str, Any]]:
        return self._datos.get("kpis", [])

    def curva_diaria(self, *args: Any) -> list[dict[str, Any]]:
        return []

    def real_mensual_del_anio(self, *args: Any) -> list[dict[str, Any]]:
        return []

    def campos_sin_meta(self, *args: Any) -> list[dict[str, Any]]:
        return []

    def serie_crudo_diaria(self, *args: Any) -> list[dict[str, Any]]:
        return self._datos.get("serie", [])

    def mtd_por_producto(self, *args: Any) -> list[dict[str, Any]]:
        return self._datos.get("mtd", [])

    def historico_del_anio(self, *args: Any) -> list[dict[str, Any]]:
        return self._datos.get("historico", [])

    def gap_por_campo(
        self, ids: list[int], vice_id: int | None, fin: str, producto: str
    ) -> list[dict[str, Any]]:
        return self._datos.get("gap", {}).get(producto, [])

    def nombres_de_entidad(self, ids: list[int], vice_id: int | None) -> list[str]:
        return self._datos.get("nombres", [])

    def comentarios_del_dia(
        self, fecha: Any, nombres: list[str] | None = None
    ) -> list[dict[str, Any]]:
        return self._datos.get("comentarios", [])

    def comentarios_del_campo_en_el_mes(
        self, campo: str, ini: str, fin: str, limite: int = 2
    ) -> list[dict[str, Any]]:
        return self._datos.get("comentarios_campo", {}).get(campo, [])


def _serie(valores: list[float], desde_dia: int = 1) -> list[dict[str, Any]]:
    return [
        {"fecha": date(2026, 5, desde_dia + i), "vol": v} for i, v in enumerate(valores)
    ]


def _kpi(producto: str, real: float, ppto: float) -> list[dict[str, Any]]:
    return [
        {"prod": producto, "esc": "REAL", "vol": real},
        {"prod": producto, "esc": "PPTO", "vol": ppto},
    ]


# ── Armado del panel ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_entidad_inexistente() -> None:
    servicio = EjecutivoService(RepoEjecutivoFalso(ids=[], vice_id=None))  # type: ignore[arg-type]
    assert servicio.ejecutivo("NO EXISTE", nivel="campo")["encontrada"] is False


@pytest.mark.unit
def test_las_secciones_nunca_vienen_vacias_sin_llm() -> None:
    """El composer determinista es el entregable por defecto (H4 del origen):
    con `EJECUTIVO_USAR_LLM=false` las 4 secciones deben venir completas."""
    repo = RepoEjecutivoFalso(kpis=_kpi("CRUDO", 950, 1000))
    resultado = EjecutivoService(repo).ejecutivo("CASTILLA", nivel="campo")  # type: ignore[arg-type]

    secciones = resultado["secciones"]
    assert set(secciones) == {
        "insights",
        "oportunidades",
        "puntos_atencion",
        "decisiones",
    }
    assert all(secciones[k] for k in secciones), "ninguna sección puede ir vacía"
    assert resultado["meta"]["generado_por"] == "fallback"


@pytest.mark.unit
def test_los_tres_productos_tienen_foco_en_orden_fijo() -> None:
    """Decisión 2026-07-26: Crudo→Gas→Blancos, siempre."""
    repo = RepoEjecutivoFalso(kpis=_kpi("CRUDO", 950, 1000))
    resultado = EjecutivoService(repo).ejecutivo("CASTILLA", nivel="campo")  # type: ignore[arg-type]
    assert [f["producto"] for f in resultado["focos"]] == ["CRUDO", "GAS", "BLANCOS"]


@pytest.mark.unit
def test_producto_sin_meta_no_entra_al_gap_pero_si_a_las_tarjetas() -> None:
    """Sin PPTO no hay gap que descomponer, pero la tarjeta sale igual."""
    repo = RepoEjecutivoFalso(kpis=[{"prod": "GAS", "esc": "REAL", "vol": 500}])
    resultado = EjecutivoService(repo).ejecutivo("CASTILLA", nivel="campo")  # type: ignore[arg-type]

    assert "GAS" not in resultado["gap_por_producto"]
    assert len(resultado["tarjetas"]) == 3


# ── Gap reconciliado ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_la_aritmetica_bruto_neto_cierra() -> None:
    """Invariante auditable: faltante_bruto + excedente_bruto = gap_total."""
    repo = RepoEjecutivoFalso(
        kpis=_kpi("CRUDO", 800, 1000),
        gap={
            "CRUDO": [
                {"campo": "A", "vreal": 100, "vppto": 400},  # -300
                {"campo": "B", "vreal": 300, "vppto": 400},  # -100
                {"campo": "C", "vreal": 400, "vppto": 200},  # +200
            ]
        },
    )
    gap = EjecutivoService(repo).ejecutivo("CASTILLA", nivel="campo")[  # type: ignore[arg-type]
        "gap_por_producto"
    ]["CRUDO"]

    assert gap["faltante_bruto"] == -400
    assert gap["excedente_bruto"] == 200
    assert gap["faltante_bruto"] + gap["excedente_bruto"] == gap["gap_total_campos"]


@pytest.mark.unit
def test_concentracion_se_calcula_sobre_los_detractores_brutos() -> None:
    """|top3| / |Σ detractores|, NO sobre el gap neto: sobre el neto daría
    >100 % cuando hay compensadores grandes."""
    repo = RepoEjecutivoFalso(
        kpis=_kpi("CRUDO", 800, 1000),
        gap={
            "CRUDO": [
                {"campo": "A", "vreal": 100, "vppto": 400},
                {"campo": "B", "vreal": 300, "vppto": 400},
                {"campo": "C", "vreal": 400, "vppto": 200},
            ]
        },
    )
    gap = EjecutivoService(repo).ejecutivo("CASTILLA", nivel="campo")[  # type: ignore[arg-type]
        "gap_por_producto"
    ]["CRUDO"]
    assert gap["concentracion_pct"] == 100.0  # los 2 detractores son todo el faltante
    assert gap["n_detractores"] == 2


@pytest.mark.unit
def test_n_detractores_cuenta_todos_no_solo_el_top3() -> None:
    """El denominador de 'repartido entre N campos bajo meta' es honesto."""
    campos = [{"campo": f"C{i}", "vreal": 10, "vppto": 100} for i in range(6)]
    repo = RepoEjecutivoFalso(kpis=_kpi("CRUDO", 60, 600), gap={"CRUDO": campos})
    gap = EjecutivoService(repo).ejecutivo("CASTILLA", nivel="campo")[  # type: ignore[arg-type]
        "gap_por_producto"
    ]["CRUDO"]

    assert gap["n_detractores"] == 6
    assert len(gap["detractores"]) == 3  # el detalle sí se trunca al top-3


# ── Pace y ritmo ────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_pace_calcula_el_ritmo_requerido() -> None:
    repo = RepoEjecutivoFalso(
        kpis=_kpi("CRUDO", 1000, 3100),
        serie=_serie([100.0] * 10),  # 10 días a 100 = 1000 acumulado
    )
    pace = EjecutivoService(repo).ejecutivo("CASTILLA", nivel="campo")["pace_crudo"]  # type: ignore[arg-type]

    assert pace["dias"] == 10
    assert pace["restantes"] == 21
    assert pace["promedio_dia"] == 100
    assert pace["requerido_dia"] == 100  # (3100-1000)/21


@pytest.mark.unit
def test_sin_dias_restantes_no_hay_pace() -> None:
    """Mes cerrado: no queda ritmo que exigir."""
    repo = RepoEjecutivoFalso(
        kpis=_kpi("CRUDO", 3100, 3100), serie=_serie([100.0] * 31)
    )
    assert (
        EjecutivoService(repo).ejecutivo("CASTILLA", nivel="campo")["pace_crudo"]  # type: ignore[arg-type]
        is None
    )


@pytest.mark.unit
def test_producto_cuyo_diario_no_reconcilia_queda_sin_ritmo() -> None:
    """BLANCOS: su curva diaria suma ~2x el mes, así que mostrar un ritmo
    diario sería inventar una tasa. Se omite."""
    repo = RepoEjecutivoFalso(
        kpis=_kpi("CRUDO", 1000, 2000) + _kpi("BLANCOS", 500, 1000),
        mtd=[
            {"prod": "CRUDO", "ndias": 10, "mtd": 1000},  # reconcilia
            {"prod": "BLANCOS", "ndias": 10, "mtd": 1800},  # 3.6x el real: no
        ],
    )
    tarjetas = {
        t["producto"]: t
        for t in EjecutivoService(repo).ejecutivo("CASTILLA", nivel="campo")[  # type: ignore[arg-type]
            "tarjetas"
        ]
    }
    assert tarjetas["CRUDO"]["bopd"] is not None
    assert tarjetas["BLANCOS"]["bopd"] is None


# ── Valle ───────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_valle_detectado_y_anotado() -> None:
    # 5 altos, 4 bajos, 5 altos → el valle son los 4 bajos del medio.
    valores = [100.0] * 5 + [50.0] * 4 + [100.0] * 5
    repo = RepoEjecutivoFalso(kpis=_kpi("CRUDO", 1000, 1000), serie=_serie(valores))
    resultado = EjecutivoService(repo).ejecutivo("CASTILLA", nivel="campo")  # type: ignore[arg-type]

    valle = resultado["valle"]
    assert valle is not None
    assert valle["desde"] == "2026-05-06"
    assert valle["hasta"] == "2026-05-09"
    assert valle["dias"] == 4


@pytest.mark.unit
def test_serie_estable_no_produce_valle() -> None:
    repo = RepoEjecutivoFalso(
        kpis=_kpi("CRUDO", 1000, 1000), serie=_serie([100.0] * 15)
    )
    assert (
        EjecutivoService(repo).ejecutivo("CASTILLA", nivel="campo")["valle"] is None  # type: ignore[arg-type]
    )


# ── desempeno_insight ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_insight_arma_el_titular_y_la_curva() -> None:
    repo = RepoEjecutivoFalso(kpis=_kpi("CRUDO", 950, 1000), serie=_serie([100.0] * 10))
    resultado = EjecutivoService(repo).desempeno_insight("CASTILLA", nivel="campo")  # type: ignore[arg-type]

    assert [t["producto"] for t in resultado["titular"]] == [
        "CRUDO",
        "GAS",
        "BLANCOS",
    ]
    assert len(resultado["curva_crudo"]["fechas"]) == 10
    assert resultado["meta"]["generado_por"] == "fallback"
    assert resultado["lectura_ejecutiva"]


@pytest.mark.unit
def test_insight_de_entidad_explica_el_valle_con_su_comentario() -> None:
    """Con entidad, el valle se explica POR ella; sin comentario propio se
    declara quién lo reportó de verdad."""
    valores = [100.0] * 5 + [50.0] * 4 + [100.0] * 5
    repo = RepoEjecutivoFalso(
        kpis=_kpi("CRUDO", 1000, 1000),
        serie=_serie(valores),
        nombres=["LORITO", "CPO-09"],
        comentarios=[
            {"campo": "CPO-09", "comentario": "descargas atmosfericas en la linea"}
        ],
    )
    diagnostico = EjecutivoService(repo).desempeno_insight("LORITO", nivel="campo")[  # type: ignore[arg-type]
        "valle_diagnostico"
    ]

    assert diagnostico is not None
    assert "CPO-09" in diagnostico["diagnostico"]
    assert "no trae un comentario propio de LORITO" in diagnostico["diagnostico"]


@pytest.mark.unit
def test_insight_global_lista_eventos_en_vez_de_diagnostico() -> None:
    """Sin entidad no hay a quién atribuir: se sirve la tabla global."""
    valores = [100.0] * 5 + [50.0] * 4 + [100.0] * 5
    repo = RepoEjecutivoFalso(
        kpis=_kpi("CRUDO", 1000, 1000),
        serie=_serie(valores),
        comentarios=[{"campo": "QUIFA", "comentario": "falla electrica, 12 pozos"}],
    )
    resultado = EjecutivoService(repo).desempeno_insight()  # type: ignore[arg-type]

    assert resultado["valle_diagnostico"] is None
    assert resultado["eventos"][0]["pozos"] == 12
