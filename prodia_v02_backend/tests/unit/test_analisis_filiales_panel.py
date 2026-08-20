"""Panel de FILIALES y tarjeta P50, contra un doble de repositorio.

Lo que se protege aquí es que las DOS bases de comparación no se mezclen:
PROGRAMA misma-ventana para los KPIs, PROMEDIO 2026 para las tarjetas y focos.
Mezclarlas fue el bug que hacía que Permian saliera como excedente en crudo
mientras su tarjeta lo marcaba por debajo.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from src.features.analisis.services_filiales_panel import FilialesService


class RepoFilialesFalso:
    """Doble del repositorio de filiales."""

    def __init__(self, **datos: Any) -> None:
        self._datos = datos

    def max_fecha_real(self, empresa_id: int | None = None) -> Any:
        """Por defecto, mayo-2026 (el último mes con dato del corpus real).

        `max_fecha=None` simula la ausencia total de REAL diario.
        """
        if "max_fecha" in self._datos:
            return self._datos["max_fecha"]
        return date(2026, 5, 17)

    def dias_con_real(self, ini: str, fin: str, empresa_id: int | None = None) -> int:
        return self._datos.get("ndias", 17)

    def kpis_misma_ventana(self, ini: str, fin: str) -> list[dict[str, Any]]:
        return self._datos.get("kpis", [])

    def curva_diaria(self, ini: str, fin: str) -> list[dict[str, Any]]:
        return self._datos.get("curva", [])

    def gap_por_empresa(
        self, ini: str, fin: str, producto: str
    ) -> list[dict[str, Any]]:
        return self._datos.get("gap", {}).get(producto, [])

    def programa_mes_completo(self, ini: str, fin: str) -> float:
        return self._datos.get("programa_total", 0.0)

    def promedio_mensual_del_anio(
        self, anio: int, mes_ini: str, empresa_id: int | None = None
    ) -> list[dict[str, Any]]:
        if empresa_id is not None:
            return self._datos.get("promedio_empresa", {}).get(empresa_id, [])
        return self._datos.get("promedio", [])

    def listar_empresas(self) -> list[dict[str, Any]]:
        return self._datos.get("empresas", [])

    def empresa_id_de(self, nombre: str) -> int | None:
        return self._datos.get("empresas_por_nombre", {}).get(nombre.upper())

    def mtd_de_empresa(
        self, empresa_id: int, ini: str, fin: str
    ) -> list[dict[str, Any]]:
        return self._datos.get("mtd_empresa", {}).get(empresa_id, [])

    def meses_completos_del_anio(self, empresa_id: int, anio: int, mes_ini: str) -> int:
        return self._datos.get("n_meses", 4)

    def serie_mensual_de_empresa(self, empresa_id: int) -> list[dict[str, Any]]:
        return self._datos.get("serie_mensual", [])

    def reporte_con_president(self, periodo: str | None = None) -> int | None:
        return self._datos.get("reporte_president")

    def fecha_de_reporte(self, reporte_id: int) -> Any:
        return self._datos.get("fecha_reporte", date(2026, 5, 17))

    def medidas_president(self, reporte_id: int) -> list[dict[str, Any]]:
        return self._datos.get("medidas", [])


def _kpi(producto: str, real: float, programa: float) -> dict[str, Any]:
    return {"prod": producto, "real_mtd": real, "prog_mtd": programa}


# ── Base de comparación ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_sin_real_diario_declara_sin_datos() -> None:
    servicio = FilialesService(RepoFilialesFalso(max_fecha=None))  # type: ignore[arg-type]
    assert servicio.desempeno()["sin_datos"] is True
    assert servicio.ejecutivo()["sin_datos"] is True


@pytest.mark.unit
def test_kpis_usan_programa_misma_ventana() -> None:
    """95/100 = 95 %: se compara contra el PROGRAMA de los días con REAL, no
    contra el del mes completo (que daría ~55 % por el corte)."""
    repo = RepoFilialesFalso(kpis=[_kpi("CRUDO", 95, 100)])
    resultado = FilialesService(repo).desempeno()  # type: ignore[arg-type]
    crudo = [p for p in resultado["por_producto"] if p["producto"] == "CRUDO"][0]
    assert crudo["cumplimiento"] == 95.0


@pytest.mark.unit
def test_tarjetas_usan_promedio_2026_no_programa() -> None:
    """Las tarjetas comparan la PROYECCIÓN de cierre contra el promedio del año.

    Con 17/31 días y 1700 acumulados, la proyección es ~3100; contra un
    promedio de 3100 da 100 %. Si usara el programa misma-ventana (1800) daría
    otra cifra — son preguntas distintas y no deben mezclarse.
    """
    repo = RepoFilialesFalso(
        ndias=17,
        kpis=[_kpi("CRUDO", 1700, 1800)],
        promedio=[{"prod": "CRUDO", "promedio": 3100}],
    )
    tarjetas = {
        t["producto"]: t for t in FilialesService(repo).ejecutivo()["tarjetas"]  # type: ignore[arg-type]
    }
    assert tarjetas["CRUDO"]["meta_mes"] == 3100
    assert tarjetas["CRUDO"]["proyectado_cierre"] == pytest.approx(3100, rel=0.01)


@pytest.mark.unit
def test_las_filiales_no_tienen_ritmo_diario() -> None:
    """`pace=None` en las tarjetas: las 3 usan la rama 'mes vs promedio del
    año' del frontend, sin inventar una tasa diaria."""
    repo = RepoFilialesFalso(
        kpis=[_kpi("CRUDO", 1700, 1800)],
        promedio=[{"prod": "CRUDO", "promedio": 3100}],
    )
    tarjetas = FilialesService(repo).ejecutivo()["tarjetas"]  # type: ignore[arg-type]
    assert all(t["bopd"] is None for t in tarjetas)


