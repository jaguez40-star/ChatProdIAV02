"""EBITDA, Mantenimientos y Diferidas — las tres features auxiliares.

Ningún test toca la BD real de 954 MB ni el `.xlsx` de producción: se montan
ficheros sintéticos y dobles.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

import pytest

from src.features.diferidas.services import DiferidasService, clasificar_tendencia
from src.features.ebitda.repositories import COMPONENTES
from src.features.ebitda.services import EbitdaService, aplicar_signo
from src.features.mantenimientos.repositories import EventoOW, normalizar
from src.features.mantenimientos.services import (
    MantenimientosService,
    parsear_periodo,
    solapa_el_mes,
)

# ── EBITDA ──────────────────────────────────────────────────────────────────


class RepoEbitdaFalso:
    def __init__(self, fila: dict[str, Any] | None = None) -> None:
        self._fila = fila

    def waterfall(
        self, anio: int, mes: int, nivel: str = "", entidades: list[str] | None = None
    ) -> dict[str, Any] | None:
        self.ultimo_nivel = nivel
        self.ultimas_entidades = entidades
        return self._fila


@pytest.mark.unit
def test_el_waterfall_tiene_18_componentes_en_orden_fijo() -> None:
    """El orden ES el del gráfico: Ingresos primero, NOPAT último."""
    resultado = EbitdaService(RepoEbitdaFalso({})).waterfall(2026, 5)  # type: ignore[arg-type]
    assert len(resultado.components) == 18
    assert resultado.components[0].key == "ingresos"
    assert resultado.components[-1].key == "util_neta"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("modo", "valor", "esperado"),
    [
        ("pos", 100.0, 100.0),  # totales: tal cual
        ("negabs", 100.0, -100.0),  # costos guardados en positivo, restan
        ("negabs", -100.0, -100.0),  # y siguen restando si ya venían negativos
        ("neg", 100.0, -100.0),  # cargos guardados en positivo
        ("asis", -50.0, -50.0),  # el dato YA trae su signo
    ],
)
def test_los_cuatro_modos_de_signo(modo: str, valor: float, esperado: float) -> None:
    """Cada familia de conceptos se guarda con una convención distinta;
    unificarlas aquí es lo que hace que el waterfall cuadre."""
    assert aplicar_signo(valor, modo) == esperado


@pytest.mark.unit
def test_usd_por_barril_se_calcula_sobre_los_barriles_del_ambito() -> None:
    repo = RepoEbitdaFalso({"ingresos": 1000.0, "total_bls": 500.0})
    resultado = EbitdaService(repo).waterfall(2026, 5)  # type: ignore[arg-type]
    ingresos = resultado.components[0]
    assert ingresos.value_kusd == 1000
    assert ingresos.value_usd_bl == 2000.0  # 1000 kUSD * 1000 / 500 bl


@pytest.mark.unit
def test_sin_barriles_no_se_divide_por_cero() -> None:
    resultado = EbitdaService(RepoEbitdaFalso({"ingresos": 1000.0})).waterfall(2026, 5)  # type: ignore[arg-type]
    assert resultado.components[0].value_usd_bl == 0.0


@pytest.mark.unit
def test_entidad_admite_varios_campos_separados_por_pipe() -> None:
    """Un foco agrupa N campos: el waterfall debe sumarlos todos."""
    repo = RepoEbitdaFalso({})
    EbitdaService(repo).waterfall(2026, 5, nivel="campo", entidad="CUSIANA|CUPIAGUA")  # type: ignore[arg-type]
    assert repo.ultimas_entidades == ["CUSIANA", "CUPIAGUA"]


@pytest.mark.unit
def test_sin_fila_devuelve_ceros_no_error() -> None:
    """Un periodo sin datos da un waterfall en cero, no una excepción."""
    resultado = EbitdaService(RepoEbitdaFalso(None)).waterfall(2026, 5)  # type: ignore[arg-type]
    assert all(c.value_kusd == 0 for c in resultado.components)
    assert resultado.meta.nivel == "global"


@pytest.mark.unit
def test_los_totales_estan_marcados_como_tales() -> None:
    """El frontend arranca un `total` desde cero y un `delta` desde el anterior."""
    totales = {c[1] for c in COMPONENTES if c[4] == "total"}
    assert totales == {"ingresos", "ebitda", "util_oper", "util_neta"}


# ── Mantenimientos ──────────────────────────────────────────────────────────


class RepoMantenimientosFalso:
    def __init__(self, eventos: list[EventoOW] | None) -> None:
        self._eventos = eventos

    def eventos(self) -> list[EventoOW] | None:
        return self._eventos

    def campos_disponibles(self) -> set[str]:
        return {e["campo"] for e in (self._eventos or [])}


def _evento(
    campo: str, inicio: datetime, fin: datetime | None = None, pozo: str = "P-1"
) -> EventoOW:
    return EventoOW(campo=campo, pozo=pozo, tipo="Workover", inicio=inicio, fin=fin)


@pytest.mark.unit
def test_sin_archivo_degrada_con_motivo() -> None:
    """Contrato: siempre 200, nunca una excepción."""
    resultado = MantenimientosService(RepoMantenimientosFalso(None)).eventos()  # type: ignore[arg-type]
    assert resultado["sin_datos"] is True
    assert "no disponible" in resultado["motivo"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("2026-05", (2026, 5)),
        ("Mayo 2026", (2026, 5)),
        ("mayo 2026", (2026, 5)),
    ],
)
def test_periodos_validos(texto: str, esperado: tuple[int, int]) -> None:
    assert parsear_periodo(texto) == esperado


@pytest.mark.unit
@pytest.mark.parametrize("texto", ["2026-13", "2026-00", "1800-05", "", None, "ayer"])
def test_periodo_invalido_no_revienta(texto: str | None) -> None:
    """`2026-13` calza el patrón pero `datetime(y,13,1)` lanzaría ValueError y
    rompería el contrato de 'siempre 200'. Se valida el RANGO, no el formato."""
    assert parsear_periodo(texto) is None


@pytest.mark.unit
def test_evento_abierto_solapa_cualquier_mes_posterior() -> None:
    """A2: sin fecha de cierre el evento sigue corriendo."""
    abierto = _evento("CASTILLA", datetime(2026, 3, 1), fin=None)
    assert solapa_el_mes(abierto, datetime(2026, 5, 1), datetime(2026, 6, 1)) is True


@pytest.mark.unit
def test_evento_cerrado_antes_del_mes_no_solapa() -> None:
    cerrado = _evento("CASTILLA", datetime(2026, 1, 1), fin=datetime(2026, 2, 1))
    assert solapa_el_mes(cerrado, datetime(2026, 5, 1), datetime(2026, 6, 1)) is False


@pytest.mark.unit
def test_evento_que_cruza_el_mes_si_solapa() -> None:
    """A3: empezó antes y cerró después — está vigente durante el mes."""
    cruza = _evento("CASTILLA", datetime(2026, 4, 15), fin=datetime(2026, 6, 15))
    assert solapa_el_mes(cruza, datetime(2026, 5, 1), datetime(2026, 6, 1)) is True


@pytest.mark.unit
def test_los_abiertos_se_listan_primero() -> None:
    """Es lo que sigue corriendo: va arriba."""
    repo = RepoMantenimientosFalso(
        [
            _evento(
                "CASTILLA",
                datetime(2026, 5, 10),
                fin=datetime(2026, 5, 20),
                pozo="CERRADO",
            ),
            _evento("CASTILLA", datetime(2026, 5, 5), fin=None, pozo="ABIERTO"),
        ]
    )
    resultado = MantenimientosService(repo).eventos(  # type: ignore[arg-type]
        entidad="CASTILLA", campos=["CASTILLA"], periodo="2026-05"
    )
    assert resultado["eventos"][0]["pozo"] == "ABIERTO"
    assert resultado["meta"]["abiertos"] == 1


@pytest.mark.unit
def test_el_filtro_por_campo_normaliza_acentos() -> None:
    """'Caño Sur' en el archivo y 'CANO SUR' pedido son el mismo campo."""
    repo = RepoMantenimientosFalso(
        [_evento(normalizar("Caño Sur"), datetime(2026, 5, 5), fin=None)]
    )
    resultado = MantenimientosService(repo).eventos(  # type: ignore[arg-type]
        entidad="CAÑO SUR", campos=["CAÑO SUR"], periodo="2026-05"
    )
    assert resultado["sin_datos"] is False


@pytest.mark.unit
def test_sin_eventos_en_el_mes_declara_el_periodo() -> None:
    repo = RepoMantenimientosFalso(
        [_evento("OTRO", datetime(2020, 1, 1), fin=datetime(2020, 2, 1))]
    )
    resultado = MantenimientosService(repo).eventos(  # type: ignore[arg-type]
        entidad="CASTILLA", campos=["CASTILLA"], periodo="2026-05"
    )
    assert resultado["sin_datos"] is True
    assert resultado["meta"]["periodo"] == "Mayo 2026"


# ── Diferidas ───────────────────────────────────────────────────────────────


@pytest.fixture
def bd_diferidas(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """SQLite temporal con la forma REAL de AVM_DATADIF (18 columnas)."""
    from src.core.config import get_settings

    def _crear(filas: list[tuple[Any, ...]]) -> Any:
        ruta = tmp_path / "dif.db"
        conexion = sqlite3.connect(ruta)
        conexion.execute(
            "CREATE TABLE AVM_DATADIF ("
            "id_row INTEGER, VICE TEXT, GERENCIA TEXT, AREA TEXT, CAMPO TEXT, "
            "EVENT_DATE TEXT, COMPLETION TEXT, INI_DATE TEXT, END_DATE TEXT, "
            "CAUSE_NIVEL2 TEXT, CAUSE_NIVEL3 TEXT, CAUSE_NIVEL4 TEXT, "
            "CAUSE_NIVEL5 TEXT, CAUSE TEXT, COMENTARIO TEXT, "
            "ACEITE_PERDIDO REAL, AGUA_PERDIDO REAL, GAS_PERDIDO REAL)"
        )
        conexion.executemany(
            "INSERT INTO AVM_DATADIF VALUES (" + ",".join("?" * 18) + ")", filas
        )
        conexion.commit()
        conexion.close()
        monkeypatch.setenv("DIFERIDAS_DB_PATH", str(ruta))
        get_settings.cache_clear()
        return ruta

    yield _crear
    get_settings.cache_clear()


def _fila_dif(
    campo: str,
    pozo: str,
    anio: str,
    causa_n2: str,
    causa_n4: str,
    ini: str = "A",
    aceite: float = 0.0,
    gas: float = 0.0,
) -> tuple[Any, ...]:
    return (
        1,
        "VAS",
        "GER",
        campo,
        campo,
        f"{anio}-05-01",
        pozo,
        ini,
        "F",
        causa_n2,
        "N3",
        causa_n4,
        "N5",
        "C",
        "",
        aceite,
        0.0,
        gas,
    )


@pytest.mark.unit
def test_sin_bd_degrada_con_motivo(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.config import get_settings

    monkeypatch.setenv("DIFERIDAS_DB_PATH", "")
    get_settings.cache_clear()
    resultado = DiferidasService().frecuencia(entidad="CASTILLA")
    assert resultado["sin_datos"] is True
    assert "no disponible" in resultado["motivo"]
    get_settings.cache_clear()


@pytest.mark.unit
def test_un_evento_de_varios_dias_cuenta_como_un_incidente(bd_diferidas: Any) -> None:
    """El grano es día-pozo: sin colapsar, un evento de 3 días contaría 3 veces
    y el Pareto mediría duración, no frecuencia."""
    bd_diferidas(
        [
            _fila_dif("CASTILLA", "P1", "2025", "Operacional", "Falla", ini="EV1"),
            _fila_dif("CASTILLA", "P1", "2025", "Operacional", "Falla", ini="EV1"),
            _fila_dif("CASTILLA", "P1", "2025", "Operacional", "Falla", ini="EV1"),
        ]
    )
    resultado = DiferidasService().frecuencia(entidad="CASTILLA", campos=["CASTILLA"])
    assert resultado["meta"]["total_incidentes"] == 1


@pytest.mark.unit
def test_el_volumen_se_suma_sobre_todas_las_filas_dia(bd_diferidas: Any) -> None:
    """Al revés que los incidentes: el volumen perdido SÍ se acumula por día."""
    bd_diferidas(
        [
            _fila_dif("CASTILLA", "P1", "2025", "Op", "Falla", ini="EV1", aceite=100.0),
            _fila_dif("CASTILLA", "P1", "2025", "Op", "Falla", ini="EV1", aceite=150.0),
        ]
    )
    resultado = DiferidasService().frecuencia(entidad="CASTILLA", campos=["CASTILLA"])
    assert resultado["impacto"]["CRUDO"]["total"] == 250


@pytest.mark.unit
def test_entidad_sin_diferidas_devuelve_vacio_cacheable(bd_diferidas: Any) -> None:
    bd_diferidas([_fila_dif("OTRO", "P1", "2025", "Op", "Falla")])
    resultado = DiferidasService().frecuencia(entidad="CASTILLA", campos=["CASTILLA"])
    assert resultado["sin_datos"] is True
    assert resultado["meta"]["total_incidentes"] == 0


@pytest.mark.unit
def test_el_pareto_reparte_por_anio(bd_diferidas: Any) -> None:
    bd_diferidas(
        [
            _fila_dif("CASTILLA", "P1", "2023", "Operacional", "F1", ini="A"),
            _fila_dif("CASTILLA", "P2", "2024", "Operacional", "F1", ini="B"),
            _fila_dif("CASTILLA", "P3", "2025", "Entorno", "F2", ini="C"),
        ]
    )
    resultado = DiferidasService().frecuencia(entidad="CASTILLA", campos=["CASTILLA"])
    por_grupo = {p["grupo"]: p for p in resultado["pareto"]}
    assert por_grupo["Operacional"]["total"] == 2
    assert por_grupo["Operacional"]["anios"]["2023"] == 1
    assert por_grupo["Entorno"]["total"] == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    ("pct", "esperado"),
    [
        ({"2024": 10.0, "2025": 20.0}, "empeora"),
        ({"2024": 20.0, "2025": 10.0}, "mejora"),
        ({"2024": 10.0, "2025": 10.3}, "estable"),  # <=0,5 pp es ruido
    ],
)
def test_clasificacion_de_tendencia(pct: dict[str, float], esperado: str) -> None:
    assert clasificar_tendencia(pct) == esperado


@pytest.mark.unit
def test_la_tendencia_solo_lista_lo_que_empeora(bd_diferidas: Any) -> None:
    """Decisión del usuario 2026-07-24: la tarjeta muestra solo el deterioro."""
    bd_diferidas(
        [
            _fila_dif("CASTILLA", f"P{i}", "2024", "Op", "MEJORA", ini=f"M{i}")
            for i in range(10)
        ]
        + [_fila_dif("CASTILLA", "PX", "2025", "Op", "EMPEORA", ini="X")]
    )
    resultado = DiferidasService().frecuencia(entidad="CASTILLA", campos=["CASTILLA"])
    causas = {t["causa"] for t in resultado["tendencia"]}
    assert "EMPEORA" in causas
    assert "MEJORA" not in causas


@pytest.mark.unit
def test_el_resultado_se_cachea_entre_llamadas(bd_diferidas: Any) -> None:
    """Los datos son históricos y estáticos: recalcular sería tirar ~0,7 s."""
    bd_diferidas([_fila_dif("CASTILLA", "P1", "2025", "Op", "F")])
    servicio = DiferidasService()
    primero = servicio.frecuencia(entidad="CASTILLA", campos=["CASTILLA"])
    segundo = servicio.frecuencia(entidad="CASTILLA", campos=["CASTILLA"])
    assert primero is segundo