@pytest.mark.unit
def test_las_secciones_del_ejecutivo_hablan_de_programa() -> None:
    """El composer recibe `meta_nombre='programa'`: las filiales no tienen
    presupuesto y llamarlo así sería falso."""
    repo = RepoFilialesFalso(
        kpis=[_kpi("CRUDO", 90, 100)],
        promedio=[{"prod": "CRUDO", "promedio": 200}],
    )
    secciones = FilialesService(repo).ejecutivo()["secciones"]  # type: ignore[arg-type]
    texto = " ".join(secciones["insights"])
    assert "programa" in texto.lower()
    assert "presupuesto" not in texto.lower()


@pytest.mark.unit
def test_el_insight_de_filiales_no_inventa_eventos() -> None:
    """Los comentarios del reporte son de ECP: para filiales se declara vacío
    en vez de atribuir eventos ajenos."""
    repo = RepoFilialesFalso(kpis=[_kpi("CRUDO", 95, 100)])
    resultado = FilialesService(repo).desempeno_insight()  # type: ignore[arg-type]
    assert resultado["eventos"] == []
    assert resultado["valle_diagnostico"] is None


# ── Tendencia de una filial ─────────────────────────────────────────────────


@pytest.mark.unit
def test_filial_inexistente() -> None:
    repo = RepoFilialesFalso(empresas_por_nombre={})
    assert FilialesService(repo).tendencia_filial("NO EXISTE")["encontrada"] is False  # type: ignore[arg-type]


@pytest.mark.unit
def test_sin_meses_previos_se_declara_sin_tendencia() -> None:
    """Sin base de comparación no se muestra una variación: se declara."""
    repo = RepoFilialesFalso(
        empresas_por_nombre={"HOCOL": 1},
        mtd_empresa={1: [{"prod": "CRUDO", "tot": 1000}]},
        promedio_empresa={1: []},  # sin promedio → n_base = 0
    )
    resultado = FilialesService(repo).tendencia_filial("Hocol")  # type: ignore[arg-type]
    assert resultado["sin_tendencia"] is True


@pytest.mark.unit
def test_producto_no_reportado_se_declara_no_se_pinta_cero() -> None:
    repo = RepoFilialesFalso(
        empresas_por_nombre={"HOCOL": 1},
        mtd_empresa={1: [{"prod": "CRUDO", "tot": 1700}]},
        promedio_empresa={1: [{"prod": "CRUDO", "promedio": 3100}]},
    )
    resultado = FilialesService(repo).tendencia_filial("Hocol")  # type: ignore[arg-type]
    por_producto = {p["producto"]: p for p in resultado["por_producto"]}
    assert por_producto["CRUDO"]["reporta"] is True
    assert por_producto["GAS"]["reporta"] is False
    assert "proyeccion" not in por_producto["GAS"]


@pytest.mark.unit
def test_banda_en_linea_de_cinco_por_ciento() -> None:
    """±5 % alrededor del promedio es 'en línea': ni por encima ni por debajo."""
    repo = RepoFilialesFalso(
        ndias=31,  # mes completo: proyección = mtd
        empresas_por_nombre={"HOCOL": 1},
        mtd_empresa={1: [{"prod": "CRUDO", "tot": 102}]},
        promedio_empresa={1: [{"prod": "CRUDO", "promedio": 100}]},
    )
    resultado = FilialesService(repo).tendencia_filial("Hocol")  # type: ignore[arg-type]
    crudo = [p for p in resultado["por_producto"] if p["producto"] == "CRUDO"][0]
    assert crudo["variacion_pct"] == 2.0
    assert crudo["direccion"] == "en línea"


@pytest.mark.unit
def test_serie_mensual_excluye_meses_casi_vacios() -> None:
    """Un mes con 1 día distorsiona la tendencia (Nov-2025 real)."""
    repo = RepoFilialesFalso(
        serie_mensual=[
            {"m": date(2025, 11, 1), "prod": "CRUDO", "tot": 100, "dias": 1},
            {"m": date(2026, 1, 1), "prod": "CRUDO", "tot": 3100, "dias": 31},
            {"m": date(2026, 5, 1), "prod": "CRUDO", "tot": 1700, "dias": 17},
        ]
    )
    serie = FilialesService(repo).serie_mensual(1, 2026, 5)  # type: ignore[arg-type]
    assert "Nov 2025" not in serie["meses"]
    assert serie["meses"] == ["Ene 2026", "May 2026"]


@pytest.mark.unit
def test_el_mes_en_curso_se_proyecta_y_se_marca() -> None:
    """1700 en 17 días → proyección 3100, y `proyectado_idx` lo señala para que
    el frontend no lo pinte como un valor cerrado."""
    repo = RepoFilialesFalso(
        serie_mensual=[
            {"m": date(2026, 1, 1), "prod": "CRUDO", "tot": 3000, "dias": 31},
            {"m": date(2026, 5, 1), "prod": "CRUDO", "tot": 1700, "dias": 17},
        ]
    )
    serie = FilialesService(repo).serie_mensual(1, 2026, 5)  # type: ignore[arg-type]
    assert serie["proyectado_idx"] == 1
    assert serie["series"]["CRUDO"] == [3000, 3100]


@pytest.mark.unit
def test_unidades_por_producto_en_la_serie() -> None:
    """A5: gas en MSCF, crudo y blancos en bbl — doble eje en el frontend."""
    serie = FilialesService(RepoFilialesFalso()).serie_mensual(1, 2026, 5)  # type: ignore[arg-type]
    assert serie["unidades"] == {"CRUDO": "bbl", "GAS": "MSCF", "BLANCOS": "bbl"}


# ── President (tarjeta P50) ─────────────────────────────────────────────────


@pytest.mark.unit
def test_president_sin_hoja_devuelve_no_encontrada() -> None:
    repo = RepoFilialesFalso(reporte_president=None)
    assert FilialesService(repo).president()["encontrada"] is False  # type: ignore[arg-type]


@pytest.mark.unit
def test_president_calcula_cumplimiento_vs_p50() -> None:
    repo = RepoFilialesFalso(
        reporte_president=1042,
        medidas=[
            {"ent": "Crudo", "med": "real_mes", "valor": 484.0},
            {"ent": "Crudo", "med": "base_p50", "valor": 500.0},
            {"ent": "Crudo", "med": "compromiso", "valor": 500.0},
        ],
    )
    resultado = FilialesService(repo).president()  # type: ignore[arg-type]
    crudo = resultado["productos"][0]

    assert resultado["unidad"] == "kbpe"
    assert crudo["cumpl_p50"] == 96.8
    assert crudo["compromiso_difiere"] is False


@pytest.mark.unit
def test_president_detecta_compromiso_distinto_del_p50() -> None:
    """Cuando el Reto difiere del P50, el frontend rotula distinto."""
    repo = RepoFilialesFalso(
        reporte_president=1042,
        medidas=[
            {"ent": "Crudo", "med": "real_mes", "valor": 484.0},
            {"ent": "Crudo", "med": "base_p50", "valor": 500.0},
            {"ent": "Crudo", "med": "compromiso", "valor": 520.0},
        ],
    )
    assert (
        FilialesService(repo).president()["productos"][0]["compromiso_difiere"]  # type: ignore[arg-type]
        is True
    )


@pytest.mark.unit
def test_president_sin_medida_no_fabrica_cumplimiento() -> None:
    """El bloque DÍA llega en #REF! en algunos reportes: se declara `None`, no
    un 0,0 que no es el dato."""
    repo = RepoFilialesFalso(
        reporte_president=1042,
        medidas=[{"ent": "Crudo", "med": "real_mes", "valor": 484.0}],
    )
    crudo = FilialesService(repo).president()["productos"][0]  # type: ignore[arg-type]
    assert crudo["cumpl_p50"] is None
    assert crudo["real_dia"] is None
